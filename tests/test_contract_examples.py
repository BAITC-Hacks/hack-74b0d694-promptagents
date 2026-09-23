import json

from backend.app.config import ROOT
from backend.app.models import ErrorResponse, RecommendResponse


def test_labeled_examples_follow_contract():
    examples = json.loads((ROOT / "docs/examples/responses.json").read_text(encoding="utf-8"))
    assert examples["example_only"] is True
    assert {item["status"] for item in examples["recommend"]} == {"matched", "category_absent", "no_match"}
    for item in examples["recommend"]:
        response = RecommendResponse.model_validate(item)
        assert len(response.cards) == min(3, response.eligible_count)
        assert sum(step.excluded_count for step in response.diagnostics.filters) + response.eligible_count == response.total_candidates
    ErrorResponse.model_validate(examples["error"])
