"""직방 service 공통의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.geo import MultiPolygon
from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    AmountSet,
    Listing,
    ListingDetail,
    TradeType,
    with_floor_number,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.common import (
    ZigbangFloorFilter,
    ZigbangOptionFilter,
)
from jibsa.providers.zigbang.service.common.constants import (
    ACTUAL_LISTING_CHECKED_DESCRIPTION,
    APT_LISTING_KIND_DESCRIPTION,
    APT_ONLY_DETAIL_FIELDS,
    APT_PYEONG_ID_DESCRIPTION,
    APT_PYEONG_NAME_DESCRIPTION,
    COMPLEX_DETAIL_FIELDS,
    HUG_LESSOR_DESCRIPTION,
    ROOM_ONLY_DETAIL_FIELDS,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangRegion(BaseModel):
    """검색 중심점."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='지역·역 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='전체 주소')
    ] = None
    lat: Annotated[
        float,
        Field(description='중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='중심 경도')
    ]
    search_type: Annotated[
        str | None,
        Field(exclude=True, description='직방 검색 결과 유형. 단기임대 검색용이며 출력하지 않는다')
    ] = None
    local1: Annotated[
        str | None,
        Field(exclude=True, description='시·도 검색 맥락. 출력하지 않는다')
    ] = None
    local2: Annotated[
        str | None,
        Field(exclude=True, description='시·군·구 검색 맥락. 출력하지 않는다')
    ] = None
    local3: Annotated[
        str | None,
        Field(exclude=True, description='읍·면·동 검색 맥락. 출력하지 않는다')
    ] = None
    subway_id: Annotated[
        int | None,
        Field(gt=0, exclude=True, description='직방 역 검색 결과 ID. 역 전용 API 조회용이며 출력하지 않는다')
    ] = None
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리)')
    ] = None


class ZigbangAptRegion(BaseModel):
    """아파트를 찾는 동·구 하나 (search listings apt 의 region, search complexes 의 동·구).

    아파트는 반경이 아니라 지역 코드로 찾아 좌표를 쓰지 않는다. 그래서 `ZigbangRegion` 과 달리 직방이 검색 결과에 좌표를
    주지 않아도 만들 수 있고, 그때 좌표는 모름(null)이다. 출력 필드와 순서는 `ZigbangRegion` 과 같다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동·구 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='전체 주소')
    ] = None
    lat: Annotated[
        float | None,
        Field(description='중심 위도. 이름으로 찾았는데 직방이 좌표를 주지 않았으면 모름(null)')
    ]
    lng: Annotated[
        float | None,
        Field(description='중심 경도. 이름으로 찾았는데 직방이 좌표를 주지 않았으면 모름(null)')
    ]
    local3: Annotated[
        str | None,
        Field(exclude=True, description='읍·면·동 검색 맥락. 리를 상위 읍·면으로 찾을 때 쓰며 출력하지 않는다')
    ] = None
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리)')
    ] = None


class ZigbangListing(Listing):
    """직방 원룸·오피스텔·빌라 매물. 오피스텔은 건물 ID 를 붙여 그 건물 매물을 이어서 볼 수 있다."""

    complex_id: Annotated[
        str | None,
        Field(description='오피스텔 건물 ID (예: officetel-20227, 오피스텔만). zigbang complex·items 에 넘긴다')
    ] = None
    hug_lessor: Annotated[
        bool | None,
        Field(description=HUG_LESSOR_DESCRIPTION)
    ] = None
    actual_listing_checked: Annotated[
        bool | None,
        Field(description=ACTUAL_LISTING_CHECKED_DESCRIPTION)
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.property_type != '오피스텔':
            fields = fields | {'complex_id'}
        return fields


class ZigbangBoundary(BaseModel):
    """반경 대신 쓰는 동 경계 (출력하지 않는 내부 값)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동 이름')
    ]
    code: Annotated[
        str,
        Field(description='직방 지역 코드 (법정동코드 앞 8자리)')
    ]
    polygons: Annotated[
        MultiPolygon,
        Field(description='경계 (GeoJSON MultiPolygon 좌표)')
    ]


