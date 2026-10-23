"""여러 기능이 같이 쓰는 응답 모델 (중첩·봉투·기반 모델)."""

from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import ResponseModel

from typing import (
    Annotated,
    Any,
    Generic,
    TypeVar,
)


T = TypeVar('T')


class NaverResponseModel(ResponseModel, Generic[T]):
    """모든 front-api 응답의 봉투. 실제 데이터는 `result`.

    금액 필드는 모두 **원** 단위 정수다 (직방·당근은 만원).
    """

    is_success: Annotated[
        bool,
        Field(description='성공 여부', alias='isSuccess')
    ]
    detail_code: Annotated[
        str | None,
        Field(description='상세 코드 (success, TOO_MANY_REQUESTS ...)', alias='detailCode')
    ] = None
    message: Annotated[
        str | None,
        Field(description='에러 메시지')
    ] = None
    result: Annotated[
        T | None,
        Field(description='실제 데이터. 실패 응답이면 None')
    ] = None

    @model_validator(mode='before')
    @classmethod
    def drop_result_on_failure(cls, data: Any) -> Any:
        # 내려간 매물 등 실패 응답은 `{"isSuccess": false, "result": {}}` 로 와서
        # 빈 result 가 검증에 걸린다. 실패면 result 를 버리고 None 으로 둔다.
        if isinstance(data, dict) and data.get('isSuccess') is False:
            return {**data, 'result': None}
        return data


class NaverCoordinatesModel(ResponseModel):
    """좌표. x 가 경도, y 가 위도."""

    x_coordinate: Annotated[
        float,
        Field(description='경도', alias='xCoordinate')
    ]
    y_coordinate: Annotated[
        float,
        Field(description='위도', alias='yCoordinate')
    ]


class NaverComplexAddressModel(ResponseModel):
    """단지 주소."""

    legal_division_number: Annotated[
        str | None,
        Field(description='법정동 코드', alias='legalDivisionNumber')
    ] = None
    city: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    division: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    sector: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    jibun: Annotated[
        str | None,
        Field(description='지번')
    ] = None
    road_name: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadName')
    ] = None
    zip_code: Annotated[
        str | None,
        Field(description='우편번호', alias='zipCode')
    ] = None


class NaverParkingInfoModel(ResponseModel):
    """주차."""

    total_parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수', alias='totalParkingCount')
    ] = None
    parking_count_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수', alias='parkingCountPerHousehold')
    ] = None


class NaverBuildingRatioInfoModel(ResponseModel):
    """용적률·건폐율."""

    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%)', alias='floorAreaRatio')
    ] = None
    building_coverage_ratio: Annotated[
        float | None,
        Field(description='건폐율 (%)', alias='buildingCoverageRatio')
    ] = None


class NaverComplexModel(ResponseModel):
    """단지 종합정보."""

    name: Annotated[
        str,
        Field(description='단지명')
    ]
    type: Annotated[
        str | None,
        Field(description='단지 유형 코드 (A01 아파트 ...)')
    ] = None
    address: Annotated[
        NaverComplexAddressModel | None,
        Field(description='주소')
    ] = None
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='좌표')
    ] = None
    total_household_number: Annotated[
        int | None,
        Field(description='총 세대수', alias='totalHouseholdNumber')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수', alias='dongCount')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사', alias='constructionCompany')
    ] = None
    use_approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD)', alias='useApprovalDate')
    ] = None
    approval_elapsed_year: Annotated[
        int | None,
        Field(description='준공 후 경과 연수', alias='approvalElapsedYear')
    ] = None
    building_ratio_info: Annotated[
        NaverBuildingRatioInfoModel | None,
        Field(description='용적률·건폐율', alias='buildingRatioInfo')
    ] = None
    parking_info: Annotated[
        NaverParkingInfoModel | None,
        Field(description='주차', alias='parkingInfo')
    ] = None
    highest_dong_floor: Annotated[
        int | None,
        Field(description='최고층', alias='highestDongFloor')
    ] = None
    lowest_dong_floor: Annotated[
        int | None,
        Field(description='최저층', alias='lowestDongFloor')
    ] = None
    management_office_contact: Annotated[
        str | None,
        Field(description='관리사무소 연락처', alias='managementOfficeContact')
    ] = None


