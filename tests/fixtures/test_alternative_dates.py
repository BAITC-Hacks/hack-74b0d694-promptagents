"""Alternative dates on explicit in-memory variants of tests/fixtures/catalog.csv."""

from dataclasses import replace
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.app import explanations
from backend.app.catalog import load_catalog
from backend.app.config import DATE_MAX, DATE_MIN
from backend.app.matching import TEMPORARY_WARNING, recommend
from backend.app.models import AlternativeDate, PreparedFeature, RecommendRequest
from backend.app.prepared import FeatureSet
from scripts.check_demos import evaluate


@pytest.fixture
def sample(fixture_path):
    return load_catalog(fixture_path)


@pytest.fixture
def order():
    return RecommendRequest(city=" АлмаТы ", category=" ВЕДУЩИЙ ", date="2026-10-11",
                            event_format=" КОРПОРАТИВ ", budget_kzt=100000,
                            language=" РУССКИЙ ", duration_hours=6)


def calendar():
    return [DATE_MIN + timedelta(days=i) for i in range((DATE_MAX - DATE_MIN).days + 1)]


def with_free_dates(sample, free):
    profile = sample.profiles[0].model_copy(update={"busy_dates": [d for d in calendar() if d not in free]})
    return replace(sample, profiles=(profile,))


def test_alternative_preserves_original_result_and_evidence(sample, order):
    before = sample.profiles[0].model_dump()
    result = recommend(sample, order)
    audit = evaluate(sample, order)
    assert result.status == "no_match"
    assert result.eligible_count == 0 and result.cards == [] and result.total_candidates == 1
    assert result.normalized_request == order
    assert [s.model_dump() for s in result.diagnostics.filters] == audit["filters"]
    assert result.diagnostics.busy_profiles[0].date == order.date
    assert result.diagnostics.warnings == list(sample.report["warnings"]) + list(FeatureSet.absent().warnings)
    assert result.explanation_mode == "baseline"
    alternative = result.alternative
    assert alternative.date == date(2026, 10, 12)  # Equal distance: later wins.
    assert alternative.card.id == sample.profiles[0].id
    assert "2026-10-12" in alternative.card.explanation
    assert "2026-10-11" not in alternative.card.explanation
    proof = {e.field: e for e in alternative.card.evidence}
    assert {"city", "categories", "event_formats", "price_from_kzt", "languages", "max_hours", "busy_dates"} <= proof.keys()
    raw = sample.profiles[0].model_dump(mode="json")
    for evidence in alternative.card.evidence:
        assert evidence.source == "profile" and evidence.value == raw[evidence.field]
    assert order.date.isoformat() in proof["busy_dates"].value
    assert alternative.date.isoformat() not in proof["busy_dates"].value
    assert sample.profiles[0].model_dump() == before
    assert result == recommend(sample, order)


@pytest.mark.parametrize(("requested", "free", "expected"), [
    ("2026-10-11", ["2026-10-09", "2026-10-13"], "2026-10-13"),
    ("2026-10-11", ["2026-10-10", "2026-10-13"], "2026-10-10"),
    ("2026-10-31", ["2026-10-30", "2026-11-01"], "2026-11-01"),
    ("2026-09-23", ["2026-09-24"], "2026-09-24"),
    ("2026-12-31", ["2026-12-30"], "2026-12-30"),
    ("2026-10-01", ["2026-09-23"], "2026-09-23"),
    ("2026-12-20", ["2026-12-31"], "2026-12-31"),
])
def test_nearest_calendar_day_and_inclusive_window(sample, order, requested, free, expected):
    sample = with_free_dates(sample, {date.fromisoformat(d) for d in free})
    result = recommend(sample, order.model_copy(update={"date": date.fromisoformat(requested)}))
    assert result.alternative.date.isoformat() == expected


@pytest.mark.parametrize("requested", [DATE_MIN, date(2026, 10, 11), DATE_MAX])
def test_fully_busy_window_has_no_alternative_even_if_description_claims_availability(sample, order, requested):
    sample = with_free_dates(sample, set())
    profile = sample.profiles[0].model_copy(update={"description": "Свободен каждый день, включая 2027-01-01."})
    result = recommend(replace(sample, profiles=(profile,)), order.model_copy(update={"date": requested}))
    assert result.status == "no_match" and result.alternative is None
    assert result.cards == [] and result.eligible_count == 0


@pytest.mark.parametrize("change", [
    {"budget_kzt": 99999.99}, {"event_format": "свадьба"},
    {"language": "английский"}, {"duration_hours": 6.01},
])
def test_no_relaxation_of_other_conditions(sample, order, change):
    result = recommend(sample, order.model_copy(update=change))
    assert result.status == "no_match" and result.alternative is None
    # Original diagnostics still count the busy filter first.
    assert [s.excluded_count for s in result.diagnostics.filters] == [1, 0, 0, 0, 0]


