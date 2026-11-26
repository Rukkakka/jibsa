"""단지 정보·단지 이름 검색·지역·지도 범위 단지 목록·인기 단지·단지 매물의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountSet,
    Listing,
    NumberRange,
    Result,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.service.common.models import (
    DaangnRegion,
    DaangnRegionComplex,
    region_name_parts,
)
from jibsa.providers.daangn.service.region.models import (
    DaangnRealsaleRegion,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnPyeong(BaseModel):
    """단지 평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    supply_area_pyeong: Annotated[
        float | None,
        Field(description='공급면적 (평). 흔히 말하는 "34평형" 이 이 값이다')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수. 당근이 묶음별로만 주므로 한 묶음에 평형이 여럿이면 null. 당근이 빈 항목을 줘 셀 수 없으면 null')
    ] = None
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (예: 32. 아파트형 단지만, real-price·price-trend --pyeong 에 넘긴다)')
    ] = None
    representative: Annotated[
        bool,
        Field(description='당근 웹이 처음 보여 주는 대표 평형 묶음인지 (price-trend 의 기본 평형)')
    ] = False
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음. 아파트형이 아닌 단지만 real-price·price-trend --area 에 넘긴다 (아파트형은 pyeong 을 --pyeong 에)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 공급 평형 묶음은 아파트형 단지에만 있어 그 밖에는 해당 없음이라 키를 뺀다
        data: dict[str, Any] = handler(self)
        if self.pyeong is None:
            data.pop('pyeong', None)
        return data


class DaangnComplex(Result):
    """단지 정보. 매물과 마찬가지로 좌표·사진·관리사무소 전화·후기 본문은 담지 않는다.

    `notes`: 후기를 원 사이트에서 보라는 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소. 없으면 동까지')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 꼭대기 층수의 최소(lowest)·최대(highest). 모르면 null')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 방식 (예: 개별난방)')
    ] = None
    heating_fuel: Annotated[
        str | None,
        Field(description='난방 연료 (예: 도시가스)')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    building_coverage_ratio_percent: Annotated[
        float | None,
        Field(description='건폐율 (%)')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='당근에 올라온 이 단지의 현재 주거용 매물 수')
    ] = None
    pyeongs: Annotated[
        list[DaangnPyeong] | None,
        Field(description='평형 목록 (전용면적 순). 아파트형 단지는 공급 평 묶음(pyeong)이 붙는다. 단지 공공 정보가 없으면 null')
    ] = []
    nearby_stations: Annotated[
        list[str] | None,
        Field(description='가까운 지하철역 (예: 신사역 (신분당선, 도보 4분)). 도보 시간이 짧은 순 (당근 웹 단지 화면 가까운 역 순서). 단지 공공 정보가 없으면 null')
    ] = []
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 당근 웹 학군 카드의 중·고등학교 2곳씩 (이 단지 주민이 많이 다니는 순, 같으면 도보 순. 예: 서울가락초등학교 (배정, 도보 6분, 이 단지 20명 이상)). 단지 공공 정보가 없으면 null')
    ] = []
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기 내용은 url 의 당근 단지 페이지에서 본다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class DaangnComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘긴다)')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...)')
    ] = None
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='주소 (지번, 없으면 도로명)')
    ] = None


class DaangnRegionComplexesResult(Result):
    """동·구의 단지 목록.

    `notes`: 지역을 고른 방법, 정렬·후기 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    trade_type: Annotated[
        str,
        Field(description='최근 실거래(recent_trades)와 가격 조건의 거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (세대수, 가격높은순, 가격낮은순, 입주최신순, 입주오래된순)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지가 더 있는지')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex],
        Field(description='정렬 순 단지')
    ]


