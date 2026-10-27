from pydantic import (
    Field,
    field_serializer,
    model_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
    DabangAptFiltersModel,
    DabangCategoryListRequestParameterModel,
    DabangComplexCategory,
    DabangOfficetelFiltersModel,
    DabangSellingType,
)

from typing import (
    Annotated,
    Literal,
    Self,
)


class DabangComplexListCategoryV5RequestParameterModel(DabangCategoryListRequestParameterModel):
    """`GET /api/v5/complex-list/category/{category}/{search_type}` 쿼리 (단지 지도 목록, 아파트·오피스텔)."""

    @model_validator(mode='after')
    def complex_category(self) -> Self:
        if self.category not in ('apt', 'officetel'):
            raise ValueError(f'단지 목록은 아파트·오피스텔만 있습니다: {self.category}')
        return self


class DabangComplexSummaryV5RequestParameterModel(RequestModel):
    """`GET /api/v5/complex/{complex_type}/summary` 쿼리. 경로 가운데에 단지 ID 가 아니라 소문자 유형이 들어간다
    (단지 ID 를 넣으면 403 빈 응답, 2026-10-25 실측).

    Args:
        complex_type: 'apt' 또는 'officetel' (경로).
        complex_id: 단지 ID.
    """

    complex_type: Annotated[
        DabangComplexCategory,
        Field(exclude=True, description='단지 유형 (경로)')
    ]
    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID', alias='complexId')
    ]


class DabangComplexRoomFiltersModel(RequestModel):
    """단지 매물 목록의 두 번째 필터 (거래 유형·평형).

    Args:
        selling_type_list: 거래 유형.
        space_seq_list: 평형 번호 (`spaceSeq`). 웹은 단지의 평형을 모두 넣어 보낸다.
    """

    selling_type_list: Annotated[
        list[DabangSellingType],
        Field(min_length=1, description='거래 유형', alias='sellingTypeList')
    ]
    space_seq_list: Annotated[
        list[int],
        Field(min_length=1, description='평형 번호', alias='spaceSeqList')
    ]


class DabangRoomListCategoryComplexV5RequestParameterModel(RequestModel):
    """`GET /api/v5/room-list/category/{category}/complex` 쿼리 (단지 하나의 매물).

    필터가 둘이다: `mainFilters` 는 지도 목록과 같은 유형 필터, `filters` 는 거래 유형·평형. 둘 다 JSON 으로 보낸다.

    Args:
        category: 'apt' 또는 'officetel' (경로).
        complex_id: 단지 ID.
        main_filters: 유형 필터.
        filters: 거래 유형·평형.
        order: 정렬. 웹 기본 'RANKING'.
        page: 쪽 번호 (1부터, 24건씩).
    """

    category: Annotated[
        DabangComplexCategory,
        Field(exclude=True, description='단지 유형 (경로)')
    ]
    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID', alias='complexId')
    ]
    main_filters: Annotated[
        DabangOfficetelFiltersModel | DabangAptFiltersModel,
        Field(description='유형 필터 (JSON 으로 보낸다)', alias='mainFilters')
    ]
    filters: Annotated[
        DabangComplexRoomFiltersModel,
        Field(description='거래 유형·평형 (JSON 으로 보낸다)')
    ]
    order: Annotated[
        Literal['RANKING'],
        Field(description='정렬')
    ] = 'RANKING'
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호 (1부터)')
    ] = 1

    @field_serializer('main_filters', 'filters')
    def as_json(self, value: DabangOfficetelFiltersModel | DabangAptFiltersModel | DabangComplexRoomFiltersModel) -> str:
        return value.model_dump_json(by_alias=True)

    @model_validator(mode='after')
    def filters_match_category(self) -> Self:
        expected = DabangAptFiltersModel if self.category == 'apt' else DabangOfficetelFiltersModel
        if not isinstance(self.main_filters, expected):
            raise ValueError(f'{self.category} 단지에 맞지 않는 필터입니다: {type(self.main_filters).__name__}')
        return self
