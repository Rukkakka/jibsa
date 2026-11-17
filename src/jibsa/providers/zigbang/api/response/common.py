"""여러 기능이 같이 쓰는 응답 모델 (중첩·봉투·기반 모델)."""

from pydantic import (
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from jibsa.core.schema import ResponseModel

from typing import (
    Annotated,
    Any,
    Self,
)


# ---------------------------------------------------------------------------
# 여러 엔드포인트가 같이 쓰는 중첩 모델 (검색 결과·지도 핀·좌표)
# ---------------------------------------------------------------------------

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
        Field(description='법정동코드 (10자리)', alias='법정동코드')
    ] = None
    household: Annotated[
        int | None,
        Field(description='세대수 (단지 결과만)')
    ] = None
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD, 단지 결과만)', alias='사용승인일')
    ] = None


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
        Field(description='원본 색인 문서', alias='_source')
    ] = None


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
        Field(description='등록한 중개사 회원번호', alias='userNo')
    ] = None
    building_id: Annotated[
        int | None,
        Field(description='오피스텔 건물 ID (오피스텔 핀만). /items/officetels/{buildingId} 에 넘긴다', alias='buildingId')
    ] = None


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
        Field(description='전체 주소 텍스트', alias='fullText')
    ] = None


class ZigbangWebItemSummaryModel(ResponseModel):
    """웹 목록 카드가 쓰는 매물 요약 한 건 (`itemSummaries`, camelCase). 관리비(`fee`)만 읽는다."""

    id: Annotated[
        int,
        Field(description='매물 ID')
    ]
    fee: Annotated[
        float | None,
        Field(description="월 관리비 (**원** 단위). 0 이면 웹이 '관리비 없음', null 이면 빈칸으로 보여 준다")
    ] = None


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
        Field(description='전용면적', alias='전용면적')
    ] = None
    supply_area: Annotated[
        ZigbangAreaModel | None,
        Field(description='공급면적', alias='공급면적')
    ] = None
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
        Field(description='월 관리비 (**원** 단위 문자열). 상세 응답과 단위가 다르다. 관리비 0원 매물도 null 로 와서 `web_fee` 를 우선한다')
    ] = None
    web_fee: Annotated[
        float | None,
        Field(description='웹 목록 카드의 관리비 (`itemSummaries[].fee`, **원** 단위). 같은 매물이 `itemSummaries` 에 있을 때만 응답 모델이 싣는다', exclude=True)
    ] = None
    location: Annotated[
        ZigbangLatLngModel | None,
        Field(description='좌표 (흐린 좌표)')
    ] = None
    address_origin: Annotated[
        ZigbangAddressOriginModel | None,
        Field(description='행정 주소', alias='addressOrigin')
    ] = None
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

    @property
    def listed_manage_cost(self) -> float | str | None:
        """목록에 낼 월 관리비 (원). 웹 목록 카드처럼 `web_fee` 를 실었으면 그 값(null 이면 모름), 싣지 않았으면 `manage_cost`."""
        # 속성에 대입한 필드도 model_fields_set 에 든다. 실은 값이 null 이어도 웹 값이라 manage_cost 로 넘어가지 않는다
        return self.web_fee if 'web_fee' in self.model_fields_set else self.manage_cost


