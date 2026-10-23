"""여러 기능이 같이 쓰는 응답 모델 (중첩·봉투·기반 모델)."""

from pydantic import (
    BeforeValidator,
    Field,
)

from jibsa.core.schema import ResponseModel

from typing import (
    Annotated,
    Any,
)


def _to_float(v: Any) -> Any:
    """스토어의 숫자는 문자열('29.75', '3.0')로 오기도 해서 float 로 바꾼다. 빈 문자열은 None."""
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None
    return v


def _to_str(v: Any) -> Any:
    """층 정보는 '3.0' 처럼 오므로 정수면 '3' 으로 다듬는다."""
    if v is None or v == '':
        return None
    try:
        number = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(number)) if number.is_integer() else str(number)


LooseFloat = Annotated[float | None, BeforeValidator(_to_float)]
FloorText = Annotated[str | None, BeforeValidator(_to_str)]


class DaangnCoordinateModel(ResponseModel):
    """좌표. 스토어에는 문자열로 들어 있다."""

    lat: Annotated[
        LooseFloat,
        Field(description='위도')
    ] = None
    lon: Annotated[
        LooseFloat,
        Field(description='경도')
    ] = None


class DaangnRegionModel(ResponseModel):
    """매물이 속한 지역."""

    name1: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    name2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    name3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    original_id: Annotated[
        int | None,
        Field(description='지역 ID', alias='originalId')
    ] = None
    depth: Annotated[
        int | None,
        Field(description='행정 단계. 3 이면 동/읍/면 (좌표 → 지역 조회에만)')
    ] = None
    center_coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='지역 중심 좌표', alias='centerCoordinate')
    ] = None


class DaangnSalesTypeModel(ResponseModel):
    """매물 용도."""

    type: Annotated[
        str,
        Field(description='APART, OFFICETEL, OFFICE, STORE, OPEN_ONE_ROOM, SPLIT_ONE_ROOM, TWO_ROOM, HOUSE ...')
    ]


class DaangnTradeModel(ResponseModel):
    """거래 조건. 금액은 모두 **만원**."""

    typename: Annotated[
        str | None,
        Field(description='MonthTrade / BuyTrade / BorrowTrade / ShortTrade', alias='__typename')
    ] = None
    type: Annotated[
        str,
        Field(description='MONTH(월세), BUY(매매), BORROW(전세), SHORT(단기임대)')
    ]
    preferred: Annotated[
        bool | None,
        Field(description='대표 거래 조건 여부')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 또는 전세금 (만원)')
    ] = None
    monthly_pay: Annotated[
        int | None,
        Field(description='월세 (만원)', alias='monthlyPay')
    ] = None
    price: Annotated[
        int | None,
        Field(description='매매가 (만원)')
    ] = None
    description: Annotated[
        str | None,
        Field(description='거래 조건 메모')
    ] = None


class DaangnSubwayStationModel(ResponseModel):
    """지하철역."""

    station_name: Annotated[
        str | None,
        Field(description='역 이름', alias='stationName')
    ] = None
    line_number: Annotated[
        list[str],
        Field(description='노선', alias='lineNumber')
    ] = []


class DaangnNearBySubwayStationModel(ResponseModel):
    """인근 지하철역과 도보 시간."""

    station: Annotated[
        DaangnSubwayStationModel | None,
        Field(description='역')
    ] = None
    duration_minutes: Annotated[
        int | None,
        Field(description='도보 소요 시간 (분)', alias='durationMinutes')
    ] = None


class DaangnNearbySubwayStationEdgeModel(ResponseModel):
    """주변 지하철역 연결의 edge (상세 페이지에만). 역 이름에 '역' 이 붙지 않는다 (예: 역삼)."""

    node: Annotated[
        DaangnSubwayStationModel | None,
        Field(description='역 (이름만)')
    ] = None


class DaangnImageModel(ResponseModel):
    """매물 사진."""

    thumbnail: Annotated[
        str | None,
        Field(description='썸네일 URL (300x300)')
    ] = None


class DaangnBizProfileModel(ResponseModel):
    """중개사무소 비즈프로필. 목록 페이지에서는 이름이 비어 있다."""

    original_id: Annotated[
        str | None,
        Field(description='비즈프로필 ID', alias='originalId')
    ] = None
    name: Annotated[
        str | None,
        Field(description='중개사무소명')
    ] = None
    business_company_name: Annotated[
        str | None,
        Field(description='사업자 상호 (상세 페이지에만)', alias='businessCompanyName')
    ] = None
    license_owner_contact: Annotated[
        str | None,
        Field(description='등록 중개사무소 연락처 (상세 페이지에만)', alias='licenseOwnerContact')
    ] = None
    license_registration_number: Annotated[
        str | None,
        Field(description='중개사무소 등록번호 (상세 페이지에만)', alias='licenseRegistrationNumber')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='사무소 도로명 주소 (상세 페이지에만)', alias='roadAddress')
    ] = None


