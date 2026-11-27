from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


DabangLocColumn = Literal['REGION', 'SUBWAY', 'UNIV', 'COMPLEX', 'SALE_IN_LOTS']


class DabangLocSearchV5RequestParameterModel(RequestModel):
    """`GET /api/v5/loc/search` 쿼리. `columnList` 는 같은 키를 값마다 반복해 보낸다 (웹과 같다).

    Args:
        column_list: 찾을 종류 (동·역·대학·단지·분양).
        search_keyword: 검색어.
    """

    column_list: Annotated[
        list[DabangLocColumn],
        Field(min_length=1, description='찾을 종류', alias='columnList')
    ] = ['REGION', 'SUBWAY', 'UNIV', 'COMPLEX']
    search_keyword: Annotated[
        str,
        Field(min_length=1, description='검색어', alias='searchKeyword')
    ]


class DabangGeojsonRegionRequestParameterModel(RequestModel):
    """지역 경계 파일 (`GET /geojson/region/{code}`, 지도 집계가 주는 CDN 주소) 의 경로 값. 동(8자리)과 시·군·구(5자리)
    경계가 있다 (2026-10-25 실측: 11680101 역삼동, 11680 강남구).

    Args:
        code: 법정동 코드 앞자리 (5·8자리).
    """

    code: Annotated[
        str,
        Field(exclude=True, pattern=r'^(\d{5}|\d{8})$', description='법정동 코드 앞자리 (경로)')
    ]


class DabangRegionStatesV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region/states` (시·도 목록). 쿼리가 없다."""


class DabangRegionCitiesV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region/cities` 쿼리 (시·도 하나의 시·군·구 목록, 웹 랭킹·분양 지역 고르기).

    시·도 코드 없이 부르면 400 '유효하지 않은값이 있습니다.' 다 (2026-11-14 실측).

    Args:
        state_code: 시·도 법정동 코드 2자리 (시·도 목록의 `code`).
    """

    state_code: Annotated[
        str,
        Field(pattern=r'^\d{2}$', description='시·도 코드 (2자리)', alias='stateCode')
    ]
