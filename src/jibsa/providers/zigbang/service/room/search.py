"""원룸·빌라·오피스텔 매물 검색과 검색 결과에 건물 용도 붙이기 (search listings room, --details)."""

from collections.abc import (
    Iterator,
    Sequence,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    Listing,
    LookupFailures,
    limit_notes,
    listing_as,
    lookup_failure_note,
    lookup_failure_reason,
    normalize_date,
    note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import ZigbangSalesType
from jibsa.providers.zigbang.api.request.room.base import (
    ZigbangItemsDetailV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.request.room.search import (
    ZigbangItemsOfficetelsV1RequestParameterModel,
    ZigbangItemsOneroomsV1RequestParameterModel,
    ZigbangItemsSubwaysOfficetelsV1RequestParameterModel,
    ZigbangItemsSubwaysOneroomsV1RequestParameterModel,
    ZigbangItemsSubwaysVillasV1RequestParameterModel,
    ZigbangItemsVillasV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangItemPinModel
from jibsa.providers.zigbang.api.response.room.search import ZigbangItemsResponseModel
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    ZigbangBoundary,
    ZigbangListing,
    ZigbangRegion,
    drop_unused_scope,
    officetel_complex_id,
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.common.room import (
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    ZigbangRoomConditions,
    excluded_notes,
    pin_null_notes,
    room_filter_of,
    section_ordered_ids,
    summary_to_listing,
    tradeable_summaries,
)
from jibsa.providers.zigbang.service.region import (
    outside_boundary,
    scope_geohashes,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


ZigbangPropertyType = Literal['원룸', '오피스텔', '빌라']

PROPERTY_TYPES: tuple[ZigbangPropertyType, ...] = ('원룸', '오피스텔', '빌라')
GEOHASH_PRECISION: int = 5
# 방 하나짜리 구조. 원룸 유형은 이 구조만 서버에 요청한다 (직방 원룸 목록에는 투룸 오피스텔도 섞여 온다)
# 방 하나짜리 아파트는 아파트 목록에만 있고 아파트 API 에는 방 구조 조건이 없다. 공급면적 50㎡ 이하로 찾으면
# 대부분 방 1개다 (2026-10-10 실측: 역삼동 32건 중 단지별 6건 상세에서 5건이 방 1개)
ONE_ROOM_STRUCTURES: tuple[str, ...] = ('오픈형원룸', '분리형원룸', '복층형원룸')
# --details 로 상세를 붙이는 매물 수. 한 건에 요청 1회라 목록이 길면 오래 걸린다
DETAILS_MAX: int = 30


class ZigbangSearchResult(BaseModel):
    """매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float | None,
        Field(description='검색 반경 (km). 동 경계로 찾았으면 키가 없다')
    ] = None
    boundary: Annotated[
        str | None,
        Field(description='반경 대신 경계 안을 찾은 동 이름. 반경으로 찾았으면 키가 없다')
    ] = None
    total: Annotated[
        int,
        Field(description=(
            '범위(반경·동 경계, 역은 서버가 준 역 반경) 안 서로 다른 매물 수 근사값 (limit 적용 전, 거래 불가를 빼기 전). '
            '종류 여럿에 함께 있는 매물은 한 번만 센다'
        ))
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위 안에 아직 받지 않은 매물이 남은 종류가 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 ({"offsets": {종류: 그 종류 직방 목록에서 다음에 받을 자리}}). 더 없으면 None')
    ] = None
    listings: Annotated[
        # 오피스텔의 complex_id 까지 내보낸다 (SerializeAsAny 가 없으면 공통 Listing 필드만 나간다)
        list[SerializeAsAny[Listing]],
        Field(description='직방 목록 순서의 매물. 종류 여럿이면 요청한 종류 순서로 종류별 묶음을 잇는다')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='매물이 limit 보다 많아 일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 반경과 동 경계 중 쓰지 않은 쪽은 해당 없다
        return drop_unused_scope(handler(self))


class ZigbangDetailedListing(ZigbangListing):
    """`--details` 로 매물 상세를 1회 더 받아 건물 용도를 붙인 원룸·오피스텔·빌라 매물."""

    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (예: 다가구, 다세대, 근린생활시설). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다. 모르면 null')
    ] = None


def unsearchable_types(property_types: Sequence[str], trade_types: Sequence[str]) -> list[str]:
    """거래 유형 조건 때문에 직방에서 조회할 수 없는 유형. 원룸은 매매가 없다 (전세·월세·단기임대만).

    `search_listings` 는 이런 유형을 요청 없이 건너뛰므로, 0건을 "매물이 없다"로 오해하지
    않도록 호출한 쪽이 `unsearchable_note` 로 알린다.
    """
    if '원룸' in property_types and trade_types and all(trade == '매매' for trade in trade_types):
        return ['원룸']
    return []


def unsearchable_note(types: list[str]) -> str:
    return note(
        '거래',
        f"직방은 {'·'.join(types)} 매매를 다루지 않아 조회하지 않았습니다 (전세·월세·단기임대만). "
        '매매는 빌라·오피스텔이나 다른 소스에서 찾으세요',
    )


def _scope_pins(
    client: ZigbangClient,
    property_type: ZigbangPropertyType,
    *,
    geohashes: list[str],
    subway_id: int | None,
    radius_km: float,
    sales_types: list[ZigbangSalesType],
    type_filters: dict[str, object],
) -> Iterator[tuple[str | None, ZigbangItemsResponseModel]]:
    """검색 범위의 핀을 (지도 칸, 응답) 으로 하나씩 받는다. 역 검색이면 역 API 를 한 번 부르고 칸은 None 이다."""
    # 유형별 분기를 (요청 모델, 메서드) 표로 묶지 않는다. 표로 두면 타입 검사가 요청 모델과 메서드 짝을 확인하지 못한다
    response: ZigbangItemsResponseModel
    if subway_id is not None:
        if property_type == '원룸':
            response = client.run_request_items_subways_onerooms_v1(ZigbangItemsSubwaysOneroomsV1RequestParameterModel(
                subway_id=subway_id, radius=radius_km, sales_types=sales_types, **type_filters,
            ))
        elif property_type == '오피스텔':
            response = client.run_request_items_subways_officetels_v1(ZigbangItemsSubwaysOfficetelsV1RequestParameterModel(
                subway_id=subway_id, radius=radius_km, sales_types=sales_types, **type_filters,
            ))
        else:
            response = client.run_request_items_subways_villas_v1(ZigbangItemsSubwaysVillasV1RequestParameterModel(
                subway_id=subway_id, radius=radius_km, sales_types=sales_types, **type_filters,
            ))
        yield None, response
        return
    for geohash in geohashes:
        if property_type == '원룸':
            response = client.run_request_items_onerooms_v1(ZigbangItemsOneroomsV1RequestParameterModel(
                geohash=geohash, sales_types=sales_types, **type_filters,
            ))
        elif property_type == '오피스텔':
            response = client.run_request_items_officetels_v1(ZigbangItemsOfficetelsV1RequestParameterModel(
                geohash=geohash, sales_types=sales_types, **type_filters,
            ))
        else:
            response = client.run_request_items_villas_v1(ZigbangItemsVillasV1RequestParameterModel(
                geohash=geohash, sales_types=sales_types, **type_filters,
            ))
        yield geohash, response


# 유형 하나의 (거래 유형 필터, 요청 필드)
_TypeQuery = tuple[list[ZigbangSalesType], dict[str, object]]


class _ScopePins(NamedTuple):
    """`_collect_pins` 결과: 종류마다 범위 안 매물 ID(직방 목록 순서), 매물별 중심 거리·건물 ID, 원룸 조회 조건과 지도 칸."""

    ids_by_type: dict[ZigbangPropertyType, list[int]]
    distances: dict[int, float]
    # 오피스텔 핀의 건물 ID. 원룸 목록에 섞여 온 같은 매물의 핀에는 없어 종류와 상관없이 매물 ID 로 찾는다
    buildings: dict[int, int]
    # 원룸 목록에 섞여 온 오피스텔의 건물 ID 를 같은 조건의 오피스텔 목록으로 채울 때 쓴다
    oneroom_query: _TypeQuery | None
    # 원룸 핀을 받은 지도 칸. 건물 ID 가 빠진 매물이 있던 칸만 오피스텔 목록을 다시 받는다
    oneroom_cells: dict[int, str]
    # 앞 종류 목록에도 있어 그 종류 목록에서 뺀 매물 수 (원룸 목록의 '이 지역 오피스텔' 은 오피스텔 목록에도 있다)
    overlaps: dict[ZigbangPropertyType, int]
    # 핀·섹션 목록에서 빈 항목(null)을 빼고 읽었다는 안내 (없으면 빈 목록)
    null_notes: list[str]


def search_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangRoomConditions | None = None,
    property_types: list[ZigbangPropertyType] | None = None,
    radius_km: float = 1.0,
    limit: int = 20,
    boundary: ZigbangBoundary | None = None,
    subway_id: int | None = None,
    start: dict[str, Any] | None = None,
) -> ZigbangSearchResult:
    """원룸·빌라·오피스텔 매물을 직방 웹 목록 순서로 `limit` 건 조회한다.

    종류마다 검색 범위의 지도 칸(역이면 역 반경 API)에서 핀(`items`)과 섹션(`sections`)을 받아, 웹 목록처럼 응답의 섹션
    순서(VIP → 안심추천 → 안심일반 → 추천 → 일반)대로 잇는다 (2026-11-15 번들 `_app` 의 `loadSectionsWithItemIdsByGeoHash`·
    `createSectionsToUpdate`). 섹션 안은 서버가 준 순서 그대로 둔다. 웹은 VIP 밖 섹션 안을 화면에서 무작위로 섞지만, 서버
    순서는 같은 요청에 늘 같아 (2026-11-15 실측) 이어 받기 자리가 흔들리지 않는다. 지도 칸이 여럿이면 섹션 종류마다 칸 순서
    (`scope_geohashes`)대로 잇고, 어느 섹션에도 없는 핀은 잃지 않게 맨 뒤에 핀 순서로 붙인다. 거리로 다시 세우지 않고
    `distance_km` 는 매물마다 덧붙이기만 한다. 고른 매물의 요약을 15개씩 받아 고른 순서대로 `Listing` 으로 바꾼다.
    가격·관리비(만원), 방 구조, 면적(㎡·평), 층, 욕실 수, 옵션, 기타 조건(`CONDITION_FIELD_BY_LABEL`)은 서버에서 거른다.
    요약을 받은 뒤 거래 불가·지원하지 않는 거래 종류로 뺀 매물은 다시 채우지 않고 `notes` 로 알린다.

    범위는 핀 좌표로 좁힌다. `boundary` 를 주면 반경 대신 그 동 경계 안 핀만 남기고(경계를 덮는 지도 칸을 받는다), 좌표·구·
    시·`--radius` 는 검색 중심에서 `radius_km` 안 핀만 반올림 없이 남긴다. 반경 안이 모자라도 반경 밖 핀으로 채우지 않는다
    (웹 지도 목록은 화면 사각형이라 반경이 없고, 반경 밖을 덧붙이는 화면도 없다). `subway_id` 를 명시하면 지도 칸 대신 역 반경
    API 를 종류별 1회 부르고, 서버가 반경으로 준 결과를 다시 자르지 않는다.

    종류가 여럿이면(기본은 세 종류) 웹처럼 종류마다 목록이 따로라, `limit` 을 조회할 종류 수로 고르게 나눠(20 → 7·7·6, 앞
    종류부터 한 건씩 더) 종류별 묶음을 요청한 종류 순서대로 잇는다. 한 종류의 남은 매물이 제 몫보다 적으면 남는 몫을 다른
    종류에 돌린다. 원룸 목록의 '이 지역 오피스텔' 섹션 매물은 오피스텔 목록에도 있어, 앞 종류 목록에 있는 매물은 뒤 종류
    목록에서 빼고 세며 몇 건인지 `notes` 로 알린다. 받기 전에 빼서 `--next` 로 이어 받아도 다시 나오지 않고, 이어 받기 자리·
    `total`·`[일부]` 가 모두 서로 다른 매물 수로 맞는다 (2026-11-16 리뷰: 한 호출 안에서만 빼자 강남역 이어 받기에서 앞 쪽
    매물이 16~59건씩 다시 나왔고, 자리를 종류별로 더한 수가 `total` 을 넘어 더 있는데도 `[일부]` 가 사라졌다).

    원룸은 건물 종류가 아니라 방 하나짜리를 뜻한다. 직방 원룸 목록은 오피스텔(투룸 포함)을 함께 주므로
    원룸형 구조(`ONE_ROOM_STRUCTURES`)만 서버에 요청하고, 섞여 온 원룸형 오피스텔은 결과에 넣는다.
    원룸 목록 핀에는 건물 ID 가 없어, 오피스텔을 따로 조회하지 않았으면 같은 범위·조건의 오피스텔
    목록을 한 번 더 받아 `complex_id` 를 채운다 (결과에 건물 ID 없는 오피스텔이 있을 때만).

    오피스텔 요청에는 늘 서버의 무작위 섞기 해제(`withoutRandom`)를 보낸다. 직방은 오피스텔 섹션 안 순서만 무작위로 섞어 주고
    시간이 지나면 다시 섞어, 그대로 받으면 이어 받기(`--next`)의 자리가 흔들려 매물이 겹치거나 빠진다. 섞지 않은 순서는 원룸·
    빌라처럼 매물 번호순이라 시간이 지나도 같다 (2026-11-15~16 실측: wydm6 오피스텔 안심추천 168건·안심일반 363건이 섞는
    요청과 같은 매물이고, 하루 뒤에도 남은 매물의 순서가 같았다). 맨 위 VIP 섹션(광고, 다른 섹션 매물 중 32건)만은 직방이
    요청마다·시간마다 바꿔 준다.

    `start` 는 이어 받기(`--next`) 표의 위치다 (`{'offsets': {종류: 그 종류 목록에서 다음에 받을 자리}}`). 핀은 다시 받아
    같은 순서로 세운 뒤 종류마다 그 자리부터 요약을 받는다. 핀 요청은 지도 칸 수만큼이라 적고, 요약은 15개에 1회라 앞서 받은
    매물의 요약을 다시 받지 않는다.

    직방 카테고리별 방 구조: 원룸 = 오픈형·분리형·복층형 원룸 (원룸형 오피스텔 포함), 빌라 = 투룸·
    쓰리룸·포룸이상 (원룸형 구조만 주면 빌라는 조회하지 않는다), 오피스텔 = 원룸형·투룸·쓰리룸 이상.

    거래 유형도 서버에서 거른다. 직방의 '월세' 필터는 단기임대를 빼고, 단기임대는 '단기' 로
    따로 받는다 (`SALES_TYPE_BY_TRADE`). 거래 유형을 주지 않으면 단기임대도 함께 나온다.

    Raises:
        JibsaError: 역 반경과 동 경계를 함께 줬거나, 이어 받기 표의 종류가 이번 검색과 다르거나 모양이 틀릴 때
            (INVALID_ARGUMENT).
    """
    # 방어용. CLI 는 둘을 함께 넘기지만 역 검색 결과에는 법정동코드가 없어 역이면 boundary 가 늘 None 이다.
    if subway_id is not None and boundary is not None:
        raise JibsaError(
            code='INVALID_ARGUMENT', message='역 반경 검색과 동 경계를 함께 지정할 수 없습니다',
            hint='역 검색에는 동 경계 대신 반경을 사용하세요',
        )
    conditions = conditions or ZigbangRoomConditions()
    requested_types = property_types or []
    property_types = property_types or list(PROPERTY_TYPES)

    queries, notes = _type_queries(conditions, property_types, requested_types)
    types = list(queries)
    # 핀을 받기 전에 본다. 표가 틀리면 요청 없이 멈춘다
    # 이어 받기 표(`--next`)에서 종류마다 다음에 받을 자리를 꺼낸다. 표가 없으면 모두 0 이다. 예전 `{'offset': n}` 표도 아래 에러에 걸린다
    starts: dict[ZigbangPropertyType, int]
    if start is None:
        starts = {kind: 0 for kind in types}
    else:
        offsets = start.get('offsets')
        if not (
            isinstance(offsets, dict)
            and set(offsets) == set(types)
            and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in offsets.values())
        ):
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message='이어 받기 표(--next)의 위치가 이 검색의 매물 종류와 맞지 않아 이어 받을 수 없습니다',
                hint='--next 없이 같은 지역·조건으로 다시 검색하세요',
            )
        starts = {kind: offsets[kind] for kind in types}
    geohashes = [] if subway_id is not None else scope_geohashes(region, radius_km, boundary, GEOHASH_PRECISION)
    scan = _collect_pins(
        client, region, queries, geohashes=geohashes, subway_id=subway_id, radius_km=radius_km, boundary=boundary,
    )

    # 조회 예산은 요약을 받는 자리 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    remaining = [max(len(scan.ids_by_type[kind]) - starts[kind], 0) for kind in types]
    shares = dict(zip(types, _split_limit(limit, remaining)))
    # 종류별 목록은 서로 겹치지 않는다 (_collect_pins)
    ids = [
        item_id
        for kind in types
        for item_id in scan.ids_by_type[kind][starts[kind]:starts[kind] + shares[kind]]
    ]
    tradeable = tradeable_summaries(client, ids)
    summaries = {summary.item_id: summary for summary in tradeable.items}
    # 요약 응답 순서에 기대지 않고 고른 순서로 세운다. 원룸 목록에 섞여 온 원룸형 오피스텔도 그대로 둔다
    listings: list[Listing] = [
        summary_to_listing(summaries[item_id], scan.distances.get(item_id), scan.buildings.get(item_id))
        for item_id in ids
        if item_id in summaries
    ]
    if scan.oneroom_query is not None and '오피스텔' not in queries:
        notes += _fill_officetel_complex_ids(client, listings, scan, subway_id=subway_id, radius_km=radius_km)

    return _search_result(
        region, listings, scan, notes, starts=starts, shares=shares, limit=limit, radius_km=radius_km, boundary=boundary,
        summary_nulls=tradeable.null_items,
    )


def _type_queries(
    conditions: ZigbangRoomConditions,
    property_types: list[ZigbangPropertyType],
    requested_types: list[ZigbangPropertyType],
) -> tuple[dict[ZigbangPropertyType, _TypeQuery], list[str]]:
    """조회할 종류마다 (거래 유형 필터, 요청 필드) 를 요청한 종류 순서로, 조회하지 않는 종류의 안내와 함께 만든다."""
    # 방 구조는 유형마다 달라 아래 반복에서 넣는다
    filters: dict[str, object] = {
        'deposit_min': conditions.deposit_min,
        'deposit_max': conditions.deposit_max,
        'rent_min': conditions.rent_min,
        'rent_max': conditions.rent_max,
        'sales_price_min': conditions.price_min,
        'sales_price_max': conditions.price_max,
        **room_filter_of(conditions),
    }
    notes: list[str] = []
    queries: dict[ZigbangPropertyType, _TypeQuery] = {}
    # 조회할 게 없는 유형은 건너뛰고, 사용자가 직접 고른 유형(`requested_types`)이면 `notes` 에 알린다 (원룸에 매매만 준 것은
    # `unsearchable_note` 가 알린다)
    for property_type in property_types:
        all_sales_types = [SALES_TYPE_BY_TRADE[trade] for trade in conditions.trade_types]
        sales_types = all_sales_types
        type_rooms = list(conditions.room_types)
        if property_type == '빌라' and type_rooms and all(room in ONE_ROOM_STRUCTURES for room in type_rooms):
            # 직방 빌라 목록은 투룸 이상뿐이라 원룸형 구조만 주면 늘 0건이다 (2026-10-10 실측: 3개 동 빌라
            # 135건 모두 투룸 이상, 원룸형 조건 0건). 빌라 건물의 원룸은 직방이 원룸 목록에 둔다
            if '빌라' in requested_types:
                notes.append(note(
                    '범위',
                    '직방 빌라 목록은 투룸 이상만 있어 --room 의 원룸형 조건으로는 조회하지 않았습니다. '
                    '빌라(다세대·다가구) 건물의 원룸은 -t 원룸으로 찾으세요',
                ))
            continue
        if property_type == '원룸':
            sales_types = [sales_type for sales_type in all_sales_types if sales_type != '매매']
            if conditions.trade_types and not sales_types:
                # 원룸에 매매만 요청하면 해당 유형은 조회할 게 없다.
                continue
            # 원룸 목록은 투룸 오피스텔까지 섞어 주므로 방 하나짜리 구조만 요청한다
            type_rooms = [room for room in type_rooms or ONE_ROOM_STRUCTURES if room in ONE_ROOM_STRUCTURES]
            if not type_rooms:
                if '원룸' in requested_types:
                    notes.append(note('범위', '원룸은 방 하나짜리(오픈형·분리형·복층형)만 찾아 --room 의 투룸 이상 조건으로는 조회하지 않았습니다'))
                continue
        type_filters = {**filters, 'room_types': [ROOM_TYPE_FILTER_BY_LABEL[room] for room in type_rooms]}
        # 방 1개짜리 아파트는 여기서 찾지 않는다는 안내는 원룸을 찾을 때마다 나와 docs/llm.md 로 옮겼다
        if property_type == '오피스텔':
            # 섞지 않은 순서로 받아 이어 받기의 자리가 흔들리지 않게 한다 (search_listings docstring)
            type_filters['without_random'] = True
        queries[property_type] = (sales_types, type_filters)
    return queries, notes


def _split_limit(limit: int, remaining: list[int]) -> list[int]:
    """`limit` 을 종류마다 고르게 나눈다 (20 → 7·7·6, 앞 종류부터 한 건씩 더). `remaining` 은 종류마다 남은 자리 수다.

    남은 자리가 제 몫보다 적은 종류는 남은 만큼만 받고, 남는 몫은 아직 남은 종류에 같은 규칙으로 다시 나눈다.
    """
    shares = [0] * len(remaining)
    left = limit
    open_kinds = [index for index, count in enumerate(remaining) if count > 0]
    while left > 0 and open_kinds:
        base, extra = divmod(left, len(open_kinds))
        for rank, index in enumerate(open_kinds):
            take = min(base + (1 if rank < extra else 0), remaining[index] - shares[index])
            shares[index] += take
            left -= take
        open_kinds = [index for index in open_kinds if shares[index] < remaining[index]]
    return shares


def _collect_pins(
    client: ZigbangClient,
    region: ZigbangRegion,
    queries: dict[ZigbangPropertyType, _TypeQuery],
    *,
    geohashes: list[str],
    subway_id: int | None,
    radius_km: float,
    boundary: ZigbangBoundary | None,
) -> _ScopePins:
    """종류마다 검색 범위의 핀과 섹션을 받아 범위 안 매물 ID 를 웹 목록 순서로 세운다 (`section_ordered_ids`).

    섹션 종류마다 칸 순서대로 잇고, 어느 섹션에도 없는 핀은 맨 뒤에 칸·핀 순서로 붙인다. 같은 매물이 두 번 오면 앞의 것만 둔다.
    앞 종류 목록에 있는 매물은 뒤 종류 목록에서 빼 종류별 목록이 서로 겹치지 않게 한다 (`search_listings`).
    """
    scan = _ScopePins(
        ids_by_type={}, distances={}, buildings={}, oneroom_query=queries.get('원룸'), oneroom_cells={}, overlaps={},
        null_notes=[],
    )
    claimed: set[int] = set()

    def in_scope(pin: ZigbangItemPinModel | None) -> bool:
        if pin is None:
            # 섹션에 있는데 핀이 없는 매물 (실측으로는 두 ID 집합이 같다, 2026-11-15 wydm6 원룸 1187건). 역은 서버가 반경으로
            # 준 결과라 그대로 두고, 지도 칸은 좌표를 몰라 범위 안인지 볼 수 없어 뺀다
            return subway_id is not None
        if boundary is not None:
            return not outside_boundary(boundary, pin.lat, pin.lng)
        # 역은 서버가 반경으로 거른 결과라 다시 자르지 않는다. 좌표·구·시는 반올림 없이 반경 안만 둔다
        return subway_id is not None or scan.distances[pin.id] <= radius_km

    for property_type, (sales_types, type_filters) in queries.items():
        responses = list(_scope_pins(
            client, property_type, geohashes=geohashes, subway_id=subway_id, radius_km=radius_km,
            sales_types=sales_types, type_filters=type_filters,
        ))
        for geohash, response in responses:
            for pin in response.items:
                scan.distances[pin.id] = haversine_km(region.lat, region.lng, pin.lat, pin.lng)
                if pin.building_id:
                    scan.buildings[pin.id] = pin.building_id
                if property_type == '원룸' and geohash is not None:
                    scan.oneroom_cells[pin.id] = geohash
        scan.null_notes.extend(pin_null_notes(f'직방 {property_type} 지도 매물 핀·섹션', [response for _, response in responses]))
        ordered = section_ordered_ids([response for _, response in responses], in_scope)
        ids = [item_id for item_id in ordered if item_id not in claimed]
        scan.ids_by_type[property_type] = ids
        scan.overlaps[property_type] = len(ordered) - len(ids)
        claimed.update(ids)
    return scan


def _fill_officetel_complex_ids(
    client: ZigbangClient,
    listings: list[Listing],
    scan: _ScopePins,
    *,
    subway_id: int | None,
    radius_km: float,
) -> list[str]:
    """원룸 목록에 섞여 온 오피스텔의 `complex_id` 를 같은 범위·조건의 오피스텔 목록으로 채운다.

    오피스텔 목록(덤)을 받지 못하면 채우지 못한 `complex_id` 는 모름(null)이고 `[실패]` 안내를 돌려준다.
    """
    # 원룸 목록 핀에는 건물 ID 가 없다 (2026-10-10 실측: 역삼동 468건 모두 null, 요약에도 없음).
    # 같은 범위·조건의 오피스텔 목록은 건물 ID 를 주고 섞여 온 오피스텔과 모두 겹쳤다 (286건)
    missing = [
        listing for listing in listings
        if isinstance(listing, ZigbangListing) and listing.property_type == '오피스텔' and listing.complex_id is None
    ]
    if not missing or scan.oneroom_query is None:
        return []
    sales_types, type_filters = scan.oneroom_query
    # 빠진 매물이 있던 칸만 받는다 (2026-10-11 실측: 역삼동 원룸 5km 11칸 중 건물 ID 를 채운 칸은 1칸,
    # 오피스텔 13건 모두 그 칸에서 채움)
    cells = sorted({scan.oneroom_cells[int(listing.id)] for listing in missing if int(listing.id) in scan.oneroom_cells})
    try:
        # 원룸 검색과 같은 조건의 오피스텔 핀에서 매물 ID → 건물 ID 를 받는다
        responses = _scope_pins(
            client, '오피스텔', geohashes=cells, subway_id=subway_id, radius_km=radius_km,
            sales_types=sales_types, type_filters=type_filters,
        )
        buildings = {pin.id: pin.building_id for _, response in responses for pin in response.items if pin.building_id}
    except OPTIONAL_LOOKUP_ERRORS as exc:
        # 건물 ID 는 덤이라 못 받으면 모름(null)으로 둔다
        return [lookup_failure_note(
            exc, '직방', '오피스텔 목록',
            f'원룸 목록에 섞인 오피스텔 {len(missing)}건의 complex_id 를 모릅니다 (url 의 직방 페이지에서 확인)',
        )]
    for listing in missing:
        building_id = buildings.get(int(listing.id))
        if building_id:
            listing.complex_id = officetel_complex_id(building_id)
    return []


def _search_result(
    region: ZigbangRegion,
    listings: list[Listing],
    scan: _ScopePins,
    notes: list[str],
    *,
    starts: dict[ZigbangPropertyType, int],
    shares: dict[ZigbangPropertyType, int],
    limit: int,
    radius_km: float,
    boundary: ZigbangBoundary | None,
    summary_nulls: int = 0,
) -> ZigbangSearchResult:
    """범위 안 매물 수와 조회 한도·제외 안내를 붙여 결과를 만든다.

    `shares` 는 종류마다 이번에 요약을 받은 자리 수다. 종류별 목록이 서로 겹치지 않아(`_collect_pins`) 자리를 더한 수가 곧
    받은 매물 수다. 범위(동 경계·반경) 안에 아직 요약을 받지 않은 자리가 남은 종류가 있으면 종류마다 다음 자리를 이어 받을
    위치로 붙인다. `summary_nulls` 는 요약 응답에서 빈 항목으로 뺀 수로, 제외 안내에 이유를 보탠다.
    """
    in_scope = sum(len(ids) for ids in scan.ids_by_type.values())
    offsets = {kind: starts[kind] + share for kind, share in shares.items()}
    has_more = any(offsets[kind] < len(scan.ids_by_type[kind]) for kind in offsets)
    taken = sum(shares.values())
    notes = notes + excluded_notes(
        limit, taken, len(listings), order='직방 목록 순으로 앞의', has_more=has_more, null_items=summary_nulls,
    )
    notes += scan.null_notes
    # 핀 수는 거래 불가를 요약에서 거르기 전이라 근사값이다. 이어 받은 자리는 종류별 자리를 더한 수다
    notes += limit_notes(
        in_scope, len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow='조건·반경' if boundary is None else '조건·지역',
        order='직방 목록', approximate=True, inspected=taken, offset=sum(starts.values()), resumable=has_more,
        has_more=has_more,
    )
    if len(shares) > 1:
        # 종류 여럿을 찾았을 때 종류마다 범위 안 몇 건 중 목록의 몇 번째 자리를 받았는지 한 줄로 알린다
        parts: list[str] = []
        for kind, share in shares.items():
            found = len(scan.ids_by_type[kind])
            first, last = starts[kind] + 1, starts[kind] + share
            if not found:
                parts.append(f'{kind} 0건')
            elif not share:
                parts.append(f'{kind} 약 {found}건 중 0건')
            elif first == last:
                parts.append(f'{kind} 약 {found}건 중 1건 ({first}번째)')
            else:
                parts.append(f'{kind} 약 {found}건 중 {share}건 ({first}~{last}번째)')
        overlaps = [f'{kind} {count}건' for kind, count in scan.overlaps.items() if count]
        notes.append(note(
            '참고',
            '직방은 매물 종류마다 목록이 따로라 --limit 을 종류별로 나눠 각 목록 순서대로 받았습니다: ' + ', '.join(parts)
            + (
                f". 앞 종류 목록에도 있는 매물({', '.join(overlaps)}, 원룸 목록의 '이 지역 오피스텔')은 앞 종류에서만 세고 냅니다"
                if overlaps else ''
            ),
        ))
    return ZigbangSearchResult(
        region=region,
        radius_km=radius_km if boundary is None else None,
        boundary=boundary.name if boundary is not None else None,
        total=in_scope,
        returned=len(listings),
        listings=listings,
        notes=notes,
        has_more=has_more,
        next_position={'offsets': offsets} if has_more else None,
    )


def attach_building_use(client: ZigbangClient, result: ZigbangSearchResult) -> ZigbangSearchResult:
    """목록 매물마다 상세(`/items/{id}/detail`)를 1회씩 받아 건물 용도(`residence_type`)와 사용승인일을 붙인다 (`--details`).

    목록 API 는 건물 용도·사용승인일을 주지 않는다 (2026-10-15 실측: `items/list` 요약에 용도 필드 없음). 근린생활시설·고시원처럼
    전입신고가 막힐 수 있는 매물을 상세를 하나씩 열지 않고 고르게 한다. 사용승인일도 같은 상세에 있어 함께 채운다
    (2026-10-31 에이전트 검증: 직방에는 연식 조건이 없어 '10년 이내' 를 확인하려고 상세를 8회씩 따로 불렀다).
    앞 `DETAILS_MAX` 건만 보고, 상세에서 거래가 끝난 매물(404·`status` 가 open 이 아님)은 뺀다 (만료 매물은 내보내지 않는다).
    그 밖의 덤 조회 실패(`OPTIONAL_LOOKUP_ERRORS`: 네트워크·상태 코드·응답 형식 오류·요청 제한)는 그 매물을 목록 값 그대로 두고
    건물 용도는 모름(null)으로 둔다. 상세 한 건 때문에 이미 받은 목록 전체를 버리지 않는다 (2026-11-19 리뷰). 요청 제한이면
    다음 요청도 같은 제한에 걸리므로 (앞에 다른 실패가 있었어도) 남은 매물의 상세는 요청하지 않고 같게 둔다. 못 붙인 매물 수와
    이유(거절·응답 형식 변경이 한 건이라도 있으면 그 이유(요청 제한도 왔으면 덧붙임), 없으면 요청 제한, 없으면 첫 실패 이유.
    `LookupFailures`)는 `[실패]` 안내 하나로 알린다. 업데이트 문구는 다른 직방 덤 조회와 같은 공통 기준이다 (`is_rejected`).
    """
    listings: list[Listing] = []
    gone = 0
    # 상세를 못 붙인 매물 수(실패한 것 + 요청 제한 뒤라 요청하지 않은 것)와 안내할 이유
    failures = LookupFailures()
    for index, listing in enumerate(result.listings):
        if not isinstance(listing, ZigbangListing):
            listings.append(listing)
            continue
        if index >= DETAILS_MAX:
            # 상세를 받지 않은 매물도 건물 용도는 모름(null)으로 낸다. 원래 모델 그대로 두면 residence_type 키가 빠져
            # 출력 규약상 해당 없음으로 읽힌다 (키 없음 = 해당 없음, null = 모름. 2026-10-28 실측: 역삼동 원룸 --limit 31
            # --details 의 31번째가 null, 앞 30건은 용도가 붙음)
            listings.append(listing_as(ZigbangDetailedListing, listing))
            continue
        if failures.stopped:
            failures.skip()
            listings.append(listing_as(ZigbangDetailedListing, listing))
            continue
        try:
            with unavailable_on_404(listing.id):
                item = client.run_request_items_detail_v1(
                    ZigbangItemsDetailV1RequestParameterModel(item_id=int(listing.id))
                ).item
        except ListingUnavailableError:
            gone += 1
            continue
        except OPTIONAL_LOOKUP_ERRORS as exc:
            failures.add(exc)
            listings.append(listing_as(ZigbangDetailedListing, listing))
            continue
        if item.status != 'open':
            gone += 1
            continue
        residence = item.residence
        building_use = (residence.residence_description or residence.residence_type or '').strip() or None
        approved = listing.model_copy(update={'approved_at': normalize_date(residence.approved_at) or listing.approved_at})
        listings.append(listing_as(ZigbangDetailedListing, approved, residence_type=building_use))
    notes = []
    if gone:
        # 검색이 만든 안내('이 N건이 전부입니다' 등)는 빼기 전 개수라 returned 와 다를 수 있다
        notes.append(note('제외', f'{gone}건은 상세를 보니 거래가 끝나 뺐습니다 (앞 안내의 건수는 빼기 전 기준)'))
    reason = failures.reason(lambda exc: lookup_failure_reason(exc, '직방', '매물 상세'))
    if reason is not None:
        notes.append(note(
            '실패',
            f'매물 {failures.count}건의 상세(건물 용도·사용승인일)를 받지 못해 목록 값만 넣었습니다: {reason}',
        ))
    if len(result.listings) > DETAILS_MAX:
        notes.append(f'건물 용도·사용승인일(--details)은 앞 {DETAILS_MAX}건에만 붙였습니다')
    return result.model_copy(update={'listings': listings, 'returned': len(listings), 'notes': result.notes + notes})