class DaangnArticleOptionModel(ResponseModel):
    """옵션 한 항목 (상세 페이지에만)."""

    name: Annotated[
        str,
        Field(description='옵션 코드 (PARKING, WASHER, AIRCON, PET, MORTGAGE ...)')
    ]
    value: Annotated[
        str | None,
        Field(description='YES / NO / DONT_KNOW')
    ] = None


class DaangnManageCostOptionModel(ResponseModel):
    """관리비 항목 한 건 (상세 페이지에만).

    중개사 매물(`manageCostChargeType` 있음)은 법정 표기라 `payOption` 이 FIXED(정액, 관리비에 포함)·
    USED(쓴 만큼 따로)·NONE(없음)·NEED_TO_CHECK(확인 필요) 다. 직거래 매물은 관리비에 포함된 항목만
    오고 `payOption` 이 비어 있기도 하다 (미포함 항목은 `excludeManageCostOption`).
    """

    option: Annotated[
        str,
        Field(description='COMMON(공용), ELECTRIC, WATERWORKS, GAS, BOILER, INTERNET, TV, PARKING, CLEANING, ELEVATOR, ETC')
    ]
    pay_option: Annotated[
        str | None,
        Field(description='FIXED / USED / NONE / NEED_TO_CHECK', alias='payOption')
    ] = None
    fixed_cost: Annotated[
        LooseFloat,
        Field(description='정액 금액 (만원, FIXED 일 때)', alias='fixedCost')
    ] = None
    custom_option_name: Annotated[
        str | None,
        Field(description='ETC 항목의 직접 입력 이름', alias='customOptionName')
    ] = None


class DaangnBrokerCommissionModel(ResponseModel):
    """거래 조건별 중개보수 (상세 페이지에만). 당근이 법정 상한 요율로 계산한 값이며 **원** 단위 문자열이다.

    직거래 매물에도 계산값이 붙어 온다.
    """

    trade_type: Annotated[
        str | None,
        Field(description='MONTH / BORROW / BUY / SHORT', alias='tradeType')
    ] = None
    commission: Annotated[
        LooseFloat,
        Field(description='중개보수 (원, 부가세 별도)')
    ] = None
    vat: Annotated[
        LooseFloat,
        Field(description='부가세 (원)')
    ] = None
    total: Annotated[
        LooseFloat,
        Field(description='중개보수 + 부가세 (원)')
    ] = None


class DaangnComplexRefModel(ResponseModel):
    """매물이 속한 단지 (아파트·오피스텔 등). 목록 피드에는 `originalId` 가 없고 상세 페이지에만 있다."""

    original_id: Annotated[
        str | None,
        Field(description='숫자 단지 ID. 단지 페이지 /complexes/{originalId}', alias='originalId')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='APARTMENT, OFFICETEL, MIXED_USE(주상복합) ...')
    ] = None


