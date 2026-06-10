"""
Assembles the LangGraph cleanup agent.

Graph structure:
                         ┌──────────────────┐
    START ──► fetch ──► pick_next ──► run_checks ──► score_classify
                 ▲           │ (done)                      │
                 │           └──────► END          ┌───────┴────────┐
                 │                            orphan  broken  uncertain
                 │                              │        │        │
                 └──────────────────────────────┴────────┴────────┘
                                    (loop back)
"""
from langgraph.graph import StateGraph, START, END

from agents.state import AgentState
from agents.nodes import (
    fetch_alerts,
    pick_next_sensor,
    run_checks,
    score_and_classify,
    propose_deletion,
    diagnose_connection,
    flag_uncertain,
    should_continue,
    route_classification,
)


def build_agent():
    """Build and compile the cleanup agent graph."""
    g = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    g.add_node("fetch_alerts",        fetch_alerts)
    g.add_node("pick_next",           pick_next_sensor)
    g.add_node("run_checks",          run_checks)
    g.add_node("score_and_classify",  score_and_classify)
    g.add_node("propose_deletion",    propose_deletion)
    g.add_node("diagnose_connection", diagnose_connection)
    g.add_node("flag_uncertain",      flag_uncertain)

    # ── Entry point ───────────────────────────────────────────────────────────
    g.add_edge(START, "fetch_alerts")
    g.add_edge("fetch_alerts", "pick_next")

    # ── Loop: continue processing or finish ───────────────────────────────────
    g.add_conditional_edges(
        "pick_next",
        should_continue,
        {"process": "run_checks", "done": END},
    )

    # ── Linear check pipeline ─────────────────────────────────────────────────
    g.add_edge("run_checks", "score_and_classify")

    # ── Branch by classification ──────────────────────────────────────────────
    g.add_conditional_edges(
        "score_and_classify",
        route_classification,
        {
            "orphan":            "propose_deletion",
            "broken_connection": "diagnose_connection",
            "uncertain":         "flag_uncertain",
        },
    )

    # ── After each proposal, loop back for the next sensor ───────────────────
    g.add_edge("propose_deletion",    "pick_next")
    g.add_edge("diagnose_connection", "pick_next")
    g.add_edge("flag_uncertain",      "pick_next")

    return g.compile()
