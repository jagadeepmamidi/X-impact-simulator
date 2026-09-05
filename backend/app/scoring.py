"""RankingScorer weighted mode from xai-org/x-algorithm."""

from app.calibration import CALIBRATION_NOTE, to_ui_score as calibrated_ui_score
from app.schemas import PersonaReaction

# Public default values in param.rs, whose upstream comment says its feature-switch
# mirror was last synced 2026-08-12. Runtime experiment overrides are not public.
X_WEIGHTS = {
    "favorite": 0.5,
    "reply": 5.0,
    "retweet": 1.0,
    "photo_expand": 0.05,
    "video_open": 0.05,
    "click": 0.4,
    "open_link": 0.2,
    "profile_click": 0.0,
    "vqv": 0.05,
    "share": 2.0,
    "share_via_dm": 5.0,
    "share_via_copy_link": 20.0,
    "dwell": 0.0,
    "quote": 5.0,
    "quoted_click": 0.05,
    "quoted_vqv": 0.0,
    "follow_author": 4.0,
    "post_unexplored": 0.02,
    "not_interested": -43.2,
    "block_author": -31.2,
    "mute_author": -58.8,
    "report": -234.0,
    "not_dwelled": -0.02,
}

CONT_DWELL_TIME_WEIGHT = 0.004
OON_WEIGHT_FACTOR = 0.75
NEGATIVE_SCORES_OFFSET = 0.001
POST_UNEXPLORED_IN_NETWORK_ONLY = True
ENABLE_MULTIPLICATIVE_POST_UNEXPLORED = False

WEIGHTS_NOTE = (
    "Score = RankingScorer weighted mode: sum(w_i * P(action_i)), then +0.001 "
    "offset, then OON x 0.75. Weights from xai-org/x-algorithm "
    "home-mixer/params/param.rs (upstream defaults sync 2026-08-12). Weights scale "
    "predicted probabilities, not raw counts. VQV, profile-click, click-dwell, active-seconds, "
    "author diversity/boosts, VMRanker, and visibility filters are not modeled. Not Phoenix, "
    "not the live graph, and runtime experiment overrides are unknown. "
    + CALIBRATION_NOTE
)

DISCLAIMER = (
    "Experimental, prior-mapped comparative simulation. It uses selected public X scoring "
    "defaults, not Phoenix, runtime experiments, the live user graph, or empirical calibration. "
    "It is neither an X replica nor a virality prediction."
)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _positive_sum() -> float:
    skip = {"not_interested", "block_author", "mute_author", "report", "not_dwelled"}
    total = 0.0
    for key, weight in X_WEIGHTS.items():
        if key in skip:
            continue
        if key == "post_unexplored" and ENABLE_MULTIPLICATIVE_POST_UNEXPLORED:
            continue
        total += weight
    return total


def _negative_sum() -> float:
    return -(
        X_WEIGHTS["not_interested"]
        + X_WEIGHTS["block_author"]
        + X_WEIGHTS["mute_author"]
        + X_WEIGHTS["report"]
        + X_WEIGHTS["not_dwelled"]
    )


POSITIVE_SUM = _positive_sum()
NEGATIVE_SUM = _negative_sum()
TOTAL_SUM = POSITIVE_SUM + NEGATIVE_SUM


def _apply(score: float, weight: float) -> float:
    return float(score) * weight


def weighted_parts(reaction: PersonaReaction, *, in_network: bool) -> tuple[float, float]:
    w = X_WEIGHTS
    post_unexplored_term = 0.0
    if in_network or not POST_UNEXPLORED_IN_NETWORK_ONLY:
        post_unexplored_term = _apply(reaction.post_unexplored_probability, w["post_unexplored"])
    terms = [
        _apply(reaction.like_probability, w["favorite"]),
        _apply(reaction.reply_probability, w["reply"]),
        _apply(reaction.repost_probability, w["retweet"]),
        _apply(reaction.photo_expand_probability, w["photo_expand"]),
        _apply(reaction.video_open_probability, w["video_open"]),
        _apply(reaction.click_probability, w["click"]),
        _apply(reaction.open_link_probability, w["open_link"]),
        _apply(0.0, w["profile_click"]),
        _apply(0.0, w["vqv"]),
        _apply(reaction.share_probability, w["share"]),
        _apply(reaction.share_via_dm_probability, w["share_via_dm"]),
        _apply(reaction.share_via_copy_link_probability, w["share_via_copy_link"]),
        _apply(reaction.dwell_probability, w["dwell"]),
        _apply(reaction.quote_probability, w["quote"]),
        _apply(reaction.quoted_click_probability, w["quoted_click"]),
        _apply(0.0, w["quoted_vqv"]),
        _apply(reaction.dwell_time, CONT_DWELL_TIME_WEIGHT),
        _apply(reaction.follow_probability, w["follow_author"]),
        _apply(reaction.not_interested_probability, w["not_interested"]),
        _apply(reaction.block_probability, w["block_author"]),
        _apply(reaction.mute_probability, w["mute_author"]),
        _apply(reaction.report_probability, w["report"]),
        _apply(reaction.not_dwelled_probability, w["not_dwelled"]),
        0.0 if ENABLE_MULTIPLICATIVE_POST_UNEXPLORED else post_unexplored_term,
    ]
    pos = sum(t for t in terms if t >= 0.0)
    neg = -sum(t for t in terms if t < 0.0)
    return pos, neg


def offset_score(combined: float) -> float:
    if TOTAL_SUM == 0.0:
        return max(combined, 0.0)
    if combined < 0.0:
        return (combined + NEGATIVE_SUM) / TOTAL_SUM * NEGATIVE_SCORES_OFFSET
    return combined + NEGATIVE_SCORES_OFFSET


def ranking_score(reactions: list[PersonaReaction], *, in_network: bool = True) -> float:
    if not reactions:
        return 0.0
    parts = [weighted_parts(r, in_network=in_network) for r in reactions]
    pos = sum(p for p, _ in parts) / len(parts)
    neg = sum(n for _, n in parts) / len(parts)
    raw = offset_score(pos - neg)
    if not in_network:
        raw *= OON_WEIGHT_FACTOR
    return raw


def to_ui_score(raw: float) -> float:
    return calibrated_ui_score(raw)


def audience_score(reactions: list[PersonaReaction], in_network: bool = True) -> float:
    return to_ui_score(ranking_score(reactions, in_network=in_network))
