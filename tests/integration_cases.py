"""Обязательный интеграционный прогон после подключения backend №1.

Команда: python -m pytest -q tests/integration_cases.py (после обычного pytest).
Имя намеренно не test_*: независимая ветка №3 основана на каркасе без matching.
При явном запуске без движка получаем ошибку, НЕ skip/xfail и НЕ ложный успех.
"""

import csv
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app.catalog import Catalog, load_catalog
from backend.app.config import DEFAULT_DATA_PATH, ROOT
from backend.app.main import create_app
from backend.app.matching import TEMPORARY_WARNING, recommend
from backend.app.models import PreparedFeature, RecommendRequest, RecommendResponse
from backend.app.prepared import FeatureSet, load_features
from scripts.check_demos import demo_requests, evaluate
from scripts.extract_features import parse_response

EXPECTED = [
    {"HK-88430", "HK-29829", "HK-27222", "HK-77838"},
    {"HK-44923", "HK-27222", "HK-44733", "HK-77838"},
    {"HK-39372", "HK-90001"}, set(), set(), {"HK-64395"},
]
COUNTS = [(10, 4), (10, 4), (2, 2), (0, 0), (10, 0), (7, 1)]
EXCLUDED = [[4, 2, 0, 0, 0], [4, 1, 1, 0, 0], [0]*5, [0]*5, [9, 0, 1, 0, 0], [5, 1, 0, 0, 0]]
QUOTE = "Специализируюсь на проведении корпоративных мероприятий."


def assert_response(result, catalog):
    request = result.normalized_request
    by_id = {p.id: p for p in catalog.profiles}
    assert len(result.cards) == min(3, result.eligible_count)
    assert result.eligible_count + sum(s.excluded_count for s in result.diagnostics.filters) == result.total_candidates
    remaining = result.total_candidates
    assert [s.reason for s in result.diagnostics.filters] == ["busy", "budget", "format", "language", "duration"]
    for step in result.diagnostics.filters:
        remaining -= step.excluded_count
        assert step.remaining_count == remaining
    assert TEMPORARY_WARNING not in result.diagnostics.warnings
    for card in result.cards:
        profile = by_id[card.id]
        assert request.date not in profile.busy_dates
        assert card.price_from_kzt == profile.price_from_kzt <= request.budget_kzt
        assert card.synthetic == profile.synthetic
        assert card.city_imputed == profile.city_imputed
        assert card.price_imputed == profile.price_imputed
        assert card.origin == ("source_synthetic" if profile.synthetic else "source_original")
        assert card.explanation and card.evidence
        assert "итоговая стоимость требует уточнения" in card.explanation
        for item in card.evidence:
            assert item.value == profile.model_dump(mode="json")[item.field]
            if item.source != "profile":
                assert item.field == "description" and item.quote and item.quote in profile.description
    for busy in result.diagnostics.busy_profiles:
        assert busy.date == request.date and request.date in by_id[busy.id].busy_dates
        assert busy.evidence.source == "profile" and busy.evidence.field == "busy_dates"
        assert busy.evidence.value == by_id[busy.id].model_dump(mode="json")["busy_dates"]
        assert request.date.isoformat() in busy.evidence.value


@pytest.mark.parametrize("index", range(6))
def test_engine_full_eligible_sets_and_top_three(catalog, index):
    request = demo_requests()[index]
    # У движка нет публичного unbounded-метода. Прогон каждого профиля тем же
    # recommend исключает top-3 ограничение, не дублируя условия фильтрации.
    actual = {p.id for p in catalog.profiles
              if recommend(replace(catalog, profiles=(p,)), request).eligible_count == 1}
    assert actual == EXPECTED[index]
    result = recommend(catalog, request)
    assert (result.total_candidates, result.eligible_count) == COUNTS[index]
    assert [s.excluded_count for s in result.diagnostics.filters] == EXCLUDED[index]
    expected_order = sorted(actual, key=lambda id: (next(p.price_from_kzt for p in catalog.profiles if p.id == id), id))
    assert [c.id for c in result.cards] == expected_order[:3]
    assert result == recommend(catalog, request)
    assert result == recommend(replace(catalog, profiles=tuple(reversed(catalog.profiles))), request)
    assert_response(result, catalog)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app(ROOT / DEFAULT_DATA_PATH, tmp_path / "absent.json")) as client:
        assert client.get("/api/health").json()["recommendation_implemented"] is True
        yield client


@pytest.mark.parametrize("index", range(6))
def test_six_real_requests_through_asgi_api(api, catalog, index):
    request = demo_requests()[index]
    response = api.post("/api/recommend", json=request.model_dump(mode="json"))
    assert response.status_code == 200
    result = RecommendResponse.model_validate(response.json())
    audit = evaluate(catalog, request)
    assert result.status == audit["status"]
    assert (result.total_candidates, result.eligible_count) == COUNTS[index]
    assert [c.id for c in result.cards] == audit["top_ids"]
    assert result.explanation_mode == "baseline"
    assert result.data_version == catalog.data_version
    assert result.diagnostics.warnings  # Отсутствие optional-файла отражено честно.
    assert_response(result, catalog)


