"""원룸·빌라·오피스텔 매물 검색과 주거 매물 상세 (search listings room, listing)."""

from collections.abc import (
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
from jibsa.core.listing import (
    Listing,
    ListingDetail,
    beyond_radius_notes,
    by_distance,
    join_address,
    limit_notes,
    m2_to_pyeong,
    normalize_date,
    won_to_manwon,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangItemsListV1RequestPayloadModel,
    ZigbangSalesType,
)
from jibsa.providers.zigbang.api.request.listing import (
    ZigbangBlsSchoolZonesV1RequestParameterModel,
    ZigbangItemCatalogsItemsRequestParameterModel,
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
    ZigbangItemsDetailV1ResponseModel,
    ZigbangItemsResponseModel,
)
from jibsa.providers.zigbang.service.common import (
    NEAREST_SCHOOLS,
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    SCHOOL_LOOKUP_ERRORS,
    TRADE_BY_APT_TRAN_TYPE,
    ZigbangBoundary,
    ZigbangListing,
    ZigbangRegion,
    ZigbangRoomConditions,
    apt_complex_id,
    apt_item_url,
    drop_unused_scope,
    excluded_notes,
    item_url,
    officetel_complex_id,
    room_filter_of,
    school_label,
    summary_to_listing,
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
# 원룸 검색 오피스텔의 건물 ID 보완도 덤이라 같은 실패는 건물 ID 만 모름으로 둔다
BUILDING_LOOKUP_ERRORS: tuple[type[Exception], ...] = SCHOOL_LOOKUP_ERRORS
# 단지·건물이 있는 유형(아파트·오피스텔)의 상세에만 있는 필드와 아파트 상세에만 있는 필드. 없는 유형은 키를 뺀다
COMPLEX_DETAIL_FIELDS: frozenset[str] = frozenset({'complex_id', 'complex_name'})
APT_ONLY_DETAIL_FIELDS: frozenset[str] = frozenset({'supply_area_m2'})
# 방 하나짜리 구조. 원룸 유형은 이 구조만 서버에 요청한다 (직방 원룸 목록에는 투룸 오피스텔도 섞여 온다)
ONE_ROOM_STRUCTURES: tuple[str, ...] = ('오픈형원룸', '분리형원룸', '복층형원룸')
# 방 하나짜리 아파트는 아파트 목록에만 있고 아파트 API 에는 방 구조 조건이 없다. 공급면적 50㎡ 이하로 찾으면
# 대부분 방 1개다 (2026-10-10 실측: 역삼동 32건 중 단지별 6건 상세에서 5건이 방 1개)
APT_ONE_ROOM_NOTE: str = (
    '방 1개짜리 아파트는 직방 아파트 목록에만 있어 여기서는 찾지 않았습니다. '
    'jibsa zigbang search listings apt <동·구 이름> --supply-area-max 50 으로 찾고 방 개수는 listing 의 room_count 로 확인하세요'
)
GEOHASH_PRECISION: int = 5
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
    total_in_radius: Annotated[
        int,
        Field(description='반경(동 경계로 찾았으면 경계) 안 매물 수 근사값 (limit 적용 전, 방 구조·유형으로 거르기 전). 반경 밖 매물은 세지 않아 반경 밖 매물로 채운 returned 보다 작을 수 있다')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    listings: Annotated[
        # 오피스텔의 complex_id 까지 내보낸다 (SerializeAsAny 가 없으면 공통 Listing 필드만 나간다)
        list[SerializeAsAny[Listing]],
        Field(description='가까운 순 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='매물이 limit 보다 많아 일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 반경과 동 경계 중 쓰지 않은 쪽은 해당 없다
        return drop_unused_scope(handler(self))


class ZigbangListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 매물. `complex_id`·`complex_name` 은 아파트·오피스텔, `supply_area_m2` 는 아파트에만 있다."""

    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (예: 다가구, 다세대, 오피스텔). 중개사 입력 문구라 같은 용도도 다가구·다가구주택처럼 다르게 온다')
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
        int | None,
        Field(description='총 주차 대수 (새 주거 상세만)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='주차 계산에 쓰는 매물 측 세대수. 단지 총세대수와 다를 수 있다')
    ] = None
    direction_criterion: Annotated[
        str | None,
        Field(description='방향 기준 (안방·거실)')
    ] = None
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 학교군 안 가까운 중·고등학교 2곳씩 (원룸·빌라·오피스텔만, 아파트는 complex 에서). 모르면 null')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.id.startswith('coalition-'):
            fields = fields | {'total_parking_count', 'household_count', 'direction_criterion'}
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


def detail_to_listing(
    response: ZigbangItemsDetailV1ResponseModel,
    *,
    legacy: ZigbangItemDetailModel | None = None,
    registered_at: str | None = None,
    short_term: bool = False,
    apt: ZigbangAptItemModel | None = None,
) -> ZigbangListingDetail:
    """새 주거 상세(`/items/{id}/detail`) 응답을 `ZigbangListingDetail` 로 바꾼다.

    사진·본문·중개사 정보는 응답에 있어도 옮기지 않는다 (원 사이트에서 확인).
    입주일(`moveInAt`)이 null 이면 기존 상세(`/v3/items`, `legacy`)의 입주 문구로 보완하고, 그때는 주차도
    기존 상세의 문구를 쓴다. 상세 응답에는 등록일이 없어 요약 응답의 `reg_date` 를 `registered_at` 으로 받는다.
    없으면 모름(None). 단기임대 여부도 상세 응답에는 없어 요약 응답(`trade_type_of`)에서 `short_term` 으로 받는다.
    아파트는 단지 이름·방 수·욕실 수·사용승인일을 아파트 상세(`apt`)로 채운다.
    """
    item = response.item
    residence = item.residence
    price = item.price
    manage = item.manage_cost
    manage_cost = manage.amount if manage else None
    if manage_cost is None and manage is not None:
        manage_cost = won_to_manwon(manage.fee)
    origin = item.address.origin
    address = origin.full_text if origin else None
    if item.address.jibun and origin and origin.local1:
        address = f'{origin.local1} {item.address.jibun}'
    move_in: str | None
    if residence.move_in_at is not None:
        move_in = f"{residence.move_in_at.replace('-', '.')} 이후 입주 가능"
        if residence.move_in_extra:
            move_in += f' ({residence.move_in_extra})'
    else:
        # null을 즉시 입주로 추측하지 않고 기존 상세의 설명을 쓴다
        move_in = legacy.movein_date if legacy else None
    parking = None if residence.parking is None else '주차 가능' if residence.parking else '주차 불가능'
    if legacy is not None and legacy.parking_available_text is not None:
        parking = legacy.parking_available_text

    url = (
        apt_item_url(item.id) if item.service_type == '아파트'
        else item_url(item.service_type, item.id)
    )
    detail = ZigbangListingDetail(
        source='zigbang',
        id=str(item.id),
        url=url,
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
        options=[option.name for option in item.options if option.name],
        manage_cost_includes=[entry.name for entry in manage.includes if entry.name] if manage else None,
        nearby_subways=[
            f'{subway.name} ({subway.description})' if subway.description else subway.name
            for subway in response.subways
        ],
        # 표시 문구를 정규화하지 않는다. 코드는 원룸·빌라가 대부분 '그외'라 문구가 더 정확하다 (2026-10-10 실측).
        # 원본 문구 끝에 공백이 붙어 오기도 해('주택   ') 앞뒤 공백만 뗀다
        residence_type=(residence.residence_description or residence.residence_type or '').strip() or None,
    )
    if item.service_type == '오피스텔':
        return detail.model_copy(update={
            'complex_id': officetel_complex_id(item.building_id) if item.building_id else None,
            'complex_name': response.danji.name if response.danji else None,
        })
    if item.service_type != '아파트':
        return detail
    return apply_apt_detail(detail, apt)


def get_coalition_listing(client: ZigbangClient, item_id: int) -> ZigbangListingDetail:
    """아파트 제휴(호갱노노 집주인) 매물 하나의 상세를 조회한다 (1회 호출).

    제휴 매물은 `/v3/items` 가 404 라 아파트 상세(`/apt/item-catalogs/items`)만으로 만든다.
    상태 필드가 없고 내려간 매물은 404 다. 등록일은 주지 않아 모름(None)이다.

    Raises:
        ListingUnavailableError: 없는 매물(404)일 때.
    """
    listing_id = f'coalition-{item_id}'
    with unavailable_on_404(listing_id):
        apt = client.run_request_item_catalogs_items(
            ZigbangItemCatalogsItemsRequestParameterModel(item_id=item_id, item_source='coalition')
        ).item
    trade_type = TRADE_BY_APT_TRAN_TYPE.get(apt.tran_type or '')
    if trade_type is None:
        raise ListingUnavailableError('zigbang', listing_id, reason='UNKNOWN_TRADE_TYPE')
    is_sale = trade_type == '매매'
    detail = ZigbangListingDetail(
        source='zigbang',
        id=listing_id,
        url=apt_item_url(item_id, 'coalition'),
        trade_type=trade_type,
        property_type='아파트',
        title=apt.item_title,
        price_manwon=apt.deposit if is_sale else None,
        deposit_manwon=None if is_sale else apt.deposit,
        rent_manwon=apt.rent if trade_type == '월세' else None,
        area_m2=apt.size_m2,
        area_pyeong=m2_to_pyeong(apt.size_m2),
        floor=apt.floor,
        building_floor=str(apt.building_floor) if apt.building_floor is not None else None,
        address=apt.old_address or None,
        direction=DIRECTION_LABELS.get((apt.direction or '').upper(), apt.direction),
        move_in=apt.movein_date,
        parking=f'세대당 주차 대수 {apt.parking_count_by_household:g}대' if apt.parking_count_by_household is not None else None,
    )
    return apply_apt_detail(detail, apt)


def apply_apt_detail(detail: ZigbangListingDetail, apt: ZigbangAptItemModel | None) -> ZigbangListingDetail:
    """아파트 상세(`/apt/item-catalogs/items`)로 `/v3/items` 가 비워 둔 값을 채운다.

    관리비는 아파트 상세 것만 쓴다. `/v3/items` 는 아파트 관리비를 금액 없이 '모두 별도' 로 주는데
    사실과 달라, 아파트 상세가 없거나 확인 불가면 모름(None)으로 둔다. 층은 아파트 상세가
    '저'·'중'·'고' 로만 줘서 `/v3/items` 의 층을 그대로 둔다. 옵션은 두 상세 모두 아파트에 빈 목록만 주고 아파트
    상세에는 옵션 칸이 없어 (2026-10-11 실측 19건) 모름(None)으로 둔다.
    """
    cost = apt.manage_cost.amount if apt and apt.manage_cost else None
    update: dict[str, object] = {
        'manage_cost_manwon': won_to_manwon(cost.monthly_cost) if cost else None,
        'manage_cost_includes': cost.include_items if cost else None,
        'options': None,
    }
    if apt is not None:
        update |= {
            'complex_id': apt_complex_id(apt.area_danji_id) if apt.area_danji_id else None,
            'complex_name': join_address(apt.area_danji_name, apt.area_building_name),
            'supply_area_m2': apt.size_contract_m2,
            'room_count': apt.room_count,
            'bathroom_count': apt.bathroom_count if apt.bathroom_count is not None else detail.bathroom_count,
            'approved_at': normalize_date(apt.approval_date) or detail.approved_at,
        }
    return detail.model_copy(update=update)


def unsearchable_types(property_types: Sequence[str], trade_types: Sequence[str]) -> list[str]:
    """거래 유형 조건 때문에 직방에서 조회할 수 없는 유형. 원룸은 매매가 없다 (전세·월세·단기임대만).

    `search_listings` 는 이런 유형을 요청 없이 건너뛰므로, 0건을 "매물이 없다"로 오해하지
    않도록 호출한 쪽이 `unsearchable_note` 로 알린다.
    """
    if '원룸' in property_types and trade_types and all(trade == '매매' for trade in trade_types):
        return ['원룸']
    return []


def unsearchable_note(types: list[str]) -> str:
    return (
        f"직방은 {'·'.join(types)} 매매를 다루지 않아 조회하지 않았습니다 (전세·월세·단기임대만). "
        '매매는 빌라·오피스텔이나 다른 소스에서 찾으세요'
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


def check_without_random(property_types: list[ZigbangPropertyType]) -> None:
    """무작위 섞기 해제는 오피스텔 목록에만 있다. CLI 는 지역을 찾기 전에 같은 검사로 막는다.

    Raises:
        JibsaError: 찾는 유형에 오피스텔이 없을 때 (INVALID_ARGUMENT).
    """
    if '오피스텔' not in property_types:
        raise JibsaError(
            code='INVALID_ARGUMENT', message='무작위 섞기 해제는 오피스텔에만 지원됩니다',
            hint='--type 오피스텔을 포함하거나 --without-random을 빼세요',
        )


class _ScopePins(NamedTuple):
    """`_collect_pins` 결과: 범위 안 핀(매물 ID → (핀, 중심에서 거리)), 유형별 안내, 원룸 조회 조건과 지도 칸."""

    pins: dict[int, tuple[ZigbangItemPinModel, float]]
    notes: list[str]
    # 원룸 목록에 섞여 온 오피스텔의 건물 ID 를 같은 조건의 오피스텔 목록으로 채울 때 쓴다
    oneroom_query: tuple[list[ZigbangSalesType], dict[str, object]] | None
    # 원룸 핀을 받은 지도 칸. 건물 ID 가 빠진 매물이 있던 칸만 오피스텔 목록을 다시 받는다
    oneroom_cells: dict[int, str]


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
) -> ZigbangSearchResult:
    """중심점 반경 안의 매물을 가까운 순으로 `limit` 건 조회한다.

    반경을 덮는 geohash 타일마다 매물 핀을 받아 반경 밖과 중복을 걸러낸 뒤,
    가까운 핀 `limit` 개의 요약을 15개씩 받아 `Listing` 으로 바꾼다. 가격·관리비(만원), 방 구조,
    면적(㎡·평), 층, 욕실 수, 옵션, 기타 조건(`CONDITION_FIELD_BY_LABEL`)은 서버에서 거른다.
    요약을 받은 뒤 거래 불가·지원하지 않는 거래 종류로 뺀 매물은 다시 채우지 않고 `notes` 로 알린다.

    원룸은 건물 종류가 아니라 방 하나짜리를 뜻한다. 직방 원룸 목록은 오피스텔(투룸 포함)을 함께 주므로
    원룸형 구조(`ONE_ROOM_STRUCTURES`)만 서버에 요청하고, 섞여 온 원룸형 오피스텔은 결과에 넣는다.
    원룸 목록 핀에는 건물 ID 가 없어, 오피스텔을 따로 조회하지 않았으면 같은 범위·조건의 오피스텔
    목록을 한 번 더 받아 `complex_id` 를 채운다 (결과에 건물 ID 없는 오피스텔이 있을 때만).

    받아 온 지도 칸에는 반경 밖 매물도 있다. 반경 안 매물이 `limit` 보다 적으면 그 매물도
    가까운 순으로 이어 돌려주고 `notes` 로 알린다.

    `boundary` 를 주면 반경 대신 그 동 경계 안의 매물만 찾는다 (경계를 덮는 지도 칸을 받아 경계 안 핀만
    남긴다). 이때는 반경 밖 매물을 잇지 않고, 가까운 순은 검색 중심(동 중심)에서 잰다.

    `subway_id` 를 명시하면 지도 칸 대신 역 반경 전용 API 를 유형별 1회 조회하고 반경 밖은 제외한다.
    주지 않으면(좌표·동·구 검색) 지도 칸으로 찾는다.
    `conditions.without_random` 은 오피스텔 요청의 서버 셔플만 끄며, 최종 결과는 거리순이다.

    직방 카테고리별 방 구조: 원룸 = 오픈형·분리형·복층형 원룸 (원룸형 오피스텔 포함), 빌라 = 투룸·
    쓰리룸·포룸이상 (원룸형 구조만 주면 빌라는 조회하지 않는다), 오피스텔 = 원룸형·투룸·쓰리룸 이상.

    거래 유형도 서버에서 거른다. 직방의 '월세' 필터는 단기임대를 빼고, 단기임대는 '단기' 로
    따로 받는다 (`SALES_TYPE_BY_TRADE`). 거래 유형을 주지 않으면 단기임대도 함께 나온다.
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
    if conditions.without_random:
        check_without_random(property_types)

    geohashes = [] if subway_id is not None else scope_geohashes(region, radius_km, boundary, GEOHASH_PRECISION)
    scan = _collect_pins(
        client, region, conditions, property_types, requested_types,
        geohashes=geohashes, subway_id=subway_id, radius_km=radius_km, boundary=boundary,
    )

    # 조회 예산은 요약을 받는 핀 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    nearest = sorted(scan.pins.values(), key=lambda entry: entry[1])[:limit]
    distance_by_id = {pin.id: distance for pin, distance in nearest}
    building_by_id = {pin.id: pin.building_id for pin, _ in nearest}
    ids = [pin.id for pin, _ in nearest]

    # 원룸 목록에 섞여 온 원룸형 오피스텔도 그대로 둔다
    listings: list[Listing] = [
        summary_to_listing(summary, distance_by_id.get(summary.item_id), building_by_id.get(summary.item_id))
        for summary in tradeable_summaries(client, ids)
    ]
    if scan.oneroom_query is not None and '오피스텔' not in property_types:
        _fill_officetel_complex_ids(client, listings, scan, subway_id=subway_id, radius_km=radius_km)

    listings.sort(key=by_distance)
    listings = listings[:limit]
    notes = scan.notes + excluded_notes(limit, len(ids), len(listings))
    return _search_result(region, listings, scan.pins, notes, limit=limit, radius_km=radius_km, boundary=boundary)


def _type_query(
    property_type: ZigbangPropertyType,
    conditions: ZigbangRoomConditions,
    requested_types: list[ZigbangPropertyType],
    filters: dict[str, object],
    notes: list[str],
) -> tuple[list[ZigbangSalesType], dict[str, object]] | None:
    """유형 하나의 (거래 유형 필터, 요청 필드). 그 유형은 조회할 게 없으면 None 이고 직접 찾은 유형이면 `notes` 에 알린다."""
    all_sales_types = [SALES_TYPE_BY_TRADE[trade] for trade in conditions.trade_types]
    sales_types = all_sales_types
    type_rooms = list(conditions.room_types)
    if property_type == '빌라' and type_rooms and all(room in ONE_ROOM_STRUCTURES for room in type_rooms):
        # 직방 빌라 목록은 투룸 이상뿐이라 원룸형 구조만 주면 늘 0건이다 (2026-10-10 실측: 3개 동 빌라
        # 135건 모두 투룸 이상, 원룸형 조건 0건). 빌라 건물의 원룸은 직방이 원룸 목록에 둔다
        if '빌라' in requested_types:
            notes.append(
                '직방 빌라 목록은 투룸 이상만 있어 --room 의 원룸형 조건으로는 조회하지 않았습니다. '
                '빌라(다세대·다가구) 건물의 원룸은 -t 원룸으로 찾으세요'
            )
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
                notes.append('원룸은 방 하나짜리(오픈형·분리형·복층형)만 찾아 --room 의 투룸 이상 조건으로는 조회하지 않았습니다')
            return None
    type_filters = {**filters, 'room_types': [ROOM_TYPE_FILTER_BY_LABEL[room] for room in type_rooms]}
    if property_type == '원룸':
        # 직접 원룸을 찾을 때만 알린다. 아파트에는 단기임대가 없어 단기임대만 찾으면 알리지 않는다
        if '원룸' in requested_types and set(conditions.trade_types) != {'단기임대'}:
            notes.append(APT_ONE_ROOM_NOTE)
    if property_type == '오피스텔' and conditions.without_random:
        type_filters['without_random'] = True
    return sales_types, type_filters


def _collect_pins(
    client: ZigbangClient,
    region: ZigbangRegion,
    conditions: ZigbangRoomConditions,
    property_types: list[ZigbangPropertyType],
    requested_types: list[ZigbangPropertyType],
    *,
    geohashes: list[str],
    subway_id: int | None,
    radius_km: float,
    boundary: ZigbangBoundary | None,
) -> _ScopePins:
    """유형마다 검색 범위의 핀을 받아 범위 밖과 중복을 거른다."""
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
    scan = _ScopePins(pins={}, notes=[], oneroom_query=None, oneroom_cells={})
    for property_type in property_types:
        query = _type_query(property_type, conditions, requested_types, filters, scan.notes)
        if query is None:
            continue
        sales_types, type_filters = query
        if property_type == '원룸':
            scan = scan._replace(oneroom_query=query)
        responses = _scope_pins(
            client, property_type, geohashes=geohashes, subway_id=subway_id, radius_km=radius_km,
            sales_types=sales_types, type_filters=type_filters,
        )
        for geohash, response in responses:
            for pin in response.items:
                if outside_boundary(boundary, pin.lat, pin.lng):
                    continue
                distance = haversine_km(region.lat, region.lng, pin.lat, pin.lng)
                if subway_id is not None and distance > radius_km:
                    continue
                known = scan.pins.get(pin.id)
                if known is not None and known[0].building_id and not pin.building_id:
                    # 원룸 목록에 섞여 온 오피스텔 핀이 건물 ID 를 지우지 않게 한다
                    continue
                scan.pins[pin.id] = (pin, distance)
                if property_type == '원룸' and geohash is not None:
                    scan.oneroom_cells[pin.id] = geohash
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
    except BUILDING_LOOKUP_ERRORS:
        # 건물 ID 는 덤이라 못 받으면 모름(null)으로 둔다
        buildings = {}
    for listing in missing:
        building_id = buildings.get(int(listing.id))
        if building_id:
            listing.complex_id = officetel_complex_id(building_id)


def _search_result(
    region: ZigbangRegion,
    listings: list[Listing],
    pins: dict[int, tuple[ZigbangItemPinModel, float]],
    notes: list[str],
    *,
    limit: int,
    radius_km: float,
    boundary: ZigbangBoundary | None,
) -> ZigbangSearchResult:
    """범위 안 핀 수와 조회 한도·반경 밖 안내를 붙여 결과를 만든다."""
    if boundary is not None:
        in_boundary = len(pins)
        return ZigbangSearchResult(
            region=region,
            boundary=boundary.name,
            total_in_radius=in_boundary,
            returned=len(listings),
            listings=listings,
            notes=notes
            + limit_notes(in_boundary, len(listings), limit, order=f'{boundary.name} 중심에서 가까운', approximate=True),
        )
    in_radius = sum(1 for _, distance in pins.values() if distance <= radius_km)
    return ZigbangSearchResult(
        region=region,
        radius_km=radius_km,
        total_in_radius=in_radius,
        returned=len(listings),
        listings=listings,
        # 핀 수는 거래 불가·조건 불일치를 요약에서 거르기 전이라 근사값이다
        notes=notes
        + limit_notes(in_radius, len(listings), limit, approximate=True, radius=True)
        + beyond_radius_notes(listings, radius_km),
    )


def get_listing(client: ZigbangClient, item_id: int) -> ZigbangListingDetail:
    """새 주거 상세 + 등록일·단기임대 요약을 조회한다. 입주일이 null이면 기존 상세 1회를 추가한다.

    아파트는 단지 이름·방 수·욕실 수·사용승인일·관리비를 아파트 상세에서 받아 1회 더 호출한다.
    원룸·빌라·오피스텔은 학군을 건물(필지) 학군에서 받아 1회 더 호출한다 (실패하면 모름).
    아파트 상세만 404 면 그 값들을 모름(None)으로 두고 나머지는 그대로 돌려준다.

    Raises:
        ListingUnavailableError: 없는 매물(404)이거나 상태가 open 이 아닐 때 (상태가 없을 때 포함).
        JibsaError: 거래 중인 매물인데 거래 유형·매물 유형이 없을 때 (PARSE_ERROR).
    """
    with unavailable_on_404(item_id):
        structured = client.run_request_items_detail_v1(
            ZigbangItemsDetailV1RequestParameterModel(item_id=item_id)
        )
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
        # 실측: 두 API 의 status 는 늘 같고(open·close·cancel), 아파트는 입주일이 늘 null 이라 매번 이 호출을 탄다.
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
    if structured.item.service_type != '아파트' and pnu:
        try:
            schools = building_schools(client.run_request_bls_school_zones_v1(
                ZigbangBlsSchoolZonesV1RequestParameterModel(pnu=pnu)
            ))
        except SCHOOL_LOOKUP_ERRORS:
            # 학군을 못 받아도 매물 상세는 돌려준다 (모름)
            schools = None
    apt = None
    if structured.item.service_type == '아파트':
        try:
            apt = client.run_request_item_catalogs_items(
                ZigbangItemCatalogsItemsRequestParameterModel(item_id=item_id)
            ).item
        except HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
    detail = detail_to_listing(
        structured,
        legacy=legacy.item if legacy else None,
        registered_at=summary.reg_date if summary else None,
        short_term=summary is not None and trade_type_of(summary) == '단기임대',
        apt=apt,
    )
    updates: dict[str, object] = {
        'total_parking_count': residence.total_parking_count,
        'household_count': residence.household_count,
        'direction_criterion': residence.direction_criterion,
    }
    if schools is not None:
        updates['schools'] = schools
    return detail.model_copy(update=updates)