class NaverComplexArticleCountModel(ResponseModel):
    """거래 유형별 매물 수."""

    deal_count: Annotated[
        int,
        Field(description='매매', alias='dealCount')
    ] = 0
    lease_deposit_count: Annotated[
        int,
        Field(description='전세', alias='leaseDepositCount')
    ] = 0
    lease_monthly_count: Annotated[
        int,
        Field(description='월세', alias='leaseMonthlyCount')
    ] = 0
    lease_short_term: Annotated[
        int,
        Field(description='단기임대', alias='leaseShortTerm')
    ] = 0


class NaverComplexArticlePriceModel(ResponseModel):
    """호가 범위 (원)."""

    deal_min_price: Annotated[
        int | None,
        Field(description='매매 최저 호가 (원)', alias='dealMinPrice')
    ] = None
    deal_max_price: Annotated[
        int | None,
        Field(description='매매 최고 호가 (원)', alias='dealMaxPrice')
    ] = None
    rent_min_price: Annotated[
        int | None,
        Field(description='전세 최저 호가 (원)', alias='rentMinPrice')
    ] = None
    rent_max_price: Annotated[
        int | None,
        Field(description='전세 최고 호가 (원)', alias='rentMaxPrice')
    ] = None


class NaverComplexArticleStatsModel(ResponseModel):
    """단지 매물 통계: 거래 유형별 매물 수와 호가 범위."""

    count: Annotated[
        NaverComplexArticleCountModel,
        Field(description='거래 유형별 매물 수')
    ] = Field(default_factory=NaverComplexArticleCountModel)
    price: Annotated[
        NaverComplexArticlePriceModel,
        Field(description='호가 범위 (원)')
    ] = Field(default_factory=NaverComplexArticlePriceModel)


class NaverBuildingModel(ResponseModel):
    """단지의 동 한 개. 좌표도 오지만 쓰지 않는다."""

    number: Annotated[
        int,
        Field(description='동 번호. 단지 매물 목록의 dongNumbers 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='동 이름 (예: 101, 가). 화면은 뒤에 동을 붙여 쓴다')
    ]
    use_approval_date: Annotated[
        str | None,
        Field(description='동의 사용승인일 (YYYYMMDD). 빌라 동 목록에만 온다', alias='useApprovalDate')
    ] = None


class NaverPriceRangeModel(ResponseModel):
    """시세 범위 (하한 floor, 상한 ceiling)."""

    floor: Annotated[
        float | None,
        Field(description='하한')
    ] = None
    ceiling: Annotated[
        float | None,
        Field(description='상한')
    ] = None


class NaverSchoolModel(ResponseModel):
    """배정 초등학교 한 곳. 좌표도 오지만 쓰지 않는다."""

    code: Annotated[
        str | None,
        Field(description='학교 코드 (education/school 의 schoolCode)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='설립·운영 구분 (공립, 사립, 혁신 ...)', alias='operationType')
    ] = None
    allocation_type: Annotated[
        str | None,
        Field(description='배정 방식 (사이트 ARTICLE_SCHOOL_ALLOCATION_TYPE: 01 자동, 02 선택)', alias='allocationType')
    ] = None
    students_per_classroom: Annotated[
        float | None,
        Field(description='학급당 학생 수', alias='studentsPerClassroom')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수', alias='studentsPerTeacher')
    ] = None
    distance: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    walking_minute: Annotated[
        int | None,
        Field(description='도보 시간 (분)', alias='walkingMinute')
    ] = None


class NaverPyeongModel(ResponseModel):
    """평형 한 개."""

    number: Annotated[
        int,
        Field(description='평형 번호. 평형 단위 API 의 pyeongTypeNumber')
    ]
    name: Annotated[
        str,
        Field(description='평형 이름 (공급면적 ㎡, 예: 160, 201A)')
    ]
    supply_area: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 전용+주거공용이라 평형 이름보다 작다', alias='supplyArea')
    ] = None
    contract_area: Annotated[
        float | None,
        Field(description='계약면적 (㎡). 오피스텔 평형 이름과 매물 상세의 공급면적이 이 값이다', alias='contractArea')
    ] = None
    exclusive_area: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='exclusiveArea')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCount')
    ] = None
    bath_room_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathRoomCount')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='해당 평형 세대수', alias='householdCount')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='대표 방향 코드')
    ] = None


