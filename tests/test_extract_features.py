"""Исключительно тестовые ответы через MockTransport, без внешних AI-вызовов."""

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta

import httpx
import pytest

from backend.app.models import PreparedFeatures
from scripts.extract_features import ExtractionError, extract, main, parse_response, read_prompt, save_artifact

MODEL = "test-model-2026-09-23"
QUOTE = "Специализируюсь на проведении корпоративных мероприятий."
FEATURE = {"kind": "format_specialization", "event_format": "корпоратив", "value": "корпоратив", "quote": QUOTE}


@pytest.fixture
def sample(catalog):
    profile = catalog.profiles[0].model_copy(update={"id": "TEST-ONLY", "description": QUOTE,
                                                   "event_formats": ["корпоратив"]})
    return replace(catalog, profiles=(profile,))


def response_body(features=None, **overrides):
    return {"status": "completed", "model": MODEL, "output": [
        {"type": "reasoning"},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps({"features": [FEATURE] if features is None else features})}]}], **overrides}


def test_extract_metadata_and_atomic_artifact_on_mock_transport(sample, tmp_path):
    prompt = read_prompt()
    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer TEST-KEY-NOT-A-SECRET"
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        assert payload["text"]["format"]["schema"]["additionalProperties"] is False
        assert payload["input"][0]["content"] == prompt
        assert json.loads(payload["input"][1]["content"])["description"] == QUOTE
        return httpx.Response(200, json=response_body())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact, rejected = extract(sample, client=client, api_key="TEST-KEY-NOT-A-SECRET", model=MODEL, prompt=prompt)
    assert rejected == 0
    assert artifact.dataset_sha256 == sample.sha256
    assert artifact.prompt_sha256 == hashlib.sha256(prompt.encode()).hexdigest()
    assert artifact.model == f"openai/{MODEL}"
    assert artifact.prompt_version == "features-v1"
    assert datetime.fromisoformat(artifact.generated_at).utcoffset() == timedelta(0)
    path = tmp_path / "test-artifact.json"
    save_artifact(path, artifact)
    assert PreparedFeatures.model_validate_json(path.read_bytes()) == artifact
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_artifact(path, artifact)
    assert path.read_bytes() == before
    save_artifact(path, artifact, overwrite=True)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("overrides", [
    {"status": "incomplete"}, {"status": "failed"}, {"model": "floating-alias"},
    {"output": []}, {"output": None},
    {"output": [{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "test"}]}]},
    {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"features":[],"features":[]}'}]}]},
])
def test_rejects_incomplete_refused_or_malformed_payload(sample, overrides):
    with pytest.raises(ExtractionError):
        parse_response(response_body(**overrides), sample.profiles[0])


@pytest.mark.parametrize("feature", [
    FEATURE | {"quote": "Не существующая цитата"},
    FEATURE | {"event_format": "свадьба", "value": "свадьба"},
    FEATURE | {"kind": "distinctive_detail", "value": "лучший ведущий"},
])
def test_drops_unsupported_features(sample, feature):
    model, features, rejected = parse_response(response_body([feature]), sample.profiles[0])
    assert model == MODEL and features == [] and rejected == 1


def test_deduplicates_and_accepts_empty_output(sample):
    assert len(parse_response(response_body([FEATURE, FEATURE]), sample.profiles[0])[1]) == 1
    assert parse_response(response_body([]), sample.profiles[0])[1:] == ([], 0)


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_http_failures_do_not_leak_provider_body(sample, status):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, text="SECRET_BODY"))) as client:
        with pytest.raises(ExtractionError, match=f"HTTP {status}") as error:
            extract(sample, client=client, api_key="TEST-SECRET", model=MODEL, prompt="test")
        assert "SECRET" not in str(error.value)


def test_timeout_and_model_mismatch(sample):
    def timeout(request):
        raise httpx.ReadTimeout("SECRET", request=request)
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ExtractionError, match="таймаут"):
            extract(sample, client=client, api_key="TEST", model=MODEL, prompt="test")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_body(model="other-2026-09-23")))) as client:
        with pytest.raises(ExtractionError, match="отличается"):
            extract(sample, client=client, api_key="TEST", model=MODEL, prompt="test")


def test_no_key_cli_exits_without_network_or_artifact(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: pytest.fail("Unexpected external API call"))
    target = tmp_path / "must-not-exist.json"
    assert main(["--output", str(target)]) == 2
    assert not target.exists()
    assert "Нет OPENAI_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("kwargs", [{"api_key": ""}, {"model": "alias"}, {"limit": 0}, {"limit": -1}])
def test_invalid_configuration_never_calls_provider(sample, kwargs):
    def forbidden(_):
        pytest.fail("Unexpected external API call")
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(ExtractionError):
            extract(sample, client=client, **(dict(api_key="TEST", model=MODEL, prompt="test") | kwargs))
