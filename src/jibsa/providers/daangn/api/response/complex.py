"""응답 모델: 단지 정보·단지 이름 검색·지역 단지 목록·인기 단지·단지 매물 (complex, search complexes, trending-complexes, search listings --complex)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCompareRegionModel,
    DaangnGraphQLResponseModel,
    DaangnLiveArticleCountModel,
    DaangnPageInfoModel,
    DaangnRegionComplexNodeModel,
    DaangnRegionModel,
    LooseFloat,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET realty.daangn.com/complexes/{originalId} (SSR Relay 스토어)
# ---------------------------------------------------------------------------

class DaangnPyInfoModel(ResponseModel):
    """평형 하나."""

    exclusive_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)')
    ] = Field(default=None, alias='exclusiveArea')
    supply_area: Annotated[
        LooseFloat,
        Field(description='공급면적 (㎡)')
    ] = Field(default=None, alias='supplyArea')
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = Field(default=None, alias='roomCnt')
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = Field(default=None, alias='bathCnt')


class DaangnAreaGroupModel(ResponseModel):
    """전용면적 묶음 (웹의 평형 탭 하나). 같은 묶음에 평형이 여러 개일 수 있다."""

    label: Annotated[
        int | None,
        Field(description='묶음 이름 (전용면적 ㎡ 정수)')
    ] = None
    total_count: Annotated[
        int | None,
        Field(description='묶음의 세대수')
    ] = Field(default=None, alias='totalCnt')
    py_infos: Annotated[
        list[DaangnPyInfoModel],
        Field(description='평형')
    ] = Field(default=[], alias='pyInfos')


class DaangnSubwayInfoModel(ResponseModel):
    """단지에서 가까운 지하철역."""

    station_name: Annotated[
        str | None,
        Field(description="역 이름 ('역' 이 붙지 않는다, 예: 신사)")
    ] = Field(default=None, alias='stationNm')
    line_name: Annotated[
        str | None,
        Field(description='노선 (예: 신분당선)')
    ] = Field(default=None, alias='simpleLineNm')
    walking_time_min: Annotated[
        LooseFloat,
        Field(description='도보 시간 (분)')
    ] = Field(default=None, alias='walkingTimeMin')


class DaangnSchoolModel(ResponseModel):
    """학교."""

    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = Field(default=None, alias='schNm')
    type: Annotated[
        str | None,
        Field(description='ELEMENTARY / MIDDLE / HIGH')
    ] = Field(default=None, alias='schType')


class DaangnNearbySchoolModel(ResponseModel):
    """단지 주변 학교 (배정 초등학교, 가까운 중·고등학교)."""

    school: Annotated[
        DaangnSchoolModel | None,
        Field(description='학교')
    ] = None
    walking_time_min: Annotated[
        LooseFloat,
        Field(description='도보 시간 (분)')
    ] = Field(default=None, alias='walkingTimeMin')


class DaangnDoroAddrModel(ResponseModel):
    """단지 주소. 시·도가 '서울' 처럼 줄여 온다."""

    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = Field(default=None, alias='roadAddr')
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = Field(default=None, alias='jibunAddr')


class DaangnProptierDanjiModel(ResponseModel):
    """단지 상세 (공공 데이터). 관리사무소 전화(`managementPhone`)도 오지만 내보내지 않는다."""

    households: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = Field(default=None, alias='totalTotHsehCnt')
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = Field(default=None, alias='totDongCnt')
    min_floor: Annotated[
        int | None,
        Field(description='가장 낮은 동의 최고층')
    ] = Field(default=None, alias='minFloor')
    max_floor: Annotated[
        int | None,
        Field(description='가장 높은 동의 최고층')
    ] = Field(default=None, alias='maxFloor')
    parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수. 오피스텔은 0 으로 오기도 한다')
    ] = Field(default=None, alias='totParkingCnt')
    parking_per_household: Annotated[
        LooseFloat,
        Field(description='세대당 주차 대수')
    ] = Field(default=None, alias='hsehParkingCnt')
    heating_method: Annotated[
        str | None,
        Field(description='난방 방식 (예: 개별난방)')
    ] = Field(default=None, alias='heatMthd')
    heating_fuel: Annotated[
        str | None,
        Field(description='난방 연료 (예: 도시가스)')
    ] = Field(default=None, alias='heatfuel')
    floor_area_ratio: Annotated[
        LooseFloat,
        Field(description='용적률 (%)')
    ] = Field(default=None, alias='floorSpaceIdx')
    building_coverage_ratio: Annotated[
        LooseFloat,
        Field(description='건폐율 (%)')
    ] = Field(default=None, alias='buildingCoverage')
    constructor_name: Annotated[
        str | None,
        Field(description='시공사')
    ] = Field(default=None, alias='constructorName')
    addresses: Annotated[
        list[DaangnDoroAddrModel],
        Field(description='주소')
    ] = Field(default=[], alias='doroAddrs')
    area_groups: Annotated[
        list[DaangnAreaGroupModel],
        Field(description='전용면적 묶음과 평형')
    ] = Field(default=[], alias='exclusiveAreaGroups')
    subways: Annotated[
        list[DaangnSubwayInfoModel],
        Field(description='가까운 지하철역')
    ] = []
    assigned_schools: Annotated[
        list[DaangnNearbySchoolModel],
        Field(description='배정 초등학교')
    ] = Field(default=[], alias='assignedSchools')
    middle_schools: Annotated[
        list[DaangnNearbySchoolModel],
        Field(description='가까운 중학교')
    ] = Field(default=[], alias='middleSchools')
    high_schools: Annotated[
        list[DaangnNearbySchoolModel],
        Field(description='가까운 고등학교')
    ] = Field(default=[], alias='highSchools')


class DaangnComplexModel(ResponseModel):
    """`__typename == "PropComplex"` 레코드를 참조까지 펼친 것 (단지 페이지)."""

    original_id: Annotated[
        str,
        Field(description='숫자 단지 ID')
    ] = Field(alias='originalId')
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT, OFFICETEL, MIXED_USE(주상복합), LIVING_ACCOMMODATION, REDEVELOPMENT')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수 (proptierDanji 가 없을 때 쓴다)')
    ] = None
    building_count: Annotated[
        int | None,
        Field(description='동 수 (proptierDanji 가 없을 때 쓴다)')
    ] = Field(default=None, alias='buildingCount')
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = Field(default=None, alias='approvalDate')
    region: Annotated[
        DaangnRegionModel | None,
        Field(description='단지가 있는 동')
    ] = None
    proptier_danji: Annotated[
        DaangnProptierDanjiModel | None,
        Field(description='단지 상세 (공공 데이터)')
    ] = Field(default=None, alias='proptierDanji')
    live_article_count: Annotated[
        DaangnLiveArticleCountModel | None,
        Field(description='현재 매물 수 (주거용 매물)')
    ] = Field(default=None, alias='liveArticleCount')
    lived_review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기가 없으면 null 로 오기도 한다')
    ] = Field(default=None, alias='livedReviewCount')


class DaangnComplexesResponseModel(ResponseModel):
    """단지 페이지에서 추출한 단지. 없는 단지면 페이지가 404 다."""

    complex: Annotated[
        DaangnComplexModel | None,
        Field(description='단지')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — searchComplexes
# ---------------------------------------------------------------------------

class DaangnBuildingModel(ResponseModel):
    """단지의 건물 (동) 하나."""

    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = Field(default=None, alias='roadAddress')
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소. 비어 오기도 한다')
    ] = Field(default=None, alias='jibunAddress')


class DaangnBuildingEdgeModel(ResponseModel):
    """건물 연결의 edge."""

    node: Annotated[
        DaangnBuildingModel | None,
        Field(description='건물')
    ] = None


class DaangnBuildingConnectionModel(ResponseModel):
    """건물 연결."""

    edges: Annotated[
        list[DaangnBuildingEdgeModel],
        Field(description='건물')
    ] = []


class DaangnSearchComplexNodeModel(ResponseModel):
    """이름으로 찾은 단지."""

    original_id: Annotated[
        str,
        Field(description='숫자 단지 ID')
    ] = Field(alias='originalId')
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT, OFFICETEL, MIXED_USE ...')
    ] = None
    buildings: Annotated[
        DaangnBuildingConnectionModel | None,
        Field(description='건물 (웹 쿼리가 3개까지 받는다)')
    ] = None


class DaangnSearchComplexEdgeModel(ResponseModel):
    """단지 검색 연결의 edge."""

    node: Annotated[
        DaangnSearchComplexNodeModel | None,
        Field(description='단지')
    ] = None


class DaangnSearchComplexesModel(ResponseModel):
    """`searchComplexes` 연결. 이름이 비슷한 순이며 전국 단지가 섞인다."""

    edges: Annotated[
        list[DaangnSearchComplexEdgeModel],
        Field(description='단지')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보')
    ] = Field(default=None, alias='pageInfo')


class DaangnSearchComplexesDataModel(ResponseModel):
    """GraphQL `data`."""

    search_complexes: Annotated[
        DaangnSearchComplexesModel | None,
        Field(description='단지 검색 결과')
    ] = Field(default=None, alias='searchComplexes')


class DaangnSearchComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchComplexes` 응답."""

    data: Annotated[
        DaangnSearchComplexesDataModel | None,
        Field(description='결과')
    ] = None


