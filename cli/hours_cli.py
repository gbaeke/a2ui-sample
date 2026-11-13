#!/usr/bin/env python3
"""A text client for the Project Hours agent: the same A2UI surfaces, drawn as text.

    python3 cli/hours_cli.py [agent-url]

Standard library only. It talks A2A to the agent directly (no middleware: that
exists for the browser) and is a second renderer next to the web app. The agent
is unchanged; it sends the same A2UI 1.0 messages to both.

This is a minimal hand-written renderer, not the A2UI SDK. It handles what this
sample uses: literal values, @path bindings, static child lists and event
actions. Function calls, list templates and input components are not supported.
"""

from datetime import datetime, timezone
import json
import sys
import urllib.request
import uuid

AGENT_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:10002/"
A2UI_EXTENSION = "https://a2ui.org/a2a-extension/a2ui/v1.0"
A2UI_MIME_TYPE = "application/a2ui+json"
BASIC_ID = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"
HOURS_ID = "https://example.com/catalogs/hours/v1/catalog.json"
# Sent with every message: the catalogs this renderer can draw.
CAPABILITIES = {"1.0": {"supportedCatalogIds": [BASIC_ID, HOURS_ID]}}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
COLOR = sys.stdout.isatty()


def style(text, code):
  return f"\033[{code}m{text}\033[0m" if COLOR else text


def bold(text):
  return style(text, "1")


def dim(text):
  return style(text, "2")


def fmt(number):
  return f"{number:g}"


# --- A2UI state: surfaces, each with a flat component list and a data model ---

surfaces = {}  # surfaceId -> {"components": {id: component}, "data": {...}}


def apply_message(message):
  """Applies one agent-to-renderer message to the local surface state."""
  if "createSurface" in message:
    body = message["createSurface"]
    surfaces[body["surfaceId"]] = {
        "components": {c["id"]: c for c in body.get("components", [])},
        "data": body.get("dataModel", {}),
    }
  elif "updateComponents" in message:
    body = message["updateComponents"]
    surface = surfaces.get(body["surfaceId"])
    if surface:
      surface["components"].update({c["id"]: c for c in body["components"]})
  elif "updateDataModel" in message:
    body = message["updateDataModel"]
    surface = surfaces.get(body["surfaceId"])
    if surface:
      set_pointer(surface, body.get("path", "/"), body["value"])
  elif "deleteSurface" in message:
    surfaces.pop(message["deleteSurface"]["surfaceId"], None)


def pointer_keys(path):
  return [k.replace("~1", "/").replace("~0", "~") for k in path.split("/")[1:] if k]


def get_pointer(data, path):
  for key in pointer_keys(path):
    if isinstance(data, list):
      data = data[int(key)] if key.isdigit() and int(key) < len(data) else None
    elif isinstance(data, dict):
      data = data.get(key)
    else:
      return None
  return data


def set_pointer(surface, path, value):
  keys = pointer_keys(path)
  if not keys:
    surface["data"] = value
    return
  target = surface["data"]
  for key in keys[:-1]:
    target = target[int(key)] if isinstance(target, list) else target.setdefault(key, {})
  if isinstance(target, list):
    target[int(keys[-1])] = value
  else:
    target[keys[-1]] = value


def resolve(value, data):
  """A property value: a literal, or a binding into the surface's data model."""
  if isinstance(value, dict) and "@path" in value:
    return get_pointer(data, value["@path"])
  if isinstance(value, dict) and "@call" in value:
    return None  # Function calls are not supported by this renderer.
  return value


# --- Rendering: one function per component type, each returning lines of text ---


