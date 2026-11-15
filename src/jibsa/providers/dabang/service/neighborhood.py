"""동네정보 (neighborhood) 와 동 안 인기 매물 (popular-listings)."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    Listing,
    limit_notes,
    listing_as,
    normalize_address,
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
    DabangCountGroupModel,
    DabangCountModel,
    DabangDistributionModel,
    DabangHotPlaceModel,
    DabangRankingGroupModel,
    DabangRegionInfoSummaryResultModel,
)
from jibsa.providers.dabang.service.common import (
    POPULAR_BUILDING_BY_LABEL,
    REGION_INFO_MAX_LIMIT,
    VILLA_LABEL,
    DabangListing,
    DabangPage,
    DabangPlace,
    ListingKind,
    count_of,
    fetch_pages,
    more_after,
    region_info_list_notes,
    room_item_to_listing,
    unreadable_note,
)
from jibsa.providers.dabang.service.region import DabangDong

from typing import (
    Annotated,
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
# 출력 키 (주제 라벨 → 결과 필드)
FIELD_BY_TOPIC: dict[str, str] = {
    '매물': 'listings',
    '거래': 'trades',
    '시세': 'prices',
    '인구': 'population',
    '학교': 'schools',
    '편의': 'amenities',
    '교통': 'transport',
    '안전': 'safety',
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


def single_dong(place: DabangPlace) -> DabangPlace:
    """동네정보·인기 매물은 동 하나를 받는다. '○가' 로 나뉜 동(성수동)은 위치 찾기(`resolve_places`)가 하나를 고르게 한다.

    Raises:
        JibsaError: 동이 아닌 역·대학·좌표일 때 (INVALID_ARGUMENT).
    """
    if place.kind != 'dong' or place.gid is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'동네정보는 동 이름으로만 찾습니다: {place.name}',
            hint="법정동 이름(예: '역삼동')을 주세요. 역 둘레는 jibsa dabang station-prices <역> 이나 search listings 로 봅니다",
        )
    return place


class DabangRank(BaseModel):
    """동네정보 순위 (작을수록 높다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    national: Annotated[
        int | None,
        Field(description='전국 순위')
    ] = None
    state: Annotated[
        int | None,
        Field(description='시·도 안 순위')
    ] = None
    state_name: Annotated[
        str | None,
        Field(description="시·도 ('서울')")
    ] = None
    district: Annotated[
        int | None,
        Field(description='시·군·구 안 순위')
    ] = None
    district_name: Annotated[
        str | None,
        Field(description="시·군·구 ('강남구')")
    ] = None


def _rank(group: DabangRankingGroupModel | None) -> DabangRank | None:
    if group is None:
        return None
    return DabangRank(
        national=count_of(group.formatted_national_rank),
        state=count_of(group.formatted_state_rank),
        state_name=group.state_name,
        district=count_of(group.formatted_city_rank),
        district_name=group.city_name,
    )


class DabangTypeCount(BaseModel):
    """매물 유형 하나의 수와 거래 유형별 나눔."""

    model_config = ConfigDict(
        extra='forbid',
    )

    type: Annotated[
        str,
        Field(description='매물 유형 (주택/빌라, 오피스텔, 아파트)')
    ]
    total: Annotated[
        int | None,
        Field(description='수')
    ] = None
    rent: Annotated[
        int | None,
        Field(description='월세')
    ] = None
    lease: Annotated[
        int | None,
        Field(description='전세')
    ] = None
    sale: Annotated[
        int | None,
        Field(description='매매')
    ] = None


class DabangCountStats(BaseModel):
    """매물 수 또는 거래량."""

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int | None,
        Field(description='합계')
    ] = None
    by_type: Annotated[
        list[DabangTypeCount],
        Field(description='매물 유형별')
    ]
    rank: Annotated[
        DabangRank | None,
        Field(description='합계 순위')
    ] = None


class DabangTypePrice(BaseModel):
    """매물 유형 하나의 평균가 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    type: Annotated[
        str,
        Field(description='단지 유형 (아파트, 오피스텔)')
    ]
    sale_average_manwon: Annotated[
        float | None,
        Field(description='평균 매매가 (만원)')
    ] = None
    lease_average_manwon: Annotated[
        float | None,
        Field(description='평균 전세가 (만원)')
    ] = None


class DabangPriceStats(BaseModel):
    """시세정보 평균가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    by_type: Annotated[
        list[DabangTypePrice],
        Field(description='단지 유형별 평균가')
    ]
    rank: Annotated[
        DabangRank | None,
        Field(description="아파트 평균 매매가 순위 (다방 화면 '아파트/매매 기준'. 오피스텔·전세가는 순위에 들지 않는다)")
    ] = None