def test_date_comparison_proofs_and_florist_flags(api):
    results = [RecommendResponse.model_validate(api.post("/api/recommend", json=r.model_dump(mode="json")).json())
               for r in demo_requests()[:3]]
    assert results[0].data_version == results[1].data_version
    for result, ids in [(results[0], {"HK-44923", "HK-44733"}), (results[1], {"HK-88430", "HK-29829"})]:
        assert ids <= {p.id for p in result.diagnostics.busy_profiles}
        assert ids.isdisjoint(c.id for c in result.cards)
    florist = {c.id: c for c in results[2].cards}
    assert florist["HK-90001"].origin == "source_synthetic"
    assert florist["HK-39372"].price_imputed
    assert all(any(e.field == "max_hours" and e.value is None for e in c.evidence) for c in florist.values())
    assert "всего 2" in results[2].message


@pytest.fixture
def fixture_catalog(fixture_path):
    catalog = load_catalog(fixture_path)
    p = catalog.profiles[0].model_copy(update={"description": QUOTE})
    return replace(catalog, profiles=(p,))


@pytest.fixture
def request_input():
    return RecommendRequest(city=" АлмаТы ", category=" ВЕДУЩИЙ ", event_format=" КОРПОРАТИВ ",
                            date="2026-10-10", budget_kzt=100000, duration_hours=6, language=" РУССКИЙ ")


def test_boundaries_optional_fields_and_no_duration_limit(fixture_catalog, request_input):
    assert recommend(fixture_catalog, request_input).eligible_count == 1  # Обе границы равны.
    for field, value, reason in [("budget_kzt", 99999.99, "budget"), ("duration_hours", 6.01, "duration")]:
        result = recommend(fixture_catalog, request_input.model_copy(update={field: value}))
        assert result.status == "no_match"
        assert next(s.excluded_count for s in result.diagnostics.filters if s.reason == reason) == 1
    p = fixture_catalog.profiles[0].model_copy(update={"max_hours": None})
    assert recommend(replace(fixture_catalog, profiles=(p,)), request_input.model_copy(update={"duration_hours": 100})).eligible_count == 1
    optional = request_input.model_dump(mode="json")
    del optional["duration_hours"], optional["language"]
    assert recommend(fixture_catalog, RecommendRequest.model_validate(optional)).eligible_count == 1


def test_filter_order_counts_each_profile_once(fixture_catalog, request_input):
    base = fixture_catalog.profiles[0]
    changes = [
        {"busy_dates": [request_input.date], "price_from_kzt": 200000, "languages": ["английский"]},
        {"price_from_kzt": 200000, "event_formats": ["свадьба"]},
        {"event_formats": ["свадьба"], "languages": ["английский"]},
        {"languages": ["английский"], "max_hours": 1}, {"max_hours": 1}, {},
    ]
    profiles = tuple(base.model_copy(update={"id": f"TEST-{index}", **change}) for index, change in enumerate(changes))
    sample = replace(fixture_catalog, profiles=profiles)
    result = recommend(sample, request_input)
    assert [s.excluded_count for s in result.diagnostics.filters] == [1]*5
    assert result.total_candidates == 6 and result.eligible_count == 1
    assert_response(result, sample)


def test_prepared_ranking_vs_baseline_and_structured_conditions(fixture_catalog, request_input):
    base = fixture_catalog.profiles[0]
    profiles = tuple(base.model_copy(update={"id": id, "price_from_kzt": price})
                     for id, price in [("TEST-2", 100000), ("TEST-10", 100000), ("TEST-A", 90000), ("TEST-Z", 100000)])
    sample = replace(fixture_catalog, profiles=profiles)
    baseline = recommend(sample, request_input)
    assert [c.id for c in baseline.cards] == ["TEST-A", "TEST-10", "TEST-2"]
    assert baseline.eligible_count == 4
    feature = PreparedFeature(kind="format_specialization", event_format="корпоратив", value="корпоратив", quote=QUOTE)
    features = FeatureSet(sample.sha256, {"TEST-Z": (feature,)})
    result = recommend(sample, request_input, features)
    assert [c.id for c in result.cards] == ["TEST-Z", "TEST-A", "TEST-10"]
    assert result.explanation_mode == "prepared"
    assert result.eligible_count == baseline.eligible_count
    assert any(e.source == "prepared" and e.quote == QUOTE for e in result.cards[0].evidence)
    # Специализация не компенсирует бюджет, язык, лимит или занятость.
    for change in [{"price_from_kzt": 100001}, {"languages": ["английский"]},
                   {"max_hours": 5}, {"event_formats": ["свадьба"]}, {"busy_dates": [request_input.date]}]:
        rejected = replace(sample, profiles=(profiles[-1].model_copy(update=change),))
        assert recommend(rejected, request_input, features).status == "no_match"
    stale = FeatureSet("0"*64, features.profiles)
    assert [c.id for c in recommend(sample, request_input, stale).cards] == [c.id for c in baseline.cards]


