"""네이버 목록 매물 한 건을 출력 칸으로 바꾸기 (확인 배지·층·확인일·중복 묶음 호가), 가격순·묶음 안내, 가격 조건."""

from collections.abc import Callable

from jibsa.core.dates import (
    holding_unread_dates,
    normalize_date,
    read_date,
)
from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    AmountRange,
    AmountSet,
    Listing,
    format_manwon,
    join_address,
    m2_to_pyeong,
    won_to_manwon,
)
from jibsa.core.notes import note
from jibsa.providers.naver.api.models.response.common import (
    NaverArticleListItemModel,
    NaverDuplicatedArticleInfoModel,
    NaverFacilityInfoModel,
    NaverListBuildingInfoModel,
)
from jibsa.providers.naver.service.common.constants import (
    ARTICLE_URL,
    HUG_SAFE_LESSOR_BADGE,
    NON_RESIDENTIAL_TYPES,
    NOT_APPLICABLE_FIELDS_BY_TYPE,
    OWNER_VERIFICATION_TYPES,
    PROPERTY_NAME_BY_CODE,
    SITE_VERIFICATION_TYPES,
    TRADE_CODE_BY_NAME,
    TRADE_NAME_BY_CODE,
    WON_PER_MANWON,
)
from jibsa.providers.naver.service.common.labels import dong_label
from jibsa.providers.naver.service.common.models import (
    NaverListing,
    NaverTradeConditions,
)

from typing import Any


def group_fields(group: NaverDuplicatedArticleInfoModel | None, trade_type: str) -> dict[str, Any]:
    """중복 묶음의 중개사 수와 거래 유형에 맞는 호가 범위 (`NaverListing`). 중개사가 하나뿐이면 비운다.

    금액 종류(매매 `price_manwon`, 전세 `deposit_manwon`, 월세·단기임대 `deposit_manwon`+`rent_manwon`)마다 두 끝을 만원으로 묶어
    `asking_range` 로 낸다. 두 끝이 같아도 그 종류를 버리지 않고 두 끝 모두 낸다 (월세는 보증금이 같고 월세만 다른 묶음이 있다).
    모든 종류의 두 끝이 같으면 호가가 모두 같은 묶음이라 `asking_range` 는 해당 없음(키 없음)이다.

    종류의 범위를 모르면(묶음의 호가 정보나 그 거래의 가격이 없거나 두 끝이 모두 null 이거나 한 끝은 0 이고 다른 끝은 null) 두 끝의 그 칸을
    null 로 낸다. 모든 종류를 모르면 `asking_range` 가 null 이고 그 이름을 `unknown_group_fields` 에 담는다. 보증금·매매가의 0 은 받은 그대로
    내고(보증금 0원 매물이 있다), 월세의 0 은 서버가 비운 값이라 그 끝을 null 로 읽는다(`_rent_amount` 와 같은 규칙). 한 끝만 null 이면 그 끝만
    null 이다.
    """
    if group is None or not group.realtor_count or group.realtor_count < 2:
        return {}
    prices = group.representative_price_info
    fields: dict[str, Any] = {'realtor_count': group.realtor_count}
    if trade_type == '매매':
        kinds = [('price_manwon', prices.deal_price if prices else None)]
    else:
        kinds = [('deposit_manwon', prices.warranty_price if prices else None)]
        if trade_type in ('월세', '단기임대'):
            kinds.append(('rent_manwon', prices.rent_price if prices else None))
    # 월세는 0원 매물이 없어 0 을 비운 값(None)으로 읽는다. 보증금·매매가의 0 은 받은 그대로다
    ends = {
        name: (
            (price.min_price or None, price.max_price or None) if name == 'rent_manwon' else (price.min_price, price.max_price)
        ) if price is not None else None
        for name, price in kinds
    }
    # 범위를 주지 않았거나 두 끝이 모두 null 이거나 한 끝은 0 이고 다른 끝은 null 이면 호가가 같다는 뜻이 아니라 모르는 것이라 null 로 낸다
    # (키를 빼면 '호가가 모두 같다' 로 읽힌다). 보증금·매매가의 (0, 0) 은 두 끝이 같은 값이라 모르는 것이 아니다. 한 끝만 null 이면 아는 끝을 버리지
    # 않고 그 끝만 null 이다 (재개발 호가 범위와 같다, 2026-11-24 리뷰). 한 끝이 0 이고 다른 끝이 수이면 0 을 그대로 낸다 (보증금 0원 매물이
    # 있다, 2026-11-25 리뷰)
    unknown = frozenset(
        name for name, end in ends.items()
        if end is None or (not end[0] and not end[1] and None in end)
    )
    if len(unknown) == len(kinds):
        fields['asking_range'] = None
        fields['unknown_group_fields'] = frozenset({'asking_range'})
        return fields
    if not unknown and all(end[0] == end[1] for end in ends.values() if end is not None):
        return fields
    lowest: dict[str, float | None] = {}
    highest: dict[str, float | None] = {}
    for name, end in ends.items():
        known = end is not None and name not in unknown
        lowest[name] = won_to_manwon(end[0]) if end is not None and known else None
        highest[name] = won_to_manwon(end[1]) if end is not None and known else None
    fields['asking_range'] = AmountRange(lowest=AmountSet(**lowest), highest=AmountSet(**highest))
    return fields


