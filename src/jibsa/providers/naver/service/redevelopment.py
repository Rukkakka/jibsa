"""재개발 구역 목록·정보·매물 (search redevelopment, redevelopment, search listings --redevelopment)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    Listing,
    normalize_address,
    note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverRealEstateType,
)
from jibsa.providers.naver.api.request.redevelopment import (
    NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel,
    NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel,
    NaverComplexRedevelopmentV1RequestParameterModel,
    NaverRedevelopmentAreaPagingRequestModel,
    NaverRedevelopmentAreaSortType,
)
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
    NaverRedevelopmentAreaItemModel,
    NaverRedevelopmentAreaPageModel,
    NaverResponseModel,
)
from jibsa.providers.naver.api.response.redevelopment import (
    NaverRedevelopmentAreaPinModel,
)
from jibsa.providers.naver.service.common import (
    COMPLEX_SORT_TYPE_BY_NAME,
    TRADE_CODE_BY_NAME,
    NaverListingsResult,
    NaverTradeConditions,
    PageScan,
    bounding_box,
    group_sort_notes,
    listing_keeper,
    pagination_notes,
    price_filter_of,
    price_sort_notes,
    scan_pages,
    trade_article_counts,
    unwrap,
    won_to_manwon_range,
)

from typing import (
    Annotated,
    Any,
)


# 재개발 구역(F01) 목록·매물. 페이지는 30건까지(31부터 400, 2026-10-10 확인). 네이버 목록 공통으로 기본 30·최대 120
REDEVELOPMENT_CODE: NaverRealEstateType = 'F01'
REDEVELOPMENT_PAGE_SIZE: int = 30
MAX_REDEVELOPMENT_PAGE_REQUESTS: int = 4
MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS: int = 5
# 목록·마커의 지도 줌. 12 이하는 400 이고 높을수록 중심 근처만 준다. 14 는 반경 1·3km 안 구역을 모두 주면서
# 반경 밖은 13 보다 덜 섞인다 (역 3곳 × 반경 2가지 모두 13 과 같은 구역, 15 는 3km 에서 1~4곳 빠짐, 2026-10-10).
# 반경 밖은 마커 좌표로 뺀다
REDEVELOPMENT_PRECISION: int = 14
REDEVELOPMENT_SORT_TYPE_BY_NAME: dict[str, NaverRedevelopmentAreaSortType] = {
    '매물수순': 'ARTICLE_COUNT_DESC',
    '세대수순': 'HOUSEHOLD_NUMBER_DESC',
}


def redevelopment_url(area_number: int) -> str:
    return f'https://fin.land.naver.com/redevelopments/{area_number}'


class NaverRedevelopmentArea(BaseModel):
    """재개발 구역 한 곳. 좌표는 담지 않는다 (위치는 원 사이트로)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    redevelopment_number: Annotated[
        int,
        Field(description='구역 번호. naver search listings --redevelopment 에 넘긴다')
    ]
    name: Annotated[
        str | None,
        Field(description='구역 이름 (예: 한남4재정비촉진구역)')
    ] = None
    legal_division: Annotated[
        str | None,
        Field(description='구역 대표 위치의 법정동 (예: 서울시 용산구 보광동). 동 경계로 찾으면 그 동')
    ] = None
    households: Annotated[
        int | None,
        Field(description='계획 세대수')
    ] = None
    business_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 조합설립인가, 사업시행인가)')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='검색 중심에서 구역 대표 위치까지 거리 (km). 동 경계로 찾으면 좌표를 받지 않아 null')
    ] = None
    article_counts: Annotated[
        dict[str, int] | None,
        Field(description='거래 유형별 매물 수 (매매·전세·월세·단기임대). 서버가 매물 수를 주지 않으면 null (모름)')
    ]
    sale_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 호가 범위 [최저, 최고] (만원). 매매 매물이 없으면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='구역 페이지 URL')
    ]


