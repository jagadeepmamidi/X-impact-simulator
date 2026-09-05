from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from app.config import settings
from app.schemas import ImpactReport, OutcomeRecord
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
_configured_db_path = Path(settings.sqlite_path)
DB_PATH = _configured_db_path if _configured_db_path.is_absolute() else REPO_ROOT / _configured_db_path
SNAPSHOT_SCHEMA_VERSION = "run-snapshot-v3"
_SCHEMA_LOCK = RLock()
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_OWNER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class UnknownRunError(ValueError):
    pass


class SnapshotIntegrityError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    with _SCHEMA_LOCK:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                niche TEXT NOT NULL,
                seed INTEGER NOT NULL,
                report_json TEXT NOT NULL,
                parent_run_id TEXT,
                simulator_version TEXT NOT NULL DEFAULT '',
                config_version TEXT NOT NULL DEFAULT '',
                input_hash TEXT NOT NULL DEFAULT '',
                snapshot_hash TEXT NOT NULL DEFAULT '',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                owner_id TEXT NOT NULL DEFAULT 'development'
            )"""
        )
        additions = {
            "parent_run_id": "TEXT",
            "simulator_version": "TEXT NOT NULL DEFAULT ''",
            "config_version": "TEXT NOT NULL DEFAULT ''",
            "input_hash": "TEXT NOT NULL DEFAULT ''",
            "snapshot_hash": "TEXT NOT NULL DEFAULT ''",
            "snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
            "owner_id": "TEXT NOT NULL DEFAULT 'development'",
        }
        existing = _table_columns(conn, "runs")
        for name, definition in additions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {definition}")

        conn.execute(
            """CREATE TABLE IF NOT EXISTS outcomes_v2 (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                outcome_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            )"""
        )
        if _table_columns(conn, "outcomes"):
            legacy_rows = conn.execute(
                """SELECT outcomes.run_id, outcomes.created_at, outcomes.outcome_json
                   FROM outcomes JOIN runs ON runs.id = outcomes.run_id"""
            ).fetchall()
            for row in legacy_rows:
                try:
                    payload = OutcomeRecord.model_validate(json.loads(row["outcome_json"]))
                except (json.JSONDecodeError, TypeError, ValidationError):
                    continue
                if payload.run_id != row["run_id"]:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO outcomes_v2
                       (run_id, created_at, updated_at, outcome_json) VALUES (?, ?, ?, ?)""",
                    (row["run_id"], row["created_at"], row["created_at"], payload.model_dump_json()),
                )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_parent_run_id ON runs(parent_run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_owner_id ON runs(owner_id)")
        conn.commit()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    with _SCHEMA_LOCK:
        conn.execute("PRAGMA journal_mode = WAL")
        _ensure_schema(conn)
    return conn


@contextmanager
def _connection():
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def snapshot_manifest(report: ImpactReport, owner_id: str = "development") -> dict[str, Any]:
    report_payload = report.model_dump(mode="json")
    report_payload.pop("run_id", None)
    report_payload.pop("snapshot_hash", None)
    content_payload = report.content.model_dump(mode="json")
    reactions_payload = [item.model_dump(mode="json") for item in report.reactions]
    affinities_payload = [item.model_dump(mode="json") for item in report.affinity_reactions]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "owner_hash": _sha256_text(owner_id),
        "simulator_version": report.simulator_version,
        "calibration_version": report.calibration_version,
        "config_version": report.config_version,
        "prompt_version": report.prompt_version,
        "persona_pack_version": report.persona_pack_version,
        "persona_pack_hash": report.persona_pack_hash,
        "dataset_revision": report.dataset_revision,
        "dataset_hash": report.dataset_hash,
        "action_model_version": report.action_model_version,
        "action_model_hash": report.action_model_hash,
        "weights_version": report.weights_version,
        "weights_hash": report.weights_hash,
        "niche": report.niche,
        "input_hash": report.input_hash,
        "input_text_hash": _sha256_text(report.input_text),
        "content_hash": _sha256_text(_canonical_json(content_payload)),
        "reactions_hash": _sha256_text(_canonical_json(reactions_payload)),
        "affinity_reactions_hash": _sha256_text(_canonical_json(affinities_payload)),
        "report_payload_hash": _sha256_text(_canonical_json(report_payload)),
        "probability_semantics": report.probability_semantics,
        "config": report.config_snapshot,
        "provenance": report.provenance,
        "seed": report.simulation.seed,
        "population": report.population,
        "boost": report.boost,
        "replay_contract_version": report.replay_contract_version,
        "replay_mode": report.replay_mode,
        "replayable": report.replayable,
    }


def snapshot_hash_for(report: ImpactReport, owner_id: str = "development") -> str:
    """Hash the exact provenance manifest exposed by the snapshot endpoint."""
    return _sha256_text(_canonical_json(snapshot_manifest(report, owner_id)))


