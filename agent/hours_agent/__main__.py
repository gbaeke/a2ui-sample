"""Runs the agent as an A2A server: `uv run hours-agent`."""

import argparse
import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2ui.a2a import get_a2ui_agent_extension
import uvicorn

from .catalogs import BASIC_ID, HOURS_ID, VERSION
from .executor import HoursAgentExecutor


def build_agent_card(base_url: str) -> AgentCard:
  return AgentCard(
      name="Project Hours Agent",
      description="Shows timesheets and project budgets as interactive A2UI surfaces.",
      url=base_url,
      version="0.1.0",
      default_input_modes=["text/plain"],
      default_output_modes=["text/plain", "application/a2ui+json"],
      capabilities=AgentCapabilities(
          streaming=True,
          extensions=[
              get_a2ui_agent_extension(
                  VERSION, supported_catalog_ids=[BASIC_ID, HOURS_ID]
              ),
          ],
      ),
      skills=[
          AgentSkill(
              id="timesheet",
              name="Timesheet",
              description="Show, update and approve the weekly timesheet.",
              tags=["hours", "timesheet"],
              examples=["Show my week", "Log 2 hours on Friday"],
          ),
          AgentSkill(
              id="budgets",
              name="Project budgets",
              description="Show logged hours against budget per project.",
              tags=["budget", "projects"],
              examples=["Show project budgets"],
          ),
      ],
  )


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--host", default="localhost")
  parser.add_argument("--port", type=int, default=10002)
  parser.add_argument(
      "--canned",
      action="store_true",
      help="answer with canned replies instead of calling the LLM",
  )
  args = parser.parse_args()

  logging.basicConfig(level=logging.INFO)

  if args.canned:
    from . import canned as brain
  else:
    from . import llm as brain

  card = build_agent_card(f"http://{args.host}:{args.port}/")
  handler = DefaultRequestHandler(
      agent_executor=HoursAgentExecutor(card, brain),
      task_store=InMemoryTaskStore(),
  )
  app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
  uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
  main()
