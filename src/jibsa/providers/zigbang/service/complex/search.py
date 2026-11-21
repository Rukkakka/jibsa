"""역·학교·동·구 주변 아파트 단지 (search complexes)."""

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.korean import (
    is_district_code,
    is_dong_code,
    is_ri_code,
    quoted,
)
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    more_hint,
    normalize_address,
    note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.complex.search import (
    ZigbangDanjiOrder,
    ZigbangDanjiPlaceType,
    ZigbangDanjisDetailsRequestParameterModel,
    ZigbangDanjisIdsRequestParameterModel,
    ZigbangSchoolsRequestParameterModel,
    ZigbangSubwaysRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.api.response.complex.search import ZigbangDanjiCardModel
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    SCHOOL_LOOKUP_ERRORS,
    apt_complex_id,
    apt_danji_url,
    household_count,
    text_or_none,
)
from jibsa.providers.zigbang.service.region import (
    STATION_QUERY_HINT,
    QueryPlaceKind,
    best_region_item,
    local_code_of,
    query_place_kind,
    resolve_apt_region,
    resolve_school,
    resolve_station,
    search_regions,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


# 학교 주변 단지의 거리 문구 (예: '462m', '1.1km'). 웹 학교 응답에는 숫자 거리가 없다
DISTANCE_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d+(?:\.\d+)?)\s*(km|m)')
# 단지 카드(`danjis/details`)를 한 번에 받는 수. 웹 더보기 화면이 15곳씩 보낸다
DANJI_CARD_BATCH_SIZE: int = 15

ZigbangComplexOrder = Literal['인기', '최근입주', '시세급변동', '평당가']
ZigbangComplexPlaceType = Literal['역', '학교', '동', '구']
COMPLEX_ORDERS: tuple[ZigbangComplexOrder, ...] = ('인기', '최근입주', '시세급변동', '평당가')
# 웹 탭 이름 → `danjis/ids`·`danjis/details` 의 order
DANJI_ORDER_BY_LABEL: dict[ZigbangComplexOrder, ZigbangDanjiOrder] = {
    '인기': 'viewCount',
    '최근입주': 'newest',
    '시세급변동': 'priceChange',
    '평당가': 'areaPrice',
}
# 웹 탭 설명 (2026-11-19 웹 캡처). 카드 둘째 줄(highlight)의 뜻도 탭마다 다르다
COMPLEX_ORDER_DESCRIPTIONS: dict[ZigbangComplexOrder, str] = {
    '인기': '사용자들이 많이 본 단지 순서',
    '최근입주': '곧 입주 예정이거나 최근 1년 내 입주한 단지',
    '시세급변동': '1주간 시세가 급변동한 단지',
    '평당가': '평당 가격이 높은 단지 순서',
}
# 그 조건에 든 단지만 담는 탭. 순서가 아니라 부분 목록이라 total 이 그 곳의 전체 단지 수가 아니다
# (2026-11-20 실측: 강남역 인기 112곳·최근입주 2곳·시세급변동 55곳, 가락동 최근입주 1곳)
SUBSET_ORDERS: tuple[ZigbangComplexOrder, ...] = ('최근입주', '시세급변동')
# 웹 목록 이름. 동·구는 지역 화면의 최근입주 목록뿐이라 따로 없다
TAB_TITLE_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {'역': '주변단지', '학교': '배정단지', '동': '', '구': ''}
# [일부] 안내가 단지를 부르는 말. 학교는 같은 결과의 순서 안내(`TAB_TITLE_BY_PLACE_TYPE`)와 어긋나지 않게 '배정단지' 다
SCOPE_NAME_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {'역': '주변 단지', '학교': '배정단지', '동': '단지', '구': '단지'}
SEARCH_TYPE_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, ZigbangDanjiPlaceType] = {
    '역': 'subway',
    '학교': 'school',
    '동': 'local',
    '구': 'local',
}
# 주변 단지 정보(`subways`·`schools`)가 있고 거리를 주는 곳. 동·구는 없다
AROUND_PLACE_TYPES: tuple[ZigbangComplexPlaceType, ...] = ('역', '학교')
# 주변 단지 정보에서 오는 값. 학교 쪽에는 주소가 없어 주소는 단지 카드에서 받는다
AROUND_FIELDS_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {'역': '이름·주소·세대수·거리', '학교': '이름·세대수·거리'}
# 단지 카드(`danjis/details`)에서 오는 값. 동·구는 주변 단지 정보가 없어 이름·주소·세대수도 카드에서 받는다
CARD_FIELDS_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {
    '역': 'highlight',
    '학교': '주소·highlight',
    '동': '이름·주소·세대수·highlight',
    '구': '이름·주소·세대수·highlight',
}
# 웹 학교 화면 하단 안내
SCHOOL_ASSIGNMENT_NOTICE: str = '학군배정 정보는 지역에 따라 실제 배정과 다소 차이가 있을 수 있습니다 (직방 웹 학교 화면 하단 안내)'


