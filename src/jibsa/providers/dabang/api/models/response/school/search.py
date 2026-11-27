"""응답 모델: 동 안 학교·유치원·어린이집 목록 (search schools)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangRegionalAdvancementModel(DabangBaseResponseModel):
    """동 안 학교 목록의 진학률 한 갈래 (중·고등학교). 웹은 '과고 1%' 꼴 꼬리표로 그리고 0 보다 크면 강조한다."""

    advancement_type_name: Annotated[
        str | None,
        Field(description="갈래 이름 ('과고', '외고', '자사고', '예고')", alias='advancementTypeName')
    ] = None
    advancement_percentage: Annotated[
        float | None,
        Field(description='진학률 (%)', alias='advancementPercentage')
    ] = None


class DabangRegionalSchoolModel(DabangBaseResponseModel):
    """동 안 학교·유치원·어린이집 하나. 좌표·전화는 오지 않는다 (2026-11-14 실측).

    `schoolCode` 는 상세(`3/education/{단계}/{코드}`)의 코드와 같다. 웹도 이 코드로 상세를 연다 (school-regional 청크 `W`).
    """

    school_code: Annotated[
        str,
        Field(description='학교 코드', alias='schoolCode')
    ]
    school_name: Annotated[
        str | None,
        Field(description='이름', alias='schoolName')
    ] = None
    school_establishment_type: Annotated[
        str | None,
        Field(description="설립 구분 ('PUBLIC', 'PRIVATE', 'HOME', 'WORKPLACE', 'COOPERATIVE')", alias='schoolEstablishmentType')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    advancement_list: Annotated[
        list[DabangRegionalAdvancementModel] | None,
        Field(description='진학률 (중·고등학교만 온다)', alias='advancementList')
    ] = None


class DabangRegionalSchoolResultModel(DabangBaseResponseModel):
    """동 안 학교 목록 `result` (30곳씩). 쪽이 끝나면 `list` 가 비고 `total` 은 그대로 온다 (2026-11-14 실측)."""

    list_: Annotated[
        list[DabangRegionalSchoolModel] | None,
        Field(description='학교', alias='list')
    ] = None
    total: Annotated[
        int | None,
        Field(description='전체 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRegionInfoSchoolRegionalV5ResponseModel(DabangV5ResponseModel[DabangRegionalSchoolResultModel]):
    """`GET /api/v5/region-info/school/regional/{level}` 응답."""
