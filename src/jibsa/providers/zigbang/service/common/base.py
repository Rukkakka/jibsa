"""직방 service 공통(기본): 상세 URL·단지 ID, 단지 조회, 여러 모듈이 쓰는 상수·변환 함수. 지역·매물·동 경계·상세 결과 모델은 common.models 에 있다."""

import re
from collections.abc import Generator
from contextlib import contextmanager

from httpx import HTTPStatusError
from pydantic import BaseModel

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    AmountRange,
    AmountSet,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangDanjisResponseModel
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice

from typing import (
    Any,
    Literal,
)


WEB_PATH_BY_SERVICE_TYPE: dict[str, str] = {
    '원룸': 'oneroom',
    '오피스텔': 'officetel',
    '빌라': 'villa',
}
# 덤 조회(학군·건물 ID·--details 상세 등)는 이 실패들을 그 칸만 모름으로 둔다. 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`:
# 네트워크·상태 코드, 차단 페이지·응답 형식 변경·19자리가 아닌 pnu)에 요청 제한을 더한다
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, RateLimitedError)
# 매물 목록 명령의 --limit 최대값. CLI 옵션의 max 와 상한 안내(`common.apt` 의 `apt_pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120

# 방향 코드 → 라벨. 주거 상세(`room.detail`)와 아파트 상세(`apt`)가 함께 쓴다
DIRECTION_LABELS: dict[str, str] = {
    'N': '북향',
    'S': '남향',
    'E': '동향',
    'W': '서향',
    'NE': '북동향',
    'NW': '북서향',
    'SE': '남동향',
    'SW': '남서향',
}

# 학교군 안 중·고등학교는 10곳 넘게 오기도 해 가까운 곳만 (당근과 같은 수)
NEAREST_SCHOOLS: int = 2


# 응답 형식이 달라 값을 모를 때 안내 끝 문장. 매일 API 감시가 이 안의 UPDATE_MAYBE_NEEDED 로 고장을 잡는다
UNEXPECTED_FORMAT_TEXT: str = f'직방 응답이 예상한 형식과 달라 {UPDATE_MAYBE_NEEDED}'
# 본 조회 목록을 주지 않아 UPSTREAM_ERROR 로 멈출 때의 hint
UPSTREAM_RETRY_HINT: str = f'잠시 뒤 다시 시도하세요. 계속되면 직방 API 가 바뀐 것일 수 있어 {UPDATE_MAYBE_NEEDED}'

ComplexKind = Literal['apt', 'officetel']
# 아파트 단지 ID 와 오피스텔 건물 ID 는 번호 체계가 달라 같은 숫자가 다른 단지일 수 있어 접두어로 구분한다
COMPLEX_ID_PATTERN: re.Pattern[str] = re.compile(r'^(apt|officetel)-(\d+)$')

# 세대수 문구 (예: '38세대', '1,161세대'). 관련 단지(complex)와 주변 단지 카드·학교·역 응답(search complexes)이 쓴다
HOUSEHOLD_TEXT_PATTERN: re.Pattern[str] = re.compile(r'([\d,]+)\s*세대')


def estimated_prices_of(
    sale_price_manwon: float | None,
    sale_price_per_pyeong_manwon: float | None,
    jeonse_price_manwon: float | None,
    jeonse_price_per_pyeong_manwon: float | None,
) -> dict[str, ZigbangEstimatedPrice | None]:
    """직방시세® 매매·전세 값을 estimated_prices 로 묶는다. 늘 'sale'·'jeonse' 두 키이고, 거래의 안 값이 모두 없으면 그 거래가 모름(null), 일부만 없으면 그 칸만 null 이다."""
    return {
        'sale': None if sale_price_manwon is None and sale_price_per_pyeong_manwon is None else ZigbangEstimatedPrice(
            price_manwon=sale_price_manwon, price_per_pyeong_manwon=sale_price_per_pyeong_manwon,
        ),
        'jeonse': None if jeonse_price_manwon is None and jeonse_price_per_pyeong_manwon is None else ZigbangEstimatedPrice(
            deposit_manwon=jeonse_price_manwon, price_per_pyeong_manwon=jeonse_price_per_pyeong_manwon,
        ),
    }


def sale_price_range(lowest_manwon: float | None, highest_manwon: float | None) -> AmountRange | None:
    """매매가 범위 (직방시세 estimated_ranges 의 'sale', 평형 추이 trade_range). 두 끝이 모두 없으면 모름(None)이고, 한 끝만 없으면 그 price_manwon 만 null 이다."""
    if lowest_manwon is None and highest_manwon is None:
        return None
    return AmountRange(lowest=AmountSet(price_manwon=lowest_manwon), highest=AmountSet(price_manwon=highest_manwon))


