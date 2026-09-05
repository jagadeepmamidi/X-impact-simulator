from datetime import datetime, timedelta, timezone

import app.store as store
import app.main as main
from fastapi.testclient import TestClient
from app.limits import limiter
from app.schemas import OutcomeRecord
from test_store_v2 import _report


def test_recent_runs_endpoint_auth_and_limits(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    monkeypatch.setattr(main.settings, "sim_api_key", "")
    monkeypatch.setattr(main.settings, "sim_access_keys_json", '{"alice":"alice-fixture","bob":"bob-fixture"}')
    alice = store.save_report(_report(), owner_id="alice")
    bob = store.save_report(_report(), owner_id="bob")
    limiter.reset()
    with TestClient(main.app) as client:
        assert client.get("/api/simulations").status_code == 401
        for key, expected in [("alice-fixture", alice), ("bob-fixture", bob)]:
            response = client.get("/api/simulations?limit=1", headers={"X-API-Key": key})
            assert response.status_code == 200
            assert [row["run_id"] for row in response.json()["runs"]] == [expected]
        for invalid in [0, 101]:
            assert client.get(f"/api/simulations?limit={invalid}", headers={"X-API-Key": "alice-fixture"}).status_code == 422
    limiter.reset()


def test_list_reports_is_owner_scoped_and_marks_outcomes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    alice_run = store.save_report(_report(), owner_id="alice")
    store.save_report(_report(), owner_id="bob")
    store.save_outcome(OutcomeRecord(run_id=alice_run, impressions=10, likes=1), owner_id="alice")

    rows = store.list_reports(owner_id="alice", limit=20)
    assert [row["run_id"] for row in rows] == [alice_run]
    assert rows[0]["has_outcome"] is True
    assert set(rows[0]) == {"run_id", "created_at", "niche", "input_text", "population", "boost", "has_outcome"}


def test_list_reports_purges_expired_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    monkeypatch.setattr(store.settings, "run_retention_days", 1)
    run_id = store.save_report(_report())
    expired = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with store._connection() as conn:
        conn.execute("UPDATE runs SET created_at = ? WHERE id = ?", (expired, run_id))
    assert store.list_reports(owner_id="development", limit=20) == []
