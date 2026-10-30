"""분양 (search sales · sale · sale-schedule)."""
import re
from datetime import (
    date,
    timedelta,
)

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
)
from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import DabangBboxModel
from jibsa.providers.dabang.api.request.sale import (
    ALL_SALE_BUILDING_TYPES,
    ALL_SALE_STATES,
    ALL_SALE_SUPPLY_TYPES,
    DabangSaleBuildingType,
    DabangSaleInLotsDetail2V3RequestParameterModel,
    DabangSaleInLotsFiltersModel,
    DabangSaleInLotsListScheduleV3RequestParameterModel,
    DabangSaleListCategoryBboxV5RequestParameterModel,
    DabangSaleState,
    DabangSaleSupplyType,
)
from jibsa.providers.dabang.api.response.sale import DabangSaleItemModel
from jibsa.providers.dabang.service.common import (
    MAX_LIST_PAGES,
    PAGE_SIZE,
    DabangPlace,
    bbox_of,
    household_count,
    is_missing_id,
    manwon_from_text,
)
from jibsa.providers.dabang.service.region import (
    DabangScope,
    dongs_bbox,
    scope_bbox,
    state_name,
)

from typing import Annotated


SALE_URL: str = 'https://www.dabangapp.com/sale-in-lots/{sale_id}'
SALE_BUILDING_TYPE_BY_LABEL: dict[str, DabangSaleBuildingType] = {
    '아파트': 'APT',
    '오피스텔': 'OFFICETEL',
    '도시형생활주택': 'URBAN_HOUSE',
    '지식산업센터': 'KNOWLEDGE_INDUSTRY_CENTER',
}
SALE_STATE_BY_LABEL: dict[str, DabangSaleState] = {
    '분양예정': 'EXPECTED',
    '접수중': 'ACCEPTING',
    '접수마감': 'ACCEPT_COMPLETE',
    '입주예정': 'MOVE_IN_EXPECTED',
    '입주모집': 'MOVE_IN_RECRUIT',
}
SALE_SUPPLY_BY_LABEL: dict[str, DabangSaleSupplyType] = {
    '공공분양': 'PUBLIC_SALE',
    '민간분양': 'PRIVATE_SALE',
    '공공임대': 'PUBLIC_RENTAL',
    '민간임대': 'PRIVATE_RENTAL',
}
# 분양 일정 날짜 꼴: '26.09.07' (날), '26.08월' (달)
SALE_DAY_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2})\.(\d{1,2})\.(\d{1,2})$')
SALE_MONTH_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2})\.(\d{1,2})월$')
# 청약 일정 글: '[청약접수] 인천 인천계양 A17블록 … (~10/27)'
SCHEDULE_REGION_PATTERN: re.Pattern[str] = re.compile(r'^(?:\[[^\]]+\]\s*)+(\S+)')


def sale_url(sale_id: str) -> str:
    """분양 페이지. 서버가 지도 화면으로 넘겨 준다 (2026-10-25 실측: /sale-in-lots/{id} → 302 /map/sale-in-lots?…)."""
    return SALE_URL.format(sale_id=sale_id)


def sale_date(text: str | None) -> str | None:
    """다방 분양 날짜 글을 'YYYY-MM-DD' 나 'YYYY-MM' 으로 ('26.09.07' → '2026-09-07', '26.08월' → '2026-08'). 다른 꼴은 그대로."""
    if text is None or not text.strip():
        return None
    value = text.strip()
    if (match := SALE_DAY_PATTERN.fullmatch(value)) is not None:
        return f'20{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}'
    if (match := SALE_MONTH_PATTERN.fullmatch(value)) is not None:
        return f'20{match.group(1)}-{int(match.group(2)):02d}'
    return value


