"""단지 매물 목록과 매물 상세의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    ListingDetail,
)
from jibsa.providers.naver.service.common.constants import (
    BADGES_DESCRIPTION,
    CONFIRMED_AT_DESCRIPTION,
    NOT_APPLICABLE_FIELDS_BY_TYPE,
)
from jibsa.providers.naver.service.common.models import NaverAssignedSchool
from jibsa.providers.naver.service.listing.constants import (
    ALL_TAX_TYPES,
    GENERAL_PRE_SALE_STATUS,
    NO_TAX_TYPES,
    PRE_SALE_TYPES,
    SALE_TAX_FIELDS,
)

from typing import (
    Annotated,
    Any,
)


class NaverNearbyRail(BaseModel):
    """매물 근처에 생길 지하철역 한 곳. 좌표·ID 는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="역 이름 (서버 글자 그대로, 개통 예정 연도가 붙는다: '탄천역(2027년예정)')")
    ] = None
    line: Annotated[
        str | None,
        Field(description="노선 이름 (서버 글자 그대로: '위례신사선(예정)')")
    ] = None
    open_year: Annotated[
        int | None,
        Field(description='개통 예정 연도 (2027). 없거나 숫자로 읽지 못하면 null')
    ] = None
    distance_m: Annotated[
        int | float | None,
        Field(description='매물에서의 거리 (m)')
    ] = None
    walk_minutes: Annotated[
        int | float | None,
        Field(description='도보 시간 (분)')
    ] = None


class NaverNearbyArea(BaseModel):
    """매물 근처 개발 지구 한 곳. 사업 기간이 없으면 `project_period` 키를 뺀다 (웹도 그 줄을 그리지 않는다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='개발 지구 이름. 빈 글자나 없으면 null')
    ] = None
    type: Annotated[
        str | None,
        Field(description="사업 종류 ('재개발' 등, 서버 글자 그대로). 빈 글자나 없으면 null")
    ] = None
    step: Annotated[
        int | str | None,
        Field(description='사업 단계 (서버 값 그대로). 빈 글자나 없으면 null')
    ] = None
    project_period: Annotated[
        str | None,
        Field(description="사업 기간 ('2010-07-14~2027-12-31', 서버 글자 그대로). 없으면 키를 뺀다")
    ] = None

    @model_serializer(mode='wrap')
    def drop_missing_period(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.project_period is None:
            data.pop('project_period', None)
        return data


class NaverNearbyDevelopment(BaseModel):
    """매물 근처의 개발 예정 (네이버 웹 상세의 '주변 개발 예정'). 두 목록이 모두 빌 수 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rail: Annotated[
        list[NaverNearbyRail] | None,
        Field(description='근처 예정 지하철역. 없으면 [], 네이버가 이 목록만 비워(null) 주면 null(모름)')
    ] = []
    area: Annotated[
        list[NaverNearbyArea] | None,
        Field(description='근처 개발 지구. 없으면 [], 네이버가 이 목록만 비워(null) 주면 null(모름)')
    ] = []