class NaverPropertyTaxModel(ResponseModel):
    """재산세 (원)."""

    property_tax: Annotated[
        int | None,
        Field(description='재산세', alias='propertyTax')
    ] = None
    local_education_tax: Annotated[
        int | None,
        Field(description='지방교육세', alias='localEducationTax')
    ] = None
    urban_area_segment_tax: Annotated[
        int | None,
        Field(description='도시지역분', alias='urbanAreaSegmentTax')
    ] = None


class NaverTotalRealEstateTaxModel(ResponseModel):
    """종합부동산세 (원)."""

    total_real_estate_tax: Annotated[
        int | None,
        Field(description='종합부동산세', alias='totalRealEstateTax')
    ] = None
    rural_special_tax: Annotated[
        int | None,
        Field(description='농어촌특별세', alias='ruralSpecialTax')
    ] = None


class NaverLegalDivisionModel(ResponseModel):
    """좌표가 속한 법정동."""

    legal_division_number: Annotated[
        str,
        Field(description='법정동 코드 (10자리)', alias='legalDivisionNumber')
    ]
    legal_division_name: Annotated[
        str | None,
        Field(description='법정동 전체 이름', alias='legalDivisionName')
    ] = None
    city_name: Annotated[
        str | None,
        Field(description='시/도', alias='cityName')
    ] = None
    division_name: Annotated[
        str | None,
        Field(description='시/군/구', alias='divisionName')
    ] = None
    sector_name: Annotated[
        str | None,
        Field(description='읍/면/동', alias='sectorName')
    ] = None


class NaverFacilityInfoModel(ResponseModel):
    """시설.

    생활·보안·기타·냉방 시설 목록은 고른 것이 없으면 null 이 아니라 빈 목록으로 온다 (2026-10-14 실측: 신림동 원룸 상세
    `"security": []`). 그래서 목록 필드는 None 을 받지 않는다.
    """

    life: Annotated[
        list[str],
        Field(description='생활시설')
    ] = []
    security: Annotated[
        list[str],
        Field(description='보안시설')
    ] = []
    etc: Annotated[
        list[str],
        Field(description='기타시설')
    ] = []
    aircon: Annotated[
        list[str],
        Field(description='냉방시설')
    ] = []
    total_parking_count: Annotated[
        int | None,
        Field(
            description='총 주차 대수. 단지가 없는 원룸·빌라·단독(C01·C02·C03)에도 온다. 단지 매물은 매물마다 값이 달라 '
            '단지 정보와 다를 수 있다 (강남역센트럴푸르지오시티 단지 398대, 같은 단지 매물 343대·398대, 2026-10-10)',
            alias='totalParkingCount'
        )
    ] = None
    is_parking_possible: Annotated[
        bool | None,
        Field(description='이 매물의 주차 가능 여부. 주차 대수가 있어도 불가일 수 있다. 단지 매물은 빠지기도 한다', alias='isParkingPossible')
    ] = None
    building_conjunction_date: Annotated[
        str | None,
        Field(description="건물 날짜 (YYYYMMDD). 종류 코드가 'CDY01' 이면 사용승인일. 목록의 buildingInfo 와 같은 값", alias='buildingConjunctionDate')
    ] = None
    building_conjunction_date_type: Annotated[
        str | None,
        Field(description="날짜 종류 코드. 'CDY01' 만 확인됨 (사용승인일)", alias='buildingConjunctionDateType')
    ] = None


