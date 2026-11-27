"""응답 모델: 단지·매물 실거래가 (real-price)."""

from pydantic import Field

from jibsa.providers.daangn.api.models.response.common import (
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnTransactionConnectionModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId (단지 실거래가)
# ---------------------------------------------------------------------------

class DaangnComplexTransactionsModel(DaangnBaseResponseModel):
    """단지의 실거래 연결 두 개 (웹 쿼리의 별칭)."""

    buy_transactions: Annotated[
        DaangnTransactionConnectionModel | None,
        Field(description='매매', alias='buyTransactions')
    ] = None
    borrow_transactions: Annotated[
        DaangnTransactionConnectionModel | None,
        Field(description='전세·월세', alias='borrowTransactions')
    ] = None



class DaangnComplexByOriginalIdModel(DaangnBaseResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexTransactionsModel | None,
        Field(description='단지')
    ] = None



class DaangnComplexByOriginalIdDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexByOriginalIdModel | None,
        Field(description='단지 조회 결과', alias='complexByOriginalId')
    ] = None



class DaangnComplexByOriginalIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexByOriginalId` (단지 실거래가) 응답."""

    data: Annotated[
        DaangnComplexByOriginalIdDataModel | None,
        Field(description='결과')
    ] = None



# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleByOriginalArticleId (매물 실거래가)
# ---------------------------------------------------------------------------

class DaangnArticleByOriginalArticleIdDataModel(DaangnBaseResponseModel):
    """GraphQL `data`. 실거래 연결 모양은 단지 실거래가와 같다."""

    article_by_original_article_id: Annotated[
        DaangnComplexTransactionsModel | None,
        Field(description='매물 (실거래 연결만 받는다). 없는 매물이면 null 과 recordNotFound 에러', alias='articleByOriginalArticleId')
    ] = None



class DaangnArticleByOriginalArticleIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articleByOriginalArticleId` (매물 실거래가) 응답."""

    data: Annotated[
        DaangnArticleByOriginalArticleIdDataModel | None,
        Field(description='결과')
    ] = None
