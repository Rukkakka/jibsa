"""단지 매물 목록 (search listings --complex)."""



from jibsa.core.listing import (
    Listing,
    keep_unread_dates,
    note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.listing.complex import (
    NaverComplexArticleListV1RequestPayloadModel,
    NaverComplexVillaArticleListV1RequestPayloadModel,
)
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
)
from jibsa.providers.naver.service.common.functions import (
    COMPLEX_SORT_TYPE_BY_NAME,
    TRADE_CODE_BY_NAME,
    check_pyeong_numbers,
    group_sort_notes,
    listing_keeper,
    pagination_notes,
    price_filter_of,
    price_sort_notes,
    resolve_dong_numbers,
    scan_null_items_notes,
    scan_pages,
    unwrap,
    villa_by_complex_response,
    villa_fallback_found,
)
from jibsa.providers.naver.service.common.models import (
    NaverListingsResult,
    NaverTradeConditions,
    PageScan,
)

from typing import (
    Any,
)


COMPLEX_PAGE_SIZE: int = 30


# 단지 매물 목록 요청 상한 (빌라 단지로 다시 묻는 1회 포함). limit 건까지만 받고, 받은 뒤 중복·모르는 거래 유형으로
# 빠져도 그만큼 다시 받지 않는다
MAX_COMPLEX_ARTICLE_PAGE_REQUESTS: int = 5


