"""listing 명령의 ID 분기: ID 형식을 보고 주거·상가·단기임대·제휴 상세로 보낸다."""

import re

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.service.apt.detail import get_apt_listing
from jibsa.providers.zigbang.service.common.apt import apt_item_source
from jibsa.providers.zigbang.service.common.constants import APT_ID_PREFIXES
from jibsa.providers.zigbang.service.common.models import ZigbangListingDetail
from jibsa.providers.zigbang.service.room.detail import get_listing as get_room_listing
from jibsa.providers.zigbang.service.stay.detail import get_stay_listing
from jibsa.providers.zigbang.service.stay.models import ZigbangStayListingDetail
from jibsa.providers.zigbang.service.store.models import ZigbangStoreListingDetail
from jibsa.providers.zigbang.service.store.store import get_store_listing


# 접두어: 상가·단기임대와, 아파트 매물 ID 가 출처 앞에 붙이는 것 (coalition)
LISTING_ID_PATTERN: re.Pattern[str] = re.compile(
    rf"^(?:({'|'.join(('store', 'stay', *APT_ID_PREFIXES))})-)?([1-9]\d*)$"
)


def get_listing(client: ZigbangClient, item_id: int) -> ZigbangListingDetail:
    """숫자 ID 매물 상세를 조회한다 (라이브러리 입구 `jibsa.providers.zigbang.get_listing`).

    원룸·빌라·오피스텔은 주거 상세(`room.detail`)로 만들고, 주거 상세가 아파트 매물이라고 알리면(본문 code 의 404)
    웹 아파트 매물 화면처럼 아파트 상세(`apt`) 1회로 만든다. 기능 모듈끼리는 서로 부르지 않아 분기 모듈인 여기서 잇는다.

    Raises:
        ListingUnavailableError: 거래할 수 없는 매물일 때.
    """
    detail = get_room_listing(client, item_id)
    return detail if detail is not None else get_apt_listing(client, item_id)


def get_any_listing(
    client: ZigbangClient,
    listing_id: str,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
) -> ZigbangListingDetail | ZigbangStoreListingDetail | ZigbangStayListingDetail:
    """검색 결과의 `id` 그대로 상세를 조회한다.

    숫자만이면 원룸·오피스텔·빌라(`get_listing`: 새 상세 API, 입주일이 비면 `/v3/items` 로 보완)나 아파트(새 상세가
    아파트 매물이라고 알리는 404 를 주면 아파트 상세 `/apt/item-catalogs/items` 하나로),
    `store-` 는 상가, `stay-` 는 단기임대, `coalition-` 은 아파트 제휴(집주인이 내놓은 매물·신규분양) 매물이다.
    매물 번호 체계가 서로 달라 같은 숫자가 다른 매물일 수 있어 접두어로 구분한다.
    입주·퇴거일(`check_in`·`check_out`)은 단기임대만 받는다. `listing` 명령은 ID 형식을 따로 검사하지 않고 이 에러를
    그대로 낸다.

    Raises:
        JibsaError: ID 형식이 맞지 않거나, 단기임대가 아닌데 입주·퇴거일을 줬을 때 (INVALID_ARGUMENT).
        ValidationError: 단기임대 입주·퇴거일 형식·순서가 틀렸을 때 (요청 모델 검증이라 CLI 는 INVALID_ARGUMENT).
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
    if kind != 'stay' and (check_in or check_out):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='입주·퇴거일은 직방 단기임대(stay-…) 상세에만 쓸 수 있습니다',
            hint='--check-in/--check-out 을 빼고 다시 조회하세요',
        )
    if kind == 'store':
        return get_store_listing(client, int(number))
    if kind == 'stay':
        return get_stay_listing(client, int(number), check_in=check_in, check_out=check_out)
    # 접두어가 곧 출처 이름이다 (coalition-123). store·stay 는 앞에서 갈렸고 숫자만이면 kind 가 None 이다
    if (apt_source := apt_item_source(kind)) is not None:
        return get_apt_listing(client, int(number), apt_source)
    try:
        return get_listing(client, int(number))
    except ListingUnavailableError as exc:
        # 접두어를 뗀 상가·단기임대·제휴 번호(store-961398 → 961398)는 주거 상세에서 404 로 끝나 상태값도 사유도 없다.
        # close 처럼 상태가 있거나 UNKNOWN_TRADE_TYPE·APT_ITEM_NOT_FOUND(아파트 매물로 확인된 뒤 아파트 상세가 404) 처럼
        # 사유가 있으면 매물을 찾은 것이라 접두어 안내를 붙이지 않는다.
        if exc.details.get('listing_status') is None and exc.details.get('reason') is None:
            exc.hint = (
                f'{exc.hint}. 상가·단기임대·아파트 제휴 매물이면 결과의 id 그대로 '
                "'store-…'·'stay-…'·'coalition-…' 접두어를 붙였는지 확인하세요"
            )
        raise
