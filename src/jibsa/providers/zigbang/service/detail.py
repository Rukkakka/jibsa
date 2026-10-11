"""listing 명령의 ID 분기: ID 형식을 보고 주거·상가·단기임대·제휴 상세로 보낸다."""

import re

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.service.listing import (
    ZigbangListingDetail,
    get_coalition_listing,
    get_listing,
)
from jibsa.providers.zigbang.service.stay import (
    ZigbangStayListingDetail,
    get_stay_listing,
)
from jibsa.providers.zigbang.service.store import (
    ZigbangStoreListingDetail,
    get_store_listing,
)


LISTING_ID_PATTERN: re.Pattern[str] = re.compile(r'^(?:(store|stay|coalition)-)?([1-9]\d*)$')


def get_any_listing(
    client: ZigbangClient,
    listing_id: str,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
    pet: bool = False,
) -> ZigbangListingDetail | ZigbangStoreListingDetail | ZigbangStayListingDetail:
    """검색 결과의 `id` 그대로 상세를 조회한다.

    숫자만이면 원룸·오피스텔·빌라·아파트(`get_listing`: 새 상세 API, 입주일이 비면 `/v3/items` 로 보완),
    `store-` 는 상가, `stay-` 는 단기임대, `coalition-` 은 아파트 제휴(호갱노노 집주인) 매물이다.
    매물 번호 체계가 서로 달라 같은 숫자가 다른 매물일 수 있어 접두어로 구분한다.
    입주·퇴거일(`check_in`·`check_out`, `pet`)은 단기임대만 받는다.

    Raises:
        JibsaError: ID 형식이 맞지 않거나, 단기임대가 아닌데 입주·퇴거일을 줬을 때 (INVALID_ARGUMENT).
        ListingUnavailableError: 거래할 수 없는 매물일 때.
    """
    match = LISTING_ID_PATTERN.match(listing_id.strip())
    if match is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 매물 ID 형식이 아닙니다: '{listing_id}'",
            hint="search 결과는 숫자, store 결과는 'store-123', stay 결과는 'stay-123', 아파트 제휴 매물은 'coalition-123' 처럼 결과의 id 를 그대로 주세요",
        )
    kind, number = match.groups()
    if kind != 'stay' and (check_in or check_out or pet):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='입주·퇴거일과 반려동물 조건은 직방 단기임대(stay-…) 상세에만 쓸 수 있습니다',
            hint='--check-in/--check-out/--pet 을 빼고 다시 조회하세요',
        )
    if kind == 'store':
        return get_store_listing(client, int(number))
    if kind == 'stay':
        return get_stay_listing(client, int(number), check_in=check_in, check_out=check_out, pet=pet)
    if kind == 'coalition':
        return get_coalition_listing(client, int(number))
    try:
        return get_listing(client, int(number))
    except ListingUnavailableError as exc:
        # 접두어를 뗀 상가·단기임대·제휴 번호(store-961398 → 961398)는 주거 상세에서 404 로 끝나 상태값이 없다.
        # close 처럼 상태가 있으면 실제로 내려간 주거 매물이라 접두어 안내를 붙이지 않는다.
        if exc.details.get('listing_status') is None:
            exc.hint = (
                f'{exc.hint}. 상가·단기임대·아파트 제휴 매물이면 결과의 id 그대로 '
                "'store-…'·'stay-…'·'coalition-…' 접두어를 붙였는지 확인하세요"
            )
        raise
