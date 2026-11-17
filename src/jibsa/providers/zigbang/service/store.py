"""상가·사무실 매물 검색과 상세 (search listings store, listing store-*)."""

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
    ListingUnavailableError,
)
from jibsa.core.geo import haversine_km
from jibsa.core.korean import (
    is_ri_code,
    quoted,
)
from jibsa.core.listing import (
    Listing,
    ListingDetail,
    TradeType,
    in_range,
    join_address,
    limit_notes,
    m2_to_pyeong,
    more_hint,
    note,
    parking_label,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.store import (
    ZigbangStoreArticleStoresListV2RequestPayloadModel,
    ZigbangStoreArticleStoresV2RequestPayloadModel,
    ZigbangStoreArticleStoreV2RequestParameterModel,
    ZigbangStoreBusinessModel,
    ZigbangStoreCircleModel,
    ZigbangStoreSalesType,
)
from jibsa.providers.zigbang.api.response.store import (
    ZigbangStoreArticleStoreV2ResponseModel,
    ZigbangStoreSummaryModel,
)
from jibsa.providers.zigbang.service.common import (
    MAX_LIST_LIMIT,
    ZigbangRegion,
    drop_unused_scope,
    sent_or_none,
    unavailable_on_404,
)

from typing import (
    Annotated,
    Any,
)


SCAN_FACTOR: int = 5
MIN_SCAN_PINS: int = 60


STORE_TRADE_TYPES: tuple[ZigbangStoreSalesType, ...] = ('임대', '매매')
# 결과가 limit 보다 많을 때 좁히라고 권할 조건. 상가에는 매물 유형 옵션이 없다
STORE_NARROW: str = '거래 유형·업종·가격 조건'
# 그중 서버가 거르는 조건. 가격 조건은 받은 뒤 거르므로 후보 조회 상한에 걸렸을 때는 이것만 권한다
STORE_SERVER_NARROW: str = '거래 유형·업종'
# 웹 상가 업종 필터의 대분류와 업종. 대분류 이름을 주면 그 안의 업종 전체다 (웹의 '전체').
STORE_BUSINESSES_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    '휴게음식점': ('베이커리', '카페/커피', '패스트푸드/피자', '분식', '치킨/닭요리'),
    '일반음식/주류점': ('한식/고기집', '일식/해산물', '중식', '퓨전/쌀국수', '양식/레스토랑', '기타주점'),
    '스포츠/마사지/오락': ('골프/헬스', '요가/마사지', '노래방/PC방/당구장'),
    '판매업': (
        '화장품', '가구/가전', '주방/인테리어', '건강/미용식품', '애견/애완/동물', '액세서리',
        '의류/멀티샵', '편의점/슈퍼', '정육/수산/반찬', '약국', '문구/펜시', '기타소매',
    ),
    '기타': ('숙박/펜션', '학원/학업관련', '미용/네일/피부관리', '병원', '부동산중개소', '기타'),
}
# 업종 '기타' 는 대분류 '기타' 와 이름이 같아 대분류로 읽는다 (그 안의 업종 전체).
STORE_BUSINESS_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys([*STORE_BUSINESSES_BY_CATEGORY, *(b for bs in STORE_BUSINESSES_BY_CATEGORY.values() for b in bs)])
)
STORE_LIST_BATCH_SIZE: int = 50
STORE_VACANT_SECTION: str = '이 지역 비어있는 상가'
STORE_FLOOR_PATTERN: re.Pattern[str] = re.compile(r'^(지하)?\s*(\d+)\s*층$')
# 상가 주차 문구 앞의 가능 여부 ('가능 - 자주식 6대')
STORE_PARKING_AVAILABLE: dict[str, bool] = {'가능': True, '불가': False, '불가능': False}


