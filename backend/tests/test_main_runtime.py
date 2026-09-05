import asyncio
import threading
import httpx

import pytest
from fastapi import HTTPException

import app.main as main


def test_simulation_keeps_health_responsive(monkeypatch, tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_pipeline(*args, **kwargs) -> dict:
        started.set()
        release.wait(5)
        return {"done": True}

    import app.store as store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.sqlite")
    monkeypatch.setattr(main, "run_pipeline", slow_pipeline)
    monkeypatch.setitem(main.app.dependency_overrides, main.protect_access, lambda: main.AuthContext("test"))

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            task = asyncio.create_task(client.post("/api/simulate", data={"niche": "tech", "text": "fixture"}))
            try:
                assert await asyncio.to_thread(started.wait, 1)
                health = await asyncio.wait_for(client.get("/api/health"), timeout=1)
                assert health.status_code == 200
                assert not task.done(), "Health must finish while the analysis is still running"
            finally:
                release.set()
            assert (await task).json() == {"done": True}

    asyncio.run(exercise())


def test_bounded_pipeline_rejects_when_full_and_releases_after_failure(monkeypatch) -> None:
    capacity = threading.BoundedSemaphore(1)
    monkeypatch.setattr(main, "_RUN_CAPACITY", capacity)
    started = threading.Event()
    release = threading.Event()

    def blocked_pipeline() -> None:
        started.set()
        release.wait(2)

    def failing_pipeline() -> None:
        raise RuntimeError("fixture failure")

    async def exercise() -> None:
        first = asyncio.create_task(main._run_bounded(blocked_pipeline))
        await asyncio.to_thread(started.wait, 1)
        with pytest.raises(HTTPException) as busy:
            await main._run_bounded(lambda: None)
        assert busy.value.status_code == 503
        assert busy.value.headers["Retry-After"] == "1"
        release.set()
        await first
        with pytest.raises(RuntimeError, match="fixture failure"):
            await main._run_bounded(failing_pipeline)
        assert capacity.acquire(blocking=False) is True
        capacity.release()

    asyncio.run(exercise())


def test_cancelled_request_keeps_capacity_until_worker_finishes(monkeypatch) -> None:
    capacity = threading.BoundedSemaphore(1)
    monkeypatch.setattr(main, "_RUN_CAPACITY", capacity)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocked_pipeline() -> None:
        started.set()
        release.wait(5)
        finished.set()

    async def exercise() -> None:
        first = asyncio.create_task(main._run_bounded(blocked_pipeline))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            with pytest.raises(HTTPException) as busy:
                await main._run_bounded(lambda: None)
            assert busy.value.status_code == 503
        finally:
            release.set()
        assert await asyncio.to_thread(finished.wait, 1)

    asyncio.run(exercise())
    assert capacity.acquire(blocking=False)
    capacity.release()
