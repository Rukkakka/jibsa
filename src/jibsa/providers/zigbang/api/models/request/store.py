"""요청 모델: 상가·사무실 매물 검색과 상세 (search listings store, listing store-*)."""


from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
    Self,
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
        Field(min_length=1, description='고른 업종 (예: 카페/커피)', alias='업종')
    ]
    is_activated: Annotated[
        bool,
        Field(description='조건 사용 여부. 웹은 늘 true 로 보낸다', alias='isActivated')
    ] = True


class ZigbangStoreCircleModel(RequestModel):
    """상가 검색 범위인 원 하나 (`상권`). 웹 상가 검색창은 역·동을 고르면 그 좌표에 반경 1000m 원을 보낸다."""

    lat: Annotated[
        float,
        Field(ge=-90, le=90, description='원 중심 위도')
    ]
    lng: Annotated[
        float,
        Field(ge=-180, le=180, description='원 중심 경도')
    ]
    radius: Annotated[
        int,
        Field(gt=0, description='반경 (미터)')
    ]


class ZigbangStoreArticleStoresV2RequestPayloadModel(RequestModel):
    """`POST /v2/store/article/stores` 본문. 범위(`상권` 원 또는 `지역` 법정동 코드) 안의 상가 위치.

    범위는 `상권`·`지역` 중 정확히 하나를 준다. 서버는 범위 안 매물만 준다 (2026-11-15 실측: 역삼역 반경 100m 2건·5000m
    12,385건, 가장 먼 매물이 반경 안). `지역` 에 모르는 코드(리 코드, 5자리 시·군·구 코드)를 주면 에러 없이 전국 매물을
    준다 (2026-11-15 실측: 57,782건). 그래서 10자리 코드만 받고, 리 코드는 부르는 쪽이 그 위 읍·면 코드로 바꿔 보낸다.
    `업종` 은 비어 있어도 반드시 보내야 한다 (빠지면 400 "Type validation failed.").
    면적은 ㎡ 이고 `area_max_m2` 는 미만(<)이다.
    """

    circles: Annotated[
        list[ZigbangStoreCircleModel] | None,
        Field(min_length=1, description='검색할 원 목록. 웹은 원 하나(반경 1000m)를 보낸다', alias='상권')
    ] = None
    region_codes: Annotated[
        list[Annotated[str, Field(pattern=r'^\d{10}$')]] | None,
        Field(min_length=1, description='검색할 법정동 코드(10자리) 목록. 웹은 업종으로 찾기 화면이 주소 검색 결과의 코드를 보낸다 (2026-11-17 번들)', alias='지역')
    ] = None
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
        Field(description='업종 조건. 비우면 전체', alias='업종')
    ] = []
    area_min_m2: Annotated[
        float | None,
        Field(ge=0, description='면적 하한 (㎡, 이상)', alias='면적_gteq')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(gt=0, description='면적 상한 (㎡, 미만)', alias='면적_lt')
    ] = None

    @model_validator(mode='after')
    def one_scope(self) -> Self:
        if (self.circles is None) == (self.region_codes is None):
            raise ValueError('상권(원)과 지역(법정동 코드) 중 정확히 하나를 주어야 합니다')
        return self


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
