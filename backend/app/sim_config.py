from __future__ import annotations

from dataclasses import dataclass, asdict

SIMULATOR_VERSION = "0.2.0"
CALIBRATION_VERSION = "impression-priors-v1"
CONFIG_VERSION = "sim-config-v1"
PROMPT_VERSION = "persona-reactions-v2"
HEADS_VERSION = "blueprint-tfidf-favorite-retweet-v1"
WEIGHTS_TREE = "7ba776848b12d8422eb0f291ee03ea5c17ab0188"


@dataclass(frozen=True)
class SimulationConfig:
    version: str = CONFIG_VERSION
    max_population: int = 320
    min_population: int = 8
    share_fanout_min: int = 1
    share_fanout_max: int = 3
    out_of_target_seed_frac: float = 0.35
    share_target_preference: float = 0.45
    algo_target_preference: float = 0.25
    algo_exposure_rate: float = 0.08
    algo_quality_floor: float = 42.0
    velocity_stop_threshold: float = 0.10
    velocity_stop_min_round: int = 3
    jitter_sigma: float = 0.05
    dwell_jitter_sigma: float = 0.4
    action_noise_sigma: float = 0.25
    affinity_overlap_weight: float = 0.35
    affinity_llm_weight: float = 0.65
    oon_action_scale: float = 0.75
    min_ignore_mass: float = 0.05
    target_fit_cutoff_percentile: float = 40.0

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_SIM_CONFIG = SimulationConfig()
