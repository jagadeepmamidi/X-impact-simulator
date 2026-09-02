from __future__ import annotations

from app.schemas import ContentFeatures, Persona, PersonaReaction, SimulationSummary
from app.scoring import clamp01


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _is_control(persona: Persona) -> bool:
    blob = f"{persona.role} {persona.name}".lower()
    return any(tag in blob for tag in ("adjacent", "control", "unrelated"))


def scorecard(
    reactions: list[PersonaReaction],
    personas: list[Persona],
    content: ContentFeatures,
    simulation: SimulationSummary,
) -> dict[str, float]:
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
    return {
        "audience_fit": round(audience_fit, 1),
        "niche_index": round(niche_index, 1),
        "negative_signal_risk": round(negative_signal_risk, 1),
        "stability": round(stability, 1),
        "confidence": round(stability, 1),
        "reach_pct": round(reach_pct, 1),
    }
