"""Canned brain: replies picked by keyword, no LLM. Run with `--canned`.

Useful for checking the transport without a model in the loop.
"""

from collections.abc import AsyncIterator
from typing import Any

from .catalogs import BASIC_ID, HOURS_ID
from .conversation import Conversation, Reply


async def respond(
    conv: Conversation,
    text: str,
    action: dict[str, Any] | None,
    capabilities: dict[str, Any],
) -> AsyncIterator[Reply]:
  """Yields the reply to one user turn: typed text, or a UI action."""
  replies = reply_to_action(conv, action) if action else reply_to_text(conv, text)
  if HOURS_ID not in (capabilities.get("supportedCatalogIds") or []):
    # No A2UI offered this turn: the spec says to send no A2UI parts.
    replies = [r for r in replies if isinstance(r, str)]
  for reply in replies:
    yield reply


def _create_surface(
    conv: Conversation,
    surface_id: str,
    components: list[dict[str, Any]],
    data_model: dict[str, Any] | None = None,
) -> list[Reply]:
  """createSurface, preceded by deleteSurface when the renderer already has it."""
  messages: list[Reply] = []
  if surface_id in conv.surfaces:
    messages.append({"version": "1.0", "deleteSurface": {"surfaceId": surface_id}})
  surface: dict[str, Any] = {
      "surfaceId": surface_id,
      "catalogId": BASIC_ID,
      "components": components,
  }
  if data_model is not None:
    surface["dataModel"] = data_model
  messages.append({"version": "1.0", "createSurface": surface})
  conv.surfaces.add(surface_id)
  return messages


def _week_surface(conv: Conversation) -> list[Reply]:
  sheet = conv.timesheet
  return _create_surface(
      conv,
      "week",
      [
          {"id": "root", "component": "Column", "children": ["title", "grid"]},
          {"id": "title", "component": "Text", "text": "Your timesheet"},
          {
              "id": "grid",
              "component": "WeekGrid",
              "catalogId": HOURS_ID,
              "week": {"@path": "/week"},
              "entries": {"@path": "/entries"},
              "approved": {"@path": "/approved"},
              "onApprove": {
                  "event": {
                      "name": "approve_week",
                      "context": {"week": {"@path": "/week"}},
                  }
              },
          },
      ],
      {
          "week": sheet["week"],
          "approved": sheet["approved"],
          "entries": sheet["entries"],
      },
  )


def _tone(project: dict[str, Any]) -> tuple[str, str]:
  ratio = project["hoursUsed"] / project["budgetHours"]
  if ratio > 1:
    return "over", "Over budget"
  if ratio >= 0.8:
    return "warning", "Close to budget"
  return "ok", "On track"


def _budgets_surface(conv: Conversation) -> list[Reply]:
  components: list[dict[str, Any]] = [
      {"id": "title", "component": "Text", "text": "Project budgets"},
  ]
  children = ["title"]
  for i, project in enumerate(conv.timesheet["projects"]):
    components.append({
        "id": f"card{i}",
        "component": "ProjectBudgetCard",
        "catalogId": HOURS_ID,
        **project,
        "onSelect": {
            "event": {
                "name": "select_project",
                "context": {"project": project["project"]},
            }
        },
    })
    children.append(f"card{i}")
  components.insert(0, {"id": "root", "component": "Column", "children": children})
  return _create_surface(conv, "budgets", components)


def _log_hours(conv: Conversation) -> list[Reply]:
  """Adds 2 hours on Friday to the first project: a data-only update."""
  sheet = conv.timesheet
  if sheet["approved"]:
    return [f"Week {sheet['week']} is already approved, so I can't change it."]
  entry = sheet["entries"][0]
  entry["hours"][4] += 2
  text = f"Logged 2 hours on Friday for {entry['project']}."
  if "week" not in conv.surfaces:
    return [text, *_week_surface(conv)]
  return [
      text,
      {
          "version": "1.0",
          "updateDataModel": {
              "surfaceId": "week",
              "path": "/entries",
              "value": sheet["entries"],
          },
      },
  ]


def reply_to_text(conv: Conversation, text: str) -> list[Reply]:
  words = text.lower()
  if "log" in words:
    return _log_hours(conv)
  if "budget" in words or "project" in words:
    return ["Here are your project budgets.", *_budgets_surface(conv)]
  if any(w in words for w in ("week", "hours", "timesheet")):
    return [
        f"Here is your timesheet for {conv.timesheet['week']}.",
        *_week_surface(conv),
    ]
  return [
      "I'm running on canned answers for now. Try “show my week”, "
      "“show project budgets” or “log 2 hours on Friday”."
  ]


def reply_to_action(conv: Conversation, action: dict[str, Any]) -> list[Reply]:
  name = action.get("name")
  context = action.get("context") or {}

  if name == "approve_week":
    conv.timesheet["approved"] = True
    return [
        f"Week {context.get('week', conv.timesheet['week'])} is approved.",
        {
            "version": "1.0",
            "updateDataModel": {
                "surfaceId": "week",
                "path": "/approved",
                "value": True,
            },
        },
    ]

  if name == "select_project":
    for project in conv.timesheet["projects"]:
      if project["project"] == context.get("project"):
        _, label = _tone(project)
        percent = round(100 * project["hoursUsed"] / project["budgetHours"])
        return [
            f"{project['project']} ({project['client']}): "
            f"{project['hoursUsed']:g} of {project['budgetHours']:g} hours used, "
            f"{percent}%. {label}."
        ]

  return [f"I don't know how to handle the action “{name}”."]
