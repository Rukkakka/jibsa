"""직방 service 지역 화면 공통: 동·구 해석, 결과 머리(`region`), 해당 없는 키를 빼는 결과·줄 기반 모델, 거래 유형·정렬 이름 찾기 (region-info·region-trades·region-ranking)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.korean import full_legal_division_code
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.service.common.base import ZigbangAptRegion
from jibsa.providers.zigbang.service.region import resolve_apt_area

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
    TypeVar,
)


SortValueT = TypeVar('SortValueT')
LocalLevel = Literal['동', '구']
LocalTrade = Literal['매매', '전세', '월세']
LOCAL_TRADES: tuple[LocalTrade, ...] = ('매매', '전세', '월세')
# 세 명령이 같은 말로 동·구를 찾는다. 서버는 시·도 코드(2자리)도 받지만 웹 지역 화면이 시·도를 보여 주는지 확인하지 못해 받지 않는다
LOCAL_SIDO_MESSAGE: str = '시·도 이름이라 조회할 수 없습니다 (동·구 단위로 조회합니다)'
LOCAL_SIDO_HINT: str = "구나 동 이름을 주세요 (예: '송파구', '가락동')"
# 지역 해석의 일반 hint 는 역 이름으로 다시 찾으라고 하지만 이 명령들은 역·학교·단지 이름을 받지 않는다
LOCAL_NOT_FOUND_HINT: str = "동·구 이름을 주세요 (예: '송파구', '가락동'). 역·학교·단지 이름은 받지 않습니다"
# region-info·region-trades·region-ranking 이 같이 쓴다 (세 명령 모두 직방 웹 지역 화면의 값이다)
LOCAL_RI_CHECK: str = '직방 지역 화면은 읍·면 단위입니다'
# 줄의 동(`dong`) 필드 설명. 실거래·랭킹 줄이 같이 쓴다
LOCAL_DONG_DESCRIPTION: str = (
    "줄이 속한 동 (직방이 준 local, 예: '가락동'). 구 단위 조회에만 있고 동 단위 조회는 서버가 빈 글자를 줘 키가 없다. "
    '구 단위인데 직방이 주지 않으면 null'
)


class ZigbangLocalRegion(BaseModel):
    """지역 화면 명령 결과의 머리: 조회한 동·구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동·구 이름. region-info 는 직방 지역 정보의 이름 (예: 성남시 분당구), 그 밖은 찾은 지역 이름. 리는 상위 읍·면으로 찾아 notes 로 알린다')
    ]
    level: Annotated[
        LocalLevel,
        Field(description="조회 단위. 시·군·구는 '구', 읍·면·동은 '동' (리는 상위 읍·면이라 '동')")
    ]
    address: Annotated[
        str | None,
        Field(description='찾은 지역의 전체 주소')
    ]
    legal_division_code: Annotated[
        str,
        Field(description='법정동코드 (10자리). 직방이 지역 화면에 쓰는 5자리(구)·8자리(동) 코드 뒤를 0 으로 채운 값이다. 리는 상위 읍·면 코드다')
    ]


class ZigbangLocalArea(NamedTuple):
    """찾은 동·구 하나."""

    region: ZigbangAptRegion
    level: LocalLevel
    # 직방 지역 코드 (`local_code_of`)
    code: str
    # 지역을 찾으며 생긴 안내 (○가 동·리 범위 안내)
    notes: list[str]


class ZigbangLocalModel(BaseModel):
    """결과·줄의 기반. 해당 없는 칸은 출력에서 키를 뺀다 (`not_applicable`).

    같은 모델이 거래 유형·정렬·조회 단위마다 다른 칸을 내므로, 만들 때 뺄 칸 이름을 정해 넘긴다. 값을 모르는 칸은 키를 두고 null 이다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    not_applicable: Annotated[
        frozenset[str],
        Field(exclude=True, description='이 결과·줄에 해당하지 않아 출력에서 키를 뺄 칸 이름. 출력하지 않는다')
    ] = frozenset()

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.not_applicable:
            data.pop(field, None)
        return data


def resolve_local_area(client: ZigbangClient, query: str) -> ZigbangLocalArea:
    """동·구 하나를 찾는다 (지역 검색 1회). 같은 이름 동·구, '○가' 동, 구가 있는 시는 묻고, 시·도는 받지 않는다 (`resolve_apt_area`).

    Raises:
        JibsaError: 시·도 이름일 때 (INVALID_ARGUMENT).
        RegionNotFoundError: 동·구를 찾지 못했을 때 (역·학교·단지 이름은 받지 않는다).
        RegionAmbiguousError: 같은 이름의 동·구가 여럿이거나 구가 있는 시·'○가' 로만 나뉜 동일 때.
    """
    region, level, code, notes = resolve_apt_area(
        client,
        query,
        ri_check=LOCAL_RI_CHECK,
        sido_message=LOCAL_SIDO_MESSAGE,
        sido_hint=LOCAL_SIDO_HINT,
        not_found_hint=LOCAL_NOT_FOUND_HINT,
    )
    return ZigbangLocalArea(region=region, level=level, code=code, notes=notes)


def local_region_of(area: ZigbangLocalArea, name: str | None = None) -> ZigbangLocalRegion:
    """결과 머리 `region`. `name` 이 있으면 그것(직방 지역 정보의 이름), 없으면 찾은 지역 이름이다."""
    return ZigbangLocalRegion(
        name=name or area.region.name,
        level=area.level,
        address=area.region.address,
        legal_division_code=full_legal_division_code(area.code),
    )


def dong_not_applicable(level: LocalLevel) -> frozenset[str]:
    """동 단위 조회는 줄의 동(`dong`)이 해당 없어 키를 뺀다. 구 단위에서만 키가 있다 (`LOCAL_DONG_DESCRIPTION`)."""
    return frozenset({'dong'}) if level == '동' else frozenset()


def local_sort_of(trade: LocalTrade, sort: str | None, sorts: dict[str, SortValueT]) -> tuple[str, SortValueT]:
    """정렬 이름을 (웹 이름, 서버 정렬 값) 으로 바꾼다. 안 주면 그 거래의 첫 정렬이고 (웹 기본), 빈칸 없는 이름('최신등록순')도 받는다.

    Args:
        trade: 거래 유형. 에러 문장에 쓴다.
        sort: `--sort` 값.
        sorts: 그 거래의 웹 정렬 이름 → 서버 정렬 값 (웹 순서, 첫 항목이 웹 기본).

    Raises:
        JibsaError: 그 거래에 없는 정렬일 때 (INVALID_ARGUMENT). 지역을 찾기 전에 부른다.
    """
    if sort is None:
        label = next(iter(sorts))
        return label, sorts[label]
    compact = sort.strip().replace(' ', '')
    for label, value in sorts.items():
        if label.replace(' ', '') == compact:
            return label, value
    raise JibsaError(
        code='INVALID_ARGUMENT',
        message=f"--trade {trade} 에 없는 --sort 값입니다: '{sort}'",
        hint=f"--trade {trade} 에서는 이 중에서 고르세요: {', '.join(sorts)}. 다른 거래의 정렬이면 --trade 를 바꾸세요",
    )
