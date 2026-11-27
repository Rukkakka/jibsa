"""요청 모델: 지역 이름 검색과 좌표로 지역 찾기 (search locations, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel
from jibsa.providers.daangn.api.request.region.base import DaangnQueryInputModel

from typing import Annotated


class DaangnGetRegionByCoordinateRequestPayloadModel(RequestModel):
    """GraphQL `getRegionByCoordinate` 쿼리 변수 (웹의 `regionByCoordinateQuery`)."""

    coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='찾을 좌표')
    ]


class DaangnSearchRegionRequestPayloadModel(RequestModel):
    """GraphQL `searchRegion` 쿼리 변수 (웹 지도 검색창의 `fetchRegionResultQuery`, 지역 이름 검색).

    법정동·구·시·도를 지역 중심 좌표와 함께 준다 ('서울' → 서울특별시, 그 구들, 동들 순). 행정동은 주지 않는다
    (2026-11-11 실측: 역삼1동 0건). 이름이 비슷한 곳도 섞여 와서(이도이동 → 외도이동·이호이동) 이름이 같은지는 부르는 쪽이 본다.
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description='지역 이름 (예: 역삼동, 강남구, 서울)')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=100, description='한 번에 받을 지역 수. 웹 검색창은 4곳씩 받고, 서버는 100 까지 준다 (2026-11-11 실측)')
    ] = 100
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
