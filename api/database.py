"""
SQLite persistence layer for agent proposals.
All database operations go through this module — keeps server.py clean.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "proposals.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # Rows behave like dicts
    return conn


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call on every startup."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS proposals (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id        INTEGER NOT NULL,
            device_name      TEXT    NOT NULL,
            host             TEXT    NOT NULL,
            alert_message    TEXT,
            classification   TEXT    NOT NULL,
            evidence_score   REAL,
            evidence_summary TEXT,
            proposed_action  TEXT    NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'pending',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at      TIMESTAMP,
            reviewer_notes   TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at      TIMESTAMP,
            sensors_processed INTEGER,
            proposals_created INTEGER
        );
    """)
    conn.commit()
    conn.close()


def save_proposals(proposals: list[dict]) -> int:
    """Insert proposals into the DB. Returns the number of rows inserted."""
    conn = get_conn()
    count = 0
    for p in proposals:
        conn.execute("""
            INSERT INTO proposals
              (sensor_id, device_name, host, alert_message, classification,
               evidence_score, evidence_summary, proposed_action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["sensor_id"],
            p["device_name"],
            p["host"],
            p.get("alert_message", ""),
            p["classification"],
            p["evidence_score"],
            p["evidence_summary"],
            p["proposed_action"],
        ))
        count += 1
    conn.commit()
    conn.close()
    return count


def get_proposals(status: str | None = None) -> list[dict]:
    """Return proposals, optionally filtered by status."""
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM proposals ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Return counts of proposals grouped by status."""
    conn = get_conn()
    stats = {}
    for s in ("pending", "approved", "rejected"):
        stats[s] = conn.execute(
            "SELECT COUNT(*) FROM proposals WHERE status = ?", (s,)
        ).fetchone()[0]
    conn.close()
    return stats


def update_status(proposal_id: int, status: str, notes: str = "") -> bool:
    """Update a proposal's status. Returns False if not found or already reviewed."""
    conn = get_conn()
    cursor = conn.execute(
        """UPDATE proposals
              SET status = ?,
                  reviewed_at = CURRENT_TIMESTAMP,
                  reviewer_notes = ?
            WHERE id = ?
              AND status = 'pending'""",
        (status, notes, proposal_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
