"""응답 모델: 매물 상세 (listing)."""

from pydantic import Field

from jibsa.providers.naver.api.models.response.common import (
    NaverBaseResponseModel,
    NaverCoordinatesModel,
    NaverFacilityInfoModel,
    NaverListVerificationInfoModel,
    NaverParkingInfoModel,
    NaverPropertyTaxModel,
    NaverPyeongModel,
    NaverResponseModel,
    NaverSchoolModel,
    NaverTotalRealEstateTaxModel,
)

from typing import Annotated


class NaverTransportSubwayLineModel(NaverBaseResponseModel):
    """역의 노선 한 개. 노선마다 도보 거리가 따로 온다 (출구가 달라서)."""

    name: Annotated[
        str | None,
        Field(description='노선 이름 (예: 3호선, 수인분당)')
    ] = None
    walking_distance: Annotated[
        int | None,
        Field(description='도보 거리 (m)', alias='walkingDistance')
    ] = None
    walking_duration: Annotated[
        int | None,
        Field(description='도보 시간 (분)', alias='walkingDuration')
    ] = None


class NaverTransportSubwayModel(NaverBaseResponseModel):
    """가까운 지하철역 한 개."""

    station_name: Annotated[
        str | None,
        Field(description='역 이름 (예: 대청역)', alias='stationName')
    ] = None
    type_list: Annotated[
        list[NaverTransportSubwayLineModel],
        Field(description='노선', alias='typeList')
    ] = []


class NaverTransportBusModel(NaverBaseResponseModel):
    """한 종류의 버스 노선들."""

    type_name: Annotated[
        str | None,
        Field(description='버스 종류 (간선, 지선, 마을, 광역, 직행좌석, 공항 ...)', alias='typeName')
    ] = None
    routes: Annotated[
        list[str],
        Field(description='노선 번호', alias='list')
    ] = []


class NaverTransportModel(NaverBaseResponseModel):
    """data-service/transport 결과. 가까운 지하철역과 주변 정류장의 버스 노선."""

    subway_list: Annotated[
        list[NaverTransportSubwayModel],
        Field(description='가까운 지하철역 (가까운 순)', alias='subwayList')
    ] = []
    bus_list: Annotated[
        list[NaverTransportBusModel],
        Field(description='버스 종류별 노선', alias='busList')
    ] = []


class NaverAcquisitionTaxModel(NaverBaseResponseModel):
    """취득세 (원)."""

    acquisition_tax: Annotated[
        int | None,
        Field(description='취득세', alias='acquisitionTax')
    ] = None
    local_tax: Annotated[
        int | None,
        Field(description='지방교육세', alias='localTax')
    ] = None
    rural_special_tax: Annotated[
        int | None,
        Field(description='농어촌특별세', alias='ruralSpecialTax')
    ] = None


class NaverArticleTaxModel(NaverBaseResponseModel):
    """매물 가격 기준 세금 추정 (원). 사이트가 보여 주는 네이버 계산값이다."""

    acquisition_tax: Annotated[
        NaverAcquisitionTaxModel | None,
        Field(description='취득세 (매매가 기준)', alias='acquisitionTax')
    ] = None
    property_tax: Annotated[
        NaverPropertyTaxModel | None,
        Field(description='재산세 (공시가 기준, 연)', alias='propertyTax')
    ] = None
    total_real_estate_tax: Annotated[
        NaverTotalRealEstateTaxModel | None,
        Field(description='종합부동산세 (공시가 기준, 연)', alias='totalRealEstateTax')
    ] = None


class NaverFeeRatioModel(NaverBaseResponseModel):
    """중개보수 요율 범위 (%)."""

    min: Annotated[
        float | None,
        Field(description='최저 요율 (%)')
    ] = None
    max: Annotated[
        float | None,
        Field(description='최고 요율 (%)')
    ] = None


class NaverArticleAgentFeeModel(NaverBaseResponseModel):
    """매물 가격 기준 중개보수 (원)."""

    fee: Annotated[
        int | None,
        Field(description='중개보수 상한 (원)')
    ] = None
    fee_ratio: Annotated[
        NaverFeeRatioModel | None,
        Field(description='요율 (%)', alias='feeRatio')
    ] = None
    is_individual_check_required: Annotated[
        bool | None,
        Field(description='중개사와 따로 협의해야 하는지 (요율이 정해지지 않은 고가 매물 등)', alias='isIndividualCheckRequired')
    ] = None


