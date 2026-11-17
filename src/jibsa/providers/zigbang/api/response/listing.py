"""응답 모델: 원룸·빌라·오피스텔 매물 검색과 매물 상세·아파트 매물 묶음 (search listings room, listing, catalog)."""

from pydantic import (
    Field,
    field_validator,
)

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangAddressOriginModel,
    ZigbangItemPinModel,
    ZigbangItemSectionModel,
    ZigbangLatLngModel,
    ZigbangSubwayBriefModel,
)

from typing import (
    Annotated,
    Any,
)


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/{onerooms|officetels|villas}
# ---------------------------------------------------------------------------

class ZigbangSubwayLineModel(ResponseModel):
    """지하철 노선."""

    name: Annotated[
        str,
        Field(description='노선명 (예: 2호선)')
    ]
    code: Annotated[
        str | None,
        Field(description='노선 코드')
    ] = None


class ZigbangSubwayModel(ResponseModel):
    """타일 안의 지하철역."""

    id: Annotated[
        int,
        Field(description='역 ID')
    ]
    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    location: Annotated[
        ZigbangLatLngModel | None,
        Field(description='역 좌표')
    ] = None
    lines: Annotated[
        list[ZigbangSubwayLineModel],
        Field(description='지나는 노선')
    ] = []


class ZigbangItemsResponseModel(ResponseModel):
    """geohash 타일 매물 목록 응답 (원룸·오피스텔·빌라 공통)."""

    items: Annotated[
        list[ZigbangItemPinModel],
        Field(description='타일 안의 모든 매물 핀')
    ] = []
    sections: Annotated[
        list[ZigbangItemSectionModel],
        Field(description='노출 구역별 매물 ID')
    ] = []
    subways: Annotated[
        list[ZigbangSubwayModel],
        Field(description='타일 안의 지하철역')
    ] = []


class ZigbangItemsOneroomsV1ResponseModel(ZigbangItemsResponseModel):
    """원룸 목록 응답."""


class ZigbangItemsOfficetelsV1ResponseModel(ZigbangItemsResponseModel):
    """오피스텔 목록 응답."""


class ZigbangItemsVillasV1ResponseModel(ZigbangItemsResponseModel):
    """빌라 목록 응답."""


class ZigbangItemsSubwaysOneroomsV1ResponseModel(ZigbangItemsResponseModel):
    """역 반경 안 원룸 매물 핀. 지도 목록과 같은 응답 모양이다."""


class ZigbangItemsSubwaysOfficetelsV1ResponseModel(ZigbangItemsResponseModel):
    """역 반경 안 오피스텔 매물 핀. 지도 목록과 같은 응답 모양이다."""


class ZigbangItemsSubwaysVillasV1ResponseModel(ZigbangItemsResponseModel):
    """역 반경 안 빌라 매물 핀. 지도 목록과 같은 응답 모양이다."""


# ---------------------------------------------------------------------------
# GET /v3/items/{itemId}
# ---------------------------------------------------------------------------

class ZigbangAgentModel(ResponseModel):
    """매물을 올린 중개사무소 요약."""

    agent_title: Annotated[
        str | None,
        Field(description='중개사무소명', alias='agentTitle')
    ] = None
    agent_name: Annotated[
        str | None,
        Field(description='대표 중개사 이름', alias='agentName')
    ] = None
    agent_address: Annotated[
        str | None,
        Field(description='사무소 주소', alias='agentAddress')
    ] = None
    agent_phone: Annotated[
        str | None,
        Field(description='사무소 전화번호', alias='agentPhone')
    ] = None
    agent_user_type: Annotated[
        str | None,
        Field(description='중개사 구분 (예: 대표공인중개사)', alias='agentUserType')
    ] = None


class ZigbangRealtorModel(ResponseModel):
    """중개사 상세."""

    office_title: Annotated[
        str | None,
        Field(description='중개사무소명', alias='officeTitle')
    ] = None
    office_phone: Annotated[
        str | None,
        Field(description='사무소 전화번호', alias='officePhone')
    ] = None
    office_reg_number: Annotated[
        str | None,
        Field(description='중개사무소 등록번호', alias='officeRegNumber')
    ] = None
    office_address: Annotated[
        str | None,
        Field(description='사무소 주소', alias='officeAddress')
    ] = None
    status: Annotated[
        str | None,
        Field(description='중개사 계정 상태')
    ] = None


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