class NaverRedevelopmentAreasResult(BaseModel):
    """지역 재개발 구역 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int,
        Field(description='서버 집계 구역 수 (동이면 동 안, 반경이면 반경을 감싸는 지도 범위 안. limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 구역 수')
    ]
    areas: Annotated[
        list[NaverRedevelopmentArea],
        Field(description='구역 (네이버 정렬 순서)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내 등. CLI 가 notice 아래에 붙인다')
    ] = []


def _redevelopment_area(
    item: NaverRedevelopmentAreaItemModel,
    distance_km: float | None,
    legal_division: str | None,
) -> NaverRedevelopmentArea:
    info, counts, price = item.info, item.count, item.price
    return NaverRedevelopmentArea(
        redevelopment_number=info.redevelopment_area_number,
        name=info.name,
        # 마커의 법정동 이름은 '서울시 관악구 봉천동' 처럼 줄인 시·도라 상세(redevelopment)와 같은 정식 명칭으로 맞춘다
        legal_division=normalize_address(legal_division),
        households=info.total_household_number,
        business_step=info.business_step,
        distance_km=distance_km,
        # 서버는 필터의 tradeTypes·hasArticle 과 상관없이 네 거래를 모두 센다 (한강진역 1.5km 7곳: 단기임대·매매·기본 필터
        # 모두 같은 수, 한남4 목록 매매 43 = 상세 redevelopment 43, 2026-10-10). 그래서 상세와 숫자가 어긋나지 않는다
        article_counts=trade_article_counts(counts) if counts else None,
        sale_asking_range_manwon=won_to_manwon_range(price.deal_min_price, price.deal_max_price) if price else None,
        url=redevelopment_url(info.redevelopment_area_number),
    )


def list_redevelopment_areas(
    client: NaverClient,
    lat: float,
    lng: float,
    *,
    radius_km: float = 1.0,
    legal_division_code: str | None = None,
    legal_division_name: str | None = None,
    trade_types: list[str] | None = None,
    sort: str = '매물수순',
    limit: int = 30,
) -> NaverRedevelopmentAreasResult:
    """지역 안 재개발 구역 (사업 단계·세대수·매물 수·매매 호가).

    `legal_division_code` 를 주면 그 법정동 안 구역(legalDivisionList), 아니면 반경 안 구역이다. 반경이면
    목록에 좌표가 없어 마커(1회)로 구역 위치를 받아 반경 밖·위치를 모르는 구역을 뺀다. 30곳씩 받고
    요청은 `MAX_REDEVELOPMENT_PAGE_REQUESTS` 회에서 멈춘다.

    Args:
        legal_division_name: 동 경계로 찾을 때 결과의 legal_division 에 넣을 동 이름.
        trade_types: 거래 유형 이름. 주면 그 거래 매물이 1건 이상인 구역만 남긴다. 서버는 tradeTypes 로 구역을 거르지
            않고(hasArticle 을 켜도 같다) 매물수순 정렬 순서만 바꾸므로, 받은 뒤 매물 수로 거르고 뺀 수를 `notes` 로
            알린다 (한강진역 1.5km: 단기임대만 줘도 매매만 있는 7곳이 그대로, 2026-10-10). 없으면 거르지 않는다.
        sort: `REDEVELOPMENT_SORT_TYPE_BY_NAME` 의 이름.
    """
    filter_ = NaverArticleFilterModel(real_estate_types=[REDEVELOPMENT_CODE])
    if trade_types:
        filter_ = filter_.model_copy(update={'trade_types': [TRADE_CODE_BY_NAME[name] for name in trade_types]})
    sort_type = REDEVELOPMENT_SORT_TYPE_BY_NAME[sort]
    pins: dict[int, NaverRedevelopmentAreaPinModel] = {}
    box = bounding_box(lat, lng, radius_km)
    if legal_division_code is not None:
        filter_ = filter_.model_copy(update={'legal_division_numbers': [legal_division_code], 'legal_division_type': 'EUP'})
    else:
        markers = unwrap(
            client.run_request_complex_redevelopment_area_markers_v1(
                NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel(
                    filter=filter_, bounding_box=box, precision=REDEVELOPMENT_PRECISION,
                )
            ),
            '재개발 구역 위치',
        )
        pins = {pin.redevelopment_area_number: pin for pin in markers.pins}

    areas: dict[int, NaverRedevelopmentArea] = {}
    no_trade: set[int] = set()
    scan = PageScan(limit=limit, max_requests=MAX_REDEVELOPMENT_PAGE_REQUESTS)

    def fetch(size: int, seed: str | None, last_info: Any) -> NaverRedevelopmentAreaPageModel:
        paging = NaverRedevelopmentAreaPagingRequestModel(size=size, sort_type=sort_type, seed=seed, last_info=last_info or [])
        response: NaverResponseModel[NaverRedevelopmentAreaPageModel]
        if legal_division_code is not None:
            response = client.run_request_complex_redevelopment_area_legal_division_list_v1(
                NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel(
                    filter=filter_, redevelopment_area_paging_request=paging,
                )
            )
        else:
            response = client.run_request_complex_redevelopment_area_list_v1(
                NaverComplexRedevelopmentAreaListV1RequestPayloadModel(
                    filter=filter_, bounding_box=box, precision=REDEVELOPMENT_PRECISION,
                    redevelopment_area_paging_request=paging,
                )
            )
        return unwrap(response, '재개발 구역 목록')

    def keep(item: NaverRedevelopmentAreaItemModel) -> int:
        number = item.info.redevelopment_area_number
        if legal_division_code is not None:
            area = _redevelopment_area(item, None, legal_division_name)
        else:
            # 지도 줌은 반경 밖 구역도 준다. 위치를 모르는 구역은 반경 안인지 알 수 없어 뺀다
            pin = pins.get(number)
            if pin is None or pin.coordinates is None:
                return number
            distance = round(haversine_km(lat, lng, pin.coordinates.y_coordinate, pin.coordinates.x_coordinate), 2)
            if distance > radius_km:
                return number
            area = _redevelopment_area(item, distance, pin.legal_division_name)
        # 서버가 거래 유형으로 거르지 않아 매물 수로 거른다. 매물 수를 모르는 구역도 그 거래 매물이 있는지 알 수 없어 뺀다
        counts = area.article_counts
        if trade_types and not (counts and any(counts[name] for name in trade_types)):
            no_trade.add(number)
            return number
        areas.setdefault(number, area)
        return number

    scan_pages(scan, fetch, keep, page_size=REDEVELOPMENT_PAGE_SIZE)
    result = list(areas.values())[:limit]
    notes: list[str] = []
    if scan.truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 {scan.received}곳까지만 훑었습니다. 구역이 더 있을 수 있으니 '
            + ('조건을 좁혀' if legal_division_code is not None else '반경을 줄이거나 조건을 좁혀')
            + ' 다시 검색하세요',
        ))
    if no_trade:
        notes.append(note(
            '제외',
            f"고른 거래 유형({', '.join(trade_types or [])}) 매물이 확인되지 않은 구역 {len(no_trade)}곳을 뺐습니다. "
            '네이버가 구역 목록을 거래 유형으로 거르지 않아 받은 매물 수로 걸렀습니다',
        ))
    # 구역은 거래 유형 코드가 없어 --trade 가 없으면 중복(과 반경 밖)만 뺀다
    if legal_division_code is not None:
        reason = '고른 거래 유형 매물이 없는' if trade_types else '중복된'
    else:
        reason = '검색 범위(반경) 밖이거나 고른 거래 유형 매물이 없는' if trade_types else '중복이거나 검색 범위(반경) 밖의'
    notes += pagination_notes(
        scan.total, len(result), limit, scan.received, subject='구역', truncated=scan.truncated, excluded_reason=reason,
    )
    return NaverRedevelopmentAreasResult(total=scan.total, returned=len(result), areas=result, notes=notes)


def list_redevelopment_articles(
    client: NaverClient,
    area_number: int,
    *,
    conditions: NaverTradeConditions | None = None,
    sort: str = '랭킹순',
    limit: int = 30,
) -> NaverListingsResult:
    """재개발 구역 하나의 매물을 `lastInfo`·seed 커서로 넘기며 `limit` 건까지 모은다.

    가격 조건은 서버 필터로 보내고 받은 뒤 다시 거르지 않는다 (그 금액이 없는 거래 유형은 서버도 거르지 않는다).
    요청은 `MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS` 회에서 멈추고 `notes` 로 알린다.

    Args:
        conditions: 거래 유형·가격 조건 (`NaverTradeConditions`).
        sort: 정렬 (`COMPLEX_SORT_TYPE_BY_NAME` 의 이름). 서버가 정렬해 준다.
    """
    conditions = conditions or NaverTradeConditions()
    sort_type = COMPLEX_SORT_TYPE_BY_NAME[sort]
    price_filter = price_filter_of(conditions)
    listings: dict[str, Listing] = {}
    scan = PageScan(limit=limit, max_requests=MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS)

    # 구역 매물의 lastInfo 는 마지막 페이지까지 리스트로 온다 ([1, 710.5, '2652597531'] → [0, -279.6, …], 봉천4-1-3구역
    # 57건 2쪽, 2026-10-10 확인. 봉천4-1-3·봉천14구역 랭킹·가격낮은·최신순 12쪽, 2026-10-11 재확인. 봉천14구역 37건 2쪽,
    # 마지막 쪽 [1, 120.35…, '2649066878'], 2026-10-11 코드 리뷰 뒤 재확인). 실제로 정수가 오지 않아 단지 매물
    # (list_complex_articles)처럼 정수 커서를 따로 막지 않는다. 정수가 오면 요청 모델 검증에 걸리지만 일부러 두는 것이다
    # (docs/development/providers/naver.md 의 페이지네이션 절)
    def fetch(size: int, seed: str | None, last_info: Any) -> NaverArticlePageModel:
        return unwrap(
            client.run_request_complex_redevelopment_area_article_list_v1(
                NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel(
                    redevelopment_area_number=area_number,
                    size=size,
                    trade_types=[TRADE_CODE_BY_NAME[trade] for trade in conditions.trade_types],
                    article_sort_type=sort_type,
                    seed=seed,
                    last_info=last_info or [],
                    **price_filter,
                )
            ),
            '재개발 구역 매물',
        )

    scan_pages(scan, fetch, listing_keeper(listings, None), page_size=REDEVELOPMENT_PAGE_SIZE)
    notes: list[str] = []
    if scan.truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 재개발 구역 매물 목록을 {MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS}번까지만 받았습니다. '
            '조건에 맞는 매물이 더 있을 수 있으니 조건을 좁혀 다시 검색하세요',
        ))
    notes += price_sort_notes(sort_type, conditions.trade_types)
    result = list(listings.values())[:limit]
    notes += group_sort_notes(sort_type, result)
    notes += pagination_notes(scan.total, len(result), limit, scan.received, truncated=scan.truncated)
    # 재개발 구역 매물은 이어 받지 않는다 (next 없음). 더 있는지만 알린다
    return NaverListingsResult(
        total=scan.total, returned=len(result), has_more=scan.cursor is not None, listings=result, notes=notes,
    )


class NaverRedevelopmentDetail(BaseModel):
    """재개발 구역 하나의 정보와 현재 매물 통계. 조합 연락처와 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    redevelopment_number: Annotated[
        int,
        Field(description='구역 번호. naver search listings --redevelopment 에 넘긴다')
    ]
    name: Annotated[
        str | None,
        Field(description='구역 이름')
    ] = None
    legal_division: Annotated[
        str | None,
        Field(description='대표 법정동 (예: 서울시 용산구 한남동)')
    ] = None
    households: Annotated[
        int | None,
        Field(description='계획 세대수')
    ] = None
    business_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 이주및철거)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='계획 용적률 (%)')
    ] = None
    building_coverage_ratio: Annotated[
        float | None,
        Field(description='계획 건폐율 (%)')
    ] = None
    article_counts: Annotated[
        dict[str, int],
        Field(description='거래 유형별 현재 매물 수 (매매·전세·월세·단기임대). 거래 유형을 고르면 그 유형만')
    ]
    sale_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 호가 [최저, 최고] (만원). 매매 매물이 없으면 null')
    ] = None
    jeonse_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='전세 호가 [최저, 최고] (만원). 전세 매물이 없으면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='구역 페이지 URL')
    ]


