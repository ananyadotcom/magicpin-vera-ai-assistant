import requests
import json
import time

BOT_URL = "http://localhost:8080"

def test_healthz():
    print("Testing /v1/healthz...")
    resp = requests.get(f"{BOT_URL}/v1/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print("  Healthz OK:", data)

def test_metadata():
    print("Testing /v1/metadata...")
    resp = requests.get(f"{BOT_URL}/v1/metadata")
    assert resp.status_code == 200
    print("  Metadata OK:", resp.json()["team_name"])

def push_context(scope, context_id, version, payload):
    req = {
        "scope": scope,
        "context_id": context_id,
        "version": version,
        "payload": payload,
        "delivered_at": "2026-09-27T10:00:00Z"
    }
    resp = requests.post(f"{BOT_URL}/v1/context", json=req)
    return resp

def test_context_and_tick():
    print("Testing /v1/context and /v1/tick...")
    
    # Push category
    cat_payload = {"slug": "gyms", "voice": {"tone": "energetic"}, "peer_stats": {}}
    push_context("category", "gyms", 1, cat_payload)
    
    # Push merchant
    merch_payload = {
        "merchant_id": "m_001",
        "category_slug": "gyms",
        "identity": {"name": "Test Gym"},
        "performance": {"views": 100}
    }
    push_context("merchant", "m_001", 1, merch_payload)
    
    # Push trigger
    trig_payload = {
        "id": "trg_123",
        "scope": "merchant",
        "kind": "perf_dip",
        "merchant_id": "m_001",
        "suppression_key": "perf_dip:m_001:none"
    }
    push_context("trigger", "trg_123", 1, trig_payload)
    
    # Send Tick
    tick_req = {
        "now": "2026-09-27T10:05:00Z",
        "available_triggers": ["trg_123"]
    }
    resp = requests.post(f"{BOT_URL}/v1/tick", json=tick_req)
    assert resp.status_code == 200
    data = resp.json()
    assert "actions" in data
    actions = data["actions"]
    assert len(actions) == 1
    
    action = actions[0]
    assert action["merchant_id"] == "m_001"
    assert action["send_as"] == "vera"
    print("  Tick generation OK:", action["body"])
    
    # Suppresion test: second tick should return no actions for same trigger
    resp2 = requests.post(f"{BOT_URL}/v1/tick", json=tick_req)
    data2 = resp2.json()
    assert len(data2["actions"]) == 0
    print("  Suppression logic OK.")
    
    return action["conversation_id"]

def test_reply(conv_id):
    print("Testing /v1/reply (auto-reply handling)...")
    
    # 1. First auto-reply
    req1 = {
        "conversation_id": conv_id,
        "merchant_id": "m_001",
        "from_role": "merchant",
        "message": "Thank you for contacting us.",
        "received_at": "2026-09-27T10:10:00Z",
        "turn_number": 2
    }
    resp1 = requests.post(f"{BOT_URL}/v1/reply", json=req1)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["action"] == "send"
    print("  Turn 1 auto-reply OK.")
    
    # 2. Second auto-reply
    req2 = req1.copy()
    req2["turn_number"] = 3
    resp2 = requests.post(f"{BOT_URL}/v1/reply", json=req2)
    data2 = resp2.json()
    assert data2["action"] == "wait"
    print("  Turn 2 auto-reply OK (wait).")
    
    # 3. Third auto-reply
    req3 = req1.copy()
    req3["turn_number"] = 4
    resp3 = requests.post(f"{BOT_URL}/v1/reply", json=req3)
    data3 = resp3.json()
    assert data3["action"] == "end"
    print("  Turn 3 auto-reply OK (end).")
    
    print("Testing intent transition (accept)...")
    req_accept = {
        "conversation_id": "new_conv",
        "merchant_id": "m_001",
        "from_role": "merchant",
        "message": "Yes, let's do it.",
        "received_at": "2026-09-27T10:10:00Z",
        "turn_number": 2
    }
    resp_accept = requests.post(f"{BOT_URL}/v1/reply", json=req_accept)
    assert resp_accept.json()["action"] == "send"
    print("  Accept intent OK.")
    
    print("Testing hostile reject...")
    req_reject = {
        "conversation_id": "new_conv",
        "merchant_id": "m_001",
        "from_role": "merchant",
        "message": "stop sending spam",
        "received_at": "2026-09-27T10:10:00Z",
        "turn_number": 3
    }
    resp_reject = requests.post(f"{BOT_URL}/v1/reply", json=req_reject)
    assert resp_reject.json()["action"] == "end"
    print("  Hostile reject OK.")

if __name__ == "__main__":
    test_healthz()
    test_metadata()
    conv_id = test_context_and_tick()
    test_reply(conv_id)
    print("All adaptive integration tests passed!")
