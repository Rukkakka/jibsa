"""요청 모델: 단지 매물 목록 (search listings --complex)."""

from pydantic import (
    Field,
    field_serializer,
)

from jibsa.providers.naver.api.models.request.common import (
    NaverArticleSortType,
    NaverPriceFilterModel,
    NaverTradeType,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class NaverComplexArticleListV1RequestPayloadModel(NaverPriceFilterModel):
    """`POST /front-api/v1/complex/article/list` 본문.

    `userChannelType`, `articleSortType`, `lastInfo` 가 빠지면 400 이다.
    빈 배열 필터는 "전체" 를 뜻한다. 가격 키는 사이트 프론트 JS 에서 찾아 매물 수가 줄어드는 것으로
    확인했다 (2026-10-09). 원 단위, 경계 포함이고, 지도 필터처럼 그 금액이 없는 거래 유형은 거르지 않는다
    (매매가 상한을 걸어도 전세는 그대로).
    """

    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기')
    ] = 30
    complex_number: Annotated[
        int,
        Field(gt=0, description='단지 번호. 서버가 문자열을 요구해 문자열로 직렬화한다', alias='complexNumber')
    ]
    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형 필터. 비우면 전체', alias='tradeTypes')
    ] = []
    pyeong_types: Annotated[
        list[int],
        Field(description='평형 번호 필터. 비우면 전체', alias='pyeongTypes')
    ] = []
    dong_numbers: Annotated[
        list[str],
        Field(description='동 번호 필터 (buildingList 의 number, 동 이름 아님). 비우면 전체', alias='dongNumbers')
    ] = []
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
    article_sort_type: Annotated[
        NaverArticleSortType,
        Field(description='정렬 (RANKING_DESC 네이버 랭킹 기본). 가격순은 거래 유형마다 다른 금액(매매가·보증금)을 섞어 비교한다', alias='articleSortType')
    ] = 'RANKING_DESC'
    seed: Annotated[
        str | None,
        Field(description='첫 응답의 seed. 첫 요청은 빼고, 이후 그대로 넘긴다. 빠지면 랭킹순이 페이지마다 다시 섞여 '
                          '매물이 겹치거나 빠진다 (120건 중 고유 110건, 2026-10-10 확인)')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로', alias='lastInfo')
    ] = []

    @field_serializer('complex_number')
    def serialize_complex_number(self, v: int) -> str:
        return str(v)


class NaverComplexVillaArticleListV1RequestPayloadModel(NaverComplexArticleListV1RequestPayloadModel):
    """`POST /front-api/v1/complex/villa/article/list` 본문. 아파트 단지 매물 목록과 같은 모양이다."""
