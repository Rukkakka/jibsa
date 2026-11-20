"""원룸·빌라·오피스텔 매물 검색과 주거·아파트 매물 상세·아파트 매물 묶음 (search listings room, listing, catalog)."""

from collections.abc import (
    Callable,
    Iterator,
    Sequence,
)

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.geo import haversine_km
from jibsa.core.http import error_body
from jibsa.core.listing import (
    Listing,
    ListingDetail,
    LookupFailures,
    TradeType,
    iso_date,
    join_address,
    limit_notes,
    listing_as,
    lookup_failure_reason,
    m2_to_pyeong,
    move_in_label,
    normalize_date,
    note,
    parking_label,
    won_to_manwon,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangAptItemSource,
    ZigbangItemsListV1RequestPayloadModel,
    ZigbangSalesType,
)
from jibsa.providers.zigbang.api.request.listing import (
    ZigbangBlsSchoolZonesV1RequestParameterModel,
    ZigbangItemCatalogsItemsRequestParameterModel,
    ZigbangItemCatalogsRequestParameterModel,
    ZigbangItemsDetailV1RequestParameterModel,
    ZigbangItemsOfficetelsV1RequestParameterModel,
    ZigbangItemsOneroomsV1RequestParameterModel,
    ZigbangItemsSubwaysOfficetelsV1RequestParameterModel,
    ZigbangItemsSubwaysOneroomsV1RequestParameterModel,
    ZigbangItemsSubwaysVillasV1RequestParameterModel,
    ZigbangItemsV3RequestParameterModel,
    ZigbangItemsVillasV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangItemPinModel
from jibsa.providers.zigbang.api.response.listing import (
    ZigbangAptItemModel,
    ZigbangBlsSchoolZonesV1ResponseModel,
    ZigbangItemDetailModel,
    ZigbangItemsDetailV1ManageCostModel,
    ZigbangItemsDetailV1ResponseModel,
    ZigbangItemsResponseModel,
    ZigbangManageCostEntryModel,
    ZigbangManageCostUsageFeeModel,
)
from jibsa.providers.zigbang.service.common import (
    APT_LISTING_KIND_DESCRIPTION,
    APT_PYEONG_ID_DESCRIPTION,
    APT_PYEONG_NAME_DESCRIPTION,
    MAX_LIST_LIMIT,
    NEAREST_SCHOOLS,
    OPTIONAL_LOOKUP_ERRORS,
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    TRADE_BY_APT_TRAN_TYPE,
    ZigbangBoundary,
    ZigbangListing,
    ZigbangRegion,
    ZigbangRoomConditions,
    apt_catalog_id,
    apt_catalog_url,
    apt_complex_id,
    apt_item_source,
    apt_item_url,
    apt_listing_id,
    apt_listing_kind,
    drop_unused_scope,
    excluded_notes,
    item_url,
    officetel_complex_id,
    parse_catalog_id,
    room_filter_of,
    school_label,
    section_ordered_ids,
    sent_or_none,
    summary_to_listing,
    text_or_none,
    trade_type_of,
    tradeable_summaries,
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.region import (
    outside_boundary,
    scope_geohashes,
    to_int,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


ZigbangPropertyType = Literal['원룸', '오피스텔', '빌라']

PROPERTY_TYPES: tuple[ZigbangPropertyType, ...] = ('원룸', '오피스텔', '빌라')
# 단지·건물이 있는 유형(아파트·오피스텔)의 상세에만 있는 필드와 아파트 상세에만 있는 필드. 없는 유형은 키를 뺀다
COMPLEX_DETAIL_FIELDS: frozenset[str] = frozenset({'complex_id', 'complex_name'})
APT_ONLY_DETAIL_FIELDS: frozenset[str] = frozenset({
    'supply_area_m2', 'listing_kind', 'pyeong_id', 'pyeong_name', 'confirmed_at', 'actual_listing_checked', 'non_compliant_building',
})
# 방 하나짜리 구조. 원룸 유형은 이 구조만 서버에 요청한다 (직방 원룸 목록에는 투룸 오피스텔도 섞여 온다)
ONE_ROOM_STRUCTURES: tuple[str, ...] = ('오픈형원룸', '분리형원룸', '복층형원룸')
# 방 하나짜리 아파트는 아파트 목록에만 있고 아파트 API 에는 방 구조 조건이 없다. 공급면적 50㎡ 이하로 찾으면
# 대부분 방 1개다 (2026-10-10 실측: 역삼동 32건 중 단지별 6건 상세에서 5건이 방 1개)
GEOHASH_PRECISION: int = 5
# --details 로 상세를 붙이는 매물 수. 한 건에 요청 1회라 목록이 길면 오래 걸린다
DETAILS_MAX: int = 30
# 웹 묶음 화면이 한 번에 받는 매물 수 (`useItemCatalogDetail`, 2026-11-15 번들)
CATALOG_PAGE_SIZE: int = 20
# 기존 상세(/v3/items)의 주차 문장과 가능 여부
LEGACY_PARKING_AVAILABLE: dict[str, bool] = {'주차 가능': True, '주차 불가능': False, '주차 불가': False}
DIRECTION_LABELS: dict[str, str] = {
    'N': '북향',
    'S': '남향',
    'E': '동향',
    'W': '서향',
    'NE': '북동향',
    'NW': '북서향',
    'SE': '남동향',
    'SW': '남서향',
}
# 새 주거 상세가 아파트 매물에 주는 404 의 본문 code. 없는 매물의 404 는 code 가 없다 (2026-11-15 실측)
APT_DETAIL_NOT_SUPPORTED_CODE: str = 'ITEM_QUERY_DETAIL_SERVICE_TYPE_NOT_SUPPORTED'
# 정액 관리비 사용료 항목 (관리비 포함 항목 include 가 쓰는 이름, 응답에서 그 항목을 꺼내는 함수). 순서는 웹 매물 화면의
# 순서라 응답 모델의 필드 순서와 다르다. 필드를 직접 읽어 이름이 어긋나면 mypy 가 잡는다
USAGE_FEES: tuple[tuple[str, Callable[[ZigbangManageCostUsageFeeModel], ZigbangManageCostEntryModel | None]], ...] = (
    ('전기', lambda usage: usage.electricity),
    ('수도', lambda usage: usage.water),
    ('가스', lambda usage: usage.gas),
    ('난방', lambda usage: usage.heating),
    ('인터넷', lambda usage: usage.internet),
    ('TV', lambda usage: usage.tv),
)
NORMAL_MANAGE_COST_LABEL: str = '일반(공용) 관리비'
ETC_MANAGE_COST_LABEL: str = '기타 관리비'
# 웹 매물 화면의 관리비 항목 순서 (`getFixedManageCostDetailKeys`, 2026-11-15 번들). 웹은 include 목록도 이 이름 순서로
# 정렬하고, 이 이름이 아니면 원래 순서대로 뒤에 둔다. 웹의 기타 관리비 이름은 붙여 쓴 '기타관리비' 라, include 에
# 띄어 써 오는 '기타 관리비' 는 맨 뒤로 간다 (2026-11-15 실측: 50905571 의 include 가 일반·기타·인터넷·TV 순)
MANAGE_COST_ORDER: dict[str, int] = {
    name: index for index, name in enumerate((NORMAL_MANAGE_COST_LABEL, *(label for label, _ in USAGE_FEES), '기타관리비'))
}
FIXED_MANAGE_COST_TYPE: str = 'FixedManageCost'
UNKNOWN_MANAGE_COST_TYPE: str = 'UnknownManageCost'


class ZigbangSearchResult(BaseModel):
    """매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float | None,
        Field(description='검색 반경 (km). 동 경계로 찾았으면 키가 없다')
    ] = None
    boundary: Annotated[
        str | None,
        Field(description='반경 대신 경계 안을 찾은 동 이름. 반경으로 찾았으면 키가 없다')
    ] = None
    total: Annotated[
        int,
        Field(description=(
            '범위(반경·동 경계, 역은 서버가 준 역 반경) 안 서로 다른 매물 수 근사값 (limit 적용 전, 거래 불가를 빼기 전). '
            '종류 여럿에 함께 있는 매물은 한 번만 센다'
        ))
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위 안에 아직 받지 않은 매물이 남은 종류가 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 ({"offsets": {종류: 그 종류 직방 목록에서 다음에 받을 자리}}). 더 없으면 None')
    ] = None
    listings: Annotated[
        # 오피스텔의 complex_id 까지 내보낸다 (SerializeAsAny 가 없으면 공통 Listing 필드만 나간다)
        list[SerializeAsAny[Listing]],
        Field(description='직방 목록 순서의 매물. 종류 여럿이면 요청한 종류 순서로 종류별 묶음을 잇는다')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='매물이 limit 보다 많아 일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 반경과 동 경계 중 쓰지 않은 쪽은 해당 없다
        return drop_unused_scope(handler(self))


class ZigbangDetailedListing(ZigbangListing):
    """`--details` 로 매물 상세를 1회 더 받아 건물 용도를 붙인 원룸·오피스텔·빌라 매물."""

    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (예: 다가구, 다세대, 근린생활시설). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다. 모르면 null')
    ] = None


class ZigbangListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 매물. `complex_id`·`complex_name` 은 아파트·오피스텔, 아파트 전용 필드(`APT_ONLY_DETAIL_FIELDS`)는 아파트에만 있다."""

    residence_type: Annotated[
        str | None,
        Field(description="건축물 용도 (예: 다가구, 다세대, 오피스텔). 중개사 입력 문구라 같은 용도도 다가구·다가구주택처럼 다르게 온다. 아파트는 웹의 '중개대상물 종류' (예: 아파트)이고 제휴 매물은 null")
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지·건물 ID (예: apt-68579, officetel-20227). zigbang complex·items 에 넘긴다')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름과 동 (아파트) 또는 건물 이름 (오피스텔)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡, 아파트만)')
    ] = None
    total_parking_count: Annotated[
        int | float | None,
        Field(description='총 주차 대수 (아파트는 단지 전체). 직방이 소수(0.4)로 주기도 해 그대로 준다')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='주차 계산에 쓰는 매물 측 세대수. 단지 총세대수와 다를 수 있다. 아파트는 아파트 상세에 없어 null')
    ] = None
    direction_criterion: Annotated[
        str | None,
        Field(description='방향 기준 (안방·거실)')
    ] = None
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 학교군 안 가까운 중·고등학교 2곳씩 (원룸·빌라·오피스텔만, 아파트는 complex 에서). 모르면 null')
    ] = None
    listing_kind: Annotated[
        str | None,
        Field(description=APT_LISTING_KIND_DESCRIPTION)
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description=APT_PYEONG_ID_DESCRIPTION + ' (아파트만)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description=APT_PYEONG_NAME_DESCRIPTION + ' (아파트만)')
    ] = None
    confirmed_at: Annotated[
        str | None,
        Field(description="직방이 매물을 마지막으로 확인한 날짜 (YYYY-MM-DD, 한국 시간. 아파트만). 웹 매물 화면은 이 시각으로 '2주 전 확인' 처럼 상대 표기를 보여 준다. 모르면 null")
    ] = None
    actual_listing_checked: Annotated[
        bool | None,
        Field(description="직방 웹의 '실매물 확인' 배지 (아파트만). 직방이 뜻을 설명하지 않는다. 모르면 null")
    ] = None
    non_compliant_building: Annotated[
        bool | None,
        Field(description='위반 건축물 여부 (아파트만. 웹 매물 화면의 위반 건축물 해당·해당없음). 직방이 주지 않으면(제휴 매물) null')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        # 아파트 학군은 단지 정보(zigbang complex)에서 준다
        if self.property_type == '아파트':
            fields = fields | {'schools'}
        if self.property_type not in ('아파트', '오피스텔'):
            fields = fields | COMPLEX_DETAIL_FIELDS
        if self.property_type != '아파트':
            fields = fields | APT_ONLY_DETAIL_FIELDS
        return fields


def _distance_text(meters: int | None) -> str | None:
    if meters is None:
        return None
    return f'{meters}m' if meters < 1000 else f'{meters / 1000:.1f}km'


def building_schools(response: ZigbangBlsSchoolZonesV1ResponseModel) -> list[str]:
    """원룸·빌라·오피스텔 건물 학군을 `danji_schools` 와 같은 문구로 바꾼다 (거리는 m 정수로 온다)."""
    labels: list[str | None] = []
    if response.elementary:
        labels += [
            school_label(school.name, '배정', _distance_text(school.distance))
            for school in response.elementary.schools
        ]
    for level in (response.middle, response.high):
        if level:
            zone = level.school_zone.zone_name if level.school_zone else None
            nearest = sorted(level.schools, key=lambda school: school.distance if school.distance is not None else 10**9)
            labels += [
                school_label(school.name, zone, _distance_text(school.distance))
                for school in nearest[:NEAREST_SCHOOLS]
            ]
    return [label for label in labels if label]


def _usage_fee_items(usage: ZigbangManageCostUsageFeeModel | None) -> list[tuple[str, ZigbangManageCostEntryModel]]:
    """사용료 여섯 항목을 웹 순서로 (이름, 항목) 으로. 키가 빠진 항목은 웹처럼 해당 없음으로 본다."""
    return [
        (label, (entry_of(usage) if usage else None) or ZigbangManageCostEntryModel(type='not_applicable'))
        for label, entry_of in USAGE_FEES
    ]


def manage_cost_includes(manage: ZigbangItemsDetailV1ManageCostModel) -> list[str] | None:
    """관리비에 든 항목을 웹 매물 화면(`renderManageCostData`, 2026-11-15 번들)과 같은 규칙으로 고른다.

    `include` 목록은 실비로 따로 내는 사용료까지 포함으로 담는다. 웹은 정액 관리비(`FixedManageCost`)면 항목별로
    '일반(공용) 관리비 220,000원 / 전기 실비 …' 처럼 보여 주므로, 관리비 금액에 실제로 든 항목만 낸다: 금액이 있는
    일반(공용) 관리비, 정액 사용료 항목, 금액이 있는 기타 관리비. 실비·해당 없음·미제공 항목은 넣지 않는다.
    항목별 내역을 알리지 않았거나(`hasInformed` false, 또는 키가 없는데 여섯 항목이 모두 미제공·해당 없음) 실비 관리비이거나
    `detail` 이 없으면 웹처럼 `include` 목록을 `MANAGE_COST_ORDER` 순서로 정렬해 낸다. `hasInformed` 가 null 로 오면 웹처럼
    (`void 0===e.hasInformed` 는 null 이 아니다) 항목별로 본다. `detail` 이 없고 관리비 금액도 없으면(0·null) 웹은
    '관리비 없음' 만 보여 주고 항목을 그리지 않아 빈 목록이다. 정액 관리비의 항목도 웹 순서다
    (일반(공용) 관리비, 사용료, 기타 관리비). 확인 불가(`UnknownManageCost`)는 부르는 쪽(`detail_to_listing`)이 거른다.
    """
    listed = sent_or_none(manage, 'includes', sorted(
        (entry.name for entry in manage.includes if entry.name),
        key=lambda name: MANAGE_COST_ORDER.get(name, len(MANAGE_COST_ORDER)),
    ))
    detail = manage.detail
    if detail is None:
        # 웹(`!manageCost.amount`)처럼 `amount` 로 본다. `amount` 가 비고(0·null) `fee` 만 있는 매물은 `detail_to_listing` 이 먼저 모름으로 뺀다
        return listed if manage.amount else []
    # 리뷰 오탐 (2026-11-15): 실비 관리비(ActualManageCost)도 웹은 include 이름으로 포함 항목을 그린다. detailIncludes 는
    # '전기료'·'수도료' 처럼 이름이 달라 쓰면 웹과 어긋난다 (실측 50987398 웹 '일반(공용) 관리비, 전기, 수도, 가스, 기타 관리비'
    # = include. 실비 매물 6건 모두 두 목록의 항목은 같고 이름만 다름)
    if detail.type != FIXED_MANAGE_COST_TYPE:
        return listed
    usage = _usage_fee_items(detail.usage_fee)
    if detail.has_informed is False:
        return listed
    if 'has_informed' not in detail.model_fields_set and all(entry.type in ('unknown', 'not_applicable') for _, entry in usage):
        return listed
    includes: list[str] = []
    if detail.normal_manage_cost and (detail.normal_manage_cost.amount or 0) > 0:
        includes.append(NORMAL_MANAGE_COST_LABEL)
    includes += [label for label, entry in usage if entry.type == 'fixed' and (entry.amount or 0) > 0]
    etc = detail.etc_manage_cost
    if etc and not etc.is_unknown and (etc.amount or 0) > 0:
        # 리뷰 오탐 (2026-11-15): 중개사가 쓴 설명을 이름으로 내는 것이 맞다. 웹(`renderManageCostData`)도 '기타 관리비' 소제목
        # 아래 줄의 이름표로 description 을 쓴다 (실측 50893092: '주차비 5,000원')
        includes.append(etc.description or ETC_MANAGE_COST_LABEL)
    return includes


def _manage_cost_manwon(manage: ZigbangItemsDetailV1ManageCostModel) -> float | None:
    """주거 상세 관리비 금액 (만원). 웹 매물 화면의 관리비 절이 그리는 금액을 원 단위까지 낸다.

    내역이 있으면 웹(`renderManageCostData`, 2026-11-15 번들)처럼 정액 `totalAmount`·실비 `avgManageCost`(원)다. 웹은 `fee` 를
    읽지 않고, 내역이 없으면 `amount` × 10000 원을 그린다. `amount`(만원)는 직방이 0.1만원 아래를 버린 값이라(실측 51105591:
    amount 37.5, fee 375700) 그때는 목록 카드처럼 원 단위 `fee` 를 쓴다 (개발 가이드 "웹과 다른 점"). 원 단위 금액이 없을 때만
    `amount` 다. 내역이 없고 금액도 없으면(0·null) 웹은 '관리비 없음' 이라 0 이다 (포함 항목도 빈 목록, `manage_cost_includes`).
    """
    detail = manage.detail
    if detail is not None:
        won = detail.total_amount if detail.type == FIXED_MANAGE_COST_TYPE else detail.avg_manage_cost
        if won is not None:
            return won_to_manwon(won)
    if manage.fee is not None:
        return won_to_manwon(manage.fee)
    return (manage.amount or 0) if detail is None else manage.amount


def detail_to_listing(
    response: ZigbangItemsDetailV1ResponseModel,
    *,
    legacy: ZigbangItemDetailModel | None = None,
    registered_at: str | None = None,
    short_term: bool = False,
) -> ZigbangListingDetail:
    """새 주거 상세(`/items/{id}/detail`) 응답을 `ZigbangListingDetail` 로 바꾼다 (원룸·빌라·오피스텔).

    사진·본문·중개사 정보는 응답에 있어도 옮기지 않는다 (원 사이트에서 확인).
    입주일(`moveInAt`)이 null 이면 기존 상세(`/v3/items`, `legacy`)의 입주 문구로 보완하고, 그때는 주차도
    기존 상세의 문구를 쓴다. 상세 응답에는 등록일이 없어 요약 응답의 `reg_date` 를 `registered_at` 으로 받는다.
    없으면 모름(None). 단기임대 여부도 상세 응답에는 없어 요약 응답(`trade_type_of`)에서 `short_term` 으로 받는다.
    관리비가 확인 불가(`UnknownManageCost`)면 웹처럼 금액도 항목도 모름(None)이다. 금액은 `_manage_cost_manwon` 이 정한다.
    """
    item = response.item
    residence = item.residence
    price = item.price
    manage = item.manage_cost
    if manage is not None and manage.detail is not None and manage.detail.type == UNKNOWN_MANAGE_COST_TYPE:
        # 웹은 '관리비 확인 불가' 로 보여 주고 금액도 항목도 내지 않는다
        manage = None
    if manage is not None and manage.detail is None and not manage.amount and manage.fee:
        # 내역이 없으면 웹은 `amount` 만 보고(0·null) '관리비 없음' 으로 보여 주는데 `fee` 에는 금액이 있다. 어느 쪽이 맞는지
        # 몰라 틀릴 수 있는 금액을 내지 않고 금액도 항목도 모름(None)이다 (2026-11-15 사용자 결정)
        manage = None
    manage_cost = _manage_cost_manwon(manage) if manage is not None else None
    origin = item.address.origin
    address = origin.full_text if origin else None
    if item.address.jibun and origin and origin.local1:
        address = f'{origin.local1} {item.address.jibun}'
    move_in: str | None
    if residence.move_in_at is not None:
        extra = residence.move_in_extra
        move_in = move_in_label(f'{residence.move_in_at} ({extra})' if extra else residence.move_in_at)
    else:
        # null을 즉시 입주로 추측하지 않고 기존 상세의 문장('즉시 입주 가능 (협의 가능)')을 같은 꼴로 바꿔 쓴다
        move_in = move_in_label(legacy.movein_date) if legacy else None
    parking = parking_label(residence.parking)
    if parking is None and legacy is not None and legacy.parking_available_text is not None:
        # 기존 상세는 '주차 가능'·'주차 불가능' 문장으로 준다 (2026-10-15 실측 6건). 다른 문장이면 그대로 둔다
        text = legacy.parking_available_text
        parking = parking_label(LEGACY_PARKING_AVAILABLE.get(text)) or text

    detail = ZigbangListingDetail(
        source='zigbang',
        id=str(item.id),
        url=item_url(item.service_type, item.id),
        trade_type='단기임대' if short_term and item.sales_type == '월세' else item.sales_type,
        property_type=item.service_type,
        room_type=residence.room_type,
        title=item.title,
        price_manwon=price.sales if price and item.sales_type == '매매' else None,
        deposit_manwon=price.deposit if price and item.sales_type != '매매' else None,
        rent_manwon=price.rent if price and item.sales_type == '월세' else None,
        manage_cost_manwon=manage_cost,
        area_m2=residence.area_m2,
        area_pyeong=m2_to_pyeong(residence.area_m2),
        floor=residence.floor,
        building_floor=residence.building_floor,
        address=address,
        lat=item.location.lat if item.location else None,
        lng=item.location.lng if item.location else None,
        registered_at=normalize_date(registered_at),
        bathroom_count=to_int(residence.bathroom_count),
        direction=DIRECTION_LABELS.get(residence.direction or '', residence.direction),
        move_in=move_in,
        approved_at=normalize_date(residence.approved_at),
        parking=parking,
        elevator=residence.elevator,
        options=sent_or_none(item, 'options', [option.name for option in item.options if option.name]),
        manage_cost_includes=manage_cost_includes(manage) if manage else None,
        nearby_subways=sent_or_none(response, 'subways', [
            f'{subway.name} ({subway.description})' if subway.description else subway.name
            for subway in response.subways
        ]),
        # 표시 문구를 정규화하지 않는다. 코드는 원룸·빌라가 대부분 '그외'라 문구가 더 정확하다 (2026-10-10 실측).
        # 원본 문구 끝에 공백이 붙어 오기도 해('주택   ') 앞뒤 공백만 뗀다
        residence_type=(residence.residence_description or residence.residence_type or '').strip() or None,
        total_parking_count=residence.total_parking_count,
        household_count=residence.household_count,
        direction_criterion=residence.direction_criterion,
    )
    if item.service_type == '오피스텔':
        return detail.model_copy(update={
            'complex_id': officetel_complex_id(item.building_id) if item.building_id else None,
            'complex_name': response.danji.name if response.danji else None,
        })
    return detail


def attach_building_use(client: ZigbangClient, result: ZigbangSearchResult) -> ZigbangSearchResult:
    """목록 매물마다 상세(`/items/{id}/detail`)를 1회씩 받아 건물 용도(`residence_type`)와 사용승인일을 붙인다 (`--details`).

    목록 API 는 건물 용도·사용승인일을 주지 않는다 (2026-10-15 실측: `items/list` 요약에 용도 필드 없음). 근린생활시설·고시원처럼
    전입신고가 막힐 수 있는 매물을 상세를 하나씩 열지 않고 고르게 한다. 사용승인일도 같은 상세에 있어 함께 채운다
    (2026-10-31 에이전트 검증: 직방에는 연식 조건이 없어 '10년 이내' 를 확인하려고 상세를 8회씩 따로 불렀다).
    앞 `DETAILS_MAX` 건만 보고, 상세에서 거래가 끝난 매물(404·`status` 가 open 이 아님)은 뺀다 (만료 매물은 내보내지 않는다).
    그 밖의 덤 조회 실패(`OPTIONAL_LOOKUP_ERRORS`: 네트워크·상태 코드·응답 형식 오류·요청 제한)는 그 매물을 목록 값 그대로 두고
    건물 용도는 모름(null)으로 둔다. 상세 한 건 때문에 이미 받은 목록 전체를 버리지 않는다 (2026-11-19 리뷰). 요청 제한이면
    다음 요청도 같은 제한에 걸리므로 (앞에 다른 실패가 있었어도) 남은 매물의 상세는 요청하지 않고 같게 둔다. 못 붙인 매물 수와
    이유(거절·응답 형식 변경이 한 건이라도 있으면 그 이유(요청 제한도 왔으면 덧붙임), 없으면 요청 제한, 없으면 첫 실패 이유.
    `LookupFailures`)는 `[실패]` 안내 하나로 알린다.
    """
    listings: list[Listing] = []
    gone = 0
    # 상세를 못 붙인 매물 수(실패한 것 + 요청 제한 뒤라 요청하지 않은 것)와 안내할 이유
    failures = LookupFailures()
    for index, listing in enumerate(result.listings):
        if not isinstance(listing, ZigbangListing):
            listings.append(listing)
            continue
        if index >= DETAILS_MAX:
            # 상세를 받지 않은 매물도 건물 용도는 모름(null)으로 낸다. 원래 모델 그대로 두면 residence_type 키가 빠져
            # 출력 규약상 해당 없음으로 읽힌다 (키 없음 = 해당 없음, null = 모름. 2026-10-28 실측: 역삼동 원룸 --limit 31
            # --details 의 31번째가 null, 앞 30건은 용도가 붙음)
            listings.append(listing_as(ZigbangDetailedListing, listing))
            continue
        if failures.stopped:
            failures.skip()
            listings.append(listing_as(ZigbangDetailedListing, listing))
            continue
        try:
            with unavailable_on_404(listing.id):
                item = client.run_request_items_detail_v1(
                    ZigbangItemsDetailV1RequestParameterModel(item_id=int(listing.id))
                ).item
        except ListingUnavailableError:
            gone += 1
            continue
        except OPTIONAL_LOOKUP_ERRORS as exc:
            failures.add(exc)
            listings.append(listing_as(ZigbangDetailedListing, listing))
            continue
        if item.status != 'open':
            gone += 1
            continue
        residence = item.residence
        building_use = (residence.residence_description or residence.residence_type or '').strip() or None
        approved = listing.model_copy(update={'approved_at': normalize_date(residence.approved_at) or listing.approved_at})
        listings.append(listing_as(ZigbangDetailedListing, approved, residence_type=building_use))
    notes = []
    if gone:
        # 검색이 만든 안내('이 N건이 전부입니다' 등)는 빼기 전 개수라 returned 와 다를 수 있다
        notes.append(note('제외', f'{gone}건은 상세를 보니 거래가 끝나 뺐습니다 (앞 안내의 건수는 빼기 전 기준)'))
    reason = failures.reason(lambda exc: lookup_failure_reason(exc, '직방', '매물 상세'))
    if reason is not None:
        notes.append(note(
            '실패',
            f'매물 {failures.count}건의 상세(건물 용도·사용승인일)를 받지 못해 목록 값만 넣었습니다: {reason}',
        ))
    if len(result.listings) > DETAILS_MAX:
        notes.append(f'건물 용도·사용승인일(--details)은 앞 {DETAILS_MAX}건에만 붙였습니다')
    return result.model_copy(update={'listings': listings, 'returned': len(listings), 'notes': result.notes + notes})


def get_apt_listing(client: ZigbangClient, item_id: int, item_source: ZigbangAptItemSource = 'zigbang') -> ZigbangListingDetail:
    """아파트 매물(직방, 또는 `coalition` 이면 집주인이 내놓았거나 신규분양인 제휴 매물) 하나의 상세를 아파트 상세(`/apt/item-catalogs/items`) 1회로 조회한다.

    웹 아파트 매물 화면(`/home/apt/item/v2/{id}/{출처}/0`)이 부르는 상세는 이것 하나다 (2026-11-15 실측). 주거 상세·`/v3/items` 는
    아파트에 404 다. 상태 필드가 없고 내려간 매물은 404 다. 이 상세는 주거 상세가 아파트 매물이라고 알린 숫자 ID 나
    `coalition-` ID 로만 부르므로, 404 는 다른 소스 ID 가 아니라 직방 아파트 매물이 없거나 내려간 것이다 (`APT_ITEM_NOT_FOUND`).

    Raises:
        ListingUnavailableError: 없는 매물(404, `APT_ITEM_NOT_FOUND`)이거나 거래 유형을 모를 때.
    """
    listing_id = apt_listing_id(item_id, item_source)
    with unavailable_on_404(listing_id, reason='APT_ITEM_NOT_FOUND'):
        apt = client.run_request_item_catalogs_items(
            ZigbangItemCatalogsItemsRequestParameterModel(item_id=item_id, item_source=item_source)
        ).item
    return apt_item_to_listing(apt, item_source)


def apt_item_to_listing(
    apt: ZigbangAptItemModel,
    item_source: ZigbangAptItemSource,
    trade_type: TradeType | None = None,
) -> ZigbangListingDetail:
    """아파트 상세(`/apt/item-catalogs/items`) 응답을 `ZigbangListingDetail` 로 바꾼다 (직방·제휴 매물).

    거래 유형은 `trade_type` 을 주면 그것을, 아니면 응답의 `tranType` 을 쓴다. 묶음(`get_catalog`)은 요청한 거래 유형으로
    받은 매물이라 그 거래 유형을 넘긴다 (웹 묶음 화면도 매물의 `tranType` 으로 거르지 않는다).

    제목·층·방향이 빈 글자면 주소처럼 모름(None)이다. 층은 직방 매물이면 '저'·'중'·'고' 그대로다 (웹 아파트 화면에도 정확한 층이 없다). 주소는 지번 주소(`oldAddress`)다.
    직방 매물은 지번이 빈 문자열이라 모름(None)이다: 응답의 `address` 는 도로명이라 매물 출력에 내지 않고(출력 규약), 웹 매물
    화면도 지번을 보여 주지 않는다 (2026-11-15 웹 캡처: 단지 API 도 부르지 않는다). 지번은 단지(`complex_id`)에서 본다.
    등록일·인근 역·엘리베이터·방 구조·세대수는 이 응답에 없어 모름(None)이다. 건축물 용도(`residence_type`)는 `realType`(중개대상물 종류, 예 '아파트')이고 제휴 매물은 키가 없어 모름(None)이다.
    평형(`roomTypeInfo`)은 ID·이름(평 기준)으로 내고, 확인 시각(`effectivenessUpdatedAt`)은 웹의 '2주 전 확인' 대신 한국 날짜로 낸다.
    실매물 확인 배지·위반 건축물 여부는 직방이 준 bool 그대로다 (위반 건축물은 제휴 매물에 키가 없어 모름(None)). 총 주차 대수(`parkingCount`)는 제휴 매물에 오지 않아 모름(None)이다. 관리비는
    확인 불가거나 모르는 종류거나 0원이면 모름(None)이다. 옵션은 아파트 상세에 옵션 칸이 없어 (2026-10-11 실측 19건) 모름(None)으로 둔다.

    Raises:
        ListingUnavailableError: `trade_type` 을 주지 않았는데 응답의 거래 유형을 모를 때 (UNKNOWN_TRADE_TYPE).
    """
    listing_id = apt_listing_id(apt.item_id, item_source)
    trade_type = trade_type or TRADE_BY_APT_TRAN_TYPE.get(apt.tran_type or '')
    if trade_type is None:
        raise ListingUnavailableError('zigbang', listing_id, reason='UNKNOWN_TRADE_TYPE')
    is_sale = trade_type == '매매'
    cost = apt.manage_cost.amount if apt.manage_cost else None
    # '거실기준' 을 새 주거 상세의 방향 기준('거실')과 같은 꼴로 맞춘다
    criterion = (apt.direction_base or '').strip().removesuffix('기준').strip() or None
    direction = text_or_none(apt.direction)
    room_type = apt.room_type_info
    return ZigbangListingDetail(
        source='zigbang',
        id=listing_id,
        url=apt_item_url(apt.item_id, item_source),
        trade_type=trade_type,
        property_type='아파트',
        title=text_or_none(apt.item_title),
        price_manwon=apt.deposit if is_sale else None,
        deposit_manwon=None if is_sale else apt.deposit,
        rent_manwon=apt.rent if trade_type == '월세' else None,
        # 0원이면 웹(`getManagementFee`, 2026-11-15 번들)은 관리비 칸을 빈 글자로 두어 '관리비 없음' 이 아니라 모름(None)이다
        manage_cost_manwon=won_to_manwon(cost.monthly_cost) if cost and cost.monthly_cost else None,
        area_m2=apt.size_m2,
        area_pyeong=m2_to_pyeong(apt.size_m2),
        floor=text_or_none(apt.floor),
        building_floor=str(apt.building_floor) if apt.building_floor is not None else None,
        address=text_or_none(apt.old_address),
        room_count=apt.room_count,
        bathroom_count=apt.bathroom_count,
        direction=DIRECTION_LABELS.get(direction.upper(), direction) if direction else None,
        move_in=move_in_label(apt.movein_date),
        approved_at=normalize_date(apt.approval_date),
        parking=parking_label(None, f'세대당 {apt.parking_count_by_household:g}대') if apt.parking_count_by_household is not None else None,
        options=None,
        manage_cost_includes=cost.include_items if cost else None,
        complex_id=apt_complex_id(apt.area_danji_id) if apt.area_danji_id else None,
        complex_name=join_address(apt.area_danji_name, apt.area_building_name),
        supply_area_m2=apt.size_contract_m2,
        total_parking_count=apt.parking_count,
        direction_criterion=criterion,
        listing_kind=apt_listing_kind(apt.item_type),
        pyeong_id=room_type.danji_room_type_id if room_type else None,
        pyeong_name=text_or_none(room_type.room_type_title.p) if room_type and room_type.room_type_title else None,
        confirmed_at=iso_date(apt.effectiveness_updated_at),
        actual_listing_checked=apt.is_actual_item_checked,
        non_compliant_building=apt.has_violations,
        residence_type=text_or_none(apt.real_type),
    )


class ZigbangCatalogResult(BaseModel):
    """같은 호·거래 유형의 아파트 매물 묶음 (catalog)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    catalog_id: Annotated[
        str,
        Field(description='묶음 ID (검색 결과의 catalog_id)')
    ]
    url: Annotated[
        str,
        Field(description='직방 웹 묶음 화면 (중개사별 매물 목록)')
    ]
    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형')
    ]
    total: Annotated[
        int | None,
        Field(description='묶음의 매물 수 (직방 itemCount. 상세를 볼 수 없는 출처도 센다). 직방이 묶음 수를 주지 않으면 모름(null)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description=(
            f'직방이 알린 묶음 매물 수(total)보다 덜 받았는지 (앞 {MAX_LIST_LIMIT}건까지만 받고, 직방이 다음 쪽을 주지 않으면 거기서 멈춘다). '
            f'total 이 null 이면 {MAX_LIST_LIMIT}건에 닿아 멈췄고 마지막 쪽이 가득 찼을 때 true (더 있을 수 있음)'
        ))
    ] = False
    listings: Annotated[
        list[ZigbangListingDetail],
        Field(description='묶음 매물 (직방이 준 순서 그대로). 매물마다 listing 상세와 같은 필드')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='뺀 매물·일부만 받았다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def _empty_catalog_error(catalog_id: str) -> JibsaError:
    """묶음에 매물이 없을 때의 에러. 첫 쪽이 404 든 200 빈 목록이든 같은 에러를 낸다."""
    return JibsaError(
        code='LISTING_UNAVAILABLE',
        message=(
            f'거래할 수 있는 매물이 없는 직방 아파트 묶음입니다: {catalog_id} '
            '(모두 내려갔거나 그 호에 그 거래 유형 매물이 없음)'
        ),
        hint='이 묶음은 빼고 search listings apt·search listings --complex <apt-…> 로 현재 매물을 다시 찾으세요',
        details={'catalog_id': catalog_id, 'reason': 'EMPTY_CATALOG'},
    )


def get_catalog(client: ZigbangClient, catalog_id: str) -> ZigbangCatalogResult:
    """같은 호를 올린 아파트 매물 묶음의 매물을 웹 묶음 화면과 같은 API(`/apt/item-catalogs/{areaHoId}`)로 받는다.

    웹처럼 20건씩 `itemCount` 까지 받되(앞 `MAX_LIST_LIMIT` 건까지), 웹은 스크롤할 때마다 다음 20건을 받고 여기서는 한 번에
    끝까지 받는다. 매물마다 아파트 상세와 같은 꼴이라 `apt_item_to_listing` 으로 바꿔, 매물마다 상세를 따로 부르지 않는다.
    순서는 직방이 준 그대로다 (웹도 다시 세우지 않는다). 상세를 볼 수 없는 출처(직방·제휴 밖)의 매물은 목록의 `listing_ids`
    처럼 빼고 그 수를 `[제외]` 로 알린다 (2026-11-15 헬리오시티·은마 묶음 270건은 모두 직방·제휴였다). 거래 유형은 묶음 ID 의
    것을 쓴다 (매물의 `tranType` 이 비어도 웹 묶음 화면처럼 빼지 않는다).

    받는 도중 직방이 다음 쪽을 주지 않으면(받는 사이 묶음이 줄어 404, 또는 빈 쪽) 받은 데까지 내고 `[일부]` 로 알린다.
    직방이 `itemCount` 를 주지 않으면(`total` null) 쪽이 가득(`CATALOG_PAGE_SIZE`) 찬 동안 상한까지 받고, 덜 찬 쪽이나
    404·빈 쪽이 오면 끝으로 본다. `(최대 N건)` 안내는 상한에 닿아 멈췄을 때만이다.

    Raises:
        JibsaError: 묶음 ID 형식이 아닐 때 (INVALID_ARGUMENT). 묶음에 매물이 없을 때 (LISTING_UNAVAILABLE, reason
            `EMPTY_CATALOG`. 모두 내려갔거나 그 호에 그 거래 유형 매물이 없음. 첫 쪽이 404 이거나 200 빈 목록). 묶음 ID 는
            매물 ID 가 아니라 `listing_id` 대신 `catalog_id` 로 싣는다.
    """
    area_ho_id, tran_type = parse_catalog_id(catalog_id)
    trade_type = TRADE_BY_APT_TRAN_TYPE[tran_type]
    catalog_id = apt_catalog_id(area_ho_id, tran_type)
    listings: list[ZigbangListingDetail] = []
    received = 0
    total: int | None = None
    last_page_full = False
    cut_short = False
    while True:
        try:
            page = client.run_request_item_catalogs(ZigbangItemCatalogsRequestParameterModel(
                area_ho_id=area_ho_id, tran_type=tran_type, offset=received, limit=CATALOG_PAGE_SIZE,
            ))
        except HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            if not received:
                raise _empty_catalog_error(catalog_id) from None
            # 알린 수에 못 미쳤으면 받는 사이 묶음이 줄어 뒤 쪽이 없어졌다. 수를 모르면 끝까지 받은 것으로 본다. 받은 데까지 낸다
            cut_short = total is not None
            break
        if not page.items:
            if not received:
                # 첫 쪽이 200 빈 목록이어도 404 와 같은 빈 묶음이다 (itemCount 와 상관없이)
                raise _empty_catalog_error(catalog_id)
            # 둘째 쪽부터의 빈 쪽도 404 와 같다. 이 쪽의 itemCount 는 줄어든 뒤의 수라 쓰지 않고 앞 쪽이 알린 수로 본다
            cut_short = total is not None
            break
        total = page.item_count
        received += len(page.items)
        last_page_full = len(page.items) >= CATALOG_PAGE_SIZE
        for apt in page.items:
            if (source := apt_item_source(apt.item_source)) is not None:
                listings.append(apt_item_to_listing(apt, source, trade_type))
        if total is None:
            # 묶음 수를 모르면 쪽이 가득 찬 동안만 다음 쪽을 받는다
            if not last_page_full or received >= MAX_LIST_LIMIT:
                break
            continue
        if received >= min(total, MAX_LIST_LIMIT):
            break
    notes: list[str] = []
    if received > len(listings):
        notes.append(note(
            '제외', f'묶음 매물 {received}건 중 상세를 볼 수 없는 출처 {received - len(listings)}건을 뺐습니다',
        ))
    if total is None:
        has_more = received >= MAX_LIST_LIMIT and last_page_full
    else:
        has_more = received < total
    # cut_short 는 받은 수가 직방이 알린 수(total)에 못 미친 채 멈췄을 때만 서므로 has_more 는 늘 참이다
    if cut_short:
        notes.append(note(
            '일부',
            f'직방이 다음 쪽 매물을 주지 않아 {received}건에서 멈췄습니다 (직방이 알린 묶음 {total}건, 받는 사이 묶음이 바뀌었을 수 '
            '있음). 다시 부르거나 url 의 직방 묶음 화면에서 보세요',
        ))
    elif has_more and total is None:
        notes.append(note(
            '일부',
            f'직방이 묶음 매물 수를 알려 주지 않아 앞 {received}건만 받았습니다 (최대 {MAX_LIST_LIMIT}건, 더 있을 수 있음). '
            '나머지는 url 의 직방 묶음 화면에서 보세요',
        ))
    elif has_more:
        notes.append(note(
            '일부',
            f'묶음 매물 {total}건 중 앞 {received}건만 받았습니다 (최대 {MAX_LIST_LIMIT}건). 나머지는 url 의 직방 묶음 화면에서 보세요',
        ))
    return ZigbangCatalogResult(
        catalog_id=catalog_id,
        url=apt_catalog_url(area_ho_id, tran_type),
        trade_type=trade_type,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )


def unsearchable_types(property_types: Sequence[str], trade_types: Sequence[str]) -> list[str]:
    """거래 유형 조건 때문에 직방에서 조회할 수 없는 유형. 원룸은 매매가 없다 (전세·월세·단기임대만).

    `search_listings` 는 이런 유형을 요청 없이 건너뛰므로, 0건을 "매물이 없다"로 오해하지
    않도록 호출한 쪽이 `unsearchable_note` 로 알린다.
    """
    if '원룸' in property_types and trade_types and all(trade == '매매' for trade in trade_types):
        return ['원룸']
    return []


def unsearchable_note(types: list[str]) -> str:
    return note(
        '거래',
        f"직방은 {'·'.join(types)} 매매를 다루지 않아 조회하지 않았습니다 (전세·월세·단기임대만). "
        '매매는 빌라·오피스텔이나 다른 소스에서 찾으세요',
    )


# 유형별 분기를 (요청 모델, 메서드) 표로 묶지 않는다. 표로 두면 타입 검사가 요청 모델과 메서드 짝을 확인하지 못한다.
# _fetch_subway_pins 도 같다
def _fetch_pins(
    client: ZigbangClient,
    property_type: ZigbangPropertyType,
    **parameter: object,
) -> ZigbangItemsResponseModel:
    if property_type == '원룸':
        return client.run_request_items_onerooms_v1(
            ZigbangItemsOneroomsV1RequestParameterModel(**parameter)
        )
    if property_type == '오피스텔':
        return client.run_request_items_officetels_v1(
            ZigbangItemsOfficetelsV1RequestParameterModel(**parameter)
        )
    return client.run_request_items_villas_v1(
        ZigbangItemsVillasV1RequestParameterModel(**parameter)
    )


def _fetch_subway_pins(
    client: ZigbangClient,
    property_type: ZigbangPropertyType,
    **parameter: object,
) -> ZigbangItemsResponseModel:
    if property_type == '원룸':
        return client.run_request_items_subways_onerooms_v1(
            ZigbangItemsSubwaysOneroomsV1RequestParameterModel(**parameter)
        )
    if property_type == '오피스텔':
        return client.run_request_items_subways_officetels_v1(
            ZigbangItemsSubwaysOfficetelsV1RequestParameterModel(**parameter)
        )
    return client.run_request_items_subways_villas_v1(
        ZigbangItemsSubwaysVillasV1RequestParameterModel(**parameter)
    )


def _scope_pins(
    client: ZigbangClient,
    property_type: ZigbangPropertyType,
    *,
    geohashes: list[str],
    subway_id: int | None,
    radius_km: float,
    sales_types: list[ZigbangSalesType],
    type_filters: dict[str, object],
) -> Iterator[tuple[str | None, ZigbangItemsResponseModel]]:
    """검색 범위의 핀을 (지도 칸, 응답) 으로 하나씩 받는다. 역 검색이면 역 API 를 한 번 부르고 칸은 None 이다."""
    if subway_id is not None:
        yield None, _fetch_subway_pins(
            client, property_type, subway_id=subway_id, radius=radius_km, sales_types=sales_types, **type_filters,
        )
        return
    for geohash in geohashes:
        yield geohash, _fetch_pins(client, property_type, geohash=geohash, sales_types=sales_types, **type_filters)


def _officetel_building_ids(
    client: ZigbangClient,
    *,
    geohashes: list[str],
    subway_id: int | None,
    radius_km: float,
    sales_types: list[ZigbangSalesType],
    type_filters: dict[str, object],
) -> dict[int, int]:
    """원룸 검색과 같은 조건의 오피스텔 핀에서 매물 ID → 건물 ID 를 받는다."""
    responses = _scope_pins(
        client, '오피스텔', geohashes=geohashes, subway_id=subway_id, radius_km=radius_km,
        sales_types=sales_types, type_filters=type_filters,
    )
    return {pin.id: pin.building_id for _, response in responses for pin in response.items if pin.building_id}


# 유형 하나의 (거래 유형 필터, 요청 필드)
_TypeQuery = tuple[list[ZigbangSalesType], dict[str, object]]


class _ScopePins(NamedTuple):
    """`_collect_pins` 결과: 종류마다 범위 안 매물 ID(직방 목록 순서), 매물별 중심 거리·건물 ID, 원룸 조회 조건과 지도 칸."""

    ids_by_type: dict[ZigbangPropertyType, list[int]]
    distances: dict[int, float]
    # 오피스텔 핀의 건물 ID. 원룸 목록에 섞여 온 같은 매물의 핀에는 없어 종류와 상관없이 매물 ID 로 찾는다
    buildings: dict[int, int]
    # 원룸 목록에 섞여 온 오피스텔의 건물 ID 를 같은 조건의 오피스텔 목록으로 채울 때 쓴다
    oneroom_query: _TypeQuery | None
    # 원룸 핀을 받은 지도 칸. 건물 ID 가 빠진 매물이 있던 칸만 오피스텔 목록을 다시 받는다
    oneroom_cells: dict[int, str]
    # 앞 종류 목록에도 있어 그 종류 목록에서 뺀 매물 수 (원룸 목록의 '이 지역 오피스텔' 은 오피스텔 목록에도 있다)
    overlaps: dict[ZigbangPropertyType, int]


def search_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangRoomConditions | None = None,
    property_types: list[ZigbangPropertyType] | None = None,
    radius_km: float = 1.0,
    limit: int = 20,
    boundary: ZigbangBoundary | None = None,
    subway_id: int | None = None,
    start: dict[str, Any] | None = None,
) -> ZigbangSearchResult:
    """원룸·빌라·오피스텔 매물을 직방 웹 목록 순서로 `limit` 건 조회한다.

    종류마다 검색 범위의 지도 칸(역이면 역 반경 API)에서 핀(`items`)과 섹션(`sections`)을 받아, 웹 목록처럼 응답의 섹션
    순서(VIP → 안심추천 → 안심일반 → 추천 → 일반)대로 잇는다 (2026-11-15 번들 `_app` 의 `loadSectionsWithItemIdsByGeoHash`·
    `createSectionsToUpdate`). 섹션 안은 서버가 준 순서 그대로 둔다. 웹은 VIP 밖 섹션 안을 화면에서 무작위로 섞지만, 서버
    순서는 같은 요청에 늘 같아 (2026-11-15 실측) 이어 받기 자리가 흔들리지 않는다. 지도 칸이 여럿이면 섹션 종류마다 칸 순서
    (`scope_geohashes`)대로 잇고, 어느 섹션에도 없는 핀은 잃지 않게 맨 뒤에 핀 순서로 붙인다. 거리로 다시 세우지 않고
    `distance_km` 는 매물마다 덧붙이기만 한다. 고른 매물의 요약을 15개씩 받아 고른 순서대로 `Listing` 으로 바꾼다.
    가격·관리비(만원), 방 구조, 면적(㎡·평), 층, 욕실 수, 옵션, 기타 조건(`CONDITION_FIELD_BY_LABEL`)은 서버에서 거른다.
    요약을 받은 뒤 거래 불가·지원하지 않는 거래 종류로 뺀 매물은 다시 채우지 않고 `notes` 로 알린다.

    범위는 핀 좌표로 좁힌다. `boundary` 를 주면 반경 대신 그 동 경계 안 핀만 남기고(경계를 덮는 지도 칸을 받는다), 좌표·구·
    시·`--radius` 는 검색 중심에서 `radius_km` 안 핀만 반올림 없이 남긴다. 반경 안이 모자라도 반경 밖 핀으로 채우지 않는다
    (웹 지도 목록은 화면 사각형이라 반경이 없고, 반경 밖을 덧붙이는 화면도 없다). `subway_id` 를 명시하면 지도 칸 대신 역 반경
    API 를 종류별 1회 부르고, 서버가 반경으로 준 결과를 다시 자르지 않는다.

    종류가 여럿이면(기본은 세 종류) 웹처럼 종류마다 목록이 따로라, `limit` 을 조회할 종류 수로 고르게 나눠(20 → 7·7·6, 앞
    종류부터 한 건씩 더) 종류별 묶음을 요청한 종류 순서대로 잇는다. 한 종류의 남은 매물이 제 몫보다 적으면 남는 몫을 다른
    종류에 돌린다. 원룸 목록의 '이 지역 오피스텔' 섹션 매물은 오피스텔 목록에도 있어, 앞 종류 목록에 있는 매물은 뒤 종류
    목록에서 빼고 세며 몇 건인지 `notes` 로 알린다. 받기 전에 빼서 `--next` 로 이어 받아도 다시 나오지 않고, 이어 받기 자리·
    `total`·`[일부]` 가 모두 서로 다른 매물 수로 맞는다 (2026-11-16 리뷰: 한 호출 안에서만 빼자 강남역 이어 받기에서 앞 쪽
    매물이 16~59건씩 다시 나왔고, 자리를 종류별로 더한 수가 `total` 을 넘어 더 있는데도 `[일부]` 가 사라졌다).

    원룸은 건물 종류가 아니라 방 하나짜리를 뜻한다. 직방 원룸 목록은 오피스텔(투룸 포함)을 함께 주므로
    원룸형 구조(`ONE_ROOM_STRUCTURES`)만 서버에 요청하고, 섞여 온 원룸형 오피스텔은 결과에 넣는다.
    원룸 목록 핀에는 건물 ID 가 없어, 오피스텔을 따로 조회하지 않았으면 같은 범위·조건의 오피스텔
    목록을 한 번 더 받아 `complex_id` 를 채운다 (결과에 건물 ID 없는 오피스텔이 있을 때만).

    오피스텔 요청에는 늘 서버의 무작위 섞기 해제(`withoutRandom`)를 보낸다. 직방은 오피스텔 섹션 안 순서만 무작위로 섞어 주고
    시간이 지나면 다시 섞어, 그대로 받으면 이어 받기(`--next`)의 자리가 흔들려 매물이 겹치거나 빠진다. 섞지 않은 순서는 원룸·
    빌라처럼 매물 번호순이라 시간이 지나도 같다 (2026-11-15~16 실측: wydm6 오피스텔 안심추천 168건·안심일반 363건이 섞는
    요청과 같은 매물이고, 하루 뒤에도 남은 매물의 순서가 같았다). 맨 위 VIP 섹션(광고, 다른 섹션 매물 중 32건)만은 직방이
    요청마다·시간마다 바꿔 준다.

    `start` 는 이어 받기(`--next`) 표의 위치다 (`{'offsets': {종류: 그 종류 목록에서 다음에 받을 자리}}`). 핀은 다시 받아
    같은 순서로 세운 뒤 종류마다 그 자리부터 요약을 받는다. 핀 요청은 지도 칸 수만큼이라 적고, 요약은 15개에 1회라 앞서 받은
    매물의 요약을 다시 받지 않는다.

    직방 카테고리별 방 구조: 원룸 = 오픈형·분리형·복층형 원룸 (원룸형 오피스텔 포함), 빌라 = 투룸·
    쓰리룸·포룸이상 (원룸형 구조만 주면 빌라는 조회하지 않는다), 오피스텔 = 원룸형·투룸·쓰리룸 이상.

    거래 유형도 서버에서 거른다. 직방의 '월세' 필터는 단기임대를 빼고, 단기임대는 '단기' 로
    따로 받는다 (`SALES_TYPE_BY_TRADE`). 거래 유형을 주지 않으면 단기임대도 함께 나온다.

    Raises:
        JibsaError: 역 반경과 동 경계를 함께 줬거나, 이어 받기 표의 종류가 이번 검색과 다르거나 모양이 틀릴 때
            (INVALID_ARGUMENT).
    """
    # 방어용. CLI 는 둘을 함께 넘기지만 역 검색 결과에는 법정동코드가 없어 역이면 boundary 가 늘 None 이다.
    if subway_id is not None and boundary is not None:
        raise JibsaError(
            code='INVALID_ARGUMENT', message='역 반경 검색과 동 경계를 함께 지정할 수 없습니다',
            hint='역 검색에는 동 경계 대신 반경을 사용하세요',
        )
    conditions = conditions or ZigbangRoomConditions()
    requested_types = property_types or []
    property_types = property_types or list(PROPERTY_TYPES)

    queries, notes = _type_queries(conditions, property_types, requested_types)
    types = list(queries)
    # 핀을 받기 전에 본다. 표가 틀리면 요청 없이 멈춘다
    starts = _start_offsets(start, types)
    geohashes = [] if subway_id is not None else scope_geohashes(region, radius_km, boundary, GEOHASH_PRECISION)
    scan = _collect_pins(
        client, region, queries, geohashes=geohashes, subway_id=subway_id, radius_km=radius_km, boundary=boundary,
    )

    # 조회 예산은 요약을 받는 자리 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    remaining = [max(len(scan.ids_by_type[kind]) - starts[kind], 0) for kind in types]
    shares = dict(zip(types, _split_limit(limit, remaining)))
    # 종류별 목록은 서로 겹치지 않는다 (_collect_pins)
    ids = [
        item_id
        for kind in types
        for item_id in scan.ids_by_type[kind][starts[kind]:starts[kind] + shares[kind]]
    ]
    summaries = {summary.item_id: summary for summary in tradeable_summaries(client, ids)}
    # 요약 응답 순서에 기대지 않고 고른 순서로 세운다. 원룸 목록에 섞여 온 원룸형 오피스텔도 그대로 둔다
    listings: list[Listing] = [
        summary_to_listing(summaries[item_id], scan.distances.get(item_id), scan.buildings.get(item_id))
        for item_id in ids
        if item_id in summaries
    ]
    if scan.oneroom_query is not None and '오피스텔' not in queries:
        _fill_officetel_complex_ids(client, listings, scan, subway_id=subway_id, radius_km=radius_km)

    return _search_result(
        region, listings, scan, notes, starts=starts, shares=shares, limit=limit, radius_km=radius_km, boundary=boundary,
    )


def _type_query(
    property_type: ZigbangPropertyType,
    conditions: ZigbangRoomConditions,
    requested_types: list[ZigbangPropertyType],
    filters: dict[str, object],
    notes: list[str],
) -> _TypeQuery | None:
    """유형 하나의 (거래 유형 필터, 요청 필드). 그 유형은 조회할 게 없으면 None 이고 직접 찾은 유형이면 `notes` 에 알린다."""
    all_sales_types = [SALES_TYPE_BY_TRADE[trade] for trade in conditions.trade_types]
    sales_types = all_sales_types
    type_rooms = list(conditions.room_types)
    if property_type == '빌라' and type_rooms and all(room in ONE_ROOM_STRUCTURES for room in type_rooms):
        # 직방 빌라 목록은 투룸 이상뿐이라 원룸형 구조만 주면 늘 0건이다 (2026-10-10 실측: 3개 동 빌라
        # 135건 모두 투룸 이상, 원룸형 조건 0건). 빌라 건물의 원룸은 직방이 원룸 목록에 둔다
        if '빌라' in requested_types:
            notes.append(note(
                '범위',
                '직방 빌라 목록은 투룸 이상만 있어 --room 의 원룸형 조건으로는 조회하지 않았습니다. '
                '빌라(다세대·다가구) 건물의 원룸은 -t 원룸으로 찾으세요',
            ))
        return None
    if property_type == '원룸':
        sales_types = [sales_type for sales_type in all_sales_types if sales_type != '매매']
        if conditions.trade_types and not sales_types:
            # 원룸에 매매만 요청하면 해당 유형은 조회할 게 없다.
            return None
        # 원룸 목록은 투룸 오피스텔까지 섞어 주므로 방 하나짜리 구조만 요청한다
        type_rooms = [room for room in type_rooms or ONE_ROOM_STRUCTURES if room in ONE_ROOM_STRUCTURES]
        if not type_rooms:
            if '원룸' in requested_types:
                notes.append(note('범위', '원룸은 방 하나짜리(오픈형·분리형·복층형)만 찾아 --room 의 투룸 이상 조건으로는 조회하지 않았습니다'))
            return None
    type_filters = {**filters, 'room_types': [ROOM_TYPE_FILTER_BY_LABEL[room] for room in type_rooms]}
    # 방 1개짜리 아파트는 여기서 찾지 않는다는 안내는 원룸을 찾을 때마다 나와 docs/llm.md 로 옮겼다
    if property_type == '오피스텔':
        # 섞지 않은 순서로 받아 이어 받기의 자리가 흔들리지 않게 한다 (search_listings docstring)
        type_filters['without_random'] = True
    return sales_types, type_filters


def _type_queries(
    conditions: ZigbangRoomConditions,
    property_types: list[ZigbangPropertyType],
    requested_types: list[ZigbangPropertyType],
) -> tuple[dict[ZigbangPropertyType, _TypeQuery], list[str]]:
    """조회할 종류마다 (거래 유형 필터, 요청 필드) 를 요청한 종류 순서로, 조회하지 않는 종류의 안내와 함께 만든다."""
    # 방 구조는 유형마다 달라 _type_query 에서 넣는다
    filters: dict[str, object] = {
        'deposit_min': conditions.deposit_min,
        'deposit_max': conditions.deposit_max,
        'rent_min': conditions.rent_min,
        'rent_max': conditions.rent_max,
        'sales_price_min': conditions.price_min,
        'sales_price_max': conditions.price_max,
        **room_filter_of(conditions),
    }
    notes: list[str] = []
    queries: dict[ZigbangPropertyType, _TypeQuery] = {}
    for property_type in property_types:
        query = _type_query(property_type, conditions, requested_types, filters, notes)
        if query is not None:
            queries[property_type] = query
    return queries, notes


def _start_offsets(start: dict[str, Any] | None, types: list[ZigbangPropertyType]) -> dict[ZigbangPropertyType, int]:
    """이어 받기 표(`--next`)에서 종류마다 다음에 받을 자리를 꺼낸다. 표가 없으면 모두 0 이다.

    Raises:
        JibsaError: 표의 종류가 이번 검색의 종류와 다르거나 모양이 틀릴 때 (INVALID_ARGUMENT). 예전 `{'offset': n}` 표도
            여기 걸린다.
    """
    if start is None:
        return {kind: 0 for kind in types}
    offsets = start.get('offsets')
    if (
        isinstance(offsets, dict)
        and set(offsets) == set(types)
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in offsets.values())
    ):
        return {kind: offsets[kind] for kind in types}
    raise JibsaError(
        code='INVALID_ARGUMENT',
        message='이어 받기 표(--next)의 위치가 이 검색의 매물 종류와 맞지 않아 이어 받을 수 없습니다',
        hint='--next 없이 같은 지역·조건으로 다시 검색하세요',
    )


def _split_limit(limit: int, remaining: list[int]) -> list[int]:
    """`limit` 을 종류마다 고르게 나눈다 (20 → 7·7·6, 앞 종류부터 한 건씩 더). `remaining` 은 종류마다 남은 자리 수다.

    남은 자리가 제 몫보다 적은 종류는 남은 만큼만 받고, 남는 몫은 아직 남은 종류에 같은 규칙으로 다시 나눈다.
    """
    shares = [0] * len(remaining)
    left = limit
    open_kinds = [index for index, count in enumerate(remaining) if count > 0]
    while left > 0 and open_kinds:
        base, extra = divmod(left, len(open_kinds))
        for rank, index in enumerate(open_kinds):
            take = min(base + (1 if rank < extra else 0), remaining[index] - shares[index])
            shares[index] += take
            left -= take
        open_kinds = [index for index in open_kinds if shares[index] < remaining[index]]
    return shares


def _collect_pins(
    client: ZigbangClient,
    region: ZigbangRegion,
    queries: dict[ZigbangPropertyType, _TypeQuery],
    *,
    geohashes: list[str],
    subway_id: int | None,
    radius_km: float,
    boundary: ZigbangBoundary | None,
) -> _ScopePins:
    """종류마다 검색 범위의 핀과 섹션을 받아 범위 안 매물 ID 를 웹 목록 순서로 세운다 (`section_ordered_ids`).

    섹션 종류마다 칸 순서대로 잇고, 어느 섹션에도 없는 핀은 맨 뒤에 칸·핀 순서로 붙인다. 같은 매물이 두 번 오면 앞의 것만 둔다.
    앞 종류 목록에 있는 매물은 뒤 종류 목록에서 빼 종류별 목록이 서로 겹치지 않게 한다 (`search_listings`).
    """
    scan = _ScopePins(
        ids_by_type={}, distances={}, buildings={}, oneroom_query=queries.get('원룸'), oneroom_cells={}, overlaps={},
    )
    claimed: set[int] = set()

    def in_scope(pin: ZigbangItemPinModel | None) -> bool:
        if pin is None:
            # 섹션에 있는데 핀이 없는 매물 (실측으로는 두 ID 집합이 같다, 2026-11-15 wydm6 원룸 1187건). 역은 서버가 반경으로
            # 준 결과라 그대로 두고, 지도 칸은 좌표를 몰라 범위 안인지 볼 수 없어 뺀다
            return subway_id is not None
        if boundary is not None:
            return not outside_boundary(boundary, pin.lat, pin.lng)
        # 역은 서버가 반경으로 거른 결과라 다시 자르지 않는다. 좌표·구·시는 반올림 없이 반경 안만 둔다
        return subway_id is not None or scan.distances[pin.id] <= radius_km

    for property_type, (sales_types, type_filters) in queries.items():
        responses = list(_scope_pins(
            client, property_type, geohashes=geohashes, subway_id=subway_id, radius_km=radius_km,
            sales_types=sales_types, type_filters=type_filters,
        ))
        for geohash, response in responses:
            for pin in response.items:
                scan.distances[pin.id] = haversine_km(region.lat, region.lng, pin.lat, pin.lng)
                if pin.building_id:
                    scan.buildings[pin.id] = pin.building_id
                if property_type == '원룸' and geohash is not None:
                    scan.oneroom_cells[pin.id] = geohash
        ordered = section_ordered_ids([response for _, response in responses], in_scope)
        ids = [item_id for item_id in ordered if item_id not in claimed]
        scan.ids_by_type[property_type] = ids
        scan.overlaps[property_type] = len(ordered) - len(ids)
        claimed.update(ids)
    return scan


def _fill_officetel_complex_ids(
    client: ZigbangClient,
    listings: list[Listing],
    scan: _ScopePins,
    *,
    subway_id: int | None,
    radius_km: float,
) -> None:
    """원룸 목록에 섞여 온 오피스텔의 `complex_id` 를 같은 범위·조건의 오피스텔 목록으로 채운다."""
    # 원룸 목록 핀에는 건물 ID 가 없다 (2026-10-10 실측: 역삼동 468건 모두 null, 요약에도 없음).
    # 같은 범위·조건의 오피스텔 목록은 건물 ID 를 주고 섞여 온 오피스텔과 모두 겹쳤다 (286건)
    missing = [
        listing for listing in listings
        if isinstance(listing, ZigbangListing) and listing.property_type == '오피스텔' and listing.complex_id is None
    ]
    if not missing or scan.oneroom_query is None:
        return
    sales_types, type_filters = scan.oneroom_query
    # 빠진 매물이 있던 칸만 받는다 (2026-10-11 실측: 역삼동 원룸 5km 11칸 중 건물 ID 를 채운 칸은 1칸,
    # 오피스텔 13건 모두 그 칸에서 채움)
    cells = sorted({scan.oneroom_cells[int(listing.id)] for listing in missing if int(listing.id) in scan.oneroom_cells})
    try:
        buildings = _officetel_building_ids(
            client, geohashes=cells, subway_id=subway_id, radius_km=radius_km,
            sales_types=sales_types, type_filters=type_filters,
        )
    except OPTIONAL_LOOKUP_ERRORS:
        # 건물 ID 는 덤이라 못 받으면 모름(null)으로 둔다
        buildings = {}
    for listing in missing:
        building_id = buildings.get(int(listing.id))
        if building_id:
            listing.complex_id = officetel_complex_id(building_id)


def _type_share_note(
    scan: _ScopePins,
    starts: dict[ZigbangPropertyType, int],
    shares: dict[ZigbangPropertyType, int],
) -> str:
    """종류 여럿을 찾았을 때 종류마다 범위 안 몇 건 중 목록의 몇 번째 자리를 받았는지 한 줄로 알린다."""
    parts: list[str] = []
    for kind, share in shares.items():
        found = len(scan.ids_by_type[kind])
        first, last = starts[kind] + 1, starts[kind] + share
        if not found:
            parts.append(f'{kind} 0건')
        elif not share:
            parts.append(f'{kind} 약 {found}건 중 0건')
        elif first == last:
            parts.append(f'{kind} 약 {found}건 중 1건 ({first}번째)')
        else:
            parts.append(f'{kind} 약 {found}건 중 {share}건 ({first}~{last}번째)')
    overlaps = [f'{kind} {count}건' for kind, count in scan.overlaps.items() if count]
    return note(
        '참고',
        '직방은 매물 종류마다 목록이 따로라 --limit 을 종류별로 나눠 각 목록 순서대로 받았습니다: ' + ', '.join(parts)
        + (
            f". 앞 종류 목록에도 있는 매물({', '.join(overlaps)}, 원룸 목록의 '이 지역 오피스텔')은 앞 종류에서만 세고 냅니다"
            if overlaps else ''
        ),
    )


def _search_result(
    region: ZigbangRegion,
    listings: list[Listing],
    scan: _ScopePins,
    notes: list[str],
    *,
    starts: dict[ZigbangPropertyType, int],
    shares: dict[ZigbangPropertyType, int],
    limit: int,
    radius_km: float,
    boundary: ZigbangBoundary | None,
) -> ZigbangSearchResult:
    """범위 안 매물 수와 조회 한도·제외 안내를 붙여 결과를 만든다.

    `shares` 는 종류마다 이번에 요약을 받은 자리 수다. 종류별 목록이 서로 겹치지 않아(`_collect_pins`) 자리를 더한 수가 곧
    받은 매물 수다. 범위(동 경계·반경) 안에 아직 요약을 받지 않은 자리가 남은 종류가 있으면 종류마다 다음 자리를 이어 받을
    위치로 붙인다.
    """
    in_scope = sum(len(ids) for ids in scan.ids_by_type.values())
    offsets = {kind: starts[kind] + share for kind, share in shares.items()}
    has_more = any(offsets[kind] < len(scan.ids_by_type[kind]) for kind in offsets)
    taken = sum(shares.values())
    notes = notes + excluded_notes(limit, taken, len(listings), order='직방 목록 순으로 앞의', has_more=has_more)
    # 핀 수는 거래 불가를 요약에서 거르기 전이라 근사값이다. 이어 받은 자리는 종류별 자리를 더한 수다
    notes += limit_notes(
        in_scope, len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow='조건·반경' if boundary is None else '조건·지역',
        order='직방 목록', approximate=True, inspected=taken, offset=sum(starts.values()), resumable=has_more,
        has_more=has_more,
    )
    if len(shares) > 1:
        notes.append(_type_share_note(scan, starts, shares))
    return ZigbangSearchResult(
        region=region,
        radius_km=radius_km if boundary is None else None,
        boundary=boundary.name if boundary is not None else None,
        total=in_scope,
        returned=len(listings),
        listings=listings,
        notes=notes,
        has_more=has_more,
        next_position={'offsets': offsets} if has_more else None,
    )


def get_listing(client: ZigbangClient, item_id: int) -> ZigbangListingDetail:
    """숫자 ID 매물의 상세를 조회한다. 원룸·빌라·오피스텔은 새 주거 상세 + 등록일·단기임대 요약이고, 입주일이 null 이면
    기존 상세 1회, 필지가 있으면 건물 학군 1회를 더한다 (학군은 실패하면 모름).

    새 주거 상세는 아파트 매물에 본문 code 가 `APT_DETAIL_NOT_SUPPORTED_CODE` 인 404 를 준다. 그때는 웹 아파트 매물 화면처럼
    아파트 상세 1회로 만든다 (`get_apt_listing`).

    Raises:
        ListingUnavailableError: 없는 매물(404)이거나 상태가 open 이 아닐 때 (상태가 없을 때 포함).
        JibsaError: 거래 중인 매물인데 거래 유형·매물 유형이 없을 때 (PARSE_ERROR).
    """
    structured: ZigbangItemsDetailV1ResponseModel | None
    with unavailable_on_404(item_id):
        try:
            structured = client.run_request_items_detail_v1(
                ZigbangItemsDetailV1RequestParameterModel(item_id=item_id)
            )
        except HTTPStatusError as exc:
            # 리뷰 오탐 (2026-11-15, 근거 고침 2026-11-20): 서버가 매물 유형으로 거부하는 예외를 준다 (2026-11-20 재현: 아파트
            # 51270731 → 404 code ITEM_QUERY_DETAIL_SERVICE_TYPE_NOT_SUPPORTED, metadata.serviceType '아파트'). 200 이 와도
            # detail_to_listing 이 아파트 전용 칸이 빠진 상세를 낼 뿐 틀린 값을 내지 않아 아파트 여부를 다시 확인하는 가드는 두지 않는다
            if exc.response.status_code != 404 or (error_body(exc) or {}).get('code') != APT_DETAIL_NOT_SUPPORTED_CODE:
                raise
            structured = None
    if structured is None:
        return get_apt_listing(client, item_id)
    if structured.item.status != 'open':
        raise ListingUnavailableError('zigbang', item_id, status=structured.item.status)
    # 내려간 매물 안내가 먼저다. 살아 있는 매물인데 유형이 없으면 거래·매물 유형과 url 을 만들 수 없다
    missing = [
        name for name, value in (('salesType', structured.item.sales_type), ('serviceType', structured.item.service_type))
        if value is None
    ]
    if missing:
        raise JibsaError(
            code='PARSE_ERROR',
            message=f"직방 매물 상세(/items/{item_id}/detail)에 없는 필드: {', '.join(missing)}",
            hint='비공식 API 응답 형식이 바뀌었을 수 있습니다. 다른 소스를 쓰세요',
            details={'item_id': item_id},
        )
    residence = structured.item.residence
    legacy = None
    if residence.move_in_at is None:
        # null을 즉시 입주로 추측하지 않고 기존 API의 설명으로 보완한다.
        # 실측: 두 API 의 status 는 늘 같다(open·close·cancel).
        with unavailable_on_404(item_id):
            legacy = client.run_request_items_v3(ZigbangItemsV3RequestParameterModel(item_id=item_id))
        if legacy.item.status != 'open':
            raise ListingUnavailableError('zigbang', item_id, status=legacy.item.status)
    # 상세에는 등록일과 단기임대 여부가 없어 목록과 같은 값(reg_date, contract)을 요약 API 에서 받아 온다.
    # 요약의 status(노출 여부)는 다시 보지 않는다. 2026-10-10 실측 180건: 요약 true ↔ 상세 open,
    # false ↔ close·cancel, 요약 없음 ↔ 404 로 늘 같았다
    summaries = client.run_request_items_list_v1(
        ZigbangItemsListV1RequestPayloadModel(item_ids=[item_id])
    )
    summary = next((summary for summary in summaries.items if summary.item_id == item_id), None)
    schools = None
    pnu = structured.item.address.pnu
    if pnu:
        try:
            schools = building_schools(client.run_request_bls_school_zones_v1(
                ZigbangBlsSchoolZonesV1RequestParameterModel(pnu=pnu)
            ))
        except OPTIONAL_LOOKUP_ERRORS:
            # 학군을 못 받아도 매물 상세는 돌려준다 (모름)
            schools = None
    detail = detail_to_listing(
        structured,
        legacy=legacy.item if legacy else None,
        registered_at=summary.reg_date if summary else None,
        short_term=summary is not None and trade_type_of(summary) == '단기임대',
    )
    return detail if schools is None else detail.model_copy(update={'schools': schools})
