"""`detail.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NumberRange,
    Result,
)

from typing import (
    Annotated,
    Any,
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