class ZigbangPlaceComplex(BaseModel):
    """역·학교·동·구 주변 아파트 단지 하나. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (zigbang complex·search listings --complex 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='주소. 역은 지번 주소, 학교·동·구는 직방 단지 카드의 구·동까지의 주소 (예: 송파구 가락동)')
    ]
    households: Annotated[
        int | None,
        Field(description='세대수')
    ]
    distance_m: Annotated[
        int | None,
        Field(description='역·학교에서의 거리 (m). 학교는 직방이 준 거리 문구(462m·1.1km)를 m 로 바꾼 값. 동·구에는 키가 없다')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    highlight: Annotated[
        str | None,
        Field(
            description=(
                '웹 단지 카드 둘째 줄 글자 그대로. --order 마다 뜻이 다르다: 인기는 지역 순위 (예: 가락동 1위 · 송파구 1위), '
                "최근입주는 입주 시기 (예: '2026. 1 입주'), 시세급변동은 1주 시세 변동률 (예: -3.23%), 평당가는 평당가 "
                "(예: '14,758만 / 3.3㎡'). 카드를 받지 못했거나 직방이 주지 않으면 모름(null)"
            )
        )
    ]
    has_distance: Annotated[
        bool,
        Field(exclude=True, description='거리가 있는 곳(역·학교)의 단지인지. 동·구는 해당 없어 출력에서 distance_m 키를 뺀다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.has_distance:
            data.pop('distance_m', None)
        return data


class ZigbangPlaceComplexesResult(BaseModel):
    """역·학교·동·구 주변 아파트 단지 목록 (직방 웹 목록 --order 탭의 단지와 순서)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    place: Annotated[
        str,
        Field(description='찾은 역·학교·동·구 이름')
    ]
    place_type: Annotated[
        ZigbangComplexPlaceType,
        Field(description="찾은 곳의 종류. 시·군은 '구', 리는 상위 읍·면이라 '동' 이다")
    ]
    place_address: Annotated[
        str | None,
        Field(description='찾은 곳의 주소')
    ] = None
    total: Annotated[
        int | None,
        Field(
            description=(
                '고른 목록(--order)의 단지 수 (limit 적용 전). 역은 역에서 1.5km 안이다. 최근입주·시세급변동은 그 조건에 든 단지만 담아 '
                '그 곳의 전체 단지 수가 아니다. 직방이 주지 않으면 모름(null)'
            )
        )
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='받지 않은 단지가 남았는지 (이어 받기는 없다. --limit 으로)')
    ]
    complexes: Annotated[
        list[ZigbangPlaceComplex],
        Field(description='직방 웹 목록(--order 탭)의 단지. 그 탭의 순서 그대로다')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='어느 웹 목록인지·일부만 보여 준다는 안내. CLI 가 결과 위에 붙인다')
    ] = []


