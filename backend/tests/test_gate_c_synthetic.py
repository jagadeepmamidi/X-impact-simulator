from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.gate_c_synthetic import (
    DEFAULT_CORPUS_PATH,
    GATE_C_EMPIRICAL,
    SYNTHETIC_BANNER,
    SYNTHETIC_STATUS,
    SyntheticOutcomes,
    SyntheticPost,
    keyword_promo_baseline,
    length_baseline,
    load_corpus,
    main,
    random_baseline,
    run_backtest,
    spearman,
    tertile_labels,
)
from app.schemas import OutcomeRecord
from app.store import load_outcome, load_report


def test_corpus_has_at_least_20_tech_posts() -> None:
    posts = load_corpus()
    assert DEFAULT_CORPUS_PATH.is_file()
    assert len(posts) >= 20
    assert all(post.niche == "tech" for post in posts)
    assert all(post.observation_window_hours == 24 for post in posts)
    assert all(post.outcomes.impressions > 0 for post in posts)
    assert len({post.post_id for post in posts}) == len(posts)


def test_corpus_file_is_labeled_synthetic() -> None:
    payload = json.loads(DEFAULT_CORPUS_PATH.read_text(encoding="utf-8"))
    blob = json.dumps(payload).lower()
    assert payload["status"] == SYNTHETIC_STATUS
    assert "not empirical" in payload["disclaimer"].lower()
    assert "gate c is not complete" in payload["disclaimer"].lower()
    assert "synthetic" in blob


def test_outcome_schema_accepts_synthetic_source() -> None:
    record = OutcomeRecord(
        run_id="syn-test",
        impressions=100,
        likes=3,
        data_source="synthetic",
        note=SYNTHETIC_BANNER,
    )
    assert record.data_source == "synthetic"


def test_baselines_separate_promo_from_shipping_copy() -> None:
    shipping = "Shipped a local eval harness with 12ms p95 latency. Repro fixture included."
    promo = "Buy now! Limited discount subscribe follow for the promo link sale!"
    assert length_baseline(shipping) > length_baseline("gm")
    assert keyword_promo_baseline(shipping) > keyword_promo_baseline(promo)
    assert random_baseline("syn-tech-01", 42) != random_baseline("syn-tech-02", 42)
    assert random_baseline("syn-tech-01", 42) == random_baseline("syn-tech-01", 42)


def test_spearman_and_tertiles_are_stable() -> None:
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1, 1], [9, 8, 7, 6]) == 0.0
    labels = tertile_labels([1, 2, 3, 4, 5, 6])
    assert labels[0] == "low"
    assert labels[-1] == "high"


def test_synthetic_backtest_runs_offline_heuristic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.groq_api_key", "should-not-be-used")
    monkeypatch.setattr("app.groq_client.settings.groq_api_key", "should-not-be-used")
    out_dir = tmp_path / "report"
    report = run_backtest(
        seed=42,
        population=40,
        monte_carlo_runs=4,
        offline=True,
        persist=False,
        out_dir=out_dir,
        write=True,
    )
    assert report["status"] == SYNTHETIC_STATUS
    assert report["gate_c_empirical"] == GATE_C_EMPIRICAL
    assert report["claims"]["empirically_calibrated"] is False
    assert report["claims"]["gate_c_complete"] is False
    assert report["claims"]["unlocks_calibrated_or_public_beta_claims"] is False
    assert "NOT empirical calibration" in report["disclaimer"]
    assert report["corpus"]["n_posts"] >= 20
    assert report["run"]["inference"] == "heuristic-offline"
    assert all(row["simulator"]["inference_path"].startswith("heuristic") for row in report["posts"])
    assert all(row["simulator"]["confidence"] == 0.0 for row in report["posts"])

    metrics = report["metrics"]
    for target in ("impressions", "like_rate", "engagement_rate"):
        block = metrics["targets"][target]
        for method in ("simulator_impact_score", "length", "keyword_promo", "random"):
            assert -1.0 <= block[method]["spearman"] <= 1.0
            assert 0.0 <= block[method]["band_hit_rate"] <= 1.0
    assert "impact_tertiles_vs_impression_tertiles" in metrics["band_hit_rate"]
    assert metrics["bland_post_baseline"]["tech_pack_bland_score"] is not None

    json_path = out_dir / "backtest_report.json"
    csv_path = out_dir / "backtest_report.csv"
    md_path = out_dir / "backtest_summary.md"
    assert json_path.is_file()
    assert csv_path.is_file()
    assert md_path.is_file()
    summary = md_path.read_text(encoding="utf-8")
    assert "NOT empirical calibration" in summary
    assert "Gate C is NOT complete" in summary
    assert "Spearman" in summary


