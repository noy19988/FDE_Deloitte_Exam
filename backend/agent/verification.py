"""
Automatic check: did the LLM invent numbers?

Two ADK callbacks (functions ADK calls for us at fixed moments):
1. remember_tool_numbers - after every tool call: save the numbers the tool returned.
2. check_answer_numbers  - before the final answer goes out: every number in the
   answer must be one of the saved numbers. If not, a warning is added to the answer.

This check is plain code (deterministic) - no LLM involved.
"""

import re
from pathlib import Path

from google.genai import types

# A number like 62, 62.1, 907,956 (the minus sign is ignored on purpose:
# in "0-100" the "-" is a dash, not a minus).
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# The LLM may round: 907,956 -> 908,000 is fine. Up to 1% difference is accepted.
TOLERANCE = 0.01

# Small numbers are used everywhere ("top 3", list items "1.", "2.") - always allowed.
SMALL_NUMBERS = set(range(0, 11))

# Numbers in the agent's own instructions (e.g. "0-100", "50 states") are allowed too.
INSTRUCTIONS_TEXT = (Path(__file__).parent / "instructions.md").read_text()


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
    """Before the final answer goes out: warn about numbers that came from nowhere."""
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

    unknown = unknown_numbers(answer, known)
    if not unknown:
        return None  # None = send the answer as it is

    listed = ", ".join(readable(n) for n in unknown)
    warning = (
        "\n\n---\n"
        f"⚠️ **Automatic check:** these numbers could not be matched to our data: {listed}. "
        "Please treat them with caution."
    )
    parts.append(types.Part(text=warning))
    return llm_response  # the answer, with the warning added at the end
