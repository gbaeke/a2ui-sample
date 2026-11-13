# Rendering these components in ChatGPT or Claude through an MCP server

Written on 2026-11-13. Nothing in this note is built or tested in this sample. It describes what
would be needed, based on the A2UI guide "Render A2UI Inside an MCP App", the MCP Apps
documentation and the connector help pages of Anthropic and OpenAI (see Sources).

## The idea

ChatGPT and Claude have no A2UI renderer of their own. Both support MCP Apps: an MCP server
attaches a small web page to a tool, and the chat app shows that page in a sandboxed iframe inside
the conversation.

The A2UI renderer goes inside that page. The MCP server returns A2UI messages as tool results, the
page draws them, and the chat app only sees an iframe.

## Components

```
 ChatGPT / Claude  (the host, runs in the vendor's cloud and the user's browser)
┌──────────────────────────────────────────────────────────────────────────────┐
│  host model                         conversation                             │
│  picks a tool, e.g. show_week      ┌──────────────────────────────────────┐  │
│        │                           │ sandboxed iframe: the MCP App page   │  │
│        │                           │                                      │  │
│        │        tool result        │  glue code (ext-apps `App`)          │  │
│        │   ┌──────────────────────▶│     │ A2UI messages                  │  │
│        │   │                       │     ▼                                │  │
│        │   │                       │  A2UI MessageProcessor               │  │
│        │   │                       │     │                                │  │
│        │   │                       │     ▼                                │  │
│        │   │                       │  basic catalog + hoursCatalog.tsx    │  │
│        │   │                       │  (WeekGrid, ProjectBudgetCard, ...)  │  │
│        │   │   click: tools/call   │     │                                │  │
│        │   │◀──────────────────────│◀────┘ action                         │  │
│        ▼   │                       └──────────────────────────────────────┘  │
│  MCP client in the host                                                      │
└────────┬─────────────────────────────────────────────────────────────────────┘
         │  MCP over Streamable HTTP, public HTTPS URL
         ▼
 MCP server  (new, in this repo)
┌──────────────────────────────────────────────────────────────────────────────┐
│  tools for the model:   show_week, add_hours, show_budgets                   │
│  tools for the page:    approve_week, select_project                         │
│  resource:              ui://hours/app  (the page, one HTML file)            │
│                                                                              │
│  A2UI message builder (code, like canned.py)  ◀──  timesheet data (data.py)  │
└──────────────────────────────────────────────────────────────────────────────┘
```

The existing agent, A2A and the `/a2a` middleware are not in this picture. See "Who writes the
A2UI" for the variant that keeps the agent.

## What is needed

### 1. An MCP server

A new folder next to `agent/`, for example `mcp/`. It can be Python (the `mcp` package) or
TypeScript (`@modelcontextprotocol/sdk` with `@modelcontextprotocol/ext-apps/server`). Python
lets it reuse `data.py` and the message-building code in `canned.py`.

It registers three things:

| What | Details |
| --- | --- |
| Entry tools, for the model | `show_week`, `add_hours`, `show_budgets`. Each carries `_meta.ui.resourceUri: "ui://hours/app"` so the host knows which page to show, and `_meta.ui.visibility: ["model"]`. |
| Callback tools, for the page | `approve_week`, `select_project`, with `_meta.ui.visibility: ["app"]`. Only the page calls these, on a click. |
| The UI resource | `ui://hours/app`, MIME type `text/html;profile=mcp-app`, whose content is the bundled page. |

A tool result carries the A2UI messages as an embedded resource, plus a line of text for the
model:

```json
{
  "content": [
    {"type": "text", "text": "Showing week 2026-W46: 38 hours, not approved."},
    {
      "type": "resource",
      "resource": {
        "uri": "a2ui://hours/week",
        "mimeType": "application/a2ui+json",
        "text": "[{\"version\": \"1.0\", \"createSurface\": { ... }}]"
      }
    }
  ]
}
```

The text part matters: it is all the host model learns about the result, so it should state the
facts the model may need to answer follow-up questions.

The guide advises validating the messages on the server before returning them
(`a2ui.utils.validate_payload` in Python), because an invalid message otherwise fails inside the
iframe where the server cannot see it.

### 2. The page

A second, small build of what `web/` already has: React, `@a2ui/react`, the basic catalog and
`web/src/catalog/hoursCatalog.tsx`. The chat, wire log and `session.ts` are not needed; the host
is the chat.

The glue code replaces `session.ts`. In outline, following the guide:

```ts
import {App} from '@modelcontextprotocol/ext-apps';

const app = new App({name: 'Project Hours', version: '1.0.0'});

const processor = new MessageProcessor([basicCatalog, hoursCatalog], async action => {
  // A click: call the server tool with the action's name and context.
  const result = await app.callServerTool({name: action.name, arguments: action.context});
  applyToolResult(result);
});

// The result of the tool the model called.
app.ontoolresult = result => applyToolResult(result);
await app.connect();

function applyToolResult(result) {
  // Take the application/a2ui+json resources out of result.content
  // and pass their messages to processor.processMessages(...).
}
```

The guide's example uses the Lit renderer. Using `@a2ui/react` the same way should work, since
both sit on the same `MessageProcessor`, but that is an assumption.

Build and sandbox rules from the guide:

- **One HTML file.** The page is injected into an iframe with no base URL, so separate script or
  style files cannot load. With Vite: `vite-plugin-singlefile`.
- **No browser storage.** `localStorage`, `sessionStorage`, IndexedDB and cookies throw in the
  sandbox. Keep short-lived state in the A2UI data model and the rest on the server.
- **No network by default.** The host's content security policy blocks outgoing requests, external
  images and fonts. Domains that are needed are declared in `_meta.ui.csp` on the resource.
