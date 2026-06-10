"""
LangGraph node functions.

Each function receives the full AgentState and returns a dict containing
only the fields it wants to update. LangGraph merges these back into state.
"""
import os
from dotenv import load_dotenv

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from agents.state import AgentState
from agents.tools import run_all_checks, score_evidence, classify_score

load_dotenv()

MONITORING_API = os.getenv("MONITORING_API_URL", "http://127.0.0.1:8080")

# ─── LLM setup (used only for orphan evidence summaries) ─────────────────────
try:
    _llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False


def _build_summary(sensor: dict, evidence: dict, score: float) -> str:
    """Generate a human-readable evidence summary.
    Uses the LLM if available, falls back to a rule-based sentence if not.
    """
    if LLM_AVAILABLE:
        try:
            resp = _llm.invoke([HumanMessage(content=f"""
You are an IT monitoring agent writing a brief note for an engineer.
In exactly 2 sentences, explain why this sensor appears to be orphaned.
Reference the specific evidence. Be direct and technical.

Device  : {sensor['device']} ({sensor['host']})
Alert   : {sensor['message']}
DNS     : {'resolves' if evidence['dns_resolves'] else 'DOES NOT resolve'}
Ping    : {'responds' if evidence['ping_responds'] else 'NO response'}
AD obj  : {'exists' if evidence['ad_object_exists'] else 'NOT found'}
VM      : {'found in vCenter/Azure' if evidence['vcenter_vm_exists'] else 'NOT found in vCenter/Azure'}
CMDB    : {evidence['cmdb_status']}
Score   : {score}/100
""")])
            return resp.content.strip()
        except Exception:
            pass  # Fall through to rule-based

    # Rule-based fallback (no API key required)
    reasons = []
    if not evidence["dns_resolves"]:       reasons.append("DNS does not resolve")
    if not evidence["ping_responds"]:      reasons.append("host unreachable via ping")
    if not evidence["ad_object_exists"]:   reasons.append("no AD computer object found")
    if not evidence["vcenter_vm_exists"]:  reasons.append("VM absent from vCenter/Azure")
    if evidence["cmdb_status"] != "active":
        reasons.append(f"CMDB status is '{evidence['cmdb_status']}'")

    reasons_str = "; ".join(reasons) if reasons else "multiple checks failed"
    return (
        f"Sensor for {sensor['device']} ({sensor['host']}) appears orphaned "
        f"with a confidence score of {score}/100. "
        f"Evidence: {reasons_str}."
    )


# ─── Node 1: Fetch all alerting sensors ──────────────────────────────────────

def fetch_alerts(state: AgentState) -> dict:
    """Pull all down/alerting sensors from the monitoring tool API."""
    try:
        resp = httpx.get(f"{MONITORING_API}/api/sensors", timeout=10)
        resp.raise_for_status()
        sensors = resp.json()
        print(f"\n[agent] Fetched {len(sensors)} alerting sensor(s)")
    except Exception as e:
        print(f"[agent] WARNING: Could not reach monitoring API — {e}")
        sensors = []

    return {
        "sensors":          sensors,
        "current_index":    0,
        "processing_done":  False,
    }


# ─── Node 2: Loop controller — advance to the next sensor ────────────────────

def pick_next_sensor(state: AgentState) -> dict:
    """Pick the next sensor to process. Sets processing_done=True when finished."""
    idx     = state["current_index"]
    sensors = state["sensors"]

    if idx >= len(sensors):
        print("\n[agent] All sensors processed.")
        return {"processing_done": True}

    sensor = sensors[idx]
    print(f"\n[agent] [{idx + 1}/{len(sensors)}] {sensor['device']} ({sensor['host']})")
    return {
        "current_sensor": sensor,
        "current_index":  idx + 1,
    }


def should_continue(state: AgentState) -> str:
    """Conditional edge: route to 'process' or 'done'."""
    return "done" if state.get("processing_done") else "process"


# ─── Node 3: Run all four existence checks concurrently ──────────────────────

def run_checks(state: AgentState) -> dict:
    """Run DNS, ping, AD, and vCenter/Azure checks in parallel via thread pool."""
    sensor   = state["current_sensor"]
    evidence = run_all_checks(sensor["device"], sensor["host"])

    print(
        f"  DNS={evidence['dns_resolves']}  "
        f"Ping={evidence['ping_responds']}  "
        f"AD={evidence['ad_object_exists']}  "
        f"VM={evidence['vcenter_vm_exists']}  "
        f"CMDB={evidence['cmdb_status']}"
    )
    return {"evidence": evidence}


