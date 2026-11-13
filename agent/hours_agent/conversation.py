"""What the agent remembers for one A2A context, and what a brain returns."""

from dataclasses import dataclass, field
from typing import Any

from a2ui.utils import RendererState

from .data import new_timesheet

# One item of an agent reply: a `str` is chat text, a `dict` is one A2UI 1.0
# agent-to-renderer message.
Reply = str | dict[str, Any]


@dataclass
class Conversation:
  id: str
  timesheet: dict[str, Any] = field(default_factory=new_timesheet)
  # Canned brain: ids of the surfaces the renderer currently shows.
  surfaces: set[str] = field(default_factory=set)
  # LLM brain: the A2UI SDK's view of the renderer's surfaces.
  renderer_state: RendererState | None = None