class DaangnComplexConditions(RequestModel):
    """지역 단지 목록 조건 (search complexes). 웹 지도 단지 탭 필터와 같고 당근 서버에서 건다.

    가격 조건은 지금 매물 가격이 아니라 단지의 과거 실거래 가격으로 거른다 (`list_region_complexes`).
    """

    complex_types: Annotated[
        list[str],
        Field(description='단지 유형 (COMPLEX_TYPE_FILTER_BY_LABEL). 비면 전체 (도시형 생활주택도 섞인다)')
    ] = []
    # 리뷰 오탐 (2026-11-20): CLI(search complexes)는 --trade 없이 보증금·월세 조건을 막지만, 이 설명은 라이브러리로 직접 부를 때의
    # 동작이다 (complex.py 의 조건 만들기와 맞다)
    trade_type: Annotated[
        str | None,
        Field(description='가격 조건과 단지마다 붙는 최근 실거래의 거래 유형 (매매·전세·월세). 없으면 매매로 보여 주고, 필터로는 가격 조건(보증금·월세·매매가 중 하나)이 있을 때만 기본 매매를 보낸다')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원, 과거 실거래 기준)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원, 과거 실거래 기준)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원, 과거 실거래 기준)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원, 과거 실거래 기준)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원, 과거 실거래 기준)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원, 과거 실거래 기준)')
    ] = None
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡). 단지 조건과 최근 실거래 면적에 함께 건다')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡). 단지 조건과 최근 실거래 면적에 함께 건다')
    ] = None
    building_approval: Annotated[
        str | None,
        Field(description='사용승인일 (BUILDING_APPROVAL_FILTER_BY_LABEL)')
    ] = None
    household_min: Annotated[
        int | None,
        Field(description='세대수 하한')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='세대수 상한')
    ] = None
    parking_min: Annotated[
        float | None,
        Field(description='세대당 주차 대수 하한')
    ] = None


class DaangnBoundsComplexesResult(Result):
    """지도 화면 범위의 단지 목록 (웹 지도 단지 탭의 '이 영역 단지').

    `notes`: 범위·정렬·후기 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion | None,
        Field(description='화면 가운데가 속한 동. 모르면 null')
    ] = None
    zoom: Annotated[
        int,
        Field(description='웹 지도 줌. 범위는 데스크톱 지도 화면(1440×900 창에서 목록 패널을 뺀 영역) 기준이다')
    ]
    width_km: Annotated[
        float,
        Field(description='화면 범위의 가로 (km)')
    ]
    height_km: Annotated[
        float,
        Field(description='화면 범위의 세로 (km)')
    ]
    trade_type: Annotated[
        str,
        Field(description='최근 실거래(recent_trades)와 가격 조건의 거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (세대수, 가격높은순, 가격낮은순, 입주최신순, 입주오래된순)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지가 더 있는지')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex],
        Field(description='정렬 순 단지')
    ]


class DaangnComplexListingsResult(Result):
    """단지 하나의 매물 목록.

    `notes`: 일부만 보여 준다·더 받지 못하고 멈췄다는 안내, 거래를 몰라 뺀 매물·빈 항목을 뺐다는 안내, 원룸·투룸으로 올린 단지 매물 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지')
    ]
    listings: Annotated[
        list[Listing],
        Field(description='단지 매물 (당근 단지 화면 순)')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class DaangnTrendingComplex(BaseModel):
    """인기 급상승 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[int | None, Field(description='순위. 당근이 빈 항목을 줘 셀 수 없으면 null')]
    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='시·도·구')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    representative_area_m2: Annotated[
        float | None,
        Field(description='대표 평형 전용면적 (㎡). 당근이 빈 항목을 줘 셀 수 없으면 null')
    ] = None
    latest_trades: Annotated[
        dict[str, AmountSet | None],
        Field(description="대표 평형의 가장 최근 실거래. 거래 키('sale')이고 그 안 price_manwon 은 최근 매매가 (만원). 최근 매매가 없거나 매매가가 0 이면(당근 웹도 비운다) 키가 없고({}), 대표 평형을 모르거나(당근이 빈 항목을 줘 셀 수 없을 때 포함) 당근이 실거래 칸이나 그 목록을 주지 않거나 목록에 빈 항목이 섞이거나 매매가를 모르면 'sale' 이 null")
    ]


class DaangnTrendingRegion(BaseModel):
    """인기 급상승 단지를 본 범위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sido: Annotated[
        str,
        Field(description='시/도. 전국이면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    sigungu: Annotated[
        str,
        Field(description='시/군/구. 시·도 범위면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    region_id: Annotated[
        int | None,
        Field(description='당근 지역 ID. 전국이면 null')
    ] = None
    level: Annotated[
        Literal['전국', '시도', '구'],
        Field(description='전국·시도·구(시·군 포함)')
    ]

    @model_serializer
    def with_name(self) -> dict[str, Any]:
        if self.level == '전국':
            return {'name': '전국', 'region_id': self.region_id, 'level': self.level}
        return {**region_name_parts(self.sido, self.sigungu), 'region_id': self.region_id, 'level': self.level}


class DaangnTrendingComplexesResult(Result):
    """인기 급상승 단지 목록.

    `notes`: 빈 결과 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[DaangnTrendingRegion, Field(description='본 범위')]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    complexes: Annotated[list[DaangnTrendingComplex], Field(description='어제 대비 오늘 조회가 급상승한 순 단지')]