class NaverListSpaceInfoModel(ResponseModel):
    """목록의 면적."""

    supply_space: Annotated[
        float | None,
        Field(description='공급면적 (㎡)', alias='supplySpace')
    ] = None
    exclusive_space: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='exclusiveSpace')
    ] = None
    supply_space_name: Annotated[
        str | None,
        Field(description='평형 이름', alias='supplySpaceName')
    ] = None


class NaverListFloorDetailModel(ResponseModel):
    """목록의 층."""

    target_floor: Annotated[
        str | None,
        Field(description='해당 층', alias='targetFloor')
    ] = None
    total_floor: Annotated[
        str | None,
        Field(description='전체 층', alias='totalFloor')
    ] = None


class NaverListArticleDetailModel(ResponseModel):
    """목록의 매물 설명."""

    direction: Annotated[
        str | None,
        Field(description='방향 코드')
    ] = None
    article_feature_description: Annotated[
        str | None,
        Field(description='한 줄 특징', alias='articleFeatureDescription')
    ] = None
    floor_info: Annotated[
        str | None,
        Field(description='층/전체층 (예: 18/21)', alias='floorInfo')
    ] = None
    floor_detail_info: Annotated[
        NaverListFloorDetailModel | None,
        Field(description='층 상세', alias='floorDetailInfo')
    ] = None


class NaverListAddressModel(ResponseModel):
    """목록의 주소."""

    city: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    division: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    sector: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='좌표')
    ] = None


class NaverListPriceInfoModel(ResponseModel):
    """목록의 가격 (원)."""

    deal_price: Annotated[
        int | None,
        Field(description='매매가 (원)', alias='dealPrice')
    ] = None
    warranty_price: Annotated[
        int | None,
        Field(description='보증금 또는 전세금 (원)', alias='warrantyPrice')
    ] = None
    rent_price: Annotated[
        int | None,
        Field(description='월세 (원)', alias='rentPrice')
    ] = None
    management_fee_amount: Annotated[
        int | None,
        Field(description='월 관리비 (원)', alias='managementFeeAmount')
    ] = None
    price_change_status: Annotated[
        int | None,
        Field(description='가격 변동 (-1 인하, 0 없음, 1 인상)', alias='priceChangeStatus')
    ] = None


class NaverListBrokerInfoModel(ResponseModel):
    """목록의 중개 정보."""

    brokerage_name: Annotated[
        str | None,
        Field(description='중개사무소명', alias='brokerageName')
    ] = None
    cp_id: Annotated[
        str | None,
        Field(description='매물 제공 CP', alias='cpId')
    ] = None


class NaverListVerificationInfoModel(ResponseModel):
    """목록의 확인 정보."""

    verification_type: Annotated[
        str | None,
        Field(description='확인 방식 (OWNER, S_VR ...)', alias='verificationType')
    ] = None
    exposure_start_date: Annotated[
        str | None,
        Field(description='노출 시작일', alias='exposureStartDate')
    ] = None
    article_confirm_date: Annotated[
        str | None,
        Field(description='확인일', alias='articleConfirmDate')
    ] = None


class NaverListMediaModel(ResponseModel):
    """목록의 대표 사진."""

    image_url: Annotated[
        str | None,
        Field(description='대표 이미지 URL', alias='imageUrl')
    ] = None
    image_count: Annotated[
        int | None,
        Field(description='사진 수', alias='imageCount')
    ] = None


