"""
Live airport status from the FAA (what is happening right now).

The FAA publishes one XML document with all current
ground stops, delay programs, delays and closures in the US.
"""

import xml.etree.ElementTree as ET

import requests

from backend.config import CODE_ALIASES

STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"


def to_text(element):
    """
    Turn an XML element into readable text.
    Nested fields keep their names, e.g.
    "Type: Departure, Min: 16 minutes, Max: 30 minutes, Trend: Increasing"
    """
    if len(element) == 0:  # no nested fields - just the text
        return (element.text or "").strip()
    parts = [f"{key}: {value}" for key, value in element.attrib.items()]
    parts += [f"{child.tag}: {to_text(child)}" for child in element]
    return ", ".join(parts)


def get_live_status(airport_code):
    """
    Current FAA delays for one airport (e.g. "SFO").
    Returns a list - empty if there are no delays right now.
    """
    response = requests.get(STATUS_URL, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.text)

    # The FAA may still use an airport's old code (e.g. PBI for DJT).
    codes = {airport_code} | {old for old, new in CODE_ALIASES.items() if new == airport_code}

    events = []
    # The XML has one <Delay_type> block per kind of event
    # (Ground Stop Programs, Ground Delay Programs, Airport Closures...).
    for delay_type in root.findall("Delay_type"):
        kind = delay_type.findtext("Name")

        # Inside each block, every airport entry has an <ARPT> tag with the airport code.
        for entry in delay_type.iter():
            if entry.findtext("ARPT") not in codes:
                continue

            # Keep the other fields as text (Reason, Avg, Max...).
            details = {child.tag: to_text(child) for child in entry if child.tag != "ARPT"}
            events.append({"type": kind, **details})

    return events
