import asyncio
import re
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.limits import client_ip, limiter
from app.pipeline import compare_hooks, replay_report, run_pipeline
from app.schemas import Niche, OutcomeRecord
from app.scoring import DISCLAIMER
from app.sim_config import SIMULATOR_VERSION
from app.store import (
    SnapshotIntegrityError,
    UnknownRunError,
    delete_report,
    load_outcome,
    load_report,
    load_snapshot,
    list_reports,
    save_outcome,
    storage_status,
)


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Enforce the actual ASGI body size, including chunked requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/api/"):
            await self.app(scope, receive, send)
            return
        maximum = settings.max_request_bytes
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        declared = headers.get(b"content-length", b"").decode("ascii", "ignore")
        if declared.isdigit() and int(declared) > maximum:
            await JSONResponse(status_code=413, content={"detail": "Request body exceeds configured limit"})(
                scope, receive, send
            )
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > maximum:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await JSONResponse(status_code=413, content={"detail": "Request body exceeds configured limit"})(
                scope, receive, send
            )

app = FastAPI(title="X Impact Simulator", version=SIMULATOR_VERSION)
app.add_middleware(RequestBodyLimitMiddleware)
_cors = {
    "allow_origins": settings.cors_origin_list,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_origin_regex.strip():
    _cors["allow_origin_regex"] = settings.cors_origin_regex.strip()
app.add_middleware(CORSMiddleware, **_cors)


@app.exception_handler(SnapshotIntegrityError)
async def snapshot_integrity_error(_: Request, __: SnapshotIntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Stored simulation failed integrity verification"})

ALLOWED_NICHES: tuple[Niche, ...] = ("tech", "fitness", "finance", "comedy")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MAX_IMAGES = settings.max_images
MAX_IMAGE_BYTES = settings.max_image_bytes
MAX_VIDEO_BYTES = settings.max_video_bytes
MAX_TOTAL_BYTES = settings.max_total_upload_bytes
MAX_TEXT_CHARS = settings.max_text_chars
UPLOAD_CHUNK_BYTES = settings.upload_chunk_bytes
ALLOWED_POPULATIONS = {40, 100, 320, 500}
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RUN_CAPACITY = threading.BoundedSemaphore(settings.sim_max_concurrent_runs)
REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = REPO_ROOT / "frontend" / "public"


@dataclass(frozen=True)
class AuthContext:
    owner_id: str
    is_admin: bool = False


def protect_access(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    host = client_ip(request, settings.trusted_proxy_list)
    supplied = x_api_key or ""
    admin_key = settings.sim_api_key.strip()
    access_keys = settings.sim_access_key_map
    admin_match = bool(admin_key) and secrets.compare_digest(supplied.encode(), admin_key.encode())
    matched_owner = next(
        (
            owner_id
            for owner_id, expected in access_keys.items()
            if secrets.compare_digest(supplied.encode(), expected.encode())
        ),
        None,
    )
    if not admin_key and not access_keys:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="Production authentication is not configured")
        auth = AuthContext(owner_id="development")
    elif admin_match:
        auth = AuthContext(owner_id="admin", is_admin=True)
    elif matched_owner is not None:
        auth = AuthContext(owner_id=matched_owner)
    else:
        limiter.hit(
            f"unauthenticated:{host}",
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
            max_keys=settings.rate_limit_max_clients,
        )
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    limiter.hit(
        f"{auth.owner_id}:{host}",
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
        max_keys=settings.rate_limit_max_clients,
    )
    return auth


protect_write = protect_access


def _owner_filter(auth: AuthContext) -> str | None:
    return None if auth.is_admin else auth.owner_id


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise HTTPException(404, "Unknown simulation id")
    return run_id


def _validate_controls(population: int, boost: int, seed: int | None) -> None:
    if population not in ALLOWED_POPULATIONS:
        raise HTTPException(422, f"population must be one of {sorted(ALLOWED_POPULATIONS)}")
    if not 1 <= boost <= 12:
        raise HTTPException(422, "boost must be between 1 and 12")
    if seed is not None and not 0 <= seed <= 2**63 - 1:
        raise HTTPException(422, "seed must be between 0 and 2^63-1")


def _validate_text(value: str, field: str, *, required: bool = False) -> None:
    if len(value) > MAX_TEXT_CHARS:
        raise HTTPException(413, f"{field} exceeds {MAX_TEXT_CHARS} characters")
    if "\x00" in value:
        raise HTTPException(400, f"{field} contains a null character")
    if required and not value.strip():
        raise HTTPException(400, f"{field} is required")


async def _run_bounded(function, *args, **kwargs):
    """Run synchronous analysis off the event loop with a fixed in-process capacity."""
    if not _RUN_CAPACITY.acquire(blocking=False):
        raise HTTPException(503, "Analysis capacity is busy; retry shortly", headers={"Retry-After": "1"})

    def invoke():
        try:
            return function(*args, **kwargs)
        finally:
            # The worker owns the slot so disconnect cancellation cannot release
            # capacity while the synchronous work is still running.
            _RUN_CAPACITY.release()

    # Shield queued work too: cancelling its await must not strand an acquired slot.
    task = asyncio.create_task(asyncio.to_thread(invoke))
    task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.shield(task)


def _public_text(name: str) -> str:
    path = PUBLIC_DIR / name
    if not path.is_file():
        raise HTTPException(404, name)
    return path.read_text(encoding="utf-8")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/llms.txt")


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots() -> str:
    return (
        "User-agent: *\n"
        "Allow: /llms.txt\n"
        "Allow: /llms-full.txt\n"
        "Allow: /ai.txt\n"
        "Allow: /robots.txt\n"
        "Allow: /api/health\n"
        "Disallow: /api/simulate\n"
        "Disallow: /api/compare\n"
        "Disallow: /api/simulations\n"
    )


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_txt() -> str:
    return _public_text("llms.txt")


@app.get("/llms-full.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_full() -> str:
    return _public_text("llms-full.txt")


@app.get("/ai.txt", response_class=PlainTextResponse, include_in_schema=False)
def ai_txt() -> str:
    return _public_text("ai.txt")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "groq": settings.groq_enabled,
        "experimental": True,
        "auth": bool(settings.sim_api_key.strip() or settings.sim_access_key_map),
        "environment": settings.app_env,
        "storage": storage_status(),
    }


@app.get("/api/niches")
def niches() -> dict:
    return {
        "niches": list(ALLOWED_NICHES),
        "disclaimer": DISCLAIMER,
    }


async def _read_media(
    images: list[UploadFile] | None,
    video: UploadFile | None,
) -> tuple[list[tuple[bytes, str]], tuple[bytes, str] | None]:
    uploads = [item for item in (images or []) if item.filename]
    if len(uploads) > MAX_IMAGES:
        raise HTTPException(413, f"At most {MAX_IMAGES} images are allowed")
    image_blobs: list[tuple[bytes, str]] = []
    total = 0
    for item in uploads:
        declared = _declared_mime(item)
        if declared not in IMAGE_TYPES:
            await item.close()
            raise HTTPException(415, f"Unsupported image type: {declared or 'missing'}")
        data = await _read_bounded(item, MAX_IMAGE_BYTES, total, "Image")
        total += len(data)
        actual = _sniff_media_type(data)
        if actual not in IMAGE_TYPES or actual != declared:
            raise HTTPException(415, "Image content does not match its declared supported format")
        image_blobs.append((data, actual))
    video_blob: tuple[bytes, str] | None = None
    if video is not None and video.filename:
        declared = _declared_mime(video)
        if declared not in VIDEO_TYPES:
            await video.close()
            raise HTTPException(415, f"Unsupported video type: {declared or 'missing'}")
        data = await _read_bounded(video, MAX_VIDEO_BYTES, total, "Video")
        total += len(data)
        actual = _sniff_media_type(data)
        if actual not in VIDEO_TYPES or actual != declared:
            raise HTTPException(415, "Video content does not match its declared supported format")
        suffix = ".webm" if actual == "video/webm" else ".mov" if actual == "video/quicktime" else ".mp4"
        video_blob = (data, suffix)
    return image_blobs, video_blob


def _declared_mime(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


async def _read_bounded(upload: UploadFile, maximum: int, total: int, label: str) -> bytes:
    known_size = getattr(upload, "size", None)
    if isinstance(known_size, int):
        if known_size > maximum:
            await upload.close()
            raise HTTPException(413, f"{label} exceeds its configured size limit")
        if total + known_size > MAX_TOTAL_BYTES:
            await upload.close()
            raise HTTPException(413, "Combined upload exceeds its configured size limit")

    output = bytearray()
    try:
        while True:
            remaining = maximum - len(output)
            chunk = await upload.read(min(UPLOAD_CHUNK_BYTES, remaining + 1))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > maximum:
                raise HTTPException(413, f"{label} exceeds its configured size limit")
            if total + len(output) > MAX_TOTAL_BYTES:
                raise HTTPException(413, "Combined upload exceeds its configured size limit")
    finally:
        await upload.close()
    if not output:
        raise HTTPException(400, f"{label} is empty")
    return bytes(output)


def _sniff_media_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x1aE\xdf\xa3") and b"webm" in data[:4096].lower():
        return "video/webm"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    return None


@app.post("/api/simulate")
async def simulate(
    niche: Niche = Form(...),
    text: str = Form(""),
    seed: int | None = Form(default=None),
    boost: int = Form(default=6),
    population: int = Form(default=100),
    images: list[UploadFile] | None = File(default=None),
    video: UploadFile | None = File(default=None),
    auth: AuthContext = Depends(protect_write),
):
    if niche not in ALLOWED_NICHES:
        raise HTTPException(400, "Unknown niche pack")
    _validate_text(text, "text")
    _validate_controls(population, boost, seed)
    image_blobs, video_blob = await _read_media(images, video)
    if not text.strip() and not image_blobs and video_blob is None:
        raise HTTPException(400, "Provide text, images, or a video")
    return await _run_bounded(run_pipeline,
        niche,
        text,
        image_blobs,
        video_blob,
        seed=seed,
        population=population,
        boost=boost,
        owner_id=auth.owner_id,
    )


@app.post("/api/compare")
async def compare(
    niche: Niche = Form(...),
    text_a: str = Form(...),
    text_b: str = Form(...),
    seed: int | None = Form(default=None),
    boost: int = Form(default=6),
    population: int = Form(default=100),
    images: list[UploadFile] | None = File(default=None),
    video: UploadFile | None = File(default=None),
    auth: AuthContext = Depends(protect_write),
):
    if niche not in ALLOWED_NICHES:
        raise HTTPException(400, "Unknown niche pack")
    _validate_text(text_a, "text_a", required=True)
    _validate_text(text_b, "text_b", required=True)
    _validate_controls(population, boost, seed)
    image_blobs, video_blob = await _read_media(images, video)
    return await _run_bounded(compare_hooks,
        niche,
        text_a,
        text_b,
        image_blobs,
        video_blob,
        seed=seed,
        population=population,
        boost=boost,
        owner_id=auth.owner_id,
    )


@app.get("/api/simulations/{run_id}")
def get_simulation(run_id: str, auth: AuthContext = Depends(protect_access)):
    report = load_report(_validate_run_id(run_id), owner_id=_owner_filter(auth))
    if report is None:
        raise HTTPException(404, "Unknown simulation id")
    return report


@app.post("/api/simulations/{run_id}/replay")
async def replay_simulation(run_id: str, auth: AuthContext = Depends(protect_write)):
    source = load_report(_validate_run_id(run_id), owner_id=_owner_filter(auth))
    if source is None:
        raise HTTPException(404, "Unknown simulation id")
    try:
        return await _run_bounded(replay_report, source, owner_id=auth.owner_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/simulations")
def recent_simulations(limit: int = 20, auth: AuthContext = Depends(protect_access)):
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    owner_id = _owner_filter(auth)
    return {"runs": list_reports(owner_id=owner_id, limit=limit)}


@app.get("/api/simulations/{run_id}/outcome")
def get_outcome(run_id: str, auth: AuthContext = Depends(protect_access)):
    run_id = _validate_run_id(run_id)
    owner_id = _owner_filter(auth)
    if load_report(run_id, owner_id=owner_id) is None:
        raise HTTPException(404, "Unknown simulation id")
    record = load_outcome(run_id, owner_id=owner_id)
    if record is None:
        raise HTTPException(404, "No outcome recorded")
    return record


@app.post("/api/simulations/{run_id}/outcome")
def post_outcome(run_id: str, body: OutcomeRecord, auth: AuthContext = Depends(protect_write)):
    run_id = _validate_run_id(run_id)
    if body.run_id != run_id:
        raise HTTPException(409, "Outcome run_id must match the URL")
    owner_id = _owner_filter(auth)
    if load_report(run_id, owner_id=owner_id) is None:
        raise HTTPException(404, "Unknown simulation id")
    try:
        return save_outcome(body, owner_id=owner_id)
    except UnknownRunError as exc:
        raise HTTPException(404, "Unknown simulation id") from exc


@app.get("/api/simulations/{run_id}/snapshot")
def get_simulation_snapshot(run_id: str, auth: AuthContext = Depends(protect_access)):
    snapshot = load_snapshot(_validate_run_id(run_id), owner_id=_owner_filter(auth))
    if snapshot is None:
        raise HTTPException(404, "Unknown simulation id")
    return snapshot


@app.delete("/api/simulations/{run_id}", status_code=204)
def delete_simulation(run_id: str, auth: AuthContext = Depends(protect_write)) -> None:
    if not delete_report(_validate_run_id(run_id), owner_id=_owner_filter(auth)):
        raise HTTPException(404, "Unknown simulation id")
