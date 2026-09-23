import pytest
from fastapi.testclient import TestClient

from backend.app.config import DEFAULT_DATA_PATH, ROOT
from backend.app.main import create_app
from backend.app.models import OptionsResponse, RecommendRequest
from scripts.check_demos import demo_requests


def test_health_options_and_contract(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app(ROOT / DEFAULT_DATA_PATH)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["dataset_status"] == "ready"
        assert health.json()["profile_count"] == 66
        assert isinstance(health.json()["recommendation_implemented"], bool)
        response = client.get("/api/options")
        assert response.status_code == 200
        options = OptionsResponse.model_validate(response.json())
        assert set(options.cities) == {"Алматы", "Астана", "Зарубежье"}
        assert "Декоратор" in options.categories  # Можно выбрать отсутствующую пару.
        astana = next(item for item in options.categories_by_city if item.city == "Астана")
        assert "Декоратор" not in astana.categories
        # Готовность POST проверяется строго в integration_cases.py (200, не 501).
        # Этот контракт health/options одинаков для каркаса и готового backend.
        schema = client.get("/openapi.json").json()
        assert "RecommendResponse" in schema["components"]["schemas"]


def test_missing_data_is_not_no_match(tmp_path):
    with TestClient(create_app(tmp_path / "missing.csv")) as client:
        assert client.get("/api/health").json()["dataset_status"] == "missing"
        assert client.get("/api/options").status_code == 503
        response = client.post("/api/recommend", json=demo_requests()[0].model_dump(mode="json"))
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "dataset_missing"


@pytest.mark.parametrize("changes", [
    {"date": "2026-09-22"}, {"date": "2027-01-01"}, {"date": "2026-10-32"},
    {"date": "2026-10-10T00:00:00"}, {"date": "10.10.2026"},
    {"budget_kzt": 0}, {"budget_kzt": -1}, {"budget_kzt": "100000"},
    {"budget_kzt": True}, {"duration_hours": 0}, {"language": " "}, {"city": " "},
])
def test_bad_input_is_422_even_if_data_missing(tmp_path, changes):
    with TestClient(create_app(tmp_path / "missing.csv")) as client:
        request = demo_requests()[0].model_dump(mode="json") | changes
        response = client.post("/api/recommend", json=request)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_normalization_and_calendar_boundaries():
    base = demo_requests()[0].model_dump(mode="json")
    for date in ("2026-09-23", "2026-12-31"):
        request = RecommendRequest.model_validate(base | {"city": "  АЛМАТЫ  ", "date": date})
        assert request.city == "алматы"
