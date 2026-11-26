"""지역 실거래가 (region-real-price)."""

import logging

from jibsa.core.listing import (
    floor_text,
    normalize_address,
    note,
    read_date,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.real_price.region import (
    DaangnRealsaleFeedInputModel,
    DaangnRealsaleFeedRequestPayloadModel,
    DaangnRealsaleFeedSummaryRequestPayloadModel,
    DaangnRealsaleNewHighFeedInputModel,
    DaangnRealsaleNewHighFeedRequestPayloadModel,
    DaangnRealsaleSummaryInputModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnPageInfoModel,
)
from jibsa.providers.daangn.api.response.real_price.region import (
    DaangnRealsaleFeedItemModel,
    DaangnRealsaleFeedModel,
)
from jibsa.providers.daangn.service.common.functions import (
    OPTIONAL_LOOKUP_ERRORS,
    code_label,
    partial_failure_note,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.real_price.base import (
    _collect_pages,
    _is_rent_type,
    _site_note,
    contract_type_of,
)
from jibsa.providers.daangn.service.real_price.models import (
    DaangnRealsaleSummary,
    DaangnRegionRealPrice,
    DaangnRegionRealPriceResult,
)
from jibsa.providers.daangn.service.region.functions import resolve_realsale_region


logger = logging.getLogger(__name__)


# 매매 실거래의 거래 방식 (서버 transactionType)
DEAL_TYPE_LABELS: dict[str, str] = {'DIRECT': '직거래', 'BROKERED': '중개거래'}



# '직전 최고가 대비' 비율의 소수 자릿수 (`previous_high_change_percent`). 웹 카드는 정수로 보여 준다
PREVIOUS_HIGH_PERCENT_DIGITS: int = 2


# 지역 실거래 피드 정렬. 웹 실거래 화면은 매매를 가격 순(`TRADE_PRICE_DESC`)으로만 부른다 (RealsaleFeedListQuery `Z`). 전월세는
# 웹에 없고 서버가 가격 순을 거절해 최신 순(`LATEST`)이다. 둘 다 서버 값이라 고르는 옵션은 두지 않는다 (2026-11-12 번들 대조)
REALSALE_SORT_BY_TRADE_TYPE: dict[str, str] = {'매매': 'TRADE_PRICE_DESC', '전세': 'LATEST', '월세': 'LATEST'}



REALSALE_SORT_LABEL_BY_SORT: dict[str, str] = {'TRADE_PRICE_DESC': '가격', 'LATEST': '최신'}



def previous_high_change_percent(price: int | None, previous_high: int | None) -> float | None:
    """직전 최고가 대비 변화율 (%, 소수 둘째 자리). 당근 웹 실거래 카드(RealsaleFeedListQuery `g`)의 '직전 최고가 대비 ±N%' 와 같은 비율.

    웹은 정수로 반올림하고(JS `Math.round`) 0 이 되면 소수 첫째 자리(최소 0.1)로 보여 준다. jibsa 는 자릿수를 늘려 소수 셋째
    자리에서 .5 를 올려 반올림한다 (2026-11-13 사용자 결정, [웹과 다른 점](docs/development/providers/daangn.md)). 값이 바뀌었는데
    0.00 이 되면 웹처럼 0 대신 가장 작은 값(±0.01)이다. 반올림은 정수로 셈해 0.125 같은 경계가 부동소수 오차로 내려가지 않게
    한다. 예전에는 웹처럼 정수였고, 0 일 때의 소수 자리 반올림에 Python `round` 를 써 0.25% 가 웹(0.3)과 다른 0.2 였다
    (2026-11-13 리뷰). 직전 최고가가 없거나 0 이하면 없다.
    """
    if price is None or previous_high is None or previous_high <= 0:
        return None
    diff = price - previous_high
    if diff == 0:
        return 0.0
    scale = 10 ** PREVIOUS_HIGH_PERCENT_DIGITS
    # |diff| / previous_high * 100 * scale 를 .5 올림한 정수 (floor(x + 0.5))
    units = max((abs(diff) * 100 * scale * 2 + previous_high) // (2 * previous_high), 1)
    return units / scale * (1 if diff > 0 else -1)



def realsale_to_real_price(item: DaangnRealsaleFeedItemModel, trade_type: str, new_high: bool) -> DaangnRegionRealPrice:
    """지역 피드 한 칸을 `DaangnRegionRealPrice` 로 바꾼다. 금액은 원래 만원이다.

    신고가 배지와 '직전 최고가 대비' 는 웹 카드(MapShell `yc`)와 같다: 신고가는 `priceInsight.isNewHigh` 가 true 이고 해제되지
    않은 거래, 비율은 해제되지 않은 매매에만 `previousMaxPrice` 와 견준다. 일반 피드와 신고가 피드가 같은 카드라 둘 다 낸다.
    """
    realsale = item.realsale
    assert realsale is not None
    danji = item.danji
    insight = item.price_insight
    buy = trade_type == '매매'
    cancelled = realsale.cancel is True
    return DaangnRegionRealPrice(
        trade_type=trade_type,
        from_new_high_feed=new_high,
        trade_date=read_date(realsale.contact_date, '계약일'),
        published_date=None if new_high else read_date(item.data_date, '공개일'),
        address=normalize_address(item.region_name),
        building_name=(danji.name if danji else None) or (item.complex.name if item.complex else None),
        complex_id=item.complex.original_id if item.complex else None,
        household_count=danji.households if danji else None,
        approved_date=read_date(danji.build_date, '사용승인일') if danji else None,
        area_m2=realsale.exclusive_area,
        floor=floor_text(realsale.floor),
        price_manwon=realsale.trade_price if buy else None,
        deposit_manwon=None if buy else realsale.deposit,
        rent_manwon=realsale.month_rent_fee if trade_type == '월세' else None,
        cancelled=realsale.cancel,
        deal_type=code_label(DEAL_TYPE_LABELS, realsale.transaction_type) if buy else None,
        contract_type=None if buy else contract_type_of(realsale.lease_contract_type),
        new_high=(bool(insight and insight.is_new_high) and not cancelled) if buy else None,
        prev_high_manwon=insight.previous_max_price if buy and insight else None,
        prev_high_date=read_date(insight.previous_max_contact_date, '직전 최고가 계약일') if buy and insight else None,
        prev_high_diff_percent=(
            previous_high_change_percent(realsale.trade_price, insight.previous_max_price if insight else None)
            if buy and not cancelled else None
        ),
    )



def realsale_summary(client: DaangnClient, region_id: int, notes: list[str]) -> DaangnRealsaleSummary | None:
    """지역 실거래 화면 머리의 요약 (`realsaleFeedSummary`, 요청 1회). 덤 조회라 실패하면 None 과 `notes` 로 알린다.

    요청 제한(`RateLimitedError`)도 올리지 않고 같은 `[실패]` 안내로 남긴다. 이 요약은 실거래 피드를 다 받은 뒤의 마지막
    요청이라 뒤에 막힐 요청이 없고, 올리면 모아 둔 거래를 모두 버린다 (2026-11-13 리뷰·재현: 역삼동 피드 5건을 받은 뒤 요약만
    RateLimitedError 로 바꾸니 exit 1 에 stdout 이 비었다).
    """
    try:
        response = client.run_request_realsale_feed_summary(
            DaangnRealsaleFeedSummaryRequestPayloadModel(
                input=DaangnRealsaleSummaryInputModel(region_id=region_id),
                new_high_input=DaangnRealsaleSummaryInputModel(region_id=region_id),
            )
        )
        data = unwrap_graphql(response, response.data, '실거래 요약', conditions=False)
    except OPTIONAL_LOOKUP_ERRORS as exc:
        logger.warning('daangn realsale summary failed (%s); continuing without summary', exc)
        notes.append(note('실패', partial_failure_note(exc, '실거래 요약', '공개일 요약을')))
        return None
    sale = data.realsale_feed_summary
    new_high = data.realsale_new_high_feed_summary
    return DaangnRealsaleSummary(
        latest_published_date=read_date(sale.data_date, '최근 공개일') if sale else None,
        sale_count=sale.sale_count if sale else None,
        new_high_count=new_high.new_high_count if new_high else None,
    )



def get_region_real_prices(
    client: DaangnClient,
    query: str,
    *,
    trade_type: str = '매매',
    new_high: bool = False,
    previous_days: bool = False,
    limit: int = 120,
) -> DaangnRegionRealPriceResult:
    """동·구의 최근 실거래(`realsaleFeed`) 또는 신고가 매매(`realsaleNewHighFeed`)를 모은다.

    당근 웹 실거래 화면(`RealsaleFeedListQuery`)은 늘 매매를 가격 순(`TRADE_PRICE_DESC`: 최근 공개일부터, 같은 공개일 안에서
    가격 높은 순)으로 부르고 정렬·거래 유형을 바꾸는 버튼이 없다. 매매는 웹처럼 가격 순이고 정렬 옵션은 없다 (예전에는 기본
    최신 순에 `--sort` 가 있었다, #215). 전세·월세는 같은 API(`tradeType: BORROW`)로 받는 jibsa 옵션이고, 서버가 가격 순을
    거절해 최신 순(`LATEST`)이다 (`REALSALE_SORT_BY_TRADE_TYPE`). 당근은 전월세를 섞어 주므로 전세·월세는 50건씩 최근 1200건까지
    넘겨 보며 월세 유무(`monthRentFee`, 웹 카드가 전세·월세 표시를 가르는 값)로 고른다 (`_collect_pages`). 주소(`regionName`)는
    웹 카드처럼 그대로 준다 (예전에는 읍·면으로 조회하면 리 앞에 읍·면을 끼워 넣었다, #215).

    신고가는 매매만이고 웹처럼 가격 높은 순이다. 웹 신고가 화면처럼 가장 최근 공개일의 신고가만 받고, `previous_days` 를
    주면 이전 공개일 신고가까지 받는다 (`includePreviousDays`, 2026-11-12 사용자 결정).

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        JibsaError: GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 실거래 쿼리를 바꿨을 때.
    """
    region, notes = resolve_realsale_region(client, query, sejong_whole=True)
    buy = trade_type == '매매'
    sort = REALSALE_SORT_BY_TRADE_TYPE[trade_type]

    def fetch(count: int, cursor: str | None) -> DaangnRealsaleFeedModel:
        if new_high:
            response = client.run_request_realsale_new_high_feed(
                DaangnRealsaleNewHighFeedRequestPayloadModel(
                    count=count,
                    cursor=cursor,
                    input=DaangnRealsaleNewHighFeedInputModel(
                        region_id=region.region_id, include_previous_days=previous_days,
                    ),
                )
            )
            return unwrap_graphql(
                response, response.data.realsale_new_high_feed if response.data else None, '신고가', conditions=False
            )
        feed_response = client.run_request_realsale_feed(
            DaangnRealsaleFeedRequestPayloadModel(
                count=count,
                cursor=cursor,
                input=DaangnRealsaleFeedInputModel(
                    region_id=region.region_id,
                    trade_type='SALE' if buy else 'BORROW',
                    sort=sort,
                ),
            )
        )
        return unwrap_graphql(feed_response, feed_response.data.realsale_feed if feed_response.data else None, '지역 실거래', conditions=False)

    def page(count: int, cursor: str | None) -> tuple[list[DaangnRealsaleFeedItemModel], DaangnPageInfoModel | None]:
        feed = fetch(count, cursor)
        return [edge.node for edge in feed.edges if edge.node], feed.page_info

    # 웹에 있는 조회(docstring 의 매매·가장 최근 공개일 신고가)만 당근 웹으로 안내하고, 웹에 없는 조회는 더 받을 수 없다고
    # 알린다 (개발 가이드 지역 실거래 절). 구는 동 이름으로 좁히면 더 받는다
    narrow = region.level == '구'
    if buy and not (new_high and previous_days):
        site = ('동 이름으로 좁혀 다시 조회하거나 ' if narrow else '') + _site_note('https://realty.daangn.com/')
    else:
        site = '동 이름으로 좁혀 다시 조회하세요' if narrow else '이 조건의 남은 거래는 당근 웹에도 없어 더 받을 수 없습니다'
    # 매매·전월세는 서버가 `tradeType` 으로 거르고 신고가는 매매만 와 거래 종류를 다시 보지 않는다 (2026-10-11 실측: SALE 피드 172건·BORROW 피드 293건 모두 요청한 종류)
    found = _collect_pages(
        page,
        lambda item: item.realsale is not None and (
            buy or _is_rent_type(item.realsale.month_rent_fee, trade_type)
        ),
        trade_type, limit,
        site=site,
        remaining='추가 거래가 남아 있습니다',
    )
    collected = found.items
    notes += found.notes
    # 요약은 덤 조회라 본 조회 뒤에 묻는다 (덤 조회가 첫 요청이 되면 첫 화면 실패를 삼키고 본 조회가 브라우저를 다시 띄운다).
    # 마지막 요청이라 요청 제한에 걸려도 받은 거래를 돌려준다 (`realsale_summary`)
    summary = realsale_summary(client, region.region_id, notes)
    if new_high and not previous_days:
        # 웹처럼 하루치라 동처럼 좁은 지역은 자주 비고(2026-11-12 실측: 역삼동 0건), 빈 목록을 '신고가가 없다' 로 읽지 않게 알린다
        notes.append(note(
            '범위',
            ('가장 최근 공개일에 이 지역 신고가가 없습니다' if not collected else '당근 웹처럼 가장 최근 공개일의 신고가만 줍니다')
            + '. 이전 공개일 신고가까지 보려면 --previous-days 를 붙이세요',
        ))
    return DaangnRegionRealPriceResult(
        region=region,
        trade_type=trade_type,
        new_high_only=new_high,
        sort=REALSALE_SORT_LABEL_BY_SORT['TRADE_PRICE_DESC' if new_high else sort],
        summary=summary,
        returned=len(collected),
        has_more=found.has_more,
        trades=[realsale_to_real_price(item, trade_type, new_high) for item in collected],
        notes=notes,
    )
