"""재개발 구역 목록 (search redevelopment)."""

from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    TRADE_KEY_BY_NAME,
    normalize_address,
    note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
)
from jibsa.providers.naver.api.request.redevelopment.search import (
    NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel,
    NaverRedevelopmentAreaPagingRequestModel,
)
from jibsa.providers.naver.api.response.common import (
    NaverRedevelopmentAreaItemModel,
    NaverRedevelopmentAreaPageModel,
    NaverResponseModel,
)
from jibsa.providers.naver.api.response.redevelopment.search import (
    NaverRedevelopmentAreaPinModel,
)
from jibsa.providers.naver.service.common.constants import (
    TRADE_CODE_BY_NAME,
)
from jibsa.providers.naver.service.common.models import (
    PageScan,
)
from jibsa.providers.naver.service.common.paging import (
    area_scope,
    boundary_filter,
    bounding_box,
    pagination_notes,
    scan_null_items_notes,
    scan_pages,
)
from jibsa.providers.naver.service.common.price import (
    amount_range,
    trade_article_counts,
)
from jibsa.providers.naver.service.common.response import (
    unwrap,
)
from jibsa.providers.naver.service.redevelopment.constants import (
    MAX_REDEVELOPMENT_PAGE_REQUESTS,
    REDEVELOPMENT_CODE,
    REDEVELOPMENT_PAGE_SIZE,
    REDEVELOPMENT_PRECISION,
    REDEVELOPMENT_SORT_TYPE_BY_NAME,
    REDEVELOPMENT_URL,
)
from jibsa.providers.naver.service.redevelopment.models import (
    NaverRedevelopmentArea,
    NaverRedevelopmentAreasResult,
)

from typing import (
    Any,
)


def _redevelopment_area(
    item: NaverRedevelopmentAreaItemModel,
    distance_km: float | None,
    legal_division: str | None,
) -> NaverRedevelopmentArea:
    info, counts, price = item.info, item.count, item.price
    return NaverRedevelopmentArea(
        redevelopment_id=info.redevelopment_area_number,
        name=info.name,
        # 마커의 법정동 이름은 '서울시 관악구 봉천동' 처럼 줄인 시·도라 상세(redevelopment)와 같은 정식 명칭으로 맞춘다
        legal_division=normalize_address(legal_division),
        planned_household_count=info.total_household_number,
        business_step=info.business_step,
        distance_km=distance_km,
        # 서버는 필터의 tradeTypes·hasArticle 과 상관없이 네 거래를 모두 센다 (한강진역 1.5km 7곳: 단기임대·매매·기본 필터
        # 모두 같은 수, 한남4 목록 매매 43 = 상세 redevelopment 43, 2026-10-10). 그래서 상세와 숫자가 어긋나지 않는다
        listing_counts=trade_article_counts(counts) if counts else None,
        # 그 거래 매물이 없으면 키를 뺀다. 구역 목록은 매매 호가만 준다
        asking_ranges=None if not price else ({'sale': sale} if (sale := amount_range('price_manwon', price.deal_min_price, price.deal_max_price)) else {}),
        url=REDEVELOPMENT_URL.format(info.redevelopment_area_number),
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

    `legal_division_code` 를 주면 그 법정동·시·군·구 안 구역(legalDivisionList), 아니면 반경 안 구역이다. 코드가 시·군·구면
    시·군·구 경계(GUN), 아니면 읍·면·동 경계(EUP)다 (`boundary_filter`).
    반경이면 목록에 좌표가 없어 마커(1회)로 구역 위치를 받아 반경 밖·위치를 모르는 구역을 뺀다. 30곳씩 받고
    요청은 `MAX_REDEVELOPMENT_PAGE_REQUESTS` 회에서 멈춘다. 구역은 구역 번호로만 중복을 가른다. 이름이 같은 다른 번호
    구역이 있어(금호제16구역 1000210·19625, 2026-11-18 성동구) 이름으로 합치지 않는다.

    Args:
        legal_division_name: 동·시·군·구 경계로 찾을 때 결과의 legal_division 에 넣을 이름. 시·군·구 경계의
            목록은 구역마다의 법정동(`legalDivisionAddress`)을 주지 않아 모든 구역에 같은 이름이 들어간다.
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
    box = None if legal_division_code is not None else bounding_box(lat, lng, radius_km)
    if legal_division_code is not None:
        filter_ = boundary_filter(filter_, legal_division_code)
    else:
        markers = unwrap(
            client.run_request_complex_redevelopment_area_markers_v1(
                NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel(
                    filter=filter_, bounding_box=box, precision=REDEVELOPMENT_PRECISION,
                )
            ),
            '재개발 구역 위치',
            hint=None,
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
        return unwrap(response, '재개발 구역 목록', hint=None)

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
        counts = area.listing_counts
        if trade_types and not (counts and any(counts[TRADE_KEY_BY_NAME[name]] for name in trade_types)):
            no_trade.add(number)
            return number
        areas.setdefault(number, area)
        return number

    scan_pages(scan, fetch, keep, page_size=REDEVELOPMENT_PAGE_SIZE)
    result = list(areas.values())[:limit]
    notes: list[str] = []
    area_text = area_scope(legal_division_code, radius_km)
    # --trade 는 서버가 구역을 거르지 않아 좁히는 효과가 없다. 구역 목록은 지역·반경만 좁히라고 한다
    if legal_division_code is not None:
        area_text = area_text._replace(narrow='지역', narrow_action='지역을 좁혀')
    else:
        area_text = area_text._replace(narrow='반경', narrow_action='반경을 줄여')
    if scan.truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 {scan.received}곳까지만 훑었습니다. 구역이 더 있을 수 있으니 '
            f'{area_text.narrow_action} 다시 검색하세요',
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
        reason = '검색 범위(반경) 밖이거나 위치를 모르거나 고른 거래 유형 매물이 없는' if trade_types else '중복이거나 검색 범위(반경) 밖이거나 위치를 모르는'
    notes += pagination_notes(
        scan.total, len(result), limit, scan.received, subject='구역', truncated=scan.truncated, excluded_reason=reason,
        stalled=scan.stopped_short(resumed=False), exhausted=scan.exhausted,
        scope=area_text.scope, total_basis=area_text.total_basis, null_items=scan.null_items, narrow=area_text.narrow,
    )
    notes += scan_null_items_notes(scan, '네이버 재개발 구역')
    return NaverRedevelopmentAreasResult(total=scan.total, returned=len(result), areas=result, notes=notes)
