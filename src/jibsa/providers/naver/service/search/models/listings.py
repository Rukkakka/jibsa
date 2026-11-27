"""`listings.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    Field,
)

from jibsa.providers.naver.service.common.models import (
    NaverTradeConditions,
)

from typing import (
    Annotated,
)


class NaverListingConditions(NaverTradeConditions):
    """지도 매물 검색 조건 (search listings). 금액은 만원, 면적은 ㎡.

    모두 서버 필터로 보내고 받은 뒤 다시 거르지 않는다 (`search_area`). 목록 안의 여러 값은 시설·단지 주차만
    모두 해당(AND)이고 나머지는 하나라도 해당(OR)이다. 세대수·단지 주차는 단지로 등록된 매물에만 있고, 현관 구조는
    등록된 매물(단지가 아닌 빌라 포함)에만 걸린다.
    """

    property_types: Annotated[
        list[str],
        Field(description='매물 유형 (PROPERTY_TYPES). 비면 주거용 (DEFAULT_SEARCH_PROPERTY_TYPES)')
    ] = []
    room_types: Annotated[
        list[str],
        Field(description='방 수 (ROOM_COUNT_CODE_BY_NAME). 목록에는 방 수가 없어 서버에서만 거른다')
    ] = []
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    area_basis: Annotated[
        str,
        Field(description='면적 기준 (AREA_BASES). 전용이면 전용면적, 공급이면 공급면적으로 비교한다')
    ] = '전용'
    floors: Annotated[
        list[str],
        Field(description='층 (FLOOR_CODE_BY_NAME)')
    ] = []
    directions: Annotated[
        list[str],
        Field(description='방향 (DIRECTION_FILTER_CODE_BY_NAME)')
    ] = []
    manage_cost_min: Annotated[
        int | None,
        Field(description='관리비 하한 (만원)')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(description='관리비 상한 (만원)')
    ] = None
    bathrooms: Annotated[
        list[str],
        Field(description='욕실 수 (BATHROOM_CODE_BY_NAME)')
    ] = []
    facilities: Annotated[
        list[str],
        Field(description='시설 (FACILITY_CODE_BY_NAME). 모두 갖춘 매물만')
    ] = []
    one_room_shapes: Annotated[
        list[str],
        Field(description='원룸 구조 (ONE_ROOM_SHAPE_CODE_BY_NAME). 분리형에는 방이 여럿인 매물도 들어가고, 구조를 입력하지 않은 매물(단지 매물은 전부)은 빠진다')
    ] = []
    move_in: Annotated[
        list[str],
        Field(description='입주 가능일 (MOVE_IN_CODE_BY_NAME)')
    ] = []
    loan: Annotated[
        str | None,
        Field(description='융자금 조건 (LOAN_CODE_BY_NAME)')
    ] = None
    photo_only: Annotated[
        bool,
        Field(description='사진 있는 매물만')
    ] = False
    household_min: Annotated[
        int | None,
        Field(description='단지 세대수 하한')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='단지 세대수 상한')
    ] = None
    parking: Annotated[
        list[str],
        Field(description='단지 주차 조건 (PARKING_CODE_BY_NAME). 모두 해당하는 매물만')
    ] = []
    entrances: Annotated[
        list[str],
        Field(description='현관 구조 (ENTRANCE_CODE_BY_NAME)')
    ] = []
    building_age_min: Annotated[
        int | None,
        Field(description='사용승인 후 지난 햇수 하한')
    ] = None
    building_age_max: Annotated[
        int | None,
        Field(description='사용승인 후 지난 햇수 상한')
    ] = None
    subway_minutes: Annotated[
        int | None,
        Field(description='지하철역까지 걸어서 이 분 안인 매물만 (역세권)')
    ] = None
    owner_verified_only: Annotated[
        bool,
        Field(description='집주인 확인 매물만')
    ] = False
