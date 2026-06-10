"""
FastAPI server — two responsibilities:
  1. Serve the approval dashboard UI (GET /)
  2. Expose REST endpoints for running the agent and reviewing proposals
"""
import sys
from pathlib import Path

# Ensure project root is on the path regardless of how the server is started
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.database import init_db, save_proposals, get_proposals, get_stats, update_status

app = FastAPI(title="Alerts Cleanup Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ── Proposals ──────────────────────────────────────────────────────────────────

@app.get("/api/proposals")
def list_proposals(status: str = None):
    """Return all proposals, optionally filtered by status."""
    return get_proposals(status)


@app.get("/api/stats")
def stats():
    """Return pending / approved / rejected counts."""
    return get_stats()


class ReviewBody(BaseModel):
    notes: str = ""


@app.post("/api/proposals/{proposal_id}/approve")
def approve(proposal_id: int, body: ReviewBody = ReviewBody()):
    ok = update_status(proposal_id, "approved", body.notes)
    if not ok:
        raise HTTPException(404, "Proposal not found or already reviewed")

    # ── PRODUCTION: trigger the actual action here ──
    # proposal = get_proposals()[proposal_id]
    # if proposal["proposed_action"] == "delete_sensor":
    #     httpx.delete(f"{MONITORING_API}/api/sensors/{proposal['sensor_id']}")
    # elif proposal["proposed_action"] == "rotate_credentials":
    #     create_jira_ticket(...)
    # ───────────────────────────────────────────────

    return {"status": "approved", "id": proposal_id}


@app.post("/api/proposals/{proposal_id}/reject")
def reject(proposal_id: int, body: ReviewBody = ReviewBody()):
    ok = update_status(proposal_id, "rejected", body.notes)
    if not ok:
        raise HTTPException(404, "Proposal not found or already reviewed")
    return {"status": "rejected", "id": proposal_id}


# ── Agent trigger ──────────────────────────────────────────────────────────────

@app.post("/api/run-agent")
def run_agent():
    """
    Trigger the LangGraph cleanup agent.
    Runs synchronously — for production with many sensors, wrap in BackgroundTasks.
    """
    from agents.graph import build_agent

    graph = build_agent()

    result = graph.invoke({
        "sensors":          [],
        "current_index":    0,
        "current_sensor":   None,
        "evidence":         None,
        "evidence_score":   0.0,
        "classification":   None,
        "proposals":        [],
        "processing_done":  False,
    })

    proposals = result.get("proposals", [])
    count = save_proposals(proposals)

    return {
        "sensors_processed": len(result.get("sensors", [])),
        "proposals_created": count,
    }


# ── UI ─────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def ui():
    """Serve the approval dashboard."""
    ui_path = Path(__file__).parent.parent / "ui" / "index.html"
    try:
        # Return raw bytes to avoid any encoding round-trip issues in the worker process
        return HTMLResponse(ui_path.read_bytes())
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        return PlainTextResponse(f"Exception reading UI file:\n{tb}", status_code=500)
