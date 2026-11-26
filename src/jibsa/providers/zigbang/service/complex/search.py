"""역·학교·동·구 주변 아파트 단지 (search complexes)."""

import math
import re

from jibsa.core.errors import JibsaError
from jibsa.core.korean import (
    is_ri_code,
    quoted,
)
from jibsa.core.listing import (
    lookup_failure_note,
    more_hint,
    normalize_address,
    note,
    read_date,
    won_to_manwon,
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
from jibsa.providers.zigbang.api.response.complex.search import (
    ZigbangDanjiCardModel,
    ZigbangSchoolDetailModel,
    ZigbangSchoolsResponseModel,
)
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    UPSTREAM_RETRY_HINT,
    apt_complex_id,
    apt_danji_url,
    household_count,
    text_or_none,
)
from jibsa.providers.zigbang.service.complex.models import (
    ZigbangComplexPlaceType,
    ZigbangHighAdvancement,
    ZigbangMiddleAdvancement,
    ZigbangPlaceComplex,
    ZigbangPlaceComplexesResult,
    ZigbangSchoolInfo,
)
from jibsa.providers.zigbang.service.region import (
    STATION_QUERY_HINT,
    QueryPlaceKind,
    query_place_kind,
    resolve_apt_area,
    resolve_school,
    resolve_station,
)

from typing import (
    Literal,
    NamedTuple,
)


# 학교 주변 단지의 거리 문구 (예: '462m', '1.1km'). 웹 학교 응답에는 숫자 거리가 없다
DISTANCE_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d+(?:\.\d+)?)\s*(km|m)')
# 단지 카드(`danjis/details`)를 한 번에 받는 수. 웹 더보기 화면이 15곳씩 보낸다
DANJI_CARD_BATCH_SIZE: int = 15

ZigbangComplexOrder = Literal['인기', '최근입주', '시세급변동', '평당가']

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
# 주변 단지 정보(역 `subways`·학교 상세 `schools` 의 배정단지)에서 오는 값. 학교 쪽에는 주소가 없어 주소는 단지 카드에서 받는다
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
# 직방 학교급(stage) → 학교 이름의 급. 모르는 값은 원문 그대로 낸다
SCHOOL_LEVEL_BY_STAGE: dict[str, str] = {'elementary': '초등학교', 'middle': '중학교', 'high': '고등학교'}


class _ComplexPlace(NamedTuple):
    """주변 단지를 찾을 곳 하나 (역·학교·동·구)."""

    place_type: ZigbangComplexPlaceType
    name: str
    # 직방 웹 목록 이름. 리는 읍·면 지역 목록으로 찾아(`local_code_of`) 그 읍·면 이름이고, 그 밖은 name 과 같다
    list_name: str
    address: str | None
    # `danjis/ids`·`danjis/details` 에 넘기는 ID. 역은 직방 역 ID, 학교는 학교 상세 응답의 `detail.id`(지역 검색 항목의 `id` 도,
    # 학교 코드도 아니다), 동·구는 법정동 코드(동 8자리·구 5자리)를 정수로
    place_id: int
    # 주변 단지 정보를 받는 역 ID(`subways`). 학교는 학교 상세 응답을 이미 받았고, 동·구는 주변 단지 정보가 없다
    subway_id: int | None
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


def _number(value: int | float | str | None) -> int | float | None:
    """학교 숫자 칸을 수로. 직방은 같은 칸을 숫자나 글자('28', '1077702')로 주어, 글자는 정수(안 되면 실수)로 바꾼다. 읽지 못하면(빈 글자·숫자 아님·NaN·무한) None."""
    number: int | float | None
    if isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError:
            try:
                number = float(value.strip())
            except ValueError:
                return None
    else:
        number = value
    if isinstance(number, float) and not math.isfinite(number):
        return None
    return number


