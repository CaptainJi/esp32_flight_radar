from fastapi.testclient import TestClient

from main import app

c = TestClient(app)
print("health", c.get("/health").json())
r = c.post(
    "/v1/radio/turn",
    json={
        "flight": {"callsign": "CPA123", "altitude_m": 10000},
        "user_text": "say altitude",
        "want_audio": True,
    },
)
j = r.json()
print("status", r.status_code)
print("reply", (j.get("reply_text") or "")[:200])
print("mock", j.get("mock"), "ms", j.get("latency_ms"), "audio", j.get("audio_url"))
assert r.status_code == 200
assert j.get("reply_text")
print("OK")
