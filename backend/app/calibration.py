from __future__ import annotations

import math

from app.schemas import PersonaReaction
from app.sim_config import CALIBRATION_VERSION

CALIBRATION_NOTE = f"{CALIBRATION_VERSION}: affinities mapped to impression-level priors."

IMPRESSION_PRIORS: dict[str, float] = {
    "like_probability": 0.020,
    "reply_probability": 0.0030,
    "repost_probability": 0.0040,
    "quote_probability": 0.0015,
    "share_probability": 0.0020,
    "share_via_dm_probability": 0.0006,
    "share_via_copy_link_probability": 0.00015,
    "dwell_probability": 0.40,
    "click_probability": 0.060,
    "photo_expand_probability": 0.030,
    "video_open_probability": 0.040,
    "open_link_probability": 0.010,
    "quoted_click_probability": 0.0008,
    "follow_probability": 0.0012,
    "post_unexplored_probability": 0.030,
    "not_interested_probability": 0.0008,
    "mute_probability": 0.00008,
    "block_probability": 0.000025,
    "report_probability": 0.000004,
    "not_dwelled_probability": 0.20,
    "negative_feedback_probability": 0.0012,
}

AFFINITY_LOGIT_SCALE = 2.2
TYPICAL_DWELL_SECONDS = 8.0
UI_SCORE_MIDPOINT = 0.08
UI_SCORE_SCALE = 0.07


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-9), 1.0 - 1e-9)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def calibrate_probability(affinity: float, base_rate: float, scale: float = AFFINITY_LOGIT_SCALE) -> float:
    if affinity <= 1e-9:
        return 0.0
    return _sigmoid(_logit(base_rate) + scale * (2.0 * float(affinity) - 1.0))


def to_ui_score(raw: float) -> float:
    mapped = 100.0 * _sigmoid((float(raw) - UI_SCORE_MIDPOINT) / UI_SCORE_SCALE)
    return round(min(100.0, max(0.0, mapped)), 1)


def calibrate_reaction(reaction: PersonaReaction) -> PersonaReaction:
    update: dict[str, float] = {}
    for field, prior in IMPRESSION_PRIORS.items():
        update[field] = round(calibrate_probability(float(getattr(reaction, field)), prior), 6)
    dwell = update["dwell_probability"]
    update["dwell_time"] = round(dwell / max(IMPRESSION_PRIORS["dwell_probability"], 1e-9) * TYPICAL_DWELL_SECONDS, 3)
    return reaction.model_copy(update=update)


def calibrate_reactions(reactions: list[PersonaReaction]) -> list[PersonaReaction]:
    return [calibrate_reaction(r) for r in reactions]
