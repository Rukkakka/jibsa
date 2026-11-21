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

class ZigbangSchoolDetailModel(ZigbangBaseResponseModel):
    """학교 정보. 전화·홈페이지·좌표·학생 수·급식 같은 이 밖의 키는 읽지 않는다."""

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