class DabangSaleSummary(BaseModel):
    """분양 단지 하나 (목록)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sale_id: Annotated[
        str,
        Field(description='분양 ID. jibsa dabang sale 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    state: Annotated[
        str | None,
        Field(description='분양 상태 (분양예정·접수중·접수마감·입주예정·입주모집)')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형 (공공분양·민간분양·공공임대·민간임대)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    price_kind: Annotated[
        str | None,
        Field(description="가격 종류 ('분양가', 임대는 '보증금')")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='대표 가격 (만원, 다방 표시). 아직 없으면 null')
    ] = None
    next_schedule: Annotated[
        str | None,
        Field(description="다음 일정 ('26.12.07 ~ 26.12.10 계약기간')")
    ] = None
    url: Annotated[
        str,
        Field(description='분양 페이지 URL')
    ]


class DabangSaleListResult(BaseModel):
    """분양 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        str,
        Field(description='찾은 범위')
    ]
    total: Annotated[
        int | None,
        Field(description='다방이 센 지도 범위(사각형) 안 분양 단지 수 (동·시군구 이름이면 이름으로 거르기 전)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 단지가 있는지')
    ] = False
    sales: Annotated[
        list[DabangSaleSummary],
        Field(description='다방 목록 순 분양 단지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='범위·제외 안내')
    ] = []


def _summary(item: DabangSaleItemModel) -> DabangSaleSummary:
    return DabangSaleSummary(
        sale_id=item.id,
        name=item.building_name,
        state=item.state_name,
        building_type=item.building_type_title,
        supply_type=item.supply_type_name,
        address=normalize_address(item.address),
        household_count=household_count(item.household_num_title),
        price_kind=item.supply_price_type_name,
        price_manwon=manwon_from_text(item.price_title),
        next_schedule=item.schedule_title,
        url=sale_url(item.id),
    )


def search_sales(
    client: DabangClient,
    *,
    place: DabangPlace | None = None,
    scope: DabangScope | None = None,
    places: list[DabangPlace] | None = None,
    radius_km: float | None = None,
    building_types: list[str] | None = None,
    states: list[str] | None = None,
    supply_types: list[str] | None = None,
    limit: int,
) -> DabangSaleListResult:
    """지도 범위 안 분양 단지 (다방 목록 순, 24곳씩). 다방 분양 목록은 지도 범위(사각형)만 받는다.

    동·시군구 이름이면 경계를 덮는 사각형으로 받고 주소가 그 동·시군구인 단지만 남긴다 (분양 칸에는 좌표·동 번호가 없어
    주소로 본다). 역·대학·좌표는 반경을 덮는 사각형이다 (좌표가 없어 반경 밖을 뺄 수 없다). 추천 칸(`recommendList`)은
    범위와 상관없어 넣지 않는다.

    Args:
        place: 역·대학·좌표 (반경 사각형).
        scope: 시·군·구 (경계 사각형).
        places: 동 (경계 사각형, '○가' 동이면 여럿).
    """
    notes: list[str] = []
    prefixes: list[str] = []
    bbox: DabangBboxModel | None = None
    if places:
        bbox = dongs_bbox(client, places)
        prefixes = [part.address or part.name for part in places]
        scope_name = '·'.join(part.name for part in places) + ' 안'
    elif scope is not None:
        bbox = scope_bbox(client, scope)
        prefixes = [scope.name]
        scope_name = f'{scope.name} 안'
        if bbox is None:
            if scope.lat is None or scope.lng is None:
                raise JibsaError(
                    code='REGION_NOT_SUPPORTED',
                    message=f'다방에서 {scope.name} 경계를 받지 못했습니다',
                    hint='동 이름이나 역 이름으로 찾으세요',
                )
            # 경계가 없으면 중심 5km 사각형으로 받고 주소로 거른다
            bbox = bbox_of(*box_around(scope.lat, scope.lng, 5.0))
            notes.append(note('범위', f'{scope.name} 경계를 받지 못해 중심 5km 사각형에서 주소로 골랐습니다'))
    else:
        assert place is not None  # CLI 가 셋 중 하나를 준다
        radius = radius_km or DEFAULT_RADIUS_KM
        bbox = bbox_of(*box_around(place.lat, place.lng, radius))
        scope_name = f'{place.name} 반경 {radius:g}km (사각형)'
    filters = DabangSaleInLotsFiltersModel(
        building_type_list=[SALE_BUILDING_TYPE_BY_LABEL[label] for label in building_types or []] or list(ALL_SALE_BUILDING_TYPES),
        state_list=[SALE_STATE_BY_LABEL[label] for label in states or []] or list(ALL_SALE_STATES),
        supply_type_list=[SALE_SUPPLY_BY_LABEL[label] for label in supply_types or []] or list(ALL_SALE_SUPPLY_TYPES),
    )
    sales: list[DabangSaleSummary] = []
    received = outside = 0
    total: int | None = None
    has_more = False
    for page in range(1, MAX_LIST_PAGES + 1):
        result = client.run_request_sale_list_category_bbox_v5(
            DabangSaleListCategoryBboxV5RequestParameterModel(filters=filters, bbox=bbox, page=page)
        ).result
        if result is None:
            break
        total = result.total if total is None else total
        rows = result.sale_list[:limit - received]
        for item in rows:
            received += 1
            address = normalize_address(item.address) or ''
            if prefixes and not any(address == prefix or address.startswith(f'{prefix} ') for prefix in prefixes):
                outside += 1
                continue
            sales.append(_summary(item))
        has_more = len(rows) < len(result.sale_list) or bool(result.has_more)
        if received >= limit or not result.has_more or len(result.sale_list) < PAGE_SIZE:
            break
    if outside:
        notes.append(note('제외', f'경계를 덮는 사각형에서 받은 단지 중 주소가 다른 {outside}곳을 뺐습니다 (뺀 만큼 다시 채우지 않음)'))
    if has_more and received >= limit:
        among = f' 약 {total}곳 중' if total is not None else ''
        notes.append(note('일부', f'범위 사각형 안 분양 단지{among} 다방 목록 순 앞 {received}곳을 봤습니다. 더 보려면 --limit 을 늘리세요'))
    return DabangSaleListResult(scope=scope_name, total=total, returned=len(sales), has_more=has_more, sales=sales, notes=notes)


class DabangSaleStep(BaseModel):
    """분양 일정 한 단계."""

    model_config = ConfigDict(
        extra='forbid',
    )

    step: Annotated[
        str,
        Field(description="단계 ('모집공고', '특별공급', '1순위 청약', '2순위 청약', '당첨자발표', '계약기간', '입주예정일')")
    ]
    start: Annotated[
        str | None,
        Field(description='시작 (YYYY-MM-DD, 달만 알면 YYYY-MM)')
    ] = None
    # 다방은 한 시점인 단계에만 끝을 주지 않는다. 하루짜리 청약은 끝이 시작과 같은 날로 온다 (2026-10-28 실측: 분양 3곳
    # 모두 모집공고·당첨자발표·입주예정일만 끝이 없음). 끝이 해당 없는 단계라 null(모름) 대신 키를 뺀다
    end: Annotated[
        str | None,
        Field(exclude_if=lambda value: value is None, description='끝 (하루짜리는 시작과 같은 날. 모집공고·당첨자발표·입주예정일처럼 한 시점인 단계는 키 없음)')
    ] = None


class DabangSalePyeong(BaseModel):
    """분양 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="평형 ('55A')")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='분양가 (만원, 대표값)')
    ] = None


class DabangSaleDetail(BaseModel):
    """분양 단지 정보. 상담 전화·사진·좌표는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sale_id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    state: Annotated[
        str | None,
        Field(description='분양 상태')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    sale_household_count: Annotated[
        int | None,
        Field(description='분양 세대수')
    ] = None
    building_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    floors: Annotated[
        int | None,
        Field(description='지상 층수')
    ] = None
    basement_floors: Annotated[
        int | None,
        Field(description='지하 층수')
    ] = None
    builder: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    developer: Annotated[
        str | None,
        Field(description='시행사')
    ] = None
    price_min_manwon: Annotated[
        float | None,
        Field(description='분양가 최저 (만원)')
    ] = None
    price_max_manwon: Annotated[
        float | None,
        Field(description='분양가 최고 (만원)')
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당 분양가 (만원)')
    ] = None
    move_in: Annotated[
        str | None,
        Field(description='입주 예정 (YYYY-MM)')
    ] = None
    regulation_area: Annotated[
        str | None,
        Field(description='규제 지역. 모르면 null')
    ] = None
    price_cap: Annotated[
        bool | None,
        Field(description='분양가 상한제. 모르면 null')
    ] = None
    resalable: Annotated[
        bool | None,
        Field(description='전매 가능. 모르면 null')
    ] = None
    schedules: Annotated[
        list[DabangSaleStep],
        Field(description='일정 (모집공고부터 입주까지)')
    ]
    pyeongs: Annotated[
        list[DabangSalePyeong],
        Field(description='평형별 분양가·세대수')
    ]
    notice_url: Annotated[
        str | None,
        Field(description='입주자 모집공고 파일 주소')
    ] = None
    applyhome_url: Annotated[
        str | None,
        Field(description='청약홈 주소')
    ] = None
    url: Annotated[
        str,
        Field(description='분양 페이지 URL')
    ]


def get_sale(client: DabangClient, sale_id: str) -> DabangSaleDetail:
    """분양 단지 하나 (요청 1회).

    Raises:
        JibsaError: 없는 분양 ID (NOT_FOUND).
    """
    try:
        response = client.run_request_sale_in_lots_detail2_v3(DabangSaleInLotsDetail2V3RequestParameterModel(id=sale_id))
    except HTTPStatusError as exc:
        # 분양 ID 는 쿼리로 간다. 없는 ID 는 400 '존재하지 않는 분양정보입니다.' (2026-10-27 실측)
        if is_missing_id(exc, in_path=False):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방 분양 단지를 찾지 못했습니다: {sale_id}',
                hint='jibsa dabang search sales 나 search locations 결과의 sale_id 를 그대로 주세요',
            ) from None
        raise
    info = response.sale_in_lots
    # '12억9990 ~ 22억7680' (2026-10-26 실측 19곳 모두 이 꼴). '~' 가 없으면 한 가격이라 최고가도 같고, 있는데 뒤를 못 읽으면
    # 최고가를 모르는 것이라 null 로 둔다 (최저가로 채우면 범위가 정해진 것처럼 보인다)
    low, separator, high = ((info.price_info.price_str if info.price_info else None) or '').partition('~')
    return DabangSaleDetail(
        sale_id=info.id,
        name=info.building_name,
        state=info.state_str,
        building_type=info.building_types_str,
        supply_type=info.supply_type_str,
        address=normalize_address(info.jibun_address or info.address),
        road_address=normalize_address(info.road_address),
        household_count=info.total_household_num,
        sale_household_count=info.lots_household_num,
        building_count=info.dong_count,
        floors=info.ground_floor,
        basement_floors=info.underground_floor,
        builder=info.provider_name,
        developer=info.constructor_name,
        price_min_manwon=manwon_from_text(low),
        price_max_manwon=manwon_from_text(high if separator else low),
        price_per_pyeong_manwon=manwon_from_text(info.price_info.pyeong_price) if info.price_info else None,
        move_in=sale_date(info.moving_date_str),
        regulation_area=info.regulation_area_str,
        price_cap=info.is_price_cap,
        resalable=info.is_resalable,
        schedules=[
            DabangSaleStep(step=step.type_str or '', start=sale_date(step.from_str), end=sale_date(step.to_str))
            for step in response.schedules
        ],
        pyeongs=[
            DabangSalePyeong(
                name=space.space_name,
                area_m2=space.exclusive_space,
                supply_area_m2=space.supply_space,
                household_count=space.household_num,
                price_manwon=manwon_from_text(space.price_str),
            )
            for space in response.spaces
        ],
        notice_url=info.notice_url,
        applyhome_url=info.applyhome_link,
        url=sale_url(info.id),
    )


class DabangSaleScheduleItem(BaseModel):
    """청약 일정 한 줄."""

    model_config = ConfigDict(
        extra='forbid',
    )

    date: Annotated[
        str,
        Field(description='날 (YYYY-MM-DD)')
    ]
    kind: Annotated[
        str | None,
        Field(description="종류 ('접수', '당첨자발표' 등 다방 표시)")
    ] = None
    region: Annotated[
        str | None,
        Field(description="일정 글의 시·도 ('서울', '경기'). 글이 시·도 없이 시나 단지 이름으로 시작하면 null")
    ] = None
    text: Annotated[
        str,
        Field(description="일정 글 ('[청약접수] 인천 … (~10/27)')")
    ]
    sale_id: Annotated[
        str | None,
        Field(description='분양 ID')
    ] = None


class DabangSaleSchedule(BaseModel):
    """날짜별 청약 일정."""

    model_config = ConfigDict(
        extra='forbid',
    )

    from_date: Annotated[
        str,
        Field(description='시작 날')
    ]
    to_date: Annotated[
        str,
        Field(description='끝 날')
    ]
    total: Annotated[
        int,
        Field(description='기간 안 일정 수 (--region 으로 거르기 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 일정 수')
    ]
    schedules: Annotated[
        list[DabangSaleScheduleItem],
        Field(description='날짜 순 일정')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부·거르기 안내')
    ] = []


def get_sale_schedule(
    client: DabangClient, *, start: date, days: int, region: str | None = None, limit: int,
) -> DabangSaleSchedule:
    """`start` 부터 `days` 일(최대 7일)의 청약 일정 (요청 1회). `region` 을 주면 일정 글의 시·도로 jibsa 가 거른다.

    Raises:
        JibsaError: `region` 이 시·도 이름이 아닐 때 (INVALID_ARGUMENT).
    """
    wanted = state_name(region.strip()) if region else None
    if region and wanted is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"--region 은 시·도 이름이어야 합니다: '{region}'",
            hint='서울·경기·충북처럼 줄임말이나 충청북도 같은 정식 이름을 주세요. 시·군·구로는 거르지 못합니다',
        )
    end = start + timedelta(days=days - 1)
    result = client.run_request_sale_in_lots_list_schedule_v3(
        DabangSaleInLotsListScheduleV3RequestParameterModel(from_date=start, to_date=end)
    ).root
    items: list[DabangSaleScheduleItem] = []
    total = 0
    unknown = 0
    for day in result:
        for group in day.schedule_by_type:
            kind = (group.type_title or '').split(' ')[0] or None
            for entry in group.schedules:
                total += 1
                text = entry.schedule_str or ''
                match = SCHEDULE_REGION_PATTERN.match(text)
                # 글은 '[청약접수] 인천 …' 처럼 시·도 줄임말로 시작하지만 시·도 없이 시나 단지 이름으로 시작하기도 한다
                # (2026-10-25 실측 7일 83건 중 '익산 부송에코르'·'한양립스 에듀포레', 태그가 둘인 '[계약기간]  [무순위] 올 뉴
                # 챔피언스시티'). 칸에는 좌표뿐이라 시·도가 아니면 모름(None)으로 둔다. '광주시' 로 시작하면 경기도 광주시라
                # 다른 시('익산')처럼 모름이다 (`state_name`)
                where = match.group(1) if match and state_name(match.group(1)) else None
                if wanted is not None and (where is None or state_name(where) != wanted):
                    unknown += where is None
                    continue
                items.append(DabangSaleScheduleItem(date=day.date, kind=kind, region=where, text=text, sale_id=entry.id))
    notes: list[str] = []
    if region:
        notes.append(note('참고', f"일정 글의 시·도가 '{region}' 인 것만 남겼습니다 ({total}건 중 {len(items)}건)"))
    if unknown:
        notes.append(note('제외', f'일정 글에 시·도가 없어 지역을 모르는 {unknown}건을 뺐습니다 (--region 없이 부르면 나옵니다)'))
    if len(items) > limit:
        notes.append(note('일부', f'일정 {len(items)}건 중 앞 {limit}건입니다. 더 보려면 --limit 을 늘리거나 --days 를 줄이세요'))
    return DabangSaleSchedule(
        from_date=start.isoformat(), to_date=end.isoformat(), total=total, returned=min(len(items), limit),
        schedules=items[:limit], notes=notes,
    )
