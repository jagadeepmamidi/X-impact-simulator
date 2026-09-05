from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.schemas import PersonaReaction
from app.scoring import audience_score
from app.sim_config import DEFAULT_SIM_CONFIG, RANKING_POLICY_VERSION, SimulationConfig


@dataclass(frozen=True)
class RankingDecision:
    """Result of ranking the target post against one synthetic candidate slate."""

    policy_version: str
    target_score: float
    rank: int
    slate_size: int
    selected: bool


def _stage_adjustment(stage: str, config: SimulationConfig) -> float:
    if stage == "adjacent":
        return config.adjacent_score_adjustment
    if stage == "general":
        return config.general_score_adjustment
    return config.niche_score_adjustment


def rank_target(
    reaction: PersonaReaction,
    rng: np.random.Generator,
    *,
    in_network: bool,
    stage: str,
    config: SimulationConfig | None = None,
) -> RankingDecision:
    """Rank one target post for one viewer against an explicit synthetic slate.

    The competitor distribution is a versioned scenario assumption. It is not a
    claim about X production traffic and can be replaced by observed slates later.
    """

    config = config or DEFAULT_SIM_CONFIG
    slate_size = max(1, int(config.candidate_pool_size))
    target_score = float(audience_score([reaction], in_network=in_network))
    target_score = min(100.0, max(0.0, target_score + _stage_adjustment(stage, config)))
    if slate_size == 1:
        return RankingDecision(
            policy_version=RANKING_POLICY_VERSION,
            target_score=round(target_score, 3),
            rank=1,
            slate_size=1,
            selected=True,
        )

    if in_network:
        alpha = config.competitor_alpha_in_network
        beta = config.competitor_beta_in_network
        top_k = config.candidate_top_k_in_network
    else:
        alpha = config.competitor_alpha_out_of_network
        beta = config.competitor_beta_out_of_network
        top_k = config.candidate_top_k_out_of_network
    competitors = rng.beta(max(alpha, 1e-6), max(beta, 1e-6), size=slate_size - 1) * 100.0
    rank = 1 + int(np.count_nonzero(competitors > target_score))
    selected = rank <= max(1, min(int(top_k), slate_size))
    return RankingDecision(
        policy_version=RANKING_POLICY_VERSION,
        target_score=round(target_score, 3),
        rank=rank,
        slate_size=slate_size,
        selected=selected,
    )
