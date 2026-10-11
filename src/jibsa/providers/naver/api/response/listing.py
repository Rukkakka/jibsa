"""응답 모델: 단지 매물 목록과 매물 상세 (search listings --complex, listing)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
    NaverCoordinatesModel,
    NaverFacilityInfoModel,
    NaverPropertyTaxModel,
    NaverResponseModel,
    NaverSchoolModel,
    NaverTotalRealEstateTaxModel,
)

from typing import Annotated


class NaverTransportSubwayLineModel(ResponseModel):
    """역의 노선 한 개. 노선마다 도보 거리가 따로 온다 (출구가 달라서)."""

    name: Annotated[
        str | None,
        Field(description='노선 이름 (예: 3호선, 수인분당)')
    ] = None
    walking_distance: Annotated[
        int | None,
        Field(description='도보 거리 (m)')
    ] = Field(default=None, alias='walkingDistance')
    walking_duration: Annotated[
        int | None,
        Field(description='도보 시간 (분)')
    ] = Field(default=None, alias='walkingDuration')


class NaverTransportSubwayModel(ResponseModel):
    """가까운 지하철역 한 개."""

    station_name: Annotated[
        str | None,
        Field(description='역 이름 (예: 대청역)')
    ] = Field(default=None, alias='stationName')
    type_list: Annotated[
        list[NaverTransportSubwayLineModel],
        Field(description='노선')
    ] = Field(default=[], alias='typeList')


class NaverTransportBusModel(ResponseModel):
    """한 종류의 버스 노선들."""

    type_name: Annotated[
        str | None,
        Field(description='버스 종류 (간선, 지선, 마을, 광역, 직행좌석, 공항 ...)')
    ] = Field(default=None, alias='typeName')
    routes: Annotated[
        list[str],
        Field(description='노선 번호')
    ] = Field(default=[], alias='list')


class NaverTransportModel(ResponseModel):
    """data-service/transport 결과. 가까운 지하철역과 주변 정류장의 버스 노선."""

    subway_list: Annotated[
        list[NaverTransportSubwayModel],
        Field(description='가까운 지하철역 (가까운 순)')
    ] = Field(default=[], alias='subwayList')
    bus_list: Annotated[
        list[NaverTransportBusModel],
        Field(description='버스 종류별 노선')
    ] = Field(default=[], alias='busList')


class NaverAcquisitionTaxModel(ResponseModel):
    """취득세 (원)."""

    acquisition_tax: Annotated[
        int | None,
        Field(description='취득세')
    ] = Field(default=None, alias='acquisitionTax')
    local_tax: Annotated[
        int | None,
        Field(description='지방교육세')
    ] = Field(default=None, alias='localTax')
    rural_special_tax: Annotated[
        int | None,
        Field(description='농어촌특별세')
    ] = Field(default=None, alias='ruralSpecialTax')


class NaverArticleTaxModel(ResponseModel):
    """매물 가격 기준 세금 추정 (원). 사이트가 보여 주는 네이버 계산값이다."""

    acquisition_tax: Annotated[
        NaverAcquisitionTaxModel | None,
        Field(description='취득세 (매매가 기준)')
    ] = Field(default=None, alias='acquisitionTax')
    property_tax: Annotated[
        NaverPropertyTaxModel | None,
        Field(description='재산세 (공시가 기준, 연)')
    ] = Field(default=None, alias='propertyTax')
    total_real_estate_tax: Annotated[
        NaverTotalRealEstateTaxModel | None,
        Field(description='종합부동산세 (공시가 기준, 연)')
    ] = Field(default=None, alias='totalRealEstateTax')


class NaverFeeRatioModel(ResponseModel):
    """중개보수 요율 범위 (%)."""

    min: Annotated[
        float | None,
        Field(description='최저 요율 (%)')
    ] = None
    max: Annotated[
        float | None,
        Field(description='최고 요율 (%)')
    ] = None


class NaverArticleAgentFeeModel(ResponseModel):
    """매물 가격 기준 중개보수 (원)."""

    fee: Annotated[
        int | None,
        Field(description='중개보수 상한 (원)')
    ] = None
    fee_ratio: Annotated[
        NaverFeeRatioModel | None,
        Field(description='요율 (%)')
    ] = Field(default=None, alias='feeRatio')
    is_individual_check_required: Annotated[
        bool | None,
        Field(description='중개사와 따로 협의해야 하는지 (요율이 정해지지 않은 고가 매물 등)')
    ] = Field(default=None, alias='isIndividualCheckRequired')


class NaverArticleKeyIdsModel(ResponseModel):
    """매물의 연관 키."""

    complex_number: Annotated[
        int | None,
        Field(description='단지 번호')
    ] = Field(default=None, alias='complexNumber')
    pyeong_type_number: Annotated[
        int | None,
        Field(description='평형 번호')
    ] = Field(default=None, alias='pyeongTypeNumber')
    building_number: Annotated[
        int | None,
        Field(description='건물 번호')
    ] = Field(default=None, alias='buildingNumber')


class NaverArticleTypeModel(ResponseModel):
    """매물 유형 코드 쌍."""

    real_estate_type: Annotated[
        str,
        Field(description='매물 유형 코드')
    ] = Field(alias='realEstateType')
    trade_type: Annotated[
        str,
        Field(description='거래 유형 코드')
    ] = Field(alias='tradeType')


class NaverArticleKeyAddressModel(ResponseModel):
    """매물의 법정동 코드와 지번."""

    legal_division_number: Annotated[
        str | None,
        Field(description='법정동 코드')
    ] = Field(default=None, alias='legalDivisionNumber')
    jibun: Annotated[
        str | None,
        Field(description='지번 (예: 12-2)')
    ] = None


class NaverArticleKeyModel(ResponseModel):
    """article/key 결과."""

    key: Annotated[
        NaverArticleKeyIdsModel | None,
        Field(description='단지·평형·건물 번호')
    ] = None
    type: Annotated[
        NaverArticleTypeModel,
        Field(description='basicInfo 호출에 넘길 유형 코드')
    ]
    address: Annotated[
        NaverArticleKeyAddressModel | None,
        Field(description='법정동 코드와 지번')
    ] = None


class NaverPriceInfoModel(ResponseModel):
    """상세 가격 (원). 매매는 `price`, 전세·월세는 `warrantyAmount`/`rentAmount` 로 온다."""

    price: Annotated[
        int | None,
        Field(description='매매가 (원)')
    ] = None
    warranty_amount: Annotated[
        int | None,
        Field(description='보증금·전세금 (원)')
    ] = Field(default=None, alias='warrantyAmount')
    rent_amount: Annotated[
        int | None,
        Field(description='월세 (원)')
    ] = Field(default=None, alias='rentAmount')
    monthly_rent: Annotated[
        int | None,
        Field(description='월세 (원)')
    ] = Field(default=None, alias='monthlyRent')
    loan: Annotated[
        int | None,
        Field(description='융자금 (원). 0 이면 loan_code 로 "없음"과 "입력 안 함"을 구분한다')
    ] = None
    previous_deposit: Annotated[
        int | None,
        Field(description='기존 보증금 (원)')
    ] = Field(default=None, alias='previousDeposit')
    previous_monthly_rent: Annotated[
        int | None,
        Field(description='기존 월세 (원)')
    ] = Field(default=None, alias='previousMonthlyRent')
    loan_code: Annotated[
        str | None,
        Field(description="융자 구분. '0' 이면 융자 없음을 명시, '2' 는 융자 있음. 없으면 입력 안 함")
    ] = Field(default=None, alias='loanCode')


class NaverFloorInfoModel(ResponseModel):
    """층 정보."""

    target_floor: Annotated[
        str | None,
        Field(description='해당 층 (저/중/고 로 가려질 수 있음)')
    ] = Field(default=None, alias='targetFloor')
    total_floor: Annotated[
        str | None,
        Field(description='전체 층')
    ] = Field(default=None, alias='totalFloor')


class NaverSpaceInfoModel(ResponseModel):
    """상세의 공간 정보."""

    floor_info: Annotated[
        NaverFloorInfoModel | None,
        Field(description='층')
    ] = Field(default=None, alias='floorInfo')
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = Field(default=None, alias='roomCount')
    bath_room_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = Field(default=None, alias='bathRoomCount')
    duplex: Annotated[
        bool | None,
        Field(description='복층 여부')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='방향 코드 (EE 동향, SS 남향 ...)')
    ] = None
    direction_standard: Annotated[
        str | None,
        Field(description='방향 기준 (예: 거실 기준)')
    ] = Field(default=None, alias='directionStandard')


class NaverSizeInfoModel(ResponseModel):
    """면적."""

    supply_space: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 계약면적이 온다 (평형표 contractArea 와 같음)')
    ] = Field(default=None, alias='supplySpace')
    exclusive_space: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = Field(default=None, alias='exclusiveSpace')
    pyeong_area: Annotated[
        float | None,
        Field(description='공급 평수')
    ] = Field(default=None, alias='pyeongArea')


class NaverMovingInInfoModel(ResponseModel):
    """입주 가능일."""

    moving_in_type: Annotated[
        str | None,
        Field(description=(
            "'MV001' 즉시입주(날짜 없음), 'MV004' 날짜 지정(movingInDate), 'EARLY'·'MID'·'LATE' 는 "
            'movingInDate 달의 초·중·하순 (매물 65건 실측, 2026-10-10)'
        ))
    ] = Field(default=None, alias='movingInType')
    moving_in_date: Annotated[
        str | None,
        Field(description='입주 가능일')
    ] = Field(default=None, alias='movingInDate')
    moving_in_negotiation: Annotated[
        bool | None,
        Field(description='협의 가능 여부')
    ] = Field(default=None, alias='movingInNegotiation')


class NaverArticleDetailInfoModel(ResponseModel):
    """상세 본문 정보."""

    article_name: Annotated[
        str | None,
        Field(description='매물 이름 (보통 단지명)')
    ] = Field(default=None, alias='articleName')
    article_feature_description: Annotated[
        str | None,
        Field(description='한 줄 특징')
    ] = Field(default=None, alias='articleFeatureDescription')
    article_description: Annotated[
        str | None,
        Field(description='본문')
    ] = Field(default=None, alias='articleDescription')
    exposure_start_date: Annotated[
        str | None,
        Field(description='노출 시작일')
    ] = Field(default=None, alias='exposureStartDate')
    building_principal_use: Annotated[
        str | None,
        Field(description='건축물 주용도')
    ] = Field(default=None, alias='buildingPrincipalUse')
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='좌표')
    ] = None


class NaverDetailInfoModel(ResponseModel):
    """basicInfo 의 detailInfo."""

    facility_info: Annotated[
        NaverFacilityInfoModel | None,
        Field(description='시설')
    ] = Field(default=None, alias='facilityInfo')
    article_detail_info: Annotated[
        NaverArticleDetailInfoModel | None,
        Field(description='본문 정보')
    ] = Field(default=None, alias='articleDetailInfo')
    moving_in_info: Annotated[
        NaverMovingInInfoModel | None,
        Field(description='입주 가능일')
    ] = Field(default=None, alias='movingInInfo')
    space_info: Annotated[
        NaverSpaceInfoModel | None,
        Field(description='층·방·방향')
    ] = Field(default=None, alias='spaceInfo')
    size_info: Annotated[
        NaverSizeInfoModel | None,
        Field(description='면적')
    ] = Field(default=None, alias='sizeInfo')
    shape: Annotated[
        str | None,
        Field(description=(
            "원룸 구조 코드 '10' 오픈형, '20' 분리형 (지도 필터 oneRoomShapeTypes 와 같은 코드). 방이 여럿이어도 '20' 으로 온다. "
            '단지 매물(아파트·오피스텔·단지형 빌라)은 키가 없고, 다른 매물도 구조를 입력하지 않았으면 null 이다 (2026-10-10 확인)'
        ))
    ] = None


class NaverCommunalComplexInfoModel(ResponseModel):
    """매물이 속한 단지."""

    complex_number: Annotated[
        int | None,
        Field(description='단지 번호')
    ] = Field(default=None, alias='complexNumber')
    complex_name: Annotated[
        str | None,
        Field(description='단지명')
    ] = Field(default=None, alias='complexName')
    dong_name: Annotated[
        str | None,
        Field(description='동')
    ] = Field(default=None, alias='dongName')


class NaverArticleBasicInfoModel(ResponseModel):
    """매물 상세."""

    price_info: Annotated[
        NaverPriceInfoModel | None,
        Field(description='가격 (원)')
    ] = Field(default=None, alias='priceInfo')
    detail_info: Annotated[
        NaverDetailInfoModel | None,
        Field(description='상세')
    ] = Field(default=None, alias='detailInfo')
    communal_complex_info: Annotated[
        NaverCommunalComplexInfoModel | None,
        Field(description='소속 단지')
    ] = Field(default=None, alias='communalComplexInfo')


class NaverAgentPhoneModel(ResponseModel):
    """중개사 연락처."""

    brokerage: Annotated[
        str | None,
        Field(description='사무소 대표번호')
    ] = None


class NaverArticleAgentModel(ResponseModel):
    """중개사."""

    brokerage_name: Annotated[
        str | None,
        Field(description='중개사무소명')
    ] = Field(default=None, alias='brokerageName')
    broker_name: Annotated[
        str | None,
        Field(description='대표 중개사')
    ] = Field(default=None, alias='brokerName')
    address: Annotated[
        str | None,
        Field(description='사무소 주소')
    ] = None
    business_registration_number: Annotated[
        str | None,
        Field(description='중개사무소 등록번호')
    ] = Field(default=None, alias='businessRegistrationNumber')
    phone: Annotated[
        NaverAgentPhoneModel | None,
        Field(description='연락처')
    ] = None


class NaverEtcDetailModel(ResponseModel):
    """관리비 합계 금액과 포함 항목 (typeCode '02' 의 etcDetail, '04' 의 fixNonDetailList)."""

    amount: Annotated[
        int | None,
        Field(description='월 관리비 (원)')
    ] = None
    category_list: Annotated[
        list[str] | None,
        Field(description=(
            "관리비에 포함된 항목 코드. '01' 공용, '11' 전기, '12' 수도, '13' 가스, '14' 난방, '15' 인터넷, "
            "'16' TV, '99' 기타 (사이트 화면 대조, 2026-10-10). 중개사가 항목을 입력하지 않으면 키가 없다"
        ))
    ] = Field(default=None, alias='categoryList')


class NaverFixDetailModel(ResponseModel):
    """항목별 관리비 (typeCode '01' 의 fixDetailList 한 줄)."""

    type: Annotated[
        str | None,
        Field(description="항목 코드. etcDetail.categoryList 와 같다 ('01' 공용, '11'~'16' 사용료, '99' 기타)")
    ] = None
    unit_type: Annotated[
        str | None,
        Field(description="'01' 정액 (amount 가 관리비에 들어감), '02' 실비 (금액 없이 쓴 만큼 따로 냄, 사이트 표기 '실비')")
    ] = Field(default=None, alias='unitType')
    amount: Annotated[
        int | None,
        Field(description='정액 금액 (원). 실비 항목은 없다')
    ] = None


class NaverArticleMaintenanceFeeModel(ResponseModel):
    """관리비."""

    type_code: Annotated[
        str | None,
        Field(description=(
            "관리비 입력 방식 코드. '01' 항목별 금액 (fixDetailList, 사이트는 정액 항목을 더해 합계로 보여 준다), "
            "'02' 합계 금액 (etcDetail, 0원 포함), '03' 미확인 (uncheckDetail 로 사유가 오고 금액 키는 null), "
            "'04' 정액 합계 금액 (fixNonDetailList)"
        ))
    ] = Field(default=None, alias='typeCode')
    etc_detail: Annotated[
        NaverEtcDetailModel | None,
        Field(description='합계 금액·포함 항목')
    ] = Field(default=None, alias='etcDetail')
    fix_detail_list: Annotated[
        list[NaverFixDetailModel] | None,
        Field(description='항목별 금액 (typeCode 01). 원룸 2653883790: 공용 10만원 정액 + 전기~TV 실비 = 합계 10만원 (2026-10-10)')
    ] = Field(default=None, alias='fixDetailList')
    fix_non_detail_list: Annotated[
        NaverEtcDetailModel | None,
        Field(description=(
            "정액 합계 금액·포함 항목 (typeCode '04'). 이름과 달리 리스트가 아니라 etcDetail 과 같은 모양이고, 금액은 목록의 "
            "관리비와 같다 (신림동 원룸·빌라·오피스텔 7건, 2026-10-11: 2652339975 13만원 등)"
        ))
    ] = Field(default=None, alias='fixNonDetailList')


class NaverComplexVillaArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/complex/villa/article/list` 응답."""