class NaverListingDetail(ListingDetail):
    """상세 조회로 보강한 네이버 매물. 단지 번호로 실거래가·단지 정보를 이어서 조회할 수 있다.

    `notes`: 덤 조회가 실패한 [실패] 안내 등. CLI 가 결과 위에 붙인다
    """

    complex_id: Annotated[
        int | None,
        Field(description='단지 번호 (naver complex / real-price 에 넘긴다)')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지명')
    ] = None
    building_dong: Annotated[
        str | None,
        Field(description="건물 동 ('1')")
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description='평형 ID (naver real-price --pyeong 에 넘긴다)')
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='건물 이름 (네이버 웹 제목의 건물 이름 규칙. 단지가 아닌 빌라·원룸 등). 단지 매물과 이름이 없는 건물은 키를 뺀다. 상세 정보를 못 읽었으면 null')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description="건물 세부 유형 (네이버 화면 글자: '빌라', '다세대', '일반원룸' ... 토지는 지목 '대'·'전'·'임야' 등, 사무실·숙박 등은 그 구분 '대형사무실' 등). 코드를 못 읽으면 '알 수 없는 값 (코드)'. 단지 매물은 키를 뺀다. 모르면 null")
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 네이버가 계약면적만 줘서 null')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡, 공급 + 주차장 등 기타 공용). 오피스텔만')
    ] = None
    heating: Annotated[
        str | None,
        Field(description="난방 방식 ('개별난방', '중앙난방', '지역난방' ...). 알리지 않았거나 모르면 null. 코드를 못 읽으면 '알 수 없는 값 (코드)'. 웹처럼 아파트·오피스텔·재건축·분양권은 매물에 없으면 단지의 난방, 단지형 빌라는 단지(/complex/villa)의 난방만 쓴다")
    ] = None
    heating_fuel: Annotated[
        str | None,
        Field(description="난방 연료 ('도시가스', '열병합', '전기' ...). 알리지 않았거나 모르면 null. 코드를 못 읽으면 '알 수 없는 값 (코드)'. 난방 방식과 같게 아파트·오피스텔·재건축·분양권은 매물에 없으면 단지의 연료, 단지형 빌라는 단지의 연료만 쓴다")
    ] = None
    entrance: Annotated[
        str | None,
        Field(description="현관 구조 ('계단식', '복도식', '복합식'). 모르면 null. 코드를 못 읽으면 '알 수 없는 값 (코드)'. 웹처럼 아파트·오피스텔·재건축·분양권은 매물에 없으면 평형(/complex/pyeong)의 현관 구조를 쓴다")
    ] = None
    parking: Annotated[
        str | None,
        Field(description="주차 ('가능', '불가', 대수가 있으면 '가능 (총 4대)'. 가능 여부를 모르면 대수만). 웹처럼 아파트·오피스텔·재건축·분양권은 단지 전체 대수만 ('단지 전체 12602대 (세대당 1.32대)', 가능 여부 없음)이고, 단지형 빌라는 매물 대수가 0이거나 없으면 단지 대수를 붙인다 ('가능 (단지 전체 8대, 세대당 0.5대)'). 원룸·빌라·단독 등 건축물대장 유형(15개)은 매물 주차 대수가 0 이거나 없으면 건축물대장의 총 주차 대수를 쓰고 (대장에 대수가 없으면 가능 여부만), 대수를 가져온 쪽에 세대당 대수가 0보다 크면 '가능 (총 8대, 세대당 0.5대)' 로 붙인다")
    ] = None
    badges: Annotated[
        list[str] | None,
        Field(description=BADGES_DESCRIPTION)
    ] = None
    confirmed_date: Annotated[
        str | None,
        Field(description=CONFIRMED_AT_DESCRIPTION)
    ] = None
    loan_manwon: Annotated[
        float | None,
        Field(description='융자금 (만원)')
    ] = None
    broker_fee_manwon: Annotated[
        float | None,
        Field(description="중개보수 상한 (만원, 네이버 계산). 네이버가 '개별확인' 으로 보여 주는 매물(broker_fee_individual_check_required)이면 null. 조회가 실패하거나 값이 없어도 null. 직거래면 키 없음, 직거래인지 모르면 null")
    ] = None
    broker_fee_individual_check_required: Annotated[
        bool | None,
        Field(description="중개보수를 네이버가 금액 대신 '개별확인' 으로 보여 주는 매물인지 (중개사에게 따로 확인). true 면 broker_fee_manwon 은 null. 조회가 실패하면 null. 직거래면 키 없음, 직거래인지 모르면 null")
    ] = None
    acquisition_tax_manwon: Annotated[
        float | None,
        Field(description='취득세 합계 (만원, 취득세 + 지방교육세 + 농어촌특별세. 네이버 계산. 매매만. 분양 상태를 모르는 분양권 매매는 요청하지 않아 null)')
    ] = None
    property_tax_manwon: Annotated[
        float | None,
        Field(description='연 재산세 합계 (만원, 재산세 + 지방교육세 + 도시지역분. 공시가 기준 네이버 계산. 아파트·재건축·단지형 빌라(A01·A04·A05~A07) 매매만)')
    ] = None
    comprehensive_real_estate_tax_manwon: Annotated[
        float | None,
        Field(description='연 종합부동산세 합계 (만원, 종부세 + 농어촌특별세. 공시가 기준 네이버 계산. 아파트·재건축·단지형 빌라(A01·A04·A05~A07) 매매만)')
    ] = None
    # 상세 출력에서 가장 긴 필드지만 매물 하나에 한 번이라 줄이지 않는다. 통근을 따질 때 버스만 닿는 동네가 있다
    # (2026-10-23 실측: 강남역 근처 원룸 상세 1,078자 중 381자, 약 120토큰)
    bus_routes: Annotated[
        dict[str, list[str]] | None,
        Field(description='주변 정류장의 버스 노선 (종류별, 예: {"간선": ["146", "341"]}). 조회 실패면 null')
    ] = None
    schools: Annotated[
        list[NaverAssignedSchool] | None,
        Field(description='배정 초등학교. 조회 실패면 null. 단지·동 번호가 없는 매물은 네이버가 주지 않아 키를 뺀다')
    ] = None
    nearby_development: Annotated[
        NaverNearbyDevelopment | None,
        Field(description='주변 개발 예정 (예정 지하철역 rail, 개발 지구 area). 네이버 웹은 모든 매물 상세에 그린다. 서버가 빈 목록을 주면 각각 []. 조회 실패면 null')
    ] = None
    has_school_lookup: Annotated[
        bool,
        Field(exclude=True, description='배정 학교를 조회하는 매물인지 (단지·동 번호가 있음). schools 가 해당 없는지 가리는 데만 쓴다')
    ] = False
    has_article_detail: Annotated[
        bool,
        Field(exclude=True, description='상세 정보(articleDetailInfo)를 읽었는지. 못 읽었으면 건물 이름·세부 유형이 해당 없음이 아니라 모름(null)이다')
    ] = False
    is_direct_trade: Annotated[
        bool,
        Field(exclude=True, description='직거래 매물인지 (참일 때만 참, 모르면 거짓). 중개보수가 해당 없는지 가리는 데만 쓴다')
    ] = False
    pre_sale_status_type: Annotated[
        str | None,
        Field(exclude=True, description="분양권 상태 코드 ('10' 일반분양권). 분양권 매매의 세금 칸이 해당 없는지 가리는 데만 쓴다. 모르면 null")
    ] = None
    real_estate_type: Annotated[
        str | None,
        Field(exclude=True, description='네이버 매물 유형 코드 (A01 …). 유형마다 웹에 없는 칸을 가리는 데만 쓴다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 단지에 속하지 않는 매물(빌라 등)은 단지·동·평형 번호가 원래 없다.
        fields = super().not_applicable_fields()
        if self.complex_id is None:
            fields = fields | {'complex_id', 'complex_name', 'building_dong', 'pyeong_id'}
        # 배정 학교는 단지·동 번호가 있는 매물만 있다. null 은 조회 실패(모름)로만 남긴다
        if not self.has_school_lookup:
            fields = fields | {'schools'}
        # 네이버는 오피스텔에만 계약면적을 준다 (다른 유형은 상세의 supplySpace 가 공급면적).
        if self.property_type != '오피스텔':
            fields = fields | {'contract_area_m2'}
        # 건물 이름·세부 유형은 단지 매물에는 없다 (해당 없음). 상세 정보를 못 읽었으면 둘 다 모름(null)이다. 읽었는데 이름이
        # 없으면 이름 없는 건물이라 해당 없음이고, 세부 유형은 네이버 웹 제목이 쓰는 칸이라 값만 빠진 것이어서 모름(null)이다
        # 리뷰 오탐 (2026-11-17): 현관 구조(entrance)는 단지 여부로 지우지 않는다. 단지가 아닌 매물에도 오고(빌라 2661884425 '10')
        # 네이버 웹도 단지 여부와 상관없이 값이 있으면 칸을 그리고 없으면 숨겨, 값이 없으면 해당 없음이 아니라 모름(null)이다.
        # 단지형 빌라(A05·A06·A07)는 웹 화면(ArticleVillaBuildingInfo)에 현관 구조 칸이 없지만 값을 내는 것이 의도한 차이다
        # (docs/development/providers/naver.md '단지형 빌라의 현관 구조'). 그래서 이것도 지우지 않는다
        if self.complex_id is not None:
            fields = fields | {'building_name', 'building_type'}
        elif self.has_article_detail and self.building_name is None:
            fields = fields | {'building_name'}
        # 직거래는 중개사가 없어 네이버 웹도 중개보수 칸을 그리지 않는다 (2026-11-17 번들 ArticleMain 청크 0l4pkwg0qhg2t:
        # `!articleDetailInfo.isDirectTrade` 일 때만 ArticleRealtorFee 를 붙인다). agentFee 는 직거래에도 금액을 준다 (토지 2661679787)
        if self.is_direct_trade:
            fields = fields | {'broker_fee_manwon', 'broker_fee_individual_check_required'}
        # 유형마다 웹이 칸을 그리지 않는 필드 (토지의 방 수·층·난방 등)
        fields = fields | NOT_APPLICABLE_FIELDS_BY_TYPE.get(self.real_estate_type or '', frozenset())
        # 세금은 매매 매물만 조회한다 (중개보수는 직거래가 아님이 확인된 매물만 모든 거래 유형). 원룸·고시원·일반분양권이 아닌 분양권은
        # 세금 칸이 없고, 세 세금을 모두 그리는 유형 밖의 매매는 취득세만 그린다. 분양 상태를 모르는 분양권 매매는 요청하지 않아
        # 칸이 있는지 몰라서, 취득세는 null 로 남긴다 (모름)
        draws_taxes = draws_sale_taxes(self.trade_type, self.real_estate_type, self.pre_sale_status_type)
        if draws_taxes is False:
            fields = fields | SALE_TAX_FIELDS
        elif self.real_estate_type not in ALL_TAX_TYPES:
            fields = fields | (SALE_TAX_FIELDS - {'acquisition_tax_manwon'})
        return fields


def draws_sale_taxes(trade_type: str, real_estate_type: str | None, pre_sale_status_type: str | None) -> bool | None:
    """이 매물에 네이버 웹이 세금 칸을 그리는지 (세금 요청과 키 제거가 같은 조건을 쓰도록 한 곳에 둔다). 칸이 있는지 모르면 None.

    매매가 아니거나 원룸·고시원이면 없다. 분양권(B01·B02)은 웹 getArticleTaxExposeInfo(청크 0n-xsnd22pdxz)가 매매이면서
    분양권 상태(preSaleStatusType)가 일반분양권('10')일 때만 세금 칸을 그려서, 상태가 없으면 칸이 없다. 그래서 상태를 모르는
    분양권 매매는 칸이 있다고도 없다고도 단정하지 않으려고 요청하지 않고 모름(None)으로 둔다 (직거래 여부를 모를 때 중개보수를
    요청하지 않는 것과 같은 기준). 빈 글자도 None 과 같게 본다 (`coded_label` 과 같은 기준). 상태가 일반분양권이 아니면 없다.
    """
    if trade_type != '매매' or real_estate_type in NO_TAX_TYPES:
        return False
    if real_estate_type in PRE_SALE_TYPES:
        if not pre_sale_status_type:
            return None
        return pre_sale_status_type == GENERAL_PRE_SALE_STATUS
    return True
