import traceback
from fastapi.testclient import TestClient
import api.server as s

client = TestClient(s.app)
try:
    r = client.post('/api/run-agent')
    print('STATUS', r.status_code)
    print('TEXT:', r.text)
except Exception:
    traceback.print_exc()
