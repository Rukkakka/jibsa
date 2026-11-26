"""요청 모델: 재개발 구역 매물 (search listings --redevelopment)."""

from pydantic import Field

from jibsa.providers.naver.api.request.common import (
    NaverArticleSortType,
    NaverPriceFilterModel,
    NaverTradeType,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel(NaverPriceFilterModel):
    """`POST /front-api/v1/complex/redevelopmentArea/articleList` 본문. 재개발 구역 하나의 매물.

    페이지는 30건까지 (31부터 400). 가격 키·정렬은 단지 매물 목록과 같고 서버가 거른다
    (한남4구역 매매 41건 → 50억 이하 19건, 2026-10-10 확인). 원 단위다.
    """

    size: Annotated[
        int,
        Field(ge=1, le=30, description='페이지 크기')
    ] = 30
    redevelopment_area_number: Annotated[
        int,
        Field(gt=0, description='재개발 구역 번호 (redevelopmentArea/list 의 redevelopmentAreaNumber)', alias='redevelopmentAreaNumber')
    ]
    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형 필터. 비우면 전체', alias='tradeTypes')
    ] = []
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
    article_sort_type: Annotated[
        NaverArticleSortType,
        Field(description='정렬', alias='articleSortType')
    ] = 'RANKING_DESC'
    seed: Annotated[
        str | None,
        Field(description='첫 응답의 seed. 첫 요청은 빼고, 이후 그대로 넘긴다')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로', alias='lastInfo')
    ] = []