class _ComplexPlace(NamedTuple):
    """주변 단지를 찾을 곳 하나 (역·학교·동·구)."""

    place_type: ZigbangComplexPlaceType
    name: str
    # 직방 웹 목록 이름. 리는 읍·면 지역 목록으로 찾아(`local_code_of`) 그 읍·면 이름이고, 그 밖은 name 과 같다
    list_name: str
    address: str | None
    # `danjis/ids`·`danjis/details` 에 넘기는 ID. 역은 직방 역 ID, 학교는 학교 ID(학교 코드가 아니다), 동·구는 법정동 코드
    # (동 8자리·구 5자리)를 정수로
    place_id: int
    # 주변 단지 정보를 받는 키. 역은 역 ID(`subways`), 학교는 학교 화면 코드(`schools`), 동·구는 둘 다 없다
    subway_id: int | None
    school_code: str | None
    # 곳을 찾으며 생긴 안내 (○가 동·리 범위 안내)
    notes: list[str]


class _AroundComplex(NamedTuple):
    """역·학교 주변 단지 정보에 있는 단지 하나."""

    name: str | None
    address: str | None
    households: int | None
    distance_m: int | None


def distance_m_of(text: str | None) -> int | None:
    """학교 주변 단지의 거리 문구('462m', '1.1km')를 m 정수로. 읽지 못하면 None."""
    match = DISTANCE_TEXT_PATTERN.fullmatch((text or '').strip())
    if match is None:
        return None
    meters = float(match.group(1)) * (1000 if match.group(2) == 'km' else 1)
    return round(meters)


def _card_summary(desc1: str | None) -> tuple[str | None, int | None]:
    """단지 카드 첫째 줄('송파구 가락동 · 179세대')을 (주소, 세대수) 로 나눈다. 읽지 못한 쪽은 None."""
    text = (desc1 or '').strip()
    head, separator, tail = text.rpartition(' · ')
    if separator and household_count(tail) is not None:
        return text_or_none(normalize_address(head)), household_count(tail)
    if household_count(text) is not None:
        return None, household_count(text)
    return text_or_none(normalize_address(text)), None


def complex_order_of(kind: QueryPlaceKind, order: ZigbangComplexOrder | None) -> ZigbangComplexOrder:
    """`--order` 의 웹 탭 이름. 안 주면 역·학교는 인기, 동·구는 최근입주다.

    웹 지역 화면(`/home/apt/locals/{법정동코드}`)에는 최근입주 목록뿐이고 인기 순서는 화면 버튼으로 가는 길이 없어
    (2026-11-19 웹 조사), 동·구는 웹에 없는 목록을 만들지 않으려고 최근입주 말고는 받지 않는다.

    Raises:
        JibsaError: 동·구에 최근입주가 아닌 순서를 줬을 때 (INVALID_ARGUMENT). 지역을 찾기 전에 막는다.
    """
    if kind != '동·구':
        return order or '인기'
    if order not in (None, '최근입주'):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"동·구 단지 목록은 최근입주만 있습니다 (받지 않는 --order 값: '{order}')",
            hint='역·학교 이름으로 찾거나(예: 강남역) --order 를 빼거나 최근입주로 주세요',
        )
    return '최근입주'


def _order_note(place_type: ZigbangComplexPlaceType, name: str, order: ZigbangComplexOrder) -> str:
    """결과가 직방 웹 어느 목록인지 알리는 안내. 역·학교는 가까운 순이 아니라는 말을 덧붙인다.

    최근입주·시세급변동은 순서가 아니라 그 조건에 든 단지만 담은 목록이라 전체 단지가 아니라고 알린다 (`SUBSET_ORDERS`).
    """
    tab = ' '.join(part for part in (name, TAB_TITLE_BY_PLACE_TYPE[place_type], order) if part)
    subset = order in SUBSET_ORDERS
    if subset:
        text = f'직방 웹 {tab} 목록입니다 ({COMPLEX_ORDER_DESCRIPTIONS[order]}만 담아 그 곳의 전체 단지가 아닙니다)'
    else:
        text = f'직방 웹 {tab} 순서입니다 ({COMPLEX_ORDER_DESCRIPTIONS[order]})'
    if place_type in AROUND_PLACE_TYPES:
        text += (
            '. 가까운 순이 아닙니다. 주변 단지 전체에서 가까운 곳은 --order 를 빼고(인기) --limit 을 늘려 받아 distance_m 으로 고르세요' if subset
            else '. 가까운 순이 아닙니다. 가까운 단지는 distance_m 으로 고르세요'
        )
    return text