def artifact_for(catalog, **changes):
    return dict(schema_version="1.0.0", dataset_sha256=catalog.sha256, model="test-only/model-2026-09-23",
                prompt_version="features-v1", prompt_sha256="a"*64, generated_at="2026-09-23T00:00:00+00:00",
                profiles={catalog.profiles[0].id: [{"kind": "format_specialization", "event_format": "корпоратив",
                                                  "value": "корпоратив", "quote": QUOTE}]}) | changes


@pytest.mark.parametrize("changes", [
    {"dataset_sha256": "0"*64}, {"schema_version": "2.0.0"}, {"prompt_version": "unsupported"},
    {"prompt_sha256": "bad"}, {"model": " "}, {"generated_at": "2026-09-23"},
    {"generated_at": "2026-09-23T00:00:00+05:00"}, {"profiles": {"UNKNOWN": []}},
])
def test_invalid_derived_metadata_falls_back(fixture_catalog, request_input, tmp_path, changes):
    path = tmp_path / "test-only.json"
    path.write_text(json.dumps(artifact_for(fixture_catalog, **changes)), encoding="utf-8")
    features = load_features(path, fixture_catalog)
    result = recommend(fixture_catalog, request_input, features)
    assert result.status == "matched" and result.explanation_mode == "baseline"
    assert features.warnings and not features.profiles


@pytest.mark.parametrize("content", [None, b"not JSON", b'{"profiles":{},"profiles":{}}', b"\xff\xfe", b"[]"])
def test_absent_or_corrupt_derived_falls_back(fixture_catalog, request_input, tmp_path, content):
    path = tmp_path / "test-only.json"
    if content is not None:
        path.write_bytes(content)
    features = load_features(path, fixture_catalog)
    assert features.warnings
    assert recommend(fixture_catalog, request_input, features).explanation_mode == "baseline"


def test_unconfirmed_feature_is_dropped_with_warning(fixture_catalog, request_input, tmp_path):
    artifact = artifact_for(fixture_catalog)
    artifact["profiles"][fixture_catalog.profiles[0].id][0]["quote"] = "Вымышленная цитата"
    path = tmp_path / "test-only.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    features = load_features(path, fixture_catalog)
    assert features.warnings
    assert recommend(fixture_catalog, request_input, features).explanation_mode == "baseline"


def write_fixture(path, profile):
    row = profile.model_dump(mode="json")
    for field in ("categories", "event_formats", "languages", "busy_dates"):
        row[field] = "|".join(row[field])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def test_prepared_artifact_end_to_end_on_explicit_test_fixture(fixture_catalog, request_input, tmp_path):
    data = tmp_path / "test-catalog.csv"
    write_fixture(data, fixture_catalog.profiles[0])
    sample = load_catalog(data)
    artifact = artifact_for(sample)
    # Тот же явно тестовый ответ проходит экстрактор и runtime-загрузчик.
    payload = {"status": "completed", "model": "test-model-2026-09-23", "output": [
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps({"features": artifact["profiles"][sample.profiles[0].id]})}]}]}
    assert parse_response(payload, sample.profiles[0])[2] == 0
    derived = tmp_path / "test-features.json"
    derived.write_text(json.dumps(artifact), encoding="utf-8")
    with TestClient(create_app(data, derived)) as client:
        result = RecommendResponse.model_validate(client.post("/api/recommend", json=request_input.model_dump(mode="json")).json())
        assert result.explanation_mode == "prepared"
        assert_response(result, sample)


@pytest.mark.parametrize("content", ["", "wrong,header\n1,2\n"])
def test_invalid_csv_is_503_not_no_match(tmp_path, content):
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")
    with TestClient(create_app(path, tmp_path / "absent.json")) as client:
        assert client.get("/api/health").json()["dataset_status"] == "invalid"
        response = client.post("/api/recommend", json=demo_requests()[0].model_dump(mode="json"))
        assert response.status_code == 503 and response.json()["error"]["code"] == "dataset_invalid"


@pytest.mark.parametrize("date", ["2026-09-22", "2027-01-01"])
def test_ready_api_rejects_date_outside_calendar(api, date):
    response = api.post("/api/recommend", json=demo_requests()[0].model_dump(mode="json") | {"date": date})
    assert response.status_code == 422


def test_api_null_and_omitted_fields_are_equivalent(api):
    request = demo_requests()[5].model_dump(mode="json")
    with_null = api.post("/api/recommend", json=request).json()
    del request["language"], request["duration_hours"]
    request.update(city="  АЛМАТЫ ", category="БАНКЕТНЫЙ   ЗАЛ", event_format=" СВАДЬБА ")
    assert api.post("/api/recommend", json=request).json() == with_null
