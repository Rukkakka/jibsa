"""직방 글자 다듬기: 빈 글자 → 모름, 학교 이름표, 응답에 온 키 확인, 글자 → 정수."""

from pydantic import BaseModel


def text_or_none(value: str | None) -> str | None:
    """앞뒤 공백을 떼고, 빈 글자는 모름(None). 아파트 상세는 값이 없는 칸을 빈 글자로 준다 (`oldAddress` 등).

    방향 기준(`directionBase`)은 '기준' 을 떼야 해 `apt_item_to_listing` 이 같은 규칙을 따로 적용한다.
    """
    return (value.strip() or None) if value else None


def school_label(name: str | None, *details: str | None) -> str | None:
    if not name:
        return None
    shown = [detail for detail in details if detail]
    return f"{name} ({', '.join(shown)})" if shown else name


def sent_or_none(model: BaseModel, field: str, values: list[str]) -> list[str] | None:
    """응답에 `field` 키가 왔으면 `values`, 키가 빠졌으면 모름(None).

    응답 모델은 빠진 목록을 [] 로 채워서 그대로 내보내면 모름이 '없음' 이 된다 (값이 없을 때: 모름 → null, 비어 있음 → []).
    2026-10-12 실측: 새 주거 상세 18건(원룸·빌라·오피스텔·아파트) 모두 options·subways·manageCost.includes 키가 왔다.
    """
    return values if field in model.model_fields_set else None


def to_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, '') else None
    except ValueError:
        return None
