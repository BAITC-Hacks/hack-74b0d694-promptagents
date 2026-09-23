"""Pure deterministic matching; no file access, network or relaxation of conditions."""

from collections.abc import Callable
from datetime import timedelta

from . import explanations, temporary_explanations
from .catalog import Catalog
from .config import DATE_MAX, DATE_MIN
from .models import (
    AlternativeDate, BusyProfile, Card, Diagnostics, Evidence, Explanation, FilterStep,
    PreparedFeature, Profile, RecommendRequest, RecommendResponse, normalize,
)
from .prepared import FeatureSet
from .config import RANKING_VERSION
from .models import ScoreBreakdown
from .preferences import assess, explain_preferences, interpret
from .soft_catalog import SoftCatalog, digest, load_soft_catalog

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


def exclusion_predicates(request: RecommendRequest):
    return (
        ("busy", lambda p: request.date in p.busy_dates),
        ("budget", lambda p: p.price_from_kzt > request.budget_kzt),
        ("format", lambda p: not contains(request.event_format, p.event_formats)),
        ("language", lambda p: request.language is not None and not contains(request.language, p.languages)),
        ("duration", lambda p: request.duration_hours is not None and p.max_hours is not None
         and request.duration_hours > p.max_hours),
    )


def rank_profiles(catalog: Catalog, profiles: list[Profile], request: RecommendRequest,
                  features: FeatureSet, soft: SoftCatalog, interpretation):
    # The FeatureSet only exposes features validated against this exact profile
    # and catalog hash, also for direct callers of the pure matcher.
    validated = {p.id: features.for_profile(catalog, p, request.event_format) for p in profiles}
    assessments = {p.id: assess(p, interpretation.preferences, soft.profiles[p.id],
                               prepared_keys=soft.prepared.get(p.id, frozenset())) for p in profiles}
    scores = {p.id: sum(a.points for a in assessments[p.id]) for p in profiles}
    specialization = {p.id: int(any(f.kind == "format_specialization" for f in validated[p.id])) for p in profiles}
    ranked = sorted(profiles, key=lambda p: (
        -scores[p.id], -specialization[p.id],
        p.price_from_kzt, p.id,
    ))
    return ranked, validated, assessments, scores, specialization


def build_cards(
    ranked: list[Profile], validated: dict[str, tuple[PreparedFeature, ...]],
    assessments, scores, specialization, interpretation,
    request: RecommendRequest, explainer: Explainer | None, warnings: list[str], *, limit: int,
) -> tuple[list[Card], str]:
    cards = []
    mode = "baseline"
    for profile in ranked[:limit]:
        explain = explainer if explainer is not None else explanations.explain
        try:
            explanation = (explain_preferences(profile, request, assessments[profile.id])
                           if interpretation.preferences and explainer is None
                           else explain(profile, request, validated[profile.id]))
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
            matched_preferences=[a for a in assessments[profile.id] if a.status == "matched"],
            conflicting_preferences=[a for a in assessments[profile.id] if a.status == "conflicting"],
            unknown_preferences=[a for a in assessments[profile.id] if a.status == "unknown"],
            score_breakdown=ScoreBreakdown(preference_score=scores[profile.id], specialization=specialization[profile.id],
                                           price_from_kzt=profile.price_from_kzt, tie_break_id=profile.id,
                                           criteria=assessments[profile.id], ranking_version=RANKING_VERSION),
        ))
    return cards, mode


def recommend(
    catalog: Catalog,
    request: RecommendRequest,
    features: FeatureSet | None = None,
    *,
    explainer: Explainer | None = None,
    soft_catalog: SoftCatalog | None = None,
) -> RecommendResponse:
    features = features if features is not None else FeatureSet.absent()
    if features.dataset_sha256 is not None and features.dataset_sha256 != catalog.sha256:
        features = FeatureSet(warnings=("SHA-256 подготовленных признаков не совпадает с каталогом; baseline без AI.",))
    warnings = list(catalog.report.get("warnings", ())) + list(features.warnings)
    interpretation = interpret(request)
    soft = soft_catalog if soft_catalog is not None and soft_catalog.dataset_sha256 == catalog.sha256 else load_soft_catalog(catalog)
    warnings.extend(soft.warnings)
    # Include legacy specialization artifacts as well as soft features in the snapshot.
    feature_version = "sha256:" + digest(soft.version + repr(sorted(
        (key, tuple(f.model_dump_json() for f in value)) for key, value in features.profiles.items()
    )))
    candidates = [p for p in catalog.profiles if normalize(p.city) == request.city
                  and contains(request.category, p.categories)]
    remaining = candidates
    steps = []
    busy = []
    predicates = exclusion_predicates(request)
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

    ranked, validated, assessments, scores, specialization = rank_profiles(
        catalog, remaining, request, features, soft, interpretation)
    cards, mode = build_cards(ranked, validated, assessments, scores, specialization,
                              interpretation, request, explainer, warnings, limit=3)
    total, eligible = len(candidates), len(ranked)
    message = result_message(total, eligible, steps)
    if interpretation.preferences and eligible:
        if len({(scores[p.id], specialization[p.id]) for p in ranked}) == 1:
            message += " По пожеланиям и специализации различить варианты недостаточно: порядок определён стартовой ценой и ID."
        else:
            message += " Порядок учитывает только подтверждённые пожелания, затем специализацию, стартовую цену и ID."
    proof_sources = {e.source for rows in assessments.values() for a in rows for e in a.evidence}
    preference_mode = "mixed" if {"prepared", "description"} <= proof_sources else "prepared" if "prepared" in proof_sources else "rules"
    alternative = None
    if total and not eligible:
        # Keep every non-date predicate identical to the original search.
        possible = [p for p in candidates if not any(exclude(p) for _, exclude in predicates[1:])]
        dates = (DATE_MIN + timedelta(days=offset) for offset in range((DATE_MAX - DATE_MIN).days + 1))
        ordered_dates = sorted((day for day in dates if day != request.date),
                               key=lambda day: (abs((day - request.date).days), -day.toordinal()))
        for day in ordered_dates if possible else ():
            available = [p for p in possible if day not in p.busy_dates]
            if not available:
                continue
            alternative_request = request.model_copy(update={"date": day})
            alternative_ranked, alternative_validated, alternative_assessments, alternative_scores, alternative_specialization = rank_profiles(
                catalog, available, alternative_request, features, soft, interpretation)
            alternative_warnings = []
            alternative_cards, alternative_mode = build_cards(
                alternative_ranked, alternative_validated, alternative_assessments,
                alternative_scores, alternative_specialization, interpretation,
                alternative_request, explainer, alternative_warnings, limit=1,
            )
            alternative = AlternativeDate(date=day, card=alternative_cards[0],
                                          explanation_mode=alternative_mode, warnings=alternative_warnings)
            break
    return RecommendResponse(
        status="matched" if eligible else ("no_match" if total else "category_absent"),
        message=message, normalized_request=request,
        total_candidates=total, eligible_count=eligible, cards=cards,
        diagnostics=Diagnostics(filters=steps, busy_profiles=busy, warnings=warnings),
        explanation_mode=mode, data_version=catalog.data_version,
        preference_interpretation=interpretation, preference_mode=preference_mode,
        feature_version=feature_version, ranking_version=RANKING_VERSION,
        alternative=alternative,
    )
