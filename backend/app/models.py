"""Общий контракт v1.0.0. Владелец: инженер №1."""

import re
import unicodedata
from datetime import date as Date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from .config import DATE_MAX, DATE_MIN


def normalize(value: str) -> str:
    """NFC, схлопывание пробельных символов, casefold; без транслитерации."""
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def calendar_date(value: object) -> Date:
    if isinstance(value, Date) and not hasattr(value, "hour"):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        parsed = Date.fromisoformat(value)
    else:
        raise ValueError("Дата должна иметь формат YYYY-MM-DD")
    if not DATE_MIN <= parsed <= DATE_MAX:
        raise ValueError("Дата должна быть в диапазоне 2026-09-23 — 2026-12-31")
    return parsed


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


PositiveNumber = Annotated[float, Field(gt=0, strict=True)]
NonEmpty = Annotated[str, Field(min_length=1, strict=True)]
Origin = Literal["source_original", "source_synthetic", "team_synthetic"]
ExplanationMode = Literal["baseline", "prepared"]
Reason = Literal["busy", "budget", "format", "language", "duration"]


class RecommendRequest(Model):
    city: NonEmpty
    date: Date
    event_format: NonEmpty
    category: NonEmpty
    budget_kzt: PositiveNumber
    duration_hours: PositiveNumber | None = None
    language: NonEmpty | None = None

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> Date:
        return calendar_date(value)

    @field_validator("city", "event_format", "category", "language")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        result = normalize(value)
        if not result:
            raise ValueError("Поле не должно быть пустым")
        return result


class Profile(Model):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    id: NonEmpty
    anon_name: NonEmpty
    categories: list[NonEmpty] = Field(min_length=1)
    city: NonEmpty
    price_from_kzt: Annotated[int, Field(gt=0, strict=True)]
    event_formats: list[NonEmpty] = Field(min_length=1)
    languages: list[NonEmpty] = Field(min_length=1)
    max_hours: PositiveNumber | None
    busy_dates: list[Date]
    description: str
    synthetic: bool
    city_imputed: bool
    price_imputed: bool

    @field_validator("busy_dates", mode="before")
    @classmethod
    def validate_dates(cls, value: object) -> list[Date]:
        if not isinstance(value, list):
            raise ValueError("busy_dates должен быть списком")
        dates = [calendar_date(item) for item in value]
        if len(dates) != len(set(dates)):
            raise ValueError("Повторяющиеся busy_dates")
        return dates

    @field_validator("id", "anon_name", "city")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Пустое значение")
        if value != value.strip():
            raise ValueError("Пробелы в начале или конце значения")
        return value

    @field_validator("categories", "event_formats", "languages")
    @classmethod
    def unique_labels(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Пустой элемент списка")
        if len({normalize(value) for value in values}) != len(values):
            raise ValueError("Повторяющиеся значения списка")
        return values


class Evidence(Model):
    source: Literal["profile", "description", "prepared"]
    field: NonEmpty
    value: JsonValue
    quote: str | None = None


class Explanation(Model):
    text: NonEmpty
    evidence: list[Evidence] = Field(min_length=1)
    mode: ExplanationMode


class PreparedFeature(Model):
    kind: Literal["format_specialization", "distinctive_detail"]
    event_format: NonEmpty
    value: NonEmpty
    quote: NonEmpty


class PreparedFeatures(Model):
    schema_version: Literal["1.0.0"]
    dataset_sha256: NonEmpty
    model: NonEmpty
    prompt_version: NonEmpty
    prompt_sha256: NonEmpty
    generated_at: NonEmpty
    profiles: dict[str, list[PreparedFeature]]


class Card(Model):
    id: NonEmpty
    name: NonEmpty
    category: NonEmpty
    city: NonEmpty
    price_from_kzt: PositiveNumber
    explanation: NonEmpty
    evidence: list[Evidence] = Field(min_length=1)
    synthetic: bool
    city_imputed: bool
    price_imputed: bool
    origin: Origin


class AlternativeDate(Model):
    date: Date
    card: Card
    explanation_mode: ExplanationMode
    warnings: list[str] = Field(default_factory=list)

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> Date:
        return calendar_date(value)


class FilterStep(Model):
    reason: Reason
    excluded_count: int = Field(ge=0)
    remaining_count: int = Field(ge=0)


class BusyProfile(Model):
    id: NonEmpty
    name: NonEmpty
    date: Date
    evidence: Evidence


class Diagnostics(Model):
    filters: list[FilterStep] = Field(min_length=5, max_length=5)
    busy_profiles: list[BusyProfile]
    warnings: list[str]


class RecommendResponse(Model):
    status: Literal["matched", "category_absent", "no_match"]
    message: NonEmpty
    normalized_request: RecommendRequest
    total_candidates: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    cards: list[Card] = Field(max_length=3)
    diagnostics: Diagnostics
    explanation_mode: ExplanationMode
    data_version: NonEmpty
    alternative: AlternativeDate | None = None


class DateRange(Model):
    min: Date = DATE_MIN
    max: Date = DATE_MAX


class CityCategories(Model):
    city: str
    categories: list[str]


class OptionsResponse(Model):
    cities: list[str]
    categories: list[str]
    event_formats: list[str]
    languages: list[str]
    categories_by_city: list[CityCategories]
    date_range: DateRange
    data_version: str


class DataIssue(Model):
    line: int | None = None
    id: str | None = None
    field: str | None = None
    message: str


class ErrorDetail(Model):
    code: Literal["validation_error", "dataset_missing", "dataset_invalid", "not_implemented"]
    message: str
    issues: list[DataIssue] = Field(default_factory=list)


class ErrorResponse(Model):
    error: ErrorDetail


class HealthResponse(Model):
    status: Literal["ok", "degraded"]
    contract_version: str
    dataset_status: Literal["ready", "missing", "invalid"]
    profile_count: int
    data_version: str | None
    recommendation_implemented: bool
    issues: list[DataIssue]