def school_info_of(detail: ZigbangSchoolDetailModel) -> ZigbangSchoolInfo:
    """학교 조회(`schools`)의 `detail` 을 웹 학교 화면 값으로. 못 읽은 숫자 칸은 모름(null)이고 학비·급식비는 원 단위 값을 만원으로 바꾼다 (반올림하지 않는다)."""
    stage = text_or_none(detail.stage)
    high_category = detail.only_high_new.high_category if detail.only_high_new is not None else None
    # 학교급에 맞는 진학 현황. 중학교는 `onlyMiddleNew`, 고등학교는 `onlyHighNew` 를 읽는다. 칸이 모두 비었거나(0 은 값이다) 학교급이 그 둘이 아니면 None
    advancement: ZigbangMiddleAdvancement | ZigbangHighAdvancement | None = None
    if stage == 'middle' and detail.only_middle_new is not None:
        middle = detail.only_middle_new
        advancement = ZigbangMiddleAdvancement(
            special_high=_number(middle.special),
            special_high_percent=_number(middle.special_percent),
            general_high=_number(middle.normal),
            general_high_percent=_number(middle.normal_percent),
            other=_number(middle.etc),
            other_percent=_number(middle.etc_percent),
        )
    elif stage == 'high' and detail.only_high_new is not None:
        high = detail.only_high_new
        advancement = ZigbangHighAdvancement(
            university=_number(high.normaluniv),
            university_percent=_number(high.normaluniv_percent),
            college=_number(high.college),
            college_percent=_number(high.college_percent),
            other=_number(high.etc),
            other_percent=_number(high.etc_percent),
        )
    if advancement is not None and all(value is None for value in advancement.model_dump().values()):
        advancement = None
    return ZigbangSchoolInfo(
        stage=stage,
        name=text_or_none(detail.name),
        # 모르는 학교급은 원문을 남긴다 (빈 글자는 모름)
        level=SCHOOL_LEVEL_BY_STAGE.get(stage, stage) if stage else None,
        founding_type=text_or_none(detail.sullib),
        gender=text_or_none(detail.gender),
        established_date=read_date(detail.foundation_date, '학교 설립일'),
        high_school_type=text_or_none(high_category) if stage == 'high' else None,
        students=_number(detail.all),
        male_percent=_number(detail.man_percent),
        female_percent=_number(detail.woman_percent),
        sigungu=text_or_none(detail.local2),
        sigungu_students_average=_number(detail.local),
        sigungu_male_percent=_number(detail.local_man_percent),
        sigungu_female_percent=_number(detail.local_woman_percent),
        freshmen=_number(detail.freshman),
        sigungu_freshmen_average=_number(detail.local_freshman),
        sigungu_freshmen_change_percent=_number(detail.local_increase),
        students_per_class=_number(detail.class_),
        sigungu_students_per_class=_number(detail.local_class),
        tuition_manwon=won_to_manwon(_number(detail.expense)),
        sigungu_tuition_manwon=won_to_manwon(_number(detail.local_expense)),
        meal_cost_manwon=won_to_manwon(_number(detail.meal)),
        meal_type=text_or_none(detail.meal_type),
        sigungu_meal_cost_manwon=won_to_manwon(_number(detail.meal_local)),
        advancement=advancement,
    )


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
            '. 가까운 순이 아닙니다. 주변 단지 전체에서 가까운 곳은 --order 를 빼고(인기) --limit 을 늘려 받아 distance_km 로 고르세요' if subset
            else '. 가까운 순이 아닙니다. 가까운 단지는 distance_km 로 고르세요'
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
        place_id=station.id, subway_id=station.id, notes=[],
    )


def school_has_assigned_complexes(item: ZigbangSearchItemModel) -> bool:
    """직방 웹이 그 학교의 배정단지 목록을 보여 주는지. `search complexes <학교>` 가 찾는 학교이고, 아니면 INVALID_ARGUMENT 다.

    웹은 학교 코드가 'NL_' 로 시작하면 배정단지 목록을 그리지 않는다 (2026-11-19 번들 `isAptListRender`). 코드가 없으면 웹이
    학교 화면 주소(`/home/apt/schools/{학교코드}`)를 만들 수 없다 (검색 항목의 `id` 는 학교 번호가 다시 매겨져 쓰지 않는다, `_school_place`).
    아파트 지역 매물이 역·학교를 동으로 바꿀 때 이 명령을 권할지도 이 판정으로 가른다 (`cli.zigbang`).
    """
    school_code = item.source.school_code if item.source else None
    if not school_code:
        return False
    return not school_code.startswith('NL_')