def get_redevelopment(
    client: NaverClient,
    area_number: int,
    *,
    trade_types: list[str] | None = None,
) -> NaverRedevelopmentDetail:
    """재개발 구역 하나의 기본 정보와 현재 매물 수·호가 범위 (2회 호출).

    Args:
        trade_types: `TRADE_CODE_BY_NAME` 의 이름. 주면 매물 수·호가 범위를 그 거래 유형 매물로만 센다 (서버 필터).

    Raises:
        JibsaError: 없는 구역 번호면 NOT_FOUND.
    """
    info = unwrap(
        client.run_request_complex_redevelopment_v1(
            NaverComplexRedevelopmentV1RequestParameterModel(redevelopment_area_number=area_number)
        ),
        '재개발 구역',
    )
    # 없는 구역 번호도 성공 응답에 빈 객체를 준다 (2026-10-10 확인)
    if not info.name:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'네이버 재개발 구역을 찾지 못했습니다: {area_number}',
            hint='구역 번호는 naver search redevelopment 결과의 redevelopment_number 를 쓰세요',
        )
    stats = unwrap(
        client.run_request_complex_redevelopment_area_article_stats_v1(
            NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel(
                redevelopment_area_number=area_number,
                trade_types=[TRADE_CODE_BY_NAME[name] for name in trade_types or []],
            )
        ),
        '재개발 구역 매물 통계',
    )
    counts, prices = stats.count, stats.price
    ratio = info.building_ratio_info
    return NaverRedevelopmentDetail(
        redevelopment_number=area_number,
        name=info.name,
        legal_division=normalize_address(info.legal_division_address) if info.legal_division_address else None,
        households=info.total_household_number,
        business_step=info.business_step,
        construction_company=info.construction_company or None,
        floor_area_ratio=ratio.floor_area_ratio if ratio else None,
        building_coverage_ratio=ratio.building_coverage_ratio if ratio else None,
        # 서버가 고른 거래 유형만 세고 나머지를 0 으로 준다 (매매만 고르면 전세·월세 0). 세지 않은 유형은 0건이 아니라 해당 없음이다
        article_counts={
            name: count for name, count in trade_article_counts(counts).items() if not trade_types or name in trade_types
        },
        sale_asking_range_manwon=won_to_manwon_range(prices.deal_min_price, prices.deal_max_price),
        jeonse_asking_range_manwon=won_to_manwon_range(prices.rent_min_price, prices.rent_max_price),
        url=redevelopment_url(area_number),
    )