def test_optional_persist_labels_outcomes_synthetic(monkeypatch, tmp_path: Path) -> None:
    from app import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    report = run_backtest(
        posts=load_corpus()[:1],
        corpus_file=DEFAULT_CORPUS_PATH,
        seed=7,
        population=40,
        monte_carlo_runs=2,
        offline=True,
        persist=True,
        write=False,
        require_min_posts=False,
    )
    saved_ids = [row["simulator"]["run_id"] for row in report["posts"]]
    assert all(saved_ids)
    loaded = load_report(saved_ids[0], owner_id="synthetic-gate-c")
    assert loaded is not None
    outcome = load_outcome(saved_ids[0], owner_id="synthetic-gate-c")
    assert outcome is not None
    assert outcome.data_source == "synthetic"
    assert "NOT empirical calibration" in (outcome.note or "")


def test_cli_exits_zero(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--out-dir",
            str(tmp_path),
            "--monte-carlo-runs",
            "2",
            "--population",
            "40",
            "--seed",
            "42",
        ]
    )
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == SYNTHETIC_STATUS
    assert printed["gate_c_empirical"] == GATE_C_EMPIRICAL
    assert printed["n_posts"] >= 20
    assert (tmp_path / "backtest_report.json").is_file()


def test_checked_in_report_is_labeled_synthetic() -> None:
    report_path = DEFAULT_CORPUS_PATH.parent / "backtest_report.json"
    summary_path = DEFAULT_CORPUS_PATH.parent / "backtest_summary.md"
    csv_path = DEFAULT_CORPUS_PATH.parent / "backtest_report.csv"
    assert report_path.is_file()
    assert summary_path.is_file()
    assert csv_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == SYNTHETIC_STATUS
    assert payload["gate_c_empirical"] == GATE_C_EMPIRICAL
    assert payload["claims"]["gate_c_complete"] is False
    assert payload["corpus"]["n_posts"] >= 20
    summary = summary_path.read_text(encoding="utf-8")
    assert "NOT empirical calibration" in summary
    assert "Gate C is NOT complete" in summary


def test_docs_state_empirical_gate_c_blocked() -> None:
    docs = [
        DEFAULT_CORPUS_PATH.parent.parent / "GATE_C_SYNTHETIC.md",
        DEFAULT_CORPUS_PATH.parent.parent / "SOP_PILOT_ADDENDUM.md",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in docs).lower()
    assert "not empirical calibration" in joined
    assert "gate c" in joined and "blocked" in joined
    assert "synthetic" in joined


def test_injected_short_corpus_is_rejected() -> None:
    post = SyntheticPost(
        post_id="too-few",
        niche="tech",
        text="Shipped a 12ms eval harness.",
        published_at="2026-06-01T00:00:00Z",
        observed_at="2026-06-02T00:00:00Z",
        observation_window_hours=24,
        outcomes=SyntheticOutcomes(impressions=10, likes=1, replies=0, reposts=0, follows=0),
    )
    with pytest.raises(ValueError, match="at least 20"):
        run_backtest(posts=[post], write=False)