# 상가 응답에 방·욕실·방향·입주·옵션 정보가 아예 없어(2026-10-10 실측: 상세 원본 키 35개, 상세 12건·목록 10건 모두 비어 있음)
# 모름이 아니라 해당 없음으로 키를 뺀다
STORE_NOT_APPLICABLE_FIELDS: frozenset[str] = frozenset({'room_type'})
STORE_NOT_APPLICABLE_DETAIL_FIELDS: frozenset[str] = STORE_NOT_APPLICABLE_FIELDS | frozenset({
    'room_count', 'bathroom_count', 'direction', 'move_in', 'options', 'manage_cost_includes',
})
# 업종 '사무실' 에는 권리금이 없다. 웹 상세는 이 업종이면 권리금 줄을 숨기고, 직방도 값을 주지 않는다 (2026-11-17 번들
# `renderItemInfoData`, 상가 340건 중 권리금이 없는 199건이 모두 사무실). 그래서 직방이 값을 주지 않은 사무실은 모름이
# 아니라 해당 없음으로 `key_money_manwon` 키를 뺀다. 값을 줬으면(0 포함) 그대로 낸다. 권리금 조건을 걸면 이런 사무실은
# 빼고(해당 없음을 0 으로 치지 않는다) `search_store_listings` 가 [제외] 로 알린다
STORE_OFFICE_BUSINESS: str = '사무실'


def _store_not_applicable_key_money(business: str | None, key_money_manwon: float | None) -> frozenset[str]:
    """업종이 사무실이고 직방이 권리금을 주지 않았으면 키를 뺄 권리금 필드."""
    if business == STORE_OFFICE_BUSINESS and key_money_manwon is None:
        return frozenset({'key_money_manwon'})
    return frozenset()


