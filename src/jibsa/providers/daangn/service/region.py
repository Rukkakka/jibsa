"""지역·역·대학·주소 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석, 매물 카드의 시·도 채우기).

당근 부동산 웹 지도 검색창과 같은 API 로 찾는다. 지역은 `searchRegion`, 역은 `searchSubwayStationPois`, 대학은
`searchSchoolPois`, 도로명 주소(`--address`)는 검색창 주소 모드의 `searchAddress` → `unitByAddress` 다 (`find_address`).
웹은 이름의 종류를 짐작하지 않고 검색창이 칸별로 보여 준 후보를 사용자가 고르므로, jibsa 도 종류별 입력(지역 이름,
`--station`, `--university`, `--address`)을 따로 받고 이름이 정확히 같은 곳만 쓴다 (주소는 후보가 하나거나 입력과 정확히 같은
하나일 때만).
"""

import logging

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
    UnsupportedRegionError,
)
from jibsa.core.korean import (
    legal_dong_hint,
    quoted,
)
from jibsa.core.listing import (
    CITY_NAMES_NOT_SIDO,
    SIDO_OFFICIAL_NAMES,
    join_address,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel
from jibsa.providers.daangn.api.request.region import (
    DaangnGetRegionByCoordinateRequestPayloadModel,
    DaangnJusoAddressInputModel,
    DaangnQueryInputModel,
    DaangnSchoolPoiSearchInputModel,
    DaangnSearchAddressRequestPayloadModel,
    DaangnSearchRegionRequestPayloadModel,
    DaangnSearchSchoolPoisRequestPayloadModel,
    DaangnSearchSubwayStationPoisRequestPayloadModel,
    DaangnUnitByAddressInputModel,
    DaangnUnitByAddressRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnRegionModel,
)
from jibsa.providers.daangn.api.response.region import (
    DaangnAddressModel,
    DaangnSchoolPoiModel,
    DaangnSearchRegionNodeModel,
    DaangnSubwayStationPoiModel,
)
from jibsa.providers.daangn.service.common import (
    OPTIONAL_LOOKUP_ERRORS,
    DaangnRegion,
    coordinate_point,
    next_cursor,
    partial_failure_note,
    station_name,
    unwrap_graphql,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


logger = logging.getLogger(__name__)
# 같은 이름 지역으로 멈출 때 보여 줄 후보 수 (네이버와 같다). 나머지는 전체 수(candidate_count)로만 알린다 (중앙동 58곳)
AMBIGUOUS_CANDIDATES_SHOWN: int = 5
# 웹 지도는 검색창에서 고른 지역을 19 에서 그 지역의 지도 레벨(`mapViewDefaultZoomLevel`)을 뺀 줌으로 연다
# (MapPage 의 검색창 선택. 2026-11-11 실측: 동 5 → 14, 구 7 → 12, 시·도 9 → 10)
MAP_LEVEL_BASE: int = 19
# 주소 검색 후보를 한 번에 받는 수. 웹 검색창 주소 칸은 4곳씩 받고 '더 보기' 로 넘긴다 (MapShell `Mo` 의 pageSize 4)
ADDRESS_CANDIDATES: int = 20
# 웹은 지역에 `mapViewDefaultZoomLevel` 이 없으면 5 로 본다 (`19-(t.mapViewDefaultZoomLevel||5)` → 줌 14). 실측에는 늘 있었다
DEFAULT_MAP_VIEW_LEVEL: int = 5
# 구 아래 동을 모두 셀 때 받을 지역 검색 쪽 수 상한 (100곳씩). 동이 많은 구 이름도 3쪽이다 (2026-11-12 실측: '중구' 222곳)
AREA_MAX_PAGES: int = 10
# 시·도 캐시(`sido_of`)에서 지역 ID 칸의 앞 자리. (구, 동) 이름 칸과 겹치지 않게 구 이름일 수 없는 값을 쓴다
RELAY_ID_KEY: str = '#id'
AreaLevel = Literal['동', '구', '시도']
AREA_LEVEL_BY_DEPTH: dict[int, AreaLevel] = {1: '시도', 2: '구', 3: '동'}
DONG_OR_DISTRICT: frozenset[AreaLevel] = frozenset({'동', '구'})
# 지역 단계를 안내에 쓰는 이름과 예시 (이 순서로 잇는다, `_level_words`·`_region_name_hint`)
AREA_LEVEL_LABELS: dict[AreaLevel, tuple[str, str]] = {'동': ('동', '역삼동'), '구': ('구', '강남구'), '시도': ('시·도', '서울')}
SEJONG: str = '세종특별자치시'


class SimilarAreasError(JibsaError):
    """이름이 같은 지역 없이 비슷한 지역만 있을 때 (`REGION_AMBIGUOUS`, `resolve_area`).

    같은 이름이 여러 곳인 `RegionAmbiguousError` 와 달리 준 이름이 지역 이름이 아닐 수 있어, 단지 이름도 받는 명령은 이 에러를
    따로 잡아 단지 후보를 덧붙인다 (`cli/daangn.py` 의 `_complex_name_hint`).
    """


class DaangnArea(BaseModel):
    """웹 지도 검색창의 지역 검색(`searchRegion`)으로 찾은 법정동·구·시·도."""

    model_config = ConfigDict(
        extra='forbid',
    )

    level: Annotated[
        AreaLevel,
        Field(description='동(읍·면 포함)·구(시·군 포함)·시도')
    ]
    name1: Annotated[
        str,
        Field(description='시/도')
    ]
    name2: Annotated[
        str,
        Field(description="시/군/구 ('수원시 권선구'). 시·도와 세종의 동은 빈 문자열")
    ] = ''
    name3: Annotated[
        str,
        Field(description='읍/면/동. 동이 아니면 빈 문자열')
    ] = ''
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]
    lat: Annotated[
        float,
        Field(description='지역 중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='지역 중심 경도')
    ]
    zoom: Annotated[
        int,
        Field(description='웹 지도가 이 지역을 여는 줌 (동 14, 구 12, 시·도 10)')
    ]
    node_id: Annotated[
        str | None,
        Field(exclude=True, description='지역 검색 결과의 Relay id. 매물 카드 지역의 id 와 같다 (`relay_id`, 시·도 채우기에 쓴다)')
    ] = None

    @property
    def full_name(self) -> str:
        """시·도부터 이어 붙인 이름 ('서울특별시 강남구 역삼동')."""
        return join_address(self.name1, self.name2, self.name3) or self.name1

    def as_region(self) -> DaangnRegion:
        """동 단위 검색이 쓰는 동 (`DaangnRegion`)."""
        return DaangnRegion(name1=self.name1, name2=self.name2, name3=self.name3, region_id=self.region_id)


def relay_id(region: DaangnRegionModel) -> str | None:
    """지역의 Relay id (`id`). 매물 카드·지역 검색·좌표 → 지역이 같은 동에 같은 값을 줘, 이름이 같은 동을 가른다.

    2026-11-12 실측: '중구 태평로2가' 카드의 id 는 지역 검색의 서울 중구 태평로2가와 같고 대구 중구 태평로2가와 다르다. 응답
    모델에 필드가 없어 `extra='allow'` 로 남은 값을 읽는다.
    """
    value = (region.model_extra or {}).get('id')
    return value if isinstance(value, str) and value else None


def _area_of(node: DaangnSearchRegionNodeModel) -> DaangnArea | None:
    """지역 검색 결과를 `DaangnArea` 로. 단계·ID·중심이 빠진 결과는 쓰지 않는다 (실측에는 없었다)."""
    level = AREA_LEVEL_BY_DEPTH.get(node.depth or 0)
    center = coordinate_point(node.center_coordinate)
    if level is None or node.original_id is None or center is None or not node.name1:
        return None
    zoom = MAP_LEVEL_BASE - (node.map_view_default_zoom_level or DEFAULT_MAP_VIEW_LEVEL)
    return DaangnArea(
        level=level,
        name1=node.name1,
        name2=node.name2 or '',
        name3=node.name3 or '',
        region_id=node.original_id,
        lat=center[0],
        lng=center[1],
        zoom=zoom,
        node_id=relay_id(node),
    )


class _AreaPage(NamedTuple):
    """지역 검색 한 쪽 (`_search_area_page`)."""

    areas: list[DaangnArea]
    # 다음 쪽 커서. 다음 쪽이 없거나 빈 쪽·커서 없음·같은 커서 되풀이로 멈췄으면 None
    cursor: str | None
    # 서버가 다음 쪽이 있다고 했는지. 커서가 None 인데 True 면 끝까지 받지 못하고 멈춘 것이다
    more: bool


def _search_area_page(client: DaangnClient, query: str, after: str | None = None) -> _AreaPage:
    """지역 검색 한 쪽(100곳)과 다음 쪽 커서 (`searchRegion`, 요청 1회).

    다음 쪽이 없거나, 빈 쪽·커서 없음·같은 커서 되풀이면 커서는 None 이다 (`next_cursor`, 다른 목록과 같은 규칙. 예전에는 같은
    식을 따로 두어 빈 쪽 멈춤이 빠졌다, 2026-11-12 리뷰). 다음 쪽은 구 아래 동을 세는 에러 길과 같은 이름 구의 동을 모으는 시·도
    채우기(`_remaining_areas`)에서만 받고, 멈춘 까닭은 알리지 않는다.
    """
    response = client.run_request_search_region(
        DaangnSearchRegionRequestPayloadModel(input=DaangnQueryInputModel(query=query), after=after)
    )
    connection = unwrap_graphql(response, response.data.search_region if response.data else None, '지역 검색')
    page = connection.page_info
    more = bool(page and page.has_next_page)
    received = sum(1 for edge in connection.edges if edge.node)
    cursor = next_cursor(page, after, received=received) if more else None
    return _AreaPage([area for edge in connection.edges if edge.node and (area := _area_of(edge.node))], cursor, more)


def search_areas(client: DaangnClient, query: str) -> list[DaangnArea]:
    """지역 이름으로 법정동·구·시·도 후보 첫 쪽을 받는다 (`searchRegion`, 요청 1회). 시·도 → 구 → 동 순이다.

    한 번에 100곳까지 받는다 (웹 검색창은 4곳씩). 동 이름은 비슷한 이름까지 합쳐도 100곳에 못 미치고 (2026-11-12 실측: 중앙동
    35곳, 송정동 14곳), 시·도·구 이름은 그 아래 동까지 와서 100곳을 넘지만 (중구 222곳, 서울 493곳) 시·도·구가 동보다 앞에 와
    첫 쪽에 다 있다. 구 아래 동을 모두 봐야 할 때만 나머지 쪽을 받는다 (`_remaining_areas`).
    """
    return _search_area_page(client, query).areas


def _in_context(area: DaangnArea, context: list[str]) -> bool:
    """이름 앞에 붙인 시·도·구 낱말('강남구 신사동' 의 '강남구')이 모두 이 지역의 시·도·구에 맞는지 (`place_in`)."""
    return all(place_in(word, area.name1, area.name2) for word in context)


def _remaining_areas(client: DaangnClient, query: str, first: _AreaPage) -> tuple[list[DaangnArea], bool]:
    """지역 검색의 첫 쪽(`first`) 뒤 나머지 쪽 (`AREA_MAX_PAGES` 쪽까지)과 끝까지 받았는지.

    끝까지 받지 못한 것은 쪽 수 상한에 닿았거나 서버가 다음 쪽이 있다고 했는데 커서가 멈춘 것이다 (`_AreaPage.more`). 예전에는
    받은 목록만 돌려줘, 받는 쪽은 상한에 걸린 동 수를 전체 수로 알렸고 (`resolve_area`), 끝까지 받았는지 함께 받으려던 시·도
    채우기(`_district_sido`)는 목록을 둘로 풀다 실패해 받은 쪽을 버렸다 (2026-11-13 리뷰·실측: '중구' 나머지 122곳).
    """
    areas: list[DaangnArea] = []
    page = first
    for _ in range(AREA_MAX_PAGES - 1):
        if page.cursor is None:
            break
        page = _search_area_page(client, query, page.cursor)
        areas += page.areas
    return areas, page.cursor is None and not page.more


def place_in(place: str, *texts: str | None) -> bool:
    """지역 이름 한 마디(`place`)로 시작하는 단어가 주소 조각 중 하나에 있는지.

    단어 앞부분만 본다. '강남' 은 '강남구' 에 맞지만 '남구' 는 '강남구', '동구' 는 '성동구' 에 맞지 않는다
    (2026-10-11 실측: 글자가 들어 있는지만 보면 '송정동 --city 동구' 가 대구 동구가 아닌 서울 성동구 송정동을 골랐다).
    당근은 시·도를 정식 명칭으로만 써서, 줄임말·옛 이름('서울시'·'강원도'·'전라남도')은 정식 명칭으로도 찾는다
    (2026-10-10 실측: '서울시' 는 '서울특별시' 에 들어 있지 않아 주소 검색이 못 찾았다).
    시 이름이기도 한 줄임말(`CITY_NAMES_NOT_SIDO`, '광주시')은 정식 명칭으로 넓히지 않는다.
    띄어 쓴 이름('성남시 분당구')은 마디마다 맞아야 한다 (2026-11-01 에이전트 검증: 당근 구 이름 '성남시 분당구' 를 한 마디로
    보고 맞는 곳이 없다며 REGION_NOT_FOUND 였다).
    """
    words = [word for text in texts if text for word in text.split()]

    def matches(part: str) -> bool:
        official = part if part in CITY_NAMES_NOT_SIDO else SIDO_OFFICIAL_NAMES.get(part, part)
        return any(word.startswith((part, official)) for word in words)

    parts = place.split()
    return bool(parts) and all(matches(part) for part in parts)


def _is_sido(area: DaangnArea, name: str) -> bool:
    """`name` 이 이 시·도의 이름(정식 명칭·줄임말·옛 이름)인지. 시 이름이기도 한 줄임말('광주시')은 시·도로 보지 않는다."""
    return area.level == '시도' and name not in CITY_NAMES_NOT_SIDO and SIDO_OFFICIAL_NAMES.get(name, name) == area.name1


def _ambiguous(query: str, areas: list[DaangnArea], hint: str) -> RegionAmbiguousError:
    return RegionAmbiguousError(query, [area.full_name for area in areas[:AMBIGUOUS_CANDIDATES_SHOWN]], len(areas), hint=hint)


def _same_dong_hint(dongs: list[DaangnArea], last: str) -> str:
    """이름이 같은 동이 여러 곳일 때 그대로 다시 넣으면 찾히는 이름을 예로 드는 힌트 (`resolve_area`).

    구 이름이 모두 다르면 구만 붙인 이름('강남구 신사동'), 구 이름까지 같은 동이 있으면 시·도도 붙인 이름(후보 이름 그대로)을 예로
    든다. 예전에는 늘 구만 붙여, 서울·대구 중구에 다 있는 태평로2가는 예시 '중구 태평로2가' 를 다시 넣어도 또 모호했다
    (2026-11-13 리뷰·실측).
    """
    top = dongs[0]
    districts = [area.name2 for area in dongs]
    if len(set(districts)) == len(districts):
        return f"구를 붙여 다시 주세요 (예: '{top.name2 or top.name1} {last}')"
    return f"구 이름도 같은 곳이 있어 시·도와 구를 붙여 다시 주세요 (예: '{top.full_name}')"


def _dong_not_accepted(query: str, dongs: list[DaangnArea]) -> JibsaError:
    """동을 받지 않는 명령(인기 급상승 단지)에 이름이 같은 동이 여러 곳일 때 그 동들의 구를 다시 넣을 이름으로 주는 에러.

    동이 한 곳이면 부르는 쪽이 그 구를 권한다 (`trending_region_of`, INVALID_ARGUMENT). 예전에는 여러 곳이면 동을 고르라는
    REGION_AMBIGUOUS 를 내, 예시('강남구 신사동')를 따르면 동이라 INVALID_ARGUMENT 로 끝났다 (2026-11-13 리뷰·실측:
    'trending-complexes 신사동'). 한 곳일 때와 같은 코드로 끝내고 구는 시·도까지 붙인 이름이라 그대로 다시 넣으면 찾힌다.
    """
    parents = list(dict.fromkeys(join_address(area.name1, area.name2) or area.name1 for area in dongs))
    shown = parents[:AMBIGUOUS_CANDIDATES_SHOWN]
    choices = ' 또는 '.join(f"'{name}'" for name in shown) + (' 등' if len(parents) > len(shown) else '')
    return JibsaError(
        code='INVALID_ARGUMENT',
        message=f"{quoted(query, '은/는')} 동 이름이라 이 명령에서는 받지 않습니다 (이름이 같은 동이 {len(dongs)}곳)",
        hint=f'그 동이 속한 구로 다시 주세요 ({choices})',
        details={'candidates': shown, 'candidate_count': len(parents)},
    )


def _choose_children(
    query: str,
    message: str,
    children: list[str],
    example_hint: str,
    *,
    complete: bool = True,
) -> JibsaError:
    """시·도·구가 있는 시·세종처럼 그 자체로는 조회할 수 없는 지역에, 아래 지역을 골라 다시 묻게 하는 에러.

    `children` 은 그대로 다시 넣으면 바로 찾히는 이름이어야 한다 (`DaangnArea.full_name`·'수원시 권선구'). 예전에는 시·도의 구와
    세종의 동을 짧은 이름으로 줘 다시 넣으면 또 모호했다 (2026-11-12 검증: '부산시' 의 예시 '강서구' 는 부산·서울 2곳, '세종' 의
    '금남면' 은 세종·하동 2곳). `complete` 가 거짓이면 지역 검색 첫 쪽이나 끝까지 받지 못한 쪽들에서 찾은 일부라 전체 수를 모른다
    (`candidate_count` null).
    """
    shown = children[:AMBIGUOUS_CANDIDATES_SHOWN]
    more = ' 등' if len(children) > len(shown) or not complete else ''
    return JibsaError(
        code='REGION_AMBIGUOUS',
        message=message,
        hint=f"{example_hint} (예: '{shown[0]}'). 찾은 곳: {', '.join(shown)}{more}" if shown else example_hint,
        details={'candidates': shown, 'candidate_count': len(children) if complete else None},
    )


def _level_words(levels: frozenset[AreaLevel]) -> str:
    """받는 단계를 안내에 쓰는 이름 ('동·구', '동', '구·시·도')."""
    return '·'.join(label for level, (label, _) in AREA_LEVEL_LABELS.items() if level in levels)


def _region_name_hint(levels: frozenset[AreaLevel]) -> str:
    """지역을 못 찾았을 때 이 명령이 받는 단계의 이름으로 다시 주라는 힌트.

    예전에는 명령과 상관없이 동·구를 권해, 구·시·도만 받는 인기 급상승 단지에 동을 권했다 (2026-11-12 검증:
    'trending-complexes 역삼').
    """
    examples = ', '.join(f"'{example}'" for level, (_, example) in AREA_LEVEL_LABELS.items() if level in levels)
    qualified = "'강남구 신사동' 처럼 구·시·도" if '동' in levels else "'서울 중구' 처럼 시·도"
    return (
        f'{_level_words(levels)} 이름(예: {examples})으로 다시 주세요. 같은 이름이 여러 곳이면 {qualified}를 붙입니다. '
        "후보는 'jibsa daangn search locations <이름>' 으로 볼 수 있습니다"
    )


def resolve_area(
    client: DaangnClient,
    name: str,
    *,
    levels: frozenset[AreaLevel] = DONG_OR_DISTRICT,
    other_inputs: str = '',
    sejong_whole: bool = False,
) -> DaangnArea:
    """지역 이름을 웹 지역 검색(`searchRegion`)으로 법정동이나 구로 바꾼다 (요청 1회. 동만 받는 명령에 구를 주면 그 구의 동을
    다 세려고 더 받는다).

    이름이 정확히 같은 동, 없으면 구만 쓴다. 웹 검색창처럼 비슷한 이름을 대신 고르지 않는다. 같은 이름이 여러 곳이면
    `REGION_AMBIGUOUS` 로 후보를 주고, '강남구 신사동'·'서울 중구' 처럼 앞에 붙인 시·도·구로 고른다 (`place_in`).
    시·도('서울'), 구가 있는 시('수원시'), 세종은 그 아래 구(구를 받지 않는 명령은 동)를 골라 다시 묻는다. 후보는 그대로 다시
    넣으면 찾히는 이름이다. `sejong_whole` 이면 세종은 시 전체를 준다 (지역 실거래). 이름이 같은 곳이 없으면 비슷한 지역을
    후보로 알린다. 안내는 이 명령이 받는 단계(`levels`)와 입력(`other_inputs`)만 권한다.

    Args:
        levels: 받는 단계. 동만 받는 명령이 구를 받으면 그 구의 동을 고르게 한다. '시도' 를 넣으면 시·도 이름('서울')에 그
            시·도를 준다 (인기 급상승 단지). 동을 빼도 이름이 같은 동이 한 곳이면 그 동을 돌려줘 부르는 쪽이 그 구를 권하고
            (`trending_region_of`), 여러 곳이면 그 동들의 구를 INVALID_ARGUMENT 로 권한다.
        other_inputs: 못 찾았을 때 힌트에 덧붙일, 이 명령이 받는 다른 입력 ('역은 --station 으로 찾습니다'). 좌표(`--lat/--lng`)
            처럼 명령마다 있고 없는 옵션은 여기로만 권한다.
        sejong_whole: 세종을 시 전체(시·도 단계)로 줄지.

    Raises:
        RegionAmbiguousError: 같은 이름의 동·구가 여러 곳일 때.
        SimilarAreasError: 이름이 같은 곳 없이 비슷한 곳만 있을 때 (REGION_AMBIGUOUS).
        JibsaError: 그 자체로는 조회할 수 없는 지역일 때 (REGION_AMBIGUOUS), 동을 받지 않는 명령에 이름이 같은 동이 여러
            곳일 때 (INVALID_ARGUMENT).
        RegionNotFoundError: 비슷한 지역도 없을 때.
    """
    query = ' '.join(name.split())
    if not query:
        raise RegionNotFoundError(name, hint=_region_name_hint(levels))
    *context, last = query.split()
    # 검색은 마지막 낱말로만 하고 앞 낱말은 여기서 맞춘다. 비슷한 지역 후보(similar)의 수는 첫 쪽(100곳)에서 센다
    first = _search_area_page(client, last)
    areas = [area for area in first.areas if _in_context(area, context)]
    dongs = [area for area in areas if area.level == '동' and area.name3 == last]
    districts = [area for area in areas if area.level == '구' and (area.name2 == last or area.name2.endswith(f' {last}'))]

    if dongs:
        if len(dongs) > 1 and '동' not in levels:
            raise _dong_not_accepted(query, dongs)
        if len(dongs) > 1:
            raise _ambiguous(query, dongs, _same_dong_hint(dongs, last))
        # 동을 받지 않는 명령(인기 급상승 단지)에 동 하나를 주면 부르는 쪽이 그 구를 권한다 (`trending_region_of`)
        return dongs[0]
    if districts:
        if len(districts) > 1:
            raise _ambiguous(query, districts, f"시·도를 붙여 다시 주세요 (예: '{districts[0].name1} {last}')")
        district = districts[0]
        if '구' not in levels:
            # 구 이름 검색은 그 구 아래 동도 함께 줘서 후보가 비지 않는다 (2026-11-12 실측: '강남구' → 동 14곳). 동이 첫 쪽(100곳)을
            # 넘으면 나머지 쪽도 받아 센다. 첫 쪽만 보면 '서울 중구' 가 중구 동 74곳 중 23곳으로 나왔다 (2026-11-12 리뷰·실측. '중구'
            # 는 다섯 중구와 그 동까지 222곳). 에러로 끝나는 길이라 요청이 느는 것도 이때뿐이다
            rest, complete = _remaining_areas(client, last, first)
            areas += [area for area in rest if _in_context(area, context)]
            children = [area.full_name for area in areas if area.level == '동' and area.name2 == district.name2]
            raise _choose_children(
                query, f"{quoted(query, '은/는')} 구 이름이라 이 명령에서는 받지 않습니다", children, '그 구의 동 이름으로 다시 주세요',
                complete=complete,
            )
        return district
    sido = next((area for area in areas if _is_sido(area, last)), None)
    if sido is not None and '시도' in levels:
        return sido
    # 시·도·세종·구가 있는 시의 아래 동은 지역 검색 첫 쪽에 온 것만 후보로 든다 (에러 길에서 수백 곳을 다 받지 않는다. '서울' 은
    # 493곳, 2026-11-12 실측). 첫 쪽 뒤가 있으면 전체 수는 모른다
    if sido is not None and sido.name1 == SEJONG:
        if sejong_whole:
            return sido
        children = [area.full_name for area in areas if area.level == '동' and area.name1 == SEJONG]
        raise _choose_children(
            query, f"{quoted(query, '은/는')} 구가 없는 시라 시 전체로는 조회할 수 없습니다", children, '세종의 동 이름으로 다시 주세요',
            complete=not first.more,
        )
    if sido is not None:
        # 구를 받지 않는 명령(인기 매물)에 구를 권하면 그 구도 받지 않는다 (2026-11-12 검증: 'popular-listings 서울' 의 예시
        # '강남구' 를 다시 넣으니 '구 이름이라 이 명령에서는 받지 않습니다')
        unit = '구' if '구' in levels else '동'
        children = [area.full_name for area in areas if area.level == unit and area.name1 == sido.name1]
        raise _choose_children(
            query, f"{quoted(query, '은/는')} 시·도 이름이라 시·도 전체로는 조회할 수 없습니다", children, f'{unit} 이름으로 다시 주세요',
            # 시·도의 구는 동보다 앞에 와 첫 쪽에 다 있다 (`search_areas`)
            complete=unit == '구' or not first.more,
        )
    # 구가 있는 시('수원시')는 시 자체가 오지 않고 '수원시 권선구' 처럼 시 이름이 붙은 구만 온다 (2026-11-11 실측). 시 이름은
    # 전국에 하나라 '수원시 권선구' 는 그대로 다시 넣으면 찾힌다
    city_districts = list(dict.fromkeys(area.name2 for area in areas if area.level == '구' and area.name2.startswith(f'{last} ')))
    if city_districts and '구' in levels:
        raise _choose_children(
            query, f"{quoted(query, '은/는')} 구가 있는 시라 시 전체로는 조회할 수 없습니다", city_districts, '구 이름으로 다시 주세요',
        )
    if city_districts:
        children = [area.full_name for area in areas if area.level == '동' and area.name2 in city_districts]
        raise _choose_children(
            query, f"{quoted(query, '은/는')} 구가 있는 시라 시 전체로는 조회할 수 없습니다", children, '동 이름으로 다시 주세요',
            complete=not first.more,
        )
    admin_dong_hint = legal_dong_hint(query)
    # 좌표(--lat/--lng)는 받는 명령만 `other_inputs` 로 권한다. 예전에는 늘 권해 좌표를 받지 않는 명령(popular-listings·
    # region-real-price)에서 그대로 따르면 'No such option: --lat' 이었다 (2026-11-12 검증)
    hint = admin_dong_hint or (
        '당근에는 리 단위 지역이 없습니다. 상위 읍·면 이름으로 찾으세요' if last.endswith('리') else _region_name_hint(levels)
    )
    hint = f'{hint}. {other_inputs}' if other_inputs else hint
    similar = [area for area in areas if area.level in levels]
    # `○가` 로 나뉜 동('성수동')도 이 길로 REGION_AMBIGUOUS 가 되어 1가·2가를 고르게 한다 (docs/llm.md). 지역 검색이 `○가` 동을
    # 앞에 주어 후보 앞쪽이 그 동들이다 (2026-11-12 리뷰 오탐에 실측: 성수동 → 성수동1가·2가 2곳, 문래동 → 6곳 중 1가~5가,
    # '서울 용산동' → 6곳 중 용산동1가~5가)
    # 역 이름은 비슷한 지역을 권하지 않는다. 지역 검색이 역 둘레 동을 주어('강남역' → 역삼동, 2026-11-11 실측) 역을 찾던 사람에게
    # 엉뚱한 동을 권했다. 못 찾음으로 끝내 부르는 쪽이 역 입력(--station)을 알리게 한다
    if similar and admin_dong_hint is None and not last.endswith('역'):
        shown = [area.full_name for area in similar[:AMBIGUOUS_CANDIDATES_SHOWN]]
        # 첫 쪽 뒤가 있으면 전체 수를 모른다 (모름 → null). 예전에는 첫 쪽에서 센 수를 전체처럼 알렸다 (2026-11-13 리뷰·실측:
        # '창원' 은 첫 쪽 100곳·끝까지 208곳인데 '100곳 있습니다')
        count = f'{len(similar)}곳 이상' if first.more else f'{len(similar)}곳'
        raise SimilarAreasError(
            code='REGION_AMBIGUOUS',
            message=f"{quoted(query, '과/와')} 이름이 같은 지역이 없습니다. 비슷한 지역이 {count} 있습니다",
            hint=(
                # 시·도를 받는 명령(인기 급상승 단지)은 시·도도 후보로 와서 동·구 이름이 비어 있다 ('충청' → 충청남도·충청북도,
                # 2026-11-12 실측: 예시가 '' 로 나갔다)
                f'후보의 {_level_words(levels)} 이름 그대로 다시 주세요 '
                f"(예: '{similar[0].name3 or similar[0].name2 or similar[0].name1}'). {other_inputs}"
            ).rstrip(),
            details={'candidates': shown, 'candidate_count': None if first.more else len(similar)},
        )
    raise RegionNotFoundError(query, hint=hint)


def resolve_dong(client: DaangnClient, name: str) -> DaangnRegion:
    """동 하나만 받는 명령(popular-listings)의 동 (`resolve_area`)."""
    return resolve_area(client, name, levels=frozenset({'동'})).as_region()


def with_sido(
    client: DaangnClient,
    article: DaangnArticleModel,
    cache: dict[tuple[str, str], str | None],
) -> DaangnArticleModel:
    """시·도(`region.name1`)가 빠진 매물에 당근 지역 검색으로 시·도를 채운다 (`sido_of`).

    매물 목록 카드에는 시·도가 없다 (웹 목록 카드도 가까운 역이나 동 이름(`region.name`)만 보여 준다, 2026-11-12 번들 대조:
    MainArticleCard 의 위치 줄). 구 이름이 전국에 하나면 구마다 한 번, 여러 시·도에 있으면 그 이름의 구 아래 동을 한꺼번에
    찾고, 구·동 이름이 같은 동이 여러 시·도에 있으면 카드의 지역 ID(`relay_id`)로 가른다 (`sido_of`). 검색이 실패하면 그대로
    둔다 (주소가 시·군·구부터 나온다). 요청 제한(`RateLimitedError`)도 실패로 보고 넘어간다. 주소를 다듬다 받아 둔 매물을 잃지
    않기 위함이다. 세종은 시·군·구가 없어 name2 가 '' 로 오는데(2026-10-11 실측: 매물·지역 검색 모두) 그때도 채운다. 빼면
    주소가 '반곡동' 처럼 동만 나간다.
    """
    region = article.region
    if region is None or region.name1 or not region.name3:
        return article
    name1 = sido_of(client, region.name2 or '', region.name3, cache, region_id=relay_id(region))
    if name1 is None:
        return article
    return article.model_copy(update={'region': region.model_copy(update={'name1': name1})})


def with_center_sido(
    client: DaangnClient,
    article: DaangnArticleModel,
    center: DaangnRegion | None,
    cache: dict[tuple[str, str], str | None],
) -> DaangnArticleModel:
    """시·도가 빠진 매물을 `with_sido` 로 채운다. 검색 중심 동(`center`)의 시·도는 세종 매물에만 바로 쓴다.

    역·지도·출퇴근·인기 매물 카드에는 시·도가 없다. 구 이름이 중심과 같아도 같은 구인지는 모른다. 남구·중구처럼 여러 시·도에
    있는 이름이 있어, 예전처럼 구 이름이 같으면 중심의 시·도를 붙이면 넓은 지도 화면에서 다른 시·도 매물의 주소가 틀린다
    (2026-11-12 검증: 울산 남구 삼산동 가운데 --zoom 9 에서 부산 남구 대연동 매물이 '울산광역시 남구 대연동'). 그래서 구 이름이
    같아도 지역 검색으로 정한다 (`sido_of`). 세종은 시·군·구가 없어 구 이름이 빈 동('')은 세종의 동뿐이라, 중심이 세종이면 찾지
    않고 세종으로 채운다.
    """
    known = article.region
    if center is not None and center.name1 == SEJONG and known is not None and known.name2 == '' and known.name3:
        cache.setdefault(('', known.name3), SEJONG)
    return with_sido(client, article, cache)


def sido_of(
    client: DaangnClient,
    name2: str,
    name3: str,
    cache: dict[tuple[str, str], str | None],
    *,
    region_id: str | None = None,
) -> str | None:
    """구·동 이름과 매물 카드의 지역 ID(`region_id`, `relay_id`)로 시·도를 찾는다 (`searchRegion`). 시·도가 하나로 정해지지
    않거나 실패하면(요청 제한 포함) None.

    먼저 구 이름으로 찾아 그 이름의 구가 전국에 하나면 그 시·도로 그 구의 동을 모두 채운다 (구마다 한 번). 지역 검색은
    시·도·구를 동보다 앞에 주어 같은 이름의 구가 첫 쪽에 다 온다 (`search_areas`, 2026-11-12 실측: 서초구·분당구는 구 1곳,
    중구는 대구·대전·부산·서울·울산 5곳, 남구는 5곳). 같은 이름의 구가 여러 시·도에 있으면 그 구 이름 검색을 끝까지 받아
    그 구들의 동마다 시·도를 정한다 (`_district_sido`). 끝까지 받지 못했거나 그 검색에 없는 동은 동 이름으로 찾는다
    (`_dong_sido`). 구·동 이름이 같은 동이 여러 시·도에 있으면 지역 검색 결과 가운데 카드와 지역 ID 가 같은 곳의 시·도다
    (2026-11-12 실측: '중구 태평로2가' 카드의 ID 는 서울 중구 태평로2가와 같고 대구 중구 태평로2가와 다르다). 예전에는 그런
    동을 고르지 않고 시·도 없이 냈다. 예전에는 동마다 찾아 이웃 구 매물이 많은 구 검색이 한 쪽에 요청을 8번 더 보냈다
    (2026-11-12 리뷰·실측: 강남구 --limit 40 의 서초구 5개 동·관악·성동·광진구 동).

    캐시 칸: 구는 (구 이름, ''), 동은 (구 이름, 동 이름), 이름으로 가리지 못한 동은 (`RELAY_ID_KEY`, 지역 ID). 동 캐시는 동
    이름이 늘 있어(`with_sido`) 구 캐시와 겹치지 않는다. 이름으로 가리지 못한 동의 (구, 동) 칸은 None 이다.
    """
    key = (name2, name3)
    id_key = (RELAY_ID_KEY, region_id) if region_id else None

    def known() -> bool:
        return key in cache or (id_key is not None and id_key in cache)

    if not known():
        district = _district_sido(client, name2, cache) if name2 else None
        if district is not None:
            cache[key] = district
        # 같은 이름의 구가 여러 시·도에 있으면 `_district_sido` 가 그 구들의 동을 이미 채웠다
        elif not known():
            _dong_sido(client, name2, name3, cache)
    return cache.get(key) or (cache.get(id_key) if id_key is not None else None)


def sido_cache_rows(cache: dict[tuple[str, str], str | None]) -> list[list[str]]:
    """이어 받기 표(`next`)에 담을 시·도 캐시 ([구, 동, 시·도] 줄. 구 캐시는 동이 '', 지역 ID 캐시는 [`RELAY_ID_KEY`, ID, 시·도]).
    다음 쪽이 같은 구·동을 다시 찾지 않게 한다.

    찾은 것만 담는다. None 은 실패(요청 제한 포함)와 시·도가 여럿인 구를 가리지 못해, 담으면 실패한 곳을 다음 쪽에서도 다시
    찾지 않는다 (2026-11-12 리뷰: 구 검색의 다음 쪽이 앞 쪽에서 찾은 구의 시·도를 다시 찾았다). 같은 이름 구의 동은 한꺼번에
    채워(`_district_sido`) 그 동들도 담겨, 다음 쪽이 그 구 이름 검색을 다시 받지 않는다. 이름으로 가리지 못한 동은 지역 ID 칸이
    담겨 다음 쪽도 그 ID 로 찾는다 (`sido_of`).
    """
    return [[name2, name3, sido] for (name2, name3), sido in cache.items() if sido is not None]


def sido_cache_from_rows(rows: list[list[str]] | None) -> dict[tuple[str, str], str | None]:
    """이어 받기 표의 시·도 캐시 줄(`sido_cache_rows`)을 캐시로 되돌린다. 없으면 빈 캐시."""
    return {(name2, name3): sido for name2, name3, sido in rows or []}


def _district_sido(client: DaangnClient, name2: str, cache: dict[tuple[str, str], str | None]) -> str | None:
    """구 이름이 전국에 하나면 그 시·도 (`sido_of`). 여러 시·도에 있거나 찾지 못하면 None. 구마다 한 번만 찾는다.

    여러 시·도에 있으면 그 구 이름 검색의 나머지 쪽도 받아(`_remaining_areas`) 그 구들의 동마다 시·도를 캐시에 채운다
    (`_fill_dong_sidos`). 구 이름 검색은 그 구 아래 동을 모두 준다 (`resolve_area` 의 구 아래 동 세기와 같다). 동마다 찾으면 같은
    이름 구의 동이 많은 화면에서 요청이 동 수만큼 는다 (2026-11-12 실측: 서울 중구 명동2가 가운데 줌 15 의 20건에 중구 동이
    12곳). 끝까지 받지 못하면(요청 제한·멈춘 쪽·쪽 수 상한) 받지 못한 쪽에 이름이 같은 동이 있을 수 있어 채우지 않고, `sido_of`
    가 동 이름으로 찾는다.
    """
    key = (name2, '')
    if key in cache:
        return cache[key]
    cache[key] = None
    try:
        first = _search_area_page(client, name2)
        sidos = {area.name1 for area in first.areas if area.level == '구' and area.name2 == name2}
        if len(sidos) == 1:
            cache[key] = sidos.pop()
        elif sidos:
            rest, complete = _remaining_areas(client, name2, first)
            if complete:
                _fill_dong_sidos(cache, name2, first.areas + rest)
    except OPTIONAL_LOOKUP_ERRORS:
        pass
    return cache[key]


def _dong_sido(client: DaangnClient, name2: str, name3: str, cache: dict[tuple[str, str], str | None]) -> None:
    """동 이름으로 지역 검색해 그 구·동의 시·도를 캐시에 채운다 (`_fill_dong_sidos`, `sido_of`).

    동 이름 검색은 비슷한 이름까지 합쳐도 첫 쪽(100곳)에 다 온다 (`search_areas`). 찾지 못하거나 실패하면(요청 제한 포함) (구, 동)
    칸을 None 으로 두어 같은 조회에서 다시 찾지 않는다.
    """
    try:
        areas = search_areas(client, name3)
    except OPTIONAL_LOOKUP_ERRORS:
        areas = []
    _fill_dong_sidos(cache, name2, [area for area in areas if area.name3 == name3])
    cache.setdefault((name2, name3), None)


def _fill_dong_sidos(cache: dict[tuple[str, str], str | None], name2: str, areas: list[DaangnArea]) -> None:
    """지역 검색 결과 가운데 `name2` 구의 동마다 시·도를 캐시에 채운다 (`sido_of` 의 캐시 칸).

    구·동 이름이 같은 동이 한 시·도에만 있으면 (구, 동) 칸에 그 시·도를 둔다. 여러 시·도에 있으면 (구, 동) 칸은 None 이고 그
    동마다 지역 ID 칸에 시·도를 둔다. 매물 카드의 지역 ID 가 지역 검색 결과의 ID 와 같아 (`relay_id`) 카드로 고를 수 있다.
    """
    dongs: dict[str, list[DaangnArea]] = {}
    for area in areas:
        if area.level == '동' and area.name2 == name2:
            dongs.setdefault(area.name3, []).append(area)
    for name3, found in dongs.items():
        sidos = {area.name1 for area in found}
        if len(sidos) == 1:
            cache.setdefault((name2, name3), sidos.pop())
            continue
        cache.setdefault((name2, name3), None)
        for area in found:
            if area.node_id:
                cache[(RELAY_ID_KEY, area.node_id)] = area.name1


def region_by_coordinate(client: DaangnClient, lat: float, lng: float) -> DaangnRegion:
    """좌표가 속한 당근 동을 찾는다 (`getRegionByCoordinate`).

    Raises:
        UnsupportedRegionError: 좌표가 동에 속하지 않을 때 (바다 등).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    response = client.run_request_get_region_by_coordinate(
        DaangnGetRegionByCoordinateRequestPayloadModel(
            coordinate=DaangnCoordinateInputModel(lat=lat, lon=lng)
        )
    )
    found = response.data.get_region_by_coordinate if response.data else None
    if not response.errors and (found is None or found.depth != 3 or not found.name3 or found.original_id is None):
        raise UnsupportedRegionError(
            code='REGION_NOT_FOUND',
            message=f'좌표 ({lat}, {lng}) 가 속한 당근 동을 찾지 못했습니다',
            hint='육지 안의 좌표를 주거나 동 이름으로 검색하세요',
            skip_note=f'daangn 은 좌표 ({lat}, {lng}) 가 속한 동을 찾지 못해 건너뛰었습니다',
        )
    region = unwrap_graphql(response, found, '좌표 지역')
    return DaangnRegion(
        name1=region.name1 or '',
        name2=region.name2 or '',
        name3=region.name3 or '',
        region_id=region.original_id or 0,
    )


def region_or_none(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    notes: list[str] | None = None,
) -> DaangnRegion | None:
    """좌표가 속한 당근 동 (`region_by_coordinate`). 찾지 못하거나 조회가 실패하면 None.

    결과 표시와 시·도 채우기에만 쓰는 곳에서 부른다. 요청 제한도 실패로 보고 넘어간다
    (`with_sido` 와 같다). 받아 둔 매물을 동 이름 때문에 잃지 않기 위함이다. 동을 결과에 내보내는
    곳(지도 범위 검색의 `region`)은 `notes` 를 넘겨, 동이 null 인 이유를 알린다 (`partial_failure_note`).
    시·도 채우기에만 쓰는 곳은 결과에 빠지는 게 없어(시·도는 `with_sido` 가 다시 찾는다) 넘기지 않는다.
    """
    try:
        return region_by_coordinate(client, lat, lng)
    except OPTIONAL_LOOKUP_ERRORS as exc:
        logger.warning('daangn region of coordinate (%s, %s) not found (%s); continuing without region', lat, lng, exc)
        if notes is not None:
            notes.append(note('실패', partial_failure_note(exc, '좌표 지역', '검색 중심의 동 이름을')))
        return None


def map_query_rejected_error(command: str) -> JibsaError:
    """좌표 검색(`region_by_coordinate`, 지도 범위 목록)의 쿼리 해시가 거절됐을 때의 CLI 에러.

    Args:
        command: 동 이름으로 같은 것을 찾는 명령 (`search listings`·`search complexes`·`search locations`). 좌표를 준 명령과
            같은 명령을 알려야 단지 목록을 찾던 에이전트가 매물 목록으로 가지 않는다 (2026-11-12 리뷰).
    """
    return JibsaError(
        code='UPSTREAM_ERROR',
        message='당근 지도 API 가 바뀌어(웹 쿼리 해시 거절) 좌표로 조회할 수 없습니다',
        hint=f"동 이름으로 검색하세요 (예: 'jibsa daangn {command} 역삼동'). jibsa 업데이트가 필요합니다",
    )


# 역·대학 주변 매물(`connection_edges`)은 요청당 100건까지 준다 (2026-10-10 실측: first=200 이어도 100건)
STATION_PAGE_SIZE: int = 100
# 대학 검색에서 한 번에 받는 후보 수 (요청 모델의 상한). 웹 대학 검색 쿼리는 다음 쪽을 받을 수 없어 이만큼만 본다 (`search_universities`)
UNIVERSITY_CANDIDATES: int = 50


class DaangnStation(BaseModel):
    """당근 역 검색으로 찾은 지하철역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지, 예: 역삼역)")
    ]
    lines: Annotated[
        list[str],
        Field(description='노선 (예: 서울2호선)')
    ]
    lat: Annotated[
        float,
        Field(description='역 위도')
    ]
    lng: Annotated[
        float,
        Field(description='역 경도')
    ]
    station_id: Annotated[
        str,
        Field(exclude=True, description='당근 역 ID (역 주변 매물 조회에 쓴다)')
    ]
    others: Annotated[
        list[str],
        Field(exclude=True, description="이름이 같아 고르지 않은 다른 역 ('서울5호선 양평역'). 안내에 쓴다")
    ] = []


