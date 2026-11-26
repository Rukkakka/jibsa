"""직방 service 공통(기본): 지역·매물·동 경계·상세 결과 모델, 상세 URL·단지 ID, 단지 조회, 여러 모듈이 쓰는 상수."""

import re
from collections.abc import Generator
from contextlib import contextmanager

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.geo import MultiPolygon
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    UPDATE_MAYBE_NEEDED,
    AmountRange,
    AmountSet,
    Listing,
    ListingDetail,
    with_floor_number,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangDanjisResponseModel

from typing import (
    Annotated,
    Any,
    Literal,
)


WEB_PATH_BY_SERVICE_TYPE: dict[str, str] = {
    '원룸': 'oneroom',
    '오피스텔': 'officetel',
    '빌라': 'villa',
}
# 덤 조회(학군·건물 ID·--details 상세 등)는 이 실패들을 그 칸만 모름으로 둔다. 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`:
# 네트워크·상태 코드, 차단 페이지·응답 형식 변경·19자리가 아닌 pnu)에 요청 제한을 더한다
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, RateLimitedError)
# 매물 목록 명령의 --limit 최대값. CLI 옵션의 max 와 상한 안내(`common.apt` 의 `apt_pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120
# 목록 줄(`ZigbangListing`)과 상세가 함께 쓰는 HUG안심임대인·실매물 확인 필드 설명. 배지 코드는 `common.room` 의 `HUG_BADGE`·`VERIFICATION_BADGE`
HUG_LESSOR_DESCRIPTION: str = (
    "HUG 안심임대인 (웹의 'HUG안심임대인' 꼬리표). 직방 배지에 HUG 가 있으면 true, 배지를 받았는데 없으면 false, 직방이 배지를 주지 않으면 null"
)
ACTUAL_LISTING_CHECKED_DESCRIPTION: str = (
    "직방 웹의 '실매물 확인' 꼬리표. 직방이 뜻을 설명하지 않는다. 직방 배지에 ITEM_VERIFICATION 이 있으면 true, 배지를 받았는데 없으면 false "
    '(확인 실패 ITEM_VERIFICATION_FAILED 도 false), 직방이 배지를 주지 않으면 null'
)
# 아파트 목록 줄(`common.apt` 의 `ZigbangAptListing`)과 상세가 함께 쓰는 매물 종류 필드 설명. 종류 코드 표(`APT_LISTING_KIND_LABELS`)는 `common.apt` 에 있다
APT_LISTING_KIND_DESCRIPTION: str = (
    '매물 종류: 신규분양(분양 매물, 가격은 분양가)·집주인(집주인이 내놓은 매물)·중개사(중개사무소가 등록한 매물). '
    '모르는 코드는 직방 코드 그대로, 직방이 주지 않으면 null (묶음 줄은 묶음 맨 앞 매물이 상세를 볼 수 없는 출처라 id 가 맨 앞 매물이 아닐 때도 null. '
    '묶인 매물 ID 목록에 직방이 빈 항목을 줘 맨 앞 매물을 알 수 없을 때도 null)'
)
# 아파트 매물 줄·상세가 함께 쓰는 평형 필드 설명. 이름 규칙은 real-price 의 pyeong_name(평 기준)과 같다
APT_PYEONG_ID_DESCRIPTION: str = (
    '평형 ID (complex 의 pyeongs[].pyeong_id 와 같은 번호). search listings --complex <단지> --pyeong·real-price <단지> --pyeong 에 넘긴다. 모르면 null'
)
APT_PYEONG_NAME_DESCRIPTION: str = '평형 이름 (평 기준, 예: 34A. complex 의 pyeongs[].pyeong_name 과 같다). 모르면 null'
# 단지·건물이 있는 유형(아파트·오피스텔)의 상세에만 있는 필드, 아파트 상세에만 있는 필드, 원룸·빌라·오피스텔 상세에만 있는 필드.
# 없는 유형은 키를 뺀다. 찜 수는 웹 www 의 원룸·빌라·오피스텔 화면에 보이지 않아 아파트만이다. 아파트 학군은 단지 정보
# (zigbang complex)에서 주고, 아파트 상세 응답에는 주변 시설·배송 업체가 없다
COMPLEX_DETAIL_FIELDS: frozenset[str] = frozenset({'complex_id', 'complex_name'})
APT_ONLY_DETAIL_FIELDS: frozenset[str] = frozenset({'supply_area_m2', 'listing_kind', 'pyeong_id', 'pyeong_name', 'favorite_count'})
ROOM_ONLY_DETAIL_FIELDS: frozenset[str] = frozenset({'schools', 'nearby_facilities', 'delivery_services', 'building_trades'})
# 방향 코드 → 라벨. 주거 상세(`room.detail`)와 아파트 상세(`apt`)가 함께 쓴다
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


