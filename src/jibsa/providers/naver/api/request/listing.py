"""요청 모델: 단지 매물 목록과 매물 상세 (search listings --complex, listing)."""

from pydantic import (
    Field,
    field_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverArticleSortType,
    NaverPriceFilterModel,
    NaverRealEstateType,
    NaverTradeType,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class NaverArticleRequestParameterModel(RequestModel):
    """매물 계열 GET 엔드포인트가 공유하는 쿼리. 이름이 `articleId` 가 아님에 주의."""

    article_number: Annotated[
        str,
        Field(pattern=r'^\d+$', description='매물 번호')
    ] = Field(alias='articleNumber')


class NaverArticleKeyV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/key` 쿼리."""


class NaverArticleBasicInfoV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/basicInfo` 쿼리. 유형 두 개는 article/key 로 먼저 알아낸다."""

    real_estate_type: Annotated[
        NaverRealEstateType,
        Field(description='매물 유형 코드')
    ] = Field(alias='realEstateType')
    trade_type: Annotated[
        NaverTradeType,
        Field(description='거래 유형 코드')
    ] = Field(alias='tradeType')


class NaverArticleAgentV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/agent` 쿼리."""


class NaverArticleMaintenanceFeeV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/maintenanceFee` 쿼리."""


class NaverArticleTaxV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/tax` 쿼리."""


class NaverArticleAgentFeeV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/agentFee` 쿼리."""


class NaverDataServiceTransportV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/data-service/transport` 쿼리. 매물 상세 화면은 article 과 매물 번호로 부른다."""

    item_type: Annotated[
        Literal['article', 'complex', 'villa'],
        Field(description='대상 종류 (사이트 ITEM_TRANSPORT_TYPE: 매물, 단지, 빌라 단지)')
    ] = Field(default='article', alias='itemType')
    item_id: Annotated[
        int,
        Field(gt=0, description='매물 번호 또는 단지 번호')
    ] = Field(alias='itemId')


class NaverEducationBuildingSchoolV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/building/school` 쿼리. 단지의 동마다 배정 초등학교를 준다.

    단지형 빌라(A05·A06·A07)는 villa 로 물어야 한다 (complex 로 물으면 빈 목록, 2026-10-09 확인).
    사이트는 단지·동 번호가 있는 매물에만 학교를 보여 준다.
    """

    item_type: Annotated[
        Literal['complex', 'villa'],
        Field(description='단지 종류 (사이트 ArticleSchoolItemType)')
    ] = Field(alias='itemType')
    complex_number: Annotated[
        int,
        Field(gt=0, description='단지 번호')
    ] = Field(alias='complexNumber')
    building_number: Annotated[
        int,
        Field(gt=0, description='동 번호 (article/key 의 buildingNumber)')
    ] = Field(alias='buildingNumber')


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
        Field(gt=0, description='단지 번호. 서버가 문자열을 요구해 문자열로 직렬화한다')
    ] = Field(alias='complexNumber')
    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형 필터. 비우면 전체')
    ] = Field(default=[], alias='tradeTypes')
    pyeong_types: Annotated[
        list[int],
        Field(description='평형 번호 필터. 비우면 전체')
    ] = Field(default=[], alias='pyeongTypes')
    dong_numbers: Annotated[
        list[str],
        Field(description='동 번호 필터 (buildingList 의 number, 동 이름 아님). 비우면 전체')
    ] = Field(default=[], alias='dongNumbers')
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값')
    ] = Field(default='PC', alias='userChannelType')
    article_sort_type: Annotated[
        NaverArticleSortType,
        Field(description='정렬 (RANKING_DESC 네이버 랭킹 기본). 가격순은 거래 유형마다 다른 금액(매매가·보증금)을 섞어 비교한다')
    ] = Field(default='RANKING_DESC', alias='articleSortType')
    seed: Annotated[
        str | None,
        Field(description='첫 응답의 seed. 첫 요청은 빼고, 이후 그대로 넘긴다. 빠지면 랭킹순이 페이지마다 다시 섞여 '
                          '매물이 겹치거나 빠진다 (120건 중 고유 110건, 2026-10-10 확인)')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로')
    ] = Field(default=[], alias='lastInfo')

    @field_serializer('complex_number')
    def serialize_complex_number(self, v: int) -> str:
        return str(v)


class NaverComplexVillaArticleListV1RequestPayloadModel(NaverComplexArticleListV1RequestPayloadModel):
    """`POST /front-api/v1/complex/villa/article/list` 본문. 아파트 단지 매물 목록과 같은 모양이다."""
