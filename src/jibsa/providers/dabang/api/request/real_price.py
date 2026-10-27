from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import COMPLEX_ID_PATTERN_TEXT

from typing import (
    Annotated,
    Literal,
    Self,
)


# 실거래 조회 기간 상한 (달). 화면은 3년 전 다음 달부터 이번 달까지(36달)를 묻고, 37달이면 400 "실거래가 히스토리 목록 검색
# 가능 기간을 넘겼습니다" 다 (2026-10-25 실측: 202310~202610 은 400, 202311~202610 은 200)
REAL_PRICE_MAX_MONTHS: int = 36
# 한 번에 받을 수 있는 실거래 수 (화면은 5, 50 까지 확인, 2026-10-25)
REAL_PRICE_PAGE_LIMIT: int = 50

DabangRealPriceSearchType = Literal['SALE', 'LEASE']


def months_between(from_month: str, to_month: str) -> int:
    """`YYYYMM` 두 달 사이를 양 끝을 포함해 센다 (202311~202610 → 36)."""
    return (int(to_month[:4]) - int(from_month[:4])) * 12 + int(to_month[4:]) - int(from_month[4:]) + 1


class DabangRealPricePeriodModel(RequestModel):
    """실거래 조회 기간과 쪽 (두 실거래 엔드포인트가 같이 받는다).

    Args:
        from_date: 시작 달 (YYYYMM).
        to_date: 끝 달 (YYYYMM).
        search_type: 'SALE' 매매, 'LEASE' 전세·월세.
        page: 쪽 번호 (1부터).
        limit: 한 쪽 거래 수 (최대 50).
    """

    from_date: Annotated[
        str,
        Field(pattern=r'^\d{4}(0[1-9]|1[0-2])$', description='시작 달 (YYYYMM)', alias='fromDate')
    ]
    to_date: Annotated[
        str,
        Field(pattern=r'^\d{4}(0[1-9]|1[0-2])$', description='끝 달 (YYYYMM)', alias='toDate')
    ]
    search_type: Annotated[
        DabangRealPriceSearchType,
        Field(description='매매(SALE) 또는 전월세(LEASE)', alias='searchType')
    ]
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
    limit: Annotated[
        int,
        Field(ge=1, le=REAL_PRICE_PAGE_LIMIT, description='한 쪽 거래 수')
    ] = REAL_PRICE_PAGE_LIMIT

    @model_validator(mode='after')
    def period_within_limit(self) -> Self:
        months = months_between(self.from_date, self.to_date)
        if months < 1:
            raise ValueError(f'시작 달({self.from_date})이 끝 달({self.to_date})보다 늦습니다')
        if months > REAL_PRICE_MAX_MONTHS:
            raise ValueError(f'다방 실거래는 최대 {REAL_PRICE_MAX_MONTHS}달까지 조회합니다 ({months}달)')
        return self


class DabangRealPriceComplexHistoriesV5RequestParameterModel(DabangRealPricePeriodModel):
    """`GET /api/v5/real-price/complex/histories` 쿼리 (단지 평형 하나의 실거래).

    Args:
        complex_id: 단지 ID.
        space_seq: 평형 번호.
    """

    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID', alias='complexId')
    ]
    space_seq: Annotated[
        int,
        Field(gt=0, description='평형 번호', alias='spaceSeq')
    ]


class DabangRealPriceHouseHistoryV5RequestParameterModel(DabangRealPricePeriodModel):
    """`GET /api/v5/real-price/house/history` 쿼리 (단지 없는 매물의 실거래: 그 동의 같은 건물 유형).

    Args:
        room_id: 매물 ID.
    """

    room_id: Annotated[
        str,
        Field(pattern=r'^[0-9a-f]{24}$', description='매물 ID', alias='roomId')
    ]


class DabangRealPriceComplexChartsV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-price/complex/charts` 쿼리 (평형 하나의 36달 시세 흐름).

    Args:
        complex_id: 단지 ID.
        space_seq: 평형 번호.
    """

    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID', alias='complexId')
    ]
    space_seq: Annotated[
        int,
        Field(gt=0, description='평형 번호', alias='spaceSeq')
    ]