class DabangAgeGroup(BaseModel):
    """연령대 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    age: Annotated[
        str,
        Field(description="연령대 ('20대', '10대 이하', '60대 이상')")
    ]
    count: Annotated[
        int | None,
        Field(description='인구')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='비율 (%)')
    ] = None


class DabangPopulation(BaseModel):
    """인구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int | None,
        Field(description='인구')
    ] = None
    male: Annotated[
        int | None,
        Field(description='남성')
    ] = None
    female: Annotated[
        int | None,
        Field(description='여성')
    ] = None
    ages: Annotated[
        list[DabangAgeGroup],
        Field(description='연령대별')
    ]
    rank: Annotated[
        DabangRank | None,
        Field(description='인구 순위')
    ] = None


class DabangCategoryRank(BaseModel):
    """학교·편의·교통·안전 탭 종류 하나의 합계·구성과 순위 (웹 요약 칸, `--ranks`)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    topic: Annotated[
        str,
        Field(description="주제 ('학교', '편의', '교통', '안전')")
    ]
    type: Annotated[
        str,
        Field(description="종류 (다방 요약 칸 이름표: '어린이집', '생활 편의시설', '교통시설', '안전시설' 등)")
    ]
    total: Annotated[
        int | None,
        Field(description='그 종류의 합계 (시설·학교 수)')
    ] = None
    counts: Annotated[
        dict[str, int | None] | None,
        Field(description="구성 ({'편의점': 204, '세탁소': 62}, 어린이집은 설립 구분 {'공공': 3})")
    ] = None
    rank: Annotated[
        DabangRank | None,
        Field(description='합계 순위 (전국·시도·구)')
    ] = None


class DabangNeighborhood(BaseModel):
    """다방 동네정보 요약. 고르지 않은 주제는 키가 없다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='동')
    ]
    base_month: Annotated[
        str | None,
        Field(description='다방 동네정보 기준 달 (YYYY-MM)')
    ] = None
    listings: Annotated[
        DabangCountStats | None,
        Field(description='지금 올라온 다방 매물 수 (매물 유형·거래 유형별)')
    ] = None
    trades: Annotated[
        DabangCountStats | None,
        Field(description='거래량 (국토교통부 신고 기준, 다방 집계, 매물 유형·거래 유형별)')
    ] = None
    prices: Annotated[
        DabangPriceStats | None,
        Field(description='아파트·오피스텔 평균 매매가·전세가 (국토교통부 실거래 기준, 다방 집계)')
    ] = None
    population: Annotated[
        DabangPopulation | None,
        Field(description='인구·성별·연령대 (행정안전부)')
    ] = None
    schools: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="학교 종류별 설립 구분 수와 학원 종류별 수 ({'초등학교': {'국공립': 2}, '학원': {'예체능': 92}})")
    ] = None
    amenities: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="편의시설 묶음별 시설 수 ({'생활편의시설': {'편의점': 204}})")
    ] = None
    transport: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="교통·차량 시설 수 ({'교통시설': {'지하철': 5, '버스': 73}})")
    ] = None
    safety: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="생활안전 시설 수 ({'안전시설': {'CCTV': 1074}})")
    ] = None
    ranks: Annotated[
        list[DabangCategoryRank],
        Field(description='학교·편의·교통·안전 종류마다 합계·구성과 전국·시도·구 순위 (--ranks 일 때만)')
    ] = []
    topics: Annotated[
        list[str],
        Field(exclude=True, description='고른 주제')
    ] = []
    with_ranks: Annotated[
        bool,
        Field(exclude=True, description='--ranks 를 줬는지')
    ] = False

    @model_serializer(mode='wrap')
    def drop_unrequested(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for topic, field in FIELD_BY_TOPIC.items():
            if topic not in self.topics:
                data.pop(field, None)
        if not self.with_ranks:
            data.pop('ranks', None)
        return data


def _type_counts(result: DabangRegionInfoSummaryResultModel) -> DabangCountStats:
    details: list[DabangDistributionModel] = result.distribution_detail_list or result.distribution_list or []
    by_type = []
    for item in details:
        parts = {part.name: int(part.value) if part.value is not None else None for part in item.composition_list}
        by_type.append(DabangTypeCount(
            type=item.name,
            total=int(item.value) if item.value is not None else None,
            rent=parts.get('월세'),
            lease=parts.get('전세'),
            sale=parts.get('매매'),
        ))
    total = sum(item.total or 0 for item in by_type) if by_type else None
    return DabangCountStats(total=total, by_type=by_type, rank=_rank(result.ranking_group))


def _counts(groups: list[DabangCountGroupModel]) -> dict[str, dict[str, int | None]]:
    result: dict[str, dict[str, int | None]] = {}
    for group in groups:
        name = group.amenity_type_name or group.mobility_type_name or group.life_safety_type_name or group.school_type_name
        if name:
            result[name] = _count_items(group.count_list)
    return result


def _count_items(items: list[DabangCountModel]) -> dict[str, int | None]:
    return {
        label: count_of(item.formatted_count)
        for item in items
        if (label := item.facility_name or item.establishment_type_name or item.academy_type_name)
    }


def _population(result: DabangRegionInfoSummaryResultModel) -> DabangPopulation:
    genders = {group.gender_type_name: group.count for group in result.gender_distribution_list}
    return DabangPopulation(
        total=result.total_count,
        male=genders.get('남성'),
        female=genders.get('여성'),
        ages=[
            DabangAgeGroup(age=group.age_type_name or '', count=group.count, percent=group.percent)
            for group in result.age_distribution_list
        ],
        rank=_rank(result.ranking_group),
    )


def _month(update_date: str | None) -> str | None:
    """'26.10' → '2026-10'."""
    if not update_date or '.' not in update_date:
        return None
    year, month = update_date.split('.', 1)
    return f'20{year}-{int(month):02d}' if year.isdecimal() and month.isdecimal() else None


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
    months: list[str | None] = []

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
            months.append(_month(result.update_date))
        return result

    if '매물' in chosen:
        result = summary('room', 'ROOM_COUNT')
        data['listings'] = None if result is None else _type_counts(result)
    if '거래' in chosen:
        result = summary('room', 'TRADE_VOLUME')
        data['trades'] = None if result is None else _type_counts(result)
    if '시세' in chosen:
        result = summary('real-estate', 'AVERAGE_PRICE')
        data['prices'] = None if result is None else DabangPriceStats(
            by_type=[
                DabangTypePrice(type=item.name, sale_average_manwon=item.sale_price, lease_average_manwon=item.lease_price)
                for item in result.distribution_list or []
            ],
            rank=_rank(result.ranking_group),
        )
    if '인구' in chosen:
        result = summary('population')
        data['population'] = None if result is None else _population(result)
    for topic, api_topic in COUNT_TOPIC_BY_LABEL.items():
        if topic not in chosen:
            continue
        counts = client.run_request_region_info_regional_count_v5(
            DabangRegionInfoRegionalCountV5RequestParameterModel(topic=api_topic, region_gid=gid)
        ).result
        if counts is None:
            data[FIELD_BY_TOPIC[topic]] = None
            continue
        values = _counts(counts.facility_count_list or counts.school_count_list)
        if counts.academy_count is not None:
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
                    total=count_of(result.formatted_total_count),
                    # 다방이 구성을 null 로 주면 모름(null), 빈 목록으로 주면 없음({})이다
                    counts=None if result.distribution_list is None else {
                        item.name: item.count if item.count is not None else count_of(item.formatted_count)
                        for item in result.distribution_list
                    },
                    rank=_rank(result.ranking_group),
                ))
    return DabangNeighborhood(
        region=place,
        base_month=next((month for month in months if month), None),
        topics=chosen,
        ranks=rank_list,
        with_ranks=ranks,
        **data,
    )


