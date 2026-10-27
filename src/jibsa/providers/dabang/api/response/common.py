from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import (
    Annotated,
    Generic,
    TypeVar,
)


T = TypeVar('T')


class DabangV5ResponseModel(ResponseModel, Generic[T]):
    """새 방식(`/api/v5/`) 응답의 봉투 `{code, msg, result, responseTime}`. 실제 데이터는 `result`.

    실패는 HTTP 상태(400·403·500)로 오므로 200 안의 실패는 보지 못했다 (2026-10-25 실측). 400 본문은
    `{"code": 400, "msg": "줌은 필수값 입니다.", "errorDetails": [...]}` 다.
    """

    code: Annotated[
        int | None,
        Field(description='응답 코드 (성공 200)')
    ] = None
    msg: Annotated[
        str | None,
        Field(description='응답 문구 ("성공하였습니다.")')
    ] = None
    result: Annotated[
        T | None,
        Field(description='실제 데이터')
    ] = None


class DabangLocationModel(ResponseModel):
    """좌표 (`{"lat": …, "lng": …}`)."""

    lat: Annotated[
        float,
        Field(description='위도')
    ]
    lng: Annotated[
        float,
        Field(description='경도')
    ]


class DabangRoomItemModel(ResponseModel):
    """매물 지도 목록의 매물 한 칸. 가격·층·면적·관리비가 숫자 없이 글자로만 온다 (상세에는 숫자가 있다).

    Args:
        seq: 화면의 매물번호.
        id: 매물 ID (24자리 16진수). 상세 `new-room/detail` 의 `room_id`.
        room_type_name: '원룸', '투룸', '오피스텔', '아파트' 등. 단기임대를 받는 월세 매물은 뒤에 ' • 단기' 가 붙는다.
        random_location: 다방이 몇 m 흔든 좌표 (상세 좌표와 수 m 차이, 2026-10-25 실측).
        complex_name: 단지·건물 이름 (오피스텔·아파트).
        room_title: 매물 한 줄 제목 (중개사가 쓴 글).
        room_desc: '5층, 19.83m², 관리비 7만' 처럼 층·전용면적·관리비를 쉼표로 이은 글.
        price_type_name: '월세', '전세', '매매'.
        price_title: '1000/63'(보증금/월세), '3억9000', '22억' (만원).
        gid: 매물이 있는 동의 다방 번호.
        dong_name: 동 이름.
        is_direct: 직거래인지.
    """

    seq: Annotated[
        int | None,
        Field(description='매물번호')
    ] = None
    id: Annotated[
        str,
        Field(description='매물 ID')
    ]
    room_type_name: Annotated[
        str | None,
        Field(description="매물 종류 ('원룸', '오피스텔 • 단기' 등)", alias='roomTypeName')
    ] = None
    random_location: Annotated[
        DabangLocationModel | None,
        Field(description='흔든 좌표', alias='randomLocation')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지·건물 이름', alias='complexName')
    ] = None
    room_title: Annotated[
        str | None,
        Field(description='한 줄 제목', alias='roomTitle')
    ] = None
    room_desc: Annotated[
        str | None,
        Field(description='층, 면적, 관리비', alias='roomDesc')
    ] = None
    price_type_name: Annotated[
        str | None,
        Field(description='거래 유형', alias='priceTypeName')
    ] = None
    price_title: Annotated[
        str | None,
        Field(description='가격 글자 (만원)', alias='priceTitle')
    ] = None
    gid: Annotated[
        int | None,
        Field(description='동 번호')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description='동 이름', alias='dongName')
    ] = None
    is_direct: Annotated[
        bool | None,
        Field(description='직거래', alias='isDirect')
    ] = None


class DabangPremiumGroupModel(ResponseModel):
    """`premiumList` 한 칸: 광고하는 중개사 하나와 그 매물 (중개사 정보는 모델에 두지 않는다)."""

    room_list: Annotated[
        list[DabangRoomItemModel],
        Field(description='광고 매물', alias='roomList')
    ] = []