class DaangnTrendingRealsaleNodeModel(ResponseModel):
    """인기 단지 평형의 최근 매매가."""

    trade_price: Annotated[
        int | None,
        Field(description='매매가 (만원)')
    ] = Field(default=None, alias='tradePrice')


class DaangnTrendingRealsaleEdgeModel(ResponseModel):
    """실거래 edge."""

    node: Annotated[
        DaangnTrendingRealsaleNodeModel | None,
        Field(description='실거래')
    ] = None


class DaangnTrendingRealsaleConnectionModel(ResponseModel):
    """실거래 연결 (최근 1건)."""

    edges: Annotated[
        list[DaangnTrendingRealsaleEdgeModel],
        Field(description='실거래')
    ] = []


class DaangnTrendingPyInfoModel(ResponseModel):
    """인기 단지 평형."""

    exclusive_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)')
    ] = Field(default=None, alias='exclusiveArea')
    sale_realsale: Annotated[
        DaangnTrendingRealsaleConnectionModel | None,
        Field(description='최근 매매')
    ] = Field(default=None, alias='saleRealsale')


class DaangnTrendingAreaGroupModel(ResponseModel):
    """인기 단지 전용면적 묶음."""

    is_representative: Annotated[
        bool | None,
        Field(description='대표 평형')
    ] = Field(default=None, alias='isRepresentative')
    py_infos: Annotated[
        list[DaangnTrendingPyInfoModel],
        Field(description='평형')
    ] = Field(default=[], alias='pyInfos')


