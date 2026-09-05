from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from app.calibration import CALIBRATION_STATUS, calibrate_reactions
from app.config import settings
from app.groq_client import (
    groq_explain,
    groq_persona_reactions,
    groq_text_content,
    groq_transcribe,
    groq_vision_content,
    heuristic_content,
)
from app.heads import HEADS_NOTE, apply_trained_heads, load_bundle, model_path
from app.media import encode_image_bytes, sample_video_frames, write_temp
from app.metrics import headline_impact_score, scorecard
from app.persona_population import load_audience, sample_population
from app.schemas import CompareDelta, CompareReport, ContentFeatures, Explanation, ImpactReport, Niche
from app.scoring import (
    CONT_DWELL_TIME_WEIGHT,
    DISCLAIMER,
    ENABLE_MULTIPLICATIVE_POST_UNEXPLORED,
    NEGATIVE_SCORES_OFFSET,
    OON_WEIGHT_FACTOR,
    POST_UNEXPLORED_IN_NETWORK_ONLY,
    WEIGHTS_NOTE,
    X_WEIGHTS,
)
from app.sim_config import (
    CALIBRATION_VERSION,
    CONFIG_VERSION,
    DEFAULT_SIM_CONFIG,
    HEADS_VERSION,
    PROMPT_VERSION,
    PROBABILITY_SEMANTICS,
    RANKING_POLICY_VERSION,
    SIMULATOR_VERSION,
    SimulationConfig,
    WEIGHTS_SOURCE_URL,
    WEIGHTS_TREE,
)
from app.simulation import heuristic_reactions, simulate
from app.store import load_report, save_report, snapshot_hash_for

ALLOWED_POP = (40, 100, 320, 500)


@dataclass(frozen=True)
class PreparedMedia:
    image_urls: tuple[str, ...]
    transcript: str
    note: str


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _weights_hash() -> str:
    return _canonical_hash(
        {
            "weights": X_WEIGHTS,
            "continuous_dwell_time_weight": CONT_DWELL_TIME_WEIGHT,
            "oon_weight_factor": OON_WEIGHT_FACTOR,
            "negative_scores_offset": NEGATIVE_SCORES_OFFSET,
            "post_unexplored_in_network_only": POST_UNEXPLORED_IN_NETWORK_ONLY,
            "enable_multiplicative_post_unexplored": ENABLE_MULTIPLICATIVE_POST_UNEXPLORED,
        }
    )


def _input_hash(
    niche: Niche,
    text: str,
    image_blobs: list[tuple[bytes, str]],
    video: tuple[bytes, str] | None,
) -> str:
    manifest = {
        "niche": niche,
        "text": text,
        "images": [
            {"mime": mime, "sha256": hashlib.sha256(blob).hexdigest()}
            for blob, mime in image_blobs
        ],
        "video": (
            {"suffix": video[1], "sha256": hashlib.sha256(video[0]).hexdigest()}
            if video is not None
            else None
        ),
    }
    return _canonical_hash(manifest)


def _config_snapshot(population: int, boost: int, seed: int) -> dict[str, Any]:
    return {
        "simulation": DEFAULT_SIM_CONFIG.as_dict(),
        "monte_carlo_runs": settings.sim_monte_carlo_runs,
        "max_rounds": settings.sim_max_rounds,
        "population": population,
        "boost": boost,
        "seed": seed,
        "ranking_policy_version": RANKING_POLICY_VERSION,
    }


def _config_from_snapshot(snapshot: dict[str, Any]) -> SimulationConfig:
    raw = snapshot.get("simulation") if isinstance(snapshot, dict) else None
    if not isinstance(raw, dict):
        return DEFAULT_SIM_CONFIG
    allowed = {field.name for field in fields(SimulationConfig)}
    values = {key: value for key, value in raw.items() if key in allowed}
    return SimulationConfig(**values)


def _media_note(n_images: int, has_video: bool, transcribed: bool) -> str:
    if has_video:
        extra = " Transcript included." if transcribed else " No transcript (missing Groq key or Whisper failed)."
        return (
            "Video treated as 5 sampled frames + transcript, not a full watch."
            + extra
        )
    if n_images:
        return f"Image analysis of {n_images} image(s), max 5."
    return "Text-only analysis."


