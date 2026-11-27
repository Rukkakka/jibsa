"""요청 모델: 매물·단지·분양 둘레의 지하철역·버스 노선과 주변 시설 (nearby)."""
from pydantic import (
    Field,
    model_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
    LISTING_ID_PATTERN_TEXT,
)

from typing import (
    Annotated,
    Literal,
)


# 둘레 정보를 받는 대상: 매물·단지·분양. 분양은 분양 상세의 주변 정보가 같은 두 주소를 `sale` 로 부른다 (2026-11-13 실측: 김포
# 풍무역세권 B5블록 호반써밋 `sale/{id}/near` 는 편의 6·안전 2·교육 5 종류, `transit/near/sale?saleId=` 는 풍무역 476m)
DabangNearTarget = Literal['room', 'complex', 'sale']
# 카셰어링 존을 받는 대상. 분양은 403 이다 (2026-11-14 실측)
DabangCarShareTarget = Literal['room', 'complex']
# 매물 ID(24자리) 또는 단지·분양 ID(28자리)
NEAR_TARGET_ID_PATTERN: str = f'{LISTING_ID_PATTERN_TEXT}|{COMPLEX_ID_PATTERN_TEXT}'


class DabangTransitNearV5RequestParameterModel(RequestModel):
    """`GET /api/v5/transit/near/{target}` 쿼리 (매물·단지·분양 둘레 지하철역 1km·버스 노선 500m).

    쿼리 키가 대상에 따라 `roomId`·`complexId`·`saleId` 로 바뀐다 (웹 `{[`${e}Id`]: t}`, 분양은 `saleId` 만 받는다: `id`·
    `saleInLotsId` 는 400, 2026-11-13 실측).

    Args:
        target: 'room'·'complex'·'sale' (경로).
        target_id: 매물 ID, 단지 ID 또는 분양 ID.
    """

    target: Annotated[
        DabangNearTarget,
        Field(description='대상 (경로)')
    ]
    target_id: Annotated[
        str,
        Field(pattern=NEAR_TARGET_ID_PATTERN, description='매물 ID(24자리), 단지 ID 또는 분양 ID(28자리)')
    ]

    @model_serializer(mode='plain')
    def as_query(self) -> dict[str, str]:
        return {f'{self.target}Id': self.target_id}


class DabangNearV5RequestParameterModel(RequestModel):
    """`GET /api/v5/{target}/{target_id}/near` 의 경로 값 (가까운 편의·안전·교육 시설).

    Args:
        target: 'room'·'complex'·'sale'.
        target_id: 매물 ID, 단지 ID 또는 분양 ID.
    """

    target: Annotated[
        DabangNearTarget,
        Field(exclude=True, description='대상 (경로)')
    ]
    target_id: Annotated[
        str,
        Field(exclude=True, pattern=NEAR_TARGET_ID_PATTERN, description='매물 ID, 단지 ID 또는 분양 ID (경로)')
    ]


class DabangPetPlacesV5RequestParameterModel(RequestModel):
    """`GET /api/v5/pet-places` 쿼리 (단지 둘레 2km 반려동물 장소, 웹 단지 화면 '펫세권').

    웹은 단지 화면에서만 `complexId` 로 부른다 (dong-info 청크 2026-11-13). `roomId`·`saleId` 로는 빈 목록이다 (2026-11-14 실측).

    Args:
        complex_id: 단지 ID.
    """

    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID (28자리)', alias='complexId')
    ]


class DabangPublicDataCarShareZoneV5RequestParameterModel(RequestModel):
    """`GET /api/v5/public-data/{target}/car-share-zone` 쿼리 (매물·단지 둘레 2km 카셰어링 존, 웹 'Car세권').

    쿼리 키가 대상에 따라 `roomId`·`complexId` 로 바뀐다 (dong-info 청크 2026-11-13, 2026-11-13 캡처: 매물 `roomId` 하나만 간다).

    Args:
        target: 'room'·'complex' (경로).
        target_id: 매물 ID 또는 단지 ID.
    """

    target: Annotated[
        DabangCarShareTarget,
        Field(description='대상 (경로)')
    ]
    target_id: Annotated[
        str,
        Field(pattern=NEAR_TARGET_ID_PATTERN, description='매물 ID(24자리) 또는 단지 ID(28자리)')
    ]

    @model_serializer(mode='plain')
    def as_query(self) -> dict[str, str]:
        return {f'{self.target}Id': self.target_id}
