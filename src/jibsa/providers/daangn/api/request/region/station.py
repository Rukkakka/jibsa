"""요청 모델: 역 이름 검색 (search locations 의 역)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.region.base import DaangnQueryInputModel

from typing import Annotated


class DaangnSearchSubwayStationPoisRequestPayloadModel(RequestModel):
    """GraphQL `searchSubwayStationPois` 쿼리 변수 (웹의 `fetchSubwayResultQuery`, 역 이름 검색).

    앞부분이 같은 역을 모두 준다 ('강남' → 강남, 강남구청, 강남대). 역 이름에는 '역' 이 붙지 않는다.
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description='역 이름 (예: 역삼역, 역삼)')
    ]
