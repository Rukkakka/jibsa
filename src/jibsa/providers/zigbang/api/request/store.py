"""요청 모델: 상가·사무실 매물 검색과 상세 (search listings store, listing store-*)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


# 상가 거래 유형. 모르는 값을 보내면 에러 없이 전체를 돌려주므로 여기서 막는다.
ZigbangStoreSalesType = Literal['전체', '임대', '매매']


class ZigbangStoreBusinessModel(RequestModel):
    """상가 업종 조건 하나. 대분류(`category`) 안에서 고른 업종들."""

    category: Annotated[
        str,
        Field(min_length=1, description='업종 대분류 (예: 휴게음식점)')
    ]
    businesses: Annotated[
        list[str],
        Field(min_length=1, description='고른 업종 (예: 카페/커피)')
    ] = Field(alias='업종')
    is_activated: Annotated[
        bool,
        Field(description='조건 사용 여부. 웹은 늘 true 로 보낸다')
    ] = Field(default=True, alias='isActivated')


class ZigbangStoreArticleStoresV2RequestPayloadModel(RequestModel):
    """`POST /v2/store/article/stores` 본문. geohash 칸 안의 상가 위치.

    `업종` 은 비어 있어도 반드시 보내야 한다 (빠지면 400 "Type validation failed.").
    면적은 ㎡ 이고 `area_max_m2` 는 미만(<)이다.
    """

    geohash: Annotated[
        str,
        Field(
            pattern=r'^[0-9bcdefghjkmnpqrstuvwxyz]{4,7}$',
            description='지도 타일 geohash'
        )
    ]
    domain: Annotated[
        Literal['zigbang'],
        Field(description='서비스 도메인. 고정값')
    ] = 'zigbang'
    shuffle: Annotated[
        bool,
        Field(description='결과 순서를 섞을지. 웹은 false')
    ] = False
    sales_type: Annotated[
        ZigbangStoreSalesType,
        Field(description='거래 유형 (전체, 임대, 매매)')
    ] = '전체'
    first_floor: Annotated[
        bool,
        Field(description='1층 매물만')
    ] = False
    businesses: Annotated[
        list[ZigbangStoreBusinessModel],
        Field(description='업종 조건. 비우면 전체')
    ] = Field(default=[], alias='업종')
    area_min_m2: Annotated[
        float | None,
        Field(ge=0, description='면적 하한 (㎡, 이상)')
    ] = Field(default=None, alias='면적_gteq')
    area_max_m2: Annotated[
        float | None,
        Field(gt=0, description='면적 상한 (㎡, 미만)')
    ] = Field(default=None, alias='면적_lt')


class ZigbangStoreArticleStoresListV2RequestPayloadModel(RequestModel):
    """`POST /v2/store/article/stores/list` 본문. 상가 요약을 ID 로 받는다."""

    item_ids: Annotated[
        list[int],
        Field(min_length=1, max_length=60, description='요약을 받을 상가 매물 ID 목록')
    ]


class ZigbangStoreArticleStoreV2RequestParameterModel(RequestModel):
    """`GET /v2/store/article/stores/{itemId}` 경로."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='상가 매물 ID. 경로에 들어간다')
    ]
