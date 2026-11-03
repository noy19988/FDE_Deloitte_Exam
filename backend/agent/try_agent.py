"""
Talk to the agent in the terminal (for development, before the UI exists).

Shows every tool the agent calls, then its answer.
Follow-up questions work: the whole chat is one session.

Run from the project root:
    python -m backend.agent.try_agent
"""

import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from backend.agent.agent import root_agent

APP_NAME = "airport_agent"
USER_ID = "dev"


async def main():
    # For now the chat is kept in memory. Later: PostgreSQL.
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=APP_NAME, user_id=USER_ID)
    runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=sessions)

    while True:
        question = input("\nYou: ").strip()
        if question in ("", "exit", "quit"):
            break

        message = types.Content(role="user", parts=[types.Part(text=question)])

        # ADK runs the loop and tells us about each step as an "event".
        async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
            for part in event.content.parts if event.content else []:
                if part.function_call:
                    print(f"  [tool] {part.function_call.name}({dict(part.function_call.args)})")
                if part.text and event.is_final_response():
                    print(f"\nAgent:\n{part.text}")


if __name__ == "__main__":
    asyncio.run(main())
