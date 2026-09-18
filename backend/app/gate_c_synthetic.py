"""Synthetic Gate C backtest: harness/pipeline validation only.

This module is **not** empirical calibration and does **not** complete Gate C.
Posts and outcomes are authored fixtures, not observed X impressions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app.config import settings
from app.metrics import bland_baseline
from app.persona_population import load_audience
from app.pipeline import run_pipeline
from app.schemas import ImpactReport, Niche, OutcomeRecord
from app.sim_config import CALIBRATION_VERSION, SIMULATOR_VERSION
from app.store import save_outcome

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = REPO_ROOT / "research" / "gate_c_synthetic" / "synthetic_posts.json"
DEFAULT_OUT_DIR = REPO_ROOT / "research" / "gate_c_synthetic"

SYNTHETIC_STATUS = "synthetic-harness-only"
GATE_C_EMPIRICAL = "blocked"
SYNTHETIC_BANNER = (
    "SYNTHETIC validation of the harness/pipeline. "
    "NOT empirical calibration. Gate C is NOT complete. "
    "These posts and outcomes were authored for offline testing; "
    "they are not observed X impressions."
)

DEFAULT_SEED = 42
DEFAULT_POPULATION = 40
DEFAULT_BOOST = 6
DEFAULT_MONTE_CARLO_RUNS = 8
OWNER_ID = "synthetic-gate-c"

_STOP = frozenset(
    "the and for with this that from your are was you not but how why who what when".split()
)
_PROMO_WORDS = frozenset(
    {
        "buy",
        "discount",
        "sale",
        "subscribe",
        "follow",
        "promo",
        "waitlist",
        "signup",
        "sign",
        "link",
        "offer",
        "limited",
        "bio",
        "codes",
        "tonight",
    }
)
_TECH_WORDS = frozenset(
    {
        "latency",
        "benchmark",
        "opensource",
        "oss",
        "eval",
        "llm",
        "kernel",
        "cve",
        "p95",
        "throughput",
        "rust",
        "gpu",
        "compiler",
        "repro",
        "reproducible",
        "postmortem",
        "sha",
        "pytest",
        "sqlite",
        "replay",
        "ranking",
        "tokenizer",
        "fixture",
        "cache",
        "rag",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SyntheticOutcomes:
    impressions: float
    likes: float
    replies: float
    reposts: float
    follows: float
    quotes: float = 0.0
    shares: float = 0.0

    def like_rate(self) -> float:
        return _rate(self.likes, self.impressions)

    def engagement_rate(self) -> float:
        return _rate(self.likes + self.replies + self.reposts, self.impressions)


@dataclass(frozen=True)
class SyntheticPost:
    post_id: str
    niche: Niche
    text: str
    published_at: str
    observed_at: str
    observation_window_hours: float
    outcomes: SyntheticOutcomes
    archetype: str = ""


def _rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _tokens(text: str) -> list[str]:
    return [token for token in _WORD_RE.findall(text.lower()) if token not in _STOP]


def load_corpus(path: Path | None = None) -> list[SyntheticPost]:
    target = path or DEFAULT_CORPUS_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    posts_raw = raw.get("posts") if isinstance(raw, dict) else raw
    if not isinstance(posts_raw, list) or not posts_raw:
        raise ValueError(f"{target} must contain a non-empty posts array")
    posts: list[SyntheticPost] = []
    for item in posts_raw:
        if not isinstance(item, dict):
            raise ValueError("each corpus row must be an object")
        outcomes_raw = item.get("synthetic_outcomes") or {}
        post = SyntheticPost(
            post_id=str(item["post_id"]),
            niche=item.get("niche") or "tech",
            text=str(item["text"]),
            published_at=str(item["published_at"]),
            observed_at=str(item["observed_at"]),
            observation_window_hours=float(item.get("observation_window_hours") or 24),
            outcomes=SyntheticOutcomes(
                impressions=float(outcomes_raw["impressions"]),
                likes=float(outcomes_raw.get("likes") or 0),
                replies=float(outcomes_raw.get("replies") or 0),
                reposts=float(outcomes_raw.get("reposts") or 0),
                follows=float(outcomes_raw.get("follows") or 0),
                quotes=float(outcomes_raw.get("quotes") or 0),
                shares=float(outcomes_raw.get("shares") or 0),
            ),
            archetype=str(item.get("archetype") or ""),
        )
        _validate_post(post)
        posts.append(post)
    ids = [post.post_id for post in posts]
    if len(ids) != len(set(ids)):
        raise ValueError("synthetic corpus post_id values must be unique")
    if len(posts) < 20:
        raise ValueError("synthetic Gate C corpus must contain at least 20 posts")
    return posts


def _validate_post(post: SyntheticPost) -> None:
    if post.niche != "tech":
        raise ValueError(f"{post.post_id}: beachhead corpus must use niche=tech")
    if not post.text.strip():
        raise ValueError(f"{post.post_id}: text is required")
    datetime.fromisoformat(post.published_at.replace("Z", "+00:00"))
    datetime.fromisoformat(post.observed_at.replace("Z", "+00:00"))
    counts = (
        post.outcomes.likes,
        post.outcomes.replies,
        post.outcomes.reposts,
        post.outcomes.follows,
        post.outcomes.quotes,
        post.outcomes.shares,
    )
    if any(value < 0 for value in counts) or post.outcomes.impressions < 0:
        raise ValueError(f"{post.post_id}: outcome counts must be nonnegative")
    if any(value > post.outcomes.impressions for value in counts):
        raise ValueError(f"{post.post_id}: action counts cannot exceed impressions")
    if post.observation_window_hours <= 0:
        raise ValueError(f"{post.post_id}: observation_window_hours must be positive")


def length_baseline(text: str) -> float:
    return float(len(_tokens(text)))


def keyword_promo_baseline(text: str) -> float:
    tokens = _tokens(text)
    promo = sum(1 for token in tokens if token in _PROMO_WORDS)
    tech = sum(1 for token in tokens if token in _TECH_WORDS)
    question = 1.0 if "?" in text else 0.0
    length_term = min(len(tokens) / 40.0, 1.0)
    return float(2.0 * tech - 3.0 * promo + question + length_term)


def random_baseline(post_id: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{post_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _rankdata(values: Sequence[float]) -> list[float]:
    n = len(values)
    order = sorted(range(n), key=lambda index: (values[index], index))
    ranks = [0.0] * n
    index = 0
    while index < n:
        end = index
        while end + 1 < n and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2.0 + 1.0
        for cursor in range(index, end + 1):
            ranks[order[cursor]] = average
        index = end + 1
    return ranks


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return num / (den_x * den_y)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    return pearson(_rankdata(xs), _rankdata(ys))


def kendall_tau(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n != len(ys) or n < 2:
        return 0.0
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            product = dx * dy
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    denom = concordant + discordant
    if denom == 0:
        return 0.0
    return (concordant - discordant) / denom


def tertile_labels(values: Sequence[float]) -> list[str]:
    if not values:
        return []
    ordered = sorted(values)
    n = len(ordered)
    low_cut = ordered[max(0, n // 3 - 1)]
    high_cut = ordered[min(n - 1, (2 * n) // 3)]
    labels: list[str] = []
    for value in values:
        if value <= low_cut:
            labels.append("low")
        elif value >= high_cut:
            labels.append("high")
        else:
            labels.append("mid")
    return labels


def band_hit_rate(predicted: Sequence[float], observed: Sequence[float]) -> float:
    pred_bands = tertile_labels(predicted)
    obs_bands = tertile_labels(observed)
    if not pred_bands:
        return 0.0
    hits = sum(1 for left, right in zip(pred_bands, obs_bands, strict=True) if left == right)
    return hits / len(pred_bands)


def _association(predicted: Sequence[float], observed: Sequence[float]) -> dict[str, float]:
    return {
        "spearman": round(spearman(predicted, observed), 4),
        "kendall_tau": round(kendall_tau(predicted, observed), 4),
        "band_hit_rate": round(band_hit_rate(predicted, observed), 4),
    }


@contextmanager
def _offline_groq(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    previous = settings.groq_api_key
    settings.groq_api_key = ""
    try:
        yield
    finally:
        settings.groq_api_key = previous


@contextmanager
def _monte_carlo_runs(runs: int) -> Iterator[None]:
    previous = settings.sim_monte_carlo_runs
    settings.sim_monte_carlo_runs = int(runs)
    try:
        yield
    finally:
        settings.sim_monte_carlo_runs = previous


def _score_band(report: ImpactReport) -> dict[str, float | str]:
    return {
        "impact_score": report.impact_score,
        "score_p10": report.simulation.score_p10,
        "score_p50": report.simulation.score_p50,
        "score_p90": report.simulation.score_p90,
        "audience_fit": report.audience_fit,
        "niche_index": report.niche_index,
        "negative_signal_risk": report.negative_signal_risk,
        "stability": report.stability,
        "confidence": report.confidence,
        "reach_pct": report.reach_pct,
        "distribution_potential": report.distribution_potential,
        "engagement_quality": report.engagement_quality,
        "profile_impact": report.profile_impact,
        "stop_reason": report.stop_reason,
    }


def simulate_post(
    post: SyntheticPost,
    *,
    seed: int,
    population: int,
    boost: int,
    persist: bool,
) -> ImpactReport:
    post_seed = int(hashlib.sha256(f"{seed}:{post.post_id}".encode("utf-8")).hexdigest()[:8], 16)
    return run_pipeline(
        post.niche,
        post.text,
        [],
        None,
        seed=post_seed,
        population=population,
        boost=boost,
        persist=persist,
        owner_id=OWNER_ID,
    )


def _attach_outcome(report: ImpactReport, post: SyntheticPost) -> None:
    run_id = report.run_id
    if not run_id:
        return
    save_outcome(
        OutcomeRecord(
            run_id=run_id,
            impressions=post.outcomes.impressions,
            likes=post.outcomes.likes,
            replies=post.outcomes.replies,
            reposts=post.outcomes.reposts,
            follows=post.outcomes.follows,
            quotes=post.outcomes.quotes,
            shares=post.outcomes.shares,
            observed_at=datetime.fromisoformat(post.observed_at.replace("Z", "+00:00")),
            observation_window_hours=post.observation_window_hours,
            data_source="synthetic",
            note=SYNTHETIC_BANNER,
        ),
        owner_id=OWNER_ID,
    )


def _row_for(post: SyntheticPost, report: ImpactReport, seed: int, bland_score: float) -> dict[str, Any]:
    outcomes = post.outcomes
    return {
        "post_id": post.post_id,
        "niche": post.niche,
        "archetype": post.archetype,
        "published_at": post.published_at,
        "observed_at": post.observed_at,
        "observation_window_hours": post.observation_window_hours,
        "text": post.text,
        "synthetic_outcomes": {
            "impressions": outcomes.impressions,
            "likes": outcomes.likes,
            "replies": outcomes.replies,
            "reposts": outcomes.reposts,
            "follows": outcomes.follows,
            "quotes": outcomes.quotes,
            "shares": outcomes.shares,
            "like_rate": round(outcomes.like_rate(), 6),
            "engagement_rate": round(outcomes.engagement_rate(), 6),
        },
        "simulator": {
            **_score_band(report),
            "inference_path": report.inference_path,
            "calibration_status": report.calibration_status,
            "data_coverage_status": report.data_coverage_status,
            "run_id": report.run_id,
        },
        "baselines": {
            "length": round(length_baseline(post.text), 4),
            "keyword_promo": round(keyword_promo_baseline(post.text), 4),
            "random": round(random_baseline(post.post_id, seed), 6),
            "bland_pack_score": round(bland_score, 4),
        },
    }


def _metric_block(rows: Sequence[dict[str, Any]], observed_key: str) -> dict[str, Any]:
    observed = [_observed_value(row, observed_key) for row in rows]
    methods = {
        "simulator_impact_score": [float(row["simulator"]["impact_score"]) for row in rows],
        "simulator_profile_impact": [float(row["simulator"]["profile_impact"]) for row in rows],
        "length": [float(row["baselines"]["length"]) for row in rows],
        "keyword_promo": [float(row["baselines"]["keyword_promo"]) for row in rows],
        "random": [float(row["baselines"]["random"]) for row in rows],
    }
    return {name: _association(predicted, observed) for name, predicted in methods.items()}


def _observed_value(row: dict[str, Any], key: str) -> float:
    outcomes = row["synthetic_outcomes"]
    return float(outcomes[key])


def summarize_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    impression_block = _metric_block(rows, "impressions")
    like_rate_block = _metric_block(rows, "like_rate")
    engagement_block = _metric_block(rows, "engagement_rate")
    simulator_imp = impression_block["simulator_impact_score"]
    return {
        "n_posts": len(rows),
        "targets": {
            "impressions": impression_block,
            "like_rate": like_rate_block,
            "engagement_rate": engagement_block,
        },
        "band_hit_rate": {
            "impact_tertiles_vs_impression_tertiles": simulator_imp["band_hit_rate"],
            "impact_tertiles_vs_like_rate_tertiles": like_rate_block["simulator_impact_score"][
                "band_hit_rate"
            ],
        },
        "simulator_vs_baselines_impressions_spearman": {
            "simulator": impression_block["simulator_impact_score"]["spearman"],
            "length": impression_block["length"]["spearman"],
            "keyword_promo": impression_block["keyword_promo"]["spearman"],
            "random": impression_block["random"]["spearman"],
            "simulator_minus_length": round(
                impression_block["simulator_impact_score"]["spearman"]
                - impression_block["length"]["spearman"],
                4,
            ),
            "simulator_minus_random": round(
                impression_block["simulator_impact_score"]["spearman"]
                - impression_block["random"]["spearman"],
                4,
            ),
        },
        "bland_post_baseline": {
            "note": (
                "The product bland-post baseline is a constant pack-level score and cannot rank posts. "
                "profile_impact is the simulator score relative to that bland baseline."
            ),
            "tech_pack_bland_score": rows[0]["baselines"]["bland_pack_score"] if rows else None,
        },
        "scorecard_fields_used": [
            "impact_score",
            "score_p10",
            "score_p50",
            "score_p90",
            "audience_fit",
            "niche_index",
            "profile_impact",
            "stability",
            "confidence",
        ],
    }


def build_report(
    *,
    rows: list[dict[str, Any]],
    seed: int,
    population: int,
    boost: int,
    monte_carlo_runs: int,
    offline: bool,
    persist: bool,
    corpus_file: Path,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "status": SYNTHETIC_STATUS,
        "gate_c_empirical": GATE_C_EMPIRICAL,
        "disclaimer": SYNTHETIC_BANNER,
        "claims": {
            "empirically_calibrated": False,
            "gate_c_complete": False,
            "public_beta": False,
            "unlocks_calibrated_or_public_beta_claims": False,
        },
        "generated_at": generated_at,
        "corpus": {
            "path": str(corpus_file.relative_to(REPO_ROOT)).replace("\\", "/"),
            "n_posts": len(rows),
            "beachhead_niche": "tech",
            "data_kind": "synthetic",
        },
        "run": {
            "seed": seed,
            "population": population,
            "boost": boost,
            "monte_carlo_runs": monte_carlo_runs,
            "inference": "heuristic-offline" if offline else "optional-groq-else-heuristic",
            "persist": persist,
            "simulator_version": SIMULATOR_VERSION,
            "calibration_version": CALIBRATION_VERSION,
            "owner_id": OWNER_ID if persist else None,
        },
        "metrics": summarize_metrics(rows),
        "posts": rows,
    }


def write_csv(report: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "post_id",
        "archetype",
        "published_at",
        "impressions",
        "likes",
        "replies",
        "reposts",
        "follows",
        "like_rate",
        "engagement_rate",
        "impact_score",
        "score_p10",
        "score_p50",
        "score_p90",
        "audience_fit",
        "niche_index",
        "profile_impact",
        "inference_path",
        "length_baseline",
        "keyword_promo_baseline",
        "random_baseline",
        "pred_impact_tertile",
        "obs_impression_tertile",
    ]
    posts = report["posts"]
    pred_bands = tertile_labels([float(row["simulator"]["impact_score"]) for row in posts])
    obs_bands = tertile_labels([float(row["synthetic_outcomes"]["impressions"]) for row in posts])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row, pred, obs in zip(posts, pred_bands, obs_bands, strict=True):
            writer.writerow(
                {
                    "post_id": row["post_id"],
                    "archetype": row["archetype"],
                    "published_at": row["published_at"],
                    "impressions": row["synthetic_outcomes"]["impressions"],
                    "likes": row["synthetic_outcomes"]["likes"],
                    "replies": row["synthetic_outcomes"]["replies"],
                    "reposts": row["synthetic_outcomes"]["reposts"],
                    "follows": row["synthetic_outcomes"]["follows"],
                    "like_rate": row["synthetic_outcomes"]["like_rate"],
                    "engagement_rate": row["synthetic_outcomes"]["engagement_rate"],
                    "impact_score": row["simulator"]["impact_score"],
                    "score_p10": row["simulator"]["score_p10"],
                    "score_p50": row["simulator"]["score_p50"],
                    "score_p90": row["simulator"]["score_p90"],
                    "audience_fit": row["simulator"]["audience_fit"],
                    "niche_index": row["simulator"]["niche_index"],
                    "profile_impact": row["simulator"]["profile_impact"],
                    "inference_path": row["simulator"]["inference_path"],
                    "length_baseline": row["baselines"]["length"],
                    "keyword_promo_baseline": row["baselines"]["keyword_promo"],
                    "random_baseline": row["baselines"]["random"],
                    "pred_impact_tertile": pred,
                    "obs_impression_tertile": obs,
                }
            )


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def write_markdown_summary(report: dict[str, Any], path: Path) -> None:
    metrics = report["metrics"]
    impressions = metrics["targets"]["impressions"]
    like_rate = metrics["targets"]["like_rate"]
    lines = [
        "# Synthetic Gate C backtest summary",
        "",
        f"> **{SYNTHETIC_BANNER}**",
        "",
        "This file is generated by `python -m app.gate_c_synthetic` (from `backend/`).",
        "Do not cite these numbers as X performance, calibration, or Gate C completion.",
        "",
        "## Run",
        "",
        f"- Status: `{report['status']}`",
        f"- Empirical Gate C: `{report['gate_c_empirical']}`",
        f"- Corpus: `{report['corpus']['path']}` ({report['corpus']['n_posts']} synthetic tech posts)",
        f"- Seed `{report['run']['seed']}`, population `{report['run']['population']}`, "
        f"boost `{report['run']['boost']}`, Monte Carlo runs `{report['run']['monte_carlo_runs']}`",
        f"- Inference: `{report['run']['inference']}`",
        f"- Simulator `{report['run']['simulator_version']}`, calibration `{report['run']['calibration_version']}`",
        f"- Generated at `{report['generated_at']}`",
        "",
        "## Rank correlation vs synthetic impressions",
        "",
        "| Method | Spearman | Kendall τ | Tertile band hit rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    order = (
        ("simulator_impact_score", "Simulator `impact_score`"),
        ("simulator_profile_impact", "Simulator `profile_impact` (vs bland pack)"),
        ("length", "Length heuristic (token count)"),
        ("keyword_promo", "Keyword / promo heuristic"),
        ("random", "Seeded random"),
    )
    for key, label in order:
        block = impressions[key]
        lines.append(
            f"| {label} | {_fmt(block['spearman'])} | {_fmt(block['kendall_tau'])} | {_fmt(block['band_hit_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## vs synthetic like-rate",
            "",
            "| Method | Spearman | Tertile band hit rate |",
            "| --- | ---: | ---: |",
            f"| Simulator `impact_score` | {_fmt(like_rate['simulator_impact_score']['spearman'])} | "
            f"{_fmt(like_rate['simulator_impact_score']['band_hit_rate'])} |",
            f"| Length | {_fmt(like_rate['length']['spearman'])} | {_fmt(like_rate['length']['band_hit_rate'])} |",
            f"| Keyword / promo | {_fmt(like_rate['keyword_promo']['spearman'])} | {_fmt(like_rate['keyword_promo']['band_hit_rate'])} |",
            f"| Random | {_fmt(like_rate['random']['spearman'])} | {_fmt(like_rate['random']['band_hit_rate'])} |",
            "",
            "## Band hit rate (existing scorecard fields)",
            "",
            f"- `impact_score` tertiles vs synthetic impression tertiles: "
            f"**{_fmt(metrics['band_hit_rate']['impact_tertiles_vs_impression_tertiles'])}**",
            f"- `impact_score` tertiles vs synthetic like-rate tertiles: "
            f"**{_fmt(metrics['band_hit_rate']['impact_tertiles_vs_like_rate_tertiles'])}**",
            "",
            "Monte Carlo `score_p10`–`score_p90` remain simulator-randomness bands on the 0–100 UI scale. "
            "They are not impression-count intervals and are not treated as calibration error bars here.",
            "",
            "## What this does not mean",
            "",
            "- Real X impressions were **not** collected. Empirical Gate C remains **blocked**.",
            "- Priors were **not** refit. `confidence` stays `0.0`.",
            "- Beating or losing to a length/promo/random baseline on this corpus is a harness check, not a product claim.",
            "- Public beta / Gate D is unchanged.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_artifacts(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "backtest_report.json"
    csv_path = out_dir / "backtest_report.csv"
    md_path = out_dir / "backtest_summary.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(report, csv_path)
    write_markdown_summary(report, md_path)
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
    }


def run_backtest(
    *,
    corpus_file: Path | None = None,
    posts: Iterable[SyntheticPost] | None = None,
    seed: int = DEFAULT_SEED,
    population: int = DEFAULT_POPULATION,
    boost: int = DEFAULT_BOOST,
    monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
    offline: bool = True,
    persist: bool = False,
    out_dir: Path | None = None,
    write: bool = True,
    require_min_posts: bool = True,
) -> dict[str, Any]:
    source = corpus_file or DEFAULT_CORPUS_PATH
    corpus = list(posts) if posts is not None else load_corpus(source)
    if require_min_posts and len(corpus) < 20:
        raise ValueError("synthetic backtest requires at least 20 posts")
    audience = load_audience("tech")
    personas = [profile.persona for profile in audience.behaviors]
    bland_score = bland_baseline(personas)
    rows: list[dict[str, Any]] = []
    with _offline_groq(offline), _monte_carlo_runs(monte_carlo_runs):
        for post in corpus:
            report = simulate_post(
                post,
                seed=seed,
                population=population,
                boost=boost,
                persist=persist,
            )
            if persist:
                _attach_outcome(report, post)
            rows.append(_row_for(post, report, seed, bland_score))
    payload = build_report(
        rows=rows,
        seed=seed,
        population=population,
        boost=boost,
        monte_carlo_runs=monte_carlo_runs,
        offline=offline,
        persist=persist,
        corpus_file=source,
    )
    if write:
        payload["artifacts"] = write_artifacts(payload, out_dir or DEFAULT_OUT_DIR)
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the synthetic Gate C backtest (harness/pipeline validation only). "
            "Default is offline/heuristic so CI needs no Groq key."
        )
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--population", type=int, default=DEFAULT_POPULATION, choices=(40, 100, 320, 500))
    parser.add_argument("--boost", type=int, default=DEFAULT_BOOST)
    parser.add_argument("--monte-carlo-runs", type=int, default=DEFAULT_MONTE_CARLO_RUNS)
    parser.add_argument(
        "--use-groq",
        action="store_true",
        help="Allow Groq if GROQ_API_KEY is set. Default stays offline/heuristic.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Save runs/outcomes to SQLite labeled data_source=synthetic. Default is off.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_backtest(
        corpus_file=args.corpus,
        seed=args.seed,
        population=args.population,
        boost=args.boost,
        monte_carlo_runs=args.monte_carlo_runs,
        offline=not args.use_groq,
        persist=args.persist,
        out_dir=args.out_dir,
        write=True,
    )
    metrics = report["metrics"]["simulator_vs_baselines_impressions_spearman"]
    sys.stdout.write(
        json.dumps(
            {
                "status": report["status"],
                "gate_c_empirical": report["gate_c_empirical"],
                "n_posts": report["corpus"]["n_posts"],
                "disclaimer": report["disclaimer"],
                "simulator_spearman_vs_impressions": metrics["simulator"],
                "artifacts": report.get("artifacts"),
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
