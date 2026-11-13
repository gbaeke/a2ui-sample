import type {ReactCatalogComponent} from '@a2ui/react';
import {
  type ActionPayload,
  MessageProcessor,
  basicCatalog,
  injectBasicCatalogStyles,
} from '@a2ui/web_core/v1_0';

import {hoursCatalog} from './catalog/hoursCatalog';

injectBasicCatalogStyles();

const A2UI_MIME_TYPE = 'application/a2ui+json';

/** An A2A part as relayed by the /a2a middleware. */
interface Part {
  kind: string;
  text?: string;
  data?: unknown;
  metadata?: {mimeType?: string};
}

type ServerEvent = {contextId?: string; parts: Part[]} | {error: string};

export type SessionEvent =
  | {kind: 'user-text'; text: string}
  | {kind: 'agent-text'; text: string}
  | {kind: 'sent'; payload: unknown}
  | {kind: 'received'; payload: unknown}
  | {kind: 'error'; payload: unknown}
  | {kind: 'busy'; busy: boolean};

/**
 * Owns the A2UI state for the page and the conversation with the agent.
 *
 * Agent replies arrive as A2A parts: text parts go to the chat, A2UI data
 * parts go into the MessageProcessor, which updates the surfaces. User
 * interactions come back out of the processor as `action` payloads and are
 * sent to the agent the same way typed text is.
 */
export class Session {
  private listener: (event: SessionEvent) => void = () => {};
  private contextId: string | undefined;

  readonly processor = new MessageProcessor<ReactCatalogComponent>(
    [basicCatalog, hoursCatalog],
    (action: ActionPayload) => void this.post({a2ui: {version: '1.0', action}}),
  );

  onEvent(listener: (event: SessionEvent) => void): void {
    this.listener = listener;
  }

  sendText(text: string): Promise<void> {
    this.listener({kind: 'user-text', text});
    return this.post({text});
  }

  private async post(body: {text?: string; a2ui?: unknown}): Promise<void> {
    const request = {
      ...body,
      contextId: this.contextId,
      // Sent on every message: the catalogs this renderer can draw.
      metadata: {
        a2uiRendererCapabilities: this.processor.getRendererCapabilities({versions: ['1.0']}),
      },
    };
    this.listener({kind: 'sent', payload: request});
    this.listener({kind: 'busy', busy: true});
    try {
      const response = await fetch('/a2a', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(request),
      });
      if (!response.ok || !response.body) {
        throw new Error(`/a2a answered ${response.status} ${response.statusText}`);
      }
      for await (const event of readServerEvents(response.body)) {
        this.handle(event);
      }
    } catch (error) {
      this.listener({kind: 'error', payload: String(error)});
    } finally {
      this.listener({kind: 'busy', busy: false});
    }
  }

  private handle(event: ServerEvent): void {
    if ('error' in event) {
      this.listener({kind: 'error', payload: event.error});
      return;
    }
    this.contextId = event.contextId ?? this.contextId;
    for (const part of event.parts) {
      if (part.kind === 'text' && part.text) {
        this.listener({kind: 'agent-text', text: part.text});
      } else if (part.kind === 'data' && part.metadata?.mimeType === A2UI_MIME_TYPE) {
        this.listener({kind: 'received', payload: part.data});
        for (const error of this.processor.processMessagesWithErrors(part.data)) {
          this.listener({kind: 'error', payload: error});
        }
      }
    }
  }
}

/** Parses a `text/event-stream` body into the JSON of each `data:` line. */
async function* readServerEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ServerEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const {done, value} = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, {stream: true});
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      if (block.startsWith('data: ')) yield JSON.parse(block.slice(6)) as ServerEvent;
    }
  }
}
