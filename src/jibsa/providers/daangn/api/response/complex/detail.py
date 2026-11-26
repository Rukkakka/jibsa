"""응답 모델: 단지 정보·단지 매물 (complex, search listings --complex)."""

from pydantic import (
    Field,
    model_validator,
)

from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnLiveArticleCountModel,
    DaangnPageInfoModel,
    DaangnRegionModel,
    LooseFloat,
)

from typing import (
    Annotated,
    Any,
)


# ---------------------------------------------------------------------------
# GET realty.daangn.com/complexes/{originalId} (SSR Relay 스토어)
# ---------------------------------------------------------------------------

class DaangnPyInfoModel(DaangnBaseResponseModel):
    """평형 하나."""

    ptp_cd: Annotated[
        int | None,
        Field(description='평형 타입 코드 (단지 안 번호, 실거래·시세의 ptpCds 로 보낸다)', alias='ptpCd')
    ] = None
    ptp: Annotated[
        str | None,
        Field(description="평형 타입 이름 (예: 'A', 'J1')")
    ] = None
    exclusive_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)', alias='exclusiveArea')
    ] = None
    supply_area: Annotated[
        LooseFloat,
        Field(description='공급면적 (㎡)', alias='supplyArea')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCnt')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathCnt')
    ] = None



class DaangnAreaGroupModel(DaangnBaseResponseModel):
    """평형 묶음 (웹의 평형 탭 하나). 전용면적 묶음이나 공급 평 묶음이다. 같은 묶음에 평형이 여러 개일 수 있다."""

    label: Annotated[
        int | None,
        Field(description='묶음 이름 (전용면적 묶음은 ㎡ 정수, 공급 평 묶음은 평 정수)')
    ] = None
    is_representative: Annotated[
        bool | None,
        Field(description='대표 평형 묶음 (웹이 처음 고르는 평형)', alias='isRepresentative')
    ] = None
    total_count: Annotated[
        int | None,
        Field(description='묶음의 세대수', alias='totalCnt')
    ] = None
    py_infos: Annotated[
        list[DaangnPyInfoModel],
        Field(description='평형', alias='pyInfos')
    ] = []



class DaangnSubwayInfoModel(DaangnBaseResponseModel):
    """단지에서 가까운 지하철역."""

    station_name: Annotated[
        str | None,
        Field(description="역 이름 ('역' 이 붙지 않는다, 예: 신사)", alias='stationNm')
    ] = None
    line_name: Annotated[
        str | None,
        Field(description='노선 (예: 신분당선)', alias='simpleLineNm')
    ] = None
    walking_time_min: Annotated[
        LooseFloat,
        Field(description='도보 시간 (분)', alias='walkingTimeMin')
    ] = None



class DaangnSchoolModel(DaangnBaseResponseModel):
    """학교."""

    @model_validator(mode='before')
    @classmethod
    def resident_count_key(cls, data: Any) -> Any:
        """이 단지 주민 수는 인자가 붙은 키(`complexResidentCount(complexOriginalId:"10667600")`)로 와서 이름을 맞춘다."""
        if isinstance(data, dict):
            key = next((key for key in data if str(key).startswith('complexResidentCount(')), None)
            if key is not None:
                data = {**data, 'complexResidentCount': data[key]}
        return data

    resident_count: Annotated[
        int | None,
        Field(description='이 단지 주민 중 다니는 수 (웹의 "이 단지 N명 이상이 다녀요")', alias='complexResidentCount')
    ] = None
    name: Annotated[
        str | None,
        Field(description='학교 이름', alias='schNm')
    ] = None
    type: Annotated[
        str | None,
        Field(description='ELEMENTARY / MIDDLE / HIGH', alias='schType')
    ] = None



class DaangnNearbySchoolModel(DaangnBaseResponseModel):
    """단지 주변 학교 (배정 초등학교, 가까운 중·고등학교)."""

    school: Annotated[
        DaangnSchoolModel | None,
        Field(description='학교')
    ] = None
    walking_time_min: Annotated[
        LooseFloat,
        Field(description='도보 시간 (분)', alias='walkingTimeMin')
    ] = None
    walking_distance_m: Annotated[
        LooseFloat,
        Field(description='도보 거리 (m)', alias='walkingDistanceMeters')
    ] = None
    working_time: Annotated[
        LooseFloat,
        Field(description='배정 학교의 길찾기 도보 시간 (분). walkingTimeMin 이 없을 때 웹이 쓴다', alias='workingTime')
    ] = None
    distance: Annotated[
        LooseFloat,
        Field(description='배정 학교까지 직선거리 (m). walkingDistanceMeters 가 없을 때 웹이 쓴다 (ComplexSchoolSection `Re`)')
    ] = None
    allocation_method: Annotated[
        str | None,
        Field(description="배정 방식 (예: '자동')", alias='allocationMethod')
    ] = None



class DaangnDoroAddrModel(DaangnBaseResponseModel):
    """단지 주소. 시·도가 '서울' 처럼 줄여 온다."""

    road_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadAddr')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddr')
    ] = None



