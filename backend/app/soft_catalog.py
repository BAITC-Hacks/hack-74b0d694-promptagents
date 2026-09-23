"""Load per-profile offline artifacts once; always retain the explicit-rule fallback."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from .catalog import Catalog
from .config import ROOT
from .models import Model, NonEmpty, SoftFeature
from .preference_rules import RULES_VERSION
from .preferences import extract_explicit, soft_feature_issue
from .prepared import _unique_object

PROMPT_PATH = ROOT / "scripts/prompts/preferences-v1.txt"


def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def artifact_name(profile_id: str) -> str:
    return digest(profile_id) + ".json"


class SoftArtifact(Model):
    schema_version: Literal["1.0.0"]
    rules_version: Literal["preferences-v1"]
    dataset_sha256: NonEmpty
    profile_id: NonEmpty
    description_sha256: NonEmpty
    model: NonEmpty
    prompt_version: Literal["preferences-v1"]
    prompt_sha256: NonEmpty
    generated_at: NonEmpty
    features: list[SoftFeature]


@dataclass(frozen=True)
class SoftCatalog:
    dataset_sha256: str
    profiles: dict[str, tuple[SoftFeature, ...]]
    prepared: dict[str, frozenset[tuple[str, str, str | None]]]
    version: str
    warnings: tuple[str, ...] = ()


def load_soft_catalog(catalog: Catalog, directory: Path | None = None) -> SoftCatalog:
    profiles = {p.id: extract_explicit(p) for p in catalog.profiles}
    prepared = {}
    warnings = []
    artifact_hashes = []
    if directory is not None and directory.exists():
        try:
            expected_prompt = digest(prompt_text())
        except OSError:
            expected_prompt = None
        for profile in catalog.profiles:
            path = directory / artifact_name(profile.id)
            try:
                raw = path.read_text(encoding="utf-8")
                artifact = SoftArtifact.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
                if (artifact.dataset_sha256 != catalog.sha256 or artifact.profile_id != profile.id
                        or artifact.description_sha256 != digest(profile.description)
                        or artifact.prompt_sha256 != expected_prompt):
                    raise ValueError("не совпадают версии данных, профиля или промпта")
                if not re.fullmatch(r"openai/[a-zA-Z0-9_.-]+-\d{4}-\d{2}-\d{2}", artifact.model):
                    raise ValueError("нет точной версии модели")
                generated = datetime.fromisoformat(artifact.generated_at.replace("Z", "+00:00"))
                if "T" not in artifact.generated_at or generated.utcoffset() != timedelta(0):
                    raise ValueError("неверное UTC-время")
                accepted = set()
                for feature in artifact.features:
                    if soft_feature_issue(profile, feature):
                        warnings.append(f"AI-признак {profile.id}/{feature.criterion} не подтверждён; используются правила.")
                    elif feature.evidence_type == "explicit":
                        accepted.add((feature.criterion, feature.value, feature.evidence_quote))
                prepared[profile.id] = frozenset(accepted)
                artifact_hashes.append((profile.id, digest(raw)))
            except FileNotFoundError:
                continue
            except (OSError, UnicodeError, ValueError, RecursionError):
                warnings.append(f"Артефакт пожеланий {profile.id} отсутствует, устарел или невалиден; используются правила.")
    signature = json.dumps([catalog.sha256, RULES_VERSION, sorted(artifact_hashes)], ensure_ascii=False)
    return SoftCatalog(catalog.sha256, profiles, prepared, "sha256:" + digest(signature), tuple(warnings))
