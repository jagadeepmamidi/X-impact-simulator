from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from pathlib import Path

from app.config import settings
from app.limits import limiter
from app.pipeline import compare_hooks, replay_report, run_pipeline
from app.schemas import Niche, OutcomeRecord
from app.store import load_outcome, load_report, save_outcome

app = FastAPI(title="X Impact Simulator", version="0.3.0")
_cors = {
    "allow_origins": settings.cors_origin_list,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_origin_regex.strip():
    _cors["allow_origin_regex"] = settings.cors_origin_regex.strip()
app.add_middleware(CORSMiddleware, **_cors)

ALLOWED_NICHES: tuple[Niche, ...] = ("tech", "fitness", "finance", "comedy")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = REPO_ROOT / "frontend" / "public"


def protect_write(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = settings.sim_api_key.strip()
    if expected and (x_api_key or "") != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    host = request.client.host if request.client else "anon"
    limiter.hit(host, settings.rate_limit_requests, settings.rate_limit_window_seconds)


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
        "auth": bool(settings.sim_api_key.strip()),
    }


@app.get("/api/niches")
def niches() -> dict:
    return {
        "niches": list(ALLOWED_NICHES),
        "disclaimer": (
            "Experimental / uncalibrated estimate. Not X production. "
            "Not a virality guarantee."
        ),
    }


async def _read_media(
    images: list[UploadFile] | None,
    video: UploadFile | None,
) -> tuple[list[tuple[bytes, str]], tuple[bytes, str] | None]:
    image_blobs: list[tuple[bytes, str]] = []
    total = 0
    for item in (images or [])[:5]:
        mime = item.content_type or "image/jpeg"
        if mime not in IMAGE_TYPES:
            raise HTTPException(400, f"Unsupported image type: {mime}")
        data = await item.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, "Combined upload exceeds 40 MB")
        image_blobs.append((data, mime))
    video_blob: tuple[bytes, str] | None = None
    if video is not None and video.filename:
        mime = video.content_type or "video/mp4"
        if mime not in VIDEO_TYPES:
            raise HTTPException(400, f"Unsupported video type: {mime}")
        data = await video.read()
        if len(data) > MAX_VIDEO_BYTES:
            raise HTTPException(413, f"Video exceeds {MAX_VIDEO_BYTES // (1024 * 1024)} MB")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, "Combined upload exceeds 40 MB")
        suffix = ".webm" if "webm" in mime else ".mov" if "quicktime" in mime else ".mp4"
        video_blob = (data, suffix)
    return image_blobs, video_blob


@app.post("/api/simulate")
async def simulate(
    niche: Niche = Form(...),
    text: str = Form(""),
    seed: int | None = Form(default=None),
    boost: int = Form(default=6),
    population: int = Form(default=100),
    images: list[UploadFile] | None = File(default=None),
    video: UploadFile | None = File(default=None),
    _: None = Depends(protect_write),
):
    if niche not in ALLOWED_NICHES:
        raise HTTPException(400, "Unknown niche pack")
    image_blobs, video_blob = await _read_media(images, video)
    if not text.strip() and not image_blobs and video_blob is None:
        raise HTTPException(400, "Provide text, images, or a video")
    return run_pipeline(niche, text, image_blobs, video_blob, seed=seed, population=population, boost=boost)


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
    _: None = Depends(protect_write),
):
    if niche not in ALLOWED_NICHES:
        raise HTTPException(400, "Unknown niche pack")
    if not text_a.strip() or not text_b.strip():
        raise HTTPException(400, "Provide two captions to compare")
    image_blobs, video_blob = await _read_media(images, video)
    return compare_hooks(
        niche,
        text_a,
        text_b,
        image_blobs,
        video_blob,
        seed=seed,
        population=population,
        boost=boost,
    )


@app.get("/api/simulations/{run_id}")
def get_simulation(run_id: str):
    report = load_report(run_id)
    if report is None:
        raise HTTPException(404, "Unknown simulation id")
    return report


@app.post("/api/simulations/{run_id}/replay")
def replay_simulation(run_id: str, _: None = Depends(protect_write)):
    source = load_report(run_id)
    if source is None:
        raise HTTPException(404, "Unknown simulation id")
    try:
        return replay_report(source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/simulations/{run_id}/outcome")
def get_outcome(run_id: str):
    if load_report(run_id) is None:
        raise HTTPException(404, "Unknown simulation id")
    record = load_outcome(run_id)
    if record is None:
        raise HTTPException(404, "No outcome recorded")
    return record


@app.post("/api/simulations/{run_id}/outcome")
def post_outcome(run_id: str, body: OutcomeRecord, _: None = Depends(protect_write)):
    if load_report(run_id) is None:
        raise HTTPException(404, "Unknown simulation id")
    return save_outcome(body.model_copy(update={"run_id": run_id}))
