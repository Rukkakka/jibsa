"""응답 모델: 단지 비교와 주변 단지 (compare, nearby-complexes)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnCompareRegionModel,
    DaangnGraphQLResponseModel,
    DaangnLiveArticleCountModel,
    LooseFloat,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 단지 비교 (complexByOriginalId 비교 칸), 같은 동 단지
# ---------------------------------------------------------------------------

class DaangnCompareTradeModel(ResponseModel):
    """호가 매물의 거래 조건 (금액만)."""

    price: Annotated[
        int | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금·전세금 (만원)')
    ] = None
    monthly_pay: Annotated[
        int | None,
        Field(description='월세 (만원)', alias='monthlyPay')
    ] = None


class DaangnCompareArticleModel(ResponseModel):
    """호가 매물 하나 (거래 조건만)."""

    trades: Annotated[
        list[DaangnCompareTradeModel],
        Field(description='거래 조건')
    ] = []


class DaangnCompareArticleEdgeModel(ResponseModel):
    """호가 매물 edge."""

    node: Annotated[
        DaangnCompareArticleModel | None,
        Field(description='매물')
    ] = None


class DaangnCompareArticleConnectionModel(ResponseModel):
    """호가 매물 연결 (아파트 매물 앞 30건)."""

    edges: Annotated[
        list[DaangnCompareArticleEdgeModel],
        Field(description='매물')
    ] = []


class DaangnCompareBuildingModel(ResponseModel):
    """단지 건물."""

    road_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadAddress')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddress')
    ] = None


class DaangnCompareBuildingEdgeModel(ResponseModel):
    """건물 edge."""

    node: Annotated[
        DaangnCompareBuildingModel | None,
        Field(description='건물')
    ] = None


class DaangnCompareBuildingConnectionModel(ResponseModel):
    """건물 연결."""

    edges: Annotated[
        list[DaangnCompareBuildingEdgeModel],
        Field(description='건물')
    ] = []


class DaangnKaptCostModel(ResponseModel):
    """월별 ㎡당 관리비 (K-apt)."""

    year_month: Annotated[
        str | None,
        Field(description='연월 (YYYYMM)', alias='yearMonth')
    ] = None
    cost_per_square_meter: Annotated[
        int | None,
        Field(description='㎡당 관리비 (원)', alias='costPerSquareMeter')
    ] = None


class DaangnKaptModel(ResponseModel):
    """공동주택 관리정보 (K-apt). 없는 단지면 null."""

    monthly_management_costs_per_square_meter: Annotated[
        list[DaangnKaptCostModel],
        Field(description='최근 월별 ㎡당 관리비', alias='monthlyManagementCostsPerSquareMeter')
    ] = []


class DaangnCompareSchoolModel(ResponseModel):
    """배정 학교."""

    sch_nm: Annotated[
        str | None,
        Field(description='학교 이름', alias='schNm')
    ] = None
    sch_type: Annotated[
        str | None,
        Field(description='ELEMENTARY ...', alias='schType')
    ] = None


class DaangnAssignedSchoolModel(ResponseModel):
    """배정 학교와 거리."""

    distance: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    working_time: Annotated[
        int | None,
        Field(description='도보 (분)', alias='workingTime')
    ] = None
    school: Annotated[
        DaangnCompareSchoolModel | None,
        Field(description='학교')
    ] = None


class DaangnCompareSubwayModel(ResponseModel):
    """주변 역 정보 한 줄. 같은 역이 거리(DISTANCE)·도보(WALKING) 두 줄로 온다."""

    station_nm: Annotated[
        str | None,
        Field(description="역 이름 ('역' 없음)", alias='stationNm')
    ] = None
    simple_line_nm: Annotated[
        str | None,
        Field(description='노선 (예: 2호선)', alias='simpleLineNm')
    ] = None
    data_type: Annotated[
        str | None,
        Field(description='DISTANCE(m) / WALKING(분)', alias='dataType')
    ] = None
    data_value: Annotated[
        str | None,
        Field(description='값 (문자열)', alias='dataValue')
    ] = None


class DaangnKbPriceModel(ResponseModel):
    """KB 시세 (만원)."""

    sale_std_price: Annotated[
        int | None,
        Field(description='매매 일반가', alias='saleStdPrice')
    ] = None
    sale_upper_limit: Annotated[
        int | None,
        Field(description='매매 상위가', alias='saleUpperLimit')
    ] = None
    sale_lower_limit: Annotated[
        int | None,
        Field(description='매매 하위가', alias='saleLowerLimit')
    ] = None
    lease_std_price: Annotated[
        int | None,
        Field(description='전세 일반가', alias='leaseStdPrice')
    ] = None
    lease_upper_limit: Annotated[
        int | None,
        Field(description='전세 상위가', alias='leaseUpperLimit')
    ] = None
    lease_lower_limit: Annotated[
        int | None,
        Field(description='전세 하위가', alias='leaseLowerLimit')
    ] = None
    monthly_deposit: Annotated[
        int | None,
        Field(description='월세 보증금', alias='monthlyDeposit')
    ] = None
    monthly_upper_limit: Annotated[
        int | None,
        Field(description='월세 상위', alias='monthlyUpperLimit')
    ] = None
    monthly_lower_limit: Annotated[
        int | None,
        Field(description='월세 하위', alias='monthlyLowerLimit')
    ] = None
    survey_base_date: Annotated[
        str | None,
        Field(description='조사 기준일 (YYYYMMDD)', alias='surveyBaseDate')
    ] = None


class DaangnKbPriceEdgeModel(ResponseModel):
    """KB 시세 edge."""

    node: Annotated[
        DaangnKbPriceModel | None,
        Field(description='시세')
    ] = None


class DaangnKbPriceConnectionModel(ResponseModel):
    """KB 시세 연결 (최신 1건)."""

    edges: Annotated[
        list[DaangnKbPriceEdgeModel],
        Field(description='시세')
    ] = []


class DaangnCompareRealsaleModel(ResponseModel):
    """평형 최근 실거래 (만원)."""

    trade_price: Annotated[
        int | None,
        Field(description='매매가', alias='tradePrice')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금')
    ] = None
    month_rent_fee: Annotated[
        int | None,
        Field(description='월세 (0 이면 전세)', alias='monthRentFee')
    ] = None
    contact_date: Annotated[
        str | None,
        Field(description='계약일 (YYYYMMDD)', alias='contactDate')
    ] = None
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None


class DaangnCompareRealsaleEdgeModel(ResponseModel):
    """실거래 edge."""

    node: Annotated[
        DaangnCompareRealsaleModel | None,
        Field(description='실거래')
    ] = None


class DaangnCompareRealsaleConnectionModel(ResponseModel):
    """실거래 연결 (매매 1건·전월세 5건, 최근 순)."""

    edges: Annotated[
        list[DaangnCompareRealsaleEdgeModel],
        Field(description='실거래')
    ] = []


class DaangnComparePyInfoModel(ResponseModel):
    """평형 하나와 시세·실거래."""

    exclusive_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)', alias='exclusiveArea')
    ] = None
    supply_area: Annotated[
        LooseFloat,
        Field(description='공급면적 (㎡)', alias='supplyArea')
    ] = None
    ptp_tot_hseh_cnt: Annotated[
        int | None,
        Field(description='세대수', alias='ptpTotHsehCnt')
    ] = None
    kb_prices: Annotated[
        DaangnKbPriceConnectionModel | None,
        Field(description='KB 시세', alias='kbPrices')
    ] = None
    sale_realsale: Annotated[
        DaangnCompareRealsaleConnectionModel | None,
        Field(description='최근 매매 실거래', alias='saleRealsale')
    ] = None
    borrow_realsale: Annotated[
        DaangnCompareRealsaleConnectionModel | None,
        Field(description='최근 전월세 실거래', alias='borrowRealsale')
    ] = None


class DaangnCompareAreaGroupModel(ResponseModel):
    """전용면적 묶음 (예: 59)."""

    label: Annotated[
        int | None,
        Field(description='전용면적 묶음 (㎡ 정수)')
    ] = None
    is_representative: Annotated[
        bool | None,
        Field(description='대표 평형', alias='isRepresentative')
    ] = None
    total_cnt: Annotated[
        int | None,
        Field(description='세대수', alias='totalCnt')
    ] = None
    py_infos: Annotated[
        list[DaangnComparePyInfoModel],
        Field(description='평형', alias='pyInfos')
    ] = []


class DaangnCompareDanjiModel(ResponseModel):
    """단지 공공 정보 (proptier)."""

    build_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)', alias='buildDate')
    ] = None
    tot_dong_cnt: Annotated[
        int | None,
        Field(description='동 수', alias='totDongCnt')
    ] = None
    total_tot_hseh_cnt: Annotated[
        int | None,
        Field(description='세대수', alias='totalTotHsehCnt')
    ] = None
    hseh_parking_cnt: Annotated[
        LooseFloat,
        Field(description='세대당 주차 대수', alias='hsehParkingCnt')
    ] = None
    min_floor: Annotated[
        int | None,
        Field(description='최저 층', alias='minFloor')
    ] = None
    max_floor: Annotated[
        int | None,
        Field(description='최고 층', alias='maxFloor')
    ] = None
    assigned_schools: Annotated[
        list[DaangnAssignedSchoolModel],
        Field(description='배정 학교', alias='assignedSchools')
    ] = []
    subway_info: Annotated[
        list[DaangnCompareSubwayModel],
        Field(description='주변 역', alias='subwayInfo')
    ] = []
    exclusive_area_groups: Annotated[
        list[DaangnCompareAreaGroupModel],
        Field(description='전용면적 묶음별 평형', alias='exclusiveAreaGroups')
    ] = []


class DaangnCompareComplexModel(ResponseModel):
    """비교 칸의 단지. 후기 요약 글(`livedReviewSummary`)은 읽지 않는다."""

    original_id: Annotated[
        str,
        Field(description='단지 ID', alias='originalId')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='APARTMENT / OFFICETEL / MIXED_USE ...')
    ] = None
    live_article_count: Annotated[
        DaangnLiveArticleCountModel | None,
        Field(description='현재 매물 수', alias='liveArticleCount')
    ] = None
    asking_articles: Annotated[
        DaangnCompareArticleConnectionModel | None,
        Field(description='호가 매물 (아파트 매물 앞 30건)', alias='askingArticles')
    ] = None
    lived_review_count: Annotated[
        int | None,
        Field(description='거주 후기 수', alias='livedReviewCount')
    ] = None
    buildings: Annotated[
        DaangnCompareBuildingConnectionModel | None,
        Field(description='건물')
    ] = None
    region: Annotated[
        DaangnCompareRegionModel | None,
        Field(description='지역')
    ] = None
    kapt: Annotated[
        DaangnKaptModel | None,
        Field(description='K-apt 관리비')
    ] = None
    proptier_danji: Annotated[
        DaangnCompareDanjiModel | None,
        Field(description='단지 공공 정보', alias='proptierDanji')
    ] = None


class DaangnCompareOutputModel(ResponseModel):
    """`complexByOriginalId` 결과."""

    complex: Annotated[
        DaangnCompareComplexModel | None,
        Field(description='단지. 없으면 null')
    ] = None


class DaangnComplexCompareDataModel(ResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnCompareOutputModel | None,
        Field(description='단지', alias='complexByOriginalId')
    ] = None


class DaangnComplexCompareResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexByOriginalId` 비교 칸 응답 (웹의 `ComplexCompareColumnQuery`)."""

    data: Annotated[
        DaangnComplexCompareDataModel | None,
        Field(description='결과')
    ] = None


