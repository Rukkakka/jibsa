"""당근 지역·역·대학·주소 해석 상수."""

import re

from typing import Literal


AreaLevel = Literal['동', '구', '시도']


# 같은 이름 지역으로 멈출 때 보여 줄 후보 수 (네이버와 같다). 나머지는 전체 수(candidate_count)로만 알린다 (중앙동 58곳)
AMBIGUOUS_CANDIDATES_SHOWN: int = 5


# 웹 지도는 검색창에서 고른 지역을 19 에서 그 지역의 지도 레벨(`mapViewDefaultZoomLevel`)을 뺀 줌으로 연다
# (MapPage 의 검색창 선택. 2026-11-11 실측: 동 5 → 14, 구 7 → 12, 시·도 9 → 10)
MAP_LEVEL_BASE: int = 19


# 주소 검색 후보를 한 번에 받는 수. 웹 검색창 주소 칸은 4곳씩 받고 '더 보기' 로 넘긴다 (MapShell `Mo` 의 pageSize 4)
ADDRESS_CANDIDATES: int = 20


# 웹은 지역에 `mapViewDefaultZoomLevel` 이 없으면 5 로 본다 (`19-(t.mapViewDefaultZoomLevel||5)` → 줌 14). 실측에는 늘 있었다
DEFAULT_MAP_VIEW_LEVEL: int = 5


# 숫자만 쓴 노선 ('2호선'). 당근 숫자 노선은 늘 지역을 붙여 쓰므로('서울2호선'·'부산1호선', 2026-11-20 실측 `search_stations('서울')`:
# 서울1호선~서울9호선) 이 꼴은 당근 노선 이름이 아니라 `find_station` 이 못 찾는다
NUMBER_ONLY_LINE_PATTERN: re.Pattern[str] = re.compile(r'\d+호선')


# 구 아래 동을 모두 셀 때 받을 지역 검색 쪽 수 상한 (100곳씩). 동이 많은 구 이름도 3쪽이다 (2026-11-12 실측: '중구' 222곳)
AREA_MAX_PAGES: int = 10


# 시·도 캐시(`sido_of`)에서 지역 ID 칸의 앞 자리. (구, 동) 이름 칸과 겹치지 않게 구 이름일 수 없는 값을 쓴다
RELAY_ID_KEY: str = '#id'


AREA_LEVEL_BY_DEPTH: dict[int, AreaLevel] = {1: '시도', 2: '구', 3: '동'}


DONG_OR_DISTRICT: frozenset[AreaLevel] = frozenset({'동', '구'})


# 지역 단계를 안내에 쓰는 이름과 예시 (이 순서로 잇는다, `_level_words`·`_region_name_hint`)
AREA_LEVEL_LABELS: dict[AreaLevel, tuple[str, str]] = {'동': ('동', '역삼동'), '구': ('구', '강남구'), '시도': ('시·도', '서울')}


SEJONG: str = '세종특별자치시'


# 대학 검색에서 한 번에 받는 후보 수 (요청 모델의 상한). 웹 대학 검색 쿼리는 다음 쪽을 받을 수 없어 이만큼만 본다 (`search_universities`)
UNIVERSITY_CANDIDATES: int = 50


# 위치(좌표)가 없는 후보를 이름 목록에 보일 때 붙이는 말. 그 후보는 `--station`·`--university` 로 고를 수 없다
NO_LOCATION: str = ' (위치 정보 없음)'
