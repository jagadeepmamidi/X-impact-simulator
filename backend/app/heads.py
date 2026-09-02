"""BluePrint TFIDF heads. Only favorite (overwrite-heavy) and retweet (light blend)."""

from __future__ import annotations

from pathlib import Path

from app.schemas import PersonaReaction
from app.scoring import clamp01

HEADS_NOTE = (
    "BluePrint heads blend favorite (75%) and retweet (35%) only. "
    "Reply, follow, and negative heads are unused (eval AP too low or unlabeled). Uncalibrated."
)
FAVORITE_BLEND = 0.75
RETWEET_BLEND = 0.35
MIN_CHARS = 12


_bundle: dict | None | bool = None


def model_path() -> Path:
    return Path(__file__).resolve().parents[2] / "training" / "artifacts" / "phoenix_heads.joblib"


def load_bundle() -> dict | None:
    global _bundle
    if _bundle is False:
        return None
    if isinstance(_bundle, dict):
        return _bundle
    path = model_path()
    if not path.is_file():
        _bundle = False
        return None
    try:
        import warnings

        import joblib
        from sklearn.exceptions import InconsistentVersionWarning

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InconsistentVersionWarning)
            loaded = joblib.load(path)
    except Exception:
        _bundle = False
        return None
    if not isinstance(loaded, dict) or "pipeline" not in loaded or "heads" not in loaded:
        _bundle = False
        return None
    _bundle = loaded
    return loaded


def predict_text(text: str) -> dict[str, float] | None:
    blob = (text or "").strip()
    if len(blob) < MIN_CHARS:
        return None
    bundle = load_bundle()
    if not bundle:
        return None
    proba = bundle["pipeline"].predict_proba([blob[:4000]])[0]
    heads = list(bundle["heads"])
    return {head: float(proba[i]) for i, head in enumerate(heads)}


def apply_trained_heads(reactions: list[PersonaReaction], text: str) -> tuple[list[PersonaReaction], bool]:
    probs = predict_text(text)
    if not probs:
        return reactions, False
    favorite = clamp01(probs.get("favorite", 0.0))
    retweet = clamp01(probs.get("retweet", 0.0))
    out: list[PersonaReaction] = []
    for reaction in reactions:
        like = clamp01(FAVORITE_BLEND * favorite + (1.0 - FAVORITE_BLEND) * reaction.like_probability)
        repost = clamp01(RETWEET_BLEND * retweet + (1.0 - RETWEET_BLEND) * reaction.repost_probability)
        note = f" BluePrint heads favorite={favorite:.2f} retweet={retweet:.2f}."
        out.append(
            reaction.model_copy(
                update={
                    "like_probability": like,
                    "repost_probability": repost,
                    "reason": (reaction.reason or "").rstrip() + note,
                }
            )
        )
    return out, True
