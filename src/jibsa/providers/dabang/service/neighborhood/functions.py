"""동네정보·동 안 인기 매물의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""
from jibsa.core.listing import (
    AmountSet,
    Listing,
    holding_unread_dates,
    keep_unread_dates,
    limit_notes,
    listing_as,
    normalize_address,
    null_items_note,
    read_month,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import REGION_INFO_PAGE_LIMIT
from jibsa.providers.dabang.api.request.neighborhood import (
    POPULAR_ROOM_PAGE_LIMIT,
    SUMMARY_TYPE_FIELD_BY_TOPIC,
    DabangAmenitySummaryType,
    DabangHotPlaceType,
    DabangLifeSafetySummaryType,
    DabangMobilitySummaryType,
    DabangPopularPriceType,
    DabangRegionInfoCountTopic,
    DabangRegionInfoHotPlacesV5RequestParameterModel,
    DabangRegionInfoRegionalCountV5RequestParameterModel,
    DabangRegionInfoRegionalSummaryV5RequestParameterModel,
    DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel,
    DabangRegionInfoSummaryTopic,
    DabangSchoolSummaryType,
)
from jibsa.providers.dabang.api.response.neighborhood import (
    DabangCountModel,
    DabangDistributionModel,
    DabangHotPlaceModel,
    DabangRankingGroupModel,
    DabangRegionInfoSummaryResultModel,
)
from jibsa.providers.dabang.service.common.functions import (
    POPULAR_BUILDING_BY_LABEL,
    REGION_INFO_MAX_LIMIT,
    VILLA_LABEL,
    DabangPage,
    ListingKind,
    count_of,
    fetch_pages,
    more_after,
    region_info_list_notes,
    room_item_to_listing,
    unreadable_note,
)
from jibsa.providers.dabang.service.neighborhood.models import (
    FIELD_BY_TOPIC,
    DabangAgeGroup,
    DabangCategoryRank,
    DabangCountStats,
    DabangHotPlace,
    DabangHotPlacesResult,
    DabangNeighborhood,
    DabangPopularResult,
    DabangPopulation,
    DabangPriceStats,
    DabangRank,
    DabangRankedListing,
    DabangTypeCount,
    DabangTypePrice,
)
from jibsa.providers.dabang.service.region.functions import DabangDong

from typing import (
    Any,
    Literal,
)


NeighborhoodTopic = Literal['매물', '거래', '시세', '인구', '학교', '편의', '교통', '안전']
NEIGHBORHOOD_TOPICS: tuple[NeighborhoodTopic, ...] = ('매물', '거래', '시세', '인구', '학교', '편의', '교통', '안전')
COUNT_TOPIC_BY_LABEL: dict[str, DabangRegionInfoCountTopic] = {
    '학교': 'school',
    '편의': 'amenity',
    '교통': 'mobility',
    '안전': 'life-safety',
}

POPULAR_PRICE_BY_TRADE: dict[str, DabangPopularPriceType] = {'월세': 'MONTHLY_RENT', '전세': 'LEASE', '매매': 'SALE'}
POPULAR_KIND_BY_BUILDING: dict[str, ListingKind] = {VILLA_LABEL: 'villa', '오피스텔': 'officetel', '아파트': 'apt'}
# 유형을 섞어 받으면 칸에 건물 유형이 없다. 오피스텔·아파트는 그 이름으로, 주택·빌라는 방 개수('원룸'·'투룸')로 표시한다
# (2026-10-25 실측: 역삼동·대치동 유형별 50건씩)
POPULAR_KIND_BY_ROOM_TYPE: dict[str, ListingKind] = {'오피스텔': 'officetel', '아파트': 'apt'}
POPULAR_MAX_LIMIT: int = 100
# --ranks: 학교·편의·교통·안전 탭의 요약 칸 종류 (웹 이름표, 요청 값). 웹 요약 칸의 고르기 순서 그대로다 (school·facility·
# traffic·life-safety 청크 tabList, 2026-11-13). 종류마다 요청 1회. 요청 값은 주제마다 그 탭의 Literal 로 검사한다
SCHOOL_RANK_TYPE_BY_LABEL: dict[str, DabangSchoolSummaryType] = {
    '어린이집': 'NURSERY_SCHOOL', '유치원': 'KINDER_SCHOOL', '초등학교': 'ELEMENTARY_SCHOOL', '중학교': 'MIDDLE_SCHOOL',
    '고등학교': 'HIGH_SCHOOL',
}
AMENITY_RANK_TYPE_BY_LABEL: dict[str, DabangAmenitySummaryType] = {
    '생활 편의시설': 'LIVING', '의료시설': 'MEDICAL', '외식시설': 'DINING', '대형 쇼핑시설': 'SHOPPING', '체육시설': 'SPORTS',
}
MOBILITY_RANK_TYPE_BY_LABEL: dict[str, DabangMobilitySummaryType] = {
    '교통시설': 'TRANSIT', '주차시설': 'PARKING_LOT', '주유시설': 'CHARGE_STATION', '차량관리시설': 'MAINTENANCE_SHOP',
}
LIFE_SAFETY_RANK_TYPE_BY_LABEL: dict[str, DabangLifeSafetySummaryType] = {
    '안전시설': 'SAFETY_FACILITY', '안전기관': 'SAFETY_ORGANIZATION', '불편요소': 'INCONVENIENCE',
}
RANK_TYPES_BY_TOPIC: dict[str, dict[str, str]] = {
    '학교': dict(SCHOOL_RANK_TYPE_BY_LABEL),
    '편의': dict(AMENITY_RANK_TYPE_BY_LABEL),
    '교통': dict(MOBILITY_RANK_TYPE_BY_LABEL),
    '안전': dict(LIFE_SAFETY_RANK_TYPE_BY_LABEL),
}
RANK_TOPICS: tuple[str, ...] = tuple(RANK_TYPES_BY_TOPIC)
# 핫플레이스 가이드 고르기 (웹 이름표 → 요청 값, hot-place 청크 2026-11-13)와 줄의 가이드 이름표
HOT_PLACE_TYPE_BY_LABEL: dict[str, DabangHotPlaceType] = {'전체': 'ALL', '미쉐린': 'MICHELIN_GUIDE', '블루리본': 'BLUE_RIBBON'}
HOT_PLACE_GUIDE_LABELS: dict[str, str] = {value: label for label, value in HOT_PLACE_TYPE_BY_LABEL.items() if value != 'ALL'}


def _rank(group: DabangRankingGroupModel | None) -> DabangRank | None:
    if group is None:
        return None
    return DabangRank(
        national_rank=count_of(group.formatted_national_rank),
        sido_rank=count_of(group.formatted_state_rank),
        sido=group.state_name,
        sigungu_rank=count_of(group.formatted_city_rank),
        sigungu=group.city_name,
    )


def _dropped_types(result: DabangRegionInfoSummaryResultModel) -> int:
    """매물 유형 목록(`_type_counts` 가 읽는 두 목록)에서 뺀 빈 항목 수."""
    return result.null_items('distribution_detail_list', 'distribution_list')


def _dropped_type_notes(result: DabangRegionInfoSummaryResultModel | None, topic: str, field: str) -> list[str]:
    """유형 목록에서 빈 항목을 뺐으면 그 주제의 합계(`<field>.count`)를 모른다는 안내."""
    dropped = 0 if result is None else _dropped_types(result)
    return [null_items_note(f'다방 동네정보 {topic} 유형별', dropped, (f'{field}.count',))] if dropped else []


def _type_counts(result: DabangRegionInfoSummaryResultModel) -> DabangCountStats:
    details: list[DabangDistributionModel] = result.distribution_detail_list or result.distribution_list or []
    by_type = []
    for item in details:
        parts = {part.name: int(part.value) if part.value is not None else None for part in item.composition_list}
        by_type.append(DabangTypeCount(
            property_type=item.name,
            count=int(item.value) if item.value is not None else None,
            counts={'sale': parts.get('매매'), 'jeonse': parts.get('전세'), 'wolse': parts.get('월세')},
        ))
    # 빈 항목을 뺐으면 그 유형의 수를 몰라 합계를 낼 수 없다 (받은 유형만 더하면 적은 합계가 완전한 값처럼 나간다)
    count = sum(item.count or 0 for item in by_type) if by_type and not _dropped_types(result) else None
    return DabangCountStats(count=count, by_type=by_type, ranking=_rank(result.ranking_group))


def _count_items(items: list[DabangCountModel]) -> dict[str, int | None]:
    return {
        label: count_of(item.formatted_count)
        for item in items
        if (label := item.facility_name or item.establishment_type_name or item.academy_type_name)
    }


def _base_month(update_dates: list[str | None]) -> str | None:
    """요약·쪽마다 받은 갱신일 글자('26.10') 중 처음 읽은 달을 'YYYY-MM' 으로 (`read_month`, 13월 같은 달은 못 읽음).

    값 없음(None·빈 글자·`-`)은 건너뛴다. 읽은 달이 없는데 못 읽은 글자가 있으면 출력 칸 `base_month` 하나가 null 이라 처음 못 읽은
    글자 하나만 `[참고]` 로 알린다.
    """
    with holding_unread_dates() as held:
        months = [
            read_month(f'20{text.strip()}', '기준 달', raw=text)
            for text in update_dates if text is not None and text.strip() not in ('', '-')
        ]
    month = next((value for value in months if value), None)
    if month is None:
        keep_unread_dates(held[:1])
    return month


def get_neighborhood(
    client: DabangClient, dong: DabangDong, topics: list[NeighborhoodTopic], *, ranks: bool = False,
) -> DabangNeighborhood:
    """동 하나의 다방 동네정보. 주제마다 요청 1회 (매물·거래·시세·인구는 요약과 순위, 학교·편의·교통·안전은 항목별 수).

    Args:
        dong: 찾은 동 (`resolve_dong`).
        ranks: 학교·편의·교통·안전 주제의 종류마다 웹 요약 칸(`regional/summary`)을 더 받아 합계·구성·순위를 붙일지. 종류마다
            요청 1회 (주제마다 `RANK_TYPES_BY_TOPIC` 의 종류 수만큼). 고른 주제의 종류만 받는다. Defaults to False.
    """
    place, gid = dong
    chosen = list(topics or NEIGHBORHOOD_TOPICS)
    data: dict[str, Any] = {}
    update_dates: list[str | None] = []
    notes: list[str] = []

    def summary(
        topic: DabangRegionInfoSummaryTopic | DabangRegionInfoCountTopic, summary_type: str | None = None,
    ) -> DabangRegionInfoSummaryResultModel | None:
        """요약 하나. 다방이 result 를 주지 않으면 None 이고, 부르는 쪽은 그 주제를 모름(null)으로 둔다 (빈 값이면 없다로 읽힌다).

        종류(`summary_type`)는 그 탭이 받는 칸(`SUMMARY_TYPE_FIELD_BY_TOPIC`)에 담아 보낸다. 인구는 종류가 없다.
        """
        params: dict[str, Any] = {'topic': topic, 'region_gid': gid}
        if summary_type is not None:
            params[SUMMARY_TYPE_FIELD_BY_TOPIC[topic]] = summary_type
        result = client.run_request_region_info_regional_summary_v5(
            DabangRegionInfoRegionalSummaryV5RequestParameterModel.model_validate(params)
        ).result
        if result is not None:
            update_dates.append(result.update_date)
        return result

    if '매물' in chosen:
        result = summary('room', 'ROOM_COUNT')
        data['listings'] = None if result is None else _type_counts(result)
        notes += _dropped_type_notes(result, '매물', 'listings')
    if '거래' in chosen:
        result = summary('room', 'TRADE_VOLUME')
        data['trades'] = None if result is None else _type_counts(result)
        notes += _dropped_type_notes(result, '거래', 'trades')
    if '시세' in chosen:
        result = summary('real-estate', 'AVERAGE_PRICE')
        data['prices'] = None if result is None else DabangPriceStats(
            by_type=[
                DabangTypePrice(complex_type=item.name, trade_averages={
                    'sale': None if item.sale_price is None else AmountSet(price_manwon=item.sale_price),
                    'jeonse': None if item.lease_price is None else AmountSet(deposit_manwon=item.lease_price),
                })
                for item in result.distribution_list or []
            ],
            ranking=_rank(result.ranking_group),
        )
    if '인구' in chosen:
        result = summary('population')
        if result is None:
            data['population'] = None
        else:
            genders = {group.gender_type_name: group.count for group in result.gender_distribution_list}
            data['population'] = DabangPopulation(
                population=result.total_count,
                male=genders.get('남성'),
                female=genders.get('여성'),
                ages=[
                    DabangAgeGroup(age=group.age_type_name or '', count=group.count, percent=group.percent)
                    for group in result.age_distribution_list
                ],
                ranking=_rank(result.ranking_group),
            )
    for topic, api_topic in COUNT_TOPIC_BY_LABEL.items():
        if topic not in chosen:
            continue
        counts = client.run_request_region_info_regional_count_v5(
            DabangRegionInfoRegionalCountV5RequestParameterModel(topic=api_topic, region_gid=gid)
        ).result
        if counts is None:
            data[FIELD_BY_TOPIC[topic]] = None
            continue
        # 시설·학교 종류 이름(묶음과 그 안 항목)은 다방이 보내는 이름표 그대로 키로 쓴다. 거래 키(sale 등)와 달리 어떤 이름이 올지
        # 미리 다 알 수 없어, 영어로 바꾸려면 다방에 없는 대응 표를 jibsa 가 지어야 하고 표에 없는 새 이름은 한국어로 섞이거나 빠진다
        # (출력 규약 '칸 이름 규칙' 의 예외)
        values: dict[str, dict[str, int | None]] = {}
        for group in counts.facility_count_list or counts.school_count_list:
            name = group.amenity_type_name or group.mobility_type_name or group.life_safety_type_name or group.school_type_name
            if name:
                values[name] = _count_items(group.count_list)
        if counts.academy_count is not None:
            # 학원은 다방이 이름 없이 따로 주는 칸이라 jibsa 가 키를 붙이지만, 같은 객체의 다른 키(초등학교 등)가 다방 이름표라
            # 한 객체 안에서 두 말이 섞이지 않게 한국어로 둔다 (출력 규약 '칸 이름 규칙' 의 예외)
            values['학원'] = _count_items(counts.academy_count.count_list)
        data[FIELD_BY_TOPIC[topic]] = values
    rank_list: list[DabangCategoryRank] = []
    if ranks:
        for topic, types in RANK_TYPES_BY_TOPIC.items():
            if topic not in chosen:
                continue
            api_topic = COUNT_TOPIC_BY_LABEL[topic]
            for label, value in types.items():
                result = summary(api_topic, value)
                if result is None:
                    # 다방이 result 를 주지 않으면 그 종류는 모름(null)이다
                    rank_list.append(DabangCategoryRank(topic=topic, type=label))
                    continue
                rank_list.append(DabangCategoryRank(
                    topic=topic,
                    type=label,
                    count=count_of(result.formatted_total_count),
                    # 다방이 구성을 null 로 주면 모름(null), 빈 목록으로 주면 없음({})이다
                    # 구성 항목 이름도 다방 이름표 그대로 키로 쓴다 (위 학교·시설 수와 같은 예외)
                    counts=None if result.distribution_list is None else {
                        item.name: item.count if item.count is not None else count_of(item.formatted_count)
                        for item in result.distribution_list
                    },
                    ranking=_rank(result.ranking_group),
                ))
    return DabangNeighborhood(
        region=place,
        base_month=_base_month(update_dates),
        topics=chosen,
        ranks=rank_list,
        with_ranks=ranks,
        notes=notes,
        **data,
    )


def get_popular_listings(
    client: DabangClient,
    dong: DabangDong,
    *,
    building_types: list[str],
    trade_types: list[str],
    limit: int,
) -> DabangPopularResult:
    """동 안 인기 매물 (다방 선호도 높은 순, 50건마다 요청 1회).

    매물 유형을 하나만 고르면 그 유형으로, 여럿이면 칸의 표시로 `property_type` 을 붙인다 (방 개수 표시는 빌라다).
    """
    place, gid = dong
    labels = building_types or list(POPULAR_BUILDING_BY_LABEL)
    kind: ListingKind | None = POPULAR_KIND_BY_BUILDING[labels[0]] if len(labels) == 1 else None
    listings: list[Listing] = []
    received = unreadable = dropped = 0
    total: int | None = None
    has_more = False
    page = 1
    # 다방은 (page - 1) × limit 번째부터 준다. 쪽마다 크기를 바꾸면 앞 쪽과 겹쳐 쪽 크기를 고정하고 넘치는 건 자른다
    # (2026-10-25 실측: 50건 다음 20건을 물으니 21~40위를 다시 줬다)
    page_size = min(POPULAR_ROOM_PAGE_LIMIT, limit)
    while received < limit:
        result = client.run_request_region_info_room_regional_popular_room_v5(
            DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel(
                region_gid=gid,
                building_category_list=[POPULAR_BUILDING_BY_LABEL[label] for label in labels],
                price_type_list=[POPULAR_PRICE_BY_TRADE[trade] for trade in trade_types or POPULAR_PRICE_BY_TRADE],
                limit=page_size,
                page=page,
            )
        ).result
        if result is None:
            break
        total = result.total if total is None else total
        rows = result.list_[:limit - received]
        # 이 쪽에서 빈 항목을 뺐으면 어느 자리가 빠졌는지 몰라 쪽 안 순위를 셀 수 없다 (다음 쪽은 쪽 번호로 세어 영향이 없다)
        page_dropped = result.null_items('list_')
        dropped += page_dropped
        for index, item in enumerate(rows):
            received += 1
            item_kind = kind or POPULAR_KIND_BY_ROOM_TYPE.get((item.room_type_name or '').partition('•')[0].strip(), 'villa')
            # 인기 매물 칸에는 동 번호(gid)가 없다 (모두 그 동 매물이다). 동 번호 자리 0 에 찾은 동 주소를 두어 주소를 채운다
            listing = room_item_to_listing(item, item_kind, addresses={0: place.address or place.name})
            if listing is None:
                unreadable += 1
                continue
            # 순위는 받은 수가 아니라 읽은 쪽과 칸으로 센다. 다방이 한 쪽을 덜 채워도 다음 쪽은 (page - 1) × 쪽 크기 번째부터라
            # 받은 수로 세면 그 뒤 순위가 앞으로 당겨진다
            listings.append(listing_as(
                DabangRankedListing, listing, rank=None if page_dropped else (page - 1) * page_size + index + 1,
            ))
        # 잘라 낸 줄이 있으면 더 있고, 빈 쪽이면 hasMore 가 와도 더 없다 (`more_after`)
        has_more = more_after(bool(result.has_more), len(result.list_), cut=len(result.list_) - len(rows))
        if not result.has_more or not result.list_:
            break
        page += 1
    notes: list[str] = []
    notes += unreadable_note(unreadable)
    if dropped:
        notes.append(null_items_note('다방 인기 매물', dropped, ('rank',)))
    # 동 하나(resolve_dong)의 순위라 좁힐 지역이 없어 이 명령의 -t·--trade 만 권한다 (2026-11-10 리뷰·실측: 역삼동 --limit 100
    # 600건에 '조건·지역을 좁히세요'). 이미 하나씩 골랐으면 더 좁힐 조건이 없어 권하지 않고, 한쪽만 골랐으면 다른 쪽만 권한다
    one_building = len(building_types or []) == 1
    one_trade = len(trade_types or []) == 1
    narrow = (
        None if one_building and one_trade
        else '거래 유형 조건' if one_building
        else '매물 유형 조건' if one_trade
        else '매물 유형·거래 유형 조건'
    )
    notes += limit_notes(
        total, len(listings), limit, max_limit=POPULAR_MAX_LIMIT, order='선호도 높은', narrow=narrow,
        inspected=received, has_more=has_more,
    )
    return DabangPopularResult(region=place, total=total, returned=len(listings), has_more=has_more, listings=listings, notes=notes)


def get_hot_places(client: DabangClient, dong: DabangDong, *, type_label: str, limit: int) -> DabangHotPlacesResult:
    """동 안 핫플레이스 (웹 동네정보 '핫플레이스', 30곳마다 요청 1회). 미쉐린·블루리본 가이드에 오른 식당을 다방 목록 순으로 준다.

    사진 주소는 내보내지 않는다.
    """
    place, gid = dong
    update_dates: list[str | None] = []

    def fetch(page: int) -> DabangPage[DabangHotPlaceModel] | None:
        result = client.run_request_region_info_hot_places_v5(DabangRegionInfoHotPlacesV5RequestParameterModel(
            region_gid=gid, type=HOT_PLACE_TYPE_BY_LABEL[type_label], page=page,
        )).result
        if result is None:
            return None
        update_dates.append(result.update_date)
        return DabangPage(result.list_ or [], result.total, bool(result.has_more), result.null_items('list_'))

    pages = fetch_pages(fetch, limit, page_size=REGION_INFO_PAGE_LIMIT, max_limit=REGION_INFO_MAX_LIMIT)
    places = [
        DabangHotPlace(
            name=row.restaurant_name, guide=HOT_PLACE_GUIDE_LABELS.get(row.type or ''),
            address=normalize_address(row.address or None),
            labels=row.label_list or [],
        )
        for row in pages.rows
    ]
    # 가이드 종류를 아직 고르지 않았을 때만 좁히라고 권한다
    narrow = '가이드 종류(--type 미쉐린·블루리본) 조건' if type_label == '전체' else None
    notes = region_info_list_notes(pages, limit, subject=f'{place.name} 핫플레이스', narrow=narrow)
    return DabangHotPlacesResult(
        region=place,
        type=type_label,
        basis="다방 동네정보 '핫플레이스': 미쉐린·블루리본 가이드에 오른 식당 (출처 미쉐린·블루리본)",
        base_month=_base_month(update_dates),
        total=pages.total,
        returned=len(places),
        has_more=pages.has_more,
        places=places,
        notes=notes,
    )