def prepare_media(
    image_blobs: list[tuple[bytes, str]],
    video: tuple[bytes, str] | None,
) -> PreparedMedia:
    image_urls = [encode_image_bytes(data, mime) for data, mime in image_blobs[:5]]
    transcript = ""
    has_video = video is not None
    if video:
        video_bytes, suffix = video
        frames = sample_video_frames(video_bytes, count=5)
        image_urls = (image_urls + frames)[:5]
        if settings.groq_enabled:
            path = write_temp(video_bytes, suffix or ".mp4")
            try:
                transcript = groq_transcribe(path)
            except Exception:
                transcript = ""
            finally:
                Path(path).unlink(missing_ok=True)
    return PreparedMedia(
        image_urls=tuple(image_urls),
        transcript=transcript,
        note=_media_note(len(image_urls), has_video, bool(transcript)),
    )


def extract_content(
    text: str,
    image_blobs: list[tuple[bytes, str]],
    video: tuple[bytes, str] | None,
    prepared_media: PreparedMedia | None = None,
) -> ContentFeatures:
    prepared = prepared_media or prepare_media(image_blobs, video)
    image_urls = list(prepared.image_urls)
    transcript = prepared.transcript
    combined = "\n\n".join(part for part in (text.strip(), transcript) if part)
    note = prepared.note
    if not combined and not image_urls:
        combined = "(empty post)"
    if image_urls:
        features = groq_vision_content(combined, image_urls, note)
        if features:
            if transcript:
                features.transcript_excerpt = transcript[:500]
            return features
    features = groq_text_content(combined, note)
    if features:
        return features
    return heuristic_content(combined, note)


def template_explanation(score: float, reactions: list) -> Explanation:
    top = sorted(reactions, key=lambda r: r.like_probability, reverse=True)[:2]
    low = sorted(reactions, key=lambda r: r.negative_feedback_probability, reverse=True)[:1]
    names = ", ".join(r.persona_id.replace("_", " ") for r in top) or "the pack"
    return Explanation(
        headline=f"Prior-mapped comparative score {score:.0f} / 100",
        summary=(
            f"Python scored synthetic per-impression action probabilities with public RankingScorer defaults. "
            f"Stronger fit: {names}. "
            + (f"Watch {low[0].persona_id}: higher negative risk." if low else "")
        ),
        suggestions=[
            "Rewrite the first line as a concrete result, not a topic.",
            "Cut promotional phrasing before asking this audience to repost.",
            "Run the same draft against a second niche pack and compare ranges.",
        ],
        source="heuristic",
    )


