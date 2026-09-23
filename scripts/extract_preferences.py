"""Optional per-profile LLM preparation; never called by the recommendation API."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import Field

from backend.app.catalog import CatalogError, load_catalog
from backend.app.config import DEFAULT_DATA_PATH, ROOT, configured_path
from backend.app.models import Model, Profile, SoftFeature
from backend.app.preference_rules import CRITERIA, RULES_VERSION
from backend.app.preferences import soft_feature_issue
from backend.app.soft_catalog import SoftArtifact, artifact_name, digest, prompt_text
from .extract_features import API_URL, ExtractionError, save_artifact, unique_object


class FeatureResponse(Model):
    features: list[SoftFeature] = Field(max_length=30)


def response_schema() -> dict:
    schema = FeatureResponse.model_json_schema()
    for node in [schema, *schema.get("$defs", {}).values()]:
        if "properties" in node:
            node["required"] = list(node["properties"])
    return schema


def extract_profile(profile: Profile, dataset_sha256: str, *, client: httpx.Client,
                    api_key: str, model: str) -> SoftArtifact:
    if not api_key.strip() or not re.fullmatch(r"[a-zA-Z0-9_.-]+-\d{4}-\d{2}-\d{2}", model):
        raise ExtractionError("Нужны OPENAI_API_KEY и точный snapshot модели; резервный режим работает без них.")
    prompt = prompt_text()
    # Only service fields. No identifier, name, price or personal metadata for scoring.
    data = {"description": profile.description, "categories": profile.categories,
            "event_formats": profile.event_formats, "vocabulary": {
                key: {"categories": spec["categories"], "values": {v: labels[0] for v, labels in spec["values"].items()}}
                for key, spec in CRITERIA.items()
            }}
    try:
        response = client.post(API_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=30,
                               follow_redirects=False, json={
            "model": model, "store": False, "max_output_tokens": 4096,
            "input": [{"role": "system", "content": prompt},
                      {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
            "text": {"format": {"type": "json_schema", "name": "service_preferences", "strict": True,
                                "schema": response_schema()}},
        })
        if response.status_code != 200:
            raise ExtractionError(f"AI API: HTTP {response.status_code}; используются локальные правила.")
        payload = json.loads(response.content, object_pairs_hook=unique_object)
        if not isinstance(payload, dict) or payload.get("status") != "completed" or payload.get("model") != model:
            raise ValueError("incomplete or wrong model")
        texts = []
        for output in payload["output"]:
            if output["type"] != "message":
                continue
            if output.get("role") != "assistant":
                raise ValueError("unexpected role")
            for content in output["content"]:
                if content["type"] != "output_text":
                    raise ValueError("refusal")
                texts.append(content["text"])
        parsed = FeatureResponse.model_validate(json.loads("".join(texts), object_pairs_hook=unique_object))
    except httpx.HTTPError as exc:
        raise ExtractionError("AI API недоступен или истёк таймаут; используются локальные правила.") from exc
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ExtractionError("Ответ AI не прошёл проверку; используются локальные правила.") from exc
    accepted = []
    for feature in parsed.features:
        if soft_feature_issue(profile, feature) is None and feature not in accepted:
            accepted.append(feature)
    return SoftArtifact(schema_version="1.0.0", rules_version=RULES_VERSION,
                        dataset_sha256=dataset_sha256, profile_id=profile.id,
                        description_sha256=digest(profile.description), model="openai/" + model,
                        prompt_version=RULES_VERSION, prompt_sha256=digest(prompt),
                        generated_at=datetime.now(timezone.utc).isoformat(), features=accepted)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/derived/preferences")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise ExtractionError("Нет OPENAI_API_KEY; используются правила, AI-файлы не созданы.")
        if args.limit is not None and args.limit <= 0:
            raise ExtractionError("--limit должен быть положительным")
        directory = args.output_dir.resolve()
        if not directory.is_relative_to((ROOT / "data/derived").resolve()):
            raise ExtractionError("AI-артефакты должны находиться внутри data/derived/.")
        catalog = load_catalog(configured_path("DATA_PATH", DEFAULT_DATA_PATH))
        with httpx.Client() as client:
            for profile in catalog.profiles[:args.limit]:
                target = directory / artifact_name(profile.id)
                if target.exists() and not args.overwrite:
                    print(f"{profile.id}: файл сохранён ранее; пропущен", flush=True)
                    continue
                artifact = extract_profile(profile, catalog.sha256, client=client,
                                           api_key=os.environ["OPENAI_API_KEY"], model=args.model)
                save_artifact(target, artifact, overwrite=args.overwrite)
                print(f"{profile.id}: сохранено проверенных признаков {len(artifact.features)}", flush=True)
        return 0
    except (ExtractionError, CatalogError, OSError) as exc:
        print(str(exc) if isinstance(exc, ExtractionError) else "Ошибка каталога или записи; используются правила.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
