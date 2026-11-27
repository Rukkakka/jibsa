"""요청 모델: 지역 최근 실거래 (region-trades)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


ZigbangLocalTradeDealType = Literal['sales', 'charter', 'rent']
# 웹 기간 탭. today 오늘, yesterday 어제, 그 밖은 최근 N일
ZigbangLocalTradePeriodType = Literal['today', 'yesterday', 'last_7_days', 'last_15_days', 'last_30_days']


class ZigbangLocalsTradingHistoriesRequestParameterModel(RequestModel):
    """`GET /apt/locals/trading-histories` 쿼리. 지역의 최근 실거래 (웹 지역정보 화면의 '최근 실거래').

    웹 요청의 쿼리 순서 `page`·`localCd`·`dealType`·`sortSpec`·`periodType`·`limit` 와 같게 선언한다. `page=0` 은 서버 500 이고
    `limit` 의 서버 상한은 보지 못했다 (2026-11-22 실측: limit=1000 에 616건이 모두 왔다).
    """

    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호 (1부터). 0 은 서버 500')
    ]
    local_code: Annotated[
        str,
        Field(pattern=r'^\d{2}(\d{3}(\d{3})?)?$', description='지역 코드 (동 8자리·구 5자리·시도 2자리)', alias='localCd')
    ]
    deal_type: Annotated[
        ZigbangLocalTradeDealType,
        Field(description='거래 유형 (sales 매매, charter 전세, rent 월세)', alias='dealType')
    ]
    sort_spec: Annotated[
        str,
        Field(
            description=(
                '정렬 이름. 웹 번들(2026-11-19)이 쓰는 값: 매매 sales_latest_registration·sales_highest_price·sales_lowest_price·'
                'sales_market_price_comparison·sales_lower_than_public_price, 전세 charters_latest_registration·charters_highest_price·'
                'charters_lowest_price·charters_lease_price, 월세 rents_latest_registration·rents_highest_deposit·'
                'rents_highest_monthly_rent_price. 값은 service 가 고른다'
            ),
            alias='sortSpec'
        )
    ]
    period_type: Annotated[
        ZigbangLocalTradePeriodType,
        Field(description='기간 (today 오늘, yesterday 어제, 그 밖은 최근 7·15·30일)', alias='periodType')
    ]
    limit: Annotated[
        int,
        Field(ge=1, description='쪽 크기')
    ]
