"""응답 모델: 단기임대 검색(search)·상세(detail)이 같이 쓰는 매물 요약 (by-ids)."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import ZigbangBaseResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/by-ids (검색·상세·임대인의 다른 방이 같이 쓴다)
# ---------------------------------------------------------------------------

class ZigbangStayAddressModel(ZigbangBaseResponseModel):
    """단기임대 매물 주소 (동까지)."""

    local1: Annotated[
        str | None,
        Field(description='시/도 (예: 서울시)')
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    local4: Annotated[
        str | None,
        Field(description='리')
    ] = None


class ZigbangStayDiscountModel(ZigbangBaseResponseModel):
    """단기임대 할인 조건."""

    discount_type: Annotated[
        str,
        Field(description='할인 종류 (LONG_TERM 장기 계약, INSTANT 즉시)', alias='discountType')
    ]
    condition_weeks: Annotated[
        int | None,
        Field(description='장기 할인이 붙는 최소 계약 주 수', alias='conditionWeeks')
    ] = None
    condition_days: Annotated[
        int | None,
        Field(description='즉시 할인이 붙는 조건 일 수', alias='conditionDays')
    ] = None
    discount_rate: Annotated[
        float | None,
        Field(description='할인율 (%)', alias='discountRate')
    ] = None
    discount_amount: Annotated[
        int | None,
        Field(description='할인 금액 (원)', alias='discountAmount')
    ] = None
    is_active: Annotated[
        bool | None,
        Field(description='할인 적용 중 여부', alias='isActive')
    ] = None


class ZigbangStayItemSummaryModel(ZigbangBaseResponseModel):
    """단기임대 매물 요약. 금액은 **원** 단위다."""

    id: Annotated[
        int,
        Field(description='단기임대 매물 ID')
    ]
    title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = None
    address: Annotated[
        ZigbangStayAddressModel | None,
        Field(description='주소 (동까지)')
    ] = None
    thumbnail_url: Annotated[
        str | None,
        Field(description='대표 이미지 URL', alias='thumbnailUrl')
    ] = None
    weekly_rent: Annotated[
        int | None,
        Field(description='주당 임대료 (원)', alias='weeklyRent')
    ] = None
    weekly_manage_cost: Annotated[
        int | None,
        Field(description='주당 관리비 (원)', alias='weeklyManageCost')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='방 종류 (OFFICETEL, APARTMENT, VILLA ...)', alias='buildingType')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCount')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathroomCount')
    ] = None
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='sizeM2')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='해당 층')
    ] = None
    discounts: Annotated[
        list[ZigbangStayDiscountModel],
        Field(description='할인 조건')
    ] = []
    lat: Annotated[
        float | None,
        Field(description='위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='경도')
    ] = None
    reviewed_at: Annotated[
        str | None,
        Field(description='검수 완료(노출 시작) 일시 (UTC ISO 8601)', alias='reviewedAt')
    ] = None


class ZigbangGuestItemsByIdsResponseModel(ZigbangBaseResponseModel):
    """단기임대 매물 요약 배치 응답. 내려간 매물은 빠진다."""

    items: Annotated[
        list[ZigbangStayItemSummaryModel],
        Field(description='매물 요약')
    ] = []
