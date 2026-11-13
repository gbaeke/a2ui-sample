# A2UI versus AG-UI with tool-rendering components

Written on 2026-11-13. The question: would AG-UI, with React components that render tool call
results, be more efficient than what this sample does?

Short answer: for this sample, yes. It would be cheaper per turn, faster, and it removes the risk
of wrong numbers on screen. What it gives up is the agent's ability to decide the screen.

No AG-UI version of this sample has been built. The comparison is reasoned from how the two
approaches work, not measured. The A2UI figures are from this sample.

## The two approaches

**A2UI (this sample).** The model writes a description of the screen, using components from a
catalog. The A2UI SDK validates it and compiles it to JSON messages, and the renderer draws them.

```
tool result ─▶ model ─▶ writes UI block ─▶ SDK validates + compiles ─▶ renderer ─▶ component
```

**AG-UI with tool rendering.** AG-UI is an event protocol: it streams text, tool calls, tool
results and state changes from the agent to the front end. The front end maps a tool name to a
React component and renders the tool's result with it. That mapping is a pattern the client adds,
as CopilotKit does; it is not part of the AG-UI protocol itself.

```
tool result ─▶ AG-UI event ─▶ front end looks up the component for that tool ─▶ component
                 model ─▶ one sentence of text
```

## Where tool rendering wins

| | A2UI in this sample | Tool rendering |
| --- | --- | --- |
| UI instructions in the prompt | About 26,000 characters on every turn (the generated catalog snippet) | None; only the tool schemas |
| What the model writes | A sentence plus a UI block that repeats the data | A tool call and a sentence |
| Where on-screen values come from | The model retypes them from the tool result | The tool result itself |
| Steps between model and screen | Parse, validate against the catalog, compile, retry on failure | None |
| Shared contract to maintain | `catalog/hours_catalog.json` plus matching React code | Tool result shapes plus matching React code |

The third row matters most. In the A2UI version nothing checks that the values the model wrote
match what the tool returned (see [macros.md](macros.md)). With tool rendering the model never
handles the values, so the problem does not exist.

## What you lose

- **Composition.** Each tool maps to one fixed component. The agent cannot put a grid and two
  budget cards on one surface, or lay out a screen nobody foresaw.
- **Decoupling.** The front end must know the agent's tool names and result shapes. With A2UI the
  contract is the catalog, so any agent that speaks it can drive the UI, including agents you do
  not own.
- **Other renderers.** A2UI has renderers for Flutter, SwiftUI, Jetpack Compose, Angular and Lit
  that draw the same messages. Tool rendering is implemented once per front end.
- **Agent-driven updates.** A2UI lets the agent change one value in an existing surface
  (`updateDataModel`). With tool rendering the equivalent is AG-UI's shared state, which you wire
  up yourself.
- **Interaction as part of the protocol.** A2UI defines how a click travels back (`action`). With
  tool rendering, the component calls back through whatever the client framework offers.

## For this sample

Every screen maps one-to-one to a tool:

| User asks | Tool | Screen |
| --- | --- | --- |
| Show my week | `get_week` | `WeekGrid` |
| Log hours | `add_hours` | `WeekGrid`, updated |
| Approve | `approve_week` | `WeekGrid`, approved |
| Show budgets | `get_project_budgets` | `ProjectBudgetCard` list |

That is the case tool rendering handles best. A2UI's flexibility goes unused here.

## When A2UI earns its cost

- The agent is a separate service with several clients, for example web and native mobile.
- The UI is driven by agents you do not control, such as remote agents reached over A2A.
- The model should decide what the screen looks like, not only which data to fetch.

If none of these apply, AG-UI with tool-rendering components is the better fit.

## Combining them

The two are not exclusive. A2UI can travel over AG-UI: the A2UI 1.0 announcement describes AG-UI
as its native transport, and CopilotKit supports it. A front end can render most tool results with
fixed components and use A2UI only for the screens that need composing.

Within A2UI, two things narrow the gap without changing transport:

- **Macros** move data lookup into server code, so the model only picks the component. See
  [macros.md](macros.md).
- **Code-written data.** Let the model write only the layout, bound to data paths, and have agent
  code send the `updateDataModel` messages from the tool results.

Neither removes the per-turn prompt cost of the catalog.
