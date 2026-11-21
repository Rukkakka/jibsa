"""직방 service 공통(아파트 목록·묶음): 매물 ID·URL, 묶음 ID, 아파트 매물 모델, 카탈로그 → 매물 변환, 쪽 넘김 안내."""

import re

from pydantic import Field

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    NEXT_HINT,
    Listing,
    TradeType,
    join_address,
    m2_to_pyeong,
    more_hint,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.request.common import (
    ZigbangAptItemSource,
    ZigbangAptTranType,
)
from jibsa.providers.zigbang.api.response.common import ZigbangItemCatalogModel
from jibsa.providers.zigbang.service.common.base import (
    APT_LISTING_KIND_DESCRIPTION,
    APT_PYEONG_ID_DESCRIPTION,
    APT_PYEONG_NAME_DESCRIPTION,
    MAX_LIST_LIMIT,
    apt_complex_id,
    text_or_none,
)

from typing import (
    Annotated,
    get_args,
)


def apt_item_url(item_id: int, item_source: ZigbangAptItemSource) -> str:
    # 웹 아파트 매물 페이지(v2). 옛 경로 /home/apt/item/{id} 는 /error 로 보낸다.
    # 마지막 칸은 대표로 띄울 중개사 번호인데 빠지면 404 라, 0 을 넣어 직방이 고르게 한다.
    return f'https://www.zigbang.com/home/apt/item/v2/{item_id}/{item_source}/0'


def apt_catalog_url(area_ho_id: int, tran_type: str) -> str:
    # 같은 호를 여러 중개사가 올린 묶음 화면. 웹 아파트 카드를 누르면 가격 범위(isPriceRange)와 상관없이 가는 곳이다
    # (2026-11-15 번들 ItemCard_AptItemCatalogCard 의 onPress). 신규분양 카드는 누르면 그 매물 상세 화면으로 가지만
    # (`onPressOfferItem` → `HomeAptItemDetail`), 이 묶음 화면도 그 매물 1건과 '일반 매매가 아닌 신규분양 매물입니다' 를 보여 준다
    return f'https://www.zigbang.com/home/apt/item-catalog?areaHoId={area_ho_id}&tranType={tran_type}'


# 아파트 거래 유형 코드. 요청은 영어 코드(`ZigbangAptTranType`)를 받는다
APT_TRAN_TYPE_BY_TRADE: dict[TradeType, ZigbangAptTranType] = {
    '매매': 'trade',
    '전세': 'charter',
    '월세': 'rental',
}
# 응답의 거래 유형 코드 → 거래 유형 (응답 코드는 글자라 모르는 코드도 올 수 있다)
TRADE_BY_APT_TRAN_TYPE: dict[str, TradeType] = {
    tran_type: trade for trade, tran_type in APT_TRAN_TYPE_BY_TRADE.items()
}
# 같은 호·거래 유형의 아파트 매물 묶음 ID (`<호 ID>-<거래 유형 코드>`, 예: 8260358-trade). 묶음 화면 API 가 이 둘을 받는다
CATALOG_ID_PATTERN: re.Pattern[str] = re.compile(rf"^([1-9]\d*)-({'|'.join(TRADE_BY_APT_TRAN_TYPE)})$")
# 묶음 ID 형식이 틀렸을 때 안내 (`parse_catalog_id` 의 INVALID_ARGUMENT hint)
CATALOG_ID_HINT: str = 'search listings apt·search listings --complex <apt-…> 결과의 catalog_id 를 그대로 주세요 (예: 8260358-trade)'


def apt_catalog_id(area_ho_id: int, tran_type: str) -> str:
    """아파트 목록 줄의 `catalog_id` (`zigbang catalog` 에 넘긴다). 읽는 쪽은 `parse_catalog_id` 다."""
    return f'{area_ho_id}-{tran_type}'


