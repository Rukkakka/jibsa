"""여러 기능이 같이 쓰는 응답 모델 (중첩·봉투·기반 모델)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# POST account.zigbang.com/v2/unauth/token
# ---------------------------------------------------------------------------

class ZigbangUnauthTokenV2ResponseModel(ResponseModel):
    """익명(게스트) 토큰 발급 응답."""

    result: Annotated[
        bool,
        Field(description='발급 성공 여부')
    ]
    token: Annotated[
        str,
        Field(repr=False, description='apis.zigbang.com 호출에 Bearer 로 붙이는 UUID 토큰')
    ]


class ZigbangSearchSourceModel(ResponseModel):
    """검색 결과의 원본 색인 문서. 결과 type 에 따라 채워지는 필드가 다르다."""

    local1: Annotated[
        str | None,
        Field(description='시/도 (예: 서울시)')
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시/군/구 (예: 강남구)')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동 (예: 역삼동)')
    ] = None
    step: Annotated[
        int | None,
        Field(description='행정 단계. 3 이면 동 단위')
    ] = None
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리)')
    ] = Field(default=None, alias='법정동코드')
    household: Annotated[
        int | None,
        Field(description='세대수 (단지 결과만)')
    ] = None
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD, 단지 결과만)')
    ] = Field(default=None, alias='사용승인일')


class ZigbangSearchItemModel(ResponseModel):
    """검색 결과 한 건 (지역·지하철역·학교·단지 등)."""

    id: Annotated[
        int,
        Field(description='결과 ID (2026-10-09 실측: 지역·역·학교·대학교·아파트·오피스텔 473건 모두 숫자)')
    ]
    type: Annotated[
        str,
        Field(description='결과 종류 (address, subway, school, apartment ...)')
    ]
    name: Annotated[
        str,
        Field(description='표시 이름')
    ]
    description: Annotated[
        str | None,
        Field(description='보조 설명. 지역이면 전체 주소')
    ] = None
    lat: Annotated[
        float | None,
        Field(description='중심 위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='중심 경도')
    ] = None
    source: Annotated[
        ZigbangSearchSourceModel | None,
        Field(description='원본 색인 문서')
    ] = Field(default=None, alias='_source')


class ZigbangItemPinModel(ResponseModel):
    """지도 핀 하나. 상세 정보 없이 ID 와 좌표만 담긴다."""

    id: Annotated[
        int,
        Field(description='매물 ID')
    ]
    lat: Annotated[
        float,
        Field(description='위도 (흐린 좌표)')
    ]
    lng: Annotated[
        float,
        Field(description='경도 (흐린 좌표)')
    ]
    user_no: Annotated[
        int | None,
        Field(description='등록한 중개사 회원번호')
    ] = Field(default=None, alias='userNo')
    building_id: Annotated[
        int | None,
        Field(description='오피스텔 건물 ID (오피스텔 핀만). /items/officetels/{buildingId} 에 넘긴다')
    ] = Field(default=None, alias='buildingId')


class ZigbangLatLngModel(ResponseModel):
    """좌표."""

    lat: Annotated[
        float,
        Field(description='위도')
    ]
    lng: Annotated[
        float,
        Field(description='경도')
    ]


# ---------------------------------------------------------------------------
# POST /house/property/v1/items/list
# ---------------------------------------------------------------------------

class ZigbangAreaModel(ResponseModel):
    """면적. ㎡ 와 평을 함께 준다."""

    m2: Annotated[
        float | None,
        Field(description='면적 (㎡)')
    ] = None
    p: Annotated[
        str | None,
        Field(description='면적 (평, 문자열)')
    ] = None


class ZigbangAddressOriginModel(ResponseModel):
    """행정 주소."""

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
    address2: Annotated[
        str | None,
        Field(description='지번 (목록 응답에만 존재)')
    ] = None
    full_text: Annotated[
        str | None,
        Field(description='전체 주소 텍스트')
    ] = Field(default=None, alias='fullText')


class ZigbangItemSummaryModel(ResponseModel):
    """매물 요약 한 건 (snake_case 필드 응답)."""

    item_id: Annotated[
        int,
        Field(description='매물 ID')
    ]
    sales_type: Annotated[
        str,
        Field(description='거래 유형 (전세, 월세, 매매). 단기임대도 월세로 오고 `contract` 로 구분한다')
    ]
    contract: Annotated[
        str | None,
        Field(description="계약 형태. 단기임대면 '단기', 아니면 빈 문자열")
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (만원). 매매 매물이면 매매가가 이 필드에 들어온다')
    ] = None
    rent: Annotated[
        int | None,
        Field(description='월세 (만원). 전세·매매는 0')
    ] = None
    size_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 원룸·빌라는 전용면적과 같지만 오피스텔은 다르다')
    ] = None
    exclusive_area: Annotated[
        ZigbangAreaModel | None,
        Field(description='전용면적')
    ] = Field(default=None, alias='전용면적')
    supply_area: Annotated[
        ZigbangAreaModel | None,
        Field(description='공급면적')
    ] = Field(default=None, alias='공급면적')
    floor: Annotated[
        str | None,
        Field(description="해당 층 (예 '2', '반지하', '옥탑방')")
    ] = None
    building_floor: Annotated[
        str | None,
        Field(description='건물 전체 층수')
    ] = None
    title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = None
    service_type: Annotated[
        str,
        Field(description='매물 유형 (원룸, 오피스텔, 빌라)')
    ]
    room_type: Annotated[
        str | None,
        Field(description='방 구조 코드 (01 오픈형원룸 ... 06 포룸이상)')
    ] = None
    manage_cost: Annotated[
        str | None,
        Field(description='월 관리비 (**원** 단위 문자열). 상세 응답과 단위가 다르다')
    ] = None
    location: Annotated[
        ZigbangLatLngModel | None,
        Field(description='좌표 (흐린 좌표)')
    ] = None
    address_origin: Annotated[
        ZigbangAddressOriginModel | None,
        Field(description='행정 주소')
    ] = Field(default=None, alias='addressOrigin')
    address1: Annotated[
        str | None,
        Field(description='주소 (시 구 동)')
    ] = None
    images_thumbnail: Annotated[
        str | None,
        Field(description='대표 이미지 URL')
    ] = None
    reg_date: Annotated[
        str | None,
        Field(description='등록 일시 (ISO 8601, +09:00)')
    ] = None
    is_new: Annotated[
        bool | None,
        Field(description='신규 매물 여부')
    ] = None
    status: Annotated[
        bool | None,
        Field(description='노출 중 여부')
    ] = None


class ZigbangItemsListV1ResponseModel(ResponseModel):
    """매물 요약 배치 응답.

    `items` (snake_case) 와 `itemSummaries` (camelCase) 가 같은 매물을 다른
    모양으로 담는다. 정규화에는 필드가 더 많은 `items` 를 쓴다. 토큰이
    잘못되거나 없어도 같은 결과가 200 으로 온다 (2026-10-11 실측: 가짜 토큰·토큰 없음 모두
    정상 요약. 상세·`/v3/items`·단지·단기임대 검색도 같다). 그래서 토큰 오류가 빈 결과로 숨지 않는다.
    """

    items: Annotated[
        list[ZigbangItemSummaryModel],
        Field(description='매물 요약 (snake_case)')
    ] = []
    total_count: Annotated[
        int,
        Field(description='반환된 매물 수')
    ] = Field(default=0, alias='totalCount')


class ZigbangSubwayBriefModel(ResponseModel):
    """매물 인근 지하철역."""

    id: Annotated[
        int,
        Field(description='역 ID')
    ]
    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    description: Annotated[
        str | None,
        Field(description='노선 (예: 2호선,3호선)')
    ] = None


class ZigbangRoomTypeTitleModel(ResponseModel):
    """아파트 평형 이름."""

    m2: Annotated[
        str | None,
        Field(description='공급면적 기준 평형 (㎡, 예: 80C)')
    ] = None
    p: Annotated[
        str | None,
        Field(description='공급면적 기준 평형 (평, 예: 24C)')
    ] = None


class ZigbangCatalogItemIdModel(ResponseModel):
    """카탈로그에 묶인 실제 매물 ID."""

    item_source: Annotated[
        str | None,
        Field(description="매물 출처. 'zigbang' 이면 `/v3/items/{itemId}` 로 상세를 볼 수 있다")
    ] = Field(default=None, alias='itemSource')
    item_id: Annotated[
        int,
        Field(description='매물 ID')
    ] = Field(alias='itemId')


class ZigbangItemCatalogModel(ResponseModel):
    """아파트 매물 카탈로그 한 건. 같은 호·거래 유형의 매물(중개사별)을 하나로 묶는다."""

    area_ho_id: Annotated[
        int | None,
        Field(description='호 ID')
    ] = Field(default=None, alias='areaHoId')
    tran_type: Annotated[
        str,
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세)')
    ] = Field(alias='tranType')
    item_type: Annotated[
        str | None,
        Field(description='매물 종류 (self_ad ...)')
    ] = Field(default=None, alias='itemType')
    area_danji_id: Annotated[
        int | None,
        Field(description='단지 ID')
    ] = Field(default=None, alias='areaDanjiId')
    area_danji_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = Field(default=None, alias='areaDanjiName')
    local2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    is_price_range: Annotated[
        bool | None,
        Field(description='묶인 매물끼리 가격이 달라 가격이 최솟값인지')
    ] = Field(default=None, alias='isPriceRange')
    deposit_min: Annotated[
        int | None,
        Field(description='매매가(매매) 또는 보증금·전세금 (만원). 가격이 범위면 최솟값')
    ] = Field(default=None, alias='depositMin')
    rent_min: Annotated[
        int | None,
        Field(description='월세 (만원). 매매·전세는 0')
    ] = Field(default=None, alias='rentMin')
    room_type_title: Annotated[
        ZigbangRoomTypeTitleModel | None,
        Field(description='평형 이름')
    ] = Field(default=None, alias='roomTypeTitle')
    size_contract_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = Field(default=None, alias='sizeContractM2')
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = Field(default=None, alias='sizeM2')
    dong: Annotated[
        str | None,
        Field(description='동 (예: 108동)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층. 숫자이거나 '저'·'중'·'고'")
    ] = None
    item_title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = Field(default=None, alias='itemTitle')
    item_count: Annotated[
        int | None,
        Field(description='묶인 매물 수')
    ] = Field(default=None, alias='itemCount')
    item_id_list: Annotated[
        list[ZigbangCatalogItemIdModel],
        Field(description='묶인 매물 ID')
    ] = Field(default=[], alias='itemIdList')


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}
# ---------------------------------------------------------------------------

class ZigbangDanjisResponseModel(ResponseModel):
    """아파트 단지 정보. 직방이 한글 키로 주는 값이 많다."""

    id: Annotated[
        int,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    local1: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='시/도를 뺀 지번 주소 (예: 강남구 개포동 660-1)')
    ] = Field(default=None, alias='jibunAddress')
    real_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트 ...)')
    ] = None
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD)')
    ] = Field(default=None, alias='사용승인일')
    households: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = Field(default=None, alias='총세대수')
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = Field(default=None, alias='총동수')
    max_floor: Annotated[
        int | None,
        Field(description='최고 층수')
    ] = Field(default=None, alias='최고층수')
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = Field(default=None, alias='시공사')
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = Field(default=None, alias='가구당주차대수')
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = Field(default=None, alias='용적율')
    heating: Annotated[
        str | None,
        Field(description='난방 방식 (지역난방, 개별난방 ...)')
    ] = Field(default=None, alias='난방방식')
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기 본문(resident_review)은 내보내지 않는다')
    ] = Field(default=None, alias='review_cnt')


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/item-catalogs
# ---------------------------------------------------------------------------

class ZigbangDanjiRoomTypeModel(ResponseModel):
    """단지 평형."""

    id: Annotated[
        int,
        Field(description='평형 ID (danjiRoomTypeIds 조건 값)')
    ]
    room_type_title: Annotated[
        ZigbangRoomTypeTitleModel | None,
        Field(description='평형 이름')
    ] = Field(default=None, alias='roomTypeTitle')


class ZigbangDanjisItemCatalogsResponseModel(ResponseModel):
    """단지 하나의 아파트 매물 카탈로그 응답. 카탈로그 모양은 지역 목록과 같다."""

    total_count: Annotated[
        int,
        Field(description='조건에 맞는 카탈로그 수 (페이지 무관)')
    ] = Field(default=0, alias='totalCount')
    count_by_tran_type: Annotated[
        dict[str, int],
        Field(description='거래 유형(trade·charter·rental)별 카탈로그 수. 거래 유형 조건을 반영한다')
    ] = Field(default={}, alias='itemCountPerTranType')
    room_types: Annotated[
        list[ZigbangDanjiRoomTypeModel],
        Field(description='단지의 평형 목록')
    ] = Field(default=[], alias='danjiRoomTypes')
    catalogs: Annotated[
        list[ZigbangItemCatalogModel],
        Field(description='이번 페이지의 카탈로그')
    ] = Field(default=[], alias='list')
