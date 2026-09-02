from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import cv2
import numpy as np


def encode_image_bytes(data: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _jpeg_from_bgr(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise RuntimeError("Failed to encode frame")
    return bytes(buf)


def sample_video_frames(video_bytes: bytes, count: int = 5) -> list[str]:
    suffix = ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(video_bytes)
        path = tmp.name
    cap = cv2.VideoCapture(path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        indexes = np.linspace(0, total - 1, num=min(count, total), dtype=int)
        urls: list[str] = []
        for idx in indexes:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            scale = 720 / max(h, w)
            if scale < 1:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
            urls.append(encode_image_bytes(_jpeg_from_bgr(frame)))
        return urls[:count]
    finally:
        cap.release()
        Path(path).unlink(missing_ok=True)


def write_temp(data: bytes, suffix: str) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.write(data)
    handle.close()
    return handle.name