class DaangnTrendingDanjiModel(ResponseModel):
    """인기 단지 공공 정보."""

    exclusive_area_groups: Annotated[
        list[DaangnTrendingAreaGroupModel],
        Field(description='전용면적 묶음')
    ] = Field(default=[], alias='exclusiveAreaGroups')


class DaangnTrendingComplexModel(ResponseModel):
    """요즘 많이 보는 단지. 사진(`imagesV2`)은 읽지 않는다."""

    original_id: Annotated[
        str,
        Field(description='단지 ID')
    ] = Field(alias='originalId')
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='APARTMENT ...')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approval_date_text: Annotated[
        str | None,
        Field(description="사용승인 문구 (예: '사용승인일 2022.04.28(4년차)')")
    ] = Field(default=None, alias='approvalDateText')
    region: Annotated[
        DaangnCompareRegionModel | None,
        Field(description='시·도·구')
    ] = None
    proptier_danji: Annotated[
        DaangnTrendingDanjiModel | None,
        Field(description='평형·최근 매매')
    ] = Field(default=None, alias='proptierDanji')


class DaangnTrendingComplexesDataModel(ResponseModel):
    """GraphQL `data`."""

    trending_complexes: Annotated[
        list[DaangnTrendingComplexModel],
        Field(description='인기 순 단지')
    ] = Field(default=[], alias='trendingComplexes')


class DaangnTrendingComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `trendingComplexes` 응답."""

    data: Annotated[
        DaangnTrendingComplexesDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId { complex { articles } } (단지 매물 목록)
# ---------------------------------------------------------------------------

class DaangnArticleEdgeModel(ResponseModel):
    """매물 연결 edge."""

    node: Annotated[
        DaangnArticleModel | None,
        Field(description='매물 카드 (articleFeed 카드와 같은 필드. 지역에 시·도가 없다)')
    ] = None


class DaangnArticleConnectionModel(ResponseModel):
    """매물 연결."""

    edges: Annotated[
        list[DaangnArticleEdgeModel],
        Field(description='매물')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보')
    ] = Field(default=None, alias='pageInfo')


class DaangnComplexArticlesComplexModel(ResponseModel):
    """단지 (매물 연결만 받는다)."""

    articles: Annotated[
        DaangnArticleConnectionModel | None,
        Field(description='단지의 현재 매물')
    ] = None


class DaangnComplexArticlesOutputModel(ResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexArticlesComplexModel | None,
        Field(description='단지')
    ] = None


class DaangnComplexArticlesDataModel(ResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexArticlesOutputModel | None,
        Field(description='단지 조회 결과')
    ] = Field(default=None, alias='complexByOriginalId')


class DaangnComplexArticlesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL 단지 매물 목록 응답."""

    data: Annotated[
        DaangnComplexArticlesDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — searchComplexes (지역 단지 목록, region_complexes)
# ---------------------------------------------------------------------------

class DaangnRegionComplexEdgeModel(ResponseModel):
    """지역 단지 목록의 edge."""

    node: Annotated[
        DaangnRegionComplexNodeModel | None,
        Field(description='단지')
    ] = None


class DaangnRegionComplexesModel(ResponseModel):
    """지역 단지 목록 연결. 요청한 정렬 순이다."""

    edges: Annotated[
        list[DaangnRegionComplexEdgeModel],
        Field(description='단지')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보')
    ] = Field(default=None, alias='pageInfo')


class DaangnRegionComplexesDataModel(ResponseModel):
    """GraphQL `data`."""

    search_complexes: Annotated[
        DaangnRegionComplexesModel | None,
        Field(description='단지 목록')
    ] = Field(default=None, alias='searchComplexes')


class DaangnRegionComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchComplexes` 응답 (지역 단지 목록)."""

    data: Annotated[
        DaangnRegionComplexesDataModel | None,
        Field(description='결과')
    ] = None
