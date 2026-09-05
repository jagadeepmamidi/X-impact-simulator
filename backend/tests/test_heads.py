from app.heads import FAVORITE_BLEND, RETWEET_BLEND, apply_trained_heads, blend_content_probability
from app.schemas import PersonaReaction


def _reaction() -> PersonaReaction:
    return PersonaReaction(
        persona_id="a",
        topic_affinity=0.5,
        like_probability=0.2,
        reply_probability=0.4,
        repost_probability=0.1,
        quote_probability=0.3,
        dwell_probability=0.5,
        follow_probability=0.2,
        block_probability=0.15,
        negative_feedback_probability=0.02,
        reason="base",
    )


def test_blends_favorite_and_retweet_only(monkeypatch) -> None:
    import app.heads as heads

    monkeypatch.setattr(heads, "predict_text", lambda _t: {"favorite": 0.8, "retweet": 0.2, "reply": 0.9})
    out, used = apply_trained_heads([_reaction()], "shipping a concrete result for this pack")
    assert used
    assert abs(out[0].like_probability - blend_content_probability(0.2, 0.8, FAVORITE_BLEND)) < 1e-9
    assert abs(out[0].repost_probability - blend_content_probability(0.1, 0.2, RETWEET_BLEND)) < 1e-9
    assert out[0].reply_probability == 0.4
    assert out[0].follow_probability == 0.2
    assert out[0].block_probability == 0.15
    assert "favorite=0.80" in out[0].reason


def test_skips_when_model_absent(monkeypatch) -> None:
    import app.heads as heads

    monkeypatch.setattr(heads, "predict_text", lambda _t: None)
    src = _reaction()
    out, used = apply_trained_heads([src], "shipping a concrete result for this pack")
    assert used is False
    assert out[0].like_probability == src.like_probability


def test_inference_failure_falls_back_without_crashing(monkeypatch) -> None:
    import app.heads as heads

    class BrokenPipeline:
        def predict_proba(self, _rows):
            raise RuntimeError("artifact is not fitted")

    monkeypatch.setattr(
        heads,
        "load_bundle",
        lambda: {"pipeline": BrokenPipeline(), "heads": ["favorite", "retweet"]},
    )

    src = _reaction()
    out, used = apply_trained_heads([src], "shipping a concrete result for this pack")

    assert used is False
    assert out == [src]


def test_content_head_preserves_persona_ordering(monkeypatch) -> None:
    import app.heads as heads

    monkeypatch.setattr(heads, "predict_text", lambda _t: {"favorite": 0.9, "retweet": 0.8})
    low = _reaction().model_copy(update={"persona_id": "low", "like_probability": 0.1})
    high = _reaction().model_copy(update={"persona_id": "high", "like_probability": 0.7})

    out, used = apply_trained_heads([low, high], "shipping a concrete result for this pack")

    assert used is True
    assert out[0].like_probability < out[1].like_probability
