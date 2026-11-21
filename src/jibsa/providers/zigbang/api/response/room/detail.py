"""응답 모델: 원룸·빌라·오피스텔 매물 상세 (listing): 기존 상세, 건물 학군, 건물 실거래 (새 주거 상세는 base)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangAddressOriginModel,
    ZigbangLatLngModel,
    ZigbangSubwayBriefModel,
)
from jibsa.providers.zigbang.api.response.room.base import (
    ZigbangDetailPriceModel,
    ZigbangV3DanjiModel,
)

from typing import Annotated


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
        list[ZigbangBlSchoolModel] | None,
        Field(description='통학구역·학교군 안의 학교. 키가 없거나 null 이면 None (학교 없음으로 본다)')
    ] = None


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


# ---------------------------------------------------------------------------
# GET /v2/bls/{pnu}/rts
# ---------------------------------------------------------------------------

class ZigbangBlsRtModel(ResponseModel):
    """건물(필지)의 실거래 한 건. 필지 번호(`pnu`)는 읽지 않는다. 금액은 **만원**이다."""

    deal_date: Annotated[
        str | None,
        Field(description='거래일 (YYYY-MM-DD)', alias='거래일')
    ] = None
    sales_type: Annotated[
        str | None,
        Field(description='거래 유형 (매매·전세·월세)')
    ] = None
    sale_price: Annotated[
        int | None,
        Field(description='매매금액 (만원). 매매가 아니면 null', alias='매매금액')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금액 (만원). 매매면 null', alias='보증금액')
    ] = None
    monthly_rent: Annotated[
        int | None,
        Field(description='월세금액 (만원). 전세는 0, 매매는 null', alias='월세금액')
    ] = None
    exclusive_area: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='전용면적')
    ] = None
    land_area: Annotated[
        float | None,
        Field(description='대지권면적 (㎡). 2026-11-19 표본에서는 모두 null', alias='대지권면적')
    ] = None
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None


class ZigbangBlsRtsV2ResponseModel(ResponseModel):
    """건물(필지) 하나의 실거래 목록 (최근 거래부터. 2026-11-19 실측: 한 건물 42건, 거래가 없는 필지는 빈 목록)."""

    rts: Annotated[
        list[ZigbangBlsRtModel] | None,
        Field(description='실거래. 거래가 없는 필지는 빈 목록이고, 키가 없거나 null 이면 None (모름)')
    ] = None
