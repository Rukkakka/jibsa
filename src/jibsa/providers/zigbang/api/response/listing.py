"""응답 모델: 원룸·빌라·오피스텔 매물 검색과 주거 매물 상세 (search listings room, listing)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangAddressOriginModel,
    ZigbangItemPinModel,
    ZigbangLatLngModel,
    ZigbangSubwayBriefModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/{onerooms|officetels|villas}
# ---------------------------------------------------------------------------

class ZigbangItemSectionModel(ResponseModel):
    """노출 구역별 매물 ID 묶음."""

    type: Annotated[
        str,
        Field(description='구역 종류 (VIP, PREMIUM_RECOMMEND, PREMIUM, RECOMMEND, NORMAL)')
    ]
    ids: Annotated[
        list[int],
        Field(description='해당 구역의 매물 ID')
    ] = []


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
    """상세 응답의 단지(오피스텔 건물) 요약. 아파트 매물이면 null 이다."""

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


class ZigbangItemsDetailV1ManageCostModel(ResponseModel):
    """주거 상세 관리비. amount는 만원, fee는 원이다."""

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
        Field(description='포함 항목', alias='include')
    ] = []
    excludes: Annotated[
        list[ZigbangStructuredOptionModel],
        Field(description='별도 항목', alias='exclude')
    ] = []


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
    """아파트 매물 상세 본문.

    `/v3/items` 가 아파트에 대해 주지 않는 단지 이름·방 수·욕실 수·사용승인일·공급면적과
    아파트 관리비를 준다. 층은 '저'·'중'·'고' 로만 와서 정확한 층은 `/v3/items` 에서 받는다.
    """

    item_source: Annotated[
        str | None,
        Field(description='매물 출처 (zigbang, coalition 제휴)', alias='itemSource')
    ] = None
    item_id: Annotated[
        int,
        Field(description='매물 ID', alias='itemId')
    ]
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
        Field(description='지번 주소 (예: 경기도 성남시 분당구 삼평동 705). 직방 매물은 빈 문자열로 오기도 한다', alias='oldAddress')
    ] = None
    building_floor: Annotated[
        int | None,
        Field(description='건물 층수', alias='buildingFloor')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='방향 (소문자 e, sw ...)')
    ] = None
    movein_date: Annotated[
        str | None,
        Field(description='입주 가능일 (예: 즉시입주가능, 2026.11.30(협의가능))', alias='moveinDate')
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
        Field(description="층. 직방 매물은 '저'·'중'·'고', 제휴 매물은 숫자")
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
