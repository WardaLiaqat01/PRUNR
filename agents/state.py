"""
LangGraph state shared across all agent nodes.

The `proposals` field uses operator.add as its reducer — meaning when any node
returns {"proposals": [new_item]}, LangGraph appends it to the existing list
rather than replacing it. This is how we accumulate proposals across the loop.
"""
from typing import TypedDict, Annotated, Optional
import operator


class AgentState(TypedDict):
    # ── Fetch phase ───────────────────────────────────────────────────────────
    sensors: list[dict]           # All alerting sensors pulled from the monitoring tool

    # ── Loop control ──────────────────────────────────────────────────────────
    current_index: int            # Which sensor we're currently on
    processing_done: bool         # Set True when all sensors have been processed

    # ── Per-sensor working data ───────────────────────────────────────────────
    current_sensor: Optional[dict]   # Sensor record being processed right now
    evidence: Optional[dict]         # Results of all four existence checks
    evidence_score: float            # 0–100: higher = stronger orphan signal
    classification: Optional[str]    # "orphan" | "broken_connection" | "uncertain"

    # ── Output ────────────────────────────────────────────────────────────────
    # Annotated with operator.add so each proposal node appends rather than overwrites
    proposals: Annotated[list[dict], operator.add]
