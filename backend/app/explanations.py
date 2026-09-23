"""Детерминированные объяснения по полям и консервативно отобранным цитатам.

Никаких I/O, ключей или вызовов модели. Это не универсальный семантический
анализатор: сомнительную цитату пропускаем, а не приписываем ей новый смысл.
"""

import re

from .models import Evidence, Explanation, PreparedFeature, Profile, RecommendRequest, normalize

FORMAT_PATTERNS = {
    "свадьба": r"\b(?:свад\w*|wedding)\b",
    "той": r"\b(?:той|тои|тоя|тоев|тоях|тою)\b",
    "корпоратив": r"\bкорпоратив\w*\b",
    "конференция": r"\bконференц\w*\b",
    "юбилей": r"\bюбиле\w*\b",
    "день рождения": r"\bд(?:ень|ня|ни|ней|нях|ню|нём)\s+рождения\b",
}
UNSAFE_CONTEXT = re.compile(
    r"\b(?:не|нет|ни|без|кроме|никогда|раньше|ранее|перестал\w*|прекрат\w*|"
    r"планир\w*|хочу|хотел\w*|возможно|если|бы|мечта\w*|чуж\w*|"
    r"игнорир\w*|инструкци\w*|system|assistant)\b|[?]"
)
STRUCTURED_CLAIMS = re.compile(
    r"\d|[₸$€]|\b(?:цен\w*|стоим\w*|бюджет\w*|тенге|час\w*|"
    r"длительн\w*|язык\w*|русск\w*|казахск\w*|английск\w*|"
    r"свобод\w*|занят\w*)\b"
)
MARKETING = re.compile(r"\b(?:лучш\w*|идеальн\w*|востребован\w*|незабываем\w*|гарантир\w*|харизм\w*)\b")
CITIES = {"алматы": r"\b(?:алматы|алмате)\b", "астана": r"\bастан\w*\b", "зарубежье": r"\bзарубеж\w*\b"}
DETAILS = {
    "ведущий": r"сценарист|сценари\w*|интерактив\w*|импровизац\w*|юмор|танц\w*|акт[её]р\w*|телевид\w*|специализ\w*",
    "ведущий церемонии": r"церемони\w*|регистрац\w*|подач\w*",
    "флорист": r"флорист\w*|цвет\w*|букет\w*|композици\w*",
    "декоратор": r"декор\w*|оформлен\w*|концепц\w*|фотозон\w*",
    "фотограф": r"съ[её]м\w*|репортаж\w*|портрет\w*|фотограф\w*",
    "видеограф": r"съ[её]м\w*|видео\w*|фильм\w*|монтаж\w*",
    "банкетный зал": r"панорам\w*|террас\w*|парков\w*|кейтеринг\w*|сцен\w*",
    "загородная площадка": r"террас\w*|природ\w*|панорам\w*|парков\w*",
    "ресторан": r"кухн\w*|террас\w*|панорам\w*|кейтеринг\w*",
    "отель": r"зал\w*|оснащен\w*|парков\w*|презентац\w*",
    "инструменталист": r"скрип\w*|саксофон\w*|репертуар\w*|классик\w*|кавер\w*",
    "лайв-бэнд": r"жив\w*|репертуар\w*|кавер\w*|вокал\w*",
    "национальный ансамбль": r"народн\w*|национальн\w*|инструмент\w*|репертуар\w*",
    "танцевальный коллектив": r"хореограф\w*|танц\w*|постанов\w*",
    "шоу-программа": r"свет\w*|шоу\w*|номер\w*|костюм\w*",
    "фото и видеобудки": r"фотобуд\w*|печать|печат\w*|интерактив\w*|зеркал\w*",
    "подарки и сувениры": r"сувенир\w*|гравиров\w*|персонализ\w*|упаков\w*",
}


def _contexts(description: str, quote: str) -> list[str]:
    contexts = []
    start = 0
    while (index := description.find(quote, start)) >= 0:
        left = max(description.rfind(mark, 0, index) for mark in ".!?\n") + 1
        end = index + len(quote)
        ends = [position for mark in ".!?\n" if (position := description.find(mark, end)) >= 0]
        right = end if quote[-1] in ".!?\n" else min(ends) + 1 if ends else len(description)
        contexts.append(normalize(description[left:right]))
        start = index + 1
    return contexts


def _quote_issue(profile: Profile, quote: str, event_format: str, *, prepared: bool) -> str | None:
    if not quote.strip() or quote not in profile.description:
        return "нет точной непустой цитаты"
    contexts = _contexts(profile.description, quote)
    formats = {normalize(value) for value in profile.event_formats}
    if event_format not in formats:
        return "формат отсутствует в структурированных данных"
    for context in contexts:
        if UNSAFE_CONTEXT.search(context) or STRUCTURED_CLAIMS.search(context) or MARKETING.search(context):
            return "небезопасный, рекламный или затрагивающий условия контекст"
        for city, pattern in CITIES.items():
            if re.search(pattern, context) and (prepared or city != normalize(profile.city)):
                return "цитата содержит неподходящее утверждение о городе"
        mentioned = {name for name, pattern in FORMAT_PATTERNS.items() if re.search(pattern, context)}
        if mentioned - formats or (mentioned and event_format not in mentioned):
            return "формат цитаты противоречит полям или не относится к запросу"
    return None


