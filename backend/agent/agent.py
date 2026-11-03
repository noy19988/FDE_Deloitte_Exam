"""
The agent: Gemini + instructions + our 6 tools.

ADK runs the loop for us:
question -> Gemini picks a tool -> ADK runs it -> Gemini reads the result -> answer.
"""

from pathlib import Path

from google.adk.agents import Agent

from backend.agent.verification import check_answer_numbers, remember_tool_numbers
from backend.config import GEMINI_MODEL
from backend.tools.airport_tools import (
    compare_airports,
    get_airport_profile,
    live_status,
    long_haul_share,
    rank_airports,
    unmet_demand,
)

# The instructions live in a separate text file, so they are easy to read and change.
INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text()

root_agent = Agent(
    name="airport_investment_agent",
    model=GEMINI_MODEL,
    description="Helps investment analysts find US airports where expansion would be most profitable.",
    instruction=INSTRUCTIONS,
    tools=[
        rank_airports,
        compare_airports,
        get_airport_profile,
        long_haul_share,
        unmet_demand,
        live_status,
    ],
    # Automatic check that the answer has no invented numbers (see verification.py).
    after_tool_callback=remember_tool_numbers,
    after_model_callback=check_answer_numbers,
)
