from __future__ import annotations

from app.calibration import calibrate_reactions
from app.schemas import ContentFeatures, Persona, PersonaReaction, SimulationSummary
from app.scoring import audience_score, clamp01
from app.simulation import heuristic_reactions

_BLAND = {
    "topics": ["update"],
    "hook_strength": 0.4,
    "clarity": 0.5,
    "novelty": 0.4,
    "promotional_intensity": 0.2,
    "controversy": 0.1,
    "visual_hook": 0.0,
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _is_control(persona: Persona) -> bool:
    blob = f"{persona.role} {persona.name}".lower()
    return any(tag in blob for tag in ("adjacent", "control", "unrelated"))


def bland_baseline(personas: list[Persona]) -> float:
    return audience_score(calibrate_reactions(heuristic_reactions(personas, _BLAND)))


def scorecard(
    reactions: list[PersonaReaction],
    personas: list[Persona],
    content: ContentFeatures,
    simulation: SimulationSummary,
    impact_score: float | None = None,
    max_rounds: int = 6,
) -> dict[str, float | str]:
    by_id = {p.id: p for p in personas}
    affinities = [r.topic_affinity for r in reactions]
    audience_fit = _mean(affinities) * 100.0
    core = [
        r.topic_affinity
        for r in reactions
        if not _is_control(by_id.get(r.persona_id) or personas[0])
    ]
    niche_raw = _mean(core or affinities)
    niche_index = clamp01(niche_raw * (1.0 - 0.35 * content.promotional_intensity)) * 100.0
    negative_signal_risk = _mean([r.negative_feedback_probability for r in reactions]) * 100.0
    spread = max(0.0, simulation.score_p90 - simulation.score_p10)
    stability = clamp01(1.0 - spread / 45.0) * 100.0
    people = [a for a in simulation.graph.agents if a.cohort != "origin"]
    shown = [a for a in people if a.cohort != "never_shown"]
    reach_pct = (len(shown) / len(people) * 100.0) if people else 0.0
    quality_n = sum(1 for a in shown if a.action in {"reply", "repost", "quote", "share", "follow"})
    engagement_quality = (quality_n / len(shown) * 100.0) if shown else 0.0
    distribution_potential = clamp01((simulation.reached_round_p50 - 1.0) / max(1, max_rounds - 1)) * 100.0
    impact = float(impact_score if impact_score is not None else simulation.score_p50)
    baseline = bland_baseline(personas)
    profile_impact = clamp01(0.5 + (impact - baseline) / 50.0) * 100.0
    last = simulation.rounds[-1] if simulation.rounds else None
    stop_reason = (last.stop_reason if last and last.stop_reason else None) or (
        "ran to cap" if last and not last.stopped else ""
    )
    return {
        "audience_fit": round(audience_fit, 1),
        "niche_index": round(niche_index, 1),
        "negative_signal_risk": round(negative_signal_risk, 1),
        "stability": round(stability, 1),
        "confidence": round(stability, 1),
        "reach_pct": round(reach_pct, 1),
        "distribution_potential": round(distribution_potential, 1),
        "engagement_quality": round(engagement_quality, 1),
        "profile_impact": round(profile_impact, 1),
        "stop_reason": stop_reason or "ran to cap",
    }