def _prepare_report(
    report: ImpactReport, run_id: str, owner_id: str
) -> tuple[ImpactReport, dict[str, Any]]:
    input_hash = report.input_hash or (_sha256_text(report.input_text) if report.input_text else "")
    updated = report.model_copy(update={"run_id": run_id, "input_hash": input_hash})
    snapshot = snapshot_manifest(updated, owner_id)
    snapshot_hash = snapshot_hash_for(updated, owner_id)
    updated = updated.model_copy(update={"snapshot_hash": snapshot_hash})
    return updated, snapshot


def _owner(owner_id: str | None) -> str | None:
    if owner_id is None:
        return None
    value = owner_id.strip()
    if not _OWNER_ID_RE.fullmatch(value):
        raise ValueError("Invalid owner id")
    return value


def _legacy_report(report: ImpactReport) -> ImpactReport:
    limitation = "Legacy snapshot did not bind the complete report payload; exact replay is disabled."
    limitations = list(dict.fromkeys([*report.replay_limitations, limitation]))
    return report.model_copy(
        update={
            "replayable": False,
            "replay_mode": "legacy-approximate",
            "replay_limitations": limitations,
            "provenance": {**report.provenance, "snapshot_integrity": "legacy-unverified"},
        }
    )


def _verified_report(row: sqlite3.Row, run_id: str) -> tuple[ImpactReport, dict[str, Any]]:
    try:
        report = ImpactReport.model_validate(json.loads(row["report_json"]))
        snapshot = json.loads(row["snapshot_json"] or "{}")
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise SnapshotIntegrityError("Stored simulation payload is invalid") from exc
    if not isinstance(snapshot, dict):
        raise SnapshotIntegrityError("Stored simulation snapshot is invalid")
    if report.run_id not in {None, run_id}:
        raise SnapshotIntegrityError("Stored simulation id mismatch")
    if report.run_id is None:
        report = report.model_copy(update={"run_id": run_id})
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        stored_hash = str(row["snapshot_hash"] or "")
        if stored_hash and not hmac.compare_digest(stored_hash, _sha256_text(_canonical_json(snapshot))):
            raise SnapshotIntegrityError("Stored legacy snapshot hash mismatch")
        return _legacy_report(report), snapshot
    stored_hash = str(row["snapshot_hash"] or "")
    serialized_hash = _sha256_text(_canonical_json(snapshot))
    if not stored_hash or not hmac.compare_digest(stored_hash, serialized_hash):
        raise SnapshotIntegrityError("Stored simulation snapshot hash mismatch")
    expected = snapshot_manifest(report, str(row["owner_id"]))
    expected_hash = _sha256_text(_canonical_json(expected))
    metadata_matches = (
        report.run_id == run_id
        and str(row["input_hash"] or "") == report.input_hash
        and int(row["seed"]) == report.simulation.seed
        and str(row["simulator_version"] or "") == report.simulator_version
        and str(row["config_version"] or "") == report.config_version
        and hmac.compare_digest(report.snapshot_hash, stored_hash)
    )
    if expected != snapshot or not hmac.compare_digest(expected_hash, stored_hash) or not metadata_matches:
        raise SnapshotIntegrityError("Stored simulation failed integrity verification")
    return report, snapshot


def _purge_expired(conn: sqlite3.Connection) -> int:
    days = settings.run_retention_days
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    if _table_columns(conn, "outcomes"):
        conn.execute(
            "DELETE FROM outcomes WHERE run_id IN (SELECT id FROM runs WHERE created_at < ?)",
            (cutoff,),
        )
    cursor = conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))
    return max(0, cursor.rowcount)


def save_report(report: ImpactReport, owner_id: str = "development") -> str:
    run_id = report.run_id or uuid.uuid4().hex
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Invalid simulation id")
    owner_id = _owner(owner_id) or "development"
    payload, snapshot = _prepare_report(report, run_id, owner_id)
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        _purge_expired(conn)
        conn.execute(
            """INSERT INTO runs (
                   id, created_at, niche, seed, report_json, parent_run_id,
                   simulator_version, config_version, input_hash, snapshot_hash, snapshot_json, owner_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   niche=excluded.niche,
                   seed=excluded.seed,
                   report_json=excluded.report_json,
                   parent_run_id=excluded.parent_run_id,
                   simulator_version=excluded.simulator_version,
                   config_version=excluded.config_version,
                   input_hash=excluded.input_hash,
                   snapshot_hash=excluded.snapshot_hash,
                   snapshot_json=excluded.snapshot_json,
                   owner_id=excluded.owner_id""",
            (
                run_id,
                now,
                payload.niche,
                payload.simulation.seed,
                payload.model_dump_json(),
                payload.parent_run_id,
                payload.simulator_version,
                payload.config_version,
                payload.input_hash,
                payload.snapshot_hash,
                _canonical_json(snapshot),
                owner_id,
            ),
        )
    return run_id


