"""Шесть реальных HTTP-запросов к запущенному baseline API, не mock и не браузерный E2E."""

import argparse
import json
import time

import httpx

from backend.app.catalog import load_catalog
from backend.app.config import DEFAULT_DATA_PATH, configured_path
from backend.app.models import RecommendResponse
from scripts.check_demos import demo_requests, evaluate


def verify(base_url: str) -> list[dict]:
    catalog = load_catalog(configured_path("DATA_PATH", DEFAULT_DATA_PATH))
    by_id = {p.id: p for p in catalog.profiles}
    results = []
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        if health.json().get("recommendation_implemented") is not True:
            raise ValueError("API сообщает, что подбор ещё не реализован")
        for number, request in enumerate(demo_requests(), 1):
            started = time.perf_counter()
            response = client.post("/api/recommend", json=request.model_dump(mode="json"))
            elapsed = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            result = RecommendResponse.model_validate(response.json())
            audit = evaluate(catalog, request)
            if result.explanation_mode != "baseline":
                raise ValueError("Для проверки baseline-порядка запустите API без derived-файла")
            actual = (result.status, result.total_candidates, result.eligible_count, [c.id for c in result.cards])
            expected = (audit["status"], audit["total_candidates"], audit["eligible_count"], audit["top_ids"])
            if actual != expected or result.data_version != catalog.data_version or result.normalized_request != request:
                raise ValueError(f"Сценарий {number}: результат не совпадает с независимым аудитом")
            if [s.model_dump() for s in result.diagnostics.filters] != audit["filters"]:
                raise ValueError(f"Сценарий {number}: неверная диагностика")
            for card in result.cards:
                profile = by_id[card.id]
                if not card.explanation or not card.evidence:
                    raise ValueError("Нет объяснения или evidence")
                for evidence in card.evidence:
                    if evidence.value != profile.model_dump(mode="json").get(evidence.field):
                        raise ValueError("Evidence не совпадает с исходным полем")
                    if evidence.source != "profile" and (not evidence.quote or evidence.quote not in profile.description):
                        raise ValueError("Цитата не подтверждена описанием")
            busy = [{"id": p.id, "date": p.date.isoformat(), "busy_dates": p.evidence.value}
                    for p in result.diagnostics.busy_profiles]
            if busy != audit["busy_profiles"]:
                raise ValueError("Календарные доказательства не совпадают с CSV")
            results.append(dict(number=number, http_status=response.status_code, status=result.status,
                                eligible_count=result.eligible_count, top_ids=[c.id for c in result.cards],
                                elapsed_ms=round(elapsed, 2), explanation_mode=result.explanation_mode))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    print(json.dumps({"mode": "real_http_baseline", "scenarios": verify(args.base_url)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
