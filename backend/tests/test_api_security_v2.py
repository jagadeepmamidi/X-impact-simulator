import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

import app.store as store
from app.config import Settings
from app.limits import SlidingWindowLimiter, client_ip, limiter
from app.main import RequestBodyLimitMiddleware, _read_bounded, _read_media, app, protect_access
from app.schemas import ContentFeatures, Explanation, ImpactReport, SimulationSummary

client = TestClient(app)


class TrackingUpload:
    size = None

    def __init__(self, size: int) -> None:
        self.remaining = size
        self.bytes_read = 0
        self.closed = False

    async def read(self, size: int) -> bytes:
        amount = min(size, self.remaining)
        self.remaining -= amount
        self.bytes_read += amount
        return b"x" * amount

    async def close(self) -> None:
        self.closed = True


def test_bounded_reader_stops_after_limit() -> None:
    upload = TrackingUpload(10_000)
    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_bounded(upload, 64, 0, "Image"))  # type: ignore[arg-type]
    assert error.value.status_code == 413
    assert upload.bytes_read == 65
    assert upload.closed is True


def test_media_signature_must_match_declared_type() -> None:
    upload = UploadFile(
        BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 16),
        filename="fake.jpg",
        size=24,
        headers=Headers({"content-type": "image/jpeg"}),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_media([upload], None))
    assert error.value.status_code == 415


def test_media_signature_is_returned_as_canonical_mime() -> None:
    data = b"\x89PNG\r\n\x1a\n" + b"x" * 16
    upload = UploadFile(
        BytesIO(data),
        filename="valid.png",
        size=len(data),
        headers=Headers({"content-type": "image/png"}),
    )
    images, video = asyncio.run(_read_media([upload], None))
    assert images == [(data, "image/png")]
    assert video is None


def test_actual_request_body_limit(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.max_request_bytes", 100)
    response = client.post("/api/simulate", data={"niche": "tech", "text": "x" * 200})
    assert response.status_code == 413


def test_chunked_request_body_limit(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.max_request_bytes", 4)
    received = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"de", "more_body": False},
    ]
    sent: list[dict] = []

    async def receive() -> dict:
        return received.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def consume(scope, receive, send) -> None:
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    middleware = RequestBodyLimitMiddleware(consume)
    asyncio.run(
        middleware(
            {"type": "http", "path": "/api/simulate", "headers": []},
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 413


def test_saved_run_reads_require_configured_key(monkeypatch, tmp_path) -> None:
    limiter.reset()
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    monkeypatch.setattr("app.main.settings.sim_api_key", "")
    run_id = store.save_report(
        ImpactReport(
            disclaimer="Experimental",
            niche="tech",
            groq_used=False,
            content=ContentFeatures(),
            reactions=[],
            simulation=SimulationSummary(
                seed=1,
                runs=1,
                rounds=[],
                score_p10=0,
                score_p50=0,
                score_p90=0,
                reached_round_p50=0,
                out_of_network=False,
            ),
            impact_score=0,
            explanation=Explanation(headline="h", summary="s", suggestions=[]),
            weights_note="w",
        )
    )

    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    assert client.get(f"/api/simulations/{run_id}").status_code == 401
    authorized = client.get(
        f"/api/simulations/{run_id}", headers={"X-API-Key": "secret-test-key"}
    )
    assert authorized.status_code == 200
    snapshot = client.get(
        f"/api/simulations/{run_id}/snapshot", headers={"X-API-Key": "secret-test-key"}
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["schema_version"] == store.SNAPSHOT_SCHEMA_VERSION
    limiter.reset()


def test_untrusted_peer_cannot_spoof_forwarded_for() -> None:
    request = Request(
        {
            "type": "http",
            "client": ("198.51.100.7", 1234),
            "headers": [(b"x-forwarded-for", b"203.0.113.9")],
        }
    )
    assert client_ip(request, ["10.0.0.0/8"]) == "198.51.100.7"


def test_trusted_proxy_chain_resolves_first_untrusted_hop() -> None:
    request = Request(
        {
            "type": "http",
            "client": ("10.0.0.2", 1234),
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
        }
    )
    assert client_ip(request, ["10.0.0.0/8"]) == "203.0.113.9"


def test_limiter_memory_is_bounded() -> None:
    bounded = SlidingWindowLimiter(max_keys=3)
    for index in range(20):
        bounded.hit(str(index), 10, 60)
    assert len(bounded.hits) == 3


def test_production_requires_auth_durable_store_ack_and_retention() -> None:
    with pytest.raises(ValidationError, match="SIM_API_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            sim_api_key="",
            allow_sqlite_in_production=True,
            run_retention_days=30,
        )
    with pytest.raises(ValidationError, match="SQLite"):
        Settings(
            _env_file=None,
            app_env="production",
            sim_api_key="secret",
            run_retention_days=30,
        )
    configured = Settings(
        _env_file=None,
        app_env="production",
        sim_api_key="secret",
        allow_sqlite_in_production=True,
        run_retention_days=30,
    )
    assert configured.is_production is True
    tenant_configured = Settings(
        _env_file=None,
        app_env="production",
        sim_api_key="",
        sim_access_keys_json='{"operator":"a-long-operator-secret"}',
        allow_sqlite_in_production=True,
        run_retention_days=30,
    )
    assert tenant_configured.sim_access_key_map == {"operator": "a-long-operator-secret"}


def test_tenant_key_cannot_read_another_owners_run(monkeypatch, tmp_path) -> None:
    limiter.reset()
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    monkeypatch.setattr("app.main.settings.sim_api_key", "")
    monkeypatch.setattr(
        "app.main.settings.sim_access_keys_json",
        '{"alice":"alice-secret-key","bob":"bob-secret-key"}',
    )
    created = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "owner isolated run", "population": "40"},
        headers={"X-API-Key": "alice-secret-key"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    assert client.get(
        f"/api/simulations/{run_id}", headers={"X-API-Key": "bob-secret-key"}
    ).status_code == 404
    assert client.get(
        f"/api/simulations/{run_id}", headers={"X-API-Key": "alice-secret-key"}
    ).status_code == 200
    limiter.reset()


def test_rate_limit_identity_is_scoped_by_authenticated_owner(monkeypatch) -> None:
    limiter.reset()
    monkeypatch.setattr("app.main.settings.sim_api_key", "")
    monkeypatch.setattr(
        "app.main.settings.sim_access_keys_json",
        '{"alice":"alice-secret-key","bob":"bob-secret-key"}',
    )
    monkeypatch.setattr("app.main.settings.rate_limit_requests", 1)
    request_a = Request(
        {"type": "http", "client": ("10.0.0.2", 1), "headers": [(b"x-api-key", b"alice-secret-key")]}
    )
    request_b = Request(
        {"type": "http", "client": ("10.0.0.2", 1), "headers": [(b"x-api-key", b"bob-secret-key")]}
    )
    assert protect_access(request_a, "alice-secret-key").owner_id == "alice"
    assert protect_access(request_b, "bob-secret-key").owner_id == "bob"
    with pytest.raises(HTTPException) as error:
        protect_access(request_a, "alice-secret-key")
    assert error.value.status_code == 429
    limiter.reset()