class NaverListBuildingInfoModel(ResponseModel):
    """건물 정보. 날짜는 `naver complex` 의 사용승인일(useApprovalDate)과 같다."""

    building_conjunction_date: Annotated[
        str | None,
        Field(description="건물 날짜 (YYYYMMDD). 종류 코드가 'CDY01' 이면 사용승인일", alias='buildingConjunctionDate')
    ] = None
    building_conjunction_date_type: Annotated[
        str | None,
        Field(description="날짜 종류 코드. 'CDY01' 만 확인됨 (사용승인일)", alias='buildingConjunctionDateType')
    ] = None
    approval_elapsed_year: Annotated[
        int | None,
        Field(description='사용승인 후 경과 연수', alias='approvalElapsedYear')
    ] = None


class NaverArticleInfoModel(ResponseModel):
    """목록의 매물 한 건."""

    article_number: Annotated[
        str,
        Field(description='매물 번호', alias='articleNumber')
    ]
    article_name: Annotated[
        str | None,
        Field(description='매물 이름 (단지명)', alias='articleName')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지명', alias='complexName')
    ] = None
    complex_number: Annotated[
        int | None,
        Field(description='단지 번호', alias='complexNumber')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description='동', alias='dongName')
    ] = None
    trade_type: Annotated[
        str,
        Field(description='거래 유형 코드 (A1 매매, B1 전세, B2 월세, B3 단기)', alias='tradeType')
    ]
    real_estate_type: Annotated[
        str,
        Field(description='매물 유형 코드 (A01 아파트, A02 오피스텔, C02 빌라 ...)', alias='realEstateType')
    ]
    space_info: Annotated[
        NaverListSpaceInfoModel | None,
        Field(description='면적', alias='spaceInfo')
    ] = None
    article_detail: Annotated[
        NaverListArticleDetailModel | None,
        Field(description='층·방향·특징', alias='articleDetail')
    ] = None
    address: Annotated[
        NaverListAddressModel | None,
        Field(description='주소')
    ] = None
    price_info: Annotated[
        NaverListPriceInfoModel | None,
        Field(description='가격 (원)', alias='priceInfo')
    ] = None
    broker_info: Annotated[
        NaverListBrokerInfoModel | None,
        Field(description='중개 정보', alias='brokerInfo')
    ] = None
    verification_info: Annotated[
        NaverListVerificationInfoModel | None,
        Field(description='확인 정보', alias='verificationInfo')
    ] = None
    article_media: Annotated[
        NaverListMediaModel | None,
        Field(description='사진', alias='articleMedia')
    ] = None
    building_info: Annotated[
        NaverListBuildingInfoModel | None,
        Field(description='건물 정보 (사용승인일)', alias='buildingInfo')
    ] = None


class NaverDuplicatedArticleInfoModel(ResponseModel):
    """같은 매물을 여러 중개사가 올린 묶음. 원본은 매우 커서 수만 남긴다."""

    realtor_count: Annotated[
        int | None,
        Field(description='같은 매물을 올린 중개사 수', alias='realtorCount')
    ] = None
    direct_trade_count: Annotated[
        int | None,
        Field(description='직거래 수', alias='directTradeCount')
    ] = None


class NaverArticleListItemModel(ResponseModel):
    """목록 항목: 대표 매물 + 중복 묶음."""

    representative_article_info: Annotated[
        NaverArticleInfoModel,
        Field(description='대표 매물', alias='representativeArticleInfo')
    ]
    duplicated_article_info: Annotated[
        NaverDuplicatedArticleInfoModel | None,
        Field(description='중복 묶음 요약', alias='duplicatedArticleInfo')
    ] = None


class NaverArticlePageModel(ResponseModel):
    """커서 페이지."""

    total_count: Annotated[
        int,
        Field(description='전체 매물 수', alias='totalCount')
    ] = 0
    has_next_page: Annotated[
        bool,
        Field(description='다음 페이지 존재 여부', alias='hasNextPage')
    ] = False
    seed: Annotated[
        str | None,
        Field(description='정렬 seed. 다음 요청에 그대로 넘긴다')
    ] = None
    last_info: Annotated[
        Any,
        Field(description='커서. 다음 요청에 그대로 넘긴다 (리스트 또는 정수)', alias='lastInfo')
    ] = None
    items: Annotated[
        list[NaverArticleListItemModel],
        Field(description='매물', alias='list')
    ] = []


