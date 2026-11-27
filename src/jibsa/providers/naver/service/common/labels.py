"""네이버 코드·동 이름표 함수 (코드 표에 없는 값의 글자, 동 이름 맞추기·표기)."""

import re

from jibsa.providers.naver.service.common.constants import DONG_LETTER_BY_SPELLING


def unknown_code_label(kind: str, code: str) -> str:
    """jibsa 표에 없는 코드를 낼 글자 ('알 수 없는 시설 (XYZ01)').

    값은 응답에 있는데 jibsa 가 못 읽은 것이라, 값이 없다는 뜻의 null 도 코드 글자 그대로도 아니다. 사용자가 이 글자를 보고
    코드를 알려 주면 표에 더할 수 있다.

    Args:
        kind: 무엇의 코드인지 ('값' 하나짜리, '시설' 시설 목록 항목, '항목' 관리비 포함 항목).
        code: 응답의 코드.
    """
    return f'알 수 없는 {kind} ({code})'


def dong_key(name: str) -> str:
    """'104동'·'104 동'·'104' 를 같은 동으로 본다. 'A'·'a'·'에이'·'에이동' 도 같은 동이다."""
    name = name.strip().replace(' ', '')
    name = name[:-1] if name.endswith('동') and len(name) > 1 else name
    return DONG_LETTER_BY_SPELLING.get(name, name.upper())


def dong_label(name: str) -> str:
    """제목·안내에 쓰는 동 표기. '101'·'가'·'A'·'에이' 는 뒤에 '동' 을 붙이고, 건물 이름은 그대로 둔다.

    네이버 동 이름은 '동' 없이 온다 (매물 410건 중 '동' 으로 끝나는 이름 없음). 빌라 단지 일부는 동
    이름 자리에 건물 이름('가람아트빌', '청림빌라1차')이 와서 '동' 을 붙이면 어색하다. 한글이 세 자 넘게
    이어지면 건물 이름으로 본다 (2026-10-09 확인).
    """
    if name in DONG_LETTER_BY_SPELLING or not re.search('[가-힣]{3,}', name):
        return f'{name}동'
    return name
