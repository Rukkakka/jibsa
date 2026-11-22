"""응답 모델: 역·학교·동·구 주변 아파트 단지 (search complexes)."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import ZigbangBaseResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/subways/{subwayId}
# ---------------------------------------------------------------------------

class ZigbangSubwayAptModel(ZigbangBaseResponseModel):
    """역 주변 아파트 단지 하나. 단지 좌표(`lat`·`lng`)도 오지만 읽지 않는다."""

    id: Annotated[
        int,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    old_address: Annotated[
        str | None,
        Field(description="지번 주소 (예: '서울시 서초구 서초동 1319-13', 시·도를 줄여 준다)", alias='구주소')
    ] = None
    household: Annotated[
        str | None,
        Field(description="세대수 문구 (예: '38세대')")
    ] = None
    distance_num: Annotated[
        int | None,
        Field(description='역에서의 거리 (m)', alias='distanceNum')
    ] = None


class ZigbangSubwaysResponseModel(ZigbangBaseResponseModel):
    """역 정보와 역에서 1.5km 안 아파트 단지 (거리순, 2026-11-15 실측: 강남역 112곳)."""

    id: Annotated[
        int,
        Field(description='역 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='역 이름')
    ] = None
    apt_list: Annotated[
        list[ZigbangSubwayAptModel] | None,
        Field(description='역 주변 단지 (가까운 순). 서버가 null 을 주면 없는 것으로 읽는다', alias='aptList')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/danjis/ids
# ---------------------------------------------------------------------------

class ZigbangDanjisIdsResponseModel(ZigbangBaseResponseModel):
    """주변 단지 ID 를 요청한 순서(`order` 로 고른 직방 웹 목록 순서)로."""

    count: Annotated[
        int | None,
        Field(description='주변 단지 전체 수 (limit 적용 전)')
    ] = None
    ids: Annotated[
        list[int] | None,
        Field(description='단지 ID (요청한 순서). 서버가 null 을 주면 없는 것으로 읽는다')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/danjis/details
# ---------------------------------------------------------------------------

class ZigbangDanjiCardModel(ZigbangBaseResponseModel):
    """웹 단지 목록 카드 하나. 사진(`image`)은 읽지 않는다."""

    id: Annotated[
        int,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    desc1: Annotated[
        str | None,
        Field(description="카드 첫째 줄: 구·동과 세대수 (예: '송파구 가락동 · 9,510세대')")
    ] = None
    desc2: Annotated[
        str | None,
        Field(
            description=(
                "카드 둘째 줄. 요청한 순서 탭(`order`)마다 뜻이 다르다: viewCount 는 동·구 안의 조회수 순위 (예: '가락동 1위 · 송파구 1위'), "
                "newest 는 입주 시기 (예: '2026. 1 입주'), priceChange 는 1주 시세 변동률 (예: '-3.23%'), areaPrice 는 평당가 "
                "(예: '14,758만 / 3.3㎡'). 2026-11-19 웹 캡처의 문구"
            )
        )
    ] = None
    service_category: Annotated[
        str | None,
        Field(description='단지 구분 (입주2년후·입주2년내·분양예정)', alias='서비스구분')
    ] = None


class ZigbangDanjisDetailsResponseModel(ZigbangBaseResponseModel):
    """요청한 단지 ID 의 카드 (2026-11-19 표본 둘은 요청한 ID 순서였다)."""

    apts: Annotated[
        list[ZigbangDanjiCardModel] | None,
        Field(description='단지 카드. 서버가 null 을 주면 없는 것으로 읽는다')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/schools/{schoolCode}
# ---------------------------------------------------------------------------

class ZigbangSchoolMiddleOutcomeModel(ZigbangBaseResponseModel):
    """중학교의 고등학교 진학 현황 (`onlyMiddleNew`). 웹 '고등학교 진학 현황' 이 특목고·일반고·기타 인원과 비율을 보여 준다.

    2026-11-22 표본 중학교 둘은 모두 null 이었다 (비율 칸은 표본에 없지만 웹 코드가 읽는다). 인원(명)·비율(%)이 숫자인지 글자인지 정해지지 않아 넓게 받는다.
    """

    special: Annotated[
        int | float | str | None,
        Field(description='특목고 진학 인원 (명)')
    ] = None
    special_percent: Annotated[
        int | float | str | None,
        Field(description='특목고 진학 비율 (%)', alias='specialPercent')
    ] = None
    normal: Annotated[
        int | float | str | None,
        Field(description='일반고 진학 인원 (명)')
    ] = None
    normal_percent: Annotated[
        int | float | str | None,
        Field(description='일반고 진학 비율 (%)', alias='normalPercent')
    ] = None
    etc: Annotated[
        int | float | str | None,
        Field(description='기타 진학 인원 (명)')
    ] = None
    etc_percent: Annotated[
        int | float | str | None,
        Field(description='기타 진학 비율 (%)', alias='etcPercent')
    ] = None


class ZigbangSchoolHighOutcomeModel(ZigbangBaseResponseModel):
    """고등학교의 대학 진학 현황 (`onlyHighNew`). 웹 '대학교 진학 현황' 이 일반대·전문대·기타 인원과 비율을 보여 준다.

    2026-11-22 표본에서는 인원·비율이 모두 null 이고 `highCategory` 만 있었다. 인원(명)·비율(%)이 숫자인지 글자인지 정해지지 않아 넓게 받는다.
    """

    normaluniv: Annotated[
        int | float | str | None,
        Field(description='일반대 진학 인원 (명)')
    ] = None
    normaluniv_percent: Annotated[
        int | float | str | None,
        Field(description='일반대 진학 비율 (%)', alias='normalunivPercent')
    ] = None
    college: Annotated[
        int | float | str | None,
        Field(description='전문대 진학 인원 (명)')
    ] = None
    college_percent: Annotated[
        int | float | str | None,
        Field(description='전문대 진학 비율 (%)', alias='collegePercent')
    ] = None
    etc: Annotated[
        int | float | str | None,
        Field(description='기타 진학 인원 (명)')
    ] = None
    etc_percent: Annotated[
        int | float | str | None,
        Field(description='기타 진학 비율 (%)', alias='etcPercent')
    ] = None
    high_category: Annotated[
        str | None,
        Field(description="고등학교 구분 (예: '일반고')", alias='highCategory')
    ] = None


class ZigbangSchoolDetailModel(ZigbangBaseResponseModel):
    """학교 정보. 웹 학교 화면(`SchoolsDetailScreen`)이 보여 주는 학생 수·입학생·학급·학비·급식비와 같은 구 평균, 진학 현황을 읽는다.

    전화·홈페이지·주소·좌표·기준 연도(`year`)·학교 자체의 입학생 증감(`increase`, 웹이 그리지 않는다)은 읽지 않는다. 숫자가 글자로 오는 칸이 섞여
    (2026-11-22 표본: `class` '28', `expense` '1077702', `manPercent` '71' 은 글자, `all`·`freshman`·`local` 은 숫자) 숫자 칸은 모두
    `int | float | str` 로 받고 service 가 바꾼다. 같은 구 평균 칸은 웹이 '{구} 평균' 으로 보여 주는 값이다.
    """

    id: Annotated[
        int,
        Field(description='학교 ID. 단지 ID 목록 조회(`type=school`)에 넘기는 값이다 (학교 코드가 아니다)')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    school_code: Annotated[
        str | None,
        Field(description="학교 코드 (예: 'B100006434'). 웹 학교 화면 주소의 코드", alias='schoolCode')
    ] = None
    stage: Annotated[
        str | None,
        Field(description="학교급 ('elementary' 초등, 'middle' 중, 'high' 고)")
    ] = None
    sullib: Annotated[
        str | None,
        Field(description="설립 구분 (예: '공립')")
    ] = None
    gender: Annotated[
        str | None,
        Field(description="남녀 구분 (예: '공학')")
    ] = None
    foundation_date: Annotated[
        str | None,
        Field(description='설립일 (YYYY-MM-DD)', alias='foundationDate')
    ] = None
    local2: Annotated[
        str | None,
        Field(description="학교가 있는 구 (같은 구 평균의 구. 예: '송파구')")
    ] = None
    all: Annotated[
        int | float | str | None,
        Field(description='전체 학생 수 (명)')
    ] = None
    man_percent: Annotated[
        int | float | str | None,
        Field(description='남학생 비율 (%)', alias='manPercent')
    ] = None
    woman_percent: Annotated[
        int | float | str | None,
        Field(description='여학생 비율 (%)', alias='womanPercent')
    ] = None
    local: Annotated[
        int | float | str | None,
        Field(description='같은 구 학교의 평균 학생 수 (명, 소수로 온다)')
    ] = None
    local_man_percent: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 남학생 비율 (%)', alias='localManPercent')
    ] = None
    local_woman_percent: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 여학생 비율 (%)', alias='localWomanPercent')
    ] = None
    freshman: Annotated[
        int | float | str | None,
        Field(description='입학생 수 (명)')
    ] = None
    local_freshman: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 입학생 수 (명)', alias='localFreshman')
    ] = None
    local_increase: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 입학생의 전년 대비 증감 (%, 음수는 감소)', alias='localIncrease')
    ] = None
    class_: Annotated[
        int | float | str | None,
        Field(description='학급당 학생 수 (명). 응답 키는 `class`', alias='class')
    ] = None
    local_class: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 학급당 학생 수 (명)', alias='localClass')
    ] = None
    expense: Annotated[
        int | float | str | None,
        Field(description='학비 (원). 연간인지 월인지는 웹이 적지 않아 모른다')
    ] = None
    local_expense: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 학비 (원)', alias='localExpense')
    ] = None
    meal: Annotated[
        int | float | str | None,
        Field(description='급식비 (원). 1식인지 기간 합인지는 웹이 적지 않아 모른다')
    ] = None
    meal_type: Annotated[
        str | None,
        Field(description="급식 방식 ('직영'·'일부위탁')", alias='mealType')
    ] = None
    meal_local: Annotated[
        int | float | str | None,
        Field(description='같은 구 평균 급식비 (원)', alias='mealLocal')
    ] = None
    only_middle_new: Annotated[
        ZigbangSchoolMiddleOutcomeModel | None,
        Field(description='중학교의 고등학교 진학 현황. 고등학교 표본에도 모든 칸이 null 인 채로 왔다 (2026-11-22)', alias='onlyMiddleNew')
    ] = None
    only_high_new: Annotated[
        ZigbangSchoolHighOutcomeModel | None,
        Field(description='고등학교의 대학 진학 현황. 중학교 표본에도 모든 칸이 null 인 채로 왔다 (2026-11-22)', alias='onlyHighNew')
    ] = None


class ZigbangSchoolAptModel(ZigbangBaseResponseModel):
    """학교 주변 아파트 단지 하나."""

    apartment_id: Annotated[
        int,
        Field(description='단지 ID', alias='apartmentId')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    household: Annotated[
        str | None,
        Field(description="세대수 문구 (예: '9,510세대')")
    ] = None
    distance: Annotated[
        str | None,
        Field(description="학교에서 거리 문구 (예: '462m', '1.1km')")
    ] = None


class ZigbangSchoolsResponseModel(ZigbangBaseResponseModel):
    """학교 정보와 학교 주변 아파트 단지 (가까운 순). 시세 구간(`price`)은 읽지 않는다."""

    detail: Annotated[
        ZigbangSchoolDetailModel | None,
        Field(description='학교 정보')
    ] = None
    apt_list: Annotated[
        list[ZigbangSchoolAptModel] | None,
        Field(
            description='학교 주변 단지 (가까운 순. 2026-11-19 표본 해누리중학교는 176m 부터). 서버가 null 을 주면 없는 것으로 읽는다',
            alias='aptList',
        )
    ] = None