class NaverArticleKeyIdsModel(NaverBaseResponseModel):
    """매물의 연관 키."""

    complex_number: Annotated[
        int | None,
        Field(description='단지 번호', alias='complexNumber')
    ] = None
    pyeong_type_number: Annotated[
        int | None,
        Field(description='평형 번호', alias='pyeongTypeNumber')
    ] = None
    building_number: Annotated[
        int | None,
        Field(description='건물 번호', alias='buildingNumber')
    ] = None
    pnu: Annotated[
        str | None,
        Field(description='필지 고유번호 (19자리). 건축물대장 조회(complex/buildingRegistration)에 쓴다')
    ] = None


class NaverArticleTypeModel(NaverBaseResponseModel):
    """매물 유형 코드 쌍."""

    real_estate_type: Annotated[
        str,
        Field(description='매물 유형 코드', alias='realEstateType')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형 코드', alias='tradeType')
    ]


class NaverArticleKeyAddressModel(NaverBaseResponseModel):
    """매물의 법정동 코드와 지번."""

    legal_division_number: Annotated[
        str | None,
        Field(description='법정동 코드', alias='legalDivisionNumber')
    ] = None
    jibun: Annotated[
        str | None,
        Field(description='지번 (예: 12-2). 지번을 숨기는 유형(상가·사무실·토지 등)의 매물은 null 이다 (2026-11-20 실측 15건)')
    ] = None
    li: Annotated[
        str | None,
        Field(description='리 이름. 읍·면 매물만 온다')
    ] = None


class NaverArticleKeyModel(NaverBaseResponseModel):
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


class NaverPriceInfoModel(NaverBaseResponseModel):
    """상세 가격 (원). 매매는 `price`, 전세·월세는 `warrantyAmount`/`rentAmount` 로 온다."""

    price: Annotated[
        int | None,
        Field(description='매매가 (원)')
    ] = None
    warranty_amount: Annotated[
        int | None,
        Field(description='보증금·전세금 (원)', alias='warrantyAmount')
    ] = None
    rent_amount: Annotated[
        int | None,
        Field(description='월세 (원)', alias='rentAmount')
    ] = None
    monthly_rent: Annotated[
        int | None,
        Field(description='월세 (원)', alias='monthlyRent')
    ] = None
    loan: Annotated[
        int | None,
        Field(description='융자금 (원). 0 이면 loan_code 로 "없음"과 "입력 안 함"을 구분한다')
    ] = None
    previous_deposit: Annotated[
        int | None,
        Field(description='기존 보증금 (원)', alias='previousDeposit')
    ] = None
    previous_monthly_rent: Annotated[
        int | None,
        Field(description='기존 월세 (원)', alias='previousMonthlyRent')
    ] = None
    loan_code: Annotated[
        str | None,
        Field(description="융자 구분. '0' 이면 융자 없음을 명시, '2' 는 융자 있음. 없으면 입력 안 함", alias='loanCode')
    ] = None


class NaverFloorInfoModel(NaverBaseResponseModel):
    """층 정보."""

    target_floor: Annotated[
        str | None,
        Field(description='해당 층 (저/중/고 로 가려질 수 있음)', alias='targetFloor')
    ] = None
    total_floor: Annotated[
        str | None,
        Field(description='전체 층', alias='totalFloor')
    ] = None


class NaverSpaceInfoModel(NaverBaseResponseModel):
    """상세의 공간 정보."""

    floor_info: Annotated[
        NaverFloorInfoModel | None,
        Field(description='층', alias='floorInfo')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCount')
    ] = None
    bath_room_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathRoomCount')
    ] = None
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
        Field(description='방향 기준 (예: 거실 기준)', alias='directionStandard')
    ] = None


class NaverSizeInfoModel(NaverBaseResponseModel):
    """면적."""

    supply_space: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 계약면적이 온다 (평형표 contractArea 와 같음)', alias='supplySpace')
    ] = None
    exclusive_space: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='exclusiveSpace')
    ] = None
    pyeong_area: Annotated[
        float | None,
        Field(description='공급 평수', alias='pyeongArea')
    ] = None