def listing_badges(
    verification_type: str | None,
    real_estate_type: str | None,
    is_safe_lessor_of_hug: bool | None,
) -> list[str] | None:
    """`verification_badges` 에 HUG 안심임대인 배지를 뒤에 붙인다. 목록과 상세가 함께 쓴다.

    웹은 '집주인'·'현장' 배지 옆에 'HUG 안심임대인' 배지를 따로 그린다. 방식 배지·HUG 배지가 모두 없으면 [] 이고, 방식 배지가 없는
    코드(전화·서류 확인 TEL·DOC 등, 무검증 NONE)여도 HUG 안심임대인이면 ['HUG 안심임대인'] 이라 비어 있지 않다고 집주인·현장 확인
    매물인 것은 아니다. 확인 배지를 모르면(None) HUG 가 true 여도 None 그대로 둔다 (확인 정보 없이 HUG 만 true 인 매물은 드물다).
    """
    badges = verification_badges(verification_type, real_estate_type)
    if badges is not None and is_safe_lessor_of_hug:
        return [*badges, HUG_SAFE_LESSOR_BADGE]
    return badges


def verification_badges(verification_type: str | None, real_estate_type: str | None) -> list[str] | None:
    """확인 방식 코드와 매물 유형 코드로 네이버 화면의 확인 배지를 만든다. 목록과 상세가 함께 쓴다.

    집주인(MOBL·OWNER·NDOC1)은 비주거 매물이면 '소유자', 현장(SITE·S_VR)은 '현장' 이다. 그 밖의 코드는 방식 배지가 없어
    []이고(전화·서류로 확인한 매물(TEL·DOC 등)과 무검증 매물(NONE)이 모두 [] 다), 확인 정보 자체가 없으면
    (코드가 없거나 빈 글자면) 모름이라 None 이다.
    """
    if not verification_type:
        return None
    if verification_type in OWNER_VERIFICATION_TYPES:
        return ['소유자' if real_estate_type in NON_RESIDENTIAL_TYPES else '집주인']
    if verification_type in SITE_VERIFICATION_TYPES:
        return ['현장']
    return []


def known_floor(value: str | None) -> str | None:
    """층 값. 층이 없다는 뜻으로 오는 '0'·'-'·빈 값은 모름(None)으로 둔다.

    건물 전체를 파는 재개발·단독 매물은 목록에서 해당 층·전체 층을 '0' 으로, 상세에서 '-' 로 준다
    (노량진6구역 매물: 목록 전체 층 '0', 상세 '-'/'-', 2026-10-10 확인).
    """
    return None if value in (None, '', '0', '-') else value


