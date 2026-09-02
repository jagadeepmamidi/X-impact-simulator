from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import ImpactReport, OutcomeRecord

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "runs.sqlite"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            niche TEXT NOT NULL,
            seed INTEGER NOT NULL,
            report_json TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS outcomes (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            outcome_json TEXT NOT NULL
        )"""
    )
    return conn


def save_report(report: ImpactReport) -> str:
    run_id = report.run_id or uuid.uuid4().hex[:10]
    payload = report.model_copy(update={"run_id": run_id})
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (id, created_at, niche, seed, report_json) VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                datetime.now(timezone.utc).isoformat(),
                payload.niche,
                payload.simulation.seed,
                payload.model_dump_json(),
            ),
        )
    return run_id


def load_report(run_id: str) -> ImpactReport | None:
    with _connect() as conn:
        row = conn.execute("SELECT report_json FROM runs WHERE id = ?", (run_id.strip(),)).fetchone()
    if not row:
        return None
    return ImpactReport.model_validate(json.loads(row[0]))


def save_outcome(record: OutcomeRecord) -> OutcomeRecord:
    payload = record.model_copy()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO outcomes (run_id, created_at, outcome_json) VALUES (?, ?, ?)",
            (payload.run_id, datetime.now(timezone.utc).isoformat(), payload.model_dump_json()),
        )
    return payload


def load_outcome(run_id: str) -> OutcomeRecord | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT outcome_json FROM outcomes WHERE run_id = ?", (run_id.strip(),)
        ).fetchone()
    if not row:
        return None
    return OutcomeRecord.model_validate(json.loads(row[0]))
