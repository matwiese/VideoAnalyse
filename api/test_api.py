from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_params_have_status():
    r = client.get("/api/params")
    assert r.status_code == 200
    assert r.json()["board.k_tip_75"]["status"] == "Literatur"


def test_simulate_level1():
    r = client.post("/api/simulate/level1", json={"preset": "elite_w_58", "overrides": {"board.fulcrum": 6.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["events"]["TO"] > body["events"]["LP"] > 0
    rows = {m["key"]: m for m in body["metrics"]}
    assert rows["v_z_to"]["status"] == "Schätzung"
    assert rows["board_f0"]["status"] == "Literatur" or rows["board_f0"]["status"] == "Schätzung"
    t = body["series"]["t"]
    assert abs((t[1] - t[0]) - 1e-3) < 1e-12  # 1 kHz


def test_invalid_param_rejected():
    r = client.post("/api/simulate/level1", json={"overrides": {"board.fulcrum": 20}})
    assert r.status_code == 422


def test_health():
    assert client.get("/api/health").json()["levels"] == [1, 2]


def test_simulate_level2():
    r = client.post("/api/simulate/level2", json={"preset": "elite_w_58", "overrides": {"numerics.rtol2": 1e-6}})
    assert r.status_code == 200, r.text
    body = r.json()
    rows = {m["key"]: m for m in body["metrics"]}
    assert rows["H_y"]["status"] == "Schätzung" and rows["H_y"]["value"] is not None
    assert len(body["series"]["theta"][0]) == 6
    assert len(body["series"]["points"][0]) == 24


def test_optimize_job_level1():
    import time

    r = client.post("/api/optimize", json={"level": 1, "overrides": {}, "generations": 2, "popsize": 4, "robust": False})
    jid = r.json()["job"]
    for _ in range(300):
        st = client.get(f"/api/jobs/{jid}").json()
        if st["status"] != "läuft":
            break
        time.sleep(0.2)
    assert st["status"] == "fertig", st
    assert st["result"]["best_score"] >= st["result"]["baseline_score"]
