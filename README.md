PRUNR
=====

PRUNR (PRUNing dead branches off the tree) is a small tool to find and propose cleanup actions for stale/alerting monitoring sensors. It ships with a FastAPI UI and a mock monitoring server for local testing.

Quick start
-----------
1. Install dependencies:
   python -m pip install -r requirements.txt

2. Configure environment:
   copy .env.example .env
   (set ANTHROPIC_API_KEY if you want LLM summaries)
   MONITORING_API_URL defaults to http://127.0.0.1:8080

3. Start the mock monitoring server (in a separate terminal):
   python -m mock_server.app

4. Start the API/UI server:
   python main.py
   Open http://localhost:8000 in your browser and click "Run agent scan".

API
---
- GET /api/proposals — list proposals
- GET /api/stats — counts
- POST /api/run-agent — run the cleanup agent synchronously
- POST /api/proposals/{id}/approve — approve a proposal
- POST /api/proposals/{id}/reject — reject a proposal

Notes
-----
- The mock server returns test sensors; to connect to a real monitoring API set MONITORING_API_URL in .env.
- The agent uses simple rule-based checks by default (agents/tools.py). Replace mocks with production integrations to enable AD, vCenter, CMDB checks.

License
-------
See LICENSE in the repository for licensing information.
