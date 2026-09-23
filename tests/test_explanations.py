import socket

import pytest

from backend.app.explanations import explain, feature_issue
from backend.app.models import PreparedFeature, Profile, RecommendRequest
from scripts.check_demos import demo_requests, evaluate


@pytest.fixture
def example_profile():
    return Profile(id="TEST-EXPLAIN", anon_name="Тест", categories=["Ведущий"], city="Алматы",
                   price_from_kzt=100000, event_formats=["корпоратив"], languages=["русский"],
                   max_hours=6, busy_dates=[], description="Провожу корпоративы с музыкальными викторинами.",
                   synthetic=True, city_imputed=False, price_imputed=False)


@pytest.fixture
def example_request():
    return RecommendRequest(city="Алматы", category="Ведущий", date="2026-10-10",
                            event_format="корпоратив", budget_kzt=100000, language="русский", duration_hours=6)


def assert_evidence(profile, explanation):
    raw = profile.model_dump(mode="json")
    for item in explanation.evidence:
        assert item.value == raw[item.field]
        if item.source != "profile":
            assert item.field == "description" and item.quote and item.quote in profile.description


def test_baseline_real_demos_is_deterministic_and_offline(catalog, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: pytest.fail("explain attempted network"))
    by_id = {p.id: p for p in catalog.profiles}
    for request in demo_requests():
        texts = []
        for id in evaluate(catalog, request)["eligible_ids"]:
            profile = by_id[id]
            result = explain(profile, request)
            assert result == explain(profile, request)
            assert result.mode == "baseline"
            assert result.text.count(".") in (1, 2)
            assert "итоговая стоимость требует уточнения" in result.text
            assert_evidence(profile, result)
            texts.append(result.text)
        assert len(texts) == len(set(texts)), "Объяснения реального запроса должны различаться"


def test_null_hours_does_not_claim_unlimited_service(example_profile, example_request):
    profile = example_profile.model_copy(update={"max_hours": None})
    result = explain(profile, example_request.model_copy(update={"duration_hours": 100}))
    assert "не привязана к присутствию" in result.text
    assert "без ограничений" not in result.text
    assert any(item.field == "max_hours" and item.value is None for item in result.evidence)


def test_optional_fields_are_not_invented(example_profile, example_request):
    result = explain(example_profile, example_request.model_copy(update={"language": None, "duration_hours": None}))
    assert not {"languages", "max_hours"} & {item.field for item in result.evidence}


@pytest.mark.parametrize("description,quote", [
    ("Не специализируюсь на корпоративах.", "специализируюсь на корпоративах"),
    ("Мой коллега говорит: специализируюсь на корпоративах.", "специализируюсь на корпоративах"),
    ("Специализируюсь на свадьбах.", "Специализируюсь на свадьбах."),
    ("Специализируюсь на корпоративах на английском языке.", "Специализируюсь на корпоративах на английском языке."),
    ("Специализируюсь на корпоративах до 12 часов.", "Специализируюсь на корпоративах до 12 часов."),
    ("Специализируюсь на корпоративах за 1 тенге.", "Специализируюсь на корпоративах за 1 тенге."),
    ("Специализируюсь на корпоративах в Астане.", "Специализируюсь на корпоративах в Астане."),
    ("Провожу корпоративы.", "Специализируюсь на корпоративах."),
])
def test_unsupported_features_are_not_used(example_profile, example_request, description, quote):
    profile = example_profile.model_copy(update={"description": description})
    feature = PreparedFeature(kind="format_specialization", event_format="корпоратив", value="корпоратив", quote=quote)
    assert feature_issue(profile, feature)
    result = explain(profile, example_request, (feature,))
    assert result.mode == "baseline"
    assert not any(item.source == "prepared" for item in result.evidence)


def test_prepared_specialization_has_exact_evidence(example_profile, example_request):
    profile = example_profile.model_copy(update={"description": "Специализируюсь на проведении корпоративных мероприятий."})
    feature = PreparedFeature(kind="format_specialization", event_format="корпоратив", value="корпоратив", quote=profile.description)
    assert feature_issue(profile, feature) is None
    result = explain(profile, example_request, (feature,))
    assert result.mode == "prepared"
    assert_evidence(profile, result)


@pytest.mark.parametrize("change", [{"budget_kzt": 1}, {"duration_hours": 7}, {"language": "английский"}, {"event_format": "свадьба"}, {"city": "астана"}, {"category": "фотограф"}])
def test_explainer_cannot_make_rejected_profile_look_eligible(example_profile, example_request, change):
    with pytest.raises(ValueError, match="прошедший все условия"):
        explain(example_profile, example_request.model_copy(update=change))


def test_busy_profile_is_not_explained_as_available(example_profile, example_request):
    with pytest.raises(ValueError):
        explain(example_profile.model_copy(update={"busy_dates": [example_request.date]}), example_request)


@pytest.mark.parametrize("description", [
    "Создаю идеальные сценарии корпоративов.",
    "Создаю стильные сценарии корпоративов с захватывающими танцами.",
    "Тонкий юмор и атмосфера комфорта для каждого гостя.",
    "Мой коллега — ведущий корпоративов и сценарист.",
    "Сценарист корпоративов, работаю только на английском языке.",
    "Пишу сценарии свадеб, других форматов нет.",
    "Сценарии корпоративов за 1 тенге, работаю 12 часов.",
])
def test_baseline_does_not_turn_ads_or_conflicts_into_evidence(example_profile, example_request, description):
    result = explain(example_profile.model_copy(update={"description": description}), example_request)
    assert all(e.source == "profile" for e in result.evidence)
    assert description not in result.text


def test_prepared_distinctive_detail_is_not_rewritten(example_profile, example_request):
    feature = PreparedFeature(kind="distinctive_detail", event_format="корпоратив",
                              value="музыкальными викторинами", quote=example_profile.description)
    result = explain(example_profile, example_request, (feature,))
    assert result.mode == "prepared"
    assert "музыкальными викторинами" in result.text
    assert_evidence(example_profile, result)


def test_fractional_duration_is_not_rounded_to_zero(example_profile, example_request):
    result = explain(example_profile, example_request.model_copy(update={"duration_hours": 0.00000000001}))
    assert "запрошено 0,00000000001 ч" in result.text