def _station_label(lines: list[str], name: str) -> str:
    """노선을 붙인 역 이름 ('서울5호선 양평역'). 같은 이름의 역을 노선으로 구분하고, `find_station` 이 이 이름을 그대로 받는다."""
    return ' '.join(part for part in ('·'.join(lines), station_name(name)) if part)


def same_station_notes(station: DaangnStation) -> list[str]:
    """같은 이름의 역이 여러 곳이라 첫 역으로 찾았을 때의 안내. 다른 역은 노선을 붙인 이름으로 고른다."""
    if not station.others:
        return []
    return [note(
        '모호',
        f"{quoted(station.name, '이/가')} 여러 곳이라 {_station_label(station.lines, station.name)} 기준으로 찾았습니다 "
        f"(다른 곳: {', '.join(station.others)}). 다른 역이면 노선을 붙여 주세요 (예: --station '{station.others[0]}')",
    )]


def search_stations(client: DaangnClient, query: str) -> list[DaangnSubwayStationPoiModel]:
    """역 이름 앞부분이 같은 역 (`searchSubwayStationPois`, 요청 1회). 웹 검색창의 지하철 칸이다. '역' 을 떼고 묻는다.

    검색어가 '역' 하나면 떼지 않고 그대로 묻는다. 떼면 빈 검색어가 요청 모델의 최소 길이에 걸려 `ValueError` 가 되고,
    `search locations` 가 이것을 응답 형식이 바뀐 실패로 알렸다 (2026-11-12 리뷰). 당근은 '역' 에 역을 주지 않아 빈 칸이다
    (같은 날 실측).
    """
    response = client.run_request_search_subway_station_pois(
        DaangnSearchSubwayStationPoisRequestPayloadModel(
            input=DaangnQueryInputModel(query=query.removesuffix('역') or query),
        )
    )
    return unwrap_graphql(response, response.data.search_subway_station_pois if response.data else None, '역 검색')


