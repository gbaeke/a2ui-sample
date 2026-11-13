"""Bridges A2A requests to the agent's brain and A2UI replies back to A2A parts."""

import logging
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCard,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_parts_message, new_task
from a2a.utils.errors import ServerError
from a2ui.a2a import create_a2ui_part, get_a2ui_messages, try_activate_a2ui_extension

from .conversation import Conversation, Reply

logger = logging.getLogger(__name__)

# Renderer capabilities ride on every A2A message's metadata under this key.
CAPABILITIES_KEY = "a2uiRendererCapabilities"


def _renderer_capabilities(context: RequestContext) -> dict[str, Any]:
  """What this turn's renderer offers for A2UI 1.0; empty when it offers none."""
  metadata = (context.message.metadata if context.message else None) or {}
  return (metadata.get(CAPABILITIES_KEY) or {}).get("1.0") or {}


def _inbound_action(context: RequestContext) -> dict[str, Any] | None:
  """The `action` of the first A2UI renderer-to-agent message, if any."""
  if context.message is None:
    return None
  for data in get_a2ui_messages(context.message):
    # a2ui-a2a 0.3.0 carries one message per part; the 1.0 extension spec
    # says a list. Accept both.
    for message in data if isinstance(data, list) else [data]:
      if isinstance(message, dict) and "action" in message:
        return message["action"]
  return None


def _to_part(reply: Reply) -> Part:
  if isinstance(reply, str):
    return Part(root=TextPart(text=reply))
  return create_a2ui_part(reply)


class HoursAgentExecutor(AgentExecutor):

  def __init__(self, agent_card: AgentCard, brain: Any) -> None:
    """`brain` is a module with `respond(conv, text, action, capabilities)`."""
    self._agent_card = agent_card
    self._brain = brain
    self._conversations: dict[str, Conversation] = {}

  async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
    try_activate_a2ui_extension(context, self._agent_card)

    task = context.current_task
    if task is None:
      task = new_task(context.message)
      await event_queue.enqueue_event(task)
    updater = TaskUpdater(event_queue, task.id, task.context_id)

    conv = self._conversations.setdefault(
        task.context_id, Conversation(id=task.context_id)
    )
    action = _inbound_action(context)
    text = "" if action else context.get_user_input()
    logger.info("turn: %s", action or text)

    # Each working update carries only new parts: a piece of text or one A2UI
    # message. The stream ends with a `completed` update that has no message.
    try:
      async for reply in self._brain.respond(
          conv, text, action, _renderer_capabilities(context)
      ):
        await updater.update_status(
            TaskState.working,
            new_agent_parts_message([_to_part(reply)], task.context_id, task.id),
        )
    except Exception as error:  # Report instead of leaving the stream hanging.
      logger.exception("turn failed")
      await updater.failed(
          new_agent_parts_message(
              [_to_part(f"The agent failed: {error}")], task.context_id, task.id
          )
      )
      return
    await updater.complete()

  async def cancel(
      self, context: RequestContext, event_queue: EventQueue
  ) -> Task | None:
    raise ServerError(error=UnsupportedOperationError())
