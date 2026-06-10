from fastapi.testclient import TestClient
import traceback

import api.server as s

client = TestClient(s.app)
try:
    r = client.get('/')
    print('STATUS', r.status_code)
    print('TEXT:\n', r.text)
except Exception as e:
    print('EXCEPTION')
    traceback.print_exc()