def building_approved_at(
    building: NaverListBuildingInfoModel | NaverFacilityInfoModel | None,
) -> str | None:
    """건물 날짜가 사용승인일(CDY01)이면 YYYY-MM-DD 로. 다른 종류 코드는 의미를 몰라 None.

    목록의 buildingInfo 와 상세의 facilityInfo 가 같은 필드를 준다. `naver complex` 의
    useApprovalDate 와 단지 7곳 모두 일치함을 확인했다 (2026-10-06). 다만 상세의 facilityInfo 는
    단지 매물(아파트·오피스텔·빌라 단지)이면 날짜가 비어 오고, 단지가 아닌 원룸·빌라(C01·C02)만
    채워 온다. 목록 buildingInfo 는 단지 매물도 채워 온다 (2026-10-09 확인).
    """
    if building is None or building.building_conjunction_date_type != 'CDY01':
        return None
    return normalize_date(building.building_conjunction_date)


def article_info_to_listing(
    item: NaverArticleListItemModel,
    center: tuple[float, float] | None = None,
) -> NaverListing | None:
    """목록 항목(대표 매물)을 `NaverListing` 으로 바꾼다. 원 → 만원 환산. 중복 묶음이면 중개사 수·호가 범위를 붙인다.

    모르는 거래 유형 코드면 None 이다. 어느 가격 필드가 맞는지 몰라 틀린 값을 내보내게 되므로
    목록에서 뺀다 (직방이 전세·월세·매매 밖의 매물을 빼는 것과 같다).
    """
    info = item.representative_article_info
    price = info.price_info
    trade_type = TRADE_NAME_BY_CODE.get(info.trade_type)
    if trade_type is None:
        return None
    # 목록 매물의 해당 층·전체 층. floorDetailInfo 가 있으면 그것만 본다.
    # floorDetailInfo 가 '0'/null 인데 floorInfo 가 '-1/3' 인 매물은 건물 전체를 파는 단독·다가구(C03)·상가건물(D04)이고,
    # floorInfo 는 해당 층/전체 층이 아니라 지하~지상 범위다 (봉천동 120건 중 7건, 상세도 층·전체 층 모두 null, 2026-10-11).
    # 그래서 floorInfo 로 대신 채우지 않는다.
    floor: str | None = None
    building_floor: str | None = None
    detail = info.article_detail
    if detail is not None:
        if detail.floor_detail_info is not None:
            floor = known_floor(detail.floor_detail_info.target_floor)
            building_floor = known_floor(detail.floor_detail_info.total_floor)
        elif detail.floor_info and '/' in detail.floor_info:
            target, total = detail.floor_info.split('/', 1)
            floor, building_floor = known_floor(target), known_floor(total)
        else:
            floor = known_floor(detail.floor_info)

    lat = lng = None
    address = None
    if info.address is not None:
        # 목록 응답에는 번지가 없어 동까지만 나온다. 번지는 article/key 를 매물마다 더
        # 불러야 해서(네이버 차단 위험) 목록에서는 채우지 않고 item 에서만 준다.
        address = join_address(info.address.city, info.address.division, info.address.sector)
        if info.address.coordinates is not None:
            lat = info.address.coordinates.y_coordinate
            lng = info.address.coordinates.x_coordinate
    distance = None
    if center is not None and lat is not None and lng is not None:
        distance = round(haversine_km(center[0], center[1], lat, lng), 2)

    name = info.complex_name or info.article_name
    if name and info.dong_name:
        name = f'{name} {dong_label(info.dong_name)}'
    feature = info.article_detail.article_feature_description if info.article_detail else None
    title = ' · '.join(part for part in (name, feature) if part) or None

    # 재개발(F01)처럼 건물 면적이 없는 매물은 전용면적을 0 으로 준다 (대지지분만 있음, 2026-10-10 확인). 모름으로 둔다
    exclusive = (info.space_info.exclusive_space or None) if info.space_info else None
    return NaverListing(
        source='naver',
        id=info.article_number,
        url=ARTICLE_URL.format(info.article_number),
        trade_type=trade_type,
        property_type=PROPERTY_NAME_BY_CODE.get(info.real_estate_type, info.real_estate_type),
        title=title,
        price_manwon=won_to_manwon(price.deal_price) if price and trade_type == '매매' else None,
        deposit_manwon=won_to_manwon(price.warranty_price) if price and trade_type != '매매' else None,
        rent_manwon=won_to_manwon(price.rent_price) if price and trade_type in ('월세', '단기임대') else None,
        # 목록은 관리비를 입력하지 않은 매물도 0으로 준다 (0원 3건 중 2건이 상세 관리비 정보 없음, 2026-10-09 확인).
        # 0원과 미입력을 구분할 수 없어 모름(null)으로 두고, 상세(관리비 API)에서 구분한다
        manage_cost_manwon=won_to_manwon(price.management_fee_amount) if price and price.management_fee_amount else None,
        area_m2=exclusive,
        area_pyeong=m2_to_pyeong(exclusive),
        floor=floor,
        building_floor=building_floor,
        address=address,
        lat=lat,
        lng=lng,
        distance_km=distance,
        registered_date=read_date(info.verification_info.exposure_start_date, '등록일') if info.verification_info else None,
        # 토지·고시원처럼 사용승인일 칸이 없는 유형(출력에서 키를 뺀다)은 읽지 않는다. 읽으면 출력에 없는 칸을 [참고] 로 알린다 (상세와 같다)
        approved_date=(
            None if 'approved_date' in NOT_APPLICABLE_FIELDS_BY_TYPE.get(info.real_estate_type or '', frozenset())
            else read_date(building_approved_at(info.building_info), '사용승인일')
        ),
        badges=listing_badges(
            info.verification_info.verification_type if info.verification_info else None,
            info.real_estate_type,
            info.article_detail.is_safe_lessor_of_hug if info.article_detail else None,
        ),
        confirmed_date=read_date(info.verification_info.article_confirm_date, '매물 확인일') if info.verification_info else None,
        real_estate_type=info.real_estate_type,
        **group_fields(item.duplicated_article_info, trade_type),
    )