class Screen:
  """Collects the actions the user can trigger, numbered as they are drawn."""

  def __init__(self):
    self.actions = []  # (label, surfaceId, componentId, event, data)

  def add_action(self, label, surface_id, component, action, data):
    event = (action or {}).get("event")
    if not event:
      return None
    self.actions.append((label, surface_id, component["id"], event, data))
    return len(self.actions)

  def render(self, surface_id, component_id):
    surface = surfaces[surface_id]
    component = surface["components"].get(component_id)
    if component is None:
      return [dim(f"[missing component {component_id}]")]
    renderer = RENDERERS.get(component["component"])
    if renderer is None:
      return [dim(f"[{component['component']} is not supported in text]")]
    return renderer(self, surface_id, component, surface["data"])

  def children(self, surface_id, component):
    refs = component.get("children", [])
    if not isinstance(refs, list):  # A list template: not supported.
      return [[dim("[list templates are not supported in text]")]]
    return [self.render(surface_id, ref) for ref in refs]


def column(screen, surface_id, component, data):
  return [line for child in screen.children(surface_id, component) for line in child]


def row(screen, surface_id, component, data):
  blocks = screen.children(surface_id, component)
  if all(len(block) == 1 for block in blocks):
    return ["  ".join(block[0] for block in blocks)]
  return [line for block in blocks for line in block]


def text(screen, surface_id, component, data):
  return str(resolve(component.get("text"), data) or "").splitlines() or [""]


def card(screen, surface_id, component, data):
  return screen.render(surface_id, component["child"])


def divider(screen, surface_id, component, data):
  return [dim("-" * 60)]


def button(screen, surface_id, component, data):
  label = " ".join(screen.render(surface_id, component["child"]))
  number = screen.add_action(label, surface_id, component, component.get("action"), data)
  return [f"[{number}] {label}" if number else f"[ {label} ]"]


def status_pill(screen, surface_id, component, data):
  color = {"ok": "32", "warning": "33", "over": "31"}.get(component.get("tone"), "0")
  return [style(f"({resolve(component.get('label'), data)})", color)]


def project_budget_card(screen, surface_id, component, data):
  used = float(resolve(component.get("hoursUsed"), data) or 0)
  budget = float(resolve(component.get("budgetHours"), data) or 0)
  ratio = used / budget if budget else 0
  color, word = (
      ("31", "over budget") if ratio > 1
      else ("33", "close to budget") if ratio >= 0.8
      else ("32", "on track")
  )
  filled = round(min(ratio, 1) * 24)
  bar = style("█" * filled, color) + dim("░" * (24 - filled))
  project = str(resolve(component.get("project"), data) or "")
  client = resolve(component.get("client"), data)
  number = screen.add_action(
      f"Details: {project}", surface_id, component, component.get("onSelect"), data
  )
  title = bold(project) + (dim(f"  {client}") if client else "")
  if number:
    title += dim(f"   [{number}]")
  return [
      title,
      f"  {bar}  {fmt(used)} / {fmt(budget)} h  {round(ratio * 100)}%  {style(word, color)}",
  ]


def week_grid(screen, surface_id, component, data):
  rows = []
  for entry in resolve(component.get("entries"), data) or []:
    hours = list(entry.get("hours", []))[:5]
    rows.append((str(entry.get("project", "")), hours + [0] * (5 - len(hours))))
  approved = resolve(component.get("approved"), data) is True
  width = max([len("Project")] + [len(name) for name, _ in rows])

  def line(name, hours, total):
    cells = "".join(f"{fmt(h):>6}" for h in hours)
    return f"{name:<{width}}{cells}{fmt(total):>8}"

  lines = [
      bold(f"Week {resolve(component.get('week'), data)}")
      + (style("   APPROVED", "32") if approved else ""),
      dim(f"{'Project':<{width}}" + "".join(f"{d:>6}" for d in DAYS) + f"{'Total':>8}"),
  ]
  lines += [line(name, hours, sum(hours)) for name, hours in rows]
  totals = [sum(hours[i] for _, hours in rows) for i in range(5)]
  lines.append(bold(line("Total", totals, sum(totals))))
  if not approved:
    number = screen.add_action(
        "Approve week", surface_id, component, component.get("onApprove"), data
    )
    if number:
      lines.append(f"[{number}] Approve week")
  return lines


