"""
Automatic check: did the LLM invent numbers?

Two ADK callbacks (functions ADK calls for us at fixed moments):
1. remember_tool_numbers - after every tool call: save the numbers the tool returned.
2. check_answer_numbers  - before the final answer goes out: every number in the
   answer must be one of the saved numbers (or the difference between two numbers
   from the data shown in the same answer). If not, the numbers are written to the
   server log (docker compose logs backend) - the user does not see it.

This check is plain code (deterministic) - no LLM involved.
"""

import logging
import re
from itertools import combinations
from pathlib import Path

# A number like 62, 62.1, 907,956 (the minus sign is ignored on purpose:
# in "0-100" the "-" is a dash, not a minus).
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# The LLM may round: 907,956 -> 908,000 is fine. Up to 1% difference is accepted.
TOLERANCE = 0.01

# Small numbers are used everywhere ("top 3", list items "1.", "2.") - always allowed.
SMALL_NUMBERS = set(range(0, 11))

# Numbers in the agent's own instructions (e.g. "0-100", "50 states") are allowed too.
INSTRUCTIONS_TEXT = (Path(__file__).parent / "instructions.md").read_text()

# Where unmatched numbers are reported (the backend log, not the chat).
logger = logging.getLogger(__name__)


def numbers_in_text(text):
    """All numbers in a piece of text: "LF 82.3%, 907,956 seats" -> [82.3, 907956.0]."""
    return [float(match.replace(",", "")) for match in NUMBER.findall(text)]


def numbers_in_result(value):
    """All numbers inside a tool result (dicts and lists inside dicts, text too)."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [abs(float(value))]
    if isinstance(value, str):
        return numbers_in_text(value)
    if isinstance(value, dict):
        return [n for item in value.values() for n in numbers_in_result(item)]
    if isinstance(value, list):
        return [n for item in value for n in numbers_in_result(item)]
    return []


def is_known(number, known_numbers):
    if number in SMALL_NUMBERS:
        return True
    return any(abs(number - known) <= TOLERANCE * known for known in known_numbers)


def is_difference(number, numbers):
    """True if `number` is the difference between two of `numbers` (e.g. 0.5 = 8.7 - 8.2)."""
    return any(is_known(number, [abs(a - b)]) for a, b in combinations(numbers, 2) if a != b)


def readable(number):
    """How a number is shown in the warning: 40000000.0 -> "40,000,000", 82.3 -> "82.3"."""
    return f"{number:,.0f}" if number == int(number) else f"{number:,}"


def unknown_numbers(text, known_numbers):
    """Numbers in the text that do not match any known number (each listed once)."""
    unknown = []
    for number in numbers_in_text(text):
        if not is_known(number, known_numbers) and number not in unknown:
            unknown.append(number)
    return unknown


# --- The two ADK callbacks ---

def remember_tool_numbers(tool, args, tool_context, tool_response):
    """After each tool call: add its numbers to the conversation state."""
    known = tool_context.state.get("known_numbers", [])
    tool_context.state["known_numbers"] = known + numbers_in_result(tool_response)
    return None  # None = keep the tool result as it is


def check_answer_numbers(callback_context, llm_response):
    """Before the final answer goes out: log numbers that came from nowhere."""
    parts = llm_response.content.parts if llm_response.content else []

    # If the model is asking for a tool, this is not the final answer yet.
    if any(part.function_call for part in parts):
        return None

    answer = "".join(part.text or "" for part in parts)

    # Allowed: numbers from tools, from the user's question, and from our instructions.
    question = callback_context.user_content
    question_text = "".join(p.text or "" for p in question.parts) if question else ""
    known = (
        callback_context.state.get("known_numbers", [])
        + numbers_in_text(question_text)
        + numbers_in_text(INSTRUCTIONS_TEXT)
    )

    # Also allowed: a simple difference between two numbers that are in this answer
    # and came from our data (e.g. "LAX is 0.5 points higher" for 8.7% vs 8.2%).
    shown = [number for number in numbers_in_text(answer) if is_known(number, known)]
    unknown = [number for number in unknown_numbers(answer, known) if not is_difference(number, shown)]
    if unknown:
        logger.warning("Automatic check: numbers not found in the tool results: %s",
                       ", ".join(readable(n) for n in unknown))
    return None  # None = send the answer as it is
