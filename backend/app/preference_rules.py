"""Small public vocabulary: service characteristics, never personality traits.

Each value has its own explicit evidence patterns. Missing evidence is unknown;
the opposite value is never inferred from silence. Bump RULES_VERSION on edits.
"""

RULES_VERSION = "preferences-v1"
HOST = ("ведущий", "ведущий церемонии")
DECOR = ("флорист", "декоратор")
VENUE = ("банкетный зал", "загородная площадка", "ресторан", "отель")


def criterion(label, categories, values):
    return {"label": label, "categories": categories, "values": values}


CRITERIA = {
    "delivery": criterion("Подача", HOST, {
        "calm": ("Спокойная", r"спокойн\w*\s+(?:и\s+\w+\s+)?(?:подач\w*|стил\w*|ведени\w*)"),
        "energetic": ("Энергичная", r"энергичн\w*|динамик\w*|динамичн\w*"),
    }),
    "formality": criterion("Формальность", HOST, {
        "formal": ("Официальная", r"официальн\w*|формальн\w*\s+(?:стил\w*|ведени\w*|подач\w*)"),
        "informal": ("Неформальная", r"неформальн\w*"),
    }),
    "improvisation": criterion("Импровизация", HOST, {
        "yes": ("С импровизацией", r"импровизац\w*|импровизатор\w*"),
        "no": ("Без импровизации", r"без\s+импровизац\w*"),
    }),
    "guest_engagement": criterion("Вовлечение гостей", HOST, {
        "active": ("Активное", r"интерактив\w*|активн\w*\s+(?:вовлеч\w*|взаимодейств\w*)"),
        "unobtrusive": ("Ненавязчивое", r"ненавязчив\w*|без\s+шумн\w*\s+конкурс\w*"),
    }),
    "program_focus": criterion("Акцент программы", HOST, {
        "business": ("Деловые события", r"(?:специализируюсь|специализируемся)\s+на\s+(?:проведении\s+)?делов\w*\s+(?:встреч\w*|событи\w*|мероприяти\w*)"),
        "entertainment": ("Развлечения и танцы", r"только\s+развлечения\s+и\s+танцы"),
    }),
    "photo_style": criterion("Стиль съёмки", ("фотограф",), {
        "reportage": ("Репортаж", r"репортаж\w*|фотожурнализм\w*|документальн\w*\s+съ[её]мк\w*"),
        "posed": ("Постановочная съёмка", r"постановочн\w*\s+(?:съ[её]мк\w*|фотограф\w*)"),
    }),
    "photographer_presence": criterion("Работа фотографа", ("фотограф",), {
        "unobtrusive": ("Незаметная", r"незаметн\w*\s+(?:работ\w*|снима\w*)|(?:работаю|снимаю)\s+незаметно"),
        "active": ("Активное руководство съёмкой", r"активно\s+(?:руковожу|направляю)\s+съ[её]мк\w*"),
    }),
    "decor_style": criterion("Эстетика оформления", DECOR, {
        "minimal": ("Минимализм", r"минимализм\w*|минималистичн\w*"),
        "lush": ("Пышное оформление", r"пышн\w*\s+(?:декор\w*|оформлен\w*|композици\w*)"),
    }),
    "custom_concept": criterion("Концепция", DECOR, {
        "yes": ("Индивидуальная", r"индивидуальн\w*\s+(?:концепци\w*|эскиз\w*)"),
        "no": ("Готовые решения", r"только\s+готовые\s+(?:решения|концепции)"),
    }),
    "terrace": criterion("Терраса", VENUE, {
        "yes": ("Есть терраса", r"террас\w*"), "no": ("Без террасы", r"без\s+террас\w*|террас\w*\s+нет"),
    }),
    "panorama": criterion("Панорамный вид", VENUE, {
        "yes": ("Панорамный вид", r"панорамн\w*\s+(?:вид\w*|окн\w*|локаци\w*)"),
        "no": ("Без панорамного вида", r"без\s+панорамн\w*\s+вид\w*"),
    }),
    "parking": criterion("Парковка", VENUE, {
        "yes": ("Есть парковка", r"парковк\w*"), "no": ("Без парковки", r"без\s+парковк\w*|парковк\w*\s+нет"),
    }),
}

# Free-text vocabulary is deliberately separate from evidence extraction:
# 'хочу спокойного ведущего' expresses a wish, not a contractor's capability.
QUERY_PATTERNS = {
    ("delivery", "calm"): r"спокойн\w*",
    ("delivery", "energetic"): r"энергичн\w*|динамичн\w*",
    ("formality", "formal"): r"официальн\w*|формальн\w*",
    ("formality", "informal"): r"неформальн\w*",
    ("guest_engagement", "active"): r"активн\w*\s+вовлеч\w*|интерактив\w*",
    ("program_focus", "business"): r"делов\w*\s+(?:аудитори\w*|встреч\w*|событи\w*)",
}


def options_for(category: str) -> list[dict]:
    return [{"criterion": key, "label": spec["label"],
             "values": [{"value": v, "label": labels[0]} for v, labels in spec["values"].items()]}
            for key, spec in CRITERIA.items() if category in spec["categories"]]