def station_label(station: DaangnSubwayStationPoiModel) -> str:
    """노선을 붙인 역 이름 ('서울2호선 역삼역'). `--station` 이 그대로 받는다."""
    return _station_label(station.line_names, station.station_name)


def find_station(client: DaangnClient, name: str) -> DaangnStation | None:
    """이름이 지하철역이면 그 역을 돌려준다 (`searchSubwayStationPois`). 이름이 정확히 같은 역만 본다.

    역 검색은 앞부분이 같은 역을 모두 주므로 ('강남' → 강남구청, 강남대), '역' 을 뗀 이름이 같은 역만 고른다.
    같은 이름의 역이 여러 곳이면 (2026-10-11 실측: 양평 → 경의중앙선·서울5호선, 중앙 → 서울4호선·부산1호선) 처음 것을
    쓰고 (당근 웹 역 화면도 이름이 같은 첫 역으로 연다) 다른 역을 `others` 에 담는다. 노선을 붙여 주면
    ('서울5호선 양평역', 같은 이름 역 안내의 이름 그대로) 그 노선이 다 있는 역만 본다.
    """
    *line_words, last = name.split() or ['']
    query = last.removesuffix('역')
    if not query:
        return None
    wanted = [line for word in line_words for line in word.split('·') if line]
    stations = search_stations(client, query)
    same = [
        station for station in stations
        if station.station_name == query and coordinate_point(station.coordinate) is not None
        and all(line in station.line_names for line in wanted)
    ]
    if not same:
        return None
    chosen = same[0]
    point = coordinate_point(chosen.coordinate)
    assert point is not None
    return DaangnStation(
        name=station_name(chosen.station_name),
        lines=chosen.line_names,
        lat=point[0],
        lng=point[1],
        station_id=chosen.id,
        others=[_station_label(station.line_names, station.station_name) for station in same[1:]],
    )