class DaangnProptierDanjiModel(DaangnBaseResponseModel):
    """단지 상세 (공공 데이터). 관리사무소 전화(`managementPhone`)도 오지만 내보내지 않는다."""

    households: Annotated[
        int | None,
        Field(description='총 세대수', alias='totalTotHsehCnt')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수', alias='totDongCnt')
    ] = None
    min_floor: Annotated[
        int | None,
        Field(description='가장 낮은 동의 최고층', alias='minFloor')
    ] = None
    max_floor: Annotated[
        int | None,
        Field(description='가장 높은 동의 최고층', alias='maxFloor')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수. 오피스텔은 0 으로 오기도 한다', alias='totParkingCnt')
    ] = None
    parking_per_household: Annotated[
        LooseFloat,
        Field(description='세대당 주차 대수', alias='hsehParkingCnt')
    ] = None
    heating_method: Annotated[
        str | None,
        Field(description='난방 방식 (예: 개별난방)', alias='heatMthd')
    ] = None
    heating_fuel: Annotated[
        str | None,
        Field(description='난방 연료 (예: 도시가스)', alias='heatfuel')
    ] = None
    floor_area_ratio: Annotated[
        LooseFloat,
        Field(description='용적률 (%)', alias='floorSpaceIdx')
    ] = None
    building_coverage_ratio: Annotated[
        LooseFloat,
        Field(description='건폐율 (%)', alias='buildingCoverage')
    ] = None
    constructor_name: Annotated[
        str | None,
        Field(description='시공사', alias='constructorName')
    ] = None
    addresses: Annotated[
        list[DaangnDoroAddrModel],
        Field(description='주소', alias='doroAddrs')
    ] = []
    area_groups: Annotated[
        list[DaangnAreaGroupModel],
        Field(description='전용면적 묶음과 평형', alias='exclusiveAreaGroups')
    ] = []
    supply_pyeong_area_groups: Annotated[
        list[DaangnAreaGroupModel],
        Field(description='공급 평 묶음과 평형 (아파트형 단지. 웹은 아파트형이면 이 묶음으로 평형을 고른다)', alias='supplyPyeongAreaGroups')
    ] = []
    subways: Annotated[
        list[DaangnSubwayInfoModel],
        Field(description='가까운 지하철역')
    ] = []
    assigned_schools: Annotated[
        list[DaangnNearbySchoolModel],
        Field(description='배정 초등학교', alias='assignedSchools')
    ] = []
    middle_schools: Annotated[
        list[DaangnNearbySchoolModel],
        Field(description='가까운 중학교', alias='middleSchools')
    ] = []
    high_schools: Annotated[
        list[DaangnNearbySchoolModel],
        Field(description='가까운 고등학교', alias='highSchools')
    ] = []



class DaangnComplexModel(DaangnBaseResponseModel):
    """`__typename == "PropComplex"` 레코드를 참조까지 펼친 것 (단지 페이지)."""

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
        Field(description='APARTMENT, OFFICETEL, MIXED_USE(주상복합), LIVING_ACCOMMODATION, REDEVELOPMENT')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수 (proptierDanji 가 없을 때 쓴다)')
    ] = None
    building_count: Annotated[
        int | None,
        Field(description='동 수 (proptierDanji 가 없을 때 쓴다)', alias='buildingCount')
    ] = None
    approval_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)', alias='approvalDate')
    ] = None
    region: Annotated[
        DaangnRegionModel | None,
        Field(description='단지가 있는 동')
    ] = None
    proptier_danji: Annotated[
        DaangnProptierDanjiModel | None,
        Field(description='단지 상세 (공공 데이터)', alias='proptierDanji')
    ] = None
    live_article_count: Annotated[
        DaangnLiveArticleCountModel | None,
        Field(description='현재 매물 수 (주거용 매물)', alias='liveArticleCount')
    ] = None
    lived_review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기가 없으면 null 로 오기도 한다', alias='livedReviewCount')
    ] = None



class DaangnComplexesResponseModel(DaangnBaseResponseModel):
    """단지 페이지에서 추출한 단지. 없는 단지면 페이지가 404 다."""

    complex: Annotated[
        DaangnComplexModel | None,
        Field(description='단지')
    ] = None



# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId { complex { articles } } (단지 매물 목록)
# ---------------------------------------------------------------------------

class DaangnArticleEdgeModel(DaangnBaseResponseModel):
    """매물 연결 edge."""

    node: Annotated[
        DaangnArticleModel | None,
        Field(description='매물 카드 (articleFeed 카드와 같은 필드. 지역에 시·도가 없다)')
    ] = None



class DaangnArticleConnectionModel(DaangnBaseResponseModel):
    """매물 연결."""

    edges: Annotated[
        list[DaangnArticleEdgeModel],
        Field(description='매물')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None



class DaangnComplexArticlesComplexModel(DaangnBaseResponseModel):
    """단지 (매물 연결만 받는다)."""

    articles: Annotated[
        DaangnArticleConnectionModel | None,
        Field(description='단지의 현재 매물')
    ] = None



class DaangnComplexArticlesOutputModel(DaangnBaseResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexArticlesComplexModel | None,
        Field(description='단지')
    ] = None



class DaangnComplexArticlesDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexArticlesOutputModel | None,
        Field(description='단지 조회 결과', alias='complexByOriginalId')
    ] = None



class DaangnComplexArticlesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL 단지 매물 목록 응답."""

    data: Annotated[
        DaangnComplexArticlesDataModel | None,
        Field(description='결과')
    ] = None
