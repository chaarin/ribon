"""웹 API: 세션 생성 → Cycle 진행 → 검사 입력 → 교체 → 비교."""
import pytest
from fastapi.testclient import TestClient

from src.web.server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def play(client, preset_id, overrides=None, edit_inspection=None):
    sid = client.post("/api/sessions", json={"preset_id": preset_id, "overrides": overrides}).json()["session_id"]
    records = []
    while True:
        rec = client.post(f"/api/sessions/{sid}/step").json()
        records.append(rec)
        while rec["pending"]:
            if rec["pending"]["type"] == "inspection":
                values = edit_inspection(rec) if edit_inspection else rec["pending"]["suggested"]
                rec = client.post(f"/api/sessions/{sid}/inspection", json={"values": values}).json()
            else:
                rec = client.post(f"/api/sessions/{sid}/remeasure").json()
            records.append(rec)
        if rec["finished"]:
            return sid, records


def test_presets_listed(client):
    data = client.get("/api/presets").json()
    assert {p["id"] for p in data["presets"]} == {"finishing", "roughing", "no_stock", "due_tight", "no_inspection"}
    assert data["total_cycles"] == 68


def test_full_session_matches_batch_replay(client):
    sid, records = play(client, "finishing")
    last = records[-1]
    assert last["decision"]["action"] == "REPLACE_NOW" and last["cycle"] == 13
    assert [r["cycle"] for r in records if r["kind"] == "inspection"] == [1, 7, 13]
    assert all(e["measured"] for e in records[-1]["wear"]["edges"])
    comp = client.get(f"/api/sessions/{sid}/comparison").json()
    assert comp["system_source"] == "session"
    assert len(comp["outcomes"]) == 5


def test_presenter_can_change_inspection_values(client):
    # 첫 검사에서 Edge 2를 한계 이상으로 입력하면 바로 교체 판단이 나와야 한다
    def bad_edge(rec):
        return {**rec["pending"]["suggested"], "2": 0.35}

    _, records = play(client, "finishing", edit_inspection=bad_edge)
    assert records[-1]["cycle"] == 1
    assert records[-1]["decision"]["action"] == "REPLACE_NOW"


def test_overrides_apply(client):
    _, records = play(client, "finishing", overrides={"tool_purpose": "roughing", "inspection_available": False})
    assert records[-1]["cycle"] > 13
    assert not any(r["kind"] == "inspection" for r in records)


def test_step_blocked_while_inspection_pending(client):
    sid = client.post("/api/sessions", json={"preset_id": "finishing"}).json()["session_id"]
    rec = client.post(f"/api/sessions/{sid}/step").json()
    assert rec["pending"]["type"] == "inspection"
    assert client.post(f"/api/sessions/{sid}/step").status_code == 409


def test_truth(client):
    t = client.get("/api/truth").json()
    assert len(t["worst_vb_mm"]) == 68 and t["sigma_mm"] > 0
