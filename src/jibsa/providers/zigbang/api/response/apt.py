"""응답 모델: 아파트 매물 검색 (search listings apt), 아파트 매물 상세 (listing), 매물 묶음과 호 정보 (catalog)."""

from pydantic import Field, field_validator

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangItemCatalogModel,
    ZigbangRoomTypeTitleModel,
)

from typing import Annotated, Any


# ---------------------------------------------------------------------------
# GET /apt/locals/{localCode}/item-catalogs
# ---------------------------------------------------------------------------

class ZigbangLocalsItemCatalogsResponseModel(ResponseModel):
    """지역 아파트 매물 카탈로그 응답."""

    local_code: Annotated[
        str | None,
        Field(description='조회한 지역 코드', alias='localCode')
    ] = None
    count: Annotated[
        int,
        Field(description='조건에 맞는 카탈로그 수 (페이지 무관)')
    ] = 0
    catalogs: Annotated[
        list[ZigbangItemCatalogModel],
        Field(description='이번 페이지의 카탈로그', alias='list')
    ] = []
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


# ---------------------------------------------------------------------------
# GET /apt/locals/polygon
# ---------------------------------------------------------------------------

class ZigbangLocalsPolygonResponseModel(ResponseModel):
    """geohash 칸 중심이 속한 동 (예: `{code: '11650108', name: '서초동', geojson: null}`). 경계(geojson)는 읽지 않는다."""

    code: Annotated[
        str | None,
        Field(description='직방 지역 코드. local3 이면 법정동코드 앞 8자리 (2026-11-15 실측)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='동 이름')
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
    period_basis: Annotated[
        str | None,
        Field(description="관리비 산출 기준 문구 (예: '최근 3개월 관리비 평균'). 기타 관리비(etcManageCost)에만 온다", alias='periodBasis')
    ] = None
    cost_basis_description: Annotated[
        str | None,
        Field(description='관리비 부과 방식 설명 (웹 문구 그대로). 기타 관리비(etcManageCost)에만 온다', alias='costBasisDescription')
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


class ZigbangAptRoomTypeInfoModel(ResponseModel):
    """아파트 매물 상세의 평형 정보. 이 밖에 평면도 그림 주소(`floorPlanImageUrl`)가 오지만 쓰지 않는다 (사진은 내보내지 않는다)."""

    danji_room_type_id: Annotated[
        int | None,
        Field(description='평형 ID. 단지 정보(complex)의 pyeongs[].id·--pyeong 값과 같다', alias='danjiRoomTypeId')
    ] = None
    room_type_title: Annotated[
        ZigbangRoomTypeTitleModel | None,
        Field(description='평형 이름 (m2 는 공급면적 ㎡ 기준, p 는 평 기준)', alias='roomTypeTitle')
    ] = None


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
    room_type_info: Annotated[
        ZigbangAptRoomTypeInfoModel | None,
        Field(description='평형 정보 (평형 ID·이름)', alias='roomTypeInfo')
    ] = None
    effectiveness_updated_at: Annotated[
        str | None,
        Field(description="매물 확인 시각 (ISO 8601, +09:00. 예: 2026-11-16T11:49:20+09:00). 웹은 이것으로 '2주 전 확인' 을 만든다", alias='effectivenessUpdatedAt')
    ] = None
    is_actual_item_checked: Annotated[
        bool | None,
        Field(description="직방 웹의 '실매물 확인' 배지", alias='isActualItemChecked')
    ] = None
    has_violations: Annotated[
        bool | None,
        Field(description='위반 건축물 여부. 제휴 매물은 키가 없다', alias='hasViolations')
    ] = None
    real_type: Annotated[
        str | None,
        Field(description='중개대상물 종류 (예: 아파트). 제휴 매물은 키가 없다', alias='realType')
    ] = None
    is_hug_lessor: Annotated[
        bool | None,
        Field(description='HUG 임대인 여부 (직방 필드 isHugLessor 그대로. 2026-11-19 표본 51262299 는 false). 키가 없으면 None (모름)', alias='isHugLessor')
    ] = None
    zzim_count: Annotated[
        int | None,
        Field(description='찜 수. 키가 없으면 None (모름)', alias='zzimCount')
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
# GET /apt/item-catalogs/{areaHoId}/ho-info
# ---------------------------------------------------------------------------

class ZigbangHoPriceModel(ResponseModel):
    """호의 직방 시세 하나 (매매 또는 전세)."""

    price: Annotated[
        int | None,
        Field(description='시세 (만원)')
    ] = None
    pyeong_price: Annotated[
        int | float | None,
        Field(description='평당 시세 (만원/3.3㎡)', alias='pyeongPrice')
    ] = None


class ZigbangHoZigbangPriceModel(ResponseModel):
    """호의 직방 시세. 호 ID(`areahoId`)는 읽지 않는다."""

    trade: Annotated[
        ZigbangHoPriceModel | None,
        Field(description='매매 시세')
    ] = None
    charter: Annotated[
        ZigbangHoPriceModel | None,
        Field(description='전세 시세')
    ] = None


class ZigbangHoPublicPriceModel(ResponseModel):
    """공시가격 한 해."""

    year: Annotated[
        int,
        Field(description='공시 연도')
    ]
    price: Annotated[
        int | None,
        Field(description='공시가격 (**원** 단위, 예: 2077000000). 다른 금액 필드와 단위가 다르다')
    ] = None
    compare_price_rate: Annotated[
        int | float | None,
        Field(description='전년 대비 변동률 (%, 부호 있음. 예: 26.9, -28, 0)', alias='comparePriceRate')
    ] = None


class ZigbangHoPresalePriceModel(ResponseModel):
    """호의 분양가 (키 이름이 한글이다). 금액은 **만원**이다."""

    ho: Annotated[
        int | None,
        Field(description='그 호의 분양가 (만원). 2026-11-19 표본은 null', alias='ho분양가')
    ] = None
    average_ho: Annotated[
        int | float | None,
        Field(description='호 평균 분양가 (만원, 키 averageHo분양가). 2026-11-19 표본은 null', alias='averageHo분양가')
    ] = None
    room_type: Annotated[
        int | float | None,
        Field(description='이 호가 속한 타입(평형)의 분양가 (만원). 웹은 호 분양가가 없을 때 이 값을 보여 준다 (2026-11-19 표본 12966062 는 88560)', alias='roomType분양가')
    ] = None
    pyeong_price: Annotated[
        int | float | None,
        Field(
            description='평당 분양가 (만원/3.3㎡). 웹이 보여 주는 분양가(`ho분양가 ?? roomType분양가`)의 평당가다 (표본 12966062: 88560 ÷ 공급 32.7평 = 2712)',
            alias='pyeongPrice'
        )
    ] = None


class ZigbangHoPriceInfoModel(ResponseModel):
    """호의 가격 정보. 시세 변동 차트 여부(`hasRtPrices`)는 읽지 않는다."""

    zigbang_price: Annotated[
        ZigbangHoZigbangPriceModel | None,
        Field(description='직방 시세', alias='zigbangPrice')
    ] = None
    public_prices: Annotated[
        list[ZigbangHoPublicPriceModel] | None,
        Field(description='공시가격 (최근 해부터. 2026-11-19 표본은 2026~2022 다섯 해). 키가 없거나 null 이면 None (모름)', alias='publicPrices')
    ] = None
    presale: Annotated[
        ZigbangHoPresalePriceModel | None,
        Field(description='분양가', alias='분양가')
    ] = None


class ZigbangItemCatalogsHoInfoResponseModel(ResponseModel):
    """아파트 매물 묶음의 호 정보. 단지·동·면적·관리비·VR·평면도 같은 이 밖의 키는 읽지 않는다 (사진·좌표는 내보내지 않는다)."""

    price_info: Annotated[
        ZigbangHoPriceInfoModel | None,
        Field(description='가격 정보 (직방 시세·공시가격·분양가)', alias='priceInfo')
    ] = None
