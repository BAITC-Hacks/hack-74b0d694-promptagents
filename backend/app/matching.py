"""Pure deterministic matching; no file access, network or relaxation of conditions."""

from collections.abc import Callable

from . import explanations, temporary_explanations
from .catalog import Catalog
from .models import (
    BusyProfile, Card, Diagnostics, Evidence, Explanation, FilterStep,
    PreparedFeature, Profile, RecommendRequest, RecommendResponse, normalize,
)
from .prepared import FeatureSet

Explainer = Callable[[Profile, RecommendRequest, tuple[PreparedFeature, ...]], Explanation]
TEMPORARY_WARNING = "Модуль объяснений №3 ещё не готов: используется временное фактическое объяснение (baseline)."
REASON_LABELS = {
    "busy": "заняты на выбранную дату",
    "budget": "стартовая цена выше бюджета",
    "format": "не указан нужный формат",
    "language": "не указан нужный язык",
    "duration": "превышен лимит длительности",
}


def contains(value: str, labels: list[str]) -> bool:
    return any(normalize(label) == value for label in labels)


def result_message(total: int, eligible: int, steps: list[FilterStep]) -> str:
    if not total:
        return "В выбранном городе нет подрядчиков этой категории в каталоге."
    reasons = "; ".join(
        f"{REASON_LABELS[step.reason]}: {step.excluded_count}"
        for step in steps if step.excluded_count
    )
    if not eligible:
        return f"Кандидатов этой категории в городе: {total}; никто не прошёл все условия: {reasons}."
    message = f"Подходящих подрядчиков: {eligible} из {total}; показано {min(3, eligible)}."
    if eligible < 3:
        if total < 3:
            message += f" Каталог города для этой категории небольшой: всего {total}."
        else:
            message += " Карточек меньше трёх из-за исключений по условиям заказа."
    if reasons:
        message += f" Исключены последовательно: {reasons}."
    if eligible > 3:
        message += f" Подходящих за пределами первой тройки: {eligible - 3}."
    return message


def recommend(
    catalog: Catalog,
    request: RecommendRequest,
    features: FeatureSet | None = None,
    *,
    explainer: Explainer | None = None,
) -> RecommendResponse:
    features = features if features is not None else FeatureSet.absent()
    if features.dataset_sha256 is not None and features.dataset_sha256 != catalog.sha256:
        features = FeatureSet(warnings=("SHA-256 подготовленных признаков не совпадает с каталогом; baseline без AI.",))
    warnings = list(catalog.report.get("warnings", ())) + list(features.warnings)
    candidates = [p for p in catalog.profiles if normalize(p.city) == request.city
                  and contains(request.category, p.categories)]
    remaining = candidates
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
        accepted, rejected = [], []
        for profile in remaining:
            (rejected if exclude(profile) else accepted).append(profile)
        remaining = accepted
        steps.append(FilterStep(reason=reason, excluded_count=len(rejected), remaining_count=len(remaining)))
        if reason == "busy":
            busy = [BusyProfile(
                id=p.id, name=p.anon_name, date=request.date,
                evidence=Evidence(source="profile", field="busy_dates",
                                  value=p.model_dump(mode="json")["busy_dates"]),
            ) for p in sorted(rejected, key=lambda p: p.id)]

    # The FeatureSet only exposes features validated against this exact profile
    # and catalog hash, also for direct callers of the pure matcher.
    validated = {p.id: features.for_profile(catalog, p, request.event_format) for p in remaining}
    ranked = sorted(remaining, key=lambda p: (
        -int(any(f.kind == "format_specialization" for f in validated[p.id])),
        p.price_from_kzt, p.id,
    ))
    cards = []
    mode = "baseline"
    for profile in ranked[:3]:
        explain = explainer if explainer is not None else explanations.explain
        try:
            explanation = explain(profile, request, validated[profile.id])
        except NotImplementedError:
            if explainer is not None:
                raise
            explanation = temporary_explanations.explain(profile, request)
            if TEMPORARY_WARNING not in warnings:
                warnings.append(TEMPORARY_WARNING)
        if explanation.mode == "prepared":
            mode = "prepared"
        cards.append(Card(
            id=profile.id, name=profile.anon_name,
            category=next(v for v in profile.categories if normalize(v) == request.category),
            city=profile.city, price_from_kzt=profile.price_from_kzt,
            explanation=explanation.text, evidence=explanation.evidence,
            synthetic=profile.synthetic, city_imputed=profile.city_imputed,
            price_imputed=profile.price_imputed,
            origin="source_synthetic" if profile.synthetic else "source_original",
        ))
    total, eligible = len(candidates), len(ranked)
    return RecommendResponse(
        status="matched" if eligible else ("no_match" if total else "category_absent"),
        message=result_message(total, eligible, steps), normalized_request=request,
        total_candidates=total, eligible_count=eligible, cards=cards,
        diagnostics=Diagnostics(filters=steps, busy_profiles=busy, warnings=warnings),
        explanation_mode=mode, data_version=catalog.data_version,
    )