class NaverMovingInInfoModel(NaverBaseResponseModel):
    """입주 가능일."""

    moving_in_type: Annotated[
        str | None,
        Field(
            description="'MV001' 즉시입주(날짜 없음), 'MV002' 이내입주·'MV003' 이후입주·'MV004' 날짜 지정 (모두 movingInDate, "
            "웹 번들 ARTICLE_MOVING_IN_TYPE 대조 2026-11-16), 'EARLY'·'MID'·'LATE' 는 movingInDate 달의 초·중·하순 "
            '(매물 65건 실측, 2026-10-10)',
            alias='movingInType'
        )
    ] = None
    moving_in_date: Annotated[
        str | None,
        Field(description='입주 가능일', alias='movingInDate')
    ] = None
    moving_in_negotiation: Annotated[
        bool | None,
        Field(description='협의 가능 여부', alias='movingInNegotiation')
    ] = None


class NaverArticleDetailInfoModel(NaverBaseResponseModel):
    """상세 본문 정보."""

    article_name: Annotated[
        str | None,
        Field(description='매물 이름 (보통 단지명)', alias='articleName')
    ] = None
    article_feature_description: Annotated[
        str | None,
        Field(description='한 줄 특징', alias='articleFeatureDescription')
    ] = None
    article_description: Annotated[
        str | None,
        Field(description='본문', alias='articleDescription')
    ] = None
    exposure_start_date: Annotated[
        str | None,
        Field(description='노출 시작일', alias='exposureStartDate')
    ] = None
    building_principal_use: Annotated[
        str | None,
        Field(description='건축물 주용도', alias='buildingPrincipalUse')
    ] = None
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='좌표')
    ] = None
    non_complex_building_name: Annotated[
        str | None,
        Field(description='단지에 속하지 않는 건물의 이름 (예: 새롬빌). 건물 이름이 없는 매물은 키가 없다 (2026-11-17 확인)', alias='nonComplexBuildingName')
    ] = None
    non_complex_building_sub_name: Annotated[
        str | None,
        Field(description='건물 이름 뒤에 붙이는 이름 (동 이름 등). 웹은 매물 유형에 따라 건물 이름 뒤에 붙여 제목에 쓴다', alias='nonComplexBuildingSubName')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='건물 세부 유형 코드 (C0203 빌라, C0201 다세대, C0101 일반원룸 ...). 단지 매물은 키가 없다 (2026-11-17 확인)', alias='buildingType')
    ] = None
    is_jibun_address_exposed: Annotated[
        bool | None,
        Field(description='지번 주소를 보여도 되는지. 없으면 숨기는 쪽이다 (웹 위치 칸이 같게 읽는다)', alias='isJibunAddressExposed')
    ] = None
    is_direct_trade: Annotated[
        bool | None,
        Field(description='직거래 매물인지. 네이버 웹은 직거래 매물에 중개보수 칸을 그리지 않는다 (2026-11-17 확인, 토지 2661679787)', alias='isDirectTrade')
    ] = None
    is_safe_lessor_of_hug: Annotated[
        bool | None,
        Field(description='HUG(주택도시보증공사) 안심임대인 여부. 목록의 같은 이름 필드(articleDetail.isSafeLessorOfHug)와 같다. 참이면 확인 배지 뒤에 HUG 안심임대인 배지를 붙인다', alias='isSafeLessorOfHug')
    ] = None