def load_report(run_id: str, owner_id: str | None = None) -> ImpactReport | None:
    owner_id = _owner(owner_id)
    with _connection() as conn:
        _purge_expired(conn)
        sql = """SELECT report_json, snapshot_json, snapshot_hash, input_hash, seed,
                        simulator_version, config_version, owner_id FROM runs WHERE id = ?"""
        params: tuple[Any, ...] = (run_id.strip(),)
        if owner_id is not None:
            sql += " AND owner_id = ?"
            params += (owner_id,)
        row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    report, _ = _verified_report(row, run_id.strip())
    return report


def list_reports(*, owner_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent, integrity-verified run summaries visible to the owner."""
    owner_id = _owner(owner_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with _connection() as conn:
        _purge_expired(conn)
        sql = """SELECT id, created_at, niche, report_json, snapshot_json, snapshot_hash,
                        input_hash, seed, simulator_version, config_version, owner_id,
                        EXISTS(SELECT 1 FROM outcomes_v2 o WHERE o.run_id = runs.id) AS has_outcome
                   FROM runs"""
        params: tuple[Any, ...] = ()
        if owner_id is not None:
            sql += " WHERE owner_id = ?"
            params = (owner_id,)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params += (limit,)
        rows = conn.execute(sql, params).fetchall()
    summaries: list[dict[str, Any]] = []
    for row in rows:
        report, _ = _verified_report(row, str(row["id"]))
        summaries.append(
            {
                "run_id": str(row["id"]),
                "created_at": str(row["created_at"]),
                "niche": report.niche,
                "input_text": report.input_text,
                "population": report.population,
                "boost": report.boost,
                "has_outcome": bool(row["has_outcome"]),
            }
        )
    return summaries


def load_snapshot(run_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
    owner_id = _owner(owner_id)
    with _connection() as conn:
        _purge_expired(conn)
        sql = """SELECT report_json, snapshot_json, snapshot_hash, input_hash, seed,
                        simulator_version, config_version, owner_id FROM runs WHERE id = ?"""
        params: tuple[Any, ...] = (run_id.strip(),)
        if owner_id is not None:
            sql += " AND owner_id = ?"
            params += (owner_id,)
        row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    _, snapshot = _verified_report(row, run_id.strip())
    return snapshot


def delete_report(run_id: str, owner_id: str | None = None) -> bool:
    owner_id = _owner(owner_id)
    with _connection() as conn:
        _purge_expired(conn)
        where = "id = ?" + (" AND owner_id = ?" if owner_id is not None else "")
        params: tuple[Any, ...] = (run_id.strip(),) + ((owner_id,) if owner_id is not None else ())
        cursor = conn.execute(f"DELETE FROM runs WHERE {where}", params)
        if cursor.rowcount > 0 and _table_columns(conn, "outcomes"):
            conn.execute("DELETE FROM outcomes WHERE run_id = ?", (run_id.strip(),))
    return cursor.rowcount > 0


def save_outcome(record: OutcomeRecord, owner_id: str | None = None) -> OutcomeRecord:
    payload = record.model_copy()
    owner_id = _owner(owner_id)
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        _purge_expired(conn)
        sql = "SELECT 1 FROM runs WHERE id = ?" + (" AND owner_id = ?" if owner_id is not None else "")
        params: tuple[Any, ...] = (payload.run_id,) + ((owner_id,) if owner_id is not None else ())
        exists = conn.execute(sql, params).fetchone()
        if not exists:
            raise UnknownRunError(f"Unknown simulation id: {payload.run_id}")
        conn.execute(
            """INSERT INTO outcomes_v2 (run_id, created_at, updated_at, outcome_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET
                   updated_at=excluded.updated_at,
                   outcome_json=excluded.outcome_json""",
            (payload.run_id, now, now, payload.model_dump_json()),
        )
    return payload


def load_outcome(run_id: str, owner_id: str | None = None) -> OutcomeRecord | None:
    owner_id = _owner(owner_id)
    with _connection() as conn:
        _purge_expired(conn)
        sql = """SELECT outcomes_v2.outcome_json FROM outcomes_v2
                 JOIN runs ON runs.id = outcomes_v2.run_id
                 WHERE outcomes_v2.run_id = ?"""
        params: tuple[Any, ...] = (run_id.strip(),)
        if owner_id is not None:
            sql += " AND runs.owner_id = ?"
            params += (owner_id,)
        row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    try:
        return OutcomeRecord.model_validate(json.loads(row["outcome_json"]))
    except (json.JSONDecodeError, TypeError, ValidationError):
        return None


def storage_status() -> dict[str, str | bool | int]:
    return {
        "backend": "sqlite",
        "production_ready": False,
        "scope": "single-node development",
        "retention_days": settings.run_retention_days,
    }