def listing_keeper(
    listings: dict[str, Listing],
    center: tuple[float, float] | None,
    radius_km: float | None = None,
    *,
    held: dict[str, list[tuple[str, str]]],
) -> Callable[[NaverArticleListItemModel], str]:
    """`scan_pages` 의 `keep`. 매물로 바꿔 (반경 안이면) 담고, 매물 번호를 돌려준다.

    검색 조건은 서버가 걸었으므로 다시 거르지 않는다 (provider-conventions 의 서버 필터 절).
    `radius_km` 를 주면 반경 밖이거나 좌표를 모르는 매물은 반경 안인지 알 수 없어 뺀다.
    매물마다 못 읽은 날짜를 `held` 에 맡겨 두고, 부르는 쪽이 자른 뒤 남은 매물의 것만 `keep_unread_dates` 로 넣는다.
    """
    def keep(item: NaverArticleListItemModel) -> str:
        with holding_unread_dates() as dates:
            listing = article_info_to_listing(item, center)
        if listing is not None and listing.id not in listings and (
            radius_km is None or (listing.distance_km is not None and listing.distance_km <= radius_km)
        ):
            listings[listing.id] = listing
            held[listing.id] = dates
        return item.representative_article_info.article_number

    return keep


def price_sort_notes(sort_type: str | None, trade_types: list[str] | None) -> list[str]:
    """가격순 정렬을 읽는 법. 서버 가격순은 단지·지역·재개발 매물 목록 모두 같은 방식이다.

    거래 유형이 여럿이면 매매가·보증금을 섞어 한 줄로 세운다 (단지: 전세 14.5억이 매매 29억보다 앞, 2026-10-09.
    역삼동 가격높은순: 월세 3.3억/45만이 매매 200억보다 앞, 강남역 가격낮은순: 보증금 50만 → 4,500만 → 500만, 2026-10-10).
    월세 가격순은 보증금 순도 월세 순도 아니다 (헬리오시티 월세: 1억/280 → 4억/165 → 1억/270, 2026-10-09 확인).

    Args:
        trade_types: 찾은 거래 유형 이름. 비우면 전체.
    """
    if sort_type not in ('PRICE_ASC', 'PRICE_DESC'):
        return []
    searched_trades = set(trade_types or TRADE_CODE_BY_NAME)
    if len(searched_trades) > 1:
        return [
            '가격순은 거래 유형마다 다른 금액(매매가, 전세·월세 보증금)을 섞어 정렬합니다. '
            '--trade 를 하나만 주면 같은 금액끼리 비교됩니다'
        ]
    if searched_trades & {'월세', '단기임대'}:
        return [
            '월세 가격순은 네이버 기준(보증금 순도 월세 순도 아님)으로 정렬돼 있습니다. '
            '월세·보증금은 각 매물의 rent_manwon·deposit_manwon 으로 직접 비교하세요'
        ]
    return []