# ─── Node 4: Score evidence and classify ─────────────────────────────────────

def score_and_classify(state: AgentState) -> dict:
    """Compute orphan confidence score and classify the alert."""
    score      = score_evidence(state["evidence"])
    category   = classify_score(score)
    # Use ASCII arrow to avoid Windows console encoding issues
    print(f"  Score: {score}/100  ->  {category}")
    return {"evidence_score": score, "classification": category}


def route_classification(state: AgentState) -> str:
    """Conditional edge: route by classification."""
    return state["classification"]


# ─── Node 5a: Orphan — propose deletion ──────────────────────────────────────

def propose_deletion(state: AgentState) -> dict:
    """Build a sensor deletion proposal with LLM-generated evidence summary."""
    sensor  = state["current_sensor"]
    evidence = state["evidence"]
    score   = state["evidence_score"]

    summary = _build_summary(sensor, evidence, score)

    # Returns a list — the operator.add reducer appends this to state["proposals"]
    return {"proposals": [{
        "sensor_id":        sensor["objid"],
        "device_name":      sensor["device"],
        "host":             sensor["host"],
        "alert_message":    sensor["message"],
        "classification":   "orphan",
        "evidence_score":   score,
        "evidence_summary": summary,
        "proposed_action":  "delete_sensor",
        "status":           "pending",
    }]}


# ─── Node 5b: Broken connection — diagnose and propose a fix ─────────────────

def diagnose_connection(state: AgentState) -> dict:
    """Rule-based diagnosis of why the monitoring link is broken."""
    sensor = state["current_sensor"]
    msg    = sensor["message"].lower()

    if any(k in msg for k in ["credential", "auth", "access denied", "password"]):
        summary = (
            "Credentials have likely rotated or expired. "
            "Update the stored WMI/SNMP credentials in the monitoring tool and re-test the sensor."
        )
        action = "rotate_credentials"

    elif any(k in msg for k in ["agent", "port", "refused", "cannot connect"]):
        summary = (
            "The monitoring agent is not responding on the expected port. "
            "Verify the agent service is running on the target and that the port is open through intermediate firewalls."
        )
        action = "check_agent_and_firewall"

    elif any(k in msg for k in ["timeout", "timed out", "unreachable"]):
        summary = (
            "Network path issue between the monitoring probe and the target. "
            "Run a traceroute from the probe to identify where the path is being dropped."
        )
        action = "check_network_path"

    else:
        summary = (
            "Connectivity issue with no clear pattern match. "
            "Review the full sensor error log and test connectivity manually from the monitoring probe server."
        )
        action = "manual_review"

    return {"proposals": [{
        "sensor_id":        sensor["objid"],
        "device_name":      sensor["device"],
        "host":             sensor["host"],
        "alert_message":    sensor["message"],
        "classification":   "broken_connection",
        "evidence_score":   state["evidence_score"],
        "evidence_summary": summary,
        "proposed_action":  action,
        "status":           "pending",
    }]}


# ─── Node 5c: Uncertain — flag for manual review ─────────────────────────────

def flag_uncertain(state: AgentState) -> dict:
    """Flag sensors with conflicting evidence for manual engineer review."""
    sensor   = state["current_sensor"]
    evidence = state["evidence"]
    score    = state["evidence_score"]

    signals = []
    if evidence.get("dns_resolves") and evidence.get("ping_responds"):
        signals.append("host is reachable on the network")
    if not evidence.get("ad_object_exists"):
        signals.append("no AD computer object found")
    if not evidence.get("vcenter_vm_exists"):
        signals.append("no matching VM in vCenter/Azure")
    if evidence.get("cmdb_status") == "not_found":
        signals.append("asset is missing from CMDB")

    summary = (
        f"Conflicting evidence (score {score}/100): "
        + "; ".join(signals) + ". "
        "This could be a non-Windows device (switch, appliance, NAS) "
        "or a recently provisioned server not yet registered in AD/CMDB."
    )

    return {"proposals": [{
        "sensor_id":        sensor["objid"],
        "device_name":      sensor["device"],
        "host":             sensor["host"],
        "alert_message":    sensor["message"],
        "classification":   "uncertain",
        "evidence_score":   score,
        "evidence_summary": summary,
        "proposed_action":  "manual_review",
        "status":           "pending",
    }]}