class NaverDataServiceTransportV1ResponseModel(NaverResponseModel[NaverTransportModel]):
    """`GET /front-api/v1/data-service/transport` 응답."""


class NaverEducationBuildingSchoolV1ResponseModel(NaverResponseModel[list[NaverSchoolModel]]):
    """`GET /front-api/v1/education/building/school` 응답."""


class NaverArticleKeyV1ResponseModel(NaverResponseModel[NaverArticleKeyModel]):
    """`GET /front-api/v1/article/key` 응답."""


class NaverArticleBasicInfoV1ResponseModel(NaverResponseModel[NaverArticleBasicInfoModel]):
    """`GET /front-api/v1/article/basicInfo` 응답."""


class NaverArticleAgentV1ResponseModel(NaverResponseModel[NaverArticleAgentModel]):
    """`GET /front-api/v1/article/agent` 응답."""


class NaverArticleTaxV1ResponseModel(NaverResponseModel[NaverArticleTaxModel]):
    """`GET /front-api/v1/article/tax` 응답."""


class NaverArticleAgentFeeV1ResponseModel(NaverResponseModel[NaverArticleAgentFeeModel]):
    """`GET /front-api/v1/article/agentFee` 응답."""


class NaverArticleMaintenanceFeeV1ResponseModel(NaverResponseModel[NaverArticleMaintenanceFeeModel]):
    """`GET /front-api/v1/article/maintenanceFee` 응답."""


class NaverComplexArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/complex/article/list` 응답."""
