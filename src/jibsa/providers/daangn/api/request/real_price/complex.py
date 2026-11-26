"""요청 모델: 단지·매물 실거래가 (real-price)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
)


class DaangnComplexByOriginalIdRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId` 쿼리 변수 (웹의 `useTransactionComplexPagination_Query`, 단지 실거래가).

    매매(`buy*`)와 전월세(`borrow*`)를 한 번에 받는다. 웹처럼 두 연결의 크기를 모두 보낸다.
    """

    complex_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='complexId')
    ]
    buy_first: Annotated[
        int,
        Field(ge=1, le=100, description='매매 거래 수 (서버는 100 까지 준다)', alias='buyFirst')
    ] = 1
    buy_after: Annotated[
        str | None,
        Field(description='매매 다음 페이지 커서', alias='buyAfter')
    ] = None
    borrow_first: Annotated[
        int,
        Field(ge=1, le=100, description='전월세 거래 수 (서버는 100 까지 준다)', alias='borrowFirst')
    ] = 1
    borrow_after: Annotated[
        str | None,
        Field(description='전월세 다음 페이지 커서', alias='borrowAfter')
    ] = None
    exclusive_use_area_group: Annotated[
        int | None,
        Field(gt=0, description='전용면적 묶음 (단지 평형의 전용면적 ㎡ 정수, 예: 84). 없으면 전체', alias='exclusiveUseAreaGroup')
    ] = None
    ptp_cds: Annotated[
        list[int] | None,
        Field(
            description='평형 타입 코드. 웹은 아파트형 단지의 공급 평형을 이것으로 고르고 exclusiveUseAreaGroup 을 비운다 (2026-11-12 번들)',
            alias='ptpCds',
        )
    ] = None
    trade_year_month: Annotated[
        str | None,
        Field(
            pattern=r'^\d{6}$',
            description=(
                "계약 연월 (YYYYMM, 예: '202608'). 웹 단지 화면의 시세 그래프에서 달을 누르면 그 달 거래만 보여 주는 변수다 "
                '(ComplexTopicPanel `pe` 가 그래프 점의 yearMonth 를 그대로 보낸다). 없으면 전체 기간'
            ),
            alias='tradeYearMonth',
        )
    ] = None



class DaangnArticleByOriginalArticleIdRequestPayloadModel(RequestModel):
    """GraphQL `articleByOriginalArticleId` 쿼리 변수 (웹의 `useTransactionArticlePagination_Query`, 매물 실거래가).

    매물이 있는 건물(단지)의 비슷한 면적 실거래를 매매(`buy*`)·전월세(`borrow*`)로 나눠 받는다. 단지 실거래와 달리 계약 연월
    (`tradeYearMonth`) 변수가 없다 (2026-11-12 번들 대조: 변수는 articleId·buy*·borrow* 뿐).
    """

    article_id: Annotated[
        str,
        Field(min_length=1, description='숫자 매물 ID', alias='articleId')
    ]
    buy_first: Annotated[
        int,
        Field(ge=1, le=100, description='매매 거래 수', alias='buyFirst')
    ] = 1
    buy_after: Annotated[
        str | None,
        Field(description='매매 다음 페이지 커서', alias='buyAfter')
    ] = None
    borrow_first: Annotated[
        int,
        Field(ge=1, le=100, description='전월세 거래 수', alias='borrowFirst')
    ] = 1
    borrow_after: Annotated[
        str | None,
        Field(description='전월세 다음 페이지 커서', alias='borrowAfter')
    ] = None
