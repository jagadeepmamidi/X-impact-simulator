import pytest
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError

import app.store as store
from app.schemas import ContentFeatures, Explanation, ImpactReport, OutcomeRecord, SimulationSummary


def _report() -> ImpactReport:
    return ImpactReport(
        disclaimer="Experimental",
        niche="tech",
        groq_used=False,
        content=ContentFeatures(),
        reactions=[],
        simulation=SimulationSummary(
            seed=7,
            runs=3,
            rounds=[],
            score_p10=10,
            score_p50=20,
            score_p90=30,
            reached_round_p50=2,
            out_of_network=False,
        ),
        impact_score=20,
        explanation=Explanation(headline="h", summary="s", suggestions=["test"]),
        weights_note="w",
        simulator_version="sim-v2",
        config_version="config-v3",
        calibration_version="priors-v2",
        prompt_version="prompt-v3",
        input_text="private input is represented by a hash in the snapshot",
        probability_semantics="multilabel calibrated marginals",
        config_snapshot={"max_rounds": 6, "policy": "candidate-slate-v1"},
        provenance={"content_analyzer": "heuristic-v2"},
        persona_pack_version="persona-v2",
        persona_pack_hash="a" * 64,
        weights_version="x-public-2026-09-03",
        weights_hash="b" * 64,
        replayable=True,
    )


def test_structured_snapshot_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    run_id = store.save_report(_report())
    loaded = store.load_report(run_id)
    snapshot = store.load_snapshot(run_id)

    assert len(run_id) == 32
    assert loaded is not None
    assert len(loaded.input_hash) == 64
    assert len(loaded.snapshot_hash) == 64
    assert snapshot is not None
    assert snapshot["schema_version"] == store.SNAPSHOT_SCHEMA_VERSION
    assert snapshot["config"]["policy"] == "candidate-slate-v1"
    assert snapshot["persona_pack_hash"] == "a" * 64
    assert snapshot["input_text_hash"]
    assert snapshot["content_hash"]
    assert snapshot["reactions_hash"]
    assert snapshot["affinity_reactions_hash"]
    assert snapshot["report_payload_hash"]


def test_outcome_requires_existing_run_and_cascades_on_delete(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    with pytest.raises(store.UnknownRunError):
        store.save_outcome(OutcomeRecord(run_id="missing", impressions=10, likes=1))

    run_id = store.save_report(_report())
    saved = store.save_outcome(
        OutcomeRecord(
            run_id=run_id,
            impressions=100,
            likes=10,
            replies=2,
            observation_window_hours=24,
        )
    )
    assert store.load_outcome(run_id) == saved
    assert store.delete_report(run_id) is True
    assert store.load_report(run_id) is None
    assert store.load_outcome(run_id) is None


def test_outcome_validation_rejects_impossible_counts() -> None:
    with pytest.raises(ValidationError):
        OutcomeRecord(run_id="run", impressions=-1)
    with pytest.raises(ValidationError, match="likes cannot exceed impressions"):
        OutcomeRecord(run_id="run", impressions=5, likes=6)
    with pytest.raises(ValidationError, match="impressions is required"):
        OutcomeRecord(run_id="run", likes=1)


def test_snapshot_tampering_fails_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    run_id = store.save_report(_report())
    with sqlite3.connect(store.DB_PATH) as conn:
        raw = conn.execute("SELECT report_json FROM runs WHERE id = ?", (run_id,)).fetchone()[0]
        payload = json.loads(raw)
        payload["impact_score"] = 99
        conn.execute("UPDATE runs SET report_json = ? WHERE id = ?", (json.dumps(payload), run_id))
    with pytest.raises(store.SnapshotIntegrityError):
        store.load_report(run_id)


def test_owner_filters_runs_and_outcomes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    run_id = store.save_report(_report(), owner_id="alice")
    assert store.load_report(run_id, owner_id="alice") is not None
    assert store.load_report(run_id, owner_id="bob") is None
    record = OutcomeRecord(run_id=run_id, impressions=10, likes=1)
    assert store.save_outcome(record, owner_id="alice") == record
    assert store.load_outcome(run_id, owner_id="bob") is None
    assert store.delete_report(run_id, owner_id="bob") is False
    assert store.delete_report(run_id, owner_id="alice") is True


def test_retention_is_enforced_during_read(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    monkeypatch.setattr(store.settings, "run_retention_days", 1)
    run_id = store.save_report(_report())
    expired = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with sqlite3.connect(store.DB_PATH) as conn:
        conn.execute("UPDATE runs SET created_at = ? WHERE id = ?", (expired, run_id))
    assert store.load_report(run_id) is None
    with sqlite3.connect(store.DB_PATH) as conn:
        assert conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is None


def test_invalid_legacy_outcome_is_skipped(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    run_id = store.save_report(_report())
    with sqlite3.connect(store.DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE outcomes (
                run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, outcome_json TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO outcomes VALUES (?, ?, ?)",
            (run_id, datetime.now(timezone.utc).isoformat(), json.dumps({"run_id": run_id, "likes": 4})),
        )
    assert store.load_outcome(run_id) is None