def parse_catalog_id(catalog_id: str) -> tuple[int, ZigbangAptTranType]:
    """`catalog_id` 를 (호 ID, 거래 유형 코드) 로 나눈다. 거래 유형(한글)은 `TRADE_BY_APT_TRAN_TYPE` 으로 꺼낸다.

    `zigbang catalog` 명령은 형식을 따로 검사하지 않고 이 에러를 그대로 낸다.

    Raises:
        JibsaError: 형식이 맞지 않을 때 (INVALID_ARGUMENT).
    """
    match = CATALOG_ID_PATTERN.match(catalog_id.strip())
    if match is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 아파트 묶음 ID 형식이 아닙니다: '{catalog_id}'",
            hint=CATALOG_ID_HINT,
        )
    # 정규식이 이 표의 코드만 받으므로 늘 찾는다. 글자를 표의 값으로 바꿔 거래 유형 코드 타입으로 돌려준다
    tran_type = next(code for code in APT_TRAN_TYPE_BY_TRADE.values() if code == match.group(2))
    return int(match.group(1)), tran_type


# 상세를 볼 수 있는 아파트 매물 출처
APT_ITEM_SOURCES: tuple[ZigbangAptItemSource, ...] = get_args(ZigbangAptItemSource)


# 아파트 카드·상세의 매물 종류 코드(`itemType`) → 웹 카드가 보여 주는 말. 신규분양은 가격이 분양가다. 필드 설명
# (`APT_LISTING_KIND_DESCRIPTION`)은 상세 결과 모델(`common.base` 의 `ZigbangListingDetail`)도 써 `common.base` 에 있다
APT_LISTING_KIND_LABELS: dict[str, str] = {'offer': '신규분양', 'partner': '집주인', 'self_ad': '중개사'}


def apt_listing_kind(item_type: str | None) -> str | None:
    """아파트 매물 종류 코드를 말로 바꾼다. 코드가 없으면 모름(None), 모르는 코드는 직방 코드 그대로 둔다."""
    return None if item_type is None else APT_LISTING_KIND_LABELS.get(item_type, item_type)


class ZigbangAptListing(Listing):
    """직방 아파트 매물. 같은 호·거래 유형의 매물(중개사별)을 하나로 묶은 카탈로그 한 건이다."""

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (예: apt-68579). zigbang complex·items 에 넘긴다')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). --supply-area 조건은 이 값에 걸린다')
    ] = None
    is_price_range: Annotated[
        bool | None,
        Field(description='true 면 같은 호를 올린 매물끼리 가격이 달라 가격은 묶음의 최저가라 id 매물의 가격과 다를 수 있다. 매물별 가격은 catalog_id 를 zigbang catalog 에 넘겨 한 번에 본다')
    ] = None
    catalog_id: Annotated[
        str | None,
        Field(description='같은 호·거래 유형의 매물 묶음 ID (예: 8260358-trade). zigbang catalog 에 넘기면 묶음 매물 전부를 매물마다의 가격·상세와 함께 준다. 직방이 호 ID 를 주지 않으면 모름(null)이고, 그때 url 은 id 매물 페이지이며 묶음은 catalog 로 볼 수 없어 listing_ids 를 listing 으로 하나씩 본다')
    ] = None
    listing_ids: Annotated[
        list[str],
        Field(description='같은 호를 올린 매물 중 상세를 볼 수 있는 ID 전부 (id 포함, id 가 맨 앞). zigbang listing 에 넘긴다')
    ] = []
    listing_count: Annotated[
        int | None,
        Field(description='같은 호를 올린 매물(중개사) 수')
    ] = None
    listing_kind: Annotated[
        str | None,
        Field(description=APT_LISTING_KIND_DESCRIPTION)
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description=APT_PYEONG_ID_DESCRIPTION)
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description=APT_PYEONG_NAME_DESCRIPTION)
    ] = None


# 아파트 매물 ID 앞에 출처를 붙이는 출처 (`apt_listing_id`). 직방 매물은 접두어 없이 숫자만이다
APT_ID_PREFIXES: tuple[ZigbangAptItemSource, ...] = tuple(source for source in APT_ITEM_SOURCES if source != 'zigbang')