def _station_place(client: ZigbangClient, query: str) -> _ComplexPlace:
    station = resolve_station(client, query)
    # 역 ID 가 0 이하면 단지 목록과 주변 단지 정보를 받을 수 없다
    if station is None or station.id <= 0:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"{quoted(query, '은/는')} 직방 지역 검색에서 역으로 찾지 못했습니다",
            hint=STATION_QUERY_HINT,
        )
    return _ComplexPlace(
        place_type='역', name=station.name, list_name=station.name, address=normalize_address(station.description),
        place_id=station.id, subway_id=station.id, school_code=None, notes=[],
    )


def school_has_assigned_complexes(item: ZigbangSearchItemModel) -> bool:
    """직방 웹이 그 학교의 배정단지 목록을 보여 주는지. `search complexes <학교>` 가 찾는 학교이고, 아니면 INVALID_ARGUMENT 다.

    웹은 학교 코드가 'NL_' 로 시작하면 배정단지 목록을 그리지 않는다 (2026-11-19 번들 `isAptListRender`). 코드가 없으면 웹이
    학교 화면 주소(`/home/apt/schools/{학교코드}`)를 만들 수 없고, 학교 ID 가 0 이하여도 단지 목록을 받을 수 없다.
    아파트 지역 매물이 역·학교를 동으로 바꿀 때 이 명령을 권할지도 이 판정으로 가른다 (`cli.zigbang`).
    """
    school_code = item.source.school_code if item.source else None
    if not school_code:
        return False
    return not school_code.startswith('NL_') and item.id > 0


def _school_place(client: ZigbangClient, query: str) -> _ComplexPlace:
    school = resolve_school(client, query)
    if not school_has_assigned_complexes(school):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"{quoted(school.name, '은/는')} 직방 웹이 배정단지 목록을 보여 주지 않는 학교입니다",
            hint='다른 학교 이름이나 역·동 이름으로 찾으세요 (예: jibsa zigbang search complexes 강남역)',
        )
    return _ComplexPlace(
        place_type='학교', name=school.name, list_name=school.name, address=normalize_address(school.description),
        place_id=school.id, subway_id=None, school_code=school.source.school_code if school.source else None, notes=[],
    )


def _region_place(client: ZigbangClient, query: str) -> _ComplexPlace:
    """동·구 하나를 찾는다. 아파트 지역 해석(`resolve_apt_region`)과 같다: 같은 이름 동·구, ○가 동, 구가 있는 시는 묻는다."""
    items = search_regions(client, query)
    try:
        region, notes = resolve_apt_region(
            client,
            query,
            items=items,
            ri_check='단지 address 는 읍·면까지라 리 안의 단지를 가를 수 없습니다 (url 의 단지 페이지에서 확인)',
        )
    except RegionNotFoundError:
        best = best_region_item(query, items, require_code=True)
        code = best.source.legal_division_code if best and best.source else None
        if code is not None and not (is_district_code(code) or is_dong_code(code) or is_ri_code(code)):
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"{quoted(query, '은/는')} 시·도 이름이라 단지를 찾을 수 없습니다 (동·구 단위로 조회합니다)",
                hint="구나 동 이름을 주세요 (예: '송파구', '가락동'). 역·학교 이름도 받습니다 (예: '강남역', '해누리중학교')",
            ) from None
        raise
    if region.legal_division_code is None:
        raise RegionNotFoundError(region.name)
    return _ComplexPlace(
        place_type='구' if is_district_code(region.legal_division_code) else '동',
        name=region.name,
        # 리는 읍·면 목록으로 찾아 웹 목록 이름도 그 읍·면이다 (`resolve_apt_region` 의 리 안내와 같은 local3)
        list_name=(region.local3 or region.name) if is_ri_code(region.legal_division_code) else region.name,
        address=region.address,
        place_id=int(local_code_of(region.legal_division_code)),
        subway_id=None,
        school_code=None,
        notes=notes,
    )