class DabangRankedListing(DabangListing):
    """동 안 인기 매물 (순위가 붙은 다방 매물)."""

    rank: Annotated[
        int,
        Field(description='다방 선호도(조회수·찜수·문의수를 합친 점수) 순위. 1이 가장 높다')
    ]


class DabangPopularResult(BaseModel):
    """동 안 인기 매물."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='동')
    ]
    total: Annotated[
        int | None,
        Field(description='순위가 있는 매물 수 (고른 유형·거래 유형 안)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='순위가 더 있는지')
    ] = False
    listings: Annotated[
        list[SerializeAsAny[Listing]],
        Field(description='선호도 높은 순 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='제외·일부 안내')
    ] = []


def get_popular_listings(
    client: DabangClient,
    place: DabangPlace,
    *,
    building_types: list[str],
    trade_types: list[str],
    limit: int,
) -> DabangPopularResult:
    """동 안 인기 매물 (다방 선호도 높은 순, 50건마다 요청 1회).

    매물 유형을 하나만 고르면 그 유형으로, 여럿이면 칸의 표시로 `property_type` 을 붙인다 (방 개수 표시는 빌라다).
    """
    gid = place.gid
    assert gid is not None  # single_dong 이 동만 넘긴다
    labels = building_types or list(POPULAR_BUILDING_BY_LABEL)
    kind: ListingKind | None = POPULAR_KIND_BY_BUILDING[labels[0]] if len(labels) == 1 else None
    listings: list[Listing] = []
    received = unreadable = 0
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
            listings.append(listing_as(DabangRankedListing, listing, rank=(page - 1) * page_size + index + 1))
        # 잘라 낸 줄이 있으면 더 있고, 빈 쪽이면 hasMore 가 와도 더 없다 (`more_after`)
        has_more = more_after(bool(result.has_more), len(result.list_), cut=len(result.list_) - len(rows))
        if not result.has_more or not result.list_:
            break
        page += 1
    notes: list[str] = []
    notes += unreadable_note(unreadable)
    # 동 하나(single_dong)의 순위라 좁힐 지역이 없어 이 명령의 -t·--trade 만 권한다 (2026-11-10 리뷰·실측: 역삼동 --limit 100
    # 600건에 '조건·지역을 좁히세요')
    notes += limit_notes(
        total, len(listings), limit, max_limit=POPULAR_MAX_LIMIT, order='선호도 높은', narrow='매물 유형·거래 유형 조건',
        inspected=received, has_more=has_more,
    )
    return DabangPopularResult(region=place, total=total, returned=len(listings), has_more=has_more, listings=listings, notes=notes)


class DabangHotPlace(BaseModel):
    """핫플레이스 식당 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='식당 이름')
    ] = None
    guide: Annotated[
        str | None,
        Field(description="오른 가이드 ('미쉐린', '블루리본'. 다방 이름표가 없는 값이면 null)")
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (다방이 주지 않으면 null, 웹은 '주소 정보를 확인하고 있어요.')")
    ] = None
    labels: Annotated[
        list[str],
        Field(description="꼬리표 ('한식(일반한식)', '솥밥')")
    ]