class NaverDetailInfoModel(NaverBaseResponseModel):
    """basicInfo 의 detailInfo."""

    facility_info: Annotated[
        NaverFacilityInfoModel | None,
        Field(description='시설', alias='facilityInfo')
    ] = None
    article_detail_info: Annotated[
        NaverArticleDetailInfoModel | None,
        Field(description='본문 정보', alias='articleDetailInfo')
    ] = None
    pre_sale_status_type: Annotated[
        str | None,
        Field(description="분양권 상태 코드. '10' 일반분양권. 네이버 웹은 분양권(B01·B02) 매매에서 이 값이 '10' 일 때만 세금 칸을 그린다 (2026-11-17 둔촌동 분양권 2661144592 '10'·2659804873 '20', 번들 getArticleTaxExposeInfo)", alias='preSaleStatusType')
    ] = None
    moving_in_info: Annotated[
        NaverMovingInInfoModel | None,
        Field(description='입주 가능일', alias='movingInInfo')
    ] = None
    space_info: Annotated[
        NaverSpaceInfoModel | None,
        Field(description='층·방·방향', alias='spaceInfo')
    ] = None
    size_info: Annotated[
        NaverSizeInfoModel | None,
        Field(description='면적', alias='sizeInfo')
    ] = None
    verification_info: Annotated[
        NaverListVerificationInfoModel | None,
        Field(description='확인 정보. 목록의 verificationInfo 와 같은 모양 (확인 방식 verificationType 으로 확인 배지를 정한다)', alias='verificationInfo')
    ] = None
    shape: Annotated[
        str | None,
        Field(description=(
            "원룸 구조 코드 '10' 오픈형, '20' 분리형 (지도 필터 oneRoomShapeTypes 와 같은 코드). 방이 여럿이어도 '20' 으로 온다. "
            '단지 매물(아파트·오피스텔·단지형 빌라)은 키가 없고, 다른 매물도 구조를 입력하지 않았으면 null 이다 (2026-10-10 확인)'
        ))
    ] = None


class NaverCommunalComplexInfoModel(NaverBaseResponseModel):
    """매물이 속한 단지."""

    complex_number: Annotated[
        int | None,
        Field(description='단지 번호', alias='complexNumber')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지명', alias='complexName')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description='동', alias='dongName')
    ] = None


class NaverArticleBasicInfoModel(NaverBaseResponseModel):
    """매물 상세."""

    price_info: Annotated[
        NaverPriceInfoModel | None,
        Field(description='가격 (원)', alias='priceInfo')
    ] = None
    detail_info: Annotated[
        NaverDetailInfoModel | None,
        Field(description='상세', alias='detailInfo')
    ] = None
    communal_complex_info: Annotated[
        NaverCommunalComplexInfoModel | None,
        Field(description='소속 단지', alias='communalComplexInfo')
    ] = None


class NaverEtcDetailModel(NaverBaseResponseModel):
    """관리비 합계 금액과 포함 항목 (typeCode '02' 의 etcDetail, '04' 의 fixNonDetailList)."""

    amount: Annotated[
        int | None,
        Field(description='월 관리비 (원)')
    ] = None
    category_list: Annotated[
        list[str] | None,
        Field(
            description="관리비에 포함된 항목 코드. '01' 공용, '11' 전기, '12' 수도, '13' 가스, '14' 난방, '15' 인터넷, "
            "'16' TV, '99' 기타 (사이트 화면 대조, 2026-10-10). 중개사가 항목을 입력하지 않으면 키가 없다",
            alias='categoryList'
        )
    ] = None


class NaverFixDetailModel(NaverBaseResponseModel):
    """항목별 관리비 (typeCode '01' 의 fixDetailList 한 줄)."""

    type: Annotated[
        str | None,
        Field(description="항목 코드. etcDetail.categoryList 와 같다 ('01' 공용, '11'~'16' 사용료, '99' 기타)")
    ] = None
    unit_type: Annotated[
        str | None,
        Field(description="'01' 정액 (amount 가 관리비에 들어감), '02' 실비 (금액 없이 쓴 만큼 따로 냄, 사이트 표기 '실비')", alias='unitType')
    ] = None
    amount: Annotated[
        int | None,
        Field(description='정액 금액 (원). 실비 항목은 없다')
    ] = None


class NaverUncheckDetailModel(NaverBaseResponseModel):
    """관리비를 확인할 수 없는 사유 (typeCode '03' 의 uncheckDetail)."""

    type: Annotated[
        str | None,
        Field(
            description="사유 코드 (웹 번들 UNABLE_CHECK_DETAIL_CODE_TYPE 대조, 2026-11-16). '01' 단독주택이라 중개사 미기재, "
            "'02' 오피스텔 외 상가건물이라 중개사 미기재, '03' 미등기·신축이라 확인 어려움, '04' 임대인 미고지, '99' 없음 "
            "(웹이 관리비 '없음' 으로 보여 준다)"
        )
    ] = None


