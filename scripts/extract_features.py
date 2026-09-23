"""Необязательная offline-подготовка через OpenAI Responses API; не импортируется HTTP API."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.catalog import Catalog, CatalogError, load_catalog
from backend.app.config import DEFAULT_DATA_PATH, ROOT, configured_path
from backend.app.explanations import feature_issue
from backend.app.models import PreparedFeature, PreparedFeatures, Profile

PROMPT_PATH = Path(__file__).with_name("prompts") / "features-v1.txt"
PROMPT_VERSION = "features-v1"
API_URL = "https://api.openai.com/v1/responses"


class ExtractionError(Exception):
    """Безопасное сообщение: никогда не включает ключ, заголовки или ответ провайдера."""


class FeatureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    features: list[PreparedFeature] = Field(max_length=8)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Повтор ключа JSON")
        result[key] = value
    return result


def read_prompt() -> str:
    # Хеш текста, действительно отправленного API; одинаков на Windows и Linux.
    return PROMPT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def parse_response(payload: object, profile: Profile) -> tuple[str, list[PreparedFeature], int]:
    try:
        if not isinstance(payload, dict) or payload.get("status") != "completed":
            raise ValueError("incomplete")
        model = payload["model"]
        # Требуем snapshot, чтобы артефакт не записывал плавающий alias как точную версию.
        if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+-\d{4}-\d{2}-\d{2}", model):
            raise ValueError("model snapshot missing")
        chunks = []
        for output in payload["output"]:
            if output["type"] != "message":
                continue  # Например, служебный reasoning item — не JSON результата.
            if output.get("role") != "assistant":
                raise ValueError("unexpected role")
            for content in output["content"]:
                if content["type"] != "output_text":
                    raise ValueError("refusal or unknown content")
                chunks.append(content["text"])
        parsed = FeatureResponse.model_validate(json.loads("".join(chunks), object_pairs_hook=unique_object))
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ExtractionError("Незавершённый, отклонённый или невалидный ответ модели; артефакт не сохранён.") from exc
    accepted = []
    rejected = 0
    for feature in parsed.features:
        issue = feature_issue(profile, feature)
        if issue or len(feature.quote) > 250 or re.search(r"[.!?]\s+\S", feature.quote):
            rejected += 1
        elif feature not in accepted:
            accepted.append(feature)
    return model, accepted, rejected


def extract(catalog: Catalog, *, client: httpx.Client, api_key: str, model: str,
            prompt: str, limit: int | None = None) -> tuple[PreparedFeatures, int]:
    if not api_key.strip():
        raise ExtractionError("Нет OPENAI_API_KEY; baseline работает без ключа. Артефакт не создан.")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+-\d{4}-\d{2}-\d{2}", model):
        raise ExtractionError("Укажите точный snapshot модели с суффиксом YYYY-MM-DD через --model или OPENAI_MODEL.")
    if limit is not None and limit <= 0:
        raise ExtractionError("--limit должен быть положительным")
    profiles = {}
    actual_model = None
    rejected = 0
    for profile in catalog.profiles[:limit]:
        # Отправляем один анонимизированный профиль; идентификатор результата задаёт код.
        # Не отправляем весь каталог, файлы окружения, ключи или историю запросов.
        payload = {
            "model": model, "store": False, "max_output_tokens": 4096,
            "input": [{"role": "system", "content": prompt},
                      {"role": "user", "content": profile.model_dump_json()}],
            "text": {"format": {"type": "json_schema", "name": "profile_features", "strict": True,
                                "schema": FeatureResponse.model_json_schema()}},
        }
        try:
            response = client.post(API_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload,
                                   timeout=60, follow_redirects=False)
            if response.status_code != 200:
                raise ExtractionError(f"AI API вернул HTTP {response.status_code}; артефакт не сохранён.")
            raw = json.loads(response.content, object_pairs_hook=unique_object)
        except httpx.HTTPError as exc:
            raise ExtractionError("AI API недоступен или истёк таймаут; артефакт не сохранён.") from exc
        except (ValueError, RecursionError) as exc:
            raise ExtractionError("AI API вернул невалидный JSON; артефакт не сохранён.") from exc
        returned_model, features, count = parse_response(raw, profile)
        if returned_model != model or (actual_model is not None and actual_model != returned_model):
            raise ExtractionError("Версия модели в ответе отличается от запрошенной; артефакт не сохранён.")
        actual_model = returned_model
        profiles[profile.id] = features
        rejected += count
    if actual_model is None:
        raise ExtractionError("Нет обработанных профилей; артефакт не создан.")
    return PreparedFeatures(schema_version="1.0.0", dataset_sha256=catalog.sha256,
                            model=f"openai/{actual_model}", prompt_version=PROMPT_VERSION,
                            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                            generated_at=datetime.now(timezone.utc).isoformat(), profiles=profiles), rejected


def save_artifact(path: Path, artifact: PreparedFeatures, *, overwrite: bool = False) -> None:
    """Атомарная публикация только после полного успешного прохода."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(artifact.model_dump_json(indent=2) + "\n")
        if overwrite:
            os.replace(temporary, path)
        else:
            # Не перезаписывает файл даже при гонке с другим процессом.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=configured_path("DATA_PATH", DEFAULT_DATA_PATH))
    parser.add_argument("--output", type=Path, default=ROOT / "data/derived/features.json")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""))
    parser.add_argument("--limit", type=int, help="Ограничить число профилей для пробного платного запуска")
    parser.add_argument("--overwrite", action="store_true", help="Явно разрешить замену готового артефакта")
    args = parser.parse_args(argv)
    try:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise ExtractionError("Нет OPENAI_API_KEY; baseline работает без ключа. Артефакт не создан.")
        output = args.output.resolve()
        if not output.is_relative_to((ROOT / "data/derived").resolve()) or output.suffix != ".json":
            raise ExtractionError("Результат должен быть JSON-файлом внутри data/derived/.")
        if output.exists() and not args.overwrite:
            raise ExtractionError("Файл уже существует; для замены явно передайте --overwrite.")
        catalog = load_catalog(args.data)
        with httpx.Client() as client:
            artifact, rejected = extract(catalog, client=client, api_key=os.environ["OPENAI_API_KEY"],
                                         model=args.model, prompt=read_prompt(), limit=args.limit)
        save_artifact(output, artifact, overwrite=args.overwrite)
        print(f"Сохранено профилей: {len(artifact.profiles)}; признаков: {sum(map(len, artifact.profiles.values()))}; "
              f"отброшено: {rejected}; модель: {artifact.model}; файл: {output}")
        return 0
    except (ExtractionError, CatalogError, OSError, ValidationError) as exc:
        # Не печатаем потенциально чувствительные тела ошибок транспорта/валидации.
        print(str(exc) if isinstance(exc, ExtractionError) else "Ошибка данных или записи; артефакт не опубликован.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
