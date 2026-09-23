"""Optional offline features. Uncertain text never earns a ranking bonus.

Semantic validation deliberately accepts a narrow set of affirmative Russian
phrases. This is not a general natural-language entailment model: unsupported
paraphrases fall back to structured facts with a warning.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from pydantic import ValidationError

from .catalog import Catalog
from .models import PreparedFeature, PreparedFeatures, Profile, normalize

FORMAT_PATTERNS = {
    "свадьба": r"\b(?:свад\w*|wedding)\b",
    "той": r"\b(?:той|тои|тоя|тоев|тоях|тою)\b",
    "корпоратив": r"\bкорпоратив\w*\b",
    "конференция": r"\bконференц\w*\b",
    "юбилей": r"\bюбиле\w*\b",
    "день рождения": r"\bд(?:ень|ня|ни|ней|нях|ню|нём)\s+рождения\b",
}
UNCERTAIN = re.compile(
    r"\b(?:не|нет|ни|без|кроме|никогда|раньше|ранее|перестал\w*|прекрат\w*|"
    r"планир\w*|хочу|хотел\w*|возможно|если|бы|мечта\w*|чуж\w*)\b|[?]"
)
# Free text must not be used to assert or override these structured conditions.
# Reject such mixed quotes conservatively, even if some clauses might agree.
STRUCTURED_CLAIMS = re.compile(
    r"\d|[₸$€]|\b(?:цен\w*|стоим\w*|бюджет\w*|тенге|час\w*|"
    r"длительн\w*|язык\w*|русск\w*|казахск\w*|английск\w*|"
    r"алматы|алмате|астан\w*|зарубеж\w*|свобод\w*|занят\w*)\b"
)


def _contexts(description: str, quote: str) -> list[str]:
    """Inspect enclosing sentences, so a quote cannot strip a preceding 'не'."""
    contexts = []
    start = 0
    while (index := description.find(quote, start)) >= 0:
        left = max(description.rfind(mark, 0, index) for mark in ".!?\n") + 1
        end = index + len(quote)
        boundaries = [p for mark in ".!?\n" if (p := description.find(mark, end)) >= 0]
        right = end if quote[-1] in ".!?\n" else (min(boundaries) + 1 if boundaries else len(description))
        contexts.append(normalize(description[left:right]))
        start = index + 1
    return contexts


def feature_issue(profile: Profile, feature: PreparedFeature) -> str | None:
    event_format = normalize(feature.event_format)
    allowed = {normalize(v) for v in profile.event_formats}
    if event_format not in allowed:
        return "формат противоречит event_formats"
    if not feature.quote.strip() or feature.quote not in profile.description:
        return "цитата не является точной непустой подстрокой description"
    quote = normalize(feature.quote)
    contexts = _contexts(profile.description, feature.quote)
    if any(UNCERTAIN.search(context) for context in contexts):
        return "контекст цитаты содержит отрицание или неоднозначное утверждение"
    if any(STRUCTURED_CLAIMS.search(context) for context in contexts):
        return "цитата затрагивает структурированные условия; используйте evidence из полей"
    mentioned = {name for name, pattern in FORMAT_PATTERNS.items()
                 if any(re.search(pattern, context) for context in contexts)}
    if mentioned - allowed:
        return "контекст упоминает формат, отсутствующий в event_formats"
    pattern = FORMAT_PATTERNS.get(event_format)
    if pattern is None or not re.search(pattern, quote):
        return "цитата явно не подтверждает релевантность выбранному формату"
    if feature.kind == "format_specialization":
        if normalize(feature.value) != event_format:
            return "value специализации должен совпадать с event_format"
        # A format's name alone (or attending a conference) is not expertise.
        specialization_pattern = (
            r"^(?:(?:я|мы)\s+)?специализ(?:ируюсь|ируемся)\s+на\s+"
            r"(?:проведении\s+|съ[её]мке\s+|организации\s+|оформлении\s+)?" + pattern
        )
        explicit = all(re.search(specialization_pattern, text) for text in [quote, *contexts])
        wedding_pattern = (
            r"^(?:я\s+(?:—\s+)?|я\s+являюсь\s+)свадебн\w+\s+"
            r"(?:профессиональн\w+\s+)?(?:фотограф\w*|видеограф\w*|ведущ\w*)\b"
        )
        wedding_role = event_format == "свадьба" and all(
            re.search(wedding_pattern, text) for text in [quote, *contexts]
        )
        if not (explicit or wedding_role):
            return "цитата не содержит поддерживаемого явного утверждения о специализации"
    elif not feature.value.strip() or normalize(feature.value) not in quote:
        return "distinctive_detail.value должен быть дословно подтверждён цитатой"
    return None


@dataclass(frozen=True)
class FeatureSet:
    dataset_sha256: str | None = None
    profiles: Mapping[str, tuple[PreparedFeature, ...]] = field(default_factory=lambda: MappingProxyType({}))
    warnings: tuple[str, ...] = ()

    @classmethod
    def absent(cls) -> "FeatureSet":
        return cls(warnings=("Подготовленные признаки отсутствуют; используется baseline без AI.",))

    def for_profile(self, catalog: Catalog, profile: Profile, event_format: str) -> tuple[PreparedFeature, ...]:
        if self.dataset_sha256 != catalog.sha256:
            return ()
        return tuple(f for f in self.profiles.get(profile.id, ())
                     if normalize(f.event_format) == event_format and feature_issue(profile, f) is None)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Повтор ключа JSON: {key}")
        result[key] = value
    return result


def load_features(path: Path, catalog: Catalog) -> FeatureSet:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
        artifact = PreparedFeatures.model_validate(raw)
        if artifact.dataset_sha256 != catalog.sha256:
            raise ValueError("SHA-256 датасета не совпадает")
        if artifact.prompt_version != "features-v1":
            raise ValueError("неподдерживаемая версия промпта")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact.prompt_sha256):
            raise ValueError("неверный SHA-256 промпта")
        if not artifact.model.strip():
            raise ValueError("не указана модель подготовки")
        generated = datetime.fromisoformat(artifact.generated_at.replace("Z", "+00:00"))
        if "T" not in artifact.generated_at or generated.utcoffset() != timedelta(0):
            raise ValueError("generated_at должен быть ISO-8601 UTC")
        by_id = {p.id: p for p in catalog.profiles}
        if unknown := sorted(set(artifact.profiles) - set(by_id)):
            raise ValueError(f"неизвестные id: {', '.join(unknown)}")
    except FileNotFoundError:
        return FeatureSet.absent()
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        # Feature failures never make the catalog unavailable.
        detail = "неверная схема артефакта" if isinstance(exc, ValidationError) else str(exc)
        return FeatureSet(warnings=(f"Подготовленные признаки не используются: {detail}; baseline без AI.",))

    valid = {}
    warnings = []
    for profile_id in sorted(artifact.profiles):
        accepted = []
        for feature in artifact.profiles[profile_id]:
            issue = feature_issue(by_id[profile_id], feature)
            if issue:
                warnings.append(f"Признак {profile_id} ({feature.kind}) отброшен: {issue}.")
            elif feature not in accepted:
                accepted.append(feature)
        valid[profile_id] = tuple(accepted)
    return FeatureSet(catalog.sha256, MappingProxyType(valid), tuple(warnings))
