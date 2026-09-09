from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.config import Settings
from app.groq_client import reset_request_groq_key, set_request_groq_key
from app.limits import limiter
from app.main import app, protect_access

client = TestClient(app)
DEMO_A = "pub_aaaaaaaaaaaaaaaa"
DEMO_B = "pub_bbbbbbbbbbbbbbbb"


def test_production_allows_public_demo_without_operator_key() -> None:
    configured = Settings(
        _env_file=None,
        app_env="production",
        sim_api_key="",
        sim_public_demo=True,
        allow_sqlite_in_production=True,
        run_retention_days=30,
    )
    assert configured.sim_public_demo is True
    try:
        Settings(
            _env_file=None,
            app_env="production",
            sim_api_key="",
            sim_public_demo=False,
            allow_sqlite_in_production=True,
            run_retention_days=30,
        )
    except ValidationError as exc:
        assert "SIM_API_KEY" in str(exc)
    else:
        raise AssertionError("production without public demo still requires a key")


def test_public_demo_runs_without_operator_key(monkeypatch) -> None:
    limiter.reset()
    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    monkeypatch.setattr("app.main.settings.sim_public_demo", True)
    denied = client.post("/api/simulate", data={"niche": "tech", "text": "hello", "population": "40"})
    assert denied.status_code == 401
    allowed = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "We shipped a 12ms eval harness.", "population": "40", "boost": "6"},
        headers={"X-Demo-Session": DEMO_A},
    )
    assert allowed.status_code == 200
    assert allowed.json()["affinity_reactions"]
    limiter.reset()


def test_public_demo_sessions_cannot_read_each_other(monkeypatch) -> None:
    limiter.reset()
    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    monkeypatch.setattr("app.main.settings.sim_public_demo", True)
    created = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "owner isolated public run", "population": "40"},
        headers={"X-Demo-Session": DEMO_A},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    assert client.get(f"/api/simulations/{run_id}", headers={"X-Demo-Session": DEMO_B}).status_code == 404
    assert client.get(f"/api/simulations/{run_id}", headers={"X-Demo-Session": DEMO_A}).status_code == 200
    limiter.reset()


def test_public_server_groq_budget(monkeypatch) -> None:
    limiter.reset()
    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    monkeypatch.setattr("app.main.settings.sim_public_demo", True)
    monkeypatch.setattr("app.main.settings.sim_public_runs_per_hour", 1)
    first = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "first public run", "population": "40"},
        headers={"X-Demo-Session": DEMO_A},
    )
    second = client.post(
        "/api/simulate",
        data={"niche": "tech", "text": "second public run", "population": "40"},
        headers={"X-Demo-Session": DEMO_B},
    )
    assert first.status_code == 200
    assert second.status_code == 429
    limiter.reset()


def test_request_groq_key_overrides_server_key(monkeypatch) -> None:
    import app.groq_client as groq_client

    seen: dict[str, str] = {}

    class FakeGroq:
        def __init__(self, api_key: str, **_kwargs) -> None:
            seen["api_key"] = api_key

    monkeypatch.setattr(groq_client, "Groq", FakeGroq)
    monkeypatch.setattr(groq_client.settings, "groq_api_key", "server-key")
    token = set_request_groq_key("personal-key")
    try:
        groq_client._client()
        assert seen["api_key"] == "personal-key"
    finally:
        reset_request_groq_key(token)


def test_public_demo_rate_limit_identity_is_session_scoped(monkeypatch) -> None:
    limiter.reset()
    monkeypatch.setattr("app.main.settings.sim_api_key", "secret-test-key")
    monkeypatch.setattr("app.main.settings.sim_public_demo", True)
    monkeypatch.setattr("app.main.settings.rate_limit_requests", 1)
    request_a = Request({"type": "http", "client": ("10.0.0.2", 1), "headers": [(b"x-demo-session", DEMO_A.encode())]})
    request_b = Request({"type": "http", "client": ("10.0.0.2", 1), "headers": [(b"x-demo-session", DEMO_B.encode())]})
    assert protect_access(request_a, None, DEMO_A).owner_id == DEMO_A
    assert protect_access(request_b, None, DEMO_B).owner_id == DEMO_B
    try:
        protect_access(request_a, None, DEMO_A)
        raise AssertionError("expected 429")
    except HTTPException as exc:
        assert exc.status_code == 429
    limiter.reset()
