"""요청 모델: 도로명 주소 검색과 주소 → 좌표 (search locations 의 주소)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.region.base import DaangnQueryInputModel

from typing import Annotated


class DaangnSearchAddressRequestPayloadModel(RequestModel):
    """GraphQL `searchAddress` 쿼리 변수 (웹 검색창 주소 모드의 `fetchAddressResultQuery`, 도로명 주소 검색).

    주소 글자(`input.query`)로 도로명·지번 주소 후보를 준다. 웹은 4곳씩 받고 '더 보기' 로 다음 쪽을 받는다 (MapShell `jo`).
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description="주소 (예: '테헤란로 152')")
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 후보 수 (웹은 4)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None


class DaangnJusoAddressInputModel(RequestModel):
    """`unitByAddress` 의 `input.jusoAddress`. 주소 검색 후보의 건물 관리 번호와 원본 도로명 주소를 그대로 보낸다 (MapShell `_s`)."""

    bd_mgt_sn: Annotated[
        str,
        Field(min_length=1, description='건물 관리 번호 (주소 검색 결과의 bdMgtSn)', alias='bdMgtSn')
    ]
    original_road_address: Annotated[
        str,
        Field(min_length=1, description='원본 도로명 주소 (주소 검색 결과의 originalRoadAddress)', alias='originalRoadAddress')
    ]


class DaangnUnitByAddressInputModel(RequestModel):
    """`unitByAddress` 의 `input`."""

    juso_address: Annotated[
        DaangnJusoAddressInputModel,
        Field(description='주소 검색 후보', alias='jusoAddress')
    ]


class DaangnUnitByAddressRequestPayloadModel(RequestModel):
    """GraphQL `unitByAddress` 쿼리 변수 (웹의 `getPlaceByJusoAddressQuery`, 주소 → 좌표·단지·건물)."""

    input: Annotated[
        DaangnUnitByAddressInputModel,
        Field(description='주소 검색 후보')
    ]