def group_sort_notes(sort_type: str | None, listings: list[Listing]) -> list[str]:
    """가격순인데 중개사마다 호가가 다른 중복 묶음이 있으면, 이 결과의 묶음 끝 호가를 실제 값으로 알린다 (`NaverListing`).

    네이버는 묶음의 호가 범위로 정렬해 가격높은순 첫 매물이 대표 30억(묶음 30억~33억) 뒤로 32억들이 온다. 가격 조건은 대표
    호가로만 걸려 `--price-min 325000` 은 그 33억 호가를 찾지 못하고 '0건이 전부' 다 (2026-10-31 실측: 가격 30억~30억은 그
    묶음이 나오고 33억~33억은 0건). 범위 필드와 '범위로 정렬한다' 는 안내만 두자 에이전트가 가격 조건 0건을 믿고 최고 호가를
    32억으로 답해(재검증 sonnet 2회), 끝 호가 값과 가격 조건이 걸리는 방식을 숫자 옆에 적는다.
    """
    if sort_type not in ('PRICE_ASC', 'PRICE_DESC'):
        return []
    descending = sort_type == 'PRICE_DESC'
    ends: list[tuple[float, NaverListing]] = []
    for listing in listings:
        if not isinstance(listing, NaverListing):
            continue
        if listing.asking_range is None:
            continue
        # 주 금액(매매가, 그 밖에는 보증금)의 범위만 본다. 주 금액의 두 끝이 같거나 모르면 이 매물은 범위가 없어 건너뛴다
        field = 'price_manwon' if listing.trade_type == '매매' else 'deposit_manwon'
        lowest, highest = listing.asking_range.lowest, listing.asking_range.highest
        low = getattr(lowest, field) if lowest is not None else None
        high = getattr(highest, field) if highest is not None else None
        if low != high and (end_price := high if descending else low) is not None:
            ends.append((end_price, listing))
    if not ends:
        return []
    end, pick = (max if descending else min)(ends, key=lambda pair: pair[0])
    price = pick.price_manwon if pick.price_manwon is not None else pick.deposit_manwon
    price_text = '모름' if price is None else format_manwon(price)
    edge = '최고' if descending else '최저'
    return [note(
        '참고',
        f'같은 집을 중개사 여럿이 올린 매물(realtor_count)의 가격은 대표 매물 호가이고, 네이버 가격순은 묶음의 {edge} 호가로 '
        f'정렬합니다. 이 결과의 묶음 {edge} 호가는 {format_manwon(end)}만원입니다 ({pick.id}: 대표 {price_text}만원). 가격 조건(--price-*·'
        '--deposit-*·--rent-*)은 대표 호가로만 걸려 이런 묶음 안의 호가는 찾지 못합니다',
    )]


def price_filter_of(conditions: NaverTradeConditions) -> dict[str, int]:
    """만원 가격 조건을 단지·재개발 구역 매물 목록의 가격 키(원)로 바꾼다. 없는 조건은 키를 뺀다."""
    return {
        key: value * WON_PER_MANWON
        for key, value in (
            ('min_deal_price', conditions.price_min), ('max_deal_price', conditions.price_max),
            ('min_warranty_price', conditions.deposit_min), ('max_warranty_price', conditions.deposit_max),
            ('min_rent_price', conditions.rent_min), ('max_rent_price', conditions.rent_max),
        )
        if value is not None
    }
