"""단지 정보·단지 매물 (complex, search listings --complex)."""

from math import inf

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    Listing,
    join_address,
    m2_to_pyeong,
    normalize_address,
    note,
    null_items_note,
    number_range,
    read_date,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    is_empty_property_filter,
)
from jibsa.providers.daangn.api.request.complex.detail import (
    DaangnComplexArticlesInputModel,
    DaangnComplexArticlesRequestPayloadModel,
    DaangnComplexesRequestParameterModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.api.response.complex.detail import (
    DaangnAreaGroupModel,
    DaangnComplexModel,
    DaangnNearbySchoolModel,
    DaangnProptierDanjiModel,
)
from jibsa.providers.daangn.service.common.functions import (
    COMPLEX_LISTING_DEFAULT_SALES_TYPES,
    COMPLEX_TYPE_LABELS,
    LISTING_MAX_LIMIT,
    article_to_listing,
    code_label,
    complex_building_notes,
    complex_not_found,
    complex_url,
    cursor_stopped_note,
    is_available,
    listing_budget_notes,
    next_cursor,
    no_trade_notes,
    stalled_page,
    station_name,
    trade_of,
    unwrap_graphql,
    uses_supply_pyeong,
    web_minutes,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnListingConditions,
)
from jibsa.providers.daangn.service.complex.models import (
    DaangnComplex,
    DaangnComplexListingsResult,
    DaangnPyeong,
)
from jibsa.providers.daangn.service.region.functions import (
    with_sido,
)


# 단지 정보의 중·고등학교는 학군 전체(수십 곳)가 와서, 당근 웹 학군 카드처럼 `_web_school_card` 규칙으로 남긴 앞 몇 곳만
# 보여 준다 (ComplexSchoolSection `slice(0,2)`)
NEAREST_SCHOOLS: int = 2


# 단지 매물 목록은 20건씩 최대 6페이지. 제외된 만큼 추가 조회하지 않는다
COMPLEX_LISTINGS_PAGE_SIZE: int = 20



COMPLEX_LISTINGS_MAX_PAGES: int = 6



def _school_walk(item: DaangnNearbySchoolModel, assigned: bool) -> float | None:
    """웹이 쓰는 도보 시간. 배정 학교는 walkingTimeMin 이 없으면 길찾기 시간(workingTime)이다 (ComplexSchoolSection `Re`)."""
    return item.walking_time_min if item.walking_time_min is not None or not assigned else item.working_time



def _school_distance(item: DaangnNearbySchoolModel, assigned: bool) -> float | None:
    """웹이 쓰는 도보 거리. 배정 학교는 walkingDistanceMeters 가 없으면 직선거리(distance)다 (ComplexSchoolSection `Re`)."""
    return item.walking_distance_m if item.walking_distance_m is not None or not assigned else item.distance



def _or_inf(value: float | None) -> float:
    """모르는 값(None)을 맨 뒤로 보내는 정렬 키. 0 은 그대로 둔다 (웹 `R` 의 `?? 2**53-1`)."""
    return inf if value is None else value



def _resident_count(item: DaangnNearbySchoolModel) -> int:
    return (item.school.resident_count if item.school else None) or 0



def _web_school_order(items: list[DaangnNearbySchoolModel], assigned: bool) -> list[DaangnNearbySchoolModel]:
    """당근 웹 단지 학군 순서 (ComplexSchoolSection `W`): 이 단지 주민이 많이 다니는 곳, 같으면 도보 시간·거리 순 (모르면 뒤)."""
    def key(item: DaangnNearbySchoolModel) -> tuple[int, bool, float, bool, float]:
        walk = _school_walk(item, assigned)
        distance = _school_distance(item, assigned)
        return (-_resident_count(item), walk is None, walk or 0, distance is None, distance or 0)
    return sorted(items, key=key)



def _web_school_card(items: list[DaangnNearbySchoolModel]) -> list[DaangnNearbySchoolModel]:
    """당근 웹 단지 학군 카드에 보이는 중·고등학교 (ComplexSchoolSection `Ve(list).slice(0,2)`).

    웹 순서로 세운 뒤 도보 20분 안 학교(없으면 도보 시간·거리 순으로 가장 가까운 한 곳. 둘 다 모르면 첫 학교), 이 단지 주민이
    다니는 학교, 학교가 5곳 이하면 자동 배정에 도보 40분 안 학교만 남겨 앞 `NEAREST_SCHOOLS` 곳이다. 분은 웹처럼 반올림해 견준다
    (`He`·`Ue` 의 `Math.round`). 예전에는 도보 가까운 2곳이라 주민이 많이 다니는 먼 학교나 20분 안에 학교가 없는 단지에서 웹과
    달랐다 (#215, 2026-11-12 번들 대조).
    """
    ordered = _web_school_order(items, assigned=False)
    walks = {id(item): _school_walk(item, False) for item in ordered}
    near = {id(item) for item in ordered if (walk := walks[id(item)]) is not None and web_minutes(walk) <= 20}
    if not near and ordered:
        # 웹 `[...e].sort(G).slice(0,1)`: 시간, 같으면 거리 순 (모르면 뒤). 모두 모르면 안정 정렬이라 첫 학교. 웹 비교(`R`)는
        # `e ?? 2**53-1` 이라 0 분·0 m 도 값이다. `or inf` 로 두면 거리 0 이 '모름' 이 됐다 (2026-11-12 리뷰, 웹 배포 2026-11-v73 번들 대조)
        nearest = min(ordered, key=lambda item: (_or_inf(walks[id(item)]), _or_inf(_school_distance(item, False))))
        near = {id(nearest)}
    kept = [
        item for item in ordered
        if id(item) in near
        or _resident_count(item) > 0
        or (
            len(items) <= 5 and item.allocation_method == '자동'
            and (walk := walks[id(item)]) is not None and web_minutes(walk) <= 40
        )
    ]
    return kept[:NEAREST_SCHOOLS]



def _school(item: DaangnNearbySchoolModel, assigned: bool = False) -> str | None:
    if item.school is None or not item.school.name:
        return None
    details = ['배정'] if assigned else []
    walk = _school_walk(item, assigned)
    if walk is not None:
        details.append(f'도보 {web_minutes(walk)}분')
    if _resident_count(item) > 0:
        details.append(f'이 단지 {_resident_count(item)}명 이상')
    return f'{item.school.name} ({", ".join(details)})' if details else item.school.name



def _pyeong_groups(complex_type: str | None, danji: DaangnProptierDanjiModel) -> tuple[bool, list[DaangnAreaGroupModel]]:
    """단지 평형을 묶는 평형 묶음과, 그것이 공급 평 묶음인지 (`complex_pyeongs`)."""
    supply = uses_supply_pyeong(complex_type, danji.supply_pyeong_area_groups)
    return supply, danji.supply_pyeong_area_groups if supply else danji.area_groups



def complex_pyeongs(complex_type: str | None, danji: DaangnProptierDanjiModel) -> list[DaangnPyeong]:
    """단지 평형 목록. 당근 웹처럼 아파트형 단지는 공급 평 묶음으로, 그 밖은 전용면적 묶음으로 묶는다 (utils `n()`).

    공급 평 묶음의 평형은 같은 타입 코드(ptpCd)가 든 전용면적 묶음도 함께 적는다 (어느 전용면적 묶음의 평형인지 보이게).
    `--area` 는 아파트형이 아닌 단지만 받아(`choose_pyeong`) 아파트형은 `pyeong` 으로 고른다 (2026-11-12 실측: 헬리오시티
    real-price·price-trend --area 84 는 INVALID_ARGUMENT). 예전에는 늘 전용면적 묶음이라 헬리오시티 84㎡ 묶음에 32평·33평이
    섞였다 (#215, 2026-11-12 실측).
    """
    exclusive_by_code = {
        info.ptp_cd: group.label for group in danji.area_groups for info in group.py_infos if info.ptp_cd is not None
    }
    supply, groups = _pyeong_groups(complex_type, danji)
    return [
        DaangnPyeong(
            area_m2=info.exclusive_area,
            area_pyeong=m2_to_pyeong(info.exclusive_area),
            supply_area_m2=info.supply_area,
            supply_area_pyeong=m2_to_pyeong(info.supply_area),
            room_count=info.room_count,
            bathroom_count=info.bathroom_count,
            # 평형에서 빈 항목을 뺐으면 묶음의 평형이 하나였는지 알 수 없어 세대수도 모른다 (null)
            household_count=group.total_count if len(group.py_infos) == 1 and not group.null_items('py_infos') else None,
            pyeong=group.label if supply else None,
            representative=bool(group.is_representative),
            area_group=(exclusive_by_code.get(info.ptp_cd) if info.ptp_cd is not None else None) if supply else group.label,
        )
        for group in groups
        for info in group.py_infos
    ]



def complex_to_summary(complex_: DaangnComplexModel) -> DaangnComplex:
    """단지 페이지 레코드를 `DaangnComplex` 로 바꾼다.

    후기는 본문을 옮기지 않고 수만 담는다. 후기가 있으면 원 사이트에서 보라는 안내를 `notes` 로 붙인다.
    """
    danji = complex_.proptier_danji
    address = danji.addresses[0] if danji and danji.addresses else None
    region = complex_.region
    pyeongs = complex_pyeongs(complex_.type, danji) if danji else []
    schools = []
    if danji:
        schools = [_school(item, assigned=True) for item in _web_school_order(danji.assigned_schools, assigned=True)]
        schools += [_school(item) for item in _web_school_card(danji.middle_schools)]
        schools += [_school(item) for item in _web_school_card(danji.high_schools)]
    review_count = complex_.lived_review_count
    url = complex_url(complex_.original_id)
    notes = [
        f'이 단지에 거주 후기 {review_count}개가 있습니다. 후기 내용은 당근 단지 페이지({url})에서 확인하세요'
    ] if review_count else []
    # 평형이 하나뿐인 묶음에서 빈 항목을 빼고 읽었으면 그 묶음의 세대수를 모른다 (`complex_pyeongs`)
    dropped = sum(
        group.null_items('py_infos') for group in _pyeong_groups(complex_.type, danji)[1] if len(group.py_infos) == 1
    ) if danji else 0
    if dropped:
        notes.append(null_items_note('당근 단지 평형', dropped, ('pyeongs 의 household_count',)))
    # 당근 웹 단지 화면 '가까운 역' 순서 (`Ye`): 도보 시간이 짧은 순 (모르면 뒤). 같으면 서버 순서를 지킨다 (안정 정렬).
    # 웹은 같을 때 거리도 견주지만 jibsa 가 받는 단지 응답의 역(`DaangnSubwayInfoModel`)에는 거리 칸이 없다. 웹과 달리 같은 이름 역을 합치거나
    # 앞 2곳으로 자르지 않고 (역, 노선)마다 모두 낸다.
    nearby_stations: list[str] | None = None
    if danji:
        nearby_stations = []
        for subway_item in sorted(danji.subways, key=lambda subway: _or_inf(subway.walking_time_min)):
            if not subway_item.station_name:
                continue
            details = [subway_item.line_name] if subway_item.line_name else []
            if subway_item.walking_time_min is not None:
                details.append(f'도보 {web_minutes(subway_item.walking_time_min)}분')
            name = station_name(subway_item.station_name)
            nearby_stations.append(f'{name} ({", ".join(details)})' if details else name)
    return DaangnComplex(
        complex_id=complex_.original_id,
        name=complex_.name,
        complex_type=code_label(COMPLEX_TYPE_LABELS, complex_.type),
        address=normalize_address(
            address.jibun_address if address and address.jibun_address
            else join_address(region.name1, region.name2, region.name3) if region else None
        ),
        road_address=normalize_address(address.road_address if address else None),
        household_count=danji.households if danji and danji.households is not None else complex_.households,
        dong_count=danji.dong_count if danji and danji.dong_count is not None else complex_.building_count,
        approved_date=read_date(complex_.approval_date, '사용승인일'),
        building_floor_range=number_range(danji.min_floor, danji.max_floor) if danji else None,
        construction_company=danji.constructor_name if danji else None,
        parking_count=danji.parking_count if danji else None,
        parking_per_household=danji.parking_per_household if danji else None,
        # 값이 없는 방식·연료는 모름(null)이다 (빈 글자도 같다)
        heating=(danji.heating_method or None) if danji else None,
        heating_fuel=(danji.heating_fuel or None) if danji else None,
        floor_area_ratio_percent=danji.floor_area_ratio if danji else None,
        building_coverage_ratio_percent=danji.building_coverage_ratio if danji else None,
        listing_count=complex_.live_article_count.total if complex_.live_article_count else None,
        # 단지 공공 정보가 없으면 평형·역·학교는 모른다 (null). 2026-10-10 실측: 아파트·오피스텔·주상복합·도시형 13곳 모두 있었다
        pyeongs=sorted(pyeongs, key=lambda pyeong: pyeong.area_m2 or 0) if danji else None,
        nearby_stations=nearby_stations,
        schools=[school for school in schools if school] if danji else None,
        review_count=review_count,
        url=url,
        notes=notes,
    )



def get_complex(client: DaangnClient, complex_id: int) -> DaangnComplex:
    """단지 정보를 조회한다 (단지 페이지 1회).

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND.
    """
    try:
        response = client.run_request_complexes(DaangnComplexesRequestParameterModel(original_id=complex_id))
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise complex_not_found(complex_id) from None
        raise
    if response.complex is None:
        raise complex_not_found(complex_id)
    return complex_to_summary(response.complex)



def list_complex_listings(
    client: DaangnClient,
    complex_id: int,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
) -> DaangnComplexListingsResult:
    """단지 하나의 현재 매물을 모은다 (당근 단지 화면의 매물 탭). 조건은 search listings 와 같고 서버에서 건다.

    거래 완료·숨김 매물은 빼고, 거래 조건이 여럿이면 조건에 맞는 거래로 가격을 보여 준다 (search 와 같다).
    단지 매물이라 세대수·주차대수 조건은 받지 않는다.

    Raises:
        JibsaError: 세대수·주차대수 조건을 주면 INVALID_ARGUMENT, 없는 단지면 NOT_FOUND, 그 밖의 GraphQL 에러면
            UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 단지 매물 쿼리를 바꿨을 때.
    """
    conditions = conditions or DaangnListingConditions()
    if conditions.household_min is not None or conditions.household_max is not None or conditions.parking_min is not None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='단지 매물에는 세대수·주차대수 조건을 쓸 수 없습니다',
            hint='단지 하나의 매물이라 세대수·주차대수는 이미 정해져 있습니다. 그 조건을 빼고 다시 찾으세요',
        )
    property_filter = conditions.property_filter
    filtered = not is_empty_property_filter(property_filter)  # 사용자 조건 없음 (아래에서 기본 종류를 채우기 전 값)
    if not conditions.property_types:
        # 웹 단지 매물 패널은 종류를 고르지 않으면 늘 주거 5종(아파트·주택·오피스텔·원룸·투룸)을 보낸다 (`ComplexArticleListPanel`
        # 의 `F`, 단지 페이지 SEO 본문도 같다). 빈 목록(전체)으로 부르는 경로가 없어 상가·사무실 등은 -t 로 골랐을 때만 온다
        # (2026-11-12 번들 대조. 예전에는 전체를 보내 상가 매물이 섞였다)
        property_filter = property_filter.model_copy(update={'sales_types': list(COMPLEX_LISTING_DEFAULT_SALES_TYPES)})
    matched: list[tuple[DaangnArticleModel, DaangnTradeModel]] = []
    after = None
    inspected = 0
    seen: set[str] = set()
    # 받은 서로 다른 매물 (거래 불가도 센다). 멈춤 안내의 수다. inspected 는 edge 누계라 같은 쪽이 되풀이되면 두 번 센다
    # (2026-11-10 리뷰. 출퇴근 역 목록도 이름으로 센다)
    received_ids: set[str] = set()
    received: list[DaangnArticleModel] = []
    # 서버는 빈 edge(null)도 한 자리로 세므로 빼고 읽은 수를 받은 자리에 더한다
    null_edges = 0
    has_more = False
    stopped = False
    page_capped = False
    for _ in range(COMPLEX_LISTINGS_MAX_PAGES):
        response = client.run_request_complex_articles(
            DaangnComplexArticlesRequestPayloadModel(
                complex_id=str(complex_id),
                first=min(COMPLEX_LISTINGS_PAGE_SIZE, limit - inspected),
                after=after,
                input=DaangnComplexArticlesInputModel(property_filter=property_filter),
            )
        )
        result = unwrap_graphql(
            response, response.data.complex_by_original_id if response.data else None, '단지 매물', conditions=filtered
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        connection = result.complex.articles
        # 단지의 매물 목록(articles) 자체가 null 이어도 페이지 정보가 없는 것이라 앞 쪽이 다음이 있다고 했으면 멈춘다 (stalled_page)
        if stalled_page(connection.page_info if connection else None, after):
            stopped = True
            break
        if connection:
            null_edges += connection.null_items('edges')
            inspected += len(connection.edges) + connection.null_items('edges')
        articles = [edge.node for edge in connection.edges if edge.node] if connection else []
        received_ids.update(article.original_id for article in articles)
        received += articles
        for article in articles:
            if article.original_id in seen or not is_available(article):
                continue
            seen.add(article.original_id)
            trade = trade_of(article, conditions)
            if trade is not None:
                matched.append((article, trade))
        page_info = connection.page_info if connection else None
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page_info and page_info.has_next_page) or len(matched) > limit
        if inspected >= limit or not has_more or page_info is None:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 을 늘려도 더 받지 못하니
        # 아래의 --limit 안내 대신 멈췄다고 알린다 (2026-11-10 리뷰: 같은 커서를 되풀이하면 같은 쪽을 6번 받고 '--limit 의
        # 최대값은 120입니다' 라고 했고, 커서가 비면 안내 없이 has_more 만 true 였다). 마지막 허용 쪽(6쪽)에서도 본다. 다음이
        # 있다면서 커서를 주지 않는 것은 몇 쪽째든 응답이 바뀐 것이라 멈춤 안내(업데이트 문구)가 맞다. 서버가 쪽마다 first 만큼
        # 주면(COMPLEX_PAGE_SIZE 주석) 6쪽째에 inspected 가 --limit 최대 120 에 닿아 위에서 먼저 끝난다. 하지만 서버가 first 보다 적게
        # 주면 쪽 상한(for 가 break 없이 끝남)에 먼저 닿아 inspected < limit 이고 has_more 인 채 끝나, 아래 '더 있음' 안내의
        # 조건(limit >= max_limit 또는 inspected >= limit)이 거짓이라 안내 없이 has_more 만 true 였다. 그래서 쪽 상한은
        # `stopped` 와 같은 갈래로 보아 따로 알린다 (`page_capped`. 2026-11-10 리뷰의 6쪽째 멈춤 지적은 first 만큼 줄 때만 오탐이었다)
        cursor = next_cursor(page_info, after, received=len(articles))
        if cursor is None:
            stopped = True
            break
        after = cursor
    else:
        # break 없이 끝났으면 쪽 상한에 닿은 것이다. 닿기 전 끝 조건(--limit 만큼 받음·다음 없음·pageInfo 없음)은 모두 break 다
        page_capped = True

    # 카드에는 시·도가 없어 단지가 있는 동을 지역 검색으로 한 번 채운다 (with_sido)
    sido_cache: dict[tuple[str, str], str | None] = {}
    listings: list[Listing] = []
    shown: list[DaangnArticleModel] = []
    for article, trade in matched[:limit]:
        listing = article_to_listing(with_sido(client, article, sido_cache), trade=trade)
        if listing is not None:
            listings.append(listing)
            shown.append(article)
    return DaangnComplexListingsResult(
        complex_id=str(complex_id),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        url=complex_url(complex_id),
        notes=listing_budget_notes(
            limit, inspected, len(listings), max_limit=LISTING_MAX_LIMIT, has_more=has_more, narrow='조건',
            eligible=len(matched), narrowable=not (stopped or page_capped), dropped=null_edges,
        )
            + no_trade_notes(received)
            + (
                [note('일부', cursor_stopped_note('단지 매물', f'{len(received_ids)}건') + '. 나머지는 url 의 단지 페이지에서 확인하세요')]
                if stopped else []
            )
            + (
                [note(
                    '일부',
                    f'단지 매물 {len(received_ids)}건을 받고 쪽 수 상한({COMPLEX_LISTINGS_MAX_PAGES}쪽)에 닿아 멈췄습니다. '
                    '--limit 을 늘려도 더 받지 못합니다. 나머지는 url 의 단지 페이지에서 확인하세요',
                )]
                if page_capped else []
            )
            + complex_building_notes(shown)
            + ([null_items_note('당근 단지 매물', null_edges)] if null_edges else []),
    )
