from __future__ import annotations

from pathlib import Path

from app.calibration import calibrate_reactions
from app.config import settings
from app.groq_client import (
    groq_explain,
    groq_persona_reactions,
    groq_text_content,
    groq_transcribe,
    groq_vision_content,
    heuristic_content,
)
from app.heads import HEADS_NOTE, apply_trained_heads
from app.media import encode_image_bytes, sample_video_frames, write_temp
from app.metrics import scorecard
from app.schemas import CompareDelta, CompareReport, ContentFeatures, Explanation, ImpactReport, Niche
from app.scoring import DISCLAIMER, WEIGHTS_NOTE, audience_score
from app.sim_config import (
    CALIBRATION_VERSION,
    CONFIG_VERSION,
    PROMPT_VERSION,
    SIMULATOR_VERSION,
)
from app.simulation import heuristic_reactions, load_overlays, load_pack, simulate
from app.store import save_report

ALLOWED_POP = (40, 100, 320, 500)


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


def extract_content(
    text: str,
    image_blobs: list[tuple[bytes, str]],
    video: tuple[bytes, str] | None,
) -> ContentFeatures:
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
    combined = "\n\n".join(part for part in (text.strip(), transcript) if part)
    note = _media_note(len(image_urls), has_video, bool(transcript))
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
        headline=f"Uncalibrated comparative score {score:.0f} / 100",
        summary=(
            f"Python scored predicted Phoenix P(action) with public RankingScorer weights. "
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
) -> ImpactReport:
    personas = load_pack(niche)
    overlays = load_overlays(niche)
    content = extract_content(text, image_blobs, video)
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
    used_seed = settings.sim_seed if seed is None else seed
    n_pop = population if population in ALLOWED_POP else 100
    n_boost = max(1, min(12, boost))
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
        overlays=overlays,
        sample_reactions=affinities,
    )
    impact = audience_score(reactions)
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
        "calibrated": True,
    }
    explanation = groq_explain(slim) or template_explanation(impact, reactions)
    heads_note = HEADS_NOTE if heads_used else "No trained heads applied."
    last_stop = str(card["stop_reason"])
    report = ImpactReport(
        experimental=True,
        disclaimer=DISCLAIMER,
        niche=niche,
        groq_used=inference_path == "groq",
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
        confidence=float(card["stability"]),
        reach_pct=float(card["reach_pct"]),
        inference_path=f"{inference_path}{'+heads' if heads_used else ''}+calibrated",
        simulator_version=SIMULATOR_VERSION,
        calibration_version=CALIBRATION_VERSION,
        config_version=CONFIG_VERSION,
        prompt_version=PROMPT_VERSION,
        input_text=text,
        population=n_pop,
        boost=n_boost,
        llm_model=settings.groq_text_model if inference_path == "groq" else "",
        affinity_reactions=affinities,
        distribution_potential=float(card["distribution_potential"]),
        engagement_quality=float(card["engagement_quality"]),
        profile_impact=float(card["profile_impact"]),
        stop_reason=last_stop,
    )
    if persist:
        report = report.model_copy(update={"run_id": save_report(report)})
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
) -> CompareReport:
    a = run_pipeline(niche, text_a, image_blobs, video, seed=seed, population=population, boost=boost)
    b = run_pipeline(
        niche,
        text_b,
        image_blobs,
        video,
        seed=a.simulation.seed,
        population=population,
        boost=boost,
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


def replay_report(source: ImpactReport, seed: int | None = None, persist: bool = True) -> ImpactReport:
    affinities = source.affinity_reactions
    if not affinities:
        raise ValueError("Run has no stored affinities")
    personas = load_pack(source.niche)
    overlays = load_overlays(source.niche)
    reactions = calibrate_reactions(affinities)
    used_seed = source.simulation.seed if seed is None else seed
    n_pop = source.population if source.population in ALLOWED_POP else 100
    n_boost = max(1, min(12, source.boost or 6))
    simulation = simulate(
        reactions,
        seed=used_seed,
        users_per_persona=max(1, n_pop // max(1, len(reactions))),
        runs=settings.sim_monte_carlo_runs,
        max_rounds=settings.sim_max_rounds,
        personas=personas,
        population=n_pop,
        boost=n_boost,
        target_text=source.input_text,
        topics=list(source.content.topics),
        overlays=overlays,
        sample_reactions=affinities,
    )
    impact = audience_score(reactions)
    card = scorecard(
        reactions,
        personas,
        source.content,
        simulation,
        impact_score=impact,
        max_rounds=settings.sim_max_rounds,
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
            "confidence": float(card["stability"]),
            "reach_pct": float(card["reach_pct"]),
            "distribution_potential": float(card["distribution_potential"]),
            "engagement_quality": float(card["engagement_quality"]),
            "profile_impact": float(card["profile_impact"]),
            "stop_reason": str(card["stop_reason"]),
            "groq_used": False,
            "inference_path": "replay+calibrated",
            "llm_model": source.llm_model,
            "affinity_reactions": affinities,
        }
    )
    if persist:
        report = report.model_copy(update={"run_id": save_report(report)})
    return report