class DaangnNearbyComplexNodeModel(ResponseModel):
    """같은 동 단지 (이름·유형만)."""

    original_id: Annotated[
        str,
        Field(description='단지 ID', alias='originalId')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT / OFFICETEL ...')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None


class DaangnNearbyComplexEdgeModel(ResponseModel):
    """같은 동 단지 edge."""

    node: Annotated[
        DaangnNearbyComplexNodeModel | None,
        Field(description='단지')
    ] = None


class DaangnNearbyComplexesModel(ResponseModel):
    """같은 동 단지 연결 (한 번에 전부, 2026-10-10 실측: 역삼동 255곳)."""

    edges: Annotated[
        list[DaangnNearbyComplexEdgeModel],
        Field(description='단지')
    ] = []


class DaangnNearbyComplexesDataModel(ResponseModel):
    """GraphQL `data`."""

    complexes: Annotated[
        DaangnNearbyComplexesModel | None,
        Field(description='같은 동 단지')
    ] = None


class DaangnNearbyComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexes` 응답 (웹의 `ComplexNearbySectionQuery`)."""

    data: Annotated[
        DaangnNearbyComplexesDataModel | None,
        Field(description='결과')
    ] = None


class DaangnComplexCardDanjiModel(ResponseModel):
    """단지 카드의 공공 정보."""

    total_tot_hseh_cnt: Annotated[
        int | None,
        Field(description='세대수', alias='totalTotHsehCnt')
    ] = None


class DaangnComplexCardModel(ResponseModel):
    """단지 카드 (세대수·현재 매물 수)."""

    original_id: Annotated[
        str,
        Field(description='단지 ID', alias='originalId')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='APARTMENT / OFFICETEL ...')
    ] = None
    proptier_danji: Annotated[
        DaangnComplexCardDanjiModel | None,
        Field(description='공공 정보', alias='proptierDanji')
    ] = None
    live_article_count: Annotated[
        DaangnLiveArticleCountModel | None,
        Field(description='현재 매물 수', alias='liveArticleCount')
    ] = None


class DaangnComplexesByOriginalComplexIdsDataModel(ResponseModel):
    """GraphQL `data`."""

    complexes_by_original_complex_ids: Annotated[
        list[DaangnComplexCardModel],
        Field(description='단지 카드 (ID 255개도 한 번에 된다)', alias='complexesByOriginalComplexIds')
    ] = []


class DaangnComplexesByOriginalComplexIdsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexesByOriginalComplexIds` 응답 (웹의 `ComplexNearbySectionCardsQuery`)."""

    data: Annotated[
        DaangnComplexesByOriginalComplexIdsDataModel | None,
        Field(description='결과')
    ] = None