def item_url(service_type: str | None, item_id: int) -> str:
    path = WEB_PATH_BY_SERVICE_TYPE.get(service_type or '', 'oneroom')
    return f'https://www.zigbang.com/home/{path}/items/{item_id}'


def text_or_none(value: str | None) -> str | None:
    """앞뒤 공백을 떼고, 빈 글자는 모름(None). 아파트 상세는 값이 없는 칸을 빈 글자로 준다 (`oldAddress` 등).

    방향 기준(`directionBase`)은 '기준' 을 떼야 해 `apt_item_to_listing` 이 같은 규칙을 따로 적용한다.
    """
    return (value.strip() or None) if value else None


def school_label(name: str | None, *details: str | None) -> str | None:
    if not name:
        return None
    shown = [detail for detail in details if detail]
    return f"{name} ({', '.join(shown)})" if shown else name


def sent_or_none(model: BaseModel, field: str, values: list[str]) -> list[str] | None:
    """응답에 `field` 키가 왔으면 `values`, 키가 빠졌으면 모름(None).

    응답 모델은 빠진 목록을 [] 로 채워서 그대로 내보내면 모름이 '없음' 이 된다 (값이 없을 때: 모름 → null, 비어 있음 → []).
    2026-10-12 실측: 새 주거 상세 18건(원룸·빌라·오피스텔·아파트) 모두 options·subways·manageCost.includes 키가 왔다.
    """
    return values if field in model.model_fields_set else None


@contextmanager
def unavailable_on_404(listing_id: int | str, reason: str | None = None) -> Generator[None, None, None]:
    """상세 요청의 404 를 만료 매물(`ListingUnavailableError`)로 바꾼다. 그 밖의 HTTP 오류는 그대로 낸다.

    Args:
        listing_id: 매물 ID.
        reason: 직방 매물인 것을 알고 부른 상세면 그 사유. 없으면 다른 소스 ID 일 수 있다는 안내가 붙는다.
    """
    try:
        yield
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ListingUnavailableError('zigbang', listing_id, reason=reason) from None
        raise


def drop_unused_scope(data: dict[str, Any]) -> dict[str, Any]:
    """검색 결과에서 쓰지 않은 범위 키(반경이면 boundary, 경계면 radius_km)를 뺀다."""
    for field in ('radius_km', 'boundary'):
        if data.get(field) is None:
            data.pop(field, None)
    return data


def apt_complex_id(danji_id: int) -> str:
    return f'apt-{danji_id}'


def officetel_complex_id(building_id: int) -> str:
    return f'officetel-{building_id}'


def apt_danji_url(danji_id: int) -> str:
    return f'https://www.zigbang.com/home/apt/danjis/{danji_id}'


def household_count(text: str | None) -> int | None:
    """세대수 문구('1,161세대')를 정수로. 읽지 못하면 None."""
    match = HOUSEHOLD_TEXT_PATTERN.fullmatch((text or '').strip())
    return int(match.group(1).replace(',', '')) if match else None


def parse_complex_id(complex_id: str) -> tuple[ComplexKind, int]:
    """`apt-68579` / `officetel-20227` 를 (종류, 번호) 로 나눈다.

    Raises:
        JibsaError: 형식이 맞지 않을 때 (INVALID_ARGUMENT).
    """
    match = COMPLEX_ID_PATTERN.match(complex_id.strip())
    if match is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 단지 ID 형식이 아닙니다: '{complex_id}'",
            hint="jibsa zigbang search locations <단지 이름> 결과의 complexes[].complex_id 나 검색 결과의 complex_id "
                 "(예: 'apt-68579', 'officetel-20227') 를 그대로 주세요",
        )
    kind, number = match.groups()
    return kind, int(number)  # type: ignore[return-value]


def complex_not_found(complex_id: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f"직방에서 단지를 찾을 수 없습니다: '{complex_id}'",
        hint='jibsa zigbang search locations <단지 이름> 으로 단지를 다시 찾아 결과의 complexes[].complex_id 를 그대로 주세요',
        details={'complex_id': complex_id},
    )


# 상태 코드 → 에러 변환은 엔드포인트마다 코드·에러가 달라(상세 404 → 만료 `unavailable_on_404`, 단지 404 → NOT_FOUND,
# 오피스텔 건물 400·404 → NOT_FOUND) 공통 컨텍스트 매니저로 묶지 않는다
def fetch_danji(client: ZigbangClient, complex_id: str, danji_id: int) -> ZigbangDanjisResponseModel:
    try:
        return client.run_request_danjis(ZigbangDanjisRequestParameterModel(danji_id=danji_id))
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise complex_not_found(complex_id) from None
        raise
