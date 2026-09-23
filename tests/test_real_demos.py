"""Эти проверки относятся к независимому аудиту, не готовности recommend API."""
import pytest

from scripts.check_demos import demo_requests, evaluate

EXPECTED = [
    {"HK-88430", "HK-29829", "HK-27222", "HK-77838"},
    {"HK-44923", "HK-27222", "HK-44733", "HK-77838"},
    {"HK-39372", "HK-90001"},
    set(), set(), {"HK-64395"},
]


@pytest.mark.parametrize("index", range(6))
def test_real_eligible_sets_and_determinism(catalog, index):
    request = demo_requests()[index]
    result = evaluate(catalog, request)
    assert set(result["eligible_ids"]) == EXPECTED[index]
    assert result == evaluate(catalog, request)
    assert len(result["top_ids"]) <= 3
    assert result["eligible_count"] + sum(step["excluded_count"] for step in result["filters"]) == result["total_candidates"]
    by_id = {p.id: p for p in catalog.profiles}
    assert all(request.date not in by_id[id].busy_dates for id in result["eligible_ids"])


def test_date_change_has_calendar_evidence(catalog):
    first, second = demo_requests()[:2]
    by_id = {p.id: p for p in catalog.profiles}
    for id in ("HK-88430", "HK-29829"):
        assert first.date not in by_id[id].busy_dates
        assert second.date in by_id[id].busy_dates
    for id in ("HK-44923", "HK-44733"):
        assert first.date in by_id[id].busy_dates
        assert second.date not in by_id[id].busy_dates


def test_florists_null_hours_and_flags(catalog):
    result = evaluate(catalog, demo_requests()[2])
    assert result["total_candidates"] == result["eligible_count"] == 2
    by_id = {p.id: p for p in catalog.profiles}
    assert by_id["HK-39372"].max_hours is None
    assert by_id["HK-90001"].max_hours is None
    assert by_id["HK-90001"].synthetic
    assert by_id["HK-39372"].price_imputed


def test_absent_and_no_match_have_different_reasons(catalog):
    absent = evaluate(catalog, demo_requests()[3])
    empty = evaluate(catalog, demo_requests()[4])
    assert absent["status"] == "category_absent" and absent["total_candidates"] == 0
    assert empty["status"] == "no_match" and empty["total_candidates"] == 10
    assert [item["excluded_count"] for item in empty["filters"]] == [9, 0, 1, 0, 0]


def test_venue_exclusions(catalog):
    result = evaluate(catalog, demo_requests()[5])
    assert result["total_candidates"] == 7
    assert [item["excluded_count"] for item in result["filters"]] == [5, 1, 0, 0, 0]
