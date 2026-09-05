from __future__ import annotations

from dataclasses import dataclass, asdict

SIMULATOR_VERSION = "0.5.0"
CALIBRATION_VERSION = "affinity-prior-map-v2"
CONFIG_VERSION = "sim-config-v4"
PROMPT_VERSION = "persona-reactions-v2"
HEADS_VERSION = "blueprint-tfidf-cluster-aware-favorite-retweet-v2"
WEIGHTS_TREE = "x-algorithm-main-param-defaults-sync-2026-08-12"
WEIGHTS_SOURCE_URL = "https://github.com/xai-org/x-algorithm/blob/main/home-mixer/params/param.rs"
RANKING_POLICY_VERSION = "candidate-slate-v2"
PROBABILITY_SEMANTICS = "conditional-on-impression multilabel action probabilities"


@dataclass(frozen=True)
class SimulationConfig:
    version: str = CONFIG_VERSION
    max_population: int = 500
    min_population: int = 8
    share_fanout_min: int = 1
    share_fanout_max: int = 3
    out_of_target_seed_frac: float = 0.35
    share_target_preference: float = 0.45
    algo_target_preference: float = 0.25
    in_network_target_rate: float = 0.55
    in_network_out_of_target_rate: float = 0.12
    adjacent_in_pref: float = 0.25
    niche_in_pref: float = 0.70
    general_in_pref: float = 0.40
    algo_exposure_rate: float = 0.08
    candidate_pool_size: int = 12
    candidate_top_k_in_network: int = 6
    candidate_top_k_out_of_network: int = 4
    competitor_alpha_in_network: float = 1.6
    competitor_beta_in_network: float = 2.2
    competitor_alpha_out_of_network: float = 2.2
    competitor_beta_out_of_network: float = 1.8
    adjacent_score_adjustment: float = 2.0
    niche_score_adjustment: float = 0.0
    general_score_adjustment: float = -4.0
    velocity_stop_threshold: float = 0.10
    velocity_stop_min_round: int = 3
    negative_stop_rate: float = 0.18
    jitter_sigma: float = 0.05
    dwell_jitter_sigma: float = 0.4
    action_noise_sigma: float = 0.25
    affinity_overlap_weight: float = 0.35
    affinity_llm_weight: float = 0.65
    target_fit_cutoff_percentile: float = 40.0

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_SIM_CONFIG = SimulationConfig()