class ZigbangNearbyFacility(BaseModel):
    """주변 생활 시설 하나 (웹 상세의 '주변 생활 시설' 그림에 그려지는 시설)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    type: Annotated[
        str | None,
        Field(description='시설 종류 (지하철역·버스정류장·편의점·카페·약국·세탁소·대형마트. 직방이 준 글자 그대로). 직방이 종류를 주지 않으면 null')
    ] = None
    travel_minutes: Annotated[
        int,
        Field(description='걸리는 시간 (분). 웹처럼 직방이 준 초를 분으로 반올림하고 (.5분은 올림) 0분이 되면 1분으로 쓴다')
    ]
    transport: Annotated[
        str,
        Field(description='이동 수단 (도보·차)')
    ]
    distance_m: Annotated[
        int | float | None,
        Field(description='거리 (m). 웹은 거리를 그리지 않고 분만 그린다. 직방이 주지 않으면 null')
    ] = None


class ZigbangBuildingTrade(BaseModel):
    """건물(필지)의 실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 가격 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ] = None
    trade_type: Annotated[
        str | None,
        Field(description='거래 유형 (매매·전세·월세). 직방이 모르는 값을 주면 null (그때는 가격 필드를 직방이 준 대로 모두 낸다)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 (예 '4', '지하1'). 직방이 주지 않으면 null")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원). 매매만 있고 다른 유형은 키가 없다')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금·전세금 (만원). 전세·월세만 있고 매매는 키가 없다')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원). 월세만 있고 매매·전세는 키가 없다')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡). 직방이 주지 않으면 null')
    ] = None
    land_area_m2: Annotated[
        float | None,
        Field(description='대지권면적 (㎡). 직방이 주지 않으면 null')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 거래 유형을 모르면(None) 뺄 가격 필드가 없다
        for field in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type or '', frozenset()):
            data.pop(field, None)
        return with_floor_number(data)


class ZigbangEstimatedPrice(AmountSet):
    """직방시세® 거래 하나의 값 (estimated_prices 의 sale·jeonse). 생성할 때 넘긴 칸만 출력한다 (`AmountSet` 의 직렬화기).

    넘긴 None 은 모름(null)이고, 넘기지 않은 칸은 그 거래에 해당 없음이라 키가 없다 (매매는 price_manwon, 전세는 deposit_manwon).
    안 칸을 모두 모르면 이 객체를 만들지 않고 그 거래를 null 로 낸다.
    """

    price_manwon: Annotated[
        float | None,
        Field(description='직방시세® 매매가 (만원, 추정값). 직방이 주지 않거나 0 이면 null')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='직방시세® 전세가 (만원, 추정값). 직방이 주지 않거나 0 이면 null')
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='직방시세® 평당가 (만원, 3.3㎡당). 직방이 주지 않거나 0 이면 null')
    ] = None


class ZigbangListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 매물. `complex_id`·`complex_name` 은 아파트·오피스텔, 아파트 전용 필드(`APT_ONLY_DETAIL_FIELDS`)는 아파트에만,
    원룸·빌라·오피스텔 전용 필드(`ROOM_ONLY_DETAIL_FIELDS`)는 아파트를 뺀 유형에만 있다.

    `notes`: 덤 조회(건물 학군·건물 실거래) 실패 안내와, 직방이 빈 항목을 줘 모름(null)으로 둔 칸의 [제외] 안내. CLI 가 결과 위에 붙인다
    """

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
    parking_count: Annotated[
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
    confirmed_date: Annotated[
        str | None,
        Field(description=(
            "직방이 매물을 마지막으로 확인한 날짜 (YYYY-MM-DD, 한국 시간). 웹 매물 화면은 이 시각으로 아파트는 '2주 전 확인', 원룸·빌라·오피스텔은 "
            "개요의 '33일 전' 같은 상대 표기를 보여 준다. 직방 응답의 아파트는 effectivenessUpdatedAt, 원룸·빌라·오피스텔은 meta.statusCheckedAt 이다. 모르면 null"
        ))
    ] = None
    actual_listing_checked: Annotated[
        bool | None,
        Field(description=ACTUAL_LISTING_CHECKED_DESCRIPTION + ' (아파트는 직방이 준 isActualItemChecked 그대로)')
    ] = None
    non_compliant_building: Annotated[
        bool | None,
        Field(description="위반 건축물 여부 (웹 매물 정보의 '위반건축물 여부': true 해당, false 해당 없음). 직방이 주지 않으면(제휴 매물 등) null")
    ] = None
    hug_lessor: Annotated[
        bool | None,
        Field(description=HUG_LESSOR_DESCRIPTION + ' (아파트는 직방이 준 isHugLessor 그대로)')
    ] = None
    favorite_count: Annotated[
        int | None,
        Field(description='찜 수 (웹 하트 옆 숫자, 아파트만. 0 이면 웹은 숫자를 그리지 않지만 0 그대로 낸다). 직방이 주지 않으면 null')
    ] = None
    nearby_facilities: Annotated[
        list[ZigbangNearbyFacility] | None,
        Field(description=(
            "주변 생활 시설 (원룸·빌라·오피스텔만, 웹의 '주변 생활 시설'). 가까운 시설이 있는 종류만 도보 시설을 걸리는 시간 순으로, 그다음 차 시설을 "
            '같은 순으로 낸다 (웹 그림의 순서). 가까운 시설이 하나도 없으면 [], 직방이 주변 정보를 주지 않으면 null'
        ))
    ] = None
    delivery_services: Annotated[
        list[str] | None,
        Field(description=(
            "이 주소로 배송하는 업체 이름 (원룸·빌라·오피스텔만, 웹의 '이 지역은 하루 배송권이에요'. 예: 쿠팡·SSG·마켓컬리). 직방 응답 순서. "
            '배송 업체가 없으면 [] (웹은 이 칸을 숨긴다), 직방이 주변 정보를 주지 않으면 null'
        ))
    ] = None
    manage_cost_excludes: Annotated[
        list[str] | None,
        Field(description=(
            "관리비에 들지 않는 항목 (웹 '관리비 미포함 항목', 예: 전기·수도·가스·난방·인터넷·TV·기타 관리비). 원룸·빌라·오피스텔은 웹 순서"
            '(`manage_cost_includes` 와 같다), 아파트는 직방 응답 순서. 없으면 [], 직방이 주지 않거나 관리비를 확인할 수 없거나 직방이 빈 항목을 줘 셀 수 없으면 null. '
            '원룸·빌라·오피스텔에서 관리비가 없거나 정액 관리비가 항목별 내역을 알린 매물은 웹이 미포함 항목을 보여 주지 않아 []'
        ))
    ] = None
    manage_cost_period: Annotated[
        str | None,
        Field(description=(
            "관리비 부과 기준 (예: '직전 월 관리비 기준', '최근 3개월 관리비 평균', '최근 1년 관리비 평균', 또는 중개사가 직접 쓴 글자). "
            '직방이 주지 않거나 표에 없는 코드면 null'
        ))
    ] = None
    manage_cost_method: Annotated[
        str | None,
        Field(description=(
            "관리비 부과 방식 (웹 문구 그대로, 예: '관리규약에 따라 부과해요.', 또는 중개사가 직접 쓴 글자). 실비 관리비만 직방의 방식 코드로 정하고, "
            '직방이 주지 않거나 표에 없는 코드면 null. 정액 관리비는 방식 코드를 읽지 않고 웹처럼 정한다: 항목별 내역을 알리지 않았으면 '
            "('중개 의뢰인이 세부내역을 고지하지 않아 전세입자 등을 통해 추정된 관리비를 안내해요.')를 내고, 내역을 알렸으면 null"
        ))
    ] = None
    building_trades: Annotated[
        list[ZigbangBuildingTrade] | None,
        Field(description=(
            '건물(필지) 실거래 (원룸·빌라·오피스텔만, 웹의 건물 실거래가). 직방이 준 거래 전부를 계약일 최신순으로 낸다 (웹은 3건만 보이고 더보기로 5건씩 연다). '
            '필지가 없거나 조회에 실패하면 null, 거래가 없으면 []'
        ))
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.property_type == '아파트':
            fields = fields | ROOM_ONLY_DETAIL_FIELDS
        if self.property_type not in ('아파트', '오피스텔'):
            fields = fields | COMPLEX_DETAIL_FIELDS
        if self.property_type != '아파트':
            fields = fields | APT_ONLY_DETAIL_FIELDS
        return fields


class ZigbangAptListing(Listing):
    """직방 아파트 매물. 같은 호·거래 유형의 매물(중개사별)을 하나로 묶은 카탈로그 한 건이다."""

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (예: apt-68579). zigbang complex·items 에 넘긴다')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). --supply-area 조건은 이 값에 걸린다')
    ] = None
    mixed_prices: Annotated[
        bool | None,
        Field(description='true 면 같은 호를 올린 매물끼리 가격이 달라 가격은 묶음의 최저가라 id 매물의 가격과 다를 수 있다. 매물별 가격은 catalog_id 를 zigbang catalog 에 넘겨 한 번에 본다')
    ] = None
    catalog_id: Annotated[
        str | None,
        Field(description='같은 호·거래 유형의 매물 묶음 ID (예: 8260358-trade). zigbang catalog 에 넘기면 묶음 매물 전부를 매물마다의 가격·상세와 함께 준다. 직방이 호 ID 를 주지 않으면 모름(null)이고, 그때 url 은 id 매물 페이지이며 묶음은 catalog 로 볼 수 없어 listing_ids 를 listing 으로 하나씩 본다')
    ] = None
    listing_ids: Annotated[
        list[str],
        Field(description='같은 호를 올린 매물 중 상세를 볼 수 있는 ID 전부 (id 포함, id 가 맨 앞). zigbang listing 에 넘긴다')
    ] = []
    realtor_count: Annotated[
        int | None,
        Field(description='같은 호를 올린 매물(중개사) 수')
    ] = None
    listing_kind: Annotated[
        str | None,
        Field(description=APT_LISTING_KIND_DESCRIPTION)
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description=APT_PYEONG_ID_DESCRIPTION)
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description=APT_PYEONG_NAME_DESCRIPTION)
    ] = None


class ZigbangRoomConditions(RequestModel):
    """원룸·빌라·오피스텔 매물 조건 (search listings room, search listings --complex). 금액은 만원.

    라벨은 `TRADE_TYPES`·`ROOM_TYPES`·`FLOOR_FILTERS`·`OPTION_FILTERS`·`CONDITIONS` 의 값이다. 값의 범위·조합은
    CLI 가 먼저 검사한다. 거래 유형·가격은 `filters` 처럼 유형마다 따로 넣고, 나머지는 `room_filter_of` 로 바꾼다.
    """

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형. 비면 전체')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    room_types: Annotated[
        list[str],
        Field(description='방 구조 (ROOM_TYPES). 비면 유형별 기본')
    ] = []
    manage_cost_min: Annotated[
        int | None,
        Field(description='월 관리비 하한 (만원)')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(description='월 관리비 상한 (만원)')
    ] = None
    no_manage_cost: Annotated[
        bool,
        Field(description='관리비 없는 매물만')
    ] = False
    area_min_m2: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    area_min_pyeong: Annotated[
        float | None,
        Field(description='면적 하한 (평)')
    ] = None
    area_max_pyeong: Annotated[
        float | None,
        Field(description='면적 상한 (평)')
    ] = None
    floors: Annotated[
        list[ZigbangFloorFilter],
        Field(description='층 (FLOOR_FILTERS, OR)')
    ] = []
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수 (3 은 3개 이상)')
    ] = None
    options: Annotated[
        list[ZigbangOptionFilter],
        Field(description='옵션 (OPTION_FILTERS, AND)')
    ] = []
    extra_conditions: Annotated[
        list[str],
        Field(description='기타 조건 (CONDITIONS, AND)')
    ] = []


def drop_unused_scope(data: dict[str, Any]) -> dict[str, Any]:
    """검색 결과에서 쓰지 않은 범위 키(반경이면 boundary, 경계면 radius_km)를 뺀다."""
    for field in ('radius_km', 'boundary'):
        if data.get(field) is None:
            data.pop(field, None)
    return data
