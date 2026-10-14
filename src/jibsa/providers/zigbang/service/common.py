"""직방 service 공통: 여러 모듈이 쓰는 결과 모델·URL·안내 문구·상수."""

import re
from collections.abc import Generator
from contextlib import contextmanager

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.geo import MultiPolygon
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    Listing,
    TradeType,
    join_address,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    won_to_manwon,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisRequestParameterModel,
    ZigbangFloorFilter,
    ZigbangItemsListV1RequestPayloadModel,
    ZigbangOptionFilter,
    ZigbangRoomTypeFilter,
    ZigbangSalesType,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangDanjisResponseModel,
    ZigbangItemCatalogModel,
    ZigbangItemSummaryModel,
    ZigbangSearchItemModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


TRADE_TYPES: tuple[TradeType, ...] = ('전세', '월세', '매매', '단기임대')
# jibsa 거래 유형 → 직방 거래 유형 필터 값. 단기임대만 이름이 다르다.
SALES_TYPE_BY_TRADE: dict[str, ZigbangSalesType] = {
    '전세': '전세',
    '월세': '월세',
    '매매': '매매',
    '단기임대': '단기',
}
SHORT_TERM_CONTRACT: str = '단기'
WEB_PATH_BY_SERVICE_TYPE: dict[str, str] = {
    '원룸': 'oneroom',
    '오피스텔': 'officetel',
    '빌라': 'villa',
}
ITEMS_LIST_BATCH_SIZE: int = 15
# 학군은 덤이라 이 실패들은 학군만 모름으로 둔다. 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`: 네트워크·상태 코드,
# 차단 페이지·응답 형식 변경·19자리가 아닌 pnu)에 학군 차례의 요청 제한을 더한다
SCHOOL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, RateLimitedError)
# 매물 목록 명령의 --limit 최대값. CLI 옵션의 max 와 상한 안내(`apt_pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120
ROOM_TYPE_BY_CODE: dict[str, str] = {
    '01': '오픈형원룸',
    '02': '분리형원룸',
    '03': '복층형원룸',
    '04': '투룸',
    '05': '쓰리룸',
    '06': '포룸이상',
}
ROOM_TYPES: tuple[str, ...] = tuple(ROOM_TYPE_BY_CODE.values())
# 방 구조 라벨 → 목록 API 의 방 구조 필터 값. 쓰리룸·포룸이상만 필터 이름이 다르다.
ROOM_TYPE_FILTER_BY_LABEL: dict[str, ZigbangRoomTypeFilter] = {
    '오픈형원룸': '오픈형원룸',
    '분리형원룸': '분리형원룸',
    '복층형원룸': '복층형원룸',
    '투룸': '투룸',
    '쓰리룸': '쓰리룸플러스',
    '포룸이상': '포룸플러스',
}
FLOOR_FILTERS: tuple[ZigbangFloorFilter, ...] = ('지상', '반지하', '옥탑방', '1층')
OPTION_FILTERS: tuple[ZigbangOptionFilter, ...] = (
    '에어컨', '냉장고', '세탁기', '가스레인지', '인덕션', '전자레인지',
    '책상', '책장', '침대', '옷장', '신발장', '싱크대',
)
# 기타 조건 라벨 → 목록 요청 모델의 참/거짓 필드.
CONDITION_FIELD_BY_LABEL: dict[str, str] = {
    '즉시입주': 'immediate_move',
    '남향': 'south_facing',
    '엘리베이터': 'elevator',
    '주차': 'parking',
    'CCTV': 'cctv',
    '반려동물': 'pet',
    '전세대출': 'loan_lease',
    '전기차충전': 'ev_station',
}
CONDITIONS: tuple[str, ...] = tuple(CONDITION_FIELD_BY_LABEL)


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


