"""직방 service 지역 화면 공통: 동·구 해석, 결과 머리(`region`), 거래 유형·정렬 이름 찾기 (region-info·region-trades·region-ranking). 해당 없는 키를 빼는 결과·줄 기반 모델은 local.models 에 있다."""

from jibsa.core.errors import JibsaError
from jibsa.core.korean import full_legal_division_code
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.service.common.models import ZigbangAptRegion
from jibsa.providers.zigbang.service.local.models import (
    LocalLevel,
    LocalTrade,
    ZigbangLocalRegion,
)
from jibsa.providers.zigbang.service.region import resolve_apt_area

from typing import (
    NamedTuple,
    TypeVar,
)


SortValueT = TypeVar('SortValueT')

LOCAL_TRADES: tuple[LocalTrade, ...] = ('매매', '전세', '월세')
# 세 명령이 같은 말로 동·구를 찾는다. 서버는 시·도 코드(2자리)도 받지만 웹 지역 화면이 시·도를 보여 주는지 확인하지 못해 받지 않는다
LOCAL_SIDO_MESSAGE: str = '시·도 이름이라 조회할 수 없습니다 (동·구 단위로 조회합니다)'
LOCAL_SIDO_HINT: str = "구나 동 이름을 주세요 (예: '송파구', '가락동')"
# 지역 해석의 일반 hint 는 역 이름으로 다시 찾으라고 하지만 이 명령들은 역·학교·단지 이름을 받지 않는다
LOCAL_NOT_FOUND_HINT: str = "동·구 이름을 주세요 (예: '송파구', '가락동'). 역·학교·단지 이름은 받지 않습니다"
# region-info·region-trades·region-ranking 이 같이 쓴다 (세 명령 모두 직방 웹 지역 화면의 값이다)
LOCAL_RI_CHECK: str = '직방 지역 화면은 읍·면 단위입니다'


class ZigbangLocalArea(NamedTuple):
    """찾은 동·구 하나."""

    region: ZigbangAptRegion
    level: LocalLevel
    # 직방 지역 코드 (`local_code_of`)
    code: str
    # 지역을 찾으며 생긴 안내 (○가 동·리 범위 안내)
    notes: list[str]


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