class NaverArticleMaintenanceFeeModel(NaverBaseResponseModel):
    """관리비."""

    type_code: Annotated[
        str | None,
        Field(
            description="관리비 입력 방식 코드. '01' 항목별 금액 (fixDetailList, 사이트는 정액 항목을 더해 합계로 보여 준다), "
            "'02' 합계 금액 (etcDetail, 0원 포함), '03' 미확인 (uncheckDetail 로 사유가 오고 금액 키는 null), "
            "'04' 정액 합계 금액 (fixNonDetailList)",
            alias='typeCode'
        )
    ] = None
    etc_detail: Annotated[
        NaverEtcDetailModel | None,
        Field(description='합계 금액·포함 항목', alias='etcDetail')
    ] = None
    fix_detail_list: Annotated[
        list[NaverFixDetailModel] | None,
        Field(description='항목별 금액 (typeCode 01). 원룸 2653883790: 공용 10만원 정액 + 전기~TV 실비 = 합계 10만원 (2026-10-10)', alias='fixDetailList')
    ] = None
    uncheck_detail: Annotated[
        NaverUncheckDetailModel | None,
        Field(description="확인 불가 사유 (typeCode '03')", alias='uncheckDetail')
    ] = None
    fix_non_detail_list: Annotated[
        NaverEtcDetailModel | None,
        Field(
            description="정액 합계 금액·포함 항목 (typeCode '04'). 이름과 달리 리스트가 아니라 etcDetail 과 같은 모양이고, 금액은 목록의 "
            "관리비와 같다 (신림동 원룸·빌라·오피스텔 7건, 2026-10-11: 2652339975 13만원 등)",
            alias='fixNonDetailList'
        )
    ] = None


class NaverArticleOldMaintenanceFeeModel(NaverBaseResponseModel):
    """옛 형식 관리비. 웹은 maintenanceFee 로 '관리비' 칸을 못 만들 때 이 금액으로 그린다."""

    amount: Annotated[
        int | float | None,
        Field(description='월 관리비 (원). 값이 없으면 result 가 빈 객체 {} 라 null', alias='amount')
    ] = None


class NaverDataServiceTransportV1ResponseModel(NaverResponseModel[NaverTransportModel]):
    """`GET /front-api/v1/data-service/transport` 응답."""


class NaverDevelopmentRailModel(NaverBaseResponseModel):
    """매물 근처에 생길 지하철역 한 곳. 좌표도 오지만 쓰지 않는다."""

    station_id: Annotated[
        int | str | None,
        Field(description='역 ID. 타입을 실측하지 못해 숫자·문자열을 모두 받는다', alias='stationId')
    ] = None
    station_name: Annotated[
        str | None,
        Field(description="역 이름. 개통 예정 연도가 괄호로 붙는다 ('탄천역(2027년예정)')", alias='stationName')
    ] = None
    rail_id: Annotated[
        int | str | None,
        Field(description='노선 ID. 타입을 실측하지 못해 숫자·문자열을 모두 받는다', alias='railId')
    ] = None
    rail_name: Annotated[
        str | None,
        Field(description="노선 이름 ('위례신사선(예정)')", alias='railName')
    ] = None
    open_date: Annotated[
        str | None,
        Field(description="개통 예정 연도 ('2027', 문자열)", alias='openDate')
    ] = None
    distance: Annotated[
        int | float | None,
        Field(description='매물에서의 거리 (m)')
    ] = None
    walking_time: Annotated[
        int | float | None,
        Field(description='도보 시간 (분)', alias='walkingTime')
    ] = None


class NaverDevelopmentJiguModel(NaverBaseResponseModel):
    """매물 근처 개발 지구 한 곳."""

    id: Annotated[
        int | str | None,
        Field(description='개발 지구 ID. 타입을 실측하지 못해 숫자·문자열을 모두 받는다')
    ] = None
    name: Annotated[
        str | None,
        Field(description='개발 지구 이름')
    ] = None
    type_name: Annotated[
        str | None,
        Field(description='개발 유형 이름', alias='typeName')
    ] = None
    step: Annotated[
        int | str | None,
        Field(description='진행 단계. 타입을 실측하지 못해 숫자·문자열을 모두 받는다')
    ] = None
    period: Annotated[
        str | None,
        Field(description="사업 기간 ('2010-07-14~2027-12-31'). 없을 수 있다")
    ] = None


