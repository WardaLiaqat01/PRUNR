"""
Lightweight mock monitoring server that simulates the PRTG REST API.
Returns a realistic mix of test scenarios for the cleanup agent.

Run with:  python -m mock_server.app
"""
from fastapi import FastAPI, HTTPException
import uvicorn

app = FastAPI(title="Mock Monitoring Server", version="1.0")

# ─── Test data: 5 sensors covering all 3 classification scenarios ─────────────
SENSORS = [
    # ── Orphaned: resource was decommissioned but sensor was never removed ─────
    {
        "objid": 1001, "name": "CPU Usage", "device": "WEB-SERVER-01",
        "host": "192.168.1.100", "status": "Down", "status_raw": 5,
        "message": "Ping timed out for 192.168.1.100",
        "lastdown": "2024-01-15 08:00:00",
    },
    {
        "objid": 1002, "name": "HTTP Check", "device": "OLD-APP-SERVER",
        "host": "app-legacy-01", "status": "Down", "status_raw": 5,
        "message": "DNS lookup failed for app-legacy-01",
        "lastdown": "2024-01-01 00:00:00",
    },
    # ── Broken connection: resource is alive but link to tool is broken ────────
    {
        "objid": 1003, "name": "WMI Monitor", "device": "FILE-SERVER-02",
        "host": "192.168.1.205", "status": "Down", "status_raw": 5,
        "message": "WMI authentication failed — access denied",
        "lastdown": "2024-03-12 08:30:00",
    },
    {
        "objid": 1004, "name": "Disk Space", "device": "DB-SERVER-PROD",
        "host": "10.0.0.50", "status": "Down", "status_raw": 5,
        "message": "Cannot connect to monitoring agent on port 9000",
        "lastdown": "2024-03-05 12:00:00",
    },
    # ── Uncertain: reachable but missing from AD/vCenter (switch/appliance) ────
    {
        "objid": 1005, "name": "SNMP Check", "device": "SWITCH-CORE-01",
        "host": "10.0.0.1", "status": "Down", "status_raw": 5,
        "message": "SNMP request timed out",
        "lastdown": "2024-03-10 16:00:00",
    },
]


@app.get("/api/sensors")
def get_sensors():
    """Return all down/alerting sensors."""
    return SENSORS


@app.delete("/api/sensors/{sensor_id}")
def delete_sensor(sensor_id: int):
    """Simulate sensor deletion (called after engineer approval)."""
    sensor = next((s for s in SENSORS if s["objid"] == sensor_id), None)
    if not sensor:
        raise HTTPException(404, f"Sensor {sensor_id} not found")
    return {"status": "deleted", "sensor_id": sensor_id, "device": sensor["device"]}


if __name__ == "__main__":
    uvicorn.run("mock_server.app:app", host="0.0.0.0", port=8080, reload=True)
