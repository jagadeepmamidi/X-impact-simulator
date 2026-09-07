import base64

import cv2
import numpy as np

from app import pipeline
from app.media import encode_image_bytes


def test_five_images_preserved_in_provider_safe_contact_sheet(monkeypatch):
    monkeypatch.setattr(pipeline.settings, 'groq_vision_model', 'qwen/qwen3.6-27b')
    colors = [(0, 0, 250), (0, 250, 0), (250, 0, 0), (0, 250, 250), (250, 0, 250)]
    images = []
    for color in colors:
        ok, blob = cv2.imencode('.png', np.full((100, 100, 3), color, dtype=np.uint8))
        assert ok
        images.append((blob.tobytes(), 'image/png'))
    prepared = pipeline.prepare_media(images, None)
    assert len(prepared.image_urls) == 1
    assert 'All 5 images/frames' in prepared.note
    decoded = cv2.imdecode(np.frombuffer(base64.b64decode(prepared.image_urls[0].split(',')[1]), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (1080, 1536)
    for index, expected in enumerate(colors):
        actual = decoded[(index // 3) * 540 + 284, (index % 3) * 512 + 256]
        assert np.max(np.abs(actual.astype(int) - np.array(expected))) < 8


def test_single_image_keeps_original_detail(monkeypatch):
    monkeypatch.setattr(pipeline.settings, 'groq_vision_model', 'qwen/qwen3.6-27b')
    blob = b'untouched encoded source'
    prepared = pipeline.prepare_media([(blob, 'image/png')], None)
    assert prepared.image_urls == (encode_image_bytes(blob, 'image/png'),)
