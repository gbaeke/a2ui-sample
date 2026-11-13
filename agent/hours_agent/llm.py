"""LLM brain: a Deep Agent that answers with A2UI built from the catalogs.

The A2UI agent SDK does two things here. Before the model call it produces a
prompt snippet describing the components the renderer supports. During the
call it reads the model's text stream, validates each `<a2ui>` block against
the catalogs and turns it into A2UI 1.0 messages.
"""

from collections.abc import AsyncIterator
import json
import logging
import os
from typing import Any, Literal

from a2ui.core.exceptions import A2uiError
from a2ui.inference_formats import ExpressFormatFactory
from a2ui.parser import A2uiPart, TextPart
from a2ui.processor import A2uiGenerator, A2uiRequestProcessor, CatalogConfig
from deepagents import create_deep_agent
from langchain_core.messages import AIMessageChunk
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from .catalogs import CATALOGS, HOURS_ID
from .conversation import Conversation, Reply

logger = logging.getLogger(__name__)

# Any OpenAI-compatible endpoint. The default is a local Agent Gateway.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:4000/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "azure-gpt-6.1-sol")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "unused")

MAX_ATTEMPTS = 2
DAYS = ["mon", "tue", "wed", "thu", "fri"]

ROLE = """\
You are a project-hours assistant. You show the user's weekly timesheet and \
project budgets, log hours and approve weeks.

Rules:
- Get data with the tools. Never invent hours, projects or budgets.
- Answer with one short sentence of text, plus a UI surface when there is \
something to show. Do not repeat in text what the surface shows.
- These are simple requests: do not plan with todos, write files or start \
sub-agents.

Messages starting with [UI action] are not typed by the user: they report a \
click in a surface.
- approve_week: approve the week with the tool, then update the "week" surface.
- select_project: answer in text only, with one or two sentences about that \
project's hours against its budget. Leave the surface as it is.
"""

# With the hours catalog the model places ready-made domain components.
UI_HOURS = """\
UI conventions:
- Timesheet: surface id "week". Put week, approved and entries in the data \
model at /week, /approved and /entries and bind a WeekGrid to those paths. \
Give it onApprove=Event("approve_week", {week: $/week}).
- Budgets: surface id "budgets". One ProjectBudgetCard per project, each with \
onSelect=Event("select_project", {project: "<project name>"}).
- When a surface already exists and only its data changed (hours logged, week \
approved), update it with surface("<id>", update=true) and assign the new \
values to the data paths. Replace /entries as a whole array.
- Use the basic catalog (Column, Row, Text) for layout around these.
"""

# With only the basic catalog the model composes the screens itself.
UI_BASIC = """\
UI conventions:
- The renderer has no timesheet or budget components. Compose the screens \
yourself from the basic catalog (Card, Column, Row, Text, Divider, Button).
- Timesheet: surface id "week". Show the week label, a row per project with \
its hours per weekday (Mon-Fri) and its total, and a row of totals per day. \
While the week is not approved, add a Button "Approve week" with \
action=Event("approve_week", {week: "<week label>"}). Once approved, say so \
on the surface and leave the button out.
- Budgets: surface id "budgets". One Card per project with its client, hours \
used against budget, the percentage, and whether it is on track (below 80%), \
close to budget (80-100%) or over budget. Give each a Button "Details" with \
action=Event("select_project", {project: "<project name>"}).
- When the data of an existing surface changed, send its components again \
with surface("<id>", update=true).
"""

_generator = A2uiGenerator(
    catalogs=[CatalogConfig(catalog=c) for c in CATALOGS],
    inference_format_factory=ExpressFormatFactory(),
)
_model = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    # azure-gpt-6.1-sol only accepts tool calls on the Responses API.
    use_responses_api=True,
    streaming=True,
)
# Chat history per conversation, keyed by thread id.
_checkpointer = InMemorySaver()


