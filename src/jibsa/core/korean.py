import re


# 행정동이 법정동 이름 뒤에 붙이는 번호 ('역삼1동' 의 1, '화곡제1동' 의 제1, '상계3.4동' 의 3.4, '중계2·3동' 의 2·3).
# 번호는 한두 자리다 (상계10동). 세 자리부터는 건물 동 번호라(래미안101동, 2026-10-11 실측: 직방 검색 0건에 행정동 힌트가
# 나갔다) 받지 않는다. 당근 주변 동 고르기(`_dong_stem`)도 같은 규칙을 쓴다
ADMIN_DONG_NUMBER: str = r'제?\d{1,2}(?:[.·]\d{1,2})*'
# 이름 부분은 한글만 받는다. 숫자가 섞이면 '○가' 법정동(성수1가1동 → 성수동1가)이나 띄어 쓴 건물 동 번호(래미안 101동)라
# 번호를 떼도 법정동이 아니다. '○가동'(금호2·3가동)은 '가' 로 끝나 맞지 않는다
ADMIN_DONG_PATTERN: re.Pattern[str] = re.compile(rf'([가-힣]+?){ADMIN_DONG_NUMBER}동')


def particle(word: str, pair: str) -> str:
    """`word` 뒤에 붙일 조사를 받침에 맞춰 고른다.

    지역·역·단지 이름처럼 끝 글자가 바뀌는 한글 이름에 쓴다 ('가락동' 과, '강남구' 와). 숫자·ID·옵션 값은
    읽는 법에 따라 받침이 달라(1 → 일, 2 → 이) 고를 수 없으니, 조사가 필요 없게 문장을 바꾼다
    ('허용되지 않는 값입니다: ...').

    Args:
        word: 조사를 붙일 말.
        pair: 받침이 있을 때/없을 때 조사 ('은/는', '이/가', '을/를', '과/와'). '으로/로' 는 ㄹ 받침 예외가 있어
            받지 않는다.

    Returns:
        고른 조사. 한글로 끝나지 않으면 받침을 몰라 '은(는)' 처럼 둘 다 쓴다.
    """
    with_final, without_final = pair.split('/')
    last = word[-1:]
    if not ('가' <= last <= '힣'):
        return f'{with_final}({without_final})'
    return with_final if (ord(last) - ord('가')) % 28 else without_final


def quoted(word: str, pair: str) -> str:
    """따옴표로 감싼 `word` 와 조사 ("'가락동' 과", "'강남구' 와")."""
    return f"'{word}' {particle(word, pair)}"


def legal_dong_hint(query: str) -> str | None:
    """검색어 끝 낱말이 행정동 이름이면 법정동 이름으로 다시 찾으라는 힌트. 아니면 None.

    직방·당근은 매물을 법정동으로만 찾아 행정동에는 0건(직방 검색)이나 없는 지도 페이지(당근)를 준다
    (2026-10-11 실측: 역삼1동). 행정동이 어느 법정동에 걸치는지는 모르니 이름으로 다시 찾지 않고 안내만 한다.
    번호를 뗀 이름은 예로만 든다. 법정동 이름이 다른 곳이 있어서다 (2026-10-11 실측: 성북구 월곡1동의 법정동은
    하월곡동인데 '월곡동' 을 넣으면 당근이 광주 광산구 월곡동을 조회했다).
    """
    words = query.split()
    match = ADMIN_DONG_PATTERN.fullmatch(words[-1]) if words else None
    if match is None:
        return None
    return (
        f"{quoted(words[-1], '은/는')} 행정동 이름입니다. 매물은 법정동 이름으로 찾습니다. 번호를 뗀 '{match.group(1)}동' 이 "
        "법정동인 경우가 많지만 다를 수 있으니(월곡1동 → 하월곡동) 구 이름을 붙여 찾고 결과의 주소가 맞는지 확인하세요"
    )


def is_dong_code(legal_division_code: str | None) -> bool:
    """10자리 법정동 코드가 읍·면·동인지. 시·도·시·군·구(1168000000)와 리(끝 두 자리가 00 이 아님)는 아니다."""
    code = legal_division_code or ''
    return len(code) == 10 and code[5:8] != '000' and code[8:] == '00'


def is_ri_code(legal_division_code: str | None) -> bool:
    """10자리 법정동 코드가 리인지 (끝 두 자리가 00 이 아님)."""
    code = legal_division_code or ''
    return len(code) == 10 and code[8:] != '00'