- **Theme.** The page can read the host's light or dark setting (`app.getHostContext()?.theme`,
  `app.onhostcontextchanged`) and set the `a2ui-light` or `a2ui-dark` class. Colours and fonts are
  otherwise the page's own (see [styling.md](styling.md)).

### 3. Who writes the A2UI

In ChatGPT or Claude, the host model only chooses a tool and its arguments. The MCP server has to
produce the A2UI messages. Two options:

| | Code writes them | The server calls the existing agent |
| --- | --- | --- |
| How | Fixed layout per tool, data from `data.py`, as `canned.py` does today | The MCP server sends the request to the agent over A2A, as the text client does, and relays the A2UI parts |
| Models per turn | One (the host's) | Two (the host's and the agent's) |
| Numbers on screen | Always the real data | Retyped by the agent's model (see [macros.md](macros.md)) |
| Reuses | `data.py`, the messages in `canned.py`, `hoursCatalog.tsx` | The whole agent |

The first option is the simple one and fits this sample, where every screen maps to one tool. The
second only makes sense when the agent composes screens that code cannot foresee.

### 4. A public address

- ChatGPT and claude.ai call the MCP server from the vendor's cloud, not from the user's machine.
  Anthropic's help page says the server "must be reachable over the public internet"; OpenAI's
  asks for "a public HTTPS endpoint" that supports Streamable HTTP, typically at `/mcp`.
- For a test, a tunnel to the local server is enough. The MCP Apps build guide uses
  `npx cloudflared tunnel --url http://localhost:3001`.
- OpenAI also offers a "Secure MCP Tunnel" for servers that should not be public.

### 5. Registration in the client

| Client | Where | Notes |
| --- | --- | --- |
| Claude | Customize > Connectors > "+ Add" > "Add custom connector" (on Team and Enterprise: Organization settings > Connectors, by an owner) | Available on all plans; Free is limited to one custom connector. Sign-in can be OAuth, a fixed header, or none. |
| ChatGPT | chatgpt.com/plugins > plus button > "Add custom MCP server" | The page mentions account and workspace policies but no plan list. Changes need "Refresh" and a new conversation. |

Both help pages describe interactive UI from connectors. Neither says in so many words that a
custom connector's MCP App will render, so that is the first thing to test.

### 6. State and sign-in

- **Whose timesheet.** A2A gave the agent a `contextId` per conversation. MCP has no such id; the
  server would key state by MCP session, or keep one shared timesheet for a demo.
- **Access.** A public URL with no sign-in lets anyone who has it call the tools. That is
  acceptable with the fake data here. Real data needs OAuth, which both clients support.

## One turn, step by step

1. The user types "show my week" in ChatGPT or Claude.
2. The host model calls `show_week`.
3. The MCP server builds the `createSurface` message with a `WeekGrid` bound to the data model,
   and returns it with a summary line.
4. The host sees `_meta.ui.resourceUri` on the tool, reads `ui://hours/app` and shows the page in
   an iframe.
5. The page receives the tool result, passes the A2UI messages to the `MessageProcessor`, and the
   grid appears.
6. The user clicks "Approve week". The page calls the `approve_week` tool through the host.
7. The server approves the week and returns an `updateDataModel` message. The grid shows
   "Approved". The host model is not involved in this step.

## Testing without a public address

- **`basic-host`**, an example in the `modelcontextprotocol/ext-apps` repository, is a local host
  that renders MCP Apps: `SERVERS='["http://localhost:3001/mcp"]' npm start`, then open
  `http://localhost:8080`.
- **MCP Inspector** (`npx @modelcontextprotocol/inspector@latest`) checks the tools and resources,
  without the chat.
- **Claude Desktop** can run local MCP servers from its config file and is listed as an MCP Apps
  host. Whether it shows app UIs from a local server has not been checked.

## Differences from the current sample

| | Current sample | Through an MCP App |
| --- | --- | --- |
| Chat UI | `web/` | ChatGPT or Claude |
| Model | Yours, through Agent Gateway | The host's |
| Writes the A2UI | The Deep Agent | Server code (or the agent, as an option) |
| Transport | A2A 0.3 | MCP, Streamable HTTP |
| Clicks | A2UI `action` sent to the agent | A tool call from the page |
| Look | The client's own | The page's own, inside the host's frame |
| Reused as is | | `hoursCatalog.tsx`, `catalog/hours_catalog.json`, `data.py` |

## Open points

- The published web renderer accepts `catalogId` and rejects `@catalogId` on components from a
  non-default catalog (see the README). The server's messages must match what the bundled
  renderer accepts.
- The guide's community sample still sends A2UI 0.8; its walkthrough text covers 1.0 and 0.9.1.
- `@modelcontextprotocol/ext-apps` 2.x needs the 2.x MCP SDK packages; the build guide and the API
  pages do not name the same package set, so versions need checking at install time.
- Host support differs per client; the MCP documentation keeps a client matrix.

## Sources

- A2UI guide, "Render A2UI Inside an MCP App": https://a2ui.org/guides/a2ui-in-mcp-apps/
- MCP Apps overview: https://modelcontextprotocol.io/docs/extensions/apps
- MCP Apps build guide: https://modelcontextprotocol.io/extensions/apps/build.md
- MCP Apps SDK reference: https://apps.extensions.modelcontextprotocol.io/api/
- Claude, custom connectors using remote MCP:
  https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp
- ChatGPT, connect and test a custom MCP server:
  https://developers.openai.com/apps-sdk/deploy/connect-chatgpt
- Google, "A2UI + MCP Apps": https://developers.googleblog.com/en/a2ui-and-mcp-apps/