def estimated_prices_of(
    sale_price_manwon: float | None,
    sale_price_per_pyeong_manwon: float | None,
    jeonse_price_manwon: float | None,
    jeonse_price_per_pyeong_manwon: float | None,
) -> dict[str, ZigbangEstimatedPrice | None]:
    """직방시세® 매매·전세 값을 estimated_prices 로 묶는다. 늘 'sale'·'jeonse' 두 키이고, 거래의 안 값이 모두 없으면 그 거래가 모름(null), 일부만 없으면 그 칸만 null 이다."""
    return {
        'sale': None if sale_price_manwon is None and sale_price_per_pyeong_manwon is None else ZigbangEstimatedPrice(
            price_manwon=sale_price_manwon, price_per_pyeong_manwon=sale_price_per_pyeong_manwon,
        ),
        'jeonse': None if jeonse_price_manwon is None and jeonse_price_per_pyeong_manwon is None else ZigbangEstimatedPrice(
            deposit_manwon=jeonse_price_manwon, price_per_pyeong_manwon=jeonse_price_per_pyeong_manwon,
        ),
    }


def sale_price_range(lowest_manwon: float | None, highest_manwon: float | None) -> AmountRange | None:
    """매매가 범위 (직방시세 estimated_ranges 의 'sale', 평형 추이 trade_range). 두 끝이 모두 없으면 모름(None)이고, 한 끝만 없으면 그 price_manwon 만 null 이다."""
    if lowest_manwon is None and highest_manwon is None:
        return None
    return AmountRange(lowest=AmountSet(price_manwon=lowest_manwon), highest=AmountSet(price_manwon=highest_manwon))


class ZigbangListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 매물. `complex_id`·`complex_name` 은 아파트·오피스텔, 아파트 전용 필드(`APT_ONLY_DETAIL_FIELDS`)는 아파트에만,
    원룸·빌라·오피스텔 전용 필드(`ROOM_ONLY_DETAIL_FIELDS`)는 아파트를 뺀 유형에만 있다."""

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
    notes: Annotated[
        list[str],
        Field(exclude=True, description=(
            '덤 조회(건물 학군·건물 실거래) 실패 안내와, 직방이 빈 항목을 줘 모름(null)으로 둔 칸의 [제외] 안내. CLI 가 결과 위에 붙인다'
        ))
    ] = []

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.property_type == '아파트':
            fields = fields | ROOM_ONLY_DETAIL_FIELDS
        if self.property_type not in ('아파트', '오피스텔'):
            fields = fields | COMPLEX_DETAIL_FIELDS
        if self.property_type != '아파트':
            fields = fields | APT_ONLY_DETAIL_FIELDS
        return fields


def item_url(service_type: str | None, item_id: int) -> str:
    path = WEB_PATH_BY_SERVICE_TYPE.get(service_type or '', 'oneroom')
    return f'https://www.zigbang.com/home/{path}/items/{item_id}'


# 학교군 안 중·고등학교는 10곳 넘게 오기도 해 가까운 곳만 (당근과 같은 수)
NEAREST_SCHOOLS: int = 2


# 응답 형식이 달라 값을 모를 때 안내 끝 문장. 매일 API 감시가 이 안의 UPDATE_MAYBE_NEEDED 로 고장을 잡는다
UNEXPECTED_FORMAT_TEXT: str = f'직방 응답이 예상한 형식과 달라 {UPDATE_MAYBE_NEEDED}'
# 본 조회 목록을 주지 않아 UPSTREAM_ERROR 로 멈출 때의 hint
UPSTREAM_RETRY_HINT: str = f'잠시 뒤 다시 시도하세요. 계속되면 직방 API 가 바뀐 것일 수 있어 {UPDATE_MAYBE_NEEDED}'


def text_or_none(value: str | None) -> str | None:
    """앞뒤 공백을 떼고, 빈 글자는 모름(None). 아파트 상세는 값이 없는 칸을 빈 글자로 준다 (`oldAddress` 등).

    방향 기준(`directionBase`)은 '기준' 을 떼야 해 `apt_item_to_listing` 이 같은 규칙을 따로 적용한다.
    """
    return (value.strip() or None) if value else None


def school_label(name: str | None, *details: str | None) -> str | None:
    if not name:
        return None
    shown = [detail for detail in details if detail]
    return f"{name} ({', '.join(shown)})" if shown else name


def sent_or_none(model: BaseModel, field: str, values: list[str]) -> list[str] | None:
    """응답에 `field` 키가 왔으면 `values`, 키가 빠졌으면 모름(None).

    응답 모델은 빠진 목록을 [] 로 채워서 그대로 내보내면 모름이 '없음' 이 된다 (값이 없을 때: 모름 → null, 비어 있음 → []).
    2026-10-12 실측: 새 주거 상세 18건(원룸·빌라·오피스텔·아파트) 모두 options·subways·manageCost.includes 키가 왔다.
    """
    return values if field in model.model_fields_set else None


@contextmanager
def unavailable_on_404(listing_id: int | str, reason: str | None = None) -> Generator[None, None, None]:
    """상세 요청의 404 를 만료 매물(`ListingUnavailableError`)로 바꾼다. 그 밖의 HTTP 오류는 그대로 낸다.

    Args:
        listing_id: 매물 ID.
        reason: 직방 매물인 것을 알고 부른 상세면 그 사유. 없으면 다른 소스 ID 일 수 있다는 안내가 붙는다.
    """
    try:
        yield
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ListingUnavailableError('zigbang', listing_id, reason=reason) from None
        raise


def drop_unused_scope(data: dict[str, Any]) -> dict[str, Any]:
    """검색 결과에서 쓰지 않은 범위 키(반경이면 boundary, 경계면 radius_km)를 뺀다."""
    for field in ('radius_km', 'boundary'):
        if data.get(field) is None:
            data.pop(field, None)
    return data


ComplexKind = Literal['apt', 'officetel']
# 아파트 단지 ID 와 오피스텔 건물 ID 는 번호 체계가 달라 같은 숫자가 다른 단지일 수 있어 접두어로 구분한다
COMPLEX_ID_PATTERN: re.Pattern[str] = re.compile(r'^(apt|officetel)-(\d+)$')


def apt_complex_id(danji_id: int) -> str:
    return f'apt-{danji_id}'


def officetel_complex_id(building_id: int) -> str:
    return f'officetel-{building_id}'


def apt_danji_url(danji_id: int) -> str:
    return f'https://www.zigbang.com/home/apt/danjis/{danji_id}'


# 세대수 문구 (예: '38세대', '1,161세대'). 관련 단지(complex)와 주변 단지 카드·학교·역 응답(search complexes)이 쓴다
HOUSEHOLD_TEXT_PATTERN: re.Pattern[str] = re.compile(r'([\d,]+)\s*세대')


def household_count(text: str | None) -> int | None:
    """세대수 문구('1,161세대')를 정수로. 읽지 못하면 None."""
    match = HOUSEHOLD_TEXT_PATTERN.fullmatch((text or '').strip())
    return int(match.group(1).replace(',', '')) if match else None


def parse_complex_id(complex_id: str) -> tuple[ComplexKind, int]:
    """`apt-68579` / `officetel-20227` 를 (종류, 번호) 로 나눈다.

    Raises:
        JibsaError: 형식이 맞지 않을 때 (INVALID_ARGUMENT).
    """
    match = COMPLEX_ID_PATTERN.match(complex_id.strip())
    if match is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 단지 ID 형식이 아닙니다: '{complex_id}'",
            hint="jibsa zigbang search locations <단지 이름> 결과의 complexes[].complex_id 나 검색 결과의 complex_id "
                 "(예: 'apt-68579', 'officetel-20227') 를 그대로 주세요",
        )
    kind, number = match.groups()
    return kind, int(number)  # type: ignore[return-value]


def complex_not_found(complex_id: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f"직방에서 단지를 찾을 수 없습니다: '{complex_id}'",
        hint='jibsa zigbang search locations <단지 이름> 으로 단지를 다시 찾아 결과의 complexes[].complex_id 를 그대로 주세요',
        details={'complex_id': complex_id},
    )


# 상태 코드 → 에러 변환은 엔드포인트마다 코드·에러가 달라(상세 404 → 만료 `unavailable_on_404`, 단지 404 → NOT_FOUND,
# 오피스텔 건물 400·404 → NOT_FOUND) 공통 컨텍스트 매니저로 묶지 않는다
def fetch_danji(client: ZigbangClient, complex_id: str, danji_id: int) -> ZigbangDanjisResponseModel:
    try:
        return client.run_request_danjis(ZigbangDanjisRequestParameterModel(danji_id=danji_id))
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise complex_not_found(complex_id) from None
        raise
