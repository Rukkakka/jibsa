"""요청 모델: 아파트 매물 상세 (listing), 매물 묶음과 호 정보 (catalog)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.models.request.common import (
    ZigbangAptItemSource,
    ZigbangAptTranType,
)

from typing import (
    Annotated,
    Literal,
)


class ZigbangItemCatalogsItemsRequestParameterModel(RequestModel):
    """`GET /apt/item-catalogs/items/{itemId}` 경로 + 쿼리. 아파트 매물 상세."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='매물 ID. 경로에 들어가며 쿼리로는 보내지 않는다')
    ]
    item_source: Annotated[
        ZigbangAptItemSource,
        Field(description="매물 출처. 직방 매물은 'zigbang', 제휴 매물은 'coalition'. 서버가 필수로 요구한다", alias='itemSource')
    ] = 'zigbang'


class ZigbangItemCatalogsRequestParameterModel(RequestModel):
    """`GET /apt/item-catalogs/{areaHoId}` 경로 + 쿼리. 같은 호·거래 유형을 올린 아파트 매물 묶음 (웹 묶음 화면)."""

    area_ho_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='호 ID (목록 카탈로그의 areaHoId). 경로에 들어가며 쿼리로는 보내지 않는다')
    ]
    tran_type: Annotated[
        ZigbangAptTranType,
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세). 서버가 필수로 요구한다', alias='tranType')
    ]
    offset: Annotated[
        int,
        Field(ge=0, description='건너뛸 매물 수')
    ] = 0
    limit: Annotated[
        int,
        Field(ge=1, description='쪽 크기. 웹 묶음 화면은 20건씩 받는다')
    ] = 20
    first_item_source: Annotated[
        Literal['coalition'],
        Field(
            description='맨 앞에 둘 매물의 출처. 웹이 firstItemId 없이도 늘 보내는 기본값이고, 매물 ID 를 함께 주지 않으면 순서가 '
            '바뀌지 않는다 (2026-11-15 실측)',
            alias='firstItemSource'
        )
    ] = 'coalition'


class ZigbangItemCatalogsHoInfoRequestParameterModel(RequestModel):
    """`GET /apt/item-catalogs/{areaHoId}/ho-info` 경로. 아파트 매물 묶음의 호 정보 (직방 시세·공시가격·분양가)."""

    area_ho_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='호 ID (목록 카탈로그의 areaHoId). 경로에 들어간다')
    ]