class DabangRoomListResultModel(ResponseModel):
    """매물 목록 `result`. 한 쪽 24건 고정이고 `total`·`hasMore` 는 일반 목록(`roomList`) 기준이다 (역삼동 원룸 423건 =
    17쪽×24 + 15 로 18쪽이 `hasMore: false`, 19쪽은 빈 목록, 2026-10-25 실측). 광고(`premiumList`)는 따로 온다.
    """

    room_list: Annotated[
        list[DabangRoomItemModel],
        Field(description='매물', alias='roomList')
    ] = []
    premium_list: Annotated[
        list[DabangPremiumGroupModel],
        Field(description='광고 중개사별 매물', alias='premiumList')
    ] = []
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 매물 수')
    ] = None
    limit: Annotated[
        int | None,
        Field(description='한 쪽 크기 (24)')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None
    page: Annotated[
        int | None,
        Field(description='쪽 번호')
    ] = None


class DabangRoomListResponseModel(DabangV5ResponseModel[DabangRoomListResultModel]):
    """매물 목록 응답 (지도 목록과 단지 매물 목록이 같은 모양)."""


class DabangComplexInfoModel(ResponseModel):
    """단지 상세의 단지 (`complex`).

    `buildCovRatio`·`floorAreaIndex` 는 이름과 값이 뒤바뀌어 온다: `buildCovRatio` 가 용적률, `floorAreaIndex` 가 건폐율이다
    (2026-10-25 실측: 은마 204·20 은 알려진 용적률 204%·건폐율 20%, 강남역센트럴푸르지오시티 799·59). 그래서 필드
    이름을 값의 뜻대로 붙인다.
    """

    complex_id: Annotated[
        str,
        Field(description='단지 ID', alias='complexId')
    ]
    complex_type: Annotated[
        str | None,
        Field(description="'APT' 또는 'OFFICETEL'", alias='complexType')
    ] = None
    complex_type_name: Annotated[
        str | None,
        Field(description="'아파트' 또는 '오피스텔'", alias='complexTypeName')
    ] = None
    complex_name: Annotated[
        str,
        Field(description='단지 이름', alias='complexName')
    ]
    household_num: Annotated[
        int | None,
        Field(description='세대수', alias='householdNum')
    ] = None
    building_num: Annotated[
        int | None,
        Field(description='동 수', alias='buildingNum')
    ] = None
    parking_num: Annotated[
        int | None,
        Field(description='총 주차 대수', alias='parkingNum')
    ] = None
    parking_average: Annotated[
        float | None,
        Field(description='세대당 주차 대수', alias='parkingAverage')
    ] = None
    complex_lowest_floor: Annotated[
        str | None,
        Field(description='최저층', alias='complexLowestFloor')
    ] = None
    complex_highest_floor: Annotated[
        str | None,
        Field(description='최고층', alias='complexHighestFloor')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%). 원본 키 이름은 buildCovRatio 다', alias='buildCovRatio')
    ] = None
    building_coverage_ratio: Annotated[
        float | None,
        Field(description='건폐율 (%). 원본 키 이름은 floorAreaIndex 다', alias='floorAreaIndex')
    ] = None
    provider_name: Annotated[
        str | None,
        Field(description='시공사', alias='providerName')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddress')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadAddress')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    location: Annotated[
        DabangLocationModel | None,
        Field(description='단지 좌표 (출력하지 않는다)')
    ] = None
    heat_type_name: Annotated[
        str | None,
        Field(description='난방', alias='heatTypeName')
    ] = None
    fuel_type_name: Annotated[
        str | None,
        Field(description='연료', alias='fuelTypeName')
    ] = None
    entrance_type_name: Annotated[
        str | None,
        Field(description='현관 구조', alias='entranceTypeName')
    ] = None
    building_approval_date_name: Annotated[
        str | None,
        Field(description="날짜 ('1979.08.30')", alias='buildingApprovalDateName')
    ] = None
    building_approval_type_name: Annotated[
        str | None,
        Field(description="날짜 종류 ('사용승인일')", alias='buildingApprovalTypeName')
    ] = None
    trade_average_pyeong_price: Annotated[
        float | None,
        Field(description='매매 평당 평균가 (만원)', alias='tradeAveragePyeongPrice')
    ] = None


class DabangComplexSpaceModel(ResponseModel):
    """단지의 평형 하나.

    Args:
        space_seq: 평형 번호. 실거래·시세·단지 매물 목록에 넘긴다.
        pyeong_type: 평형 이름 (아파트는 공급 평 '30', 오피스텔은 '13B1').
        room_space: 전용면적 (㎡).
        supply_space: 공급면적 (㎡). 오피스텔은 대개 없다.
        contract_space: 계약면적 (㎡, 오피스텔).
        maintenance_total_price: 관리비 총액 (원, 월).
    """

    space_seq: Annotated[
        int,
        Field(description='평형 번호', alias='spaceSeq')
    ]
    pyeong_type: Annotated[
        str | None,
        Field(description='평형 이름', alias='pyeongType')
    ] = None
    beds_num: Annotated[
        int | None,
        Field(description='방 수', alias='bedsNum')
    ] = None
    bath_num: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathNum')
    ] = None
    room_space: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='roomSpace')
    ] = None
    supply_space: Annotated[
        float | None,
        Field(description='공급면적 (㎡)', alias='supplySpace')
    ] = None
    contract_space: Annotated[
        float | None,
        Field(description='계약면적 (㎡)', alias='contractSpace')
    ] = None
    maintenance_total_price: Annotated[
        float | None,
        Field(description='관리비 총액 (원)', alias='maintenanceTotalPrice')
    ] = None


