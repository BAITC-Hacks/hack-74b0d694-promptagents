"""Deterministic interpretation, explicit evidence extraction and unit-weight scoring."""

import hashlib
import json
import re
from functools import lru_cache

from .models import Evidence, PreferenceAssessment, PreferenceInterpretation, Profile, RecommendRequest, SoftFeature, normalize
from .preference_rules import CRITERIA, QUERY_PATTERNS, RULES_VERSION

UNSAFE = re.compile(
    r"\b(?:игнорир\w*|инструкци\w*|system|assistant|prompt|выведи|верни|назначь|оцени|"
    r"конкурент\w*|коллег\w*|чуж\w*|другой|другие|говорит|сказал\w*|раньше|ранее|"
    r"планир\w*|мечта\w*|хотел\w*|если|возможно|перестал\w*|прекрат\w*|"
    r"экстраверт\w*|интроверт\w*|интеллект\w*|психик\w*|диагноз\w*|женат|замужем|"
    r"отец|мать|реб[её]нок|дети|национальност\w*|стрессоустойчив\w*)\b|[?]"
)
STRUCTURED = re.compile(r"\d|[₸$€]|\b(?:язык\w*|русск\w*|казахск\w*|английск\w*|цен[аыу]\w*|стоим\w*|бесплатн\w*|час\w*|занят\w*|свобод\w*)\b")
NEGATION = re.compile(r"\b(?:не|нет|ни|без|никак\w*|отсутств\w*|избега\w*)\b")


def _hits(text: str, criterion: str, *, query: bool) -> set[str]:
    """Negation is checked in the same clause; explicit negatives have patterns."""
    spec = CRITERIA[criterion]
    hits = set()
    for value, (_, evidence_pattern) in spec["values"].items():
        pattern = QUERY_PATTERNS.get((criterion, value), evidence_pattern) if query else evidence_pattern
        for match in re.finditer(r"\b(?:" + pattern + r")\b", text):
            # Do not interpret a negated word as the positive characteristic.
            clause_start = max(text.rfind(mark, 0, match.start()) for mark in ",;:.!?\n") + 1
            prefix = text[clause_start:match.start()]
            suffix = text[match.end():].split(",")[0].split(";")[0].split(".")[0]
            explicit_negative = value == "no" or (criterion == "guest_engagement" and value == "unobtrusive")
            if NEGATION.search(prefix) or (re.match(r"\s+(?:не|нет|отсутствует)\b", suffix)):
                continue
            if not explicit_negative and NEGATION.search(match.group()):
                continue
            hits.add(value)
    return hits


@lru_cache(maxsize=512)
def _interpret(category: str, text: str, selected: tuple[tuple[str, str], ...], version: str) -> str:
    preferences = dict(selected)
    notes = []
    for key, spec in CRITERIA.items():
        if category not in spec["categories"]:
            continue
        values = _hits(text, key, query=True)
        if len(values) > 1:
            notes.append(f'Пожелание «{spec["label"]}» в тексте неоднозначно; уточните его в форме.')
        elif values:
            value = next(iter(values))
            if key in preferences and preferences[key] != value:
                notes.append(f'Текст расходится с выбором «{spec["label"]}»; применено значение из формы.')
            else:
                preferences[key] = value
    clarification = []
    if re.search(r"\d|[₸$€]|\b(?:бюджет\w*|тенге|дата|завтра|сегодня|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|час\w*|русск\w*|казахск\w*|английск\w*|алматы|астан\w*)\b", text):
        clarification.append("В тексте упомянуты условия заказа: проверьте дату, город, бюджет, язык и длительность в форме; текст их не изменяет.")
    if text:
        notes.append("Применены только распознанные пожелания из фиксированного словаря; остальные формулировки не оцениваются. Проверьте список ниже.")
    signature = json.dumps([version, category, text, selected], ensure_ascii=False, separators=(",", ":"))
    return PreferenceInterpretation(
        preferences=dict(sorted(preferences.items())), clarification_needed=clarification,
        labels={key: f'{CRITERIA[key]["label"]}: {CRITERIA[key]["values"][value][0]}' for key, value in sorted(preferences.items())},
        notes=notes, interpretation_id="sha256:" + hashlib.sha256(signature.encode()).hexdigest(),
        rules_version=version,
    ).model_dump_json()


def interpret(request: RecommendRequest) -> PreferenceInterpretation:
    # Cache stores immutable JSON; callers cannot alter subsequent responses.
    return PreferenceInterpretation.model_validate_json(_interpret(
        request.category, request.preferences_text or "", tuple(sorted(request.preferences.items())), RULES_VERSION,
    ))