def apt_listing_id(item_id: int, item_source: ZigbangAptItemSource) -> str:
    """아파트 매물의 jibsa ID (목록 `id`·`listing_ids` 와 상세 `id`). 직방 매물은 숫자 그대로, 제휴 매물은 `coalition-<id>`.

    접두어를 다시 출처로 읽는 쪽은 `apt_item_source` 다 (접두어가 곧 출처 이름이다).
    """
    return f'{item_source}-{item_id}' if item_source in APT_ID_PREFIXES else str(item_id)


def apt_item_source(name: str | None) -> ZigbangAptItemSource | None:
    """출처 이름(응답의 매물 출처, 또는 ID 접두어) → 상세를 볼 수 있는 아파트 매물 출처. 그 밖의 출처(상세를 볼 수 없음)면 None."""
    return next((source for source in APT_ITEM_SOURCES if source == name), None)


def catalog_to_listing(catalog: ZigbangItemCatalogModel, local1: str | None) -> ZigbangAptListing | None:
    """카탈로그 한 건을 `ZigbangAptListing` 으로 바꾼다. 상세를 볼 수 있는 매물 ID 가 없으면 None.

    `depositMin` 은 매매면 매매가, 전세·월세면 보증금이다. 묶인 매물 중 상세를 볼 수 있는 것(직방 매물, 제휴
    매물 = 집주인이 내놓은 매물이나 신규분양, 제휴는 `coalition-123` ID)을 직방 응답(`itemIdList`) 순서 그대로
    `listing_ids` 에 담고 `id` 는 그 맨 앞이다. 둘 다 `zigbang listing` 으로 상세를 볼 수 있다. 그 밖의 출처는 상세를
    볼 수 없어 뺀다. 출처로 다시 정렬하지 않는 까닭은 묶음의 `itemType`·`itemTitle`·`floor` 가 모두 `itemIdList` 맨 앞
    매물의 값이라, 응답 순서를 지켜야 `id` 가 그 값들과 같은 매물을 가리키기 때문이다 (2026-11-17 실측: 서패동(41480119)
    묶음 `itemIdList: [coalition 254486, zigbang 50026248]` 에 `itemType: partner`·숫자 층·제목이 모두 제휴 매물 것이었다).
    응답 맨 앞이 상세를 볼 수 없는 출처라 `id` 가 맨 앞 매물이 아니면 묶음 `itemType` 은 `id` 매물의 종류가 아니므로
    `listing_kind` 는 null(모름)이다. `itemIdList` 에 빈 항목(null)이 와서 뺐을 때도 같다 (빈 항목이 맨 앞이었는지 알 수 없다,
    `catalog_null_notes` 가 안내한다).

    `isPriceRange` 가 true 면 가격은 묶음의 최저가라 `id` 매물의 가격과 다를 수 있다 (웹 카드는 '최저가 ~').
    웹 카드는 가격 범위와 상관없이 누르면 그 호의 묶음 화면으로 가므로(2026-11-15 번들 ItemCard_AptItemCatalogCard 의
    onPress) `url` 도 호 ID 가 있으면 늘 그 화면이다. 웹 신규분양 카드는 누르면 그 매물의 상세 화면으로 가지만
    (`onPressOfferItem` → `HomeAptItemDetail`), 분양 줄의 묶음 화면 주소도 그 매물 1건과 '일반 매매가 아닌 신규분양
    매물입니다' 를 보여 줘 사실이 어긋나지 않는다. 호 ID 가 없으면 묶음 화면을 만들 수 없어 `id` 매물의 웹 페이지다.
    묶음 화면이 받는 호 ID·거래 유형은 `catalog_id` 로 낸다.

    지역 목록(`/apt/locals/{코드}/item-catalogs`)에는 신규분양 카드가 일반 매물과 같은 목록에 섞여 온다. 서버는
    `includeOfferItem` 이 없으면 `true` 와 똑같이 분양을 넣어 주고(웹 기본 화면의 '신규 분양 포함' 켠 상태와 같다),
    분양 카드도 `count`·`offset` 에 든다 (2026-11-17 실측: 파주시 41480 은 값 없음·true 608건, false 600건). 분양 카드는
    `itemType: offer` 에 출처가 `coalition` 이라 일반 제휴 매물처럼 `coalition-` 줄이 되고 `listing_kind` 가 '신규분양'
    이다 (가격은 분양가). `offerItemCount` 는 단지 요약(`/apt/danjis/{id}/item-catalogs/summary`)의 파라미터라 이 목록과
    상관없다.
    """
    entries = [
        (entry.item_id, source)
        for entry in catalog.item_id_list if (source := apt_item_source(entry.item_source)) is not None
    ]
    trade_type = TRADE_BY_APT_TRAN_TYPE.get(catalog.tran_type)
    if not entries or trade_type is None:
        return None
    item_id, item_source = entries[0]
    listing_ids = [apt_listing_id(*entry) for entry in entries]
    # 묶음 종류는 응답 맨 앞 매물의 값이라, 그 매물이 id 가 아니면(상세를 볼 수 없는 출처) id 매물의 종류를 모른다.
    # 빈 항목을 빼고 읽었으면 지금 맨 앞이 응답 맨 앞인지 알 수 없어 마찬가지로 모른다
    leads_bundle = apt_item_source(catalog.item_id_list[0].item_source) is not None and not catalog.null_items('item_id_list')
    is_sale = trade_type == '매매'
    return ZigbangAptListing(
        source='zigbang',
        id=listing_ids[0],
        url=(
            apt_catalog_url(catalog.area_ho_id, catalog.tran_type)
            if catalog.area_ho_id is not None
            else apt_item_url(item_id, item_source)
        ),
        trade_type=trade_type,
        property_type='아파트',
        title=catalog.item_title or join_address(catalog.area_danji_name, catalog.dong),
        price_manwon=catalog.deposit_min if is_sale else None,
        deposit_manwon=None if is_sale else catalog.deposit_min,
        rent_manwon=catalog.rent_min if trade_type == '월세' else None,
        area_m2=catalog.size_m2,
        area_pyeong=m2_to_pyeong(catalog.size_m2),
        floor=catalog.floor,
        address=join_address(local1, catalog.local2, catalog.local3),
        complex_id=apt_complex_id(catalog.area_danji_id) if catalog.area_danji_id else None,
        complex_name=join_address(catalog.area_danji_name, catalog.dong),
        supply_area_m2=catalog.size_contract_m2,
        is_price_range=catalog.is_price_range,
        catalog_id=apt_catalog_id(catalog.area_ho_id, catalog.tran_type) if catalog.area_ho_id is not None else None,
        listing_ids=listing_ids,
        listing_count=catalog.item_count,
        listing_kind=apt_listing_kind(catalog.item_type) if leads_bundle else None,
        pyeong_id=catalog.danji_room_type_id,
        pyeong_name=text_or_none(catalog.room_type_title.p) if catalog.room_type_title else None,
    )


