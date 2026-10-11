"""요청 모델: 동네·역·주소·좌표 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel

from typing import Annotated


class DaangnRegionsKeywordV1RequestParameterModel(RequestModel):
    """`GET www.daangn.com/kr/api/v1/regions/keyword` 쿼리."""

    keyword: Annotated[
        str,
        Field(min_length=1, description='지역명 (예: 역삼동, 강남구). 구 이름이면 그 구의 동 목록이 나온다')
    ]


class DaangnGetRegionByCoordinateRequestPayloadModel(RequestModel):
    """GraphQL `getRegionByCoordinate` 쿼리 변수 (웹의 `regionByCoordinateQuery`)."""

    coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='찾을 좌표')
    ]


class DaangnQueryInputModel(RequestModel):
    """검색어 하나만 받는 `input` (역·주소 검색)."""

    query: Annotated[
        str,
        Field(min_length=1, description='검색어')
    ]


class DaangnSearchSubwayStationPoisRequestPayloadModel(RequestModel):
    """GraphQL `searchSubwayStationPois` 쿼리 변수 (웹의 `fetchSubwayResultQuery`, 역 이름 검색).

    앞부분이 같은 역을 모두 준다 ('강남' → 강남, 강남구청, 강남대). 역 이름에는 '역' 이 붙지 않는다.
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description='역 이름 (예: 역삼역, 역삼)')
    ]


class DaangnSearchAddressRequestPayloadModel(RequestModel):
    """GraphQL `searchAddress` 쿼리 변수 (웹의 `fetchAddressResultQuery`, 주소·건물 이름 검색).

    건물 이름도 찾는다 (2026-10-10 실측: 강남파이낸스센터 → 테헤란로 152, 서울대학교 → 관악로 1).
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description='주소 또는 건물 이름')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=100, description='한 번에 받을 주소 수 (서버는 100 까지 준다)')
    ] = 4
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None


class DaangnGeocodeAddressRequestPayloadModel(RequestModel):
    """GraphQL `geocodeAddress` 쿼리 변수 (웹의 `coordinateFinderQuery`, 주소 → 좌표).

    완전한 주소만 좌표로 바꾼다 (건물 이름은 null). 주소 검색(`searchAddress`) 결과의 도로명 주소를 넣는다.
    """

    query: Annotated[
        str,
        Field(min_length=1, description='주소 (예: 서울특별시 강남구 테헤란로 152)')
    ]
