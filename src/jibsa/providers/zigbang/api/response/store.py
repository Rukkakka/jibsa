"""응답 모델: 상가·사무실 매물 검색과 상세 (search listings store, listing store-*)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import ZigbangSubwayBriefModel

from typing import Annotated


# ---------------------------------------------------------------------------
# POST /v2/store/article/stores
# ---------------------------------------------------------------------------

class ZigbangStoreLocationModel(ResponseModel):
    """상가 위치 핀."""

    item_id: Annotated[
        int,
        Field(description='상가 매물 ID')
    ]
    lat: Annotated[
        float,
        Field(description='위도')
    ]
    lng: Annotated[
        float,
        Field(description='경도')
    ]


class ZigbangStoreSectionModel(ResponseModel):
    """상가 위치 묶음.

    '이 지역 상가' 는 조건에 맞는 상가, '이 지역 비어있는 상가' 는 업종 조건을 걸었을 때
    그 업종과 무관하게 함께 오는 공실이다. 업종 조건이 없으면 공실도 '이 지역 상가' 에 들어 있다.
    """

    title: Annotated[
        str,
        Field(description="묶음 이름 ('이 지역 상가', '이 지역 비어있는 상가')")
    ]
    item_locations: Annotated[
        list[ZigbangStoreLocationModel],
        Field(description='상가 위치')
    ] = []


class ZigbangStoreArticleStoresV2ResponseModel(ResponseModel):
    """상가 위치 응답. 최상위가 배열이라 `sections` 로 감싸 검증한다."""

    sections: Annotated[
        list[ZigbangStoreSectionModel],
        Field(description='위치 묶음')
    ] = []


# ---------------------------------------------------------------------------
# POST /v2/store/article/stores/list, GET /v2/store/article/stores/{itemId}
# ---------------------------------------------------------------------------

class ZigbangStoreSummaryModel(ResponseModel):
    """상가 요약 한 건. 금액은 모두 **만원** 이다."""

    item_id: Annotated[
        int,
        Field(description='상가 매물 ID')
    ]
    service_type: Annotated[
        str | None,
        Field(description='서비스 (상가)')
    ] = None
    sales_type: Annotated[
        str,
        Field(description='거래 유형 (임대, 매매)')
    ]
    sales_title: Annotated[
        str | None,
        Field(description='표시용 거래 이름 (월세, 전세, 매매)')
    ] = None
    title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = None
    business: Annotated[
        str | None,
        Field(description='업종 (현재·직전 업종, 공실이면 기타)')
    ] = Field(default=None, alias='업종')
    key_money: Annotated[
        int | None,
        Field(description='권리금 (만원)')
    ] = Field(default=None, alias='권리금액')
    sales_price: Annotated[
        int | None,
        Field(description='매매가 (만원). 임대는 0')
    ] = Field(default=None, alias='매매금액')
    deposit: Annotated[
        int | None,
        Field(description='보증금 (만원)')
    ] = Field(default=None, alias='보증금액')
    rent: Annotated[
        int | None,
        Field(description='월세 (만원)')
    ] = Field(default=None, alias='월세금액')
    manage_cost: Annotated[
        int | None,
        Field(description='월 관리비 (만원)')
    ] = Field(default=None, alias='관리금액')
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="해당 층 (예: '4층', '지하1층')")
    ] = None
    local1: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    image_thumbnail: Annotated[
        str | None,
        Field(description='대표 이미지 URL')
    ] = None
    status: Annotated[
        str | None,
        Field(description="매물 상태 ('open' 이면 거래 가능)")
    ] = None


class ZigbangStoreDetailModel(ZigbangStoreSummaryModel):
    """상가 상세. 요약 필드에 시설 정보가 더해진다."""

    section_type: Annotated[
        str | None,
        Field(description='구분 (예: 공실)')
    ] = None
    recommended_business: Annotated[
        str | None,
        Field(description='추천 업종')
    ] = Field(default=None, alias='추천업종')
    lease_unit: Annotated[
        str | None,
        Field(description='임대 구분 (예: 개별호, 통임대)')
    ] = Field(default=None, alias='임대구분')
    interior: Annotated[
        str | None,
        Field(description='인테리어 유무')
    ] = None
    floor_all: Annotated[
        str | None,
        Field(description='건물 전체 층수 (예: 4층)')
    ] = None
    lat: Annotated[
        float | None,
        Field(description='위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='경도')
    ] = None
    elevator: Annotated[
        str | None,
        Field(description='엘리베이터 (있음, 없음)')
    ] = None
    parking: Annotated[
        str | None,
        Field(description='주차 (예: 가능 - 자주식 6대)')
    ] = None
    toilet: Annotated[
        str | None,
        Field(description='화장실 (예: 내부(남녀혼용))')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 종류')
    ] = Field(default=None, alias='난방종류')
    description: Annotated[
        str | None,
        Field(description='중개사가 쓴 상세 설명')
    ] = None
    images: Annotated[
        list[str],
        Field(description='사진 URL')
    ] = []
    phone: Annotated[
        str | None,
        Field(repr=False, description='중개사 연락처')
    ] = None


class ZigbangStoreArticleStoresListV2ResponseModel(ResponseModel):
    """상가 요약 배치 응답. 최상위가 배열이라 `items` 로 감싸 검증한다."""

    items: Annotated[
        list[ZigbangStoreSummaryModel],
        Field(description='상가 요약')
    ] = []


class ZigbangStoreArticleStoreV2ResponseModel(ResponseModel):
    """상가 상세 응답."""

    item: Annotated[
        ZigbangStoreDetailModel,
        Field(description='상가 상세')
    ]
    subways: Annotated[
        list[ZigbangSubwayBriefModel],
        Field(description='인근 지하철역')
    ] = []
