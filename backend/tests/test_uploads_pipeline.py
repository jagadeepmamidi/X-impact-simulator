import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import ContentAnalysisUnavailableError, PreparedMedia, extract_content, run_pipeline
from app.schemas import ContentFeatures

client = TestClient(app)


def test_oversized_image_rejected(monkeypatch) -> None:
    monkeypatch.setattr("app.main.MAX_IMAGE_BYTES", 64)
    monkeypatch.setattr("app.main.MAX_TOTAL_BYTES", 64)
    response = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "shipping a concrete eval today"},
        files={"images": ("big.png", b"x" * 128, "image/png")},
    )
    assert response.status_code == 413


def test_simulate_text_returns_calibrated_report() -> None:
    response = client.post(
        "/api/simulate",
        data={
            "niche": "tech",
            "text": "We open-sourced a 12ms eval harness for local LLMs.",
            "population": "40",
            "boost": "6",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["inference_path"].endswith("+prior-map")
    assert body["calibration_status"] == "prior-mapped-not-empirically-calibrated"
    assert body["calibration_version"]
    assert 0 <= body["impact_score"] <= 100
    assert body["impact_score"] < 98
    assert body["simulation"]["score_p10"] <= body["simulation"]["score_p50"] <= body["simulation"]["score_p90"]
    assert body["stability"] > 0
    assert body["confidence"] == 0.0
    assert "simulator randomness only" in body["uncertainty_note"]
    assert body["simulator_version"]


def test_pipeline_separates_strong_and_weak_text() -> None:
    strong = run_pipeline(
        "tech",
        "We open-sourced a 12ms eval harness for local LLMs with a public leaderboard.",
        [],
        None,
        seed=3,
        population=40,
        persist=False,
    )
    weak = run_pipeline("tech", "hello", [], None, seed=3, population=40, persist=False)
    promo = run_pipeline(
        "tech",
        "Buy now! Discount sale subscribe click the link follow for promo codes!!!",
        [],
        None,
        seed=3,
        population=40,
        persist=False,
    )
    assert strong.inference_path.endswith("+prior-map")
    assert weak.impact_score < strong.impact_score
    assert promo.impact_score < strong.impact_score
    assert strong.impact_score < 98
    assert weak.impact_score > 0
    assert any("too little text" in reason.lower() for reason in weak.fallback_reasons)


def test_image_only_input_fails_closed_when_vision_analysis_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.pipeline.groq_vision_content", lambda *args: None)
    monkeypatch.setattr(
        "app.pipeline.prepare_media",
        lambda *args: PreparedMedia(("data:image/png;base64,fixture",), "", "Image analysis of 1 image."),
    )
    monkeypatch.setattr(
        "app.pipeline.groq_text_content",
        lambda *args: (_ for _ in ()).throw(AssertionError("caption fallback must not run for image-only input")),
    )
    try:
        extract_content("", [], None)
    except ContentAnalysisUnavailableError as exc:
        assert "Image analysis is unavailable" in str(exc)
    else:
        raise AssertionError("image-only input must fail closed")
    ok, png = cv2.imencode(".png", np.zeros((8, 8, 3), dtype=np.uint8))
    assert ok
    response = client.post("/api/simulate", data={"niche": "tech"}, files={"images": ("image.png", png.tobytes(), "image/png")})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert "Image analysis is unavailable" in response.json()["detail"]


def test_caption_fallback_marks_image_as_unanalyzed(monkeypatch) -> None:
    monkeypatch.setattr("app.pipeline.groq_vision_content", lambda *args: None)
    monkeypatch.setattr(
        "app.pipeline.prepare_media",
        lambda *args: PreparedMedia(("data:image/png;base64,fixture",), "", "Image analysis of 1 image."),
    )
    monkeypatch.setattr(
        "app.pipeline.groq_text_content",
        lambda text, note: ContentFeatures(topics=["caption"], transcript_excerpt=text, source="groq", media_note=note),
    )
    content = extract_content("caption text", [], None)
    assert "caption-only" in content.media_note.lower()