@pytest.mark.parametrize("change", [{"city": "астана"}, {"category": "флорист"}])
def test_category_absent_never_proposes_date(sample, order, change):
    result = recommend(sample, order.model_copy(update=change))
    assert result.status == "category_absent" and result.alternative is None
    assert result.total_candidates == 0 and result.cards == []


def test_other_cities_and_categories_cannot_supply_an_alternative(sample, order):
    base = sample.profiles[0]
    profiles = (base.model_copy(update={"busy_dates": calendar()}),
                base.model_copy(update={"id": "OTHER-CITY", "city": "Астана", "busy_dates": []}),
                base.model_copy(update={"id": "OTHER-CATEGORY", "categories": ["Флорист"], "busy_dates": []}))
    result = recommend(replace(sample, profiles=profiles), order)
    assert result.status == "no_match" and result.total_candidates == 1 and result.alternative is None


def test_matched_does_not_search_another_date(sample, order):
    result = recommend(sample, order.model_copy(update={"date": date(2026, 10, 10)}))
    assert result.status == "matched" and result.eligible_count == 1 and result.alternative is None


def test_optional_conditions_and_null_hours_keep_original_semantics(sample, order):
    result = recommend(sample, order.model_copy(update={"language": None, "duration_hours": None}))
    assert result.alternative is not None
    profile = sample.profiles[0].model_copy(update={"max_hours": None})
    result = recommend(replace(sample, profiles=(profile,)), order.model_copy(update={"duration_hours": 100}))
    assert result.alternative is not None
    assert any(e.field == "max_hours" and e.value is None for e in result.alternative.card.evidence)


def test_nearest_date_beats_a_better_rank_on_a_farther_date(sample, order):
    near = with_free_dates(sample, {date(2026, 10, 12)}).profiles[0]
    far = with_free_dates(sample, {date(2026, 10, 13)}).profiles[0].model_copy(
        update={"id": "CHEAPER", "price_from_kzt": 1})
    result = recommend(replace(sample, profiles=(far, near)), order)
    assert result.alternative.date == date(2026, 10, 12) and result.alternative.card.id == near.id


def test_existing_ranking_and_explanation_mode_apply_only_to_selected_card(sample, order):
    quote = "Специализируюсь на проведении корпоративных мероприятий."
    base = sample.profiles[0].model_copy(update={"description": quote})
    profiles = tuple(base.model_copy(update={"id": id, "price_from_kzt": price}) for id, price in
                     [("TEST-2", 90000), ("TEST-10", 90000), ("TEST-Z", 100000)])
    sample = replace(sample, profiles=profiles)
    feature = PreparedFeature(kind="format_specialization", event_format="корпоратив", value="корпоратив", quote=quote)
    valid = FeatureSet(sample.sha256, {"TEST-Z": (feature,)})
    for features, expected_id, expected_mode in [(None, "TEST-10", "baseline"),
                                                (valid, "TEST-Z", "prepared"),
                                                (FeatureSet("0" * 64, valid.profiles), "TEST-10", "baseline")]:
        result = recommend(sample, order, features)
        assert result.alternative.card.id == expected_id
        assert result.alternative.explanation_mode == expected_mode
        assert result.explanation_mode == "baseline" and result.cards == []
        assert result == recommend(replace(sample, profiles=tuple(reversed(profiles))), order, features)
        new_order = order.model_copy(update={"date": result.alternative.date})
        assert result.alternative.card == recommend(sample, new_order, features).cards[0]


def test_explainer_receives_only_one_profile_and_alternative_request(sample, order):
    calls = []

    def explain(profile, request, features):
        calls.append((profile.id, request))
        return explanations.explain(profile, request, features)

    profiles = tuple(sample.profiles[0].model_copy(update={"id": f"TEST-{i}"}) for i in range(4))
    result = recommend(replace(sample, profiles=profiles), order, explainer=explain)
    assert len(calls) == 1
    assert calls[0][0] == result.alternative.card.id
    assert calls[0][1].model_dump() == order.model_dump() | {"date": result.alternative.date}


def test_alternative_fallback_warning_does_not_change_original_diagnostics(sample, order, monkeypatch):
    original = recommend(sample, order)

    def unfinished(*args):
        raise NotImplementedError

    monkeypatch.setattr(explanations, "explain", unfinished)
    result = recommend(sample, order)
    assert result.diagnostics == original.diagnostics
    assert result.alternative.warnings == [TEMPORARY_WARNING]
    assert result.alternative.explanation_mode == "baseline"


@pytest.mark.parametrize("invalid_date", ["2026-09-22", "2027-01-01"])
def test_response_model_rejects_alternative_outside_window(sample, order, invalid_date):
    alternative = recommend(sample, order).alternative.model_dump(mode="json")
    with pytest.raises(ValidationError):
        AlternativeDate.model_validate(alternative | {"date": invalid_date})