def run_pipeline(
    niche: Niche,
    text: str,
    image_blobs: list[tuple[bytes, str]],
    video: tuple[bytes, str] | None,
    seed: int | None = None,
    population: int = 100,
    boost: int = 6,
    persist: bool = True,
    owner_id: str = "development",
    _prepared_media: PreparedMedia | None = None,
) -> ImpactReport:
    used_seed = settings.sim_seed if seed is None else seed
    n_pop = population if population in ALLOWED_POP else 100
    n_boost = max(1, min(12, boost))
    audience = load_audience(niche)
    personas = [profile.persona for profile in audience.behaviors]
    members = sample_population(audience, n_pop, seed=used_seed)
    content = extract_content(text, image_blobs, video, _prepared_media)
    llm_reactions = groq_persona_reactions(personas, content)
    if llm_reactions:
        reactions = llm_reactions
        inference_path = "groq"
    else:
        reactions = heuristic_reactions(personas, content.model_dump())
        inference_path = "heuristic"
    head_text = " ".join(
        part for part in (text.strip(), content.transcript_excerpt, " ".join(content.topics)) if part
    )
    reactions, heads_used = apply_trained_heads(reactions, head_text)
    affinities = reactions
    reactions = calibrate_reactions(affinities)
    simulation = simulate(
        reactions,
        seed=used_seed,
        users_per_persona=max(1, n_pop // max(1, len(reactions))),
        runs=settings.sim_monte_carlo_runs,
        max_rounds=settings.sim_max_rounds,
        personas=personas,
        population=n_pop,
        boost=n_boost,
        target_text=text,
        topics=list(content.topics),
        config=DEFAULT_SIM_CONFIG,
        population_members=members,
    )
    impact = headline_impact_score(reactions, simulation)
    card = scorecard(
        reactions,
        personas,
        content,
        simulation,
        impact_score=impact,
        max_rounds=settings.sim_max_rounds,
    )
    slim = {
        "niche": niche,
        "impact_score": impact,
        "score_range": [simulation.score_p10, simulation.score_p50, simulation.score_p90],
        "content": content.model_dump(),
        "reactions": [r.model_dump() for r in reactions],
        "rounds": [r.model_dump() for r in simulation.rounds],
        "inference_path": inference_path,
        "calibration_status": CALIBRATION_STATUS,
        "probability_semantics": PROBABILITY_SEMANTICS,
    }
    explanation = groq_explain(slim) or template_explanation(impact, reactions)
    heads_note = HEADS_NOTE if heads_used else "No valid trained-head artifact was applied; deterministic persona estimates remain active."
    last_stop = str(card["stop_reason"])
    bundle = load_bundle() if heads_used else None
    training = bundle.get("training", {}) if isinstance(bundle, dict) else {}
    dataset_metadata = training.get("dataset", {}) if isinstance(training, dict) else {}
    if not isinstance(dataset_metadata, dict):
        dataset_metadata = {}
    artifact_hash = _file_hash(model_path()) if heads_used else ""
    fallback_reasons: list[str] = []
    if content.source != "groq":
        fallback_reasons.append("Content features used the deterministic extractor because Groq was unavailable or failed.")
    if inference_path != "groq":
        fallback_reasons.append("Persona action affinities used the deterministic model because the LLM response was unavailable or invalid.")
    if not heads_used:
        fallback_reasons.append("No compatible BluePrint trained-head artifact was available for this input.")
    if video is not None and "No transcript" in content.media_note:
        fallback_reasons.append("Video audio transcription was unavailable; five sampled frames were used.")
    config_snapshot = _config_snapshot(n_pop, n_boost, used_seed)
    input_digest = _input_hash(niche, text, image_blobs, video)
    weight_digest = _weights_hash()
    action_version_parts = [
        (
            f"groq:{settings.groq_text_model}:{PROMPT_VERSION}"
            if inference_path == "groq"
            else "heuristic-reactions-v2"
        )
    ]
    if heads_used:
        action_version_parts.append(HEADS_VERSION)
    action_version = "+".join(action_version_parts)
    provenance = {
        "content_source": content.source,
        "reaction_source": inference_path,
        "persona_population_version": audience.version,
        "persona_population_hash": audience.source_hash,
        "persona_overlay_rejections": len(audience.rejections),
        "persona_overlay_rejection_reasons": sorted({item.reason for item in audience.rejections}),
        "ranking_policy_version": RANKING_POLICY_VERSION,
        "weight_source": WEIGHTS_SOURCE_URL,
        "weight_defaults_version": WEIGHTS_TREE,
        "population_seed": used_seed,
    }
    report = ImpactReport(
        experimental=True,
        disclaimer=DISCLAIMER,
        niche=niche,
        groq_used=(content.source == "groq" or inference_path == "groq" or explanation.source == "groq"),
        content=content,
        reactions=reactions,
        simulation=simulation,
        impact_score=impact,
        explanation=explanation,
        weights_note=WEIGHTS_NOTE,
        heads_used=heads_used,
        heads_note=heads_note,
        audience_fit=float(card["audience_fit"]),
        niche_index=float(card["niche_index"]),
        negative_signal_risk=float(card["negative_signal_risk"]),
        stability=float(card["stability"]),
        confidence=0.0,
        reach_pct=float(card["reach_pct"]),
        inference_path=f"{inference_path}{'+heads' if heads_used else ''}+prior-map",
        simulator_version=SIMULATOR_VERSION,
        calibration_version=CALIBRATION_VERSION,
        config_version=CONFIG_VERSION,
        prompt_version=PROMPT_VERSION,
        input_text=text,
        population=n_pop,
        boost=n_boost,
        llm_model=(
            settings.groq_text_model
            if content.source == "groq" or inference_path == "groq" or explanation.source == "groq"
            else ""
        ),
        affinity_reactions=affinities,
        distribution_potential=float(card["distribution_potential"]),
        engagement_quality=float(card["engagement_quality"]),
        profile_impact=float(card["profile_impact"]),
        stop_reason=last_stop,
        probability_semantics=PROBABILITY_SEMANTICS,
        calibration_status=CALIBRATION_STATUS,
        data_coverage_status="synthetic-personas; no observed X outcome calibration",
        uncertainty_note=(
            "The p10-p90 bands measure simulator randomness only. They exclude model error, "
            "distribution shift, X runtime experiments, and uncertainty in the assumed base rates."
        ),
        fallback_reasons=fallback_reasons,
        config_snapshot=config_snapshot,
        provenance=provenance,
        persona_pack_version=audience.version,
        persona_pack_hash=audience.source_hash,
        dataset_revision=str(dataset_metadata.get("revision") or dataset_metadata.get("config") or ""),
        dataset_hash=str(dataset_metadata.get("sha256") or ""),
        action_model_version=action_version,
        action_model_hash=artifact_hash,
        weights_version=WEIGHTS_TREE,
        weights_hash=weight_digest,
        input_hash=input_digest,
        replayable=True,
        replay_limitations=[
            "Exact replay requires the recorded simulator version and unchanged persona/weight hashes.",
            "Replay reuses stored action probabilities and does not repeat external LLM inference.",
        ],
    )
    report = report.model_copy(update={"snapshot_hash": snapshot_hash_for(report, owner_id)})
    if persist:
        run_id = save_report(report, owner_id=owner_id)
        report = load_report(run_id) or report.model_copy(update={"run_id": run_id})
    return report


def compare_hooks(
    niche: Niche,
    text_a: str,
    text_b: str,
    image_blobs: list[tuple[bytes, str]],
    video: tuple[bytes, str] | None,
    seed: int | None = None,
    population: int = 100,
    boost: int = 6,
    owner_id: str = "development",
) -> CompareReport:
    prepared_media = prepare_media(image_blobs, video)
    a = run_pipeline(
        niche,
        text_a,
        image_blobs,
        video,
        seed=seed,
        population=population,
        boost=boost,
        owner_id=owner_id,
        _prepared_media=prepared_media,
    )
    b = run_pipeline(
        niche,
        text_b,
        image_blobs,
        video,
        seed=a.simulation.seed,
        population=population,
        boost=boost,
        owner_id=owner_id,
        _prepared_media=prepared_media,
    )
    return CompareReport(
        a=a,
        b=b,
        delta=CompareDelta(
            impact_score=round(b.impact_score - a.impact_score, 1),
            niche_index=round(b.niche_index - a.niche_index, 1),
            audience_fit=round(b.audience_fit - a.audience_fit, 1),
            reach_pct=round(b.reach_pct - a.reach_pct, 1),
            confidence=round(b.confidence - a.confidence, 1),
            distribution_potential=round(b.distribution_potential - a.distribution_potential, 1),
            engagement_quality=round(b.engagement_quality - a.engagement_quality, 1),
            profile_impact=round(b.profile_impact - a.profile_impact, 1),
        ),
    )


def replay_report(
    source: ImpactReport,
    seed: int | None = None,
    persist: bool = True,
    owner_id: str = "development",
) -> ImpactReport:
    affinities = source.affinity_reactions
    if not affinities:
        raise ValueError("Run has no stored affinities")
    audience = load_audience(source.niche)
    current_weights_hash = _weights_hash()
    if source.persona_pack_hash and source.persona_pack_hash != audience.source_hash:
        raise ValueError("Persona population changed since this run; exact replay is unavailable")
    if source.weights_hash and source.weights_hash != current_weights_hash:
        raise ValueError("Scoring weights changed since this run; exact replay is unavailable")
    if source.simulator_version and source.simulator_version != SIMULATOR_VERSION:
        raise ValueError("Simulator version changed since this run; exact replay is unavailable")

    personas = [profile.persona for profile in audience.behaviors]
    # New reports persist the exact per-action probabilities. Older reports fall
    # back to the recorded affinities and current prior map, and are labelled so.
    exact_probabilities = bool(source.replayable and source.reactions and source.config_snapshot)
    reactions = source.reactions if exact_probabilities else calibrate_reactions(affinities)
    used_seed = source.simulation.seed if seed is None else seed
    is_seed_variant = used_seed != source.simulation.seed
    n_pop = source.population if source.population in ALLOWED_POP else 100
    n_boost = max(1, min(12, source.boost or 6))
    members = sample_population(audience, n_pop, seed=used_seed)
    cfg = _config_from_snapshot(source.config_snapshot)
    runs = max(
        1,
        min(
            500,
            int(source.config_snapshot.get("monte_carlo_runs", source.simulation.runs or settings.sim_monte_carlo_runs)),
        ),
    )
    max_rounds = max(1, min(20, int(source.config_snapshot.get("max_rounds", settings.sim_max_rounds))))
    config_snapshot = dict(source.config_snapshot) if source.config_snapshot else _config_snapshot(n_pop, n_boost, used_seed)
    config_snapshot.update(
        {
            "simulation": cfg.as_dict(),
            "monte_carlo_runs": runs,
            "max_rounds": max_rounds,
            "population": n_pop,
            "boost": n_boost,
            "seed": used_seed,
        }
    )
    replay_mode = (
        "legacy-approximate"
        if not exact_probabilities
        else "seed-variant"
        if is_seed_variant
        else "exact"
    )
    replay_limitations = (
        ["Legacy run lacked a complete configuration/probability snapshot; replay is approximate."]
        if not exact_probabilities
        else [
            *source.replay_limitations,
            "This is a deterministic seed variant of the parent run, not an exact reproduction of it.",
        ]
        if is_seed_variant
        else source.replay_limitations
    )
    simulation = simulate(
        reactions,
        seed=used_seed,
        users_per_persona=max(1, n_pop // max(1, len(reactions))),
        runs=runs,
        max_rounds=max_rounds,
        personas=personas,
        population=n_pop,
        boost=n_boost,
        target_text=source.input_text,
        topics=list(source.content.topics),
        config=cfg,
        population_members=members,
    )
    impact = headline_impact_score(reactions, simulation)
    card = scorecard(
        reactions,
        personas,
        source.content,
        simulation,
        impact_score=impact,
        max_rounds=max_rounds,
    )
    report = source.model_copy(
        update={
            "run_id": None,
            "parent_run_id": source.run_id,
            "reactions": reactions,
            "simulation": simulation,
            "impact_score": impact,
            "audience_fit": float(card["audience_fit"]),
            "niche_index": float(card["niche_index"]),
            "negative_signal_risk": float(card["negative_signal_risk"]),
            "stability": float(card["stability"]),
            "confidence": 0.0,
            "reach_pct": float(card["reach_pct"]),
            "distribution_potential": float(card["distribution_potential"]),
            "engagement_quality": float(card["engagement_quality"]),
            "profile_impact": float(card["profile_impact"]),
            "stop_reason": str(card["stop_reason"]),
            "groq_used": False,
            "inference_path": "replay+stored-probabilities" if exact_probabilities else "replay+prior-map",
            "llm_model": source.llm_model,
            "affinity_reactions": affinities,
            "weights_hash": current_weights_hash,
            "persona_pack_hash": audience.source_hash,
            "persona_pack_version": audience.version,
            "config_snapshot": config_snapshot,
            "replay_mode": replay_mode,
            "replayable": exact_probabilities,
            "replay_limitations": replay_limitations,
            "fallback_reasons": [
                *source.fallback_reasons,
                "Replay reused stored action probabilities; external models were not called.",
            ],
            "provenance": {
                **source.provenance,
                "replay_parent_run_id": source.run_id,
                "replay_seed": used_seed,
                "replay_mode": replay_mode,
                "replay_exact_parent_match": replay_mode == "exact",
                "replay_probability_source": "stored" if exact_probabilities else "legacy-prior-map",
            },
        }
    )
    report = report.model_copy(update={"snapshot_hash": snapshot_hash_for(report, owner_id)})
    if persist:
        run_id = save_report(report, owner_id=owner_id)
        report = load_report(run_id) or report.model_copy(update={"run_id": run_id})
    return report
