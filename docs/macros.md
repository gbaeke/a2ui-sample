# A2UI macros, and what they would fix here

Written on 2026-11-13. Macros are not used in this sample yet. Everything below about how they
work comes from the A2UI macros guide and the installed SDK; the section on applying them to this
sample is a design sketch that has not been run.

## The problem they would solve

In the LLM version of the agent (`agent/hours_agent/llm.py`), data reaches the screen like this:

1. A tool (`get_week`, `add_hours`, `approve_week`, `get_project_budgets`) returns the real data to
   the model as text.
2. The model writes that data again, by hand, into the A2UI block it sends to the browser, for
   example `$/entries = [...]` and `$/approved = true`.
3. The A2UI SDK checks that the block fits the catalogs. It does not check the values.

So the grid can show a wrong number, or an "Approved" badge when the model never called
`approve_week`. The canned version (`agent/hours_agent/canned.py`) does not have this risk,
because code fills in the data.

## What a macro is

A macro is a Python function on the agent, decorated with `@macro`, that returns a tree of catalog
components. To the model it looks like one more component it can call. Before anything is sent to
the browser, the SDK runs the function and replaces the call with the components it returned.

- The model sees: a component signature generated from the function's parameters and docstring.
- The renderer sees: only components it already implements. It never knows a macro was involved.
- The function is ordinary server code, so it can take an identifier from the model, look the
  record up, and fill in the values itself.

That last point is what addresses the problem above: the model picks what to show, and code
supplies the numbers.

The guide lists four reasons to use macros:

1. Fewer output tokens and less latency: one call instead of a nested component tree.
2. Consistent layout, because server code builds the hierarchy.
3. Server-side data lookup from an identifier the model passes.
4. New composite components ship with an agent deployment alone, with no client change.

## How it works

`MacroExpander` acts on both sides of the model call:

```
before the call:  catalogs + macro schemas  ──▶  prompt snippet the model reads
after the call:   model output with macro calls  ──▶  expanded catalog components  ──▶  renderer
```

Example from the guide. The macro:

```python
from a2ui.builder.v1_0 import Card, Column, DynamicString, Text
from a2ui.transformers.macros import macro


@macro
def FlightCard(flight: str, route: str, status: DynamicString) -> Card:
    """Summary card for a flight with a live status line.

    Args:
        flight: Flight number, such as "OS 87".
        route: Departure and arrival cities, such as "Vienna to New York".
        status: Current status text or data binding.
    """
    return Card(
        child=Column(
            children=[
                Text(text=f"### {flight}"),
                Text(text=route, variant="caption"),
                Text(text=status),
            ]
        )
    )
```

What the model writes:

```text
<a2ui>
$/flight/status = "Boarding"
root = FlightCard("OS 87", "Vienna to New York", $/flight/status)
</a2ui>
```

What the renderer receives: a `Card`, a `Column` and three `Text` components, with the two static
strings baked in and the `/flight/status` binding kept live.

Wiring, as the guide shows it:

```python
from a2ui.core.basic_catalog import BasicCatalog
from a2ui.parser import A2uiPart
from a2ui.processor import A2uiRequestProcessor
from a2ui.transformers.macros import MacroExpander

expander = MacroExpander([FlightCard], on_error="raise")
inference_catalogs = expander.transform_catalogs([basic_catalog, custom_catalog])

processor = A2uiRequestProcessor(catalogs=inference_catalogs)
system_prompt = processor.prompt_snippet

parts = processor.parse_response(llm_output)
messages = [m for p in parts if isinstance(p, A2uiPart) for m in p.a2ui]
transport_messages = expander.transform_to_transport(messages)
```

## Rules worth knowing

- **Parameter types decide what the model may pass.** Plain `str`, `int`, `float`, `bool` take only
  literal values, baked in when the macro runs. `DynamicString`, `DynamicNumber`, `DynamicBoolean`
  and `DynamicStringList` also take a data binding, which stays live in the browser. `Action`
  takes an event or function call.
- **Arguments are untrusted.** They are model output. The guide says to validate identifiers
  against backend data.
- **One expander per session.** `MacroExpander` tracks which catalogs each surface uses across
  turns.
- **Errors.** The default `on_error="passthrough"` logs a failing macro and leaves it unexpanded,
  which the renderer cannot draw. `on_error="raise"` raises `A2uiValidationError`, which fits the
  retry loop this sample already has.
- **Hiding base components.** `passthrough_components=[...]` limits which catalog components the
  model sees next to the macros. `passthrough_components=[]` exposes only the macros.
- **Custom catalogs need generated builders.** Builder classes for the basic catalog ship in
  `a2ui.builder.v1_0`. For a custom catalog such as `hours_catalog.json`, the A2UI CLI generates
  them: `a2ui codegen --lang python --catalog <file> --out <module>.py --catalog-name <name>`.
- **Python only.** The guide says other languages are coming.

## Availability here

- `a2ui.transformers.macros` and `a2ui.builder.v1_0` are in the installed `a2ui-agent-sdk` 0.11.0.
  Importing `macro` and `MacroExpander` works in the agent's environment.
- The `a2ui` CLI is not installed on this machine. It is a separate download (CLI v0.3.0 was
  released on 2026-11-11).

## How it could apply to this sample

A sketch, not tested. Two macros that take no data from the model:

| Macro | Model passes | Macro does |
| --- | --- | --- |
| `Timesheet(on_approve: Action)` | only the action | Reads the conversation's timesheet and returns a `WeekGrid` with the real week, entries and approved flag. |
| `ProjectBudgets()` | nothing | Reads the projects and returns a `Column` of `ProjectBudgetCard`s, each with its `select_project` action. |

The model's whole answer to "show my week" would then be something like
`root = Timesheet(Event("approve_week"))`.

What it would take:

1. Install the A2UI CLI and generate Python builders from `catalog/hours_catalog.json`.
2. Write the two macros. They need the current conversation's timesheet, so they would be created
   per conversation, the way the tools in `llm.py` are.
3. Add a `MacroExpander` per conversation, build the prompt from its inference catalogs, and pass
   the model's messages through `transform_to_transport` before sending.
4. Optionally hide `WeekGrid` and `ProjectBudgetCard` from the model with
   `passthrough_components`, so it can only reach them through the macros.

Open questions:

- **Streaming.** The guide's example parses a complete response with `parse_response`. This sample
  feeds the model's text into a stream and sends messages as they complete. Whether
  `transform_to_transport` behaves well on those partial messages is not known.
- **Data-only updates.** Today, logging hours changes `/entries` without resending components.
  With values baked in by a macro, an update would resend the components, unless the macro binds
  to data paths and code (not the model) writes the data model. The second option keeps cheap
  updates but is more work.
- **The published web renderer.** Expanded components are stamped with a catalog id by the SDK.
  The published renderer accepts `catalogId` and rejects `@catalogId` (see the README), so which
  key the expander emits needs checking.

## Without macros

The same guarantee can be had with less machinery: let the model write only the layout, bound to
data paths, and have agent code send the `updateDataModel` messages from the tool results. The
model then never types a number. This keeps cheap data-only updates and needs no CLI or generated
builders, but it is custom code and not an A2UI feature.

## Sources

- Macros guide: https://a2ui.org/guides/macros/
- Macros README:
  https://github.com/a2ui-project/a2ui/blob/main/python/a2ui_agent/src/a2ui/transformers/macros/README.md
- Community sample (FastAPI agent, React client):
  https://github.com/a2ui-project/a2ui/tree/main/samples/community/macros