RENDERERS = {
    # Basic catalog (the parts this sample uses).
    "Column": column,
    "Row": row,
    "Text": text,
    "Card": card,
    "Divider": divider,
    "Button": button,
    # Hours catalog.
    "StatusPill": status_pill,
    "ProjectBudgetCard": project_budget_card,
    "WeekGrid": week_grid,
}


def draw():
  """Draws every surface and returns the screen with its numbered actions."""
  screen = Screen()
  for surface_id in surfaces:
    print()
    print(dim(f"── surface: {surface_id} " + "─" * (46 - len(surface_id))))
    for line in screen.render(surface_id, "root"):
      print(line)
  if surfaces:
    print(dim("─" * 60))
  return screen


# --- A2A: one JSON-RPC message/stream call per turn ---

context_id = None


def send(part):
  """Sends one A2A message and applies the streamed reply."""
  global context_id
  request = {
      "jsonrpc": "2.0",
      "id": str(uuid.uuid4()),
      "method": "message/stream",
      "params": {
          "message": {
              "kind": "message",
              "role": "user",
              "messageId": str(uuid.uuid4()),
              "contextId": context_id,
              "parts": [part],
              "metadata": {"a2uiRendererCapabilities": CAPABILITIES},
          }
      },
  }
  http_request = urllib.request.Request(
      AGENT_URL,
      data=json.dumps(request).encode(),
      headers={"Content-Type": "application/json", "X-A2A-Extensions": A2UI_EXTENSION},
  )
  wrote_text = False
  with urllib.request.urlopen(http_request, timeout=180) as response:
    for raw in response:
      line = raw.decode().strip()
      if not line.startswith("data:"):
        continue
      event = json.loads(line[5:])
      if "error" in event:
        print(style(f"agent error: {event['error'].get('message')}", "31"))
        continue
      result = event["result"]
      context_id = result.get("contextId") or context_id
      if result.get("kind") == "status-update":
        parts = (result["status"].get("message") or {}).get("parts", [])
      elif result.get("kind") == "message":
        parts = result.get("parts", [])
      else:
        parts = []
      for reply in parts:
        if reply["kind"] == "text":
          # Agent text is printed as it streams in.
          sys.stdout.write(reply["text"] if wrote_text else reply["text"].lstrip())
          sys.stdout.flush()
          wrote_text = wrote_text or bool(reply["text"].strip())
        elif (reply.get("metadata") or {}).get("mimeType") == A2UI_MIME_TYPE:
          messages = reply["data"]
          for message in messages if isinstance(messages, list) else [messages]:
            apply_message(message)
  if wrote_text:
    print()


def send_text(text_value):
  send({"kind": "text", "text": text_value})


def send_action(action):
  _, surface_id, component_id, event, data = action
  context = {k: resolve(v, data) for k, v in (event.get("context") or {}).items()}
  message = {
      "version": "1.0",
      "action": {
          "name": event["name"],
          "surfaceId": surface_id,
          "sourceComponentId": component_id,
          "timestamp": datetime.now(timezone.utc).isoformat(),
          "context": context,
      },
  }
  send({"kind": "data", "data": message, "metadata": {"mimeType": A2UI_MIME_TYPE}})


def main():
  print(bold("Project Hours") + dim("  text client, A2UI 1.0 over A2A"))
  print(dim("Type a message, a number to use an action, or /quit."))
  screen = Screen()
  while True:
    try:
      line = input(bold("\n> ")).strip()
    except (EOFError, KeyboardInterrupt):
      print()
      return
    if not line:
      continue
    if line in ("/quit", "/q", "exit"):
      return
    try:
      if line.isdigit():
        if not 1 <= int(line) <= len(screen.actions):
          print(dim("No action with that number."))
          continue
        action = screen.actions[int(line) - 1]
        print(dim(f"(action: {action[0]})"))
        send_action(action)
      else:
        send_text(line)
    except OSError as error:
      print(style(f"Could not reach the agent at {AGENT_URL}: {error}", "31"))
      continue
    screen = draw()


if __name__ == "__main__":
  main()
