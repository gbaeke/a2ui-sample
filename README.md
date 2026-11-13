# a2ui

A sample of [A2UI 1.0](https://a2ui.org/): a project-hours assistant whose agent answers with UI
built from components declared in advance (a custom catalog), not with free-form markup.

This is a sample, not a production setup.

## Layout

| Path | What it is |
| --- | --- |
| `catalog/hours_catalog.json` | The contract: three domain components (`WeekGrid`, `ProjectBudgetCard`, `StatusPill`). The agent reads it to build its prompt and validate output; the web app implements it. |
| `web/` | React + Vite renderer using `@a2ui/react`, with the basic catalog for layout and the hours catalog for domain components. |
| `web/middleware/a2a.ts` | The service in between: a Vite dev-server plugin. The browser POSTs to `/a2a`; the plugin calls the agent over A2A and relays the reply as server-sent events. |
| `cli/hours_cli.py` | A second renderer: a text client in one Python file, standard library only. It talks A2A to the agent directly and draws the same surfaces as text. |
| `agent/` | Python A2A server (`a2a-sdk`, `a2ui-a2a`). A Deep Agent (`hours_agent/llm.py`) with timesheet tools answers with A2UI 1.0 messages; `a2ui-agent-sdk` supplies the catalog prompt and validates what the model writes. `hours_agent/canned.py` is a no-LLM stand-in. |

```
browser ──POST /a2a──▶ Vite middleware ──A2A (JSON-RPC + SSE)──▶ agent :10002
        ◀──── SSE ────                 ◀──── text + A2UI parts ────
```

## Status

1. **Done:** the web app renders A2UI 1.0 messages with the custom catalog.
2. **Done:** the agent returns surfaces over A2A through the middleware, and actions (approve
   week, select project) travel back the same way.
3. **Done:** an LLM generates the surfaces from the catalog and handles the actions.

## Run it

The agent needs an OpenAI-compatible endpoint that supports the Responses API. By default it uses
a local [Agent Gateway](https://agentgateway.dev/) on port 4000 and the model `azure-gpt-6.1-sol`.
Override with `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.

Two terminals:

```bash
cd agent
uv run hours-agent            # A2A server on http://localhost:10002
uv run hours-agent --canned   # same, with canned replies and no LLM
```

```bash
cd web
npm install
npm run dev                   # http://localhost:5173
```

Try “Show my week”, “Log 2 hours on Friday for Contoso”, “Show project budgets”, then click
“Approve week” or a budget card. The wire log on the right shows every message in both directions.

## Text client

With the agent running:

```bash
python3 cli/hours_cli.py
```

Type a message, or the number shown next to an action (such as `[1] Approve week`) to trigger it.
The agent does not know which client it is talking to: it sends the same A2UI messages, and this
client draws `WeekGrid` as a text table and `ProjectBudgetCard` as a bar of block characters.

It is a minimal hand-written renderer, not the A2UI SDK. It supports what this sample uses
(literal values, `@path` bindings, static child lists, event actions) and prints a placeholder for
anything else.

## Basic catalog only

The domain components are optional. To see the agent compose the screens itself from A2UI's basic
catalog (`Card`, `Column`, `Row`, `Text`, `Divider`, `Button`), let the renderer announce only that
catalog:

```bash
python3 cli/hours_cli.py --basic     # text client
# web: http://localhost:5173/?basic
```

The agent then uses a second set of UI conventions (`UI_BASIC` in `agent/hours_agent/llm.py`). The
screens are plainer and take many more messages: the model writes every cell and works out the
totals itself.

## How a turn works

1. The browser POSTs the text, or the `action` from a click, to `/a2a`, with the catalogs its
   renderer supports.
2. The middleware sends it to the agent as an A2A message with the A2UI extension activated.
3. The agent appends the A2UI prompt snippet for those catalogs to the system prompt and runs the
   Deep Agent, which calls the timesheet tools.
4. The model answers in A2UI Express, a compact notation inside `<a2ui>` tags. The SDK validates
   it against the catalogs and compiles it to A2UI 1.0 JSON messages. If validation fails, the
   error goes back to the model for one more try.
5. Text and A2UI messages stream back as A2A parts; the renderer applies them to its surfaces.

## Known limitation

The model copies the numbers from the tool results into the screen by hand, and nothing checks
them. The screen can therefore differ from the real data. See [docs/macros.md](docs/macros.md) for
the A2UI feature that addresses this and how it could be applied here.

## Further notes

- [docs/a2a-version.md](docs/a2a-version.md): why the sample is on A2A 0.3 and how to move to 1.0.
- [docs/macros.md](docs/macros.md): A2UI macros and how they could be applied here.
- [docs/a2ui-vs-ag-ui-tool-rendering.md](docs/a2ui-vs-ag-ui-tool-rendering.md): A2UI compared with
  AG-UI and React components that render tool results.

## Things the published packages do differently from the 1.0 spec

Found with `@a2ui/react` and `@a2ui/web_core` 0.15.0:

- A component from a non-default catalog is marked with `catalogId`, not `@catalogId` as the final
  spec says. `@catalogId` is rejected. The unreleased code in the A2UI repo uses `@catalogId`, so
  this will change in a later release.
- A component bound to an array does not re-render when only a nested element is updated
  (`/entries/0/hours/4`). Replace the whole array instead.
- `@a2ui/markdown-it` 0.2.2 requires `@a2ui/web_core` 0.14, so it is left out and `Text` does not
  render Markdown.
- `zod` must be version 3; the A2UI packages do not accept zod 4.

With `a2ui-a2a` 0.3.0 (Python):

- It requires `a2a-sdk` 0.3, so the agent speaks A2A 0.3, not A2A 1.0. The web middleware uses
  `@a2a-js/sdk` 0.3 to match. See [docs/a2a-version.md](docs/a2a-version.md).
- It puts one A2UI message in each A2A data part. The 1.0 extension spec says a part holds a list.