class DaangnUniversity(BaseModel):
    """웹 지도 검색창의 대학 검색(`searchSchoolPois`)으로 찾은 대학 캠퍼스 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='캠퍼스까지 붙인 대학 이름 (예: 연세대학교 신촌캠퍼스). 당근이 캠퍼스 이름을 주지 않으면 대학 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    lat: Annotated[
        float,
        Field(description='대학 위도')
    ]
    lng: Annotated[
        float,
        Field(description='대학 경도')
    ]
    university_id: Annotated[
        str,
        Field(exclude=True, description='당근 대학 ID (대학 주변 매물 조회에 쓴다)')
    ]


def search_universities(client: DaangnClient, name: str) -> tuple[list[DaangnSchoolPoiModel], bool]:
    """대학 이름으로 캠퍼스 후보와 뒤에 더 있을 수 있는지 (`searchSchoolPois`, 요청 1회). 웹 검색창의 대학 칸이다. 좌표가 없는
    곳은 뺀다.

    웹의 이 쿼리는 다음 쪽을 받을 수 없어 서버가 받는 50곳(`UNIVERSITY_CANDIDATES`)을 한 번에 받는다 (웹 검색창은 4곳). 50곳이 다
    오면 뒤에 더 있을 수 있다. 예전에는 20곳만 받아 고려대학교(23곳)의 치의학대학원 안암캠퍼스 등 3곳이 알림 없이 빠졌다
    (2026-11-13 리뷰·실측).
    """
    response = client.run_request_search_school_pois(
        DaangnSearchSchoolPoisRequestPayloadModel(
            input=DaangnSchoolPoiSearchInputModel(name=name), first=UNIVERSITY_CANDIDATES,
        )
    )
    connection = unwrap_graphql(response, response.data.search_school_pois if response.data else None, '대학 검색')
    pois = [edge.node for edge in connection.edges if edge.node and coordinate_point(edge.node.coordinate) is not None]
    return pois, len(connection.edges) >= UNIVERSITY_CANDIDATES


def university_label(poi: DaangnSchoolPoiModel) -> str:
    """캠퍼스를 보여 주는 이름 (캠퍼스까지 붙인 `fullName`, 없으면 대학 이름). 웹 검색창의 대학 칸도 이 이름이다 (MapShell `uu`)."""
    return poi.full_name or poi.name


def _matching_universities(query: str, pois: list[DaangnSchoolPoiModel]) -> list[DaangnSchoolPoiModel]:
    """`find_university` 가 쓸 캠퍼스. 보여 주는 이름(`university_label`)이 같은 곳이 하나면 그곳, 아니면 대학 이름이나 캠퍼스까지
    붙인 이름이 같은 곳 모두다."""
    labelled = [poi for poi in pois if university_label(poi) == query]
    if len(labelled) == 1:
        return labelled
    return [poi for poi in pois if query in (poi.name, poi.full_name)]


def find_university(client: DaangnClient, name: str) -> DaangnUniversity:
    """대학 이름을 웹 대학 검색(`searchSchoolPois`)으로 캠퍼스 하나로 바꾼다 (요청 1회. 후보가 잘렸는데 못 찾으면 1회 더).

    먼저 보여 주는 이름(`university_label`, `search locations` 의 `universities[].name`)이 같은 캠퍼스를 찾아 하나면 그곳을 쓴다.
    본교는 캠퍼스 이름(`fullName`)이 없기도 해서다 (2026-11-13 실측: 고려대학교는 세종캠퍼스가 `name` '고려대학교'·`fullName`
    '고려대학교 세종캠퍼스', 본교가 `name` '고려대학교'·`fullName` null). 예전에는 대학 이름으로만 맞춰 '고려대학교' 가 늘
    REGION_AMBIGUOUS 였고 후보 '고려대학교' 를 다시 넣어도 같았다. 없거나 여럿이면 대학 이름(`name`)이나 캠퍼스까지 붙인
    이름(`fullName`)이 같은 곳을 보고, 여럿이면 웹처럼 고르게 한다 (2026-11-11 실측: 연세대학교 → 국제·미래·신촌캠퍼스, 서울대학교 →
    관악·연건·시흥·평창캠퍼스). 대학원은 `name` 이 따로라 ('경영대학원') 대학 이름에 섞이지 않는다.

    캠퍼스 이름('연세대학교 신촌캠퍼스')은 대학 이름(첫 낱말)으로 찾아 맞춘다. 그 검색이 50곳에서 잘렸는데 못 찾으면 이름 전체로 한
    번 더 찾는다 (웹 검색창에 이름 전체를 넣은 것과 같고, `search locations` 도 통째로 보낸다).

    Raises:
        RegionAmbiguousError: 이름이 같은 캠퍼스가 여러 곳일 때.
        JibsaError: 이름이 같은 캠퍼스가 여러 곳이고 후보가 잘려 전체 수를 모를 때 (REGION_AMBIGUOUS).
        RegionNotFoundError: 이름이 같은 대학이 없을 때. 비슷한 대학을 힌트로 주고, 후보가 잘렸으면 그것도 알린다.
    """
    query = ' '.join(name.split())
    if not query:
        raise RegionNotFoundError(name, hint="대학 이름(예: '연세대학교')으로 다시 주세요")
    word = query.split()[0]
    pois, cut = search_universities(client, word)
    matched = _matching_universities(query, pois)
    if not matched and cut and query != word:
        pois, cut = search_universities(client, query)
        matched = _matching_universities(query, pois)
    if len(matched) > 1:
        shown = [university_label(poi) for poi in matched[:AMBIGUOUS_CANDIDATES_SHOWN]]
        hint = f"캠퍼스까지 붙인 이름으로 다시 주세요 (예: --university '{shown[0]}')"
        if not cut:
            raise RegionAmbiguousError(query, shown, len(matched), hint=hint)
        # 받은 후보가 잘렸으면 이름이 같은 캠퍼스가 뒤에도 있을 수 있어 전체 수를 모른다 (`_choose_children` 과 같다)
        raise JibsaError(
            code='REGION_AMBIGUOUS',
            message=f"'{query}' 에 해당하는 곳이 {len(matched)}곳보다 많을 수 있습니다",
            hint=hint,
            details={'candidates': shown, 'candidate_count': None},
        )
    if not matched:
        similar = [university_label(poi) for poi in pois[:AMBIGUOUS_CANDIDATES_SHOWN]]
        hint = (
            f"이름이 같은 대학이 없습니다. 비슷한 대학: {', '.join(similar)}. 그 이름 그대로 다시 주세요"
            if similar else "대학 이름(예: '연세대학교')으로 다시 주세요"
        )
        if cut:
            hint += (
                f'. 대학 검색은 {UNIVERSITY_CANDIDATES}곳까지만 받아 찾는 캠퍼스·대학원이 그 뒤에 있을 수 있습니다. '
                "'jibsa daangn search locations <캠퍼스·대학원까지 붙인 이름>' 으로 이름을 확인해 그대로 주면 그 이름으로 다시 찾습니다"
            )
        raise RegionNotFoundError(query, hint=hint)
    poi = matched[0]
    point = coordinate_point(poi.coordinate)
    assert point is not None
    return DaangnUniversity(
        name=university_label(poi), address=poi.jibun_address, lat=point[0], lng=point[1], university_id=poi.id,
    )


class DaangnAddress(BaseModel):
    """웹 검색창 주소 모드(`searchAddress`)로 찾은 도로명 주소와 `unitByAddress` 로 받은 그 좌표."""

    model_config = ConfigDict(
        extra='forbid',
    )

    road_address: Annotated[
        str,
        Field(description="도로명 주소 (예: '서울특별시 강남구 테헤란로 152 (역삼동)')")
    ]
    region_address: Annotated[
        str | None,
        Field(description="지번 주소 (건물 이름까지, 예: '서울특별시 강남구 역삼동 737 강남파이낸스센터')")
    ] = None
    place: Annotated[
        str | None,
        Field(description='그 주소의 당근 단지·건물 이름. 당근이 모르면 null')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='그 주소가 당근 단지면 단지 ID (search listings --complex·complex 에 넘긴다). 단지가 아니면 키가 없다')
    ] = None
    lat: Annotated[
        float,
        Field(description='주소 위도')
    ]
    lng: Annotated[
        float,
        Field(description='주소 경도')
    ]

    @property
    def label(self) -> str:
        """안내에 쓰는 주소 이름 (`'서울특별시 강남구 테헤란로 152 (역삼동)' (강남파이낸스센터)`). 당근이 모르는 건물이면 이름을 붙이지 않는다."""
        return f"'{self.road_address}'" + (f' ({self.place})' if self.place else '')

    @model_serializer(mode='wrap')
    def drop_missing_complex(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.complex_id is None:
            data.pop('complex_id', None)
        return data


def search_addresses(client: DaangnClient, query: str) -> tuple[list[DaangnAddressModel], bool]:
    """도로명 주소 글자로 주소 후보 첫 쪽과 다음 쪽이 있는지 (`searchAddress`, 요청 1회). 웹 검색창 주소 모드의 주소 칸이다.

    `unitByAddress` 에 보낼 건물 관리 번호·원본 도로명 주소가 없는 후보는 쓸 수 없어 뺀다 (실측에는 없었다).
    """
    response = client.run_request_search_address(
        DaangnSearchAddressRequestPayloadModel(input=DaangnQueryInputModel(query=query), first=ADDRESS_CANDIDATES)
    )
    connection = unwrap_graphql(response, response.data.search_address if response.data else None, '주소 검색')
    candidates = [
        edge.node for edge in connection.edges
        if edge.node and edge.node.road_address and edge.node.bd_mgt_sn and edge.node.original_road_address
    ]
    return candidates, bool(connection.page_info and connection.page_info.has_next_page)


def find_address(client: DaangnClient, query: str) -> DaangnAddress:
    """도로명 주소를 웹 검색창 주소 모드처럼 후보 하나로 좁혀 좌표를 받는다 (`searchAddress` → `unitByAddress`, 요청 2회).

    웹은 주소 후보(도로명 주소, 아래에 지번 주소)를 보여 주고 사용자가 하나를 고르면 `unitByAddress` 로 좌표를 받아 지도를
    옮긴다 (MapShell `ys`·`_s`). jibsa 는 후보가 하나면 그것, 여럿이면 도로명·지번 주소가 입력과 정확히 같은 하나, 없으면
    `REGION_AMBIGUOUS` 로 도로명 주소 후보를 주어 그대로 다시 받는다. 좌표는 웹처럼 주소 좌표(`location`), 없으면 단지·건물
    좌표다.

    Raises:
        RegionAmbiguousError: 후보가 여럿이고 정확히 같은 주소가 없을 때.
        RegionNotFoundError: 후보가 없거나 당근이 그 주소의 위치를 모를 때.
        JibsaError: 후보가 첫 쪽(`ADDRESS_CANDIDATES`)보다 많고 정확히 같은 주소가 없을 때 (REGION_AMBIGUOUS, 'N곳이 넘습니다'),
            GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 웹이 주소 쿼리를 바꿨을 때.
    """
    query = ' '.join(query.split())
    address_hint = "도로명 주소(예: '테헤란로 152', '서울특별시 강남구 테헤란로 152')로 다시 주세요. 후보는 당근 웹 검색창의 주소 검색과 같습니다"
    if not query:
        raise RegionNotFoundError(query, hint=address_hint)
    candidates, more = search_addresses(client, query)
    if not candidates:
        raise RegionNotFoundError(query, hint=address_hint)
    chosen = candidates[0]
    if len(candidates) > 1 or more:
        exact = [
            candidate for candidate in candidates
            if query in (' '.join((candidate.road_address or '').split()), ' '.join((candidate.region_address or '').split()))
        ]
        if len(exact) != 1:
            shown = [candidate.road_address or '' for candidate in candidates[:AMBIGUOUS_CANDIDATES_SHOWN]]
            hint = f"후보의 도로명 주소 그대로 다시 주세요 (예: --address '{shown[0]}')"
            if not more:
                raise RegionAmbiguousError(query, shown, len(candidates), hint=hint)
            # 첫 쪽 뒤에도 후보가 있으면 전체 수를 모른다. 받은 수를 전체처럼 알리면 고를 곳이 그만큼뿐인 줄 안다 (2026-11-12
            # 리뷰·실측: '중앙로 1' 은 20곳에 hasNextPage true 인데 '20곳입니다' 였다). 다 받아 세지 않는다 (웹도 4곳씩 '더 보기').
            # 시·구를 붙이면 준다 (같은 날 실측: '부산 중앙로 1' 10곳, '부산광역시 중구 중앙로 1' 1곳)
            raise JibsaError(
                code='REGION_AMBIGUOUS',
                message=f"'{query}' 에 해당하는 주소가 {len(candidates)}곳이 넘습니다",
                hint=f'{hint}. 시·구를 앞에 붙이면 후보가 줄어듭니다',
                details={'candidates': shown, 'candidate_count': len(candidates)},
            )
        chosen = exact[0]
    assert chosen.bd_mgt_sn is not None and chosen.original_road_address is not None and chosen.road_address is not None
    response = client.run_request_unit_by_address(
        DaangnUnitByAddressRequestPayloadModel(
            input=DaangnUnitByAddressInputModel(
                juso_address=DaangnJusoAddressInputModel(
                    bd_mgt_sn=chosen.bd_mgt_sn, original_road_address=chosen.original_road_address,
                ),
            ),
        )
    )
    found = response.data.unit_by_address if response.data else None
    unit = found.unit if found else None
    if not response.errors and unit is None:
        # 웹도 이때 '주소를 찾지 못했어요' 로 끝낸다 (MapShell `ys`)
        raise RegionNotFoundError(
            query, hint=f"당근이 '{chosen.road_address}' 의 위치를 모릅니다. 다른 주소나 --lat/--lng 로 좌표를 주세요",
        )
    unit = unwrap_graphql(response, unit, '주소 위치')
    place = unit.complex or unit.building
    point = coordinate_point(unit.location) or coordinate_point(place.coordinate if place else None)
    if point is None:
        raise RegionNotFoundError(
            query, hint=f"당근이 '{chosen.road_address}' 의 좌표를 주지 않았습니다. 다른 주소나 --lat/--lng 로 좌표를 주세요",
        )
    return DaangnAddress(
        road_address=chosen.road_address,
        region_address=chosen.region_address,
        place=(place.name or place.building_name) if place else None,
        complex_id=unit.complex.original_id if unit.complex else None,
        lat=point[0],
        lng=point[1],
    )


class DaangnRealsaleRegion(BaseModel):
    """지역 실거래를 조회한 동 또는 구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description="지역 이름 (예: '서울특별시 강남구 역삼동', '서울특별시 강남구')")
    ]
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]
    level: Annotated[
        Literal['동', '구'],
        Field(description='동(읍·면 포함) 또는 구(시·군 포함, 구가 없는 세종은 세종특별자치시 전체)')
    ]
    name1: Annotated[
        str,
        Field(exclude=True, description='시/도. 후기 페이지 경로에 쓴다')
    ] = ''
    name2: Annotated[
        str,
        Field(exclude=True, description='시/군/구. 후기 페이지 경로에 쓴다')
    ] = ''
    name3: Annotated[
        str,
        Field(exclude=True, description='읍/면/동 (동일 때만)')
    ] = ''


def resolve_realsale_region(
    client: DaangnClient,
    query: str,
    *,
    sejong_whole: bool = False,
) -> tuple[DaangnRealsaleRegion, list[str]]:
    """지역 실거래·후기·단지 목록을 볼 동 또는 구를 고른다 (`resolve_area`).

    세종은 시·군·구가 없다. 세종 시·도 ID 로 부르면 실거래는 세종 전체가 오지만 단지 목록은 0건이고 구 후기 페이지도 없다
    (2026-10-11 실측: ID 1241 실거래 50건이 도담동·나성동 등 여러 동, 단지 목록 0건). 그래서 `sejong_whole` 이면 세종 전체로
    고르고, 아니면 동 이름으로 다시 묻는다.

    Raises:
        RegionNotFoundError, RegionAmbiguousError, JibsaError: `resolve_area` 와 같다.
    """
    area = resolve_area(client, query, sejong_whole=sejong_whole)
    notes = ['세종은 구가 없어 세종특별자치시 전체로 조회했습니다'] if area.level == '시도' else []
    return DaangnRealsaleRegion(
        name=area.full_name,
        region_id=area.region_id,
        level='동' if area.level == '동' else '구',
        name1=area.name1,
        name2=area.name2,
        name3=area.name3,
    ), notes