class ZigbangStoreListing(Listing):
    """직방 상가·사무실 매물."""

    business: Annotated[
        str | None,
        Field(description='업종 (현재·직전 업종, 공실이면 기타)')
    ] = None
    key_money_manwon: Annotated[
        float | None,
        Field(description='권리금 (만원). 0 이면 무권리. 업종이 사무실이고 직방이 주지 않으면 키가 없다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        return (
            super().not_applicable_fields()
            | STORE_NOT_APPLICABLE_FIELDS
            | _store_not_applicable_key_money(self.business, self.key_money_manwon)
        )


class ZigbangStoreListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 상가·사무실 매물."""

    business: Annotated[
        str | None,
        Field(description='업종 (현재·직전 업종, 공실이면 기타)')
    ] = None
    key_money_manwon: Annotated[
        float | None,
        Field(description='권리금 (만원). 0 이면 무권리. 업종이 사무실이고 직방이 주지 않으면 키가 없다')
    ] = None
    recommended_business: Annotated[
        str | None,
        Field(description='추천 업종')
    ] = None
    vacancy: Annotated[
        str | None,
        Field(description="구분 (예: '공실')")
    ] = None
    lease_unit: Annotated[
        str | None,
        Field(description='임대 구분 (예: 개별호, 통임대)')
    ] = None
    interior: Annotated[
        str | None,
        Field(description='인테리어 유무')
    ] = None
    toilet: Annotated[
        str | None,
        Field(description='화장실')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 종류')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        return (
            super().not_applicable_fields()
            | STORE_NOT_APPLICABLE_DETAIL_FIELDS
            | _store_not_applicable_key_money(self.business, self.key_money_manwon)
        )


class ZigbangStoreSearchResult(BaseModel):
    """상가·사무실 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float | None,
        Field(description='검색 반경 (km). 동 안을 찾았으면 키가 없다')
    ] = None
    boundary: Annotated[
        str | None,
        Field(description="반경 대신 법정동 코드로 그 안을 찾은 동 이름 (여럿이면 '·' 로 잇는다). 반경으로 찾았으면 키가 없다")
    ] = None
    total: Annotated[
        int,
        Field(description='반경(또는 동) 안 직방 목록의 매물 수. 가격 필터 적용 전')
    ]
    inspected_in_radius: Annotated[
        int | None,
        Field(description='반경(또는 동) 안 직방 목록 앞에서부터 요약을 요청한 매물 수. 가격 조건이 있을 때만 출력')
    ] = None
    price_matched_in_radius: Annotated[
        int | None,
        Field(description='확인한 후보 중 거래 가능하고 가격 조건에 맞는 수. 전체 매물 수가 아니다')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위(반경·동) 안에 더 있는지: 요약을 받지 않은 매물이 남았거나 --limit 에 맞춰 잘랐다 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        list[ZigbangStoreListing],
        Field(description='직방 목록 순서 그대로의 매물 (거리순이 아니다)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다·공실이 따로 있다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = drop_unused_scope(handler(self))
        for key in ('inspected_in_radius', 'price_matched_in_radius'):
            if data.get(key) is None:
                data.pop(key, None)
        return data


def store_url(item_id: int) -> str:
    return f'https://www.zigbang.com/home/store/items/{item_id}'


def store_floor(floor: str | None) -> str | None:
    """상가 층 표기('4층', '지하1층')를 매물 공통 표기('4', '지하1')로 맞춘다."""
    if floor is None:
        return None
    match = STORE_FLOOR_PATTERN.match(floor.strip())
    if match is None:
        return floor
    basement, number = match.groups()
    return f'지하{number}' if basement else number


def store_parking(text: str | None) -> str | None:
    """상가 주차 문구('가능 - 자주식 6대')를 매물 공통 꼴('가능 (자주식 6대)')로 맞춘다. 다른 문구는 그대로 둔다."""
    if not text:
        return None
    status, _, detail = text.partition(' - ')
    available = STORE_PARKING_AVAILABLE.get(status.strip())
    return text if available is None else parking_label(available, detail.strip() or None)


def store_trade(summary: ZigbangStoreSummaryModel) -> TradeType:
    """상가 거래 유형. 매매가 아니면 임대이고, 월세가 있으면 월세, 없으면 전세다.

    임대 상가는 월세금액이 늘 있어 월세가 비어 전세로 잘못 읽히는 일은 없다 (2026-10-10 실측: 7개 역 1,709건 중
    임대 1,649건 모두 월세 > 0, 전세 상가 0건, 매매는 월세 0).
    """
    if summary.sales_type == '매매':
        return '매매'
    return '월세' if summary.rent else '전세'


def store_businesses(names: list[str]) -> list[ZigbangStoreBusinessModel]:
    """업종·대분류 이름을 웹과 같은 대분류별 업종 조건으로 묶는다. 대분류 이름은 그 안의 업종 전체.

    CLI 는 `split_csv` 로 먼저 막는다.

    Raises:
        JibsaError: 직방 상가 업종·대분류가 아닌 이름이 있을 때 (INVALID_ARGUMENT).
    """
    chosen: dict[str, list[str]] = {}
    for name in names:
        if name in STORE_BUSINESSES_BY_CATEGORY:
            chosen.setdefault(name, []).extend(STORE_BUSINESSES_BY_CATEGORY[name])
            continue
        category = next(
            (category for category, businesses in STORE_BUSINESSES_BY_CATEGORY.items() if name in businesses),
            None,
        )
        if category is None:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"직방 상가 업종이 아닙니다: '{name}'",
                hint='jibsa zigbang search listings store --help 에서 --business 값을 확인하세요',
            )
        chosen.setdefault(category, []).append(name)
    return [
        ZigbangStoreBusinessModel(category=category, businesses=list(dict.fromkeys(businesses)))
        for category, businesses in chosen.items()
    ]


def store_summary_to_listing(
    summary: ZigbangStoreSummaryModel,
    distance_km: float | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> ZigbangStoreListing:
    trade_type = store_trade(summary)
    return ZigbangStoreListing(
        source='zigbang',
        id=f'store-{summary.item_id}',
        url=store_url(summary.item_id),
        trade_type=trade_type,
        property_type='상가',
        title=summary.title,
        price_manwon=summary.sales_price if trade_type == '매매' else None,
        deposit_manwon=None if trade_type == '매매' else summary.deposit,
        rent_manwon=summary.rent if trade_type == '월세' else None,
        manage_cost_manwon=summary.manage_cost,
        area_m2=summary.size_m2,
        area_pyeong=m2_to_pyeong(summary.size_m2),
        floor=store_floor(summary.floor),
        address=join_address(summary.local1, summary.local2, summary.local3),
        lat=lat,
        lng=lng,
        distance_km=None if distance_km is None else round(distance_km, 2),
        business=summary.business,
        key_money_manwon=summary.key_money,
    )


def store_price_trade(
    trade: ZigbangStoreSalesType,
    bounds: dict[str, tuple[int | None, int | None]],
) -> ZigbangStoreSalesType:
    """상가 가격 범위를 검증하고 가격 조건에 맞는 임대·매매 유형을 정한다.

    CLI 는 지역을 찾기 전에 이 함수로 막고 좁힌 거래 유형을 안내하며, `search_store_listings` 도 다시 부른다.

    Raises:
        JibsaError: 범위가 음수·거꾸로이거나, 임대·매매 가격 조건을 섞었거나 `trade` 와 맞지 않을 때 (INVALID_ARGUMENT).
    """
    def invalid(message: str) -> JibsaError:
        return JibsaError(
            code='INVALID_ARGUMENT', message=message,
            hint='jibsa zigbang search listings store --help 에서 가격·거래 유형 조건을 확인하세요',
        )

    for field, (minimum, maximum) in bounds.items():
        option = field.removesuffix('_manwon').replace('_', '-')
        if any(value is not None and value < 0 for value in (minimum, maximum)):
            raise invalid(f'--{option}-min/max 는 0 이상이어야 합니다')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise invalid(f'--{option}-max 는 --{option}-min 이상이어야 합니다')
    rental = any(
        any(value is not None for value in bounds[field])
        for field in ('deposit_manwon', 'rent_manwon', 'key_money_manwon')
    )
    sale = any(value is not None for value in bounds['price_manwon'])
    if rental and sale:
        raise invalid('보증금·월세·권리금 조건과 매매가 조건은 함께 쓸 수 없습니다')
    if (rental and trade == '매매') or (sale and trade == '임대'):
        raise invalid('--trade 와 가격 조건이 맞지 않습니다. 보증금·월세·권리금은 임대, 매매가는 매매에만 쓰세요')
    return '임대' if rental else '매매' if sale else trade


def _store_price_matches(
    listing: ZigbangStoreListing,
    bounds: dict[str, tuple[int | None, int | None]],
) -> bool:
    for field, (minimum, maximum) in bounds.items():
        if minimum is None and maximum is None:
            continue
        if field in ('deposit_manwon', 'key_money_manwon') and listing.trade_type == '매매':
            return False
        if field == 'rent_manwon' and listing.trade_type != '월세':
            return False
        if not in_range(getattr(listing, field), minimum, maximum):
            return False
    return True


class ZigbangStoreConditions(RequestModel):
    """상가·사무실 매물 조건 (search listings store). 금액은 만원, 면적은 ㎡.

    거래 유형·1층·업종·면적은 서버에서 거르고, 가격은 요약을 받은 뒤 거른다 (`search_store_listings`).
    """

    trade: Annotated[
        ZigbangStoreSalesType,
        Field(description='거래 유형 (임대·매매·전체)')
    ] = '전체'
    first_floor: Annotated[
        bool,
        Field(description='1층만')
    ] = False
    businesses: Annotated[
        list[str],
        Field(description='업종·업종 대분류 (STORE_BUSINESS_NAMES)')
    ] = []
    area_min_m2: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='면적 상한 (㎡, 미만)')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금 상한 (만원)')
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
    manage_cost_min: Annotated[
        int | None,
        Field(description='월 관리비 하한 (만원)')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(description='월 관리비 상한 (만원)')
    ] = None
    key_money_min: Annotated[
        int | None,
        Field(description='권리금 하한 (만원)')
    ] = None
    key_money_max: Annotated[
        int | None,
        Field(description='권리금 상한 (만원)')
    ] = None


def store_region_codes(dongs: list[ZigbangRegion]) -> tuple[list[str], list[str]]:
    """동 이름으로 찾을 때 `지역` 에 보낼 법정동 코드(10자리)와 안내.

    직방은 모르는 코드에 에러 없이 전국 매물을 준다 (2026-11-15 실측: 리 코드 4183025021 → 57,782건). 그래서 리는 그 위
    읍·면 코드(앞 8자리 + '00')로 바꿔 읍·면 전체를 찾고 알리며, 코드가 없는 동은 전국 목록을 내지 않게 막는다.

    Raises:
        JibsaError: 법정동 코드(10자리)가 없는 동이 있을 때 (REGION_NOT_SUPPORTED).
    """
    codes: list[str] = []
    notes: list[str] = []
    for dong in dongs:
        code = dong.legal_division_code or ''
        if len(code) != 10 or not (code.isascii() and code.isdigit()):
            raise JibsaError(
                code='REGION_NOT_SUPPORTED',
                message=f"직방 지역 검색 결과에 '{dong.name}' 의 법정동 코드(10자리)가 없어 그 동 안을 찾을 수 없습니다",
                hint=f"--radius 를 주면 '{dong.name}' 중심에서 반경으로 찾습니다 (예: --radius 1)",
            )
        if is_ri_code(code):
            code = f'{code[:8]}00'
            notes.append(note(
                '범위',
                f"{quoted(dong.name, '은/는')} 리라 그 리가 속한 읍·면 전체를 찾았습니다. 직방 상가는 리 단위로 찾지 못합니다 "
                '(반경으로 찾으려면 --radius)',
            ))
        codes.append(code)
    return list(dict.fromkeys(codes)), notes


def search_store_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangStoreConditions | None = None,
    radius_km: float = 1.0,
    limit: int = 20,
    dongs: list[ZigbangRegion] | None = None,
) -> ZigbangStoreSearchResult:
    """중심점 반경(또는 `dongs` 동) 안의 상가·사무실을 직방 목록 순서 그대로 `limit` 건 조회한다.

    웹 상가 검색처럼 범위 안 위치 목록을 한 번에 받고 그 순서대로 앞에서부터 요약을 받는다 (2026-11-15 번들
    `HomeStoreListScreenModel.loadItems`: 응답 순서대로 15건씩, 정렬 없음). 순서는 거리순이 아니고, `distance_km` 는
    검색 중심에서 잰 거리다. 반경은 원(`상권`)으로 보내고, `dongs` 가 있으면 반경 대신 그 동들의 법정동 코드(`지역`)로
    찾는다 (`store_region_codes`). 서버가 범위 안 매물만 준다.

    거래 유형(임대·매매), 1층, 업종, 면적(㎡, 상한은 미만)은 서버에서 거른다.
    가격 조건은 요약을 받은 뒤 거른다 (상·하한 포함, 모르는 금액은 제외). 권리금 조건을 걸면 권리금이 해당 없는
    사무실(`key_money_manwon` 키 없음)도 빠지므로, 권리금만 아니면 다른 가격 조건에 맞던 수를 `notes` 로 알린다.
    직방 목록 앞의 후보를 조회
    상한(max(limit * SCAN_FACTOR, MIN_SCAN_PINS))까지 확인하며, 전체 후보를 확인하지 못하면 안내한다.
    업종 조건을 걸면 직방이 그 업종과 무관한 범위 안 공실을 따로 주는데, 업종 조건을
    지키도록 공실은 빼고 몇 건인지 `notes` 로 알린다.

    Raises:
        JibsaError: `dongs` 에 법정동 코드가 없는 동이 있을 때 (`store_region_codes`).
    """
    conditions = conditions or ZigbangStoreConditions()
    bounds = {
        'deposit_manwon': (conditions.deposit_min, conditions.deposit_max),
        'rent_manwon': (conditions.rent_min, conditions.rent_max),
        'price_manwon': (conditions.price_min, conditions.price_max),
        'manage_cost_manwon': (conditions.manage_cost_min, conditions.manage_cost_max),
        'key_money_manwon': (conditions.key_money_min, conditions.key_money_max),
    }
    trade = store_price_trade(conditions.trade, bounds)
    filter_price = any(value is not None for pair in bounds.values() for value in pair)
    business_conditions = store_businesses(conditions.businesses or [])
    circles: list[ZigbangStoreCircleModel] | None = None
    region_codes: list[str] | None = None
    scope_notes: list[str] = []
    if dongs:
        region_codes, scope_notes = store_region_codes(dongs)
    else:
        circles = [ZigbangStoreCircleModel(lat=region.lat, lng=region.lng, radius=round(radius_km * 1000))]
    response = client.run_request_store_article_stores_v2(
        ZigbangStoreArticleStoresV2RequestPayloadModel(
            circles=circles,
            region_codes=region_codes,
            sales_type=trade,
            first_floor=conditions.first_floor,
            businesses=business_conditions,
            area_min_m2=conditions.area_min_m2,
            area_max_m2=conditions.area_max_m2,
        )
    )
    # 직방 목록 순서대로 매물 ID → 좌표
    pins: dict[int, tuple[float, float]] = {}
    vacant: set[int] = set()
    for section in response.sections:
        # 공실 묶음은 업종 조건을 걸 때만 찬다. 업종 조건이 없으면 비어 와서 안내 없이 빼는 매물이 없다 (2026-10-18 실측:
        # 성수역 0.3km 업종 조건 없이 일반 묶음 393건, 공실 묶음 0건). 2026-10-18 리뷰 오탐 확인. 공실 묶음도 범위 안
        # 매물만 온다 (2026-11-15 실측: 역삼역 1000m 카페/커피 공실 970건)
        if section.title == STORE_VACANT_SECTION:
            vacant.update(location.item_id for location in section.item_locations)
            continue
        for location in section.item_locations:
            pins.setdefault(location.item_id, (location.lat, location.lng))

    scan_cap = max(limit * SCAN_FACTOR, MIN_SCAN_PINS)
    candidates = list(pins)[:scan_cap]
    listings: list[ZigbangStoreListing] = []
    inspected = 0
    matched = 0
    # 권리금 조건 때문에만 빠진 권리금 해당 없음 사무실 수
    key_money_bounds = bounds['key_money_manwon']
    other_bounds = {field: pair for field, pair in bounds.items() if field != 'key_money_manwon'}
    office_no_key_money = 0
    for start in range(0, len(candidates), STORE_LIST_BATCH_SIZE):
        if len(listings) >= limit:
            break
        batch = candidates[start:start + STORE_LIST_BATCH_SIZE]
        inspected += len(batch)
        summaries = client.run_request_store_article_stores_list_v2(
            ZigbangStoreArticleStoresListV2RequestPayloadModel(item_ids=batch)
        )
        # 요약 응답의 순서에 기대지 않고 보낸 순서(직방 목록 순서)대로 놓는다
        summary_by_id = {summary.item_id: summary for summary in summaries.items}
        for item_id in batch:
            summary = summary_by_id.get(item_id)
            if summary is None or summary.status != 'open':
                continue
            lat, lng = pins[item_id]
            listing = store_summary_to_listing(summary, haversine_km(region.lat, region.lng, lat, lng), lat, lng)
            # 거래 유형은 서버가 걸었으므로 다시 거르지 않는다 (2026-10-10 실측: 역삼역·성수동 임대·매매 662건 모두 조건 안)
            if not _store_price_matches(listing, bounds):
                if (
                    any(value is not None for value in key_money_bounds)
                    and listing.business == STORE_OFFICE_BUSINESS
                    and listing.key_money_manwon is None
                    and _store_price_matches(listing, other_bounds)
                ):
                    office_no_key_money += 1
                continue
            matched += 1
            listings.append(listing)

    # --limit 에 맞춰 잘라 낸 매물. 후보 요약을 다 받았어도 잘린 매물이 있으면 더 있다 (2026-10-21 실측: 성수역 반경
    # 0.2km 범위 안 35건을 한 묶음에 다 받고 3건만 주며 has_more false 였다)
    cut = listings[limit:]
    listings = listings[:limit]
    total = len(pins)
    has_more = inspected < total or bool(cut)
    area = '지역' if dongs else '반경'
    if filter_price:
        notes = [
            f'가격 조건은 요약을 받은 뒤 거릅니다. total({total}건)은 가격 적용 전 직방 목록의 매물 수이고, '
            f'그중 앞의 {inspected}건의 요약을 요청해 거래 가능하고 가격 조건에 맞는 {matched}건을 확인했습니다'
        ]
        # 가격 조건이 있으면 limit_notes 의 [일부] 를 쓰지 않으므로, 더 있다는 안내와 다음 할 일을 여기서 붙인다. 후보 조회
        # 상한도 --limit 에 비례해(SCAN_FACTOR) --limit 을 늘리면 더 확인한다 (2026-11-10 리뷰·실측: 성수역 0.2km --rent-max
        # 1000 --limit 5 는 34건 중 5건, 0.8km --limit 120 은 '150건만 조회했습니다' 에서 끝나 다음 할 일이 없었다)
        # 후보 조회 상한에서 멈췄으면 가격 조건은 권하지 않는다. 가격은 직방 목록 앞의 후보를 상한까지 고른 뒤 거르므로, 좁혀도
        # 같은 후보만 다시 보고 일치 수만 준다. 미확인 후보에 닿는 건 --limit(상한이 비례)과 서버가 거르는 조건·범위다
        # (2026-11-11 리뷰·실측: 성수역 0.8km --limit 5 를 --rent-max 50 에서 30 으로 좁혀도 같은 60건만 보고 242건이 미확인)
        capped = inspected < total and len(listings) < limit
        hint = more_hint(limit, MAX_LIST_LIMIT, f'{STORE_SERVER_NARROW if capped else STORE_NARROW}·{area}')
        if inspected < total:
            notes.append(note(
                '일부',
                f"{'후보 조회 상한' if capped else '결과 개수 제한'}으로 직방 목록 앞의 후보 {inspected}건만 조회했습니다 "
                # 상한이 --limit 에 비례한다는 말이 없으면 '--limit 을 늘리라' 와 따로 정해진 상한으로 읽혀 늘리지 않았다
                # (2026-11-11 LLM 사용 시험: 성수역 --rent-max 50 --limit 20 의 '조회 상한 100건' 에 --limit 대신 반경만 좁힘)
                f'(조회 상한은 --limit 의 {SCAN_FACTOR}배·최소 {MIN_SCAN_PINS}건이라 {scan_cap}건, '
                f'미확인 후보 {total - inspected}건). 전체 가격 조건 일치 수는 모릅니다. {hint}',
            ))
        elif has_more:
            # 위 분기가 아니면 has_more 는 확인한 일치 매물이 --limit 에 잘렸다는 뜻이다
            notes.append(note('일부', f'확인한 가격 조건 일치 매물 중 직방 목록 앞의 {len(listings)}건만 보여 줍니다. {hint}'))
    else:
        notes = limit_notes(
            total, len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow=f'{STORE_NARROW}·{area}', order='직방 목록',
            inspected=inspected, has_more=has_more,
        )
    if office_no_key_money:
        notes.append(note(
            '제외',
            f'권리금 조건을 걸어 확인한 후보 중 권리금이 해당 없는 사무실 {office_no_key_money}건을 뺐습니다 '
            '(직방이 사무실에는 권리금을 주지 않습니다). 사무실도 보려면 권리금 조건 없이 검색하세요',
        ))
    if business_conditions and vacant:
        # [제외] 가 아니라 [참고] 다. 공실은 업종 조건에 맞는 매물을 뺀 것이 아니라 직방이 업종과 무관하게 따로 주는 묶음이다
        # (2026-11-10 리뷰가 [제외] 라고 했으나 오탐. 실측: 성수역 0.5km --business 카페/커피 는 카페 5건과 '이 지역 비어있는
        # 상가' 23건. 업종 조건 없이 찾는 법은 안내에 있다)
        notes.append(
            f"업종 조건과 별개로 {'동' if dongs else '반경'} 안에 비어 있는 상가가 {len(vacant)}건 있습니다. "
            '공실도 보려면 --business 없이 다시 검색하세요'
        )
    return ZigbangStoreSearchResult(
        region=region,
        radius_km=None if dongs else radius_km,
        boundary='·'.join(dong.name for dong in dongs) if dongs else None,
        total=total,
        inspected_in_radius=inspected if filter_price else None,
        price_matched_in_radius=matched if filter_price else None,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=scope_notes + notes,
    )