class NaverComplexListAddressModel(NaverComplexAddressModel):
    """단지 목록의 주소. 거리를 재려고 좌표도 받는다 (출력하지 않는다)."""

    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='단지 좌표')
    ] = None


class NaverComplexListInfoModel(ResponseModel):
    """단지 목록의 단지 정보 (아파트·오피스텔은 complexInfo, 빌라 단지는 villaInfo 로 같은 모양)."""

    complex_number: Annotated[
        int,
        Field(description='단지 번호', alias='complexNumber')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    type: Annotated[
        str | None,
        Field(description='단지 유형 코드')
    ] = None
    building_count: Annotated[
        int | None,
        Field(description='동 수', alias='buildingCount')
    ] = None
    total_household_number: Annotated[
        int | None,
        Field(description='총 세대수', alias='totalHouseholdNumber')
    ] = None
    address: Annotated[
        NaverComplexListAddressModel | None,
        Field(description='주소')
    ] = None
    use_approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD)', alias='useApprovalDate')
    ] = None


class NaverComplexListEntryModel(ResponseModel):
    """단지 목록 한 곳의 본문. 대표 사진·주민 댓글(mostRecentComment)도 오지만 쓰지 않는다."""

    complex_info: Annotated[
        NaverComplexListInfoModel | None,
        Field(description='아파트·오피스텔 단지 정보', alias='complexInfo')
    ] = None
    villa_info: Annotated[
        NaverComplexListInfoModel | None,
        Field(description='빌라 단지 정보', alias='villaInfo')
    ] = None
    article_price_info: Annotated[
        NaverComplexArticlePriceModel | None,
        Field(description='호가 범위 (원). 매물이 없으면 빈 객체', alias='articlePriceInfoDto')
    ] = None
    article_count_info: Annotated[
        NaverComplexArticleCountModel | None,
        Field(description='거래 유형별 매물 수', alias='articleCountInfoDto')
    ] = None


class NaverComplexListItemModel(ResponseModel):
    """단지 목록 항목. type 이 COMPLEX 면 complex, VILLA 면 villa 에 본문이 있다."""

    type: Annotated[
        str | None,
        Field(description='COMPLEX / VILLA')
    ] = None
    complex: Annotated[
        NaverComplexListEntryModel | None,
        Field(description='아파트·오피스텔 단지')
    ] = None
    villa: Annotated[
        NaverComplexListEntryModel | None,
        Field(description='빌라 단지')
    ] = None


class NaverComplexListPageModel(ResponseModel):
    """단지 목록 커서 페이지."""

    total_count: Annotated[
        int,
        Field(description='전체 단지 수', alias='totalCount')
    ] = 0
    has_next_page: Annotated[
        bool,
        Field(description='다음 페이지 존재 여부', alias='hasNextPage')
    ] = False
    seed: Annotated[
        str | None,
        Field(description='정렬 seed. 다음 요청에 그대로 넘긴다')
    ] = None
    last_info: Annotated[
        list[Any] | None,
        Field(description='커서. 다음 요청에 그대로 넘긴다', alias='lastInfo')
    ] = None
    items: Annotated[
        list[NaverComplexListItemModel],
        Field(description='단지', alias='list')
    ] = []


class NaverRedevelopmentAreaInfoModel(ResponseModel):
    """재개발 구역 기본 정보."""

    redevelopment_area_number: Annotated[
        int,
        Field(description='구역 번호. 구역 매물 목록의 redevelopmentAreaNumber', alias='redevelopmentAreaNumber')
    ]
    name: Annotated[
        str | None,
        Field(description='구역 이름 (예: 한남4재정비촉진구역)')
    ] = None
    total_household_number: Annotated[
        int | None,
        Field(description='계획 세대수', alias='totalHouseholdNumber')
    ] = None
    business_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 조합설립인가, 사업시행인가)', alias='businessStep')
    ] = None