def catalog_null_notes(what: str, dropped_catalogs: int, dropped_id_lists: int) -> list[str]:
    """아파트 매물 카탈로그 목록(`list`)과 카탈로그의 묶인 매물 ID 목록(`itemIdList`)에서 빈 항목(null)을 빼고 읽었을 때의 안내.

    목록에서 뺀 빈 항목(`dropped_catalogs`)은 받은 자리 수(offset·inspected)에 더해 셌다는 안내이고, 묶인 매물 ID 목록에서 뺀 빈
    항목(`dropped_id_lists`)은 그 묶음의 맨 앞 매물을 알 수 없어 `listing_kind` 를 모름(null)으로 뒀다는 안내다. 둘 다 없으면 빈 목록이다.

    Args:
        what: 사이트 이름을 붙인 목록 이름 (예: '직방 지역 아파트'). 뒤에 ' 매물'·' 묶음의 매물 ID' 가 붙는다.
        dropped_catalogs: 카탈로그 목록에서 뺀 빈 항목 수 (받은 쪽 전부의 합).
        dropped_id_lists: 카탈로그의 묶인 매물 ID 목록에서 뺀 빈 항목 수 (받은 카탈로그 전부의 합).
    """
    notes: list[str] = []
    if dropped_catalogs:
        notes.append(null_items_note(f'{what} 매물', dropped_catalogs))
    if dropped_id_lists:
        notes.append(null_items_note(f'{what} 묶음의 매물 ID', dropped_id_lists, ('listing_kind',)))
    return notes


