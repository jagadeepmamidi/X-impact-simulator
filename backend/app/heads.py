"""Optional BluePrint text heads used as content-level log-odds signals."""

from __future__ import annotations

import math
from pathlib import Path

from app.schemas import PersonaReaction
from app.scoring import clamp01

HEADS_NOTE = (
    "BluePrint heads infer the content cluster, then apply content-level log-odds lifts to "
    "favorite (40%) and retweet (25%) while preserving persona differences. Other heads "
    "remain unused. Uncalibrated."
)
FAVORITE_BLEND = 0.40
RETWEET_BLEND = 0.25
MIN_CHARS = 12
ARTIFACT_SCHEMA = "phoenix-heads-v2"
REQUIRED_HEADS = frozenset({"favorite", "retweet"})


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
    if not isinstance(loaded, dict):
        _bundle = False
        return None
    heads = loaded.get("heads")
    pipeline = loaded.get("pipeline")
    cluster_pipeline = loaded.get("cluster_pipeline")
    if (
        loaded.get("artifact_schema") != ARTIFACT_SCHEMA
        or not isinstance(heads, (list, tuple))
        or len(heads) != len(set(heads))
        or not REQUIRED_HEADS.issubset(set(heads))
        or not callable(getattr(pipeline, "predict_proba", None))
        or (
            cluster_pipeline is not None
            and not callable(getattr(cluster_pipeline, "predict", None))
        )
        or (cluster_pipeline is None and "cluster_default" not in loaded)
        or not isinstance(loaded.get("training"), dict)
    ):
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
    try:
        cluster_pipeline = bundle.get("cluster_pipeline")
        if cluster_pipeline is not None:
            cluster_id = int(cluster_pipeline.predict([blob[:4000]])[0])
        else:
            cluster_id = int(bundle.get("cluster_default", 0))
        model_input = f"__cluster_{cluster_id}__ {blob[:4000]}"
        proba = bundle["pipeline"].predict_proba([model_input])[0]
        heads = list(bundle["heads"])
        if len(proba) != len(heads):
            return None
        values = [float(value) for value in proba]
        if not all(math.isfinite(value) for value in values):
            return None
        return {head: clamp01(values[i]) for i, head in enumerate(heads)}
    except Exception:
        # Model artifacts are optional. A corrupt/incompatible artifact must never
        # make the deterministic heuristic path unavailable.
        return None


def blend_content_probability(persona_probability: float, content_probability: float, weight: float) -> float:
    """Apply a shared content lift without replacing persona-level variation."""

    persona_probability = clamp01(persona_probability)
    content_probability = clamp01(content_probability)
    if persona_probability in (0.0, 1.0) or weight <= 0.0:
        return persona_probability
    eps = 1e-6
    content_probability = min(max(content_probability, eps), 1.0 - eps)
    persona_logit = math.log(persona_probability / (1.0 - persona_probability))
    content_logit = math.log(content_probability / (1.0 - content_probability))
    shifted = persona_logit + clamp01(weight) * content_logit
    return clamp01(1.0 / (1.0 + math.exp(-shifted)))


def apply_trained_heads(reactions: list[PersonaReaction], text: str) -> tuple[list[PersonaReaction], bool]:
    probs = predict_text(text)
    if not probs:
        return reactions, False
    favorite = clamp01(probs.get("favorite", 0.0))
    retweet = clamp01(probs.get("retweet", 0.0))
    out: list[PersonaReaction] = []
    for reaction in reactions:
        like = blend_content_probability(reaction.like_probability, favorite, FAVORITE_BLEND)
        repost = blend_content_probability(reaction.repost_probability, retweet, RETWEET_BLEND)
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