class NaverRedevelopmentAreaPriceModel(ResponseModel):
    """구역 매물의 호가 범위 (원). 그 거래 유형 매물이 없으면 키가 오지 않는다."""

    deal_min_price: Annotated[
        int | None,
        Field(description='매매 최저가', alias='dealMinPrice')
    ] = None
    deal_max_price: Annotated[
        int | None,
        Field(description='매매 최고가', alias='dealMaxPrice')
    ] = None


class NaverRedevelopmentAreaCountModel(ResponseModel):
    """구역 매물 수 (거래 유형별)."""

    deal_count: Annotated[
        int,
        Field(description='매매', alias='dealCount')
    ] = 0
    lease_deposit_count: Annotated[
        int,
        Field(description='전세', alias='leaseDepositCount')
    ] = 0
    lease_monthly_count: Annotated[
        int,
        Field(description='월세', alias='leaseMonthlyCount')
    ] = 0
    lease_short_term: Annotated[
        int,
        Field(description='단기임대', alias='leaseShortTerm')
    ] = 0


class NaverRedevelopmentAreaItemModel(ResponseModel):
    """재개발 구역 목록의 구역 한 곳. 좌표는 오지 않아 마커(redevelopmentArea/markers)로 받는다."""

    info: Annotated[
        NaverRedevelopmentAreaInfoModel,
        Field(description='구역 정보', alias='redevelopmentAreaInfoDto')
    ]
    price: Annotated[
        NaverRedevelopmentAreaPriceModel | None,
        Field(description='호가 범위', alias='articlePriceInfoDto')
    ] = None
    count: Annotated[
        NaverRedevelopmentAreaCountModel | None,
        Field(description='매물 수', alias='articleCountInfoDto')
    ] = None


class NaverRedevelopmentAreaPageModel(ResponseModel):
    """재개발 구역 목록 커서 페이지."""

    total_count: Annotated[
        int,
        Field(description='전체 구역 수', alias='totalCount')
    ] = 0
    has_next_page: Annotated[
        bool,
        Field(description='다음 페이지 존재 여부', alias='hasNextPage')
    ] = False
    seed: Annotated[
        str | None,
        Field(description='정렬 seed. 다음 요청에 그대로 넘긴다')
    ] = None
    last_info: Annotated[
        list[Any] | None,
        Field(description='커서. 다음 요청에 그대로 넘긴다', alias='lastInfo')
    ] = None
    items: Annotated[
        list[NaverRedevelopmentAreaItemModel],
        Field(description='구역', alias='list')
    ] = []


class NaverComplexV1ResponseModel(NaverResponseModel[NaverComplexModel]):
    """`GET /front-api/v1/complex` 응답."""


class NaverComplexVillaV1ResponseModel(NaverResponseModel[NaverComplexModel]):
    """`GET /front-api/v1/complex/villa` 응답. 아파트 단지와 같은 모양이고 동 수·건설사가 없다."""


class NaverComplexVillaPyeongListV1ResponseModel(NaverResponseModel[list[NaverPyeongModel]]):
    """`GET /front-api/v1/complex/villa/pyeongList` 응답. 방 수가 없다."""


class NaverComplexPyeongListV1ResponseModel(NaverResponseModel[list[NaverPyeongModel]]):
    """`GET /front-api/v1/complex/pyeongList` 응답."""


class NaverComplexBuildingListV1ResponseModel(NaverResponseModel[list[NaverBuildingModel]]):
    """`GET /front-api/v1/complex/buildingList` 응답."""


class NaverComplexVillaBuildingListV1ResponseModel(NaverResponseModel[list[NaverBuildingModel]]):
    """`GET /front-api/v1/complex/villa/buildingList` 응답."""


class NaverLegalDivisionSearchByCoordinateV1ResponseModel(NaverResponseModel[NaverLegalDivisionModel]):
    """`GET /front-api/v1/legalDivision/searchByCoordinate` 응답."""