class DaangnArticleModel(ResponseModel):
    """`__typename == "Article"` 레코드를 참조까지 펼친 것.

    목록(map) 페이지와 상세(articles) 페이지가 같은 타입을 쓰지만 상세 페이지에만
    채워지는 필드가 많아 대부분 optional 이다.
    """

    original_id: Annotated[
        str,
        Field(description='숫자 매물 ID. 상세 URL /articles/{originalId}', alias='originalId')
    ]
    area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area: Annotated[
        LooseFloat,
        Field(description='공급면적 (㎡)', alias='supplyArea')
    ] = None
    floor: Annotated[
        FloorText,
        Field(description='해당 층')
    ] = None
    top_floor: Annotated[
        FloorText,
        Field(description='건물 최고층', alias='topFloor')
    ] = None
    is_ambiguous_floor: Annotated[
        bool | None,
        Field(description='층을 숫자 대신 저층·중층·고층으로만 밝혔는지. 그러면 floor 가 비어 있다', alias='isAmbiguousFloor')
    ] = None
    ambiguous_floor: Annotated[
        str | None,
        Field(description='LOW(저층) / MIDDLE(중층) / HIGH(고층)', alias='ambiguousFloor')
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='건물/단지 이름', alias='buildingName')
    ] = None
    address_info: Annotated[
        str | None,
        Field(description='작성자가 쓴 한 줄 소개 (목록에서 제목처럼 쓰인다)', alias='addressInfo')
    ] = None
    status: Annotated[
        str | None,
        Field(description='거래 상태. ON_GOING 만 거래 가능 (그 외 예약·거래완료 등)')
    ] = None
    is_hide: Annotated[
        bool | None,
        Field(description='숨김 여부', alias='isHide')
    ] = None
    invisible_reason: Annotated[
        str | None,
        Field(description='노출 제한 사유 (예: CHECK_DENY). 있으면 거래할 수 없는 매물', alias='invisibleReason')
    ] = None
    invisible_infos: Annotated[
        list[dict[str, Any]] | None,
        Field(description='노출 제한 정보 (GraphQL 피드). 비어 있지 않으면 거래할 수 없는 매물', alias='invisibleInfos')
    ] = None
    writer_type: Annotated[
        str | None,
        Field(description='작성자 유형 (BROKER, LESSOR ...)', alias='writerTypeV2')
    ] = None
    sales_type: Annotated[
        DaangnSalesTypeModel | None,
        Field(description='매물 용도', alias='salesTypeV3')
    ] = None
    trades: Annotated[
        list[DaangnTradeModel],
        Field(description='거래 조건 (여러 개일 수 있음)')
    ] = []
    region: Annotated[
        DaangnRegionModel | None,
        Field(description='소속 지역')
    ] = None
    public_coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='공개 좌표', alias='publicCoordinate')
    ] = None
    subway_stations: Annotated[
        list[DaangnNearBySubwayStationModel],
        Field(description='인근 지하철역 (도보 시간 포함). 상세 페이지에서는 비어 있기도 하다', alias='subwayStations')
    ] = []
    nearby_subway_stations: Annotated[
        list[DaangnNearbySubwayStationEdgeModel],
        Field(description='주변 지하철역 이름 (상세 페이지에만). subwayStations 가 비어도 채워져 있기도 하다', alias='nearbySubwayStations')
    ] = []
    images: Annotated[
        list[DaangnImageModel],
        Field(description='사진')
    ] = []
    biz_profile: Annotated[
        DaangnBizProfileModel | None,
        Field(description='중개사무소 비즈프로필', alias='bizProfile')
    ] = None
    content: Annotated[
        str | None,
        Field(description='본문 (상세 페이지에만)')
    ] = None
    public_address: Annotated[
        str | None,
        Field(description='도로명 주소 (상세 페이지에만)', alias='publicAddress')
    ] = None
    public_jibun_address: Annotated[
        str | None,
        Field(description='지번 주소 (상세 페이지에만)', alias='publicJibunAddress')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCnt')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathroomCnt')
    ] = None
    total_manage_cost: Annotated[
        LooseFloat,
        Field(description='월 관리비 (만원)', alias='totalManageCost')
    ] = None
    manage_cost_charge_type: Annotated[
        str | None,
        Field(description='관리비 부과 방식 (FIXED, ETC, UNAVAILABLE). 중개사 매물에만 있고 직거래는 null', alias='manageCostChargeType')
    ] = None
    manage_cost_detail_is_disclosed: Annotated[
        bool | None,
        Field(description='관리비 항목을 밝혔는지. False 면 항목 목록은 빈 껍데기다', alias='manageCostDetailIsDisclosed')
    ] = None
    manage_cost_options: Annotated[
        list[DaangnManageCostOptionModel] | None,
        Field(description='관리비 항목 (상세 페이지에만)', alias='includeManageCostOptionV3')
    ] = None
    exclude_manage_cost_options: Annotated[
        list[str] | None,
        Field(description='관리비에 포함되지 않는 항목 코드 (직거래 매물, 상세 페이지에만)', alias='excludeManageCostOption')
    ] = None
    premium_money: Annotated[
        LooseFloat,
        Field(description='권리금 (만원, 상가). 상세 페이지에만', alias='premiumMoney')
    ] = None
    premium_money_negotiable: Annotated[
        bool | None,
        Field(description='권리금 협의 가능 여부. 협의 가능이면 권리금이 1만원처럼 자리만 채운 값이기도 하다', alias='premiumMoneyNegotiable')
    ] = None
    broker_commissions: Annotated[
        list[DaangnBrokerCommissionModel] | None,
        Field(description='거래 조건별 중개보수 (상세 페이지에만)', alias='brokerCommissions')
    ] = None
    watch_count: Annotated[
        int | None,
        Field(description='관심(찜) 수', alias='watchCount')
    ] = None
    complex: Annotated[
        DaangnComplexRefModel | None,
        Field(description='매물이 속한 단지. 단지가 없는 매물(원룸·빌라 등)은 null')
    ] = None
    move_in_date: Annotated[
        str | None,
        Field(description='입주 가능일 (YYYY-MM-DD)', alias='moveInDate')
    ] = None
    move_in_date_negotiable: Annotated[
        bool | None,
        Field(description='입주일 협의 가능 여부', alias='moveInDateNegotiable')
    ] = None
    building_approval_date: Annotated[
        str | None,
        Field(description='사용승인일', alias='buildingApprovalDate')
    ] = None
    building_orientation: Annotated[
        str | None,
        Field(description='방향 (SOUTH_FACING ...)', alias='buildingOrientation')
    ] = None
    building_usage: Annotated[
        str | None,
        Field(description='건축물 용도 코드', alias='buildingUsage')
    ] = None
    available_total_parking_spots: Annotated[
        int | None,
        Field(description='주차 가능 대수', alias='availableTotalParkingSpots')
    ] = None
    options: Annotated[
        list[DaangnArticleOptionModel],
        Field(description='옵션 (상세 페이지에만)')
    ] = []
    published_at: Annotated[
        str | None,
        Field(description='게시 일시 (UTC ISO 8601)', alias='publishedAt')
    ] = None
    updated_at: Annotated[
        str | None,
        Field(description='수정 일시 (UTC ISO 8601)', alias='updatedAt')
    ] = None
    view_count: Annotated[
        int | None,
        Field(description='조회수', alias='viewCount')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 공통
# ---------------------------------------------------------------------------

class DaangnGraphQLErrorModel(ResponseModel):
    """GraphQL 에러 한 건. 잘못된 조건에도 이유 없이 "알 수 없는 오류" 가 온다."""

    message: Annotated[
        str | None,
        Field(description='에러 메시지')
    ] = None
    extensions: Annotated[
        dict[str, Any] | None,
        Field(description='에러 코드 등 (예: code=PERSISTED_QUERY_NOT_IN_LIST)')
    ] = None


class DaangnGraphQLResponseModel(ResponseModel):
    """GraphQL 응답 공통. 실패도 HTTP 200 에 `errors` 로 온다."""

    errors: Annotated[
        list[DaangnGraphQLErrorModel],
        Field(description='에러. 없으면 []')
    ] = []


class DaangnPageInfoModel(ResponseModel):
    """커서 페이지 정보."""

    end_cursor: Annotated[
        str | None,
        Field(description='다음 페이지를 받을 커서', alias='endCursor')
    ] = None
    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 존재 여부', alias='hasNextPage')
    ] = None