def _school_place(client: ZigbangClient, query: str) -> tuple[_ComplexPlace, ZigbangSchoolsResponseModel]:
    """학교 하나를 찾고 학교 상세(`schools`)를 받아 웹처럼 그 `detail.id` 를 단지 ID 목록 조회의 학교 ID 로 쓴다.

    지역 검색 항목의 `id` 는 쓰지 않는다. 직방이 학교 번호를 다시 매기면서(2026-11) 검색이 옛 번호를 주어 엉뚱한 학교의 단지가 나온
    적이 있고, 웹은 학교 화면을 학교 코드로 열어 학교 상세의 `detail.id` 로 배정단지를 부른다 (2026-11-19 웹 캡처·번들). 학교 상세는
    배정단지 이름·세대수·거리와 학교 정보(`school`)의 출처이기도 한 본 조회라, 실패는 그대로 올린다.

    Raises:
        JibsaError: 직방 웹이 배정단지를 보여 주지 않는 학교일 때 (INVALID_ARGUMENT). 학교 상세에 학교 정보나 그 ID 가 없을 때 (UPSTREAM_ERROR).
        RegionNotFoundError: 그 이름의 학교를 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 학교가 여러 곳일 때.
    """
    school = resolve_school(client, query)
    if not school_has_assigned_complexes(school) or school.source is None or not school.source.school_code:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"{quoted(school.name, '은/는')} 직방 웹이 배정단지 목록을 보여 주지 않는 학교입니다",
            hint='다른 학교 이름이나 역·동 이름으로 찾으세요 (예: jibsa zigbang search complexes 강남역)',
        )
    response = client.run_request_schools(ZigbangSchoolsRequestParameterModel(school_code=school.source.school_code))
    if response.detail is None or response.detail.id <= 0:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f"직방이 '{school.name}' 의 학교 정보(학교 ID)를 주지 않아 배정단지를 찾을 수 없습니다",
            hint=UPSTREAM_RETRY_HINT,
        )
    place = _ComplexPlace(
        place_type='학교', name=school.name, list_name=school.name, address=normalize_address(school.description),
        place_id=response.detail.id, subway_id=None, notes=[],
    )
    return place, response