def apt_pagination_notes(
    returned: int,
    limit: int,
    inspected: int,
    *,
    has_more: bool = False,
    suggest_limit: bool = True,
    resumable: bool = False,
    resumed: bool = False,
    narrow: str,
) -> list[str]:
    """실제로 받은 원본 매물 수를 조회 예산으로 세고 추가 조회 없이 안내한다.

    `has_more` 는 같은 조건으로 더 받을 매물이 남았다는 뜻이다 (결과의 `has_more`). 그러면 '이 N건이 전부' 라고 하지
    않는다 (2026-10-17 리뷰: 반경 안 단지 204곳 중 30곳만 훑은 결과에 '전부입니다' 와 '30곳만 조회' 가 함께 나갔다).
    더 있다는 안내도 이 값으로만 정한다. 서버 수(total)는 받은 뒤 뺀 매물까지 세어 돌려준 수와 견주면, 다 받고 일부를
    뺐을 뿐인데도 '더 있다' 고 했다 (2026-10-23 리뷰: 단지 매물 3건 중 1건을 뺀 --limit 3 에 has_more false 와 '[일부]').
    `suggest_limit` 이 False 면 --limit 을 늘리라는 안내를 뺀다. 늘려도 못 찾는 경우(반경 면적 검색의 단지 상한)에 쓴다.
    당근 `listing_budget_notes`·네이버의 같은 역할 함수와 문구는 비슷하지만 공통 헬퍼로 합치지 않는다. 제외 수를 세는
    방식(직방 받은 수 − 반환 수, 네이버 min(받은 수, limit) − 반환 수, 당근 eligible)과 더 받을 매물 판단(당근 has_more,
    네이버 truncated)이 소스마다 달라 합치면 그 옵션을 모두 받는 함수가 된다.
    `resumable` 이면 결과의 `next` 로 이어 받으라고 권하고, `resumed`(이어 받은 결과)면 '전부' 대신 '남은 매물' 이라 한다.
    `narrow` 는 더 남았을 때 좁히라고 권할 것이다 (`more_hint`). 동·구 검색은 '조건·지역', 반경 검색은 '조건·반경', 단지
    하나의 매물은 좁힐 지역이 없어 그 단지 매물의 조건만 준다 (2026-11-10 리뷰·실측: 헬리오시티 apt-38487 434건 --limit 120
    에 '조건·지역을 좁히세요'). 빠뜨리면 틀린 말이 나가므로 기본값을 두지 않는다 (네이버 `pagination_notes` 와 같다).
    """
    notes: list[str] = []
    if returned < limit:
        if inspected > returned:
            notes.append(note(
                '제외',
                f'{inspected}건을 받아 중복·거래 불가·조건 불일치를 빼고 {returned}건입니다 '
                + ('(뺀 만큼 다시 채우지 않음)' if has_more else '(더 받을 매물 없음)'),
            ))
        elif not has_more:
            # 0건이면 '이 0건이 전부입니다' 대신 없다고 한다 (2026-11-11 LLM 사용 시험: 네이버·당근·직방이 같은 꼴로 냈다)
            what = '남은' if resumed else '조건에 맞는'
            notes.append(f'{what} 매물은 이 {returned}건이 전부입니다' if returned else f'{what} 매물이 없습니다')
    if resumable:
        notes.append(note('일부', f'매물이 더 있습니다. {NEXT_HINT}'))
    elif limit >= MAX_LIST_LIMIT and has_more:
        notes.append(note('일부', more_hint(limit, MAX_LIST_LIMIT, narrow)))
    elif suggest_limit and inspected >= limit and has_more:
        notes.append(note('일부', f'매물이 더 있습니다. {more_hint(limit, MAX_LIST_LIMIT, narrow)}'))
    return notes