class DaangnLiveArticleCountModel(ResponseModel):
    """단지의 현재 매물 수."""

    total: Annotated[
        int | None,
        Field(description='매물 수')
    ] = None


class DaangnTransactionModel(ResponseModel):
    """국토부 실거래 한 건. 매매(`TransactionBuy`)와 전월세(`TransactionRent`)가 필드를 나눠 쓴다. 금액은 **만원**."""

    typename: Annotated[
        str | None,
        Field(description='TransactionBuy / TransactionRent', alias='__typename')
    ] = None
    original_id: Annotated[
        str | None,
        Field(description='거래 ID', alias='originalId')
    ] = None
    deal_year: Annotated[
        int | None,
        Field(description='계약 연도', alias='dealYear')
    ] = None
    deal_month: Annotated[
        int | None,
        Field(description='계약 월', alias='dealMonth')
    ] = None
    deal_day: Annotated[
        int | None,
        Field(description='계약 일', alias='dealDay')
    ] = None
    exclusive_use_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)', alias='exclusiveUseArea')
    ] = None
    floor: Annotated[
        FloorText,
        Field(description='층')
    ] = None
    deal_amount: Annotated[
        int | None,
        Field(description='매매가 (만원, 매매만)', alias='dealAmount')
    ] = None
    deal_canceled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)', alias='dealCanceled')
    ] = None
    registrated_at: Annotated[
        str | None,
        Field(description='등기일. 있으면 등기까지 마친 거래 (매매만)', alias='registratedAt')
    ] = None
    ownership: Annotated[
        str | None,
        Field(description='REGISTERED_OWNER / PRE_SALE_RIGHT(분양권) / PRE_SALE_OWNER(입주권) (매매만)')
    ] = None
    type: Annotated[
        str | None,
        Field(description='BORROW(전세) / MONTHLY(월세) (전월세만)')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (만원, 전월세만)')
    ] = None
    monthly_rent: Annotated[
        int | None,
        Field(description='월세 (만원, 전월세만)', alias='monthlyRent')
    ] = None
    contract_type: Annotated[
        str | None,
        Field(description='NEW(신규) / RENEWAL(재계약) (전월세만)', alias='contractType')
    ] = None
    use_renewal_of_contract_right: Annotated[
        bool | None,
        Field(description='계약갱신요구권을 쓴 계약 (전월세만)', alias='useRenewalOfContractRight')
    ] = None


