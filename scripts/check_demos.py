"""Независимая проверка реальных сценариев, НЕ реализация /api/recommend.

Алгоритм использует каталог, не ожидаемые ID. На этом этапе specialization=0:
AI-артефакта нет. После реализации №1 тесты дополнительно проверяют настоящий API.
"""
import json

from backend.app.catalog import Catalog, load_catalog
from backend.app.config import DEFAULT_DATA_PATH, configured_path
from backend.app.models import Profile, RecommendRequest, normalize


def demo_requests() -> list[RecommendRequest]:
    base = dict(city="Алматы", category="Ведущий", event_format="корпоратив",
                budget_kzt=1000000, language="русский", duration_hours=6)
    return [
        RecommendRequest(**base, date="2026-10-10"),
        RecommendRequest(**base, date="2026-10-11"),
        RecommendRequest(city="Алматы", category="Флорист", date="2026-10-11",
                         event_format="свадьба", budget_kzt=300000, language="русский", duration_hours=8),
        RecommendRequest(city="Астана", category="Декоратор", date="2026-10-10",
                         event_format="свадьба", budget_kzt=500000),
        RecommendRequest(**base, date="2026-12-12"),
        RecommendRequest(city="Алматы", category="Банкетный зал", date="2026-11-14",
                         event_format="свадьба", budget_kzt=3000000),
    ]


def contains(value: str, labels: list[str]) -> bool:
    return value in {normalize(label) for label in labels}


def evaluate(catalog: Catalog, request: RecommendRequest) -> dict:
    candidates = [p for p in catalog.profiles if normalize(p.city) == request.city
                  and contains(request.category, p.categories)]
    remaining = list(candidates)
    steps = []
    busy = []
    predicates = (
        ("busy", lambda p: request.date in p.busy_dates),
        ("budget", lambda p: p.price_from_kzt > request.budget_kzt),
        ("format", lambda p: not contains(request.event_format, p.event_formats)),
        ("language", lambda p: request.language is not None and not contains(request.language, p.languages)),
        ("duration", lambda p: request.duration_hours is not None and p.max_hours is not None
         and request.duration_hours > p.max_hours),
    )
    for reason, exclude in predicates:
        rejected: list[Profile] = [p for p in remaining if exclude(p)]
        remaining = [p for p in remaining if not exclude(p)]
        if reason == "busy":
            busy = [{"id": p.id, "date": request.date.isoformat(),
                     "busy_dates": [date.isoformat() for date in p.busy_dates]}
                    for p in sorted(rejected, key=lambda p: p.id)]
        steps.append(dict(reason=reason, excluded_count=len(rejected), remaining_count=len(remaining)))
    ranked = sorted(remaining, key=lambda p: (0, p.price_from_kzt, p.id))
    return {
        "status": "matched" if ranked else ("no_match" if candidates else "category_absent"),
        "total_candidates": len(candidates), "eligible_count": len(ranked),
        "eligible_ids": [p.id for p in ranked], "top_ids": [p.id for p in ranked[:3]],
        "filters": steps, "busy_profiles": busy,
    }


def main() -> None:
    catalog = load_catalog(configured_path("DATA_PATH", DEFAULT_DATA_PATH))
    results = [dict(number=index, request=request.model_dump(mode="json"), **evaluate(catalog, request))
               for index, request in enumerate(demo_requests(), start=1)]
    print(json.dumps({"data_version": catalog.data_version, "mode": "offline_baseline_audit",
                      "scenarios": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
