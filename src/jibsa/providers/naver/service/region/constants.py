"""지역 해석 상수: 후보 안내 수, 자동완성 쪽 상한, 안내 토막, 주소·지역 단위 이름, 옛 시·도 이름."""


# 같은 이름 지역·역을 안내할 때 보여 줄 후보 수
MAX_CANDIDATE_NOTES: int = 5


# 끝말 없이 준 지역 이름('송정', '해운대')에 붙여 이름 전체로 보는 끝말
DIVISION_NAME_SUFFIXES: tuple[str, ...] = ('동', '구', '시', '군', '읍', '면')


# 이름이 맞는 후보를 모으려고 받는 자동완성 쪽 수 (첫 쪽 포함). 법정동·역은 한 쪽 5곳이라 15곳까지 본다
MAX_AUTOCOMPLETE_PAGES: int = 3


# 시·도·시·군·구 이름에 붙이는 '[범위] … 단위의 넓은 지역이라 중심에서 반경 … 안만 검색했습니다' 안내(`_wide_region_note`)의 토막.
# 시·군·구 경계 전체로 찾으면 맞지 않는 안내라 CLI 가 이 토막으로 그 안내를 찾아 뺀다 (`_area_location`)
WIDE_REGION_NOTE_MARK: str = '단위의 넓은 지역이라'


# 주소 검색 itemLevel 이 이 값 이상이면 번지·건물 단위다 (5 시·도/시·군·구, 8 동·읍·면, 12 번지·건물)
ADDRESS_LOT_ITEM_LEVEL: int = 12


REGION_LEVEL_LABELS: dict[str, str] = {'SI': '시·도', 'GUN': '시·군·구', 'EUP': '읍·면·동'}


# 합쳐진 시·도의 옛 이름. 시·도 목록에 광주광역시·전라남도 없이 전남광주통합특별시(네이버 이름 '전남광주시') 하나만
# 있고, 그 아래에 광산구 등 광주의 구와 강진군 등 전남의 군 27곳이 있다 (2026-10-10). 시·도는 `SIDO_OFFICIAL_NAMES` 로
# 찾고, 이 이름으로 찾았으면 옛 이름이라고 알린다
FORMER_PROVINCE_NAMES: frozenset[str] = frozenset({'전라남도', '전남', '광주광역시', '광주'})


# 옛 이름이 다른 시·도의 시와 겹칠 때 덧붙이는 안내 (search listings '광주' 는 경기도 광주시와 겹쳐 REGION_AMBIGUOUS, 2026-10-10)
FORMER_PROVINCE_NAME_HINTS: dict[str, str] = {
    '광주': "경기도 광주시는 '광주시' 로 찾으세요",
}