class ZigbangDetailFloorModel(ResponseModel):
    """층 정보."""

    floor: Annotated[
        str | None,
        Field(description='해당 층')
    ] = None
    all_floors: Annotated[
        str | None,
        Field(description='건물 전체 층수', alias='allFloors')
    ] = None


class ZigbangDetailAreaModel(ResponseModel):
    """상세 면적."""

    exclusive_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='전용면적M2')
    ] = None
    land_m2: Annotated[
        float | None,
        Field(description='대지권면적 (㎡)', alias='대지권면적M2')
    ] = None


class ZigbangManageCostModel(ResponseModel):
    """관리비."""

    amount: Annotated[
        float | None,
        Field(description='월 관리비 (**만원**). 목록 응답의 manage_cost(원) 와 단위가 다르다')
    ] = None
    includes: Annotated[
        list[str],
        Field(description='관리비 포함 항목')
    ] = []
    not_includes: Annotated[
        list[str],
        Field(description='관리비 별도 항목', alias='notIncludes')
    ] = []


class ZigbangItemDetailModel(ResponseModel):
    """매물 상세 본문."""

    item_id: Annotated[
        int,
        Field(description='매물 ID', alias='itemId')
    ]
    sales_type: Annotated[
        str,
        Field(description='거래 유형 (전세, 월세, 매매)', alias='salesType')
    ]
    service_type: Annotated[
        str,
        Field(description='매물 유형 (원룸, 오피스텔, 빌라)', alias='serviceType')
    ]
    title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = None
    description: Annotated[
        str | None,
        Field(description='중개사가 쓴 상세 설명')
    ] = None
    price: Annotated[
        ZigbangDetailPriceModel | None,
        Field(description='가격 (만원)')
    ] = None
    area: Annotated[
        ZigbangDetailAreaModel | None,
        Field(description='면적')
    ] = None
    floor: Annotated[
        ZigbangDetailFloorModel | None,
        Field(description='층')
    ] = None
    room_type: Annotated[
        str | None,
        Field(description='방 구조 (예: 오픈형원룸, 투룸)', alias='roomType')
    ] = None
    manage_cost: Annotated[
        ZigbangManageCostModel | None,
        Field(description='관리비', alias='manageCost')
    ] = None
    options: Annotated[
        list[str],
        Field(description='옵션 (에어컨, 세탁기 ...)')
    ] = []
    images: Annotated[
        list[str],
        Field(description='사진 URL')
    ] = []
    image_thumbnail: Annotated[
        str | None,
        Field(description='대표 이미지 URL', alias='imageThumbnail')
    ] = None
    location: Annotated[
        ZigbangLatLngModel | None,
        Field(description='좌표')
    ] = None
    address_origin: Annotated[
        ZigbangAddressOriginModel | None,
        Field(description='행정 주소', alias='addressOrigin')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소 (구 동 번지)', alias='jibunAddress')
    ] = None
    bjd_code: Annotated[
        str | None,
        Field(description='법정동코드', alias='bjdCode')
    ] = None
    pnu: Annotated[
        str | None,
        Field(description='필지 고유번호 (19자리). 원룸·빌라·오피스텔 학군 조회(/bls/{pnu}/school_zones)에 쓴다')
    ] = None
    parking_available_text: Annotated[
        str | None,
        Field(description='주차 가능 여부 설명', alias='parkingAvailableText')
    ] = None
    elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 유무')
    ] = None
    room_direction: Annotated[
        str | None,
        Field(description='방향 (N, S, E, W, SE ...)', alias='roomDirection')
    ] = None
    movein_date: Annotated[
        str | None,
        Field(description='입주 가능일', alias='moveinDate')
    ] = None
    approve_date: Annotated[
        str | None,
        Field(description='사용승인일', alias='approveDate')
    ] = None
    bathroom_count: Annotated[
        str | None,
        Field(description='욕실 수', alias='bathroomCount')
    ] = None
    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (예: 단독주택, 다세대주택)', alias='residenceType')
    ] = None
    building_id: Annotated[
        int | None,
        Field(description='오피스텔 건물 ID (오피스텔만). /items/officetels/{buildingId} 에 넘긴다', alias='buildingId')
    ] = None
    updated_at: Annotated[
        str | None,
        Field(description='수정 일시 (KST, YYYY-MM-DD HH:MM:SS)', alias='updatedAt')
    ] = None
    status: Annotated[
        str | None,
        Field(description='매물 상태 (open ...)')
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


class ZigbangItemsV3ResponseModel(ResponseModel):
    """매물 풀 상세 응답."""

    item: Annotated[
        ZigbangItemDetailModel,
        Field(description='매물 상세')
    ]
    agent: Annotated[
        ZigbangAgentModel | None,
        Field(description='중개사무소 요약')
    ] = None
    realtor: Annotated[
        ZigbangRealtorModel | None,
        Field(description='중개사 상세')
    ] = None
    subways: Annotated[
        list[ZigbangSubwayBriefModel],
        Field(description='인근 지하철역')
    ] = []
    danji: Annotated[
        ZigbangV3DanjiModel | None,
        Field(description='단지·건물 요약 (오피스텔만)')
    ] = None


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/{itemId}/detail
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# GET /apt/item-catalogs/items/{itemId}
# ---------------------------------------------------------------------------

class ZigbangAptManageCostAmountModel(ResponseModel):
    """아파트 관리비 금액과 항목."""

    monthly_cost: Annotated[
        int | None,
        Field(description='월 관리비 (**원**)', alias='monthlyCost')
    ] = None
    include_items: Annotated[
        list[str] | None,
        Field(description='관리비 포함 항목', alias='includeItems')
    ] = None
    exclude_items: Annotated[
        list[str] | None,
        Field(description='관리비 별도 항목', alias='excludeItems')
    ] = None


class ZigbangAptManageCostModel(ResponseModel):
    """아파트 관리비. `type` 에 따라 금액이 `fixedManageCost` 나 `etcManageCost` 에 온다."""

    type: Annotated[
        str | None,
        Field(description='관리비 종류 (fixed 정액, etc 기타, unconfirmed 확인 불가)')
    ] = None
    fixed_manage_cost: Annotated[
        ZigbangAptManageCostAmountModel | None,
        Field(description='정액 관리비 (type 이 fixed 일 때)', alias='fixedManageCost')
    ] = None
    etc_manage_cost: Annotated[
        ZigbangAptManageCostAmountModel | None,
        Field(description='기타 관리비 (type 이 etc 일 때)', alias='etcManageCost')
    ] = None

    @property
    def amount(self) -> ZigbangAptManageCostAmountModel | None:
        """`type` 에 맞는 관리비. 확인 불가거나 모르는 종류면 None."""
        if self.type == 'fixed':
            return self.fixed_manage_cost
        if self.type == 'etc':
            return self.etc_manage_cost
        return None


class ZigbangAptItemModel(ResponseModel):
    """아파트 매물 상세 본문 (직방·제휴 매물).

    웹 아파트 매물 화면이 부르는 유일한 상세다 (주거 상세·`/v3/items` 는 아파트에 404). 직방 매물의 층은
    '저'·'중'·'고' 로만 오고 웹 화면에도 정확한 층이 없다. 상태·등록일·인근 역·엘리베이터·건축물 용도·세대수 필드는 없다.
    """

    item_source: Annotated[
        str | None,
        Field(description='매물 출처 (zigbang, coalition 제휴)', alias='itemSource')
    ] = None
    item_id: Annotated[
        int,
        Field(description='매물 ID', alias='itemId')
    ]
    item_type: Annotated[
        str | None,
        Field(description='매물 종류 (offer 신규분양, partner 집주인이 내놓음, self_ad 중개사무소가 등록)', alias='itemType')
    ] = None
    area_danji_id: Annotated[
        int | None,
        Field(description='단지 ID', alias='areaDanjiId')
    ] = None
    area_danji_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='areaDanjiName')
    ] = None
    area_building_name: Annotated[
        str | None,
        Field(description='동 (예: 154동)', alias='areaBuildingName')
    ] = None
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD)', alias='approvalDate')
    ] = None
    tran_type: Annotated[
        str | None,
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세)', alias='tranType')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='매매가(매매) 또는 보증금·전세금 (만원)')
    ] = None
    rent: Annotated[
        int | None,
        Field(description='월세 (만원). 매매·전세는 0')
    ] = None
    item_title: Annotated[
        str | None,
        Field(description='매물 제목', alias='itemTitle')
    ] = None
    old_address: Annotated[
        str | None,
        Field(description='지번 주소 (예: 경기도 성남시 분당구 삼평동 705). 직방 매물은 빈 문자열로 온다', alias='oldAddress')
    ] = None
    address: Annotated[
        str | None,
        Field(description="도로명 주소 (예: '서울시 송파구 송파대로 345'). 웹 아파트 매물 화면이 보여 주는 주소다")
    ] = None
    building_floor: Annotated[
        int | None,
        Field(description='건물 층수', alias='buildingFloor')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='방향 (소문자 e, sw ...)')
    ] = None
    direction_base: Annotated[
        str | None,
        Field(description="방향 기준 (예: '거실기준')", alias='directionBase')
    ] = None
    movein_date: Annotated[
        str | None,
        Field(description='입주 가능일 (예: 즉시입주가능, 2026.11.30(협의가능))', alias='moveinDate')
    ] = None
    parking_count: Annotated[
        int | float | None,
        Field(description='단지 전체 주차 대수', alias='parkingCount')
    ] = None
    parking_count_by_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수', alias='parkingCountByHousehold')
    ] = None
    domain: Annotated[
        str | None,
        Field(description='제휴 매물의 원 서비스 (hogangnono)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCount')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathroomCount')
    ] = None
    size_contract_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)', alias='sizeContractM2')
    ] = None
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='sizeM2')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층. 직방 매물은 '저'·'중'·'고' (정확한 층은 주지 않는다), 제휴 매물은 숫자")
    ] = None
    manage_cost: Annotated[
        ZigbangAptManageCostModel | None,
        Field(description='관리비', alias='manageCost')
    ] = None