def list_complex_articles(
    client: NaverClient,
    complex_number: int,
    *,
    conditions: NaverTradeConditions | None = None,
    pyeong_numbers: list[int] | None = None,
    dong_names: list[str] | None = None,
    sort: str = '랭킹순',
    villa: bool | None = None,
    limit: int = 30,
) -> NaverListingsResult:
    """단지 매물을 `lastInfo` 커서로 넘기며 `limit` 건까지 모은다.

    빌라 단지(A05·A06·A07)는 아파트 단지 목록이 0건으로 오므로, 첫 페이지가 비면 빌라 단지 목록으로
    다시 묻는다 (매물이 없는 아파트 단지도 한 번 더 묻고, 빌라 쪽이 실패하면 0건이다. `villa` 를 주었거나
    동 목록을 조회했으면 단지 종류를 이미 알아 다시 묻지 않는다). 요청은 `MAX_COMPLEX_ARTICLE_PAGE_REQUESTS` 회에서
    멈추고 `notes` 로 알린다. 다음 쪽이 있다는데 준 매물이 모두 이미 받은 것이거나 쪽이 비면 커서가 멈춘 것으로 보고 끝낸다.
    평형 번호를 주었는데 0건이면 평형 목록으로 번호를 확인한다 (1~2회 추가, 아파트로 정해지면 빌라 목록은 묻지 않는다).
    단지 종류를 모른 채 0건이면 단지 정보로 단지가 있는지 확인한다 (1~2회 추가).

    Raises:
        JibsaError: 평형 번호가 그 단지에 없거나, 단지 번호가 아파트·빌라 단지 어디에도 없으면 NOT_FOUND.

    Args:
        conditions: 거래 유형·가격 조건 (`NaverTradeConditions`). 서버 필터로 보내고 받은 뒤 다시 거르지 않는다.
        dong_names: 동 이름 ('104', '104동'). 주면 동 목록을 먼저 조회해 동 번호로 바꾼다 (요청 1~2회 추가).
        sort: 정렬 (`COMPLEX_SORT_TYPE_BY_NAME` 의 이름). 서버가 정렬해 준다.
        villa: 빌라 단지인지 (`resolve_complex_number` 결과). 모르면 None.
    """
    conditions = conditions or NaverTradeConditions()
    sort_type = COMPLEX_SORT_TYPE_BY_NAME[sort]
    dong_numbers: list[str] = []
    if dong_names:
        dong_numbers, villa = resolve_dong_numbers(client, complex_number, dong_names, villa=villa)
    # 단지 종류를 알면(단지 이름 검색·동 목록) 빌라는 아파트 목록을 건너뛰고, 아파트는 첫 페이지가 비어도 빌라 목록으로
    # 다시 묻지 않는다. 모르면(None) 첫 페이지가 빌 때 그 자리에서 정한다 (`villa_by_complex_response`)
    known_at_start = villa is not None
    price_filter = price_filter_of(conditions)
    listings: dict[str, Listing] = {}
    held: dict[str, list[tuple[str, str]]] = {}
    scan = PageScan(limit=limit, max_requests=MAX_COMPLEX_ARTICLE_PAGE_REQUESTS)

    def fetch(size: int, seed: str | None, last_info: Any) -> NaverArticlePageModel | None:
        nonlocal villa
        # 다음 쪽이 있는 동안 lastInfo 는 리스트로 온다 ([1, 점수, 매물 번호], 가격·최신순은 가격·날짜가 더 붙는다.
        # 헬리오시티 1,774건 랭킹·가격낮은·최신순 각 3쪽, 2026-10-10). 마지막 쪽도 리스트다 (개포자이 랭킹·가격높은순 각 3쪽,
        # 2026-10-11). 정수가 오면 응답 형식이 바뀐 것이라 멈춘다. 그때 '검색을 마쳤다' 로 안내되지만 실제로 오지 않는
        # 경우라 따로 알리지 않는다
        if last_info is not None and not isinstance(last_info, list):
            return None
        # lastInfo 가 비었으면 첫 쪽으로 본다. 리뷰 오탐 (2026-10-19, 근거 고침 2026-11-20·2026-11-25): 첫 쪽 요청은 jibsa 가 `last_info=[]` 로
        # 보내므로, 서버가 다음 커서로 [] 를 줬다면 다음 요청은 서버에게도 첫 쪽 요청과 같다. 같은 쪽이 다시 오면 새 매물 번호가 없고,
        # `scan_pages` 는 다음 쪽이 있다는데 새 번호가 없고 번호를 모르는 항목·빈 항목도 없으면 `stalled` 로 멈춰 `[일부]`·`has_more: true` 로
        # 알린다 (다음 쪽이 있다는 빈 쪽도 같다. 마지막 쪽이 비면 정상 종료). 번호를 모르는 항목·빈 항목이 섞이면 세고 넘어가 요청 상한에서
        # 멈춘다. 그래서 어떤 응답에서도 끝없이 돌거나 중복이
        # 나오지 않고, 드는 것은 빌라 목록 요청 한 번 정도다. 2026-10-19 실측은 덧붙임이다 (헬리오시티 단지 번호로 랭킹순 4쪽·최신순
        # 월세 4쪽 모두 값이 든 리스트)
        first = not last_info
        payload = NaverComplexArticleListV1RequestPayloadModel(
            complex_number=complex_number,
            size=size,
            trade_types=[TRADE_CODE_BY_NAME[trade] for trade in conditions.trade_types],
            pyeong_types=pyeong_numbers or [],
            dong_numbers=dong_numbers,
            article_sort_type=sort_type,
            seed=seed,
            last_info=last_info or [],
            **price_filter,
        )
        if not villa:
            page = unwrap(client.run_request_complex_article_list_v1(payload), '단지 매물')
            # 빈 항목(null)만 온 쪽도 서버는 매물이 든 쪽으로 센다 (비었다고 보고 빌라 목록을 다시 묻지 않는다)
            if villa is False or not first or page.items or page.null_items('items'):
                return page
            if pyeong_numbers:
                # 평형 번호가 틀려도 0건이 온다. 평형 번호를 확인하면서 단지 종류를 정해, 아파트면 빌라 목록을 묻지 않는다.
                # 빌라 단지로 정해지면 빌라 목록 실패를 '빌라가 아님(0건)' 으로 보지 않고 에러로 낸다
                villa = check_pyeong_numbers(client, complex_number, pyeong_numbers)
                if not villa:
                    return page
            # 첫 페이지가 비면 빌라 단지 목록으로 다시 묻는다. 이 1회도 요청 상한에 센다
            scan.page_requests += 1
        response = client.run_request_complex_villa_article_list_v1(
            NaverComplexVillaArticleListV1RequestPayloadModel(**payload.model_dump())
        )
        # 단지 종류를 모른 채 빌라로 다시 물었는데 빌라 단지도 아니면, 에러 대신 매물 0건으로 본다
        if villa is None:
            if not villa_fallback_found(response):
                return None
            villa = True
        return unwrap(response, '단지 매물')

    scan_pages(scan, fetch, listing_keeper(listings, None, held=held), page_size=COMPLEX_PAGE_SIZE)
    total, inspected, truncated = scan.total, scan.received, scan.truncated
    if pyeong_numbers and not inspected and known_at_start:
        # 단지 종류를 알아 빌라로 다시 묻지 않았어도, 0건이면 평형 번호가 틀린 것인지 확인한다. 모르고 시작했으면
        # 첫 페이지가 빌 때 fetch 안에서 이미 확인했다
        check_pyeong_numbers(client, complex_number, pyeong_numbers, villa=villa)
    elif not inspected and not known_at_start and not pyeong_numbers:
        # 아파트 단지 정보를 먼저 묻고, 빈 결과면 빌라 단지 정보를 묻는다. 단지 매물 목록은 아파트·빌라 모두 없는 단지 번호에도
        # 빈 성공 응답을 줘서, 매물이 없는 단지와 구분되지 않는다 (2026-10-23 실측: 빌라 목록이 99999999 와 아파트 단지
        # 헬리오시티 111515 에 똑같이 `totalCount: 0`).
        if villa_by_complex_response(client.run_request_complex_v1(NaverComplexV1RequestParameterModel(complex_number=complex_number))):
            unwrap(client.run_request_complex_villa_v1(NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)), '단지')

    notes: list[str] = []
    if truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 단지 매물 목록을 {MAX_COMPLEX_ARTICLE_PAGE_REQUESTS}번까지만 받았습니다. '
            '조건에 맞는 매물이 더 있을 수 있으니 조건을 좁혀 다시 검색하세요',
        ))
    notes += price_sort_notes(sort_type, conditions.trade_types)
    result = list(listings.values())[:limit]
    for listing in result:
        keep_unread_dates(held.get(listing.id, ()))
    notes += group_sort_notes(sort_type, result)
    # 단지 하나라 지역 대신 단지 매물의 조건만 좁히라고 한다 (직방·다방 단지 매물과 같다)
    notes += pagination_notes(
        total, len(result), limit, inspected, truncated=truncated, null_items=scan.null_items,
        stalled=scan.stopped_short(resumed=False), exhausted=scan.exhausted,
        narrow='거래 유형·평형·동·가격 조건',
    )
    notes += scan_null_items_notes(scan, '네이버 단지 매물')
    return NaverListingsResult(
        total=total,
        returned=len(result),
        # 단지 매물은 이어 받지 않는다 (next 없음). 더 있는지만 알린다. 네이버가 더 있다면서 새 매물을 주지 않아 멈췄어도(stalled)
        # 네이버가 센 수를 다 받았으면 false, 덜 받았으면 [일부] 안내와 같게 true 다 (2026-11-24 리뷰)
        has_more=scan.cursor is not None or scan.stopped_short(resumed=False),
        listings=result,
        notes=notes,
    )