class ZigbangItemsListV1ResponseModel(ResponseModel):
    """매물 요약 배치 응답.

    `items` (snake_case) 와 `itemSummaries` (camelCase) 가 같은 매물을 다른
    모양으로 담는다. 정규화에는 필드가 더 많은 `items` 를 쓰되, 웹 목록 카드가 보여 주는 관리비는
    `itemSummaries[].fee` 다 (관리비 0원 매물이 `items` 의 `manage_cost` 에서는 null 이다, 2026-11-15 실측).
    같은 ID 의 요약에 `fee` 를 실어 주므로(`web_fee`) 호출하는 쪽은 `items` 의 `listed_manage_cost` 만 본다. 토큰이
    잘못되거나 없어도 같은 결과가 200 으로 온다 (2026-10-11 실측: 가짜 토큰·토큰 없음 모두
    정상 요약. 상세·`/v3/items`·단지·단기임대 검색도 같다). jibsa 는 로그인하지 않은 웹처럼 토큰 없이 부른다.
    """

    items: Annotated[
        list[ZigbangItemSummaryModel],
        Field(description='매물 요약 (snake_case)')
    ] = []
    item_summaries: Annotated[
        list[ZigbangWebItemSummaryModel],
        Field(description='웹 목록 카드가 쓰는 매물 요약 (camelCase). 관리비를 `items` 에 실어 주는 데만 쓴다', alias='itemSummaries')
    ] = []
    total_count: Annotated[
        int,
        Field(description='반환된 매물 수', alias='totalCount')
    ] = 0

    @field_validator('item_summaries', mode='before')
    @classmethod
    def readable_summaries(cls, value: Any) -> Any:
        """관리비를 실을 수 있는 요약만 받는다. 관리비 한 칸 때문에 배치 전체(검색 요약·상세의 등록일)를 읽지 못하면 안 된다.

        목록이 아니면(null 등) 빈 목록, `ZigbangWebItemSummaryModel` 이 읽지 못하는 항목(ID 가 정수가 아니거나 관리비가
        숫자·null 이 아닌 '', '-' 등)은 빼서 그 매물은 `items` 의 `manage_cost` 로 돌아간다. 형식 규칙은 모델 한 곳에 둔다.
        """
        if not isinstance(value, list):
            return []
        summaries = []
        for summary in value:
            try:
                summaries.append(ZigbangWebItemSummaryModel.model_validate(summary))
            except ValidationError:
                continue
        return summaries

    @model_validator(mode='after')
    def attach_web_fee(self) -> Self:
        """같은 ID 의 `items` 요약에 웹 목록의 관리비(`fee`)를 실어 준다."""
        fee_by_id = {summary.id: summary.fee for summary in self.item_summaries}
        for summary in self.items:
            if summary.item_id in fee_by_id:
                summary.web_fee = fee_by_id[summary.item_id]
        return self


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
        Field(description="매물 출처. 'zigbang'(직방)·'coalition'(제휴) 이면 아파트 상세(`/apt/item-catalogs/items/{itemId}`)로 상세를 볼 수 있다", alias='itemSource')
    ] = None
    item_id: Annotated[
        int,
        Field(description='매물 ID', alias='itemId')
    ]


class ZigbangItemCatalogModel(ResponseModel):
    """아파트 매물 카탈로그 한 건. 같은 호·거래 유형의 매물(중개사별)을 하나로 묶는다."""

    area_ho_id: Annotated[
        int | None,
        Field(description='호 ID', alias='areaHoId')
    ] = None
    tran_type: Annotated[
        str,
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세)', alias='tranType')
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
        Field(description='묶인 매물끼리 가격이 달라 가격이 최솟값인지', alias='isPriceRange')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='매매가(매매) 또는 보증금·전세금 (만원). 가격이 범위면 최솟값', alias='depositMin')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 (만원). 매매·전세는 0', alias='rentMin')
    ] = None
    room_type_title: Annotated[
        ZigbangRoomTypeTitleModel | None,
        Field(description='평형 이름', alias='roomTypeTitle')
    ] = None
    size_contract_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)', alias='sizeContractM2')
    ] = None
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='sizeM2')
    ] = None
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
        Field(description='매물 제목', alias='itemTitle')
    ] = None
    item_count: Annotated[
        int | None,
        Field(description='묶인 매물 수', alias='itemCount')
    ] = None
    item_id_list: Annotated[
        list[ZigbangCatalogItemIdModel],
        Field(description='묶인 매물 ID', alias='itemIdList')
    ] = []


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
        Field(description='시/도를 뺀 지번 주소 (예: 강남구 개포동 660-1)', alias='jibunAddress')
    ] = None
    real_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트 ...)')
    ] = None
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD)', alias='사용승인일')
    ] = None
    households: Annotated[
        int | None,
        Field(description='총 세대수', alias='총세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수', alias='총동수')
    ] = None
    max_floor: Annotated[
        int | None,
        Field(description='최고 층수', alias='최고층수')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사', alias='시공사')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수', alias='가구당주차대수')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%)', alias='용적율')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 방식 (지역난방, 개별난방 ...)', alias='난방방식')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기 본문(resident_review)은 내보내지 않는다', alias='review_cnt')
    ] = None


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
        Field(description='평형 이름', alias='roomTypeTitle')
    ] = None


class ZigbangDanjisItemCatalogsResponseModel(ResponseModel):
    """단지 하나의 아파트 매물 카탈로그 응답. 카탈로그 모양은 지역 목록과 같다."""

    total_count: Annotated[
        int,
        Field(description='조건에 맞는 카탈로그 수 (페이지 무관)', alias='totalCount')
    ] = 0
    count_by_tran_type: Annotated[
        dict[str, int],
        Field(description='거래 유형(trade·charter·rental)별 카탈로그 수. 거래 유형 조건을 반영한다', alias='itemCountPerTranType')
    ] = {}
    room_types: Annotated[
        list[ZigbangDanjiRoomTypeModel],
        Field(description='단지의 평형 목록', alias='danjiRoomTypes')
    ] = []
    catalogs: Annotated[
        list[ZigbangItemCatalogModel],
        Field(description='이번 페이지의 카탈로그', alias='list')
    ] = []