@lru_cache(maxsize=2048)
def _extract(description: str, categories: tuple[str, ...], formats: tuple[str, ...], city: str, version: str) -> str:
    from .prepared import FORMAT_PATTERNS
    found = []
    for match in re.finditer(r"[^.!?\n•]+[.!?]?", description):
        quote = match.group().strip()
        text = normalize(quote)
        if not quote or len(quote) > 450 or UNSAFE.search(text) or STRUCTURED.search(text):
            continue
        if any(re.search(pattern, text) and name != city for name, pattern in {
            "алматы": r"\bалмат[ыeе]\b", "астана": r"\bастан\w*\b", "зарубежье": r"\bзарубеж\w*\b",
        }.items()):
            continue
        mentioned = {name for name, pattern in FORMAT_PATTERNS.items() if re.search(pattern, text)}
        if mentioned - set(formats):
            continue
        for key, spec in CRITERIA.items():
            applicable = sorted(set(categories) & set(spec["categories"]))
            if not applicable:
                continue
            for value in sorted(_hits(text, key, query=False)):
                feature = SoftFeature(criterion=key, value=value, evidence_quote=quote,
                                      evidence_type="explicit", applicable_categories=applicable)
                if feature not in found:
                    found.append(feature)
    for key, spec in CRITERIA.items():
        applicable = sorted(set(categories) & set(spec["categories"]))
        if applicable and not any(f.criterion == key for f in found):
            found.append(SoftFeature(criterion=key, value="unknown", evidence_quote=None,
                                     evidence_type="unknown", applicable_categories=applicable))
    return json.dumps([f.model_dump() for f in found], ensure_ascii=False)


def extract_explicit(profile: Profile) -> tuple[SoftFeature, ...]:
    return tuple(SoftFeature.model_validate(f) for f in json.loads(_extract(
        profile.description, tuple(sorted(normalize(c) for c in profile.categories)),
        tuple(sorted(normalize(f) for f in profile.event_formats)), normalize(profile.city), RULES_VERSION,
    )))


def soft_feature_issue(profile: Profile, feature: SoftFeature) -> str | None:
    if feature not in extract_explicit(profile):
        return "признак, категория или полная цитата не подтверждены фиксированными правилами"
    return None


def assess(profile: Profile, preferences: dict[str, str], features: tuple[SoftFeature, ...],
           *, prepared_keys: frozenset[tuple[str, str, str | None]] = frozenset()) -> list[PreferenceAssessment]:
    results = []
    for key, desired in sorted(preferences.items()):
        spec = CRITERIA[key]
        proofs = [f for f in features if f.criterion == key and f.evidence_type == "explicit"]
        values = {f.value for f in proofs}
        # Both styles stated -> no claim that one dominates; do not cherry-pick.
        observed = next(iter(values)) if len(values) == 1 else None
        status = "unknown" if observed is None else "matched" if observed == desired else "conflicting"
        evidence = []
        for f in sorted(proofs, key=lambda f: (f.value, f.evidence_quote or "")):
            item = Evidence(source="prepared" if (f.criterion, f.value, f.evidence_quote) in prepared_keys else "description",
                            field="description", value=profile.description, quote=f.evidence_quote)
            if item not in evidence:
                evidence.append(item)
        results.append(PreferenceAssessment(
            criterion=key, label=spec["label"], requested_value=desired, requested_label=spec["values"][desired][0],
            observed_value=observed, observed_label=spec["values"][observed][0] if observed else None,
            status=status, points={"matched": 1, "conflicting": -1, "unknown": 0}[status], evidence=evidence,
        ))
    return results


def explain_preferences(profile: Profile, request: RecommendRequest, assessments: list[PreferenceAssessment]):
    from .explanations import _number
    from .models import Explanation
    facts = [f"Стартовая цена от {_number(profile.price_from_kzt)} ₸ не выше бюджета (итоговая стоимость требует уточнения)",
             f"дата {request.date.isoformat()} свободна по календарю", f"формат «{request.event_format}» указан"]
    fields = ["price_from_kzt", "busy_dates", "event_formats", "city", "categories"]
    if request.language:
        facts.append(f"язык — {request.language}")
        fields.append("languages")
    if request.duration_hours is not None:
        facts.append("услуга не привязана к присутствию" if profile.max_hours is None else f"лимит {_number(profile.max_hours)} ч покрывает запрос")
        fields.append("max_hours")
    chosen = next((a for a in assessments if a.status == "conflicting"), None)
    chosen = chosen or next((a for a in assessments if a.status == "matched"), None)
    raw = profile.model_dump(mode="json")
    evidence = [Evidence(source="profile", field=f, value=raw[f]) for f in fields]
    for assessment in assessments:
        for proof in assessment.evidence:
            if proof not in evidence:
                evidence.append(proof)
    if chosen:
        # Quote the contractor rather than presenting self-description as verified quality.
        quote = chosen.evidence[0].quote.rstrip(".!?")
        relation = "соответствует пожеланию" if chosen.status == "matched" else "расходится с пожеланием"
        detail = f'В описании указано: «{quote}» — это {relation} «{chosen.label}: {chosen.requested_label}»'
        unknown = [a.label for a in assessments if a.status == "unknown"]
        if unknown:
            detail += "; недостаточно сведений: " + ", ".join(unknown)
    else:
        detail = "Для заданных пожеланий подтверждений недостаточно или описание неоднозначно; отсутствие сведений не считается противоречием"
    return Explanation(text="; ".join(facts) + ". " + detail + ".", evidence=evidence,
                       mode="prepared" if any(e.source == "prepared" for e in evidence) else "baseline")