class DabangHotPlacesResult(BaseModel):
    """동 안 핫플레이스."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='동')
    ]
    type: Annotated[
        str,
        Field(description="고른 가이드 ('전체', '미쉐린', '블루리본')")
    ]
    basis: Annotated[
        str,
        Field(description='무엇을 모은 목록인지')
    ]
    base_month: Annotated[
        str | None,
        Field(description='다방 기준 달 (YYYY-MM)')
    ] = None
    total: Annotated[
        int | None,
        Field(description='전체 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 있는지')
    ] = False
    places: Annotated[
        list[DabangHotPlace],
        Field(description='다방 목록 순 식당')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부 안내')
    ] = []


def get_hot_places(client: DabangClient, dong: DabangDong, *, type_label: str, limit: int) -> DabangHotPlacesResult:
    """동 안 핫플레이스 (웹 동네정보 '핫플레이스', 30곳마다 요청 1회). 미쉐린·블루리본 가이드에 오른 식당을 다방 목록 순으로 준다.

    사진 주소는 내보내지 않는다.
    """
    place, gid = dong
    month: list[str | None] = []

    def fetch(page: int) -> DabangPage[DabangHotPlaceModel] | None:
        result = client.run_request_region_info_hot_places_v5(DabangRegionInfoHotPlacesV5RequestParameterModel(
            region_gid=gid, type=HOT_PLACE_TYPE_BY_LABEL[type_label], page=page,
        )).result
        if result is None:
            return None
        month.append(_month(result.update_date))
        return DabangPage(result.list_ or [], result.total, bool(result.has_more))

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
        base_month=next((value for value in month if value), None),
        total=pages.total,
        returned=len(places),
        has_more=pages.has_more,
        places=places,
        notes=notes,
    )
