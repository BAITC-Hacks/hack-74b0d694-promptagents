"""CSV загружается целиком при старте; частичная выдача при ошибках запрещена."""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .models import (
    CityCategories, DataIssue, DateRange, OptionsResponse, Profile, normalize,
)

CITIES = {"алматы", "астана", "зарубежье"}
FORMATS = {"свадьба", "той", "корпоратив", "конференция", "юбилей", "день рождения"}
LANGUAGES = {"русский", "казахский", "английский"}
# Список категорий из сохранённого HTML-превью, не придуманный каталог.
CATEGORIES = {normalize(value) for value in (
    "Банкетный зал", "Ведущий", "Ведущий церемонии", "Видеограф", "Декоратор",
    "Загородная площадка", "Инструменталист", "Лайв-бэнд", "Национальный ансамбль",
    "Отель", "Подарки и сувениры", "Ресторан", "Танцевальный коллектив",
    "Флорист", "Фото и видеобудки", "Фотограф", "Шоу-программа",
)}


class CatalogError(Exception):
    def __init__(self, code: str, issues: list[DataIssue]):
        self.code = code
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


@dataclass(frozen=True)
class Catalog:
    profiles: tuple[Profile, ...]
    sha256: str
    report: dict

    @property
    def data_version(self) -> str:
        return f"sha256:{self.sha256}"


def load_catalog(path: Path) -> Catalog:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise CatalogError("dataset_missing", [DataIssue(
            message="CSV-датасет отсутствует. Добавьте исходный CSV в корень или настройте DATA_PATH.",
        )]) from exc
    except OSError as exc:
        raise CatalogError("dataset_invalid", [DataIssue(message=f"Не удалось прочитать датасет: {exc}")]) from exc
    issues: list[DataIssue] = []
    profiles: list[Profile] = []
    seen: set[str] = set()
    records = []
    try:
        # Parse exactly the bytes used for data_version, even if the file changes
        # between reads. Preserve newlines inside description.
        with io.StringIO(raw.decode("utf-8-sig"), newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            header = reader.fieldnames or []
            expected = set(Profile.model_fields)
            if len(header) != len(set(header)) or set(header) != expected:
                raise CatalogError("dataset_invalid", [DataIssue(line=1, message=(
                    f"Неверные заголовки CSV. Отсутствуют: {sorted(expected - set(header))}; "
                    f"лишние: {sorted(set(header) - expected)}; дубликаты: {len(header) != len(set(header))}"
                ))])
            for row in reader:
                # Для многострочного description указываем последнюю физическую строку записи.
                records.append((reader.line_num, row))
    except (UnicodeError, OSError, csv.Error) as exc:
        raise CatalogError("dataset_invalid", [DataIssue(message=f"Ошибка чтения CSV: {exc}")]) from exc

    for number, row in records:
        profile_id = None
        try:
            profile_id = row.get("id")
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Число ячеек не соответствует заголовку")
            record = dict(row)
            for field in ("categories", "event_formats", "languages", "busy_dates"):
                record[field] = row[field].split("|") if row[field] else []
            for field in ("synthetic", "city_imputed", "price_imputed"):
                if row[field] not in ("True", "False"):
                    raise ValueError(f"{field}: ожидалось True или False, получено {row[field]!r}")
                record[field] = row[field] == "True"
            if not re.fullmatch(r"[0-9]+", row["price_from_kzt"]):
                raise ValueError("price_from_kzt: ожидалось целое число")
            record["price_from_kzt"] = int(row["price_from_kzt"])
            record["max_hours"] = float(row["max_hours"]) if row["max_hours"] else None
            profile = Profile.model_validate(record)
        except ValidationError as exc:
            issues.extend(DataIssue(
                line=number, id=profile_id,
                field=".".join(map(str, error["loc"])), message=error["msg"],
            ) for error in exc.errors())
            continue
        except ValueError as exc:
            issues.append(DataIssue(line=number, id=profile_id, message=str(exc)))
            continue
        if profile.id in seen:
            issues.append(DataIssue(line=number, id=profile.id, field="id", message="Повторяющийся id"))
        seen.add(profile.id)
        for field, values, allowed in (
            ("city", [profile.city], CITIES),
            ("categories", profile.categories, CATEGORIES),
            ("event_formats", profile.event_formats, FORMATS),
            ("languages", profile.languages, LANGUAGES),
        ):
            unknown = [value for value in values if normalize(value) not in allowed]
            if unknown:
                issues.append(DataIssue(line=number, id=profile.id, field=field,
                                        message=f"Неизвестные значения: {unknown}"))
        profiles.append(profile)
    if not records:
        issues.append(DataIssue(message="CSV-каталог пуст"))
    if issues:
        raise CatalogError("dataset_invalid", issues)

    report = {
        "record_count": len(profiles), "unique_ids": len(seen),
        "values": {
            "cities": dict(Counter(profile.city for profile in profiles)),
            **{field: dict(Counter(value for profile in profiles for value in getattr(profile, field)))
               for field in ("categories", "event_formats", "languages")},
        },
        "flags": {field: {"true": sum(getattr(p, field) for p in profiles),
                          "false": sum(not getattr(p, field) for p in profiles)}
                  for field in ("synthetic", "city_imputed", "price_imputed")},
        "null_max_hours": sum(p.max_hours is None for p in profiles),
        "multiple_categories": sum(len(p.categories) > 1 for p in profiles),
        "empty_descriptions": sum(not p.description.strip() for p in profiles),
        "warnings": [] if len(profiles) == 66 else [f"Ожидалось 66 записей по заданию, найдено {len(profiles)}"],
    }
    return Catalog(tuple(profiles), hashlib.sha256(raw).hexdigest(), report)


def labels(values: list[str]) -> list[str]:
    """Один исходный label на нормализованный ключ, независимо от порядка строк."""
    selected = {}
    for value in sorted(set(values)):
        selected.setdefault(normalize(value), value)
    return sorted(selected.values(), key=lambda value: (normalize(value), value))


def options(catalog: Catalog) -> OptionsResponse:
    profiles = catalog.profiles
    cities = labels([profile.city for profile in profiles])
    return OptionsResponse(
        cities=cities,
        categories=labels([value for p in profiles for value in p.categories]),
        event_formats=labels([value for p in profiles for value in p.event_formats]),
        languages=labels([value for p in profiles for value in p.languages]),
        categories_by_city=[CityCategories(city=city, categories=labels([
            value for p in profiles if normalize(p.city) == normalize(city) for value in p.categories
        ])) for city in cities],
        date_range=DateRange(), data_version=catalog.data_version,
    )