class DaangnTransactionEdgeModel(ResponseModel):
    """실거래 연결의 edge."""

    node: Annotated[
        DaangnTransactionModel | None,
        Field(description='거래')
    ] = None


class DaangnTransactionConnectionModel(ResponseModel):
    """실거래 연결. 최근 계약 순이다."""

    edges: Annotated[
        list[DaangnTransactionEdgeModel],
        Field(description='거래')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnRealsaleDanjiModel(ResponseModel):
    """거래가 난 건물·단지 (공공 데이터). 빌라 같은 소규모 건물도 있다."""

    name: Annotated[
        str | None,
        Field(description='건물·단지 이름', alias='danjiAreaNm')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수', alias='totalTotHsehCnt')
    ] = None
    build_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)', alias='buildDate')
    ] = None


class DaangnCommuteArticleModel(ResponseModel):
    """역 주변 매물. 카드에 상태·종류·주소가 없어 ID 만 쓰고 `articlesByOriginalArticleIds` 로 다시 받는다."""

    article: Annotated[
        DaangnArticleModel | None,
        Field(description='매물 (일부 필드만)')
    ] = None


class DaangnCommuteArticleEdgeModel(ResponseModel):
    """역 주변 매물 edge."""

    node: Annotated[
        DaangnCommuteArticleModel | None,
        Field(description='매물')
    ] = None


class DaangnCommuteStationArticleConnectionModel(ResponseModel):
    """역 주변 매물 연결."""

    edges: Annotated[
        list[DaangnCommuteArticleEdgeModel],
        Field(description='매물')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnCompareRegionModel(ResponseModel):
    """단지 지역."""

    name1: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    name2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    name3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None


class DaangnTradeArticleCountModel(ResponseModel):
    """단지의 거래 유형별 현재 매물 수."""

    buy: Annotated[
        int | None,
        Field(description='매매 매물 수')
    ] = None
    borrow: Annotated[
        int | None,
        Field(description='전세 매물 수')
    ] = None
    month: Annotated[
        int | None,
        Field(description='월세 매물 수')
    ] = None


class DaangnLivedReviewPreviewModel(ResponseModel):
    """단지 목록 카드의 거주 후기 미리보기. 본문은 내보내지 않으므로 있는지만 본다."""

    edges: Annotated[
        list[dict[str, Any]],
        Field(description='후기 (웹은 1건만 받는다)')
    ] = []


class DaangnRegionComplexNodeModel(ResponseModel):
    """지역 단지 목록의 단지 카드."""

    original_id: Annotated[
        str,
        Field(description='숫자 단지 ID', alias='originalId')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT, OFFICETEL, MIXED_USE ...')
    ] = None
    danji: Annotated[
        DaangnRealsaleDanjiModel | None,
        Field(description='세대수·사용승인일 (공공 데이터)', alias='proptierDanji')
    ] = None
    transactions: Annotated[
        DaangnTransactionConnectionModel | None,
        Field(description=(
            '요청한 거래 유형의 최근 실거래 10건 (최근 계약 순). 계약일·층은 없고, 전월세는 전세·월세가 섞여 온다 '
            '(월세 0 이면 전세)'
        ))
    ] = None
    live_article_count: Annotated[
        DaangnTradeArticleCountModel | None,
        Field(description='거래 유형별 현재 매물 수', alias='liveArticleCount')
    ] = None
    near_station: Annotated[
        bool | None,
        Field(description='역 가까운 단지 (당근 기준)', alias='nearStation')
    ] = None
    lived_reviews: Annotated[
        DaangnLivedReviewPreviewModel | None,
        Field(description='거주 후기 미리보기', alias='livedReviews')
    ] = None
    lived_review_summary: Annotated[
        dict[str, Any] | None,
        Field(description='당근이 후기로 만든 요약. 내보내지 않고 있는지만 본다', alias='livedReviewSummary')
    ] = None