class ZigbangListing(Listing):
    """직방 원룸·오피스텔·빌라 매물. 오피스텔은 건물 ID 를 붙여 그 건물 매물을 이어서 볼 수 있다."""

    complex_id: Annotated[
        str | None,
        Field(description='오피스텔 건물 ID (예: officetel-20227, 오피스텔만). zigbang complex·items 에 넘긴다')
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


def item_url(service_type: str | None, item_id: int) -> str:
    path = WEB_PATH_BY_SERVICE_TYPE.get(service_type or '', 'oneroom')
    return f'https://www.zigbang.com/home/{path}/items/{item_id}'


def apt_item_url(item_id: int, item_source: str = 'zigbang') -> str:
    # 웹 아파트 매물 페이지(v2). 옛 경로 /home/apt/item/{id} 는 /error 로 보낸다.
    # 마지막 칸은 대표로 띄울 중개사 번호인데 빠지면 404 라, 0 을 넣어 직방이 고르게 한다.
    return f'https://www.zigbang.com/home/apt/item/v2/{item_id}/{item_source}/0'


def region_from_search_item(item: ZigbangSearchItemModel) -> ZigbangRegion:
    return ZigbangRegion(
        name=item.name,
        # 설명은 정식 시·도 이름으로 오지만 세종 학교는 '세종특별자치시  반곡동' 처럼 공백이 두 칸이라 정규화한다 (2026-10-11)
        address=normalize_address(item.description),
        search_type=item.type,
        local1=normalize_address(item.source.local1) if item.source and item.source.local1 else None,
        local2=item.source.local2 if item.source else None,
        local3=item.source.local3 if item.source else None,
        subway_id=item.id if item.type == 'subway' and item.id > 0 else None,
        lat=item.lat,
        lng=item.lng,
        legal_division_code=item.source.legal_division_code if item.source else None,
    )


def trade_type_of(summary: ZigbangItemSummaryModel) -> str:
    """요약 응답의 거래 유형. 직방은 단기임대를 월세로 주고 `contract` 로만 구분한다.

    그대로 옮기면 보증금이 월세 한두 달치(예: 75/75)인 단기임대가 싼 월세로 보인다.
    """
    if summary.sales_type == '월세' and summary.contract == SHORT_TERM_CONTRACT:
        return '단기임대'
    return summary.sales_type


def summary_to_listing(
    summary: ZigbangItemSummaryModel,
    distance_km: float | None = None,
    building_id: int | None = None,
) -> ZigbangListing:
    """요약 응답 한 건을 `ZigbangListing` 으로 바꾼다.

    매매 매물은 요약 응답의 `deposit` 에 매매가가 들어오므로 `price_manwon` 으로
    옮긴다. 관리비는 원 단위 문자열이라 만원으로 환산한다. 면적은 `size_m2`
    (공급면적) 대신 `전용면적` 을 쓴다. 단기임대는 `trade_type_of` 로 구분한다.
    요약에는 오피스텔 건물 ID 가 없어 지도 핀의 `buildingId` 를 `building_id` 로 받는다.
    """
    is_sale = summary.sales_type == '매매'
    # `size_m2` 는 공급면적이라(오피스텔은 전용의 2배 넘게 나오기도 한다) 전용면적을 우선한다.
    # 원룸·빌라는 둘이 같아 전용면적이 빠졌을 때 대신 쓰지만, 오피스텔은 전용으로 잘못 읽히므로 모름(None)으로 둔다.
    area_m2 = summary.exclusive_area.m2 if summary.exclusive_area else None
    if area_m2 is None and summary.service_type != '오피스텔':
        area_m2 = summary.size_m2

    return ZigbangListing(
        source='zigbang',
        id=str(summary.item_id),
        url=item_url(summary.service_type, summary.item_id),
        trade_type=trade_type_of(summary),
        property_type=summary.service_type,
        room_type=ROOM_TYPE_BY_CODE.get(summary.room_type or ''),
        title=summary.title,
        price_manwon=summary.deposit if is_sale else None,
        deposit_manwon=None if is_sale else summary.deposit,
        rent_manwon=summary.rent if summary.sales_type == '월세' else None,
        manage_cost_manwon=won_to_manwon(summary.manage_cost),
        area_m2=area_m2,
        area_pyeong=m2_to_pyeong(area_m2),
        floor=summary.floor,
        building_floor=summary.building_floor,
        address=join_address(
            summary.address1,
            summary.address_origin.address2 if summary.address_origin else None,
        ),
        lat=summary.location.lat if summary.location else None,
        lng=summary.location.lng if summary.location else None,
        distance_km=None if distance_km is None else round(distance_km, 2),
        registered_at=normalize_date(summary.reg_date),
        complex_id=officetel_complex_id(building_id) if building_id else None,
    )


# 학교군 안 중·고등학교는 10곳 넘게 오기도 해 가까운 곳만 (당근과 같은 수)
NEAREST_SCHOOLS: int = 2


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
def unavailable_on_404(listing_id: int | str) -> Generator[None, None, None]:
    """상세 요청의 404 를 만료 매물(`ListingUnavailableError`)로 바꾼다. 그 밖의 HTTP 오류는 그대로 낸다."""
    try:
        yield
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ListingUnavailableError('zigbang', listing_id) from None
        raise


def drop_unused_scope(data: dict[str, Any]) -> dict[str, Any]:
    """검색 결과에서 쓰지 않은 범위 키(반경이면 boundary, 경계면 radius_km)를 뺀다."""
    for field in ('radius_km', 'boundary'):
        if data.get(field) is None:
            data.pop(field, None)
    return data


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
    without_random: Annotated[
        bool,
        Field(description='오피스텔 서버의 무작위 섞기 해제')
    ] = False


def room_filter_of(conditions: ZigbangRoomConditions) -> dict[str, object]:
    """관리비·면적·층·욕실·옵션·시설 조건을 원룸·빌라·오피스텔 요청 필드로 바꾼다 (지도 목록과 오피스텔 건물 공통)."""
    return {
        'manage_cost_min': conditions.manage_cost_min,
        'manage_cost_max': conditions.manage_cost_max,
        'no_manage_cost': conditions.no_manage_cost or None,
        'size_min_m2': conditions.area_min_m2,
        'size_max_m2': conditions.area_max_m2,
        'size_min_pyeong': conditions.area_min_pyeong,
        'size_max_pyeong': conditions.area_max_pyeong,
        'floors': conditions.floors,
        'bathroom_count': conditions.bathroom_count,
        'options': conditions.options,
        **{CONDITION_FIELD_BY_LABEL[condition]: True for condition in conditions.extra_conditions},
    }


def tradeable_summaries(client: ZigbangClient, ids: list[int]) -> list[ZigbangItemSummaryModel]:
    """`ids` 의 요약을 15개씩 받아 거래 중인 전세·월세·매매(단기임대 포함)만 준다. 뺀 매물은 다시 채우지 않는다.

    받은 뒤에는 거래 불가와 지원하지 않는 거래 종류만 뺀다. 유형·거래 유형·방 구조는 서버가 걸었으므로 다시 거르지
    않는다 (2026-10-10 실측: 원룸·빌라·오피스텔 월세·전세·단기임대와 방 구조 조건 200건, 오피스텔 건물 3곳 34건 모두 조건 안).
    """
    summaries: list[ZigbangItemSummaryModel] = []
    for start in range(0, len(ids), ITEMS_LIST_BATCH_SIZE):
        batch = ids[start:start + ITEMS_LIST_BATCH_SIZE]
        requested = set(batch)
        response = client.run_request_items_list_v1(ZigbangItemsListV1RequestPayloadModel(item_ids=batch))
        for summary in response.items:
            # 방어용. 실측으로는 요청한 매물만 오지만(2026-10-10 오피스텔 건물 8곳 108건), 끼어 온 매물은 뺀다
            if summary.item_id not in requested:
                continue
            # 내려간 매물. 상태를 알려 주지 않으면(필드가 빠지면) 만료 매물이 섞일 수 있어 함께 뺀다
            if summary.status is not True or summary.sales_type not in ('전세', '월세', '매매'):
                continue
            summaries.append(summary)
    return summaries


APT_TRAN_TYPE_BY_TRADE: dict[TradeType, str] = {
    '매매': 'trade',
    '전세': 'charter',
    '월세': 'rental',
}
TRADE_BY_APT_TRAN_TYPE: dict[str, TradeType] = {
    tran_type: trade for trade, tran_type in APT_TRAN_TYPE_BY_TRADE.items()
}
DANJI_CATALOG_PAGE_SIZE: int = 50
# 상세를 볼 수 있는 아파트 매물 출처 (앞이 우선). coalition 은 호갱노노 집주인 매물이다
APT_ITEM_SOURCES: tuple[str, ...] = ('zigbang', 'coalition')


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
    is_price_range: Annotated[
        bool | None,
        Field(description='같은 호를 올린 매물끼리 가격이 달라 가격이 최솟값이면 true')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='같은 호를 올린 매물(중개사) 수')
    ] = None


