from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_robots_allows_llms() -> None:
    text = client.get("/robots.txt").text
    assert "Allow: /llms.txt" in text
    assert "Disallow: /api/simulate" in text
    assert "Disallow: /api/compare" in text
    assert "Disallow: /api/simulations" in text


def test_unknown_simulation_404() -> None:
    assert client.get("/api/simulations/missing").status_code == 404


def test_llms_txt_served() -> None:
    response = client.get("/llms.txt")
    assert response.status_code == 200
    assert "Impact Simulator" in response.text
