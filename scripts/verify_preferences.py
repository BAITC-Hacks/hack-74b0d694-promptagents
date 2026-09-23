"""Two real HTTP requests demonstrating soft wishes without weakening filters."""

import argparse
import json
from time import perf_counter

import httpx

from backend.app.catalog import load_catalog
from backend.app.config import DEFAULT_DATA_PATH, ROOT, configured_path
from backend.app.models import RecommendRequest, RecommendResponse
from scripts.check_demos import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    catalog = load_catalog(configured_path("DATA_PATH", DEFAULT_DATA_PATH))
    requests = json.loads((ROOT / "docs/examples/preference-requests.json").read_text(encoding="utf-8"))
    results = []
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        for payload in requests:
            started = perf_counter()
            response = client.post("/api/recommend", json=payload)
            response.raise_for_status()
            result = RecommendResponse.model_validate(response.json())
            duration_ms = round((perf_counter() - started) * 1000, 2)
            expected = evaluate(catalog, RecommendRequest.model_validate(payload))
            assert result.data_version == catalog.data_version
            assert result.eligible_count == expected["eligible_count"] == 4
            assert [s.model_dump() for s in result.diagnostics.filters] == expected["filters"]
            assert {c.id for c in result.cards} <= set(expected["eligible_ids"])
            assert result.model_dump(mode="json") == client.post("/api/recommend", json=payload).json()
            results.append({"request": payload, "eligible_count": result.eligible_count,
                            "ids": [c.id for c in result.cards], "duration_ms": duration_ms,
                            "explanation": result.cards[0].explanation,
                            "mode": result.preference_mode, "feature_version": result.feature_version})
    assert results[0]["ids"] != results[1]["ids"]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
