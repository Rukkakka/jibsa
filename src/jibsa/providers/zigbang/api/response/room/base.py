"""응답 모델: 원룸·빌라·오피스텔 검색(search)·상세(detail)이 같이 쓰는 주거 상세 경로."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangAddressOriginModel,
    ZigbangLatLngModel,
    ZigbangSubwayBriefModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/{itemId}/detail (`get_listing`·`attach_building_use` 가 같이 부른다)
# ---------------------------------------------------------------------------

# 가격·단지 요약 모델은 기존 상세(`GET /v3/items/{itemId}`, detail.py)도 쓴다 (base → detail 방향으로만 가져다 쓴다)
class ZigbangDetailPriceModel(ResponseModel):
    """상세 가격 (만원)."""

    deposit: Annotated[
        int | None,
        Field(description='보증금 또는 전세금 (만원)')
    ] = None
    rent: Annotated[
        int | None,
        Field(description='월세 (만원)')
    ] = None
    sales: Annotated[
        int | None,
        Field(description='매매가 (만원)')
    ] = None


class ZigbangV3DanjiModel(ResponseModel):
    """상세 응답의 단지(오피스텔 건물) 요약. 아파트는 이 상세가 404 라 여기서 받지 않는다."""

    id: Annotated[
        int | None,
        Field(description='직방 내부 단지 ID. 오피스텔 건물 ID(item.buildingId)와 다르다')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지·건물 이름')
    ] = None


class ZigbangStructuredOptionModel(ResponseModel):
    """코드와 표시 이름을 갖는 옵션·관리비 항목."""

    name: Annotated[
        str | None,
        Field(description='표시 이름')
    ] = None
    code: Annotated[
        str | None,
        Field(description='항목 코드')
    ] = None


class ZigbangItemsDetailV1AddressModel(ResponseModel):
    """주거 상세의 주소 묶음."""

    origin: Annotated[
        ZigbangAddressOriginModel | None,
        Field(description='행정 주소', alias='addressOrigin')
    ] = None
    jibun: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddress')
    ] = None
    pnu: Annotated[
        str | None,
        Field(description='필지 ID')
    ] = None


class ZigbangItemsDetailV1ResidenceModel(ResponseModel):
    """주거 상세의 면적·층·입주·주차 정보. null 입주일의 의미는 확정하지 않는다."""

    room_type: Annotated[
        str | None,
        Field(description='방 구조', alias='roomType')
    ] = None
    bathroom_count: Annotated[
        str | None,
        Field(description='욕실 수', alias='bathroomCnt')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='방향', alias='roomDirection')
    ] = None
    direction_criterion: Annotated[
        str | None,
        Field(description='방향 기준', alias='directionCriterionType')
    ] = None
    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 코드', alias='residenceType')
    ] = None
    residence_description: Annotated[
        str | None,
        Field(description='건축물 용도 표시', alias='residenceTypeDescription')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일', alias='approveDate')
    ] = None
    parking: Annotated[
        bool | None,
        Field(description='주차 가능 여부')
    ] = None
    total_parking_count: Annotated[
        int | float | None,
        Field(description='총 주차 대수. 소수로도 온다 (상가주택 매물 50785711 은 0.4, 2026-10-20)', alias='totalParkingCnt')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='주차 비율 계산에 쓰는 매물 측 세대수. 단지 총세대수와 다를 수 있다', alias='householdCnt')
    ] = None
    elevator: Annotated[
        bool | None,
        Field(description='엘리베이터', alias='isElevator')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적', alias='sizeM2')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='해당 층')
    ] = None
    building_floor: Annotated[
        str | None,
        Field(description='전체 층수', alias='floorAll')
    ] = None
    move_in_at: Annotated[
        str | None,
        Field(description='입주 날짜. null은 기존 API로 보완', alias='moveInAt')
    ] = None
    move_in_extra: Annotated[
        str | None,
        Field(description='입주 추가 설명', alias='moveInDateExtra')
    ] = None


class ZigbangManageCostEntryModel(ResponseModel):
    """정액 관리비의 항목 하나: 일반(공용) 관리비(`normalManageCost`) 또는 사용료 항목(전기·수도·가스·난방·인터넷·TV)."""

    type: Annotated[
        str | None,
        Field(description='부과 방식 (fixed 정액, actual 실비, not_applicable 해당 없음, unknown 미제공). 일반(공용) 관리비는 fixed 다')
    ] = None
    amount: Annotated[
        float | None,
        Field(description='정액 금액 (원, type 이 fixed 일 때)')
    ] = None


class ZigbangManageCostUsageFeeModel(ResponseModel):
    """정액 관리비의 사용료 항목들. 키가 빠진 항목은 웹이 해당 없음(not_applicable)으로 본다."""

    total_amount: Annotated[
        float | None,
        Field(description='정액 사용료 합계 (원)', alias='totalAmount')
    ] = None
    electricity: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='전기')
    ] = None
    gas: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='가스')
    ] = None
    water: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='수도')
    ] = None
    heating: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='난방')
    ] = None
    internet: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='인터넷')
    ] = None
    tv: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='TV')
    ] = None


class ZigbangEtcManageCostModel(ResponseModel):
    """정액 관리비의 기타 관리비."""

    is_unknown: Annotated[
        bool | None,
        Field(description='금액을 알 수 없는지', alias='isUnknown')
    ] = None
    description: Annotated[
        str | None,
        Field(description='기타 관리비 항목 설명')
    ] = None
    amount: Annotated[
        float | None,
        Field(description='금액 (원)')
    ] = None


class ZigbangItemsDetailV1ManageCostDetailModel(ResponseModel):
    """주거 상세 관리비의 부과 방식별 내역. 웹 매물 화면은 `type` 에 따라 관리비 항목을 다르게 보여 준다.

    `FixedManageCost` 는 일반(공용) 관리비·사용료 항목(정액·실비·해당 없음·미제공)·기타 관리비로 나눠 주고,
    `ActualManageCost` 는 포함 항목 코드와 평균 관리비, `UnknownManageCost` 는 관리비를 확인할 수 없는 매물이다.
    """

    type: Annotated[
        str | None,
        Field(description='부과 방식 (FixedManageCost 정액, ActualManageCost 실비, UnknownManageCost 확인 불가)')
    ] = None
    total_amount: Annotated[
        float | None,
        Field(description='정액 관리비 합계 (원)', alias='totalAmount')
    ] = None
    has_informed: Annotated[
        bool | None,
        Field(description='항목별 내역을 알렸는지. false 면 웹은 항목별 내역 대신 포함 항목 목록을 보여 준다', alias='hasInformed')
    ] = None
    usage_fee: Annotated[
        ZigbangManageCostUsageFeeModel | None,
        Field(description='사용료 항목 (정액 관리비)', alias='usageFee')
    ] = None
    normal_manage_cost: Annotated[
        ZigbangManageCostEntryModel | None,
        Field(description='일반(공용) 관리비 (정액 관리비)', alias='normalManageCost')
    ] = None
    etc_manage_cost: Annotated[
        ZigbangEtcManageCostModel | None,
        Field(description='기타 관리비 (정액 관리비)', alias='etcManageCost')
    ] = None
    manage_cost_criteria: Annotated[
        str | None,
        Field(description='관리비 기준 코드', alias='manageCostCriteria')
    ] = None
    avg_manage_cost: Annotated[
        float | None,
        Field(description='평균 관리비 (원, 실비 관리비)', alias='avgManageCost')
    ] = None


class ZigbangItemsDetailV1ManageCostModel(ResponseModel):
    """주거 상세 관리비. amount는 만원, fee는 원이다.

    `include` 는 실비로 따로 내는 항목도 포함으로 담는다 (2026-11-15 실측: 매물 51161523 은 include 에 전기·수도·가스가
    있는데 `detail.usageFee` 는 모두 실비). 웹은 `detail` 이 정액 관리비면 항목별 내역을 보여 준다.
    """

    amount: Annotated[
        float | None,
        Field(description='관리비 (만원)')
    ] = None
    fee: Annotated[
        float | None,
        Field(description='관리비 (원)')
    ] = None
    includes: Annotated[
        list[ZigbangStructuredOptionModel],
        Field(description='포함 항목. 실비 항목도 들어 있다', alias='include')
    ] = []
    excludes: Annotated[
        list[ZigbangStructuredOptionModel],
        Field(description='별도 항목', alias='exclude')
    ] = []
    detail: Annotated[
        ZigbangItemsDetailV1ManageCostDetailModel | None,
        Field(description='부과 방식별 내역. 관리비가 없는 매물은 null')
    ] = None


class ZigbangItemsDetailV1ItemModel(ResponseModel):
    """주거 상세 본문. 사진·본문·중개사 정보는 정규화하지 않는다."""

    # id·address·residence 는 내려간 매물을 포함해 모든 유형에서 온다 (없는 매물은 200 대신 404).
    id: Annotated[
        int,
        Field(description='매물 ID')
    ]
    address: Annotated[
        ZigbangItemsDetailV1AddressModel,
        Field(description='주소 묶음')
    ]
    residence: Annotated[
        ZigbangItemsDetailV1ResidenceModel,
        Field(description='주거 정보')
    ]
    sales_type: Annotated[
        str | None,
        Field(description='거래 유형', alias='salesType')
    ] = None
    service_type: Annotated[
        str | None,
        Field(description='매물 유형', alias='serviceType')
    ] = None
    status: Annotated[
        str | None,
        Field(description='매물 상태')
    ] = None
    title: Annotated[
        str | None,
        Field(description='제목')
    ] = None
    price: Annotated[
        ZigbangDetailPriceModel | None,
        Field(description='가격 (만원)')
    ] = None
    location: Annotated[
        ZigbangLatLngModel | None,
        Field(description='좌표. 출력하지 않는다')
    ] = None
    building_id: Annotated[
        int | None,
        Field(description='오피스텔 건물 ID', alias='buildingId')
    ] = None
    manage_cost: Annotated[
        ZigbangItemsDetailV1ManageCostModel | None,
        Field(description='관리비', alias='manageCost')
    ] = None
    options: Annotated[
        list[ZigbangStructuredOptionModel],
        Field(description='옵션')
    ] = []


class ZigbangItemsDetailV1ResponseModel(ResponseModel):
    """새 주거 상세 응답."""

    item: Annotated[
        ZigbangItemsDetailV1ItemModel,
        Field(description='새 주거 상세 본문')
    ]
    subways: Annotated[
        list[ZigbangSubwayBriefModel],
        Field(description='인근 지하철역')
    ] = []
    danji: Annotated[
        ZigbangV3DanjiModel | None,
        Field(description='단지·건물 요약')
    ] = None