class DabangAreaAveragePriceModel(ResponseModel):
    """평당 평균가 비교 한 칸 (이 단지·동·구, 만원)."""

    scope: Annotated[
        str,
        Field(description="범위 ('해당 단지', '대치동', '강남구')")
    ]
    trade_average_pyeong_price: Annotated[
        float | None,
        Field(description='매매 평당가 (만원)', alias='tradeAveragePyeongPrice')
    ] = None
    lease_average_pyeong_price: Annotated[
        float | None,
        Field(description='전세 평당가 (만원)', alias='leaseAveragePyeongPrice')
    ] = None


class DabangComplexSchoolModel(ResponseModel):
    """단지 근처 학교 하나. 초등학교의 `hakgudoName` 은 통학구역(배정 학구), 중·고등학교는 학교군 이름이다.

    수는 글자로 온다: `avgStudentsPerClass` '24명', 중학교 `totalEnterSpecialHighSchool` '11명'(특목고 진학)·
    `totalEnterAutonomousHighSchool` '46명'(자율형 진학), 고등학교 `enterUniversity` '대학교 163명' (2026-10-25 은마·
    강남역센트럴푸르지오시티). 중·고등학교는 단지가 든 학교군의 학교를 거리순으로 준다 (17곳·22곳).
    """

    code: Annotated[
        str | None,
        Field(description="학교 코드 (학교알리미, 'S010000743'). `/api/3/education/{level}/{code}` 의 값")
    ] = None
    name: Annotated[
        str,
        Field(description='학교 이름')
    ]
    hakgudo_name: Annotated[
        str | None,
        Field(description='통학구역·학교군 이름', alias='hakgudoName')
    ] = None
    establish_divide: Annotated[
        str | None,
        Field(description="설립 ('공립', '사립')", alias='establishDivide')
    ] = None
    distance: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    avg_students_per_class: Annotated[
        str | None,
        Field(description="학급당 학생 수 ('24명')", alias='avgStudentsPerClass')
    ] = None
    total_enter_special_high_school: Annotated[
        str | None,
        Field(description="특목고 진학 인원 ('11명', 중학교)", alias='totalEnterSpecialHighSchool')
    ] = None
    total_enter_autonomous_high_school: Annotated[
        str | None,
        Field(description="자율형(자사고·자공고) 진학 인원 ('46명', 중학교)", alias='totalEnterAutonomousHighSchool')
    ] = None
    enter_university: Annotated[
        str | None,
        Field(description="대학교 진학 인원 ('대학교 163명', 고등학교)", alias='enterUniversity')
    ] = None


class DabangComplexEducationModel(ResponseModel):
    """단지 근처 학교. 어린이집·유치원도 오지만 jibsa 는 초·중·고만 쓴다."""

    elementary_school: Annotated[
        list[DabangComplexSchoolModel],
        Field(description='초등학교 (배정)', alias='elementarySchool')
    ] = []
    middle_school: Annotated[
        list[DabangComplexSchoolModel],
        Field(description='중학교', alias='middleSchool')
    ] = []
    high_school: Annotated[
        list[DabangComplexSchoolModel],
        Field(description='고등학교', alias='highSchool')
    ] = []


class DabangComplexRegionModel(ResponseModel):
    """단지가 있는 동."""

    full_name: Annotated[
        str | None,
        Field(description='전체 이름', alias='fullName')
    ] = None


class DabangComplexResultModel(ResponseModel):
    """단지 상세 `result`. 사진(`complex.images`)·평면도·광고 중개사(`premiumNearAgents`)도 오지만 모델에 두지 않는다."""

    complex: Annotated[
        DabangComplexInfoModel,
        Field(description='단지')
    ]
    spaces: Annotated[
        list[DabangComplexSpaceModel],
        Field(description='평형')
    ] = []
    area_average_price: Annotated[
        list[DabangAreaAveragePriceModel],
        Field(description='평당가 비교', alias='areaAveragePrice')
    ] = []
    education: Annotated[
        DabangComplexEducationModel | None,
        Field(description='근처 학교')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수', alias='roomCount')
    ] = None
    primary_space_seq: Annotated[
        int | None,
        Field(description='대표 평형 번호', alias='primarySpaceSeq')
    ] = None
    region: Annotated[
        DabangComplexRegionModel | None,
        Field(description='동')
    ] = None


class DabangComplexV5ResponseModel(DabangV5ResponseModel[DabangComplexResultModel]):
    """`GET /api/v5/complex/{complex_id}` 응답. 없는 단지 ID 는 HTTP 오류다."""