def feature_issue(profile: Profile, feature: PreparedFeature) -> str | None:
    """Дополнительная защита объяснений и экстрактора. Хеш проверяет загрузчик №1."""
    event_format = normalize(feature.event_format)
    if issue := _quote_issue(profile, feature.quote, event_format, prepared=True):
        return issue
    pattern = FORMAT_PATTERNS.get(event_format)
    quote = normalize(feature.quote)
    if pattern is None or not re.search(pattern, quote):
        return "цитата не подтверждает релевантность формату"
    if feature.kind == "format_specialization":
        if normalize(feature.value) != event_format:
            return "value специализации не совпадает с форматом"
        specialization = (r"^(?:(?:я|мы)\s+)?специализ(?:ируюсь|ируемся)\s+на\s+"
                          r"(?:проведении\s+|съ[её]мке\s+|организации\s+|оформлении\s+)?" + pattern)
        wedding_role = r"^(?:я\s+(?:—\s+)?|я\s+являюсь\s+)свадебн\w+\s+(?:профессиональн\w+\s+)?(?:фотограф\w*|видеограф\w*|ведущ\w*)\b"
        texts = [quote, *_contexts(profile.description, feature.quote)]
        if not (all(re.search(specialization, text) for text in texts)
                or (event_format == "свадьба" and all(re.search(wedding_role, text) for text in texts))):
            return "не подтверждена явная специализация самого подрядчика"
    elif not feature.value.strip() or normalize(feature.value) not in quote:
        return "value не подтверждён дословно"
    return None


def _baseline_quote(profile: Profile, request: RecommendRequest) -> str | None:
    detail = DETAILS.get(request.category)
    if not detail:
        return None
    candidates = []
    for match in re.finditer(r"[^.!?\n•]+[.!?]?", profile.description):
        quote = match.group().strip()
        if not 15 <= len(quote) <= 250 or _quote_issue(profile, quote, request.event_format, prepared=False):
            continue
        if re.search(detail, normalize(quote)):
            mentions_format = bool(re.search(FORMAT_PATTERNS.get(request.event_format, r"(?!)"), normalize(quote)))
            candidates.append((not mentions_format, match.start(), quote))
    return min(candidates)[2] if candidates else None


def _number(value: float | int) -> str:
    return f"{value:,.10f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")


def explain(
    profile: Profile,
    request: RecommendRequest,
    features: tuple[PreparedFeature, ...] = (),
) -> Explanation:
    """Вызывается для уже прошедшего фильтры профиля; несоответствие — ошибка кода."""
    if (normalize(profile.city) != request.city or request.category not in {normalize(x) for x in profile.categories}
            or request.event_format not in {normalize(x) for x in profile.event_formats}
            or request.date in profile.busy_dates or profile.price_from_kzt > request.budget_kzt
            or (request.language is not None and request.language not in {normalize(x) for x in profile.languages})
            or (request.duration_hours is not None and profile.max_hours is not None and request.duration_hours > profile.max_hours)):
        raise ValueError("explain() принимает только профиль, прошедший все условия заказа")

    raw = profile.model_dump(mode="json")
    fields = ["city", "categories", "event_formats", "busy_dates", "price_from_kzt"]
    parts = [f"Город — {profile.city}", f"формат «{request.event_format}» указан в каталоге",
             f"дата {request.date.isoformat()} свободна по календарю",
             f"стартовая цена от {_number(profile.price_from_kzt)} ₸ не выше бюджета {_number(request.budget_kzt)} ₸ (итоговая стоимость требует уточнения)"]
    if request.language:
        parts.append(f"язык — {request.language}")
        fields.append("languages")
    if request.duration_hours is not None:
        parts.append("работа не привязана к присутствию на площадке, поэтому длительность не ограничивает подбор"
                     if profile.max_hours is None else f"запрошено {_number(request.duration_hours)} ч при лимите {_number(profile.max_hours)} ч")
        fields.append("max_hours")
    evidence = [Evidence(source="profile", field=field, value=raw[field]) for field in fields]
    supported = sorted((f for f in features if normalize(f.event_format) == request.event_format and feature_issue(profile, f) is None),
                       key=lambda f: (f.kind != "format_specialization", f.quote, f.value))
    # Многофразный AI-фрагмент не превращаем в длинное рекламное объяснение.
    supported = [f for f in supported if len(f.quote) <= 250 and not re.search(r"[.!?]\s+\S", f.quote)]
    quote = supported[0].quote if supported else _baseline_quote(profile, request)
    mode = "prepared" if supported else "baseline"
    text = "; ".join(parts) + "."
    if quote:
        # Пунктуацию вне цитаты не меняем внутри самого evidence.
        text += f" В описании: «{quote.rstrip('.!?')}»."
        evidence.append(Evidence(source="prepared" if supported else "description", field="description", value=profile.description, quote=quote))
    return Explanation(text=text, evidence=evidence, mode=mode)