class NaverDevelopmentArticleModel(NaverBaseResponseModel):
    """매물 근처 개발 예정. 두 목록 모두 빈 매물이 많다 (원룸은 `{"railList": [], "jiguList": []}`)."""

    # 한 목록이 null 로 와도 다른 목록까지 모름이 되지 않게 None 을 받는다 (service 가 그 목록만 null 로 낸다)
    rail_list: Annotated[
        list[NaverDevelopmentRailModel] | None,
        Field(description='근처 예정 지하철역', alias='railList')
    ] = []
    jigu_list: Annotated[
        list[NaverDevelopmentJiguModel] | None,
        Field(description='근처 개발 지구', alias='jiguList')
    ] = []


class NaverEducationBuildingSchoolV1ResponseModel(NaverResponseModel[list[NaverSchoolModel]]):
    """`GET /front-api/v1/education/building/school` 응답."""


class NaverBuildingRegistrationModel(NaverBaseResponseModel):
    """건축물대장 요약. 주차(parkingInfo)만 읽고 나머지(좌표·주소·용도·세대 수 등)는 내보내지 않아 extra 로 둔다."""

    parking_info: Annotated[
        NaverParkingInfoModel | None,
        Field(description='건축물대장의 주차 (총 대수, 세대당 대수)', alias='parkingInfo')
    ] = None


class NaverArticleKeyV1ResponseModel(NaverResponseModel[NaverArticleKeyModel]):
    """`GET /front-api/v1/article/key` 응답."""


class NaverComplexBuildingRegistrationV1ResponseModel(NaverResponseModel[NaverBuildingRegistrationModel]):
    """`GET /front-api/v1/complex/buildingRegistration` 응답."""


class NaverArticleBasicInfoV1ResponseModel(NaverResponseModel[NaverArticleBasicInfoModel]):
    """`GET /front-api/v1/article/basicInfo` 응답."""


class NaverArticleTaxV1ResponseModel(NaverResponseModel[NaverArticleTaxModel]):
    """`GET /front-api/v1/article/tax` 응답."""


class NaverArticleAgentFeeV1ResponseModel(NaverResponseModel[NaverArticleAgentFeeModel]):
    """`GET /front-api/v1/article/agentFee` 응답."""


class NaverArticleMaintenanceFeeV1ResponseModel(NaverResponseModel[NaverArticleMaintenanceFeeModel]):
    """`GET /front-api/v1/article/maintenanceFee` 응답."""


class NaverArticleOldMaintenanceFeeV1ResponseModel(NaverResponseModel[NaverArticleOldMaintenanceFeeModel]):
    """`GET /front-api/v1/article/oldMaintenanceFee` 응답."""


class NaverDevelopmentArticleV1ResponseModel(NaverResponseModel[NaverDevelopmentArticleModel]):
    """`GET /front-api/v1/development/article` 응답."""


class NaverComplexPyeongV1ResponseModel(NaverResponseModel[NaverPyeongModel]):
    """`GET /front-api/v1/complex/pyeong` 응답. 평형 하나. 항목 모양은 pyeongList 와 같다."""


class NaverLegalDivisionInfoListItemModel(NaverBaseResponseModel):
    """`legalDivision/infoList` 의 법정동 하나. 서버가 어느 칸이든 비워 줄 수 있어 모두 선택이다."""

    legal_division_number: Annotated[
        str | None,
        Field(description='법정동 코드 (10자리)', alias='legalDivisionNumber')
    ] = None
    legal_division_name: Annotated[
        str | None,
        Field(description='그 단위 이름만 (예: 용문면)', alias='legalDivisionName')
    ] = None
    legal_division_level_type: Annotated[
        str | None,
        Field(description='단위 (SI 시·도, GUN 시·군·구, EUP 읍·면·동)', alias='legalDivisionLevelType')
    ] = None
    region_name: Annotated[
        str | None,
        Field(description='시·도부터 이은 전체 이름 (예: 경기도 양평군 용문면, 서울시 중구 무교동). 웹 매물 화면의 위치 칸이 쓴다', alias='regionName')
    ] = None
    full_address: Annotated[
        str | None,
        Field(description='전체 주소', alias='fullAddress')
    ] = None


class NaverLegalDivisionInfoListV1ResponseModel(NaverResponseModel[dict[str, NaverLegalDivisionInfoListItemModel]]):
    """`GET /front-api/v1/legalDivision/infoList` 응답. `result` 는 법정동 코드를 키로 하는 사전이다."""
