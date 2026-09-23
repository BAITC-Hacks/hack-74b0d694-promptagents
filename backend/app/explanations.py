"""Интерфейс инженера №3. Реализация объяснений пока отсутствует."""

from .models import Explanation, PreparedFeature, Profile, RecommendRequest


def explain(
    profile: Profile,
    request: RecommendRequest,
    features: tuple[PreparedFeature, ...] = (),
) -> Explanation:
    """1–2 предложения + evidence. Только проверенные features; без сетевых вызовов.

    Пустые features -> baseline. Prepared допустим только при использовании
    проверенного признака. Проверку хеша датасета выполняет вызывающая сторона.
    """
    raise NotImplementedError("Объяснения реализует инженер №3")
