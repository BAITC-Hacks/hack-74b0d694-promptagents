"""Temporary factual baseline until engineer #3 implements explanations.explain."""

from decimal import Decimal

from .models import Evidence, Explanation, PreparedFeature, Profile, RecommendRequest, normalize


def _number(value: int | float) -> str:
    result = format(Decimal(str(value)), ",f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result.replace(",", " ").replace(".", ",")


def explain(
    profile: Profile,
    request: RecommendRequest,
    features: tuple[PreparedFeature, ...] = (),
) -> Explanation:
    event_format = next(v for v in profile.event_formats if normalize(v) == request.event_format)
    facts = [f'В профиле указан формат «{event_format}»']
    fields = ["price_from_kzt", "event_formats", "busy_dates"]
    if request.language is not None:
        language = next(v for v in profile.languages if normalize(v) == request.language)
        facts.append(f'язык «{language}»')
        fields.append("languages")
    if request.duration_hours is not None:
        fields.append("max_hours")
        if profile.max_hours is None:
            facts.append("услуга не привязана к длительности присутствия")
        else:
            facts.append(f"лимит {_number(profile.max_hours)} ч покрывает запрос {_number(request.duration_hours)} ч")
    facts.append(f"дата {request.date.isoformat()} отсутствует в списке занятых дат")
    source = profile.model_dump(mode="json")
    return Explanation(
        text=(f"Цена от {_number(profile.price_from_kzt)} ₸ не превышает бюджет "
              f"{_number(request.budget_kzt)} ₸; итоговую стоимость нужно уточнить. "
              + "; ".join(facts) + "."),
        evidence=[Evidence(source="profile", field=field, value=source[field]) for field in fields],
        mode="baseline",
    )
