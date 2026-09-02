from fastapi.testclient import TestClient

from app.limits import limiter
from app.main import app

client = TestClient(app)


def test_missing_api_key_rejected(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    response = client.post("/api/simulate", data={"niche": "tech", "text": "hello", "population": "40"})
    assert response.status_code == 401


def test_valid_api_key_accepted(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    response = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "We shipped a 12ms eval harness.", "population": "40", "boost": "6"},
        headers={"X-API-Key": "secret-test-key"},
    )
    assert response.status_code == 200
    assert response.json()["affinity_reactions"]


def test_rate_limit_returns_429(monkeypatch) -> None:
    limiter.reset()
    monkeypatch.setattr("app.main.settings.rate_limit_requests", 1)
    monkeypatch.setattr("app.main.settings.rate_limit_window_seconds", 60)
    first = client.post("/api/simulate", data={"niche": "tech", "text": "first", "population": "40"})
    second = client.post("/api/simulate", data={"niche": "tech", "text": "second", "population": "40"})
    assert first.status_code == 200
    assert second.status_code == 429
    limiter.reset()


def test_replay_and_outcome_http() -> None:
    created = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "We open-sourced a 12ms eval harness.", "population": "40"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    replayed = client.post(f"/api/simulations/{run_id}/replay")
    assert replayed.status_code == 200
    body = replayed.json()
    assert body["parent_run_id"] == run_id
    assert body["inference_path"] == "replay+calibrated"
    saved = client.post(
        f"/api/simulations/{run_id}/outcome",
        json={"run_id": run_id, "impressions": 900, "likes": 12, "replies": 2, "reposts": 1, "follows": 0},
    )
    assert saved.status_code == 200
    loaded = client.get(f"/api/simulations/{run_id}/outcome")
    assert loaded.status_code == 200
    assert loaded.json()["impressions"] == 900