def store_detail_to_listing(response: ZigbangStoreArticleStoreV2ResponseModel) -> ZigbangStoreListingDetail:
    """상가 상세를 `ZigbangStoreListingDetail` 로 바꾼다. 연락처·사진·본문은 옮기지 않는다."""
    item = response.item
    trade_type = store_trade(item)
    elevator = {'있음': True, '없음': False}.get(item.elevator or '')
    return ZigbangStoreListingDetail(
        source='zigbang',
        id=f'store-{item.item_id}',
        url=store_url(item.item_id),
        trade_type=trade_type,
        property_type='상가',
        title=item.title,
        price_manwon=item.sales_price if trade_type == '매매' else None,
        deposit_manwon=None if trade_type == '매매' else item.deposit,
        rent_manwon=item.rent if trade_type == '월세' else None,
        manage_cost_manwon=item.manage_cost,
        area_m2=item.size_m2,
        area_pyeong=m2_to_pyeong(item.size_m2),
        floor=store_floor(item.floor),
        building_floor=store_floor(item.floor_all),
        address=join_address(item.local1, item.local2, item.local3),
        lat=item.lat,
        lng=item.lng,
        parking=store_parking(item.parking),
        elevator=elevator,
        nearby_subways=sent_or_none(response, 'subways', [
            f'{subway.name} ({subway.description})' if subway.description else subway.name
            for subway in response.subways
        ]),
        business=item.business,
        key_money_manwon=item.key_money,
        recommended_business=item.recommended_business,
        vacancy=item.section_type,
        lease_unit=item.lease_unit,
        interior=item.interior,
        toilet=item.toilet,
        heating=item.heating,
    )


def get_store_listing(client: ZigbangClient, item_id: int) -> ZigbangStoreListingDetail:
    """상가 매물 하나의 상세를 조회한다.

    Raises:
        ListingUnavailableError: 없는 매물(404)이거나 상태가 open 이 아닐 때.
    """
    listing_id = f'store-{item_id}'
    with unavailable_on_404(listing_id):
        response = client.run_request_store_article_store_v2(
            ZigbangStoreArticleStoreV2RequestParameterModel(item_id=item_id)
        )
    if response.item.status != 'open':
        raise ListingUnavailableError('zigbang', listing_id, status=response.item.status)
    return store_detail_to_listing(response)
