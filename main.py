"""
Starts the Alerts Cleanup Agent API server on http://localhost:8000

Before running:
  1. Start the mock monitoring server first (separate terminal):
       python -m mock_server.app

  2. Copy .env.example to .env and fill in your ANTHROPIC_API_KEY:
       cp .env.example .env

  3. Start this server:
       python main.py

  4. Open http://localhost:8000 in your browser and click "Run agent scan"
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug",
    )