def _around_complexes(
    client: ZigbangClient,
    place: _ComplexPlace,
) -> tuple[str | None, dict[int, _AroundComplex]]:
    """역·학교의 주변 단지 정보를 받는다 (요청 1회). 이름과 단지 ID 별 이름·주소·세대수·거리다. 동·구는 없다."""
    if place.subway_id is not None:
        station = client.run_request_subways(ZigbangSubwaysRequestParameterModel(subway_id=place.subway_id))
        return station.name, {
            apt.id: _AroundComplex(
                name=apt.name,
                address=normalize_address(apt.old_address),
                households=household_count(apt.household),
                distance_m=apt.distance_num,
            )
            for apt in station.apt_list or []
        }
    if place.school_code is not None:
        school = client.run_request_schools(ZigbangSchoolsRequestParameterModel(school_code=place.school_code))
        return school.detail.name if school.detail else None, {
            apt.apartment_id: _AroundComplex(
                name=apt.name, address=None, households=household_count(apt.household), distance_m=distance_m_of(apt.distance),
            )
            for apt in school.apt_list or []
        }
    return None, {}


def _danji_cards(
    client: ZigbangClient,
    ids: list[int],
    place: _ComplexPlace,
    order: ZigbangDanjiOrder,
) -> tuple[dict[int, ZigbangDanjiCardModel], Exception | None]:
    """단지 카드(이름·구동·세대수·탭별 둘째 줄)를 15곳씩 받는다 (웹 더보기 화면과 같은 크기·같은 type·id·order).

    중간에 실패(요청 제한 포함)하면 받은 카드까지 주고 그 예외를 함께 준다.
    """
    cards: dict[int, ZigbangDanjiCardModel] = {}
    try:
        for start in range(0, len(ids), DANJI_CARD_BATCH_SIZE):
            response = client.run_request_danjis_details(ZigbangDanjisDetailsRequestParameterModel(
                apt_ids=ids[start:start + DANJI_CARD_BATCH_SIZE],
                search_type=SEARCH_TYPE_BY_PLACE_TYPE[place.place_type],
                place_id=place.place_id,
                order=order,
            ))
            cards.update({card.id: card for card in response.apts or []})
    except SCHOOL_LOOKUP_ERRORS as exc:
        return cards, exc
    return cards, None


def place_complex_of(
    danji_id: int,
    place_type: ZigbangComplexPlaceType,
    around: _AroundComplex | None,
    card: ZigbangDanjiCardModel | None,
) -> ZigbangPlaceComplex:
    """단지 ID 와 주변 단지 정보·단지 카드로 결과 한 줄을 만든다. 받지 못한 값은 모름(null)이다.

    이름·주소·세대수·거리는 역이 주변 단지 정보에서, 학교가 주소만 카드에서, 동·구는 주변 단지 정보가 없어 이름·주소·세대수를
    카드에서 받는다 (동·구 줄에는 거리가 없다). 둘째 줄(highlight)은 늘 카드다.
    """
    card_address, card_households = _card_summary(card.desc1 if card else None)
    if place_type in AROUND_PLACE_TYPES:
        name = around.name if around else None
        # 학교 주변 단지 정보에는 주소가 없어 학교만 카드의 주소다. 역은 주변 단지 정보에 없으면 모름이다
        address = (around.address if around else None) if place_type == '역' else card_address
        households = around.households if around else None
        distance_m = around.distance_m if around else None
    else:
        name, address, households, distance_m = (card.name if card else None), card_address, card_households, None
    return ZigbangPlaceComplex(
        complex_id=apt_complex_id(danji_id),
        name=name,
        address=address,
        households=households,
        distance_m=distance_m,
        url=apt_danji_url(danji_id),
        highlight=text_or_none(card.desc2) if card else None,
        has_distance=place_type in AROUND_PLACE_TYPES,
    )


