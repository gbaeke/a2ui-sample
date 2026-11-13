/**
 * The service between the browser and the agent, as a Vite dev-server plugin.
 *
 * The browser POSTs a small JSON body to /a2a. This wraps it in an A2A
 * message, calls the agent with the A2UI extension activated, and relays the
 * reply parts back as server-sent events. It keeps the A2A client, the agent
 * URL and (in a real app) credentials out of the browser.
 */
import {randomUUID} from 'node:crypto';
import type {IncomingMessage, ServerResponse} from 'node:http';

import type {MessageSendParams, Part} from '@a2a-js/sdk';
import {A2AClient} from '@a2a-js/sdk/client';
import type {Plugin} from 'vite';

const AGENT_URL = process.env.AGENT_URL ?? 'http://localhost:10002';
const A2UI_EXTENSION = 'https://a2ui.org/a2a-extension/a2ui/v1.0';
const A2UI_MIME_TYPE = 'application/a2ui+json';
const MAX_BODY_BYTES = 1024 * 1024;

/** What the browser sends. Exactly one of `text` or `a2ui` is set. */
interface BrowserRequest {
  text?: string;
  /** One A2UI renderer-to-agent message, such as `{version, action}`. */
  a2ui?: Record<string, unknown>;
  contextId?: string;
  /** Goes on the A2A message as-is: a2uiRendererCapabilities and friends. */
  metadata?: Record<string, unknown>;
}

/** What the browser gets back, one per SSE `data:` line. */
type BrowserEvent = {contextId?: string; parts: Part[]} | {error: string};

const withA2uiExtension: typeof fetch = (input, init) => {
  const headers = new Headers(init?.headers);
  headers.set('X-A2A-Extensions', A2UI_EXTENSION);
  return fetch(input, {...init, headers});
};

let client: Promise<A2AClient> | undefined;
function getClient(): Promise<A2AClient> {
  client ??= A2AClient.fromCardUrl(`${AGENT_URL}/.well-known/agent-card.json`, {
    fetchImpl: withA2uiExtension,
  }).catch(error => {
    client = undefined; // Retry on the next request, e.g. once the agent is up.
    throw error;
  });
  return client;
}

async function readBody(req: IncomingMessage): Promise<string> {
  let body = '';
  for await (const chunk of req) {
    body += chunk;
    if (body.length > MAX_BODY_BYTES) throw new Error('Request body too large');
  }
  return body;
}

function toSendParams(request: BrowserRequest): MessageSendParams {
  const part: Part = request.a2ui
    ? {kind: 'data', data: request.a2ui, metadata: {mimeType: A2UI_MIME_TYPE}}
    : {kind: 'text', text: request.text ?? ''};
  return {
    message: {
      kind: 'message',
      messageId: randomUUID(),
      role: 'user',
      parts: [part],
      contextId: request.contextId,
      metadata: request.metadata,
    },
  };
}

async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const send = (event: BrowserEvent) => res.write(`data: ${JSON.stringify(event)}\n\n`);

  let request: BrowserRequest;
  try {
    request = JSON.parse(await readBody(req)) as BrowserRequest;
  } catch (error) {
    res.statusCode = 400;
    res.end(String(error));
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });

  try {
    const a2a = await getClient();
    for await (const event of a2a.sendMessageStream(toSendParams(request))) {
      if (res.destroyed) break; // Browser went away.
      if (event.kind === 'status-update' && event.status.message?.parts.length) {
        send({contextId: event.contextId, parts: event.status.message.parts});
      } else if (event.kind === 'message') {
        send({contextId: event.contextId, parts: event.parts});
      } else if (event.kind === 'task') {
        send({contextId: event.contextId, parts: []});
      }
    }
  } catch (error) {
    console.error('[a2a]', error);
    const message = error instanceof Error ? error.message : String(error);
    send({error: `Could not reach the agent at ${AGENT_URL}: ${message}`});
  }
  res.end();
}

export function a2aMiddleware(): Plugin {
  return {
    name: 'a2a-middleware',
    configureServer(server) {
      server.middlewares.use('/a2a', (req, res, next) => {
        if (req.method !== 'POST') return next();
        void handle(req, res);
      });
    },
  };
}