def in_range(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    """범위 조건에 맞는지. 조건이 있는데 값을 모르면 맞지 않는다고 본다 (서버가 받지 않아 받은 뒤 거르는 조건에 쓴다)."""
    if minimum is None and maximum is None:
        return True
    return value is not None and (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def catalog_to_listing(catalog: ZigbangItemCatalogModel, local1: str | None) -> ZigbangAptListing | None:
    """카탈로그 한 건을 `ZigbangAptListing` 으로 바꾼다. 상세를 볼 수 있는 매물 ID 가 없으면 None.

    `depositMin` 은 매매면 매매가, 전세·월세면 보증금이다. 묶인 매물 중 직방 매물을 먼저 쓰고, 없으면 제휴
    (호갱노노 집주인) 매물을 `coalition-123` ID 로 쓴다. 둘 다 `zigbang item` 으로 상세를 볼 수 있고
    `url` 은 그 매물의 웹 페이지다. 그 밖의 출처는 상세를 볼 수 없어 뺀다.
    """
    entry = next(
        (entry for source in APT_ITEM_SOURCES for entry in catalog.item_id_list if entry.item_source == source),
        None,
    )
    trade_type = TRADE_BY_APT_TRAN_TYPE.get(catalog.tran_type)
    if entry is None or trade_type is None:
        return None
    is_sale = trade_type == '매매'
    return ZigbangAptListing(
        source='zigbang',
        id=str(entry.item_id) if entry.item_source == 'zigbang' else f'coalition-{entry.item_id}',
        url=apt_item_url(entry.item_id, entry.item_source or 'zigbang'),
        trade_type=trade_type,
        property_type='아파트',
        title=catalog.item_title or join_address(catalog.area_danji_name, catalog.dong),
        price_manwon=catalog.deposit_min if is_sale else None,
        deposit_manwon=None if is_sale else catalog.deposit_min,
        rent_manwon=catalog.rent_min if trade_type == '월세' else None,
        area_m2=catalog.size_m2,
        area_pyeong=m2_to_pyeong(catalog.size_m2),
        floor=catalog.floor,
        address=join_address(local1, catalog.local2, catalog.local3),
        complex_id=apt_complex_id(catalog.area_danji_id) if catalog.area_danji_id else None,
        complex_name=join_address(catalog.area_danji_name, catalog.dong),
        supply_area_m2=catalog.size_contract_m2,
        is_price_range=catalog.is_price_range,
        listing_count=catalog.item_count,
    )


ComplexKind = Literal['apt', 'officetel']
# 아파트 단지 ID 와 오피스텔 건물 ID 는 번호 체계가 달라 같은 숫자가 다른 단지일 수 있어 접두어로 구분한다
COMPLEX_ID_PATTERN: re.Pattern[str] = re.compile(r'^(apt|officetel)-(\d+)$')


def apt_complex_id(danji_id: int) -> str:
    return f'apt-{danji_id}'


def officetel_complex_id(building_id: int) -> str:
    return f'officetel-{building_id}'


def apt_danji_url(danji_id: int) -> str:
    return f'https://www.zigbang.com/home/apt/danjis/{danji_id}'


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


def excluded_notes(limit: int, inspected: int, returned: int) -> list[str]:
    """요약을 받은 뒤 뺀 매물이 있어 `limit` 보다 적게 돌려줄 때의 안내. 뺀 만큼 다시 조회하지 않는다."""
    if returned >= limit or inspected <= returned:
        return []
    return [
        f'가까운 매물 {inspected}건을 확인했지만 거래 불가이거나 지원하지 않는 거래 종류인 매물을 제외해 '
        f'{returned}건을 반환했습니다. 제외된 수만큼 추가 조회하지 않았습니다'
    ]


def apt_pagination_notes(
    total: int,
    returned: int,
    limit: int,
    inspected: int,
    *,
    has_more: bool = False,
    suggest_limit: bool = True,
) -> list[str]:
    """실제로 받은 원본 매물 수를 조회 예산으로 세고 추가 조회 없이 안내한다.

    `suggest_limit` 이 False 면 --limit 을 늘리라는 안내를 뺀다. 늘려도 못 찾는 경우(반경 면적 검색의 단지 상한)에 쓴다.
    당근 `listing_budget_notes`·네이버의 같은 역할 함수와 문구는 비슷하지만 공통 헬퍼로 합치지 않는다. 제외 수를 세는
    방식(직방 받은 수 − 반환 수, 네이버 min(받은 수, limit) − 반환 수, 당근 eligible)과 더 받을 매물 판단(당근 has_more,
    네이버 truncated)이 소스마다 달라 합치면 그 옵션을 모두 받는 함수가 된다.
    """
    notes: list[str] = []
    if returned < limit:
        if inspected > returned:
            notes.append(
                f'최대 {limit}건을 요청했지만, 중복·거래 불가 또는 검색 조건에 맞지 않는 매물을 제외해 '
                f'{returned}건을 반환했습니다. 제외된 수만큼 추가 조회하지 않았습니다'
            )
        else:
            notes.append(f'최대 {limit}건을 요청했지만 조회한 결과는 {returned}건입니다. 요청한 조회 범위에서 검색을 마쳤습니다')
    if limit >= MAX_LIST_LIMIT and (inspected >= limit or total > returned or has_more):
        notes.append(f'--limit의 최대값은 {MAX_LIST_LIMIT}입니다. 더 구체적인 결과를 보려면 거래 유형·가격·지역 등 지원되는 필터로 검색 범위를 좁혀 주세요')
    elif suggest_limit and inspected >= limit and (total > returned or has_more):
        notes.append(f'조회 예산 {limit}건 중 {returned}건을 반환했습니다. --limit을 늘리거나 지원되는 필터로 검색 범위를 좁혀 주세요')
    return notes