def _region_place(client: ZigbangClient, query: str) -> _ComplexPlace:
    """동·구 하나를 찾는다. 아파트 지역 해석(`resolve_apt_region`)과 같다: 같은 이름 동·구, ○가 동, 구가 있는 시는 묻는다."""
    region, place_type, local_code, notes = resolve_apt_area(
        client,
        query,
        ri_check='단지 address 는 읍·면까지라 리 안의 단지를 가를 수 없습니다 (url 의 단지 페이지에서 확인)',
        sido_message='시·도 이름이라 단지를 찾을 수 없습니다 (동·구 단위로 조회합니다)',
        sido_hint="구나 동 이름을 주세요 (예: '송파구', '가락동'). 역·학교 이름도 받습니다 (예: '강남역', '해누리중학교')",
    )
    return _ComplexPlace(
        place_type=place_type,
        name=region.name,
        # 리는 읍·면 목록으로 찾아 웹 목록 이름도 그 읍·면이다 (`resolve_apt_region` 의 리 안내와 같은 local3)
        list_name=(region.local3 or region.name) if is_ri_code(region.legal_division_code) else region.name,
        address=region.address,
        place_id=int(local_code),
        subway_id=None,
        notes=notes,
    )


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
    except OPTIONAL_LOOKUP_ERRORS as exc:
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
    # 단지 카드 첫째 줄('송파구 가락동 · 179세대')을 (주소, 세대수) 로 나눈다. 읽지 못한 쪽은 None
    card_text = ((card.desc1 if card else None) or '').strip()
    head, separator, tail = card_text.rpartition(' · ')
    if separator and household_count(tail) is not None:
        card_address, card_households = text_or_none(normalize_address(head)), household_count(tail)
    elif household_count(card_text) is not None:
        card_address, card_households = None, household_count(card_text)
    else:
        card_address, card_households = text_or_none(normalize_address(card_text)), None
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
        household_count=households,
        distance_km=None if distance_m is None else round(distance_m / 1000, 2),
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
    역이 지역 검색 1회 + 단지 ID 1회 + 주변 단지(`subways`) 1회 + 단지 카드 15곳마다 1회 (주변 단지는 단지가 있을 때만), 학교가
    지역 검색 1회 + 학교 상세(`schools`) 1회 + 단지 ID 1회 + 단지 카드 15곳마다 1회 (배정단지가 0곳이어도 같다), 동·구가 지역
    해석 + 단지 ID 1회 + 단지 카드 15곳마다 1회다.

    학교는 웹처럼 학교 상세(`schools`)를 먼저 받아 그 `detail.id` 로 단지 ID 를 부른다 (지역 검색 항목의 `id` 는 쓰지 않는다,
    `_school_place`). 학교 상세는 본 조회라 실패하면 그대로 에러이고, 배정단지 이름·세대수·거리와 `school` 정보는 그 응답에서 꺼낸다.

    목록과 수는 `/apt/danjis/ids`(웹 패널·더보기 화면과 같은 변수: type·id·order·limit) 그대로이고 다시 세우지 않는다. 최근입주·
    시세급변동은 순서가 아니라 그 조건에 든 단지만 담은 목록이라 `total` 도 그 수다 (`SUBSET_ORDERS`). 역·학교는
    단지 이름·주소·세대수·거리를 웹이 곳을 고를 때 함께 부르는 주변 단지 정보에서 붙이고 (출력 보강, 2026-11-15 실측: 강남역
    112곳이 두 응답에 똑같이 있다), 학교 쪽에 없는 주소와 모든 곳의 둘째 줄(highlight)은 웹 더보기 화면과 같은 단지 카드에서
    붙인다. 학교 상세의 학교 정보는 결과의 `school` 로 낸다 (웹 학교 화면 값). 동·구는 주변 단지 정보가 없어 이름·주소·세대수도 카드에서
    오고 거리가 없다. 두 응답이 어긋나 주변 단지 정보나 카드에 없는 단지는 빼지 않고 그 값을 모름(null)으로 두고 알린다. 역 주변
    단지 정보와 단지 카드는 본 조회(단지 ID) 뒤에 부르는 덤이라, 실패(요청 제한 포함)하면 단지 ID 목록만 `[실패]` 안내와 함께 낸다.

    Raises:
        JibsaError: 역 이름으로 역을 찾지 못했거나, 직방 웹이 배정단지를 보여 주지 않는 학교거나, 시·도일 때, 동·구에 최근입주가
            아닌 `order` 를 줬을 때 (INVALID_ARGUMENT). 직방이 학교 상세에 학교 ID 를 주지 않았거나, 단지 수만 주고 단지 목록(`ids`)을
            주지 않았을 때 (UPSTREAM_ERROR).
        RegionNotFoundError: 이름을 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 역·학교·동·구가 여러 곳이거나, 구가 있는 시·○가 동일 때.
    """
    kind = query_place_kind(query)
    order = complex_order_of(kind, order)
    school_response: ZigbangSchoolsResponseModel | None = None
    if kind == '역':
        place = _station_place(client, query)
    elif kind == '학교':
        place, school_response = _school_place(client, query)
    else:
        place = _region_place(client, query)
    danji_order = DANJI_ORDER_BY_LABEL[order]
    # 순서·수를 주는 본 조회(학교는 학교 상세에 이어)를 먼저 받는다. 역 주변 단지 정보·카드는 덤이라 실패해도 단지 ID 목록은 버리지 않는다
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
            hint=UPSTREAM_RETRY_HINT,
        )
    all_ids = response.ids or []
    ids = all_ids[:limit]
    notes = list(place.notes)
    place_name = place.name
    around: dict[int, _AroundComplex] = {}
    school: ZigbangSchoolInfo | None = None
    around_name: str | None = None
    around_loaded = False
    if school_response is not None and school_response.detail is not None:
        # 학교는 본 조회로 받은 학교 상세에서 꺼낸다 (요청 없음. 배정단지가 없어도 학교 정보는 낸다)
        around_name = school_response.detail.name
        around = {
            apt.apartment_id: _AroundComplex(
                name=apt.name, address=None, households=household_count(apt.household), distance_m=distance_m_of(apt.distance),
            )
            for apt in school_response.apt_list or []
        }
        school = school_info_of(school_response.detail)
        around_loaded = True
    elif ids and place.subway_id is not None:
        # 역은 단지가 있을 때만 주변 단지 정보를 받는다 (덤)
        try:
            station = client.run_request_subways(ZigbangSubwaysRequestParameterModel(subway_id=place.subway_id))
            around_name, around = station.name, {
                apt.id: _AroundComplex(
                    name=apt.name,
                    address=normalize_address(apt.old_address),
                    households=household_count(apt.household),
                    distance_m=apt.distance_num,
                )
                for apt in station.apt_list or []
            }
        except OPTIONAL_LOOKUP_ERRORS as exc:
            notes.append(lookup_failure_note(
                exc, '직방', '역 주변 단지 정보',
                f'단지 {AROUND_FIELDS_BY_PLACE_TYPE["역"]}를 모릅니다 (url 의 단지 페이지에서 확인)',
            ))
        else:
            around_loaded = True
    if around_loaded:
        place_name = around_name or place.name
        unknown = sum(1 for danji_id in ids if danji_id not in around)
        if unknown:
            around_fields = AROUND_FIELDS_BY_PLACE_TYPE[place.place_type]
            notes.append(note(
                '참고',
                f'{unknown}곳은 직방 {place.place_type} 주변 단지 정보에 없어 {around_fields}를 모릅니다 (url 의 단지 페이지에서 확인)',
            ))
    cards, card_error = _danji_cards(client, ids, place, danji_order)
    card_fields = CARD_FIELDS_BY_PLACE_TYPE[place.place_type]
    missing = sum(1 for danji_id in ids if danji_id not in cards)
    if card_error is not None:
        notes.append(lookup_failure_note(
            card_error, '직방', '단지 카드', f'받지 못한 단지는 {card_fields} 값을 모릅니다 (url 의 단지 페이지에서 확인)',
        ))
    elif missing:
        notes.append(note('참고', f'{missing}곳은 직방 단지 카드에 없어 {card_fields} 값을 모릅니다 (url 의 단지 페이지에서 확인)'))
    complexes = [
        place_complex_of(danji_id, place.place_type, around.get(danji_id), cards.get(danji_id)) for danji_id in ids
    ]
    total = response.count
    # --limit 개를 직방에 그대로 요청하므로, 그보다 적게 왔으면 직방이 줄 것을 다 준 것이라 단지 수가 더 커도 더 받을 수 없다.
    # 직방이 단지 수를 주지 않으면 더 있는지 모른다. 꽉 찬 쪽이면 더 있을 수 있다고 본다
    has_more = len(all_ids) > limit or (len(all_ids) >= limit and (total is None or total > len(complexes)))
    # 동·구는 직방 웹 목록 이름이다 (리는 읍·면). 역·학교는 주변 단지 정보가 준 이름이 있으면 그 이름이다
    list_name = place_name if place.place_type in AROUND_PLACE_TYPES else place.list_name
    notes.append(_order_note(place.place_type, list_name, order))
    if place.place_type == '학교':
        notes.append(note('참고', SCHOOL_ASSIGNMENT_NOTICE))
    # 최근입주·시세급변동은 그 조건에 든 단지만 담은 목록이라 어느 목록의 수인지 밝힌다
    scope = SCOPE_NAME_BY_PLACE_TYPE[place.place_type]
    if order in SUBSET_ORDERS:
        scope = f'{order} {scope}'
    if total is not None and total > len(all_ids) and len(all_ids) < limit:
        notes.append(note('참고', f'직방이 {scope} 수를 {total}곳이라 주었지만 목록은 {len(all_ids)}곳만 와서 더 받을 수 없습니다'))
    if has_more:
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
        school=school,
        notes=notes,
    )