class ZigbangItemCatalogsItemsResponseModel(ResponseModel):
    """아파트 매물 상세 응답."""

    item: Annotated[
        ZigbangAptItemModel,
        Field(description='매물 상세')
    ]


# ---------------------------------------------------------------------------
# GET /apt/item-catalogs/{areaHoId}
# ---------------------------------------------------------------------------

class ZigbangItemCatalogsResponseModel(ResponseModel):
    """같은 호·거래 유형의 아파트 매물 묶음 한 쪽 (웹 묶음 화면). 매물마다 아파트 상세(`/apt/item-catalogs/items`)와 같은 꼴이다.

    이 밖에 묶음의 가격 범위(`depositMin`·`depositMax`·`rentMin`·`rentMax`)와 근처 중개사무소(`acceptedLocalAgents`, 이름·대표자·주소)가
    오지만 쓰지 않는다 (가격은 매물마다 있고, 중개사 정보는 내보내지 않는다).
    """

    area_ho_id: Annotated[
        int | None,
        Field(description='호 ID', alias='areaHoId')
    ] = None
    item_count: Annotated[
        int | None,
        Field(description='묶음의 매물 수 (쪽과 상관없는 전체). 주지 않으면 모름', alias='itemCount')
    ] = None
    items: Annotated[
        list[ZigbangAptItemModel],
        Field(description='이 쪽의 매물 (서버 순서 그대로 웹이 보여 준다). null 이면 빈 목록')
    ] = []

    @field_validator('items', mode='before')
    @classmethod
    def null_items_as_empty(cls, value: Any) -> Any:
        """null 은 빈 쪽으로 받는다. 매물이 없다는 모양이라 응답 형식 오류(PARSE_ERROR)로 끝내지 않는다."""
        return [] if value is None else value


