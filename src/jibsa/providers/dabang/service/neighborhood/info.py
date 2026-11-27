"""동 하나의 동네정보 (neighborhood)."""
from jibsa.core.listing import (
    AmountSet,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.neighborhood.info import (
    SUMMARY_TYPE_FIELD_BY_TOPIC,
    DabangRegionInfoCountTopic,
    DabangRegionInfoRegionalCountV5RequestParameterModel,
    DabangRegionInfoRegionalSummaryV5RequestParameterModel,
    DabangRegionInfoSummaryTopic,
)
from jibsa.providers.dabang.api.models.response.neighborhood.info import (
    DabangCountModel,
    DabangDistributionModel,
    DabangRankingGroupModel,
    DabangRegionInfoSummaryResultModel,
)
from jibsa.providers.dabang.service.common.text import (
    count_of,
)
from jibsa.providers.dabang.service.neighborhood.common import base_month
from jibsa.providers.dabang.service.neighborhood.constants import (
    COUNT_TOPIC_BY_LABEL,
    FIELD_BY_TOPIC,
    NEIGHBORHOOD_TOPICS,
    RANK_TYPES_BY_TOPIC,
    NeighborhoodTopic,
)
from jibsa.providers.dabang.service.neighborhood.models import (
    DabangAgeGroup,
    DabangCategoryRank,
    DabangCountStats,
    DabangNeighborhood,
    DabangPopulation,
    DabangPriceStats,
    DabangRank,
    DabangTypeCount,
    DabangTypePrice,
)
from jibsa.providers.dabang.service.region.models import DabangDong

from typing import (
    Any,
)


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
        base_month=base_month(update_dates),
        topics=chosen,
        ranks=rank_list,
        with_ranks=ranks,
        notes=notes,
        **data,
    )