def search_place_complexes(
    client: ZigbangClient,
    query: str,
    *,
    order: ZigbangComplexOrder | None = None,
    limit: int = 20,
) -> ZigbangPlaceComplexesResult:
    """역·학교·동·구 주변 아파트 단지를 직방 웹 단지 목록(`order` 탭) 그대로 `limit` 곳 준다.

    검색어 끝 글자로 역('…역')·학교('…학교')·그 밖(동·구)을 가르고 지역 검색은 한 번만 부른다 (`query_place_kind`). 요청 수는
    역·학교가 지역 검색 1회 + 단지 ID 1회 + 주변 단지(역 `subways`·학교 `schools`) 1회 + 단지 카드 15곳마다 1회, 동·구가 지역
    해석 + 단지 ID 1회 + 단지 카드 15곳마다 1회다.

    목록과 수는 `/apt/danjis/ids`(웹 패널·더보기 화면과 같은 변수: type·id·order·limit) 그대로이고 다시 세우지 않는다. 최근입주·
    시세급변동은 순서가 아니라 그 조건에 든 단지만 담은 목록이라 `total` 도 그 수다 (`SUBSET_ORDERS`). 역·학교는
    단지 이름·주소·세대수·거리를 웹이 곳을 고를 때 함께 부르는 주변 단지 정보에서 붙이고 (출력 보강, 2026-11-15 실측: 강남역
    112곳이 두 응답에 똑같이 있다), 학교 쪽에 없는 주소와 모든 곳의 둘째 줄(highlight)은 웹 더보기 화면과 같은 단지 카드에서
    붙인다. 동·구는 주변 단지 정보가 없어 이름·주소·세대수도 카드에서 오고 거리가 없다. 두 응답이 어긋나 주변 단지 정보나
    카드에 없는 단지는 빼지 않고 그 값을 모름(null)으로 두고 알린다. 이 덤 조회는 본 조회(단지 ID) 뒤에 부르고, 실패(요청 제한
    포함)하면 단지 ID 목록만 `[실패]` 안내와 함께 낸다.

    Raises:
        JibsaError: 역 이름으로 역을 찾지 못했거나, 직방 웹이 배정단지를 보여 주지 않는 학교거나, 시·도일 때, 동·구에 최근입주가
            아닌 `order` 를 줬을 때 (INVALID_ARGUMENT). 직방이 단지 수만 주고 단지 목록(`ids`)을 주지 않았을 때 (UPSTREAM_ERROR).
        RegionNotFoundError: 이름을 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 역·학교·동·구가 여러 곳이거나, 구가 있는 시·○가 동일 때.
    """
    kind = query_place_kind(query)
    order = complex_order_of(kind, order)
    if kind == '역':
        place = _station_place(client, query)
    elif kind == '학교':
        place = _school_place(client, query)
    else:
        place = _region_place(client, query)
    danji_order = DANJI_ORDER_BY_LABEL[order]
    # 순서·수를 주는 본 조회를 먼저 받는다. 주변 단지 정보·카드는 덤이라 실패해도 단지 ID 목록은 버리지 않는다
    response = client.run_request_danjis_ids(ZigbangDanjisIdsRequestParameterModel(
        search_type=SEARCH_TYPE_BY_PLACE_TYPE[place.place_type],
        place_id=place.place_id,
        order=danji_order,
        limit=limit,
    ))
    if response.ids is None and (response.count or 0) > 0:
        # 단지 수만 있고 목록이 없으면 '앞 0곳입니다. --limit 을 늘리세요' 처럼 따라 해도 소용없는 안내가 나가므로 결과를 만들지 않는다
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'직방이 단지 수({response.count}곳)만 주고 단지 목록을 주지 않았습니다',
            hint=f'잠시 뒤 다시 시도하세요. 계속되면 직방 API 가 바뀐 것일 수 있어 {UPDATE_MAYBE_NEEDED}',
        )
    all_ids = response.ids or []
    ids = all_ids[:limit]
    notes = list(place.notes)
    place_name = place.name
    around: dict[int, _AroundComplex] = {}
    if ids and place.place_type in AROUND_PLACE_TYPES:
        around_fields = AROUND_FIELDS_BY_PLACE_TYPE[place.place_type]
        try:
            around_name, around = _around_complexes(client, place)
        except SCHOOL_LOOKUP_ERRORS as exc:
            notes.append(note(
                '실패',
                f'직방 {place.place_type} 주변 단지 정보를 받지 못해({type(exc).__name__}) 단지 {around_fields}를 모릅니다 (url 의 단지 페이지에서 확인)',
            ))
        else:
            place_name = around_name or place.name
            unknown = sum(1 for danji_id in ids if danji_id not in around)
            if unknown:
                notes.append(note(
                    '참고',
                    f'{unknown}곳은 직방 {place.place_type} 주변 단지 정보에 없어 {around_fields}를 모릅니다 (url 의 단지 페이지에서 확인)',
                ))
    cards, card_error = _danji_cards(client, ids, place, danji_order)
    card_fields = CARD_FIELDS_BY_PLACE_TYPE[place.place_type]
    missing = sum(1 for danji_id in ids if danji_id not in cards)
    if card_error is not None:
        notes.append(note(
            '실패',
            f'직방 단지 카드를 받지 못해({type(card_error).__name__}) 받지 못한 단지는 {card_fields} 값을 모릅니다 (url 의 단지 페이지에서 확인)',
        ))
    elif missing:
        notes.append(note('참고', f'{missing}곳은 직방 단지 카드에 없어 {card_fields} 값을 모릅니다 (url 의 단지 페이지에서 확인)'))
    complexes = [
        place_complex_of(danji_id, place.place_type, around.get(danji_id), cards.get(danji_id)) for danji_id in ids
    ]
    total = response.count
    # 직방이 단지 수를 주지 않으면 더 있는지 모른다. 꽉 찬 쪽이면 더 있을 수 있다고 본다 (catalog 과 같다)
    has_more = total > len(complexes) if total is not None else len(all_ids) >= limit
    # 동·구는 직방 웹 목록 이름이다 (리는 읍·면). 역·학교는 주변 단지 정보가 준 이름이 있으면 그 이름이다
    list_name = place_name if place.place_type in AROUND_PLACE_TYPES else place.list_name
    notes.append(_order_note(place.place_type, list_name, order))
    if place.place_type == '학교':
        notes.append(note('참고', SCHOOL_ASSIGNMENT_NOTICE))
    if has_more:
        # 최근입주·시세급변동은 그 조건에 든 단지만 담은 목록이라 어느 목록의 수인지 밝힌다
        scope = SCOPE_NAME_BY_PLACE_TYPE[place.place_type]
        if order in SUBSET_ORDERS:
            scope = f'{order} {scope}'
        head = (
            f'{scope} {total}곳 중 앞 {len(complexes)}곳입니다' if total is not None
            else f'앞 {len(complexes)}곳입니다. 직방이 {scope} 수를 주지 않아 더 있을 수 있습니다'
        )
        notes.append(note('일부', f'{head}. {more_hint(limit, MAX_LIST_LIMIT, None)}'))
    return ZigbangPlaceComplexesResult(
        place=place_name,
        place_type=place.place_type,
        place_address=place.address,
        total=total,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )
