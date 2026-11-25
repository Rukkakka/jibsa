"""아파트 단지 기능(complex)의 상세·시세 추이가 같이 쓰는 것: 직방이 단지끼리 이어 주는 관련 단지."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    join_address,
    normalize_address,
)
from jibsa.providers.zigbang.api.response.common import ZigbangRelatedDanjiModel
from jibsa.providers.zigbang.service.common.base import (
    apt_complex_id,
    household_count,
)

from typing import Annotated


class ZigbangRelatedComplex(BaseModel):
    """직방이 단지끼리 이어 주는 단지 하나: 웹 단지 화면의 '함께 보면 좋은 단지', 직방시세 그래프 '단지 비교하기' 의 후보 ('단지 선택' 창)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (zigbang complex·search listings --complex 에 넘긴다). 직방이 ID 를 주지 않으면 모름(null)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ]
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ]


def related_complex_of(item: ZigbangRelatedDanjiModel) -> ZigbangRelatedComplex:
    """직방의 관련 단지 하나를 결과 한 줄로. 세대수 문구('6,864세대')는 정수로, 시·군·구·동은 빈 값 없이 이어 주소로 낸다."""
    return ZigbangRelatedComplex(
        complex_id=apt_complex_id(item.id) if item.id is not None else None,
        name=item.name,
        household_count=household_count(item.household),
        address=normalize_address(join_address(item.local1, item.local2, item.local3)),
    )