def _tools(conv: Conversation) -> list[Any]:
  """Tools bound to one conversation's timesheet."""
  sheet = conv.timesheet

  @tool
  def get_week() -> str:
    """Returns the current week's timesheet: week label, approved flag and hours per project (Mon-Fri)."""
    return json.dumps(
        {k: sheet[k] for k in ("week", "approved", "entries")}
    )

  @tool
  def add_hours(
      project: str, day: Literal["mon", "tue", "wed", "thu", "fri"], hours: float
  ) -> str:
    """Adds hours to one project on one weekday and returns the updated timesheet."""
    if sheet["approved"]:
      return "Error: the week is approved and can no longer be changed."
    for entry in sheet["entries"]:
      if entry["project"].lower() == project.lower():
        entry["hours"][DAYS.index(day)] += hours
        return get_week.invoke({})
    names = ", ".join(e["project"] for e in sheet["entries"])
    return f"Error: unknown project. Known projects: {names}."

  @tool
  def approve_week() -> str:
    """Approves the current week and returns the updated timesheet."""
    sheet["approved"] = True
    return get_week.invoke({})

  @tool
  def get_project_budgets() -> str:
    """Returns hours used and budgeted hours for every project."""
    return json.dumps(sheet["projects"])

  return [get_week, add_hours, approve_week, get_project_budgets]


def _processor(
    conv: Conversation, capabilities: dict[str, Any]
) -> A2uiRequestProcessor:
  """A request processor for this turn's renderer, keeping surface state across turns."""
  negotiated = {"1.0": capabilities}
  probe = _generator.create_processor(negotiated)
  if conv.renderer_state is None or not probe.accepts_state(conv.renderer_state):
    conv.renderer_state = probe.create_state()
  return _generator.create_processor(negotiated, state=conv.renderer_state)


def _chunk_text(chunk: AIMessageChunk) -> str:
  text = chunk.text
  return text if isinstance(text, str) else text()


async def respond(
    conv: Conversation,
    text: str,
    action: dict[str, Any] | None,
    capabilities: dict[str, Any],
) -> AsyncIterator[Reply]:
  """Yields the reply to one user turn: typed text, or a UI action."""
  offers_ui = bool(capabilities.get("supportedCatalogIds"))
  processor = _processor(conv, capabilities) if offers_ui else None
  system_prompt = ROLE
  if processor is not None:
    has_hours = HOURS_ID in capabilities.get("supportedCatalogIds", [])
    system_prompt += "\n" + (UI_HOURS if has_hours else UI_BASIC)
    system_prompt += "\n" + processor.prompt_snippet
  else:
    system_prompt += "\nThis client cannot show UI. Answer in plain text only."

  # Built per turn: the prompt snippet depends on what the renderer offers.
  agent = create_deep_agent(
      model=_model,
      tools=_tools(conv),
      system_prompt=system_prompt,
      checkpointer=_checkpointer,
  )
  config = {"configurable": {"thread_id": conv.id}}
  prompt = f"[UI action] {json.dumps(action)}" if action else text

  for attempt in range(1, MAX_ATTEMPTS + 1):
    stream = processor.open_stream() if processor is not None else None
    last_message_id = None
    try:
      async for chunk, _ in agent.astream(
          {"messages": [{"role": "user", "content": prompt}]},
          config,
          stream_mode="messages",
      ):
        if not isinstance(chunk, AIMessageChunk):
          continue
        chunk_text = _chunk_text(chunk)
        if not chunk_text:
          continue
        if last_message_id not in (None, chunk.id):
          yield "\n\n"  # A new model call, after a tool ran.
        last_message_id = chunk.id
        if stream is None:
          yield chunk_text
          continue
        for part in stream.feed(chunk_text):
          for reply in _to_replies(part):
            yield reply
      if stream is not None:
        for part in stream.close():
          for reply in _to_replies(part):
            yield reply
      return
    except A2uiError as error:
      # The model wrote A2UI that does not fit the catalogs. Tell it why and
      # let it try again.
      logger.warning("attempt %d: invalid A2UI: %s", attempt, error)
      prompt = (
          f"Your A2UI block was rejected: {error}\n"
          "Send the corrected block. Do not apologise."
      )

  yield "\n\nSorry, I could not build the screen for that."


def _to_replies(part: Any) -> list[Reply]:
  if isinstance(part, TextPart):
    return [part.text] if part.text else []
  if isinstance(part, A2uiPart):
    return [
        m.model_dump(mode="json", by_alias=True, exclude_unset=True)
        for m in part.a2ui
    ]
  return []