# ---------------------------------------------------------------------------
# GET /house/property/v1/bls/{pnu}/school_zones
# ---------------------------------------------------------------------------

class ZigbangBlSchoolModel(ResponseModel):
    """건물 주변 학교 하나."""

    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    distance: Annotated[
        int | None,
        Field(description='건물에서 거리 (m)')
    ] = None


class ZigbangBlSchoolZoneModel(ResponseModel):
    """통학구역·학교군."""

    zone_name: Annotated[
        str | None,
        Field(description='통학구역(초등) 또는 학교군(중·고) 이름', alias='zoneName')
    ] = None


class ZigbangBlSchoolLevelModel(ResponseModel):
    """학교급(초·중·고) 하나의 학구·학교군과 학교."""

    school_zone: Annotated[
        ZigbangBlSchoolZoneModel | None,
        Field(description='통학구역·학교군', alias='schoolZone')
    ] = None
    schools: Annotated[
        list[ZigbangBlSchoolModel],
        Field(description='통학구역·학교군 안의 학교')
    ] = []


class ZigbangBlsSchoolZonesV1ResponseModel(ResponseModel):
    """원룸·빌라·오피스텔 건물(필지)의 학군. 학구 밖 주변 학교(nearbySchools)는 읽지 않는다."""

    elementary: Annotated[
        ZigbangBlSchoolLevelModel | None,
        Field(description='초등학교 (통학구역)')
    ] = None
    middle: Annotated[
        ZigbangBlSchoolLevelModel | None,
        Field(description='중학교 (학교군)')
    ] = None
    high: Annotated[
        ZigbangBlSchoolLevelModel | None,
        Field(description='고등학교 (학교군)')
    ] = None
