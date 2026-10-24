"""단지 매물 목록과 매물 상세 (search listings --complex, listing)."""

from httpx import HTTPStatusError
from pydantic import Field

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    Listing,
    ListingDetail,
    join_address,
    m2_to_pyeong,
    move_in_label,
    normalize_date,
    note,
    parking_label,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
    NaverLegalDivisionSearchByCoordinateV1RequestParameterModel,
    NaverRealEstateType,
)
from jibsa.providers.naver.api.request.listing import (
    NaverArticleAgentFeeV1RequestParameterModel,
    NaverArticleBasicInfoV1RequestParameterModel,
    NaverArticleKeyV1RequestParameterModel,
    NaverArticleMaintenanceFeeV1RequestParameterModel,
    NaverArticleTaxV1RequestParameterModel,
    NaverComplexArticleListV1RequestPayloadModel,
    NaverComplexVillaArticleListV1RequestPayloadModel,
    NaverDataServiceTransportV1RequestParameterModel,
    NaverEducationBuildingSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
    NaverCoordinatesModel,
    NaverFacilityInfoModel,
)
from jibsa.providers.naver.api.response.listing import (
    NaverArticleBasicInfoModel,
    NaverArticleDetailInfoModel,
    NaverArticleKeyModel,
    NaverArticleMaintenanceFeeModel,
    NaverCommunalComplexInfoModel,
    NaverMovingInInfoModel,
    NaverPriceInfoModel,
    NaverSpaceInfoModel,
    NaverTransportSubwayModel,
)
from jibsa.providers.naver.service.common import (
    COMPLEX_SORT_TYPE_BY_NAME,
    OFFICETEL_CODE,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
    PROPERTY_NAME_BY_CODE,
    TRADE_CODE_BY_NAME,
    TRADE_NAME_BY_CODE,
    VILLA_COMPLEX_CODES,
    NaverAssignedSchool,
    NaverListingsResult,
    NaverTradeConditions,
    PageScan,
    article_url,
    assigned_schools,
    building_approved_at,
    check_pyeong_numbers,
    dong_label,
    known_floor,
    listing_keeper,
    pagination_notes,
    price_filter_of,
    price_sort_notes,
    resolve_dong_numbers,
    result_or_none,
    scan_pages,
    unwrap,
    villa_by_complex_response,
    villa_fallback_found,
)

from typing import (
    Annotated,
    Any,
    get_args,
)


# 서버가 받는 매물 유형 코드 전부 (`NaverRealEstateType`). 매물 상세가 응답의 유형 코드를 요청에 다시 넣기 전에 확인한다
KNOWN_REAL_ESTATE_TYPES: frozenset[str] = frozenset(get_args(NaverRealEstateType))
# 상세 detailInfo.shape 도 같은 코드다. 방 1개 매물의 room_type 이름으로 쓴다
ONE_ROOM_TYPE_BY_SHAPE: dict[str, str] = {code: f'{name}원룸' for name, code in ONE_ROOM_SHAPE_CODE_BY_NAME.items()}
DIRECTION_BY_CODE: dict[str, str] = {
    'EE': '동향',
    'WW': '서향',
    'SS': '남향',
    'NN': '북향',
    'ES': '남동향',
    'SE': '남동향',
    'WS': '남서향',
    'SW': '남서향',
    'EN': '북동향',
    'NE': '북동향',
    'WN': '북서향',
    'NW': '북서향',
}
# 입주 시기 코드. MV001 은 날짜 없이 오는 패턴으로 보아 즉시입주로 추정했다.
# EARLY / MID / LATE 는 movingInDate 의 달 초순·중순·하순이다.
MOVING_IN_LABELS: dict[str, str] = {
    'MV001': '즉시입주',
}
MOVING_IN_PERIOD_LABELS: dict[str, str] = {
    'EARLY': '초순',
    'MID': '중순',
    'LATE': '하순',
}
# 관리비 항목 코드 (사이트 관리비 상세보기 화면과 대조, 2026-10-10). 이름은 당근·직방 manage_cost_includes 와 맞춘다
MANAGE_COST_ITEM_LABELS: dict[str, str] = {
    '01': '공용',
    '11': '전기',
    '12': '수도',
    '13': '가스',
    '14': '난방',
    '15': '인터넷',
    '16': 'TV',
    '99': '기타',
}
# 시설 코드 이름. 네이버 웹 스크립트의 ARTICLE_FACILITY_*_TYPE 표와 대조했다 (2026-10-24: 사설경비·에어컨·가스오븐·소파가
# 빠져 PRIVATE_SECURITY 같은 영어 코드가 options 에 그대로 나갔다). 이름은 다른 소스와 맞춰 줄였다 (인덕션레인지 → 인덕션).
# ELEVATOR 는 options 가 아니라 elevator 로 낸다
FACILITY_LABELS: dict[str, str] = {
    # 생활시설
    'BED': '침대',
    'DESK': '책상',
    'DINING_TABLE': '식탁',
    'CLOSET': '옷장',
    'BUILT_IN_CLOSET': '붙박이장',
    'DRESSING_TABLE': '화장대',
    'SHOE_RACK': '신발장',
    'SINK': '싱크대',
    'REFRIGERATOR': '냉장고',
    'WASHING_MACHINE': '세탁기',
    'DRYER': '건조기',
    'CLOTHES_DRYER': '건조기',
    'DISH_WASHER': '식기세척기',
    'GAS_RANGE': '가스레인지',
    'GAS_STOVE': '가스레인지',
    'INDUCTION_RANGE': '인덕션',
    'MICROWAVE': '전자레인지',
    'OVEN': '오븐',
    'GAS_OVEN': '가스오븐',
    'AIRCON': '에어컨',
    'SOFA': '소파',
    'TV': 'TV',
    'BIDET': '비데',
    'SHOWER_BOOTH': '샤워부스',
    'BATHTUB': '욕조',
    # 보안시설
    'GUARD': '경비원',
    'CCTV': 'CCTV',
    'INTER_PHONE': '인터폰',
    'VIDEO_PHONE': '비디오폰',
    'SECURITY_WINDOW': '방범창',
    'CARD_KEY': '카드키',
    'DOOR_LOCK': '도어락',
    'ENTRANCE_SECURITY': '현관보안',
    'PRIVATE_SECURITY': '사설경비',
    # 기타시설
    'FIRE_ALARM': '화재경보기',
    'TERRACE': '테라스',
    'VERANDA': '베란다',
    'ROOF_TOP': '옥상',
    'YARD': '마당',
    'DELIVERY_BOX': '무인택배함',
    # 냉방시설
    'WALL': '벽걸이 에어컨',
    'CEILING': '천장형 에어컨',
    'STAND': '스탠드 에어컨',
    'CENTRAL': '중앙냉방',
}
COMPLEX_PAGE_SIZE: int = 30
# 단지 매물 목록 요청 상한 (빌라 단지로 다시 묻는 1회 포함). limit 건까지만 받고, 받은 뒤 중복·모르는 거래 유형으로
# 빠져도 그만큼 다시 받지 않는다
MAX_COMPLEX_ARTICLE_PAGE_REQUESTS: int = 5


# 매매 매물 상세에만 붙이는 필드 (요청을 아끼려고 전월세는 조회하지 않는다)
SALE_ONLY_FIELDS: frozenset[str] = frozenset({
    'agent_fee_manwon', 'acquisition_tax_manwon', 'property_tax_manwon', 'comprehensive_real_estate_tax_manwon',
})


def _sum_manwon(*amounts: int | None) -> float | None:
    """원 단위 금액들의 합을 만원으로. 모두 모르면 None.

    아는 항목만 더한다. 네이버 세금 응답은 면제 항목도 null 이 아니라 0 으로 줘서 일부만 null 인 응답은 없다
    (헬리오시티 39~150㎡·일신동 빌라 6건, 2026-10-11). 일부만 null 이 오면 응답 형식이 바뀐 것이다.
    """
    known = [amount for amount in amounts if amount is not None]
    return won_to_manwon(sum(known)) if known else None


def _sale_costs(client: NaverClient, article_number: str) -> dict[str, float | None]:
    """매매 매물의 중개보수·세금 (2회 호출). 조회가 실패하면 그 값만 모름(None)으로 둔다."""
    costs: dict[str, float | None] = dict.fromkeys(SALE_ONLY_FIELDS)
    fee = result_or_none(lambda: client.run_request_article_agent_fee_v1(
        NaverArticleAgentFeeV1RequestParameterModel(article_number=article_number)
    ))
    if fee is not None and fee.fee is not None:
        costs['agent_fee_manwon'] = won_to_manwon(fee.fee)
    tax = result_or_none(lambda: client.run_request_article_tax_v1(
        NaverArticleTaxV1RequestParameterModel(article_number=article_number)
    ))
    if tax is not None:
        if tax.acquisition_tax is not None:
            acquisition = tax.acquisition_tax
            costs['acquisition_tax_manwon'] = _sum_manwon(
                acquisition.acquisition_tax, acquisition.local_tax, acquisition.rural_special_tax,
            )
        if tax.property_tax is not None:
            property_ = tax.property_tax
            costs['property_tax_manwon'] = _sum_manwon(
                property_.property_tax, property_.local_education_tax, property_.urban_area_segment_tax,
            )
        if tax.total_real_estate_tax is not None:
            total = tax.total_real_estate_tax
            costs['comprehensive_real_estate_tax_manwon'] = _sum_manwon(
                total.total_real_estate_tax, total.rural_special_tax,
            )
    return costs


def _subway_label(station: NaverTransportSubwayModel) -> str | None:
    """'대청역 (3호선, 도보 9분)'. 노선마다 출구가 달라 도보 시간이 다르면 가장 짧은 것을 쓴다."""
    if not station.station_name:
        return None
    lines = list(dict.fromkeys(line.name for line in station.type_list if line.name))
    minutes = [line.walking_duration for line in station.type_list if line.walking_duration is not None]
    parts = ['·'.join(lines)] if lines else []
    if minutes:
        parts.append(f'도보 {min(minutes)}분')
    return f"{station.station_name} ({', '.join(parts)})" if parts else station.station_name


def _surroundings(client: NaverClient, article_number: str, key: NaverArticleKeyModel) -> dict[str, Any]:
    """매물 주변의 지하철역·버스 노선·배정 초등학교 (1~2회 호출).

    학교는 사이트처럼 단지·동 번호가 있는 매물만 묻는다 (`has_school_lookup`. 없으면 출력에서 키를 뺀다).
    조회가 실패하거나 교통이 통째로 비어 있으면 그 값만 모름(None)으로 둔다.
    """
    result: dict[str, Any] = {'nearby_subways': None, 'bus_routes': None, 'schools': None, 'has_school_lookup': False}
    transport = result_or_none(lambda: client.run_request_data_service_transport_v1(
        NaverDataServiceTransportV1RequestParameterModel(item_id=int(article_number))
    ))
    # 역도 버스도 없으면 네이버에 교통 정보가 없는 매물이다 (역삼동 단지형 빌라에서 둘 다 빈 목록,
    # 2026-10-09 확인). 주변에 정말 아무것도 없다는 뜻이 아니라 모름(None)으로 둔다
    if transport is not None and (transport.subway_list or transport.bus_list):
        result['nearby_subways'] = [label for label in map(_subway_label, transport.subway_list) if label]
        routes: dict[str, list[str]] = {}
        for bus in transport.bus_list:
            if bus.type_name and bus.routes:
                bucket = routes.setdefault(bus.type_name, [])
                bucket += [route for route in bus.routes if route not in bucket]
        result['bus_routes'] = routes

    ids = key.key
    if ids is None or not ids.complex_number or not ids.building_number:
        return result
    result['has_school_lookup'] = True
    schools = result_or_none(lambda: client.run_request_education_building_school_v1(
        NaverEducationBuildingSchoolV1RequestParameterModel(
            item_type='villa' if key.type.real_estate_type in VILLA_COMPLEX_CODES else 'complex',
            complex_number=ids.complex_number,
            building_number=ids.building_number,
        )
    ))
    if schools is not None:
        result['schools'] = assigned_schools(schools)
    return result


class NaverListingDetail(ListingDetail):
    """상세 조회로 보강한 네이버 매물. 단지 번호로 실거래가·단지 정보를 이어서 조회할 수 있다."""

    complex_number: Annotated[
        int | None,
        Field(description='단지 번호 (naver complex / real-price 에 넘긴다)')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지명')
    ] = None
    dong: Annotated[
        str | None,
        Field(description='동')
    ] = None
    pyeong_number: Annotated[
        int | None,
        Field(description='평형 번호 (naver real-price --pyeong 에 넘긴다)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 네이버가 계약면적만 줘서 null')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡, 공급 + 주차장 등 기타 공용). 오피스텔만')
    ] = None
    loan_manwon: Annotated[
        float | None,
        Field(description='융자금 (만원)')
    ] = None
    agent_fee_manwon: Annotated[
        float | None,
        Field(description='중개보수 상한 (만원, 네이버 계산. 매매만)')
    ] = None
    acquisition_tax_manwon: Annotated[
        float | None,
        Field(description='취득세 합계 (만원, 취득세 + 지방교육세 + 농어촌특별세. 네이버 계산. 매매만)')
    ] = None
    property_tax_manwon: Annotated[
        float | None,
        Field(description='연 재산세 합계 (만원, 재산세 + 지방교육세 + 도시지역분. 공시가 기준 네이버 계산. 매매만)')
    ] = None
    comprehensive_real_estate_tax_manwon: Annotated[
        float | None,
        Field(description='연 종합부동산세 합계 (만원, 종부세 + 농어촌특별세. 공시가 기준 네이버 계산. 매매만)')
    ] = None
    # 상세 출력에서 가장 긴 필드지만 매물 하나에 한 번이라 줄이지 않는다. 통근을 따질 때 버스만 닿는 동네가 있다
    # (2026-10-23 실측: 강남역 근처 원룸 상세 1,078자 중 381자, 약 120토큰)
    bus_routes: Annotated[
        dict[str, list[str]] | None,
        Field(description='주변 정류장의 버스 노선 (종류별, 예: {"간선": ["146", "341"]}). 조회 실패면 null')
    ] = None
    schools: Annotated[
        list[NaverAssignedSchool] | None,
        Field(description='배정 초등학교. 조회 실패면 null. 단지·동 번호가 없는 매물은 네이버가 주지 않아 키를 뺀다')
    ] = None
    has_school_lookup: Annotated[
        bool,
        Field(exclude=True, description='배정 학교를 조회하는 매물인지 (단지·동 번호가 있음). schools 가 해당 없는지 가리는 데만 쓴다')
    ] = False

    def not_applicable_fields(self) -> frozenset[str]:
        # 단지에 속하지 않는 매물(빌라 등)은 단지·동·평형 번호가 원래 없다.
        fields = super().not_applicable_fields()
        if self.complex_number is None:
            fields = fields | {'complex_number', 'complex_name', 'dong', 'pyeong_number'}
        # 배정 학교는 단지·동 번호가 있는 매물만 있다. null 은 조회 실패(모름)로만 남긴다
        if not self.has_school_lookup:
            fields = fields | {'schools'}
        # 네이버는 오피스텔에만 계약면적을 준다 (다른 유형은 상세의 supplySpace 가 공급면적).
        if self.property_type != '오피스텔':
            fields = fields | {'contract_area_m2'}
        # 세금·중개보수는 매매 매물만 조회한다
        if self.trade_type != '매매':
            fields = fields | SALE_ONLY_FIELDS
        return fields


def _room_type(space: NaverSpaceInfoModel | None, shape: str | None) -> str | None:
    """상세의 방 구조. 방 수로 투룸·쓰리룸·포룸이상을 가리고, 방 1개면 복층 여부와 원룸 구조(shape)로 정한다.

    shape 는 방이 여럿인 매물도 분리형('20')으로 오므로 방 수를 먼저 본다. 단지 매물(아파트·오피스텔·단지형 빌라)은
    shape 가 없어 복층이 아닌 방 1개면 구조를 몰라 None 이다 (방 수는 room_count 로 준다).
    """
    if space is None or not space.room_count:
        return None
    count = space.room_count
    if count == 2:
        return '투룸'
    if count == 3:
        return '쓰리룸'
    if count >= 4:
        return '포룸이상'
    if space.duplex:
        return '복층형원룸'
    return ONE_ROOM_TYPE_BY_SHAPE.get(shape or '')


def list_complex_articles(
    client: NaverClient,
    complex_number: int,
    *,
    conditions: NaverTradeConditions | None = None,
    pyeong_numbers: list[int] | None = None,
    dong_names: list[str] | None = None,
    sort: str = '랭킹순',
    villa: bool | None = None,
    limit: int = 30,
) -> NaverListingsResult:
    """단지 매물을 `lastInfo` 커서로 넘기며 `limit` 건까지 모은다.

    빌라 단지(A05·A06·A07)는 아파트 단지 목록이 0건으로 오므로, 첫 페이지가 비면 빌라 단지 목록으로
    다시 묻는다 (매물이 없는 아파트 단지도 한 번 더 묻고, 빌라 쪽이 실패하면 0건이다. `villa` 를 주었거나
    동 목록을 조회했으면 단지 종류를 이미 알아 다시 묻지 않는다). 요청은 `MAX_COMPLEX_ARTICLE_PAGE_REQUESTS` 회에서
    멈추고 `notes` 로 알린다. 처음 보는 매물이 없는 페이지가 오면 커서가 멈춘 것으로 보고 끝낸다.
    평형 번호를 주었는데 0건이면 평형 목록으로 번호를 확인한다 (1~2회 추가, 아파트로 정해지면 빌라 목록은 묻지 않는다).
    단지 종류를 모른 채 0건이면 단지 정보로 단지가 있는지 확인한다 (1~2회 추가, `_raise_if_missing_complex`).

    Raises:
        JibsaError: 평형 번호가 그 단지에 없거나, 단지 번호가 아파트·빌라 단지 어디에도 없으면 NOT_FOUND.

    Args:
        conditions: 거래 유형·가격 조건 (`NaverTradeConditions`). 서버 필터로 보내고 받은 뒤 다시 거르지 않는다.
        dong_names: 동 이름 ('104', '104동'). 주면 동 목록을 먼저 조회해 동 번호로 바꾼다 (요청 1~2회 추가).
        sort: 정렬 (`COMPLEX_SORT_TYPE_BY_NAME` 의 이름). 서버가 정렬해 준다.
        villa: 빌라 단지인지 (`resolve_complex_number` 결과). 모르면 None.
    """
    conditions = conditions or NaverTradeConditions()
    sort_type = COMPLEX_SORT_TYPE_BY_NAME[sort]
    dong_numbers: list[str] = []
    if dong_names:
        dong_numbers, villa = resolve_dong_numbers(client, complex_number, dong_names, villa=villa)
    # 단지 종류를 알면(단지 이름 검색·동 목록) 빌라는 아파트 목록을 건너뛰고, 아파트는 첫 페이지가 비어도 빌라 목록으로
    # 다시 묻지 않는다. 모르면(None) 첫 페이지가 빌 때 그 자리에서 정한다 (`villa_by_complex_response`)
    known_at_start = villa is not None
    price_filter = price_filter_of(conditions)
    listings: dict[str, Listing] = {}
    scan = PageScan(limit=limit, max_requests=MAX_COMPLEX_ARTICLE_PAGE_REQUESTS)

    def fetch(size: int, seed: str | None, last_info: Any) -> NaverArticlePageModel | None:
        nonlocal villa
        # 다음 쪽이 있는 동안 lastInfo 는 리스트로 온다 ([1, 점수, 매물 번호], 가격·최신순은 가격·날짜가 더 붙는다.
        # 헬리오시티 1,774건 랭킹·가격낮은·최신순 각 3쪽, 2026-10-10). 마지막 쪽도 리스트다 (개포자이 랭킹·가격높은순 각 3쪽,
        # 2026-10-11). 정수가 오면 응답 형식이 바뀐 것이라 멈춘다. 그때 '검색을 마쳤다' 로 안내되지만 실제로 오지 않는
        # 경우라 따로 알리지 않는다
        if last_info is not None and not isinstance(last_info, list):
            return None
        # 다음 쪽이 있는 동안의 lastInfo 는 빈 리스트로 오지 않아, 비었으면 첫 쪽이다 (2026-10-19 실측: 헬리오시티 단지 번호로
        # 랭킹순 4쪽·최신순 월세 4쪽 모두 값이 든 리스트). 2026-10-19 리뷰 오탐 확인
        first = not last_info
        payload = NaverComplexArticleListV1RequestPayloadModel(
            complex_number=complex_number,
            size=size,
            trade_types=[TRADE_CODE_BY_NAME[trade] for trade in conditions.trade_types],
            pyeong_types=pyeong_numbers or [],
            dong_numbers=dong_numbers,
            article_sort_type=sort_type,
            seed=seed,
            last_info=last_info or [],
            **price_filter,
        )
        if not villa:
            page = unwrap(client.run_request_complex_article_list_v1(payload), '단지 매물')
            if villa is False or not first or page.items:
                return page
            if pyeong_numbers:
                # 평형 번호가 틀려도 0건이 온다. 평형 번호를 확인하면서 단지 종류를 정해, 아파트면 빌라 목록을 묻지 않는다.
                # 빌라 단지로 정해지면 빌라 목록 실패를 '빌라가 아님(0건)' 으로 보지 않고 에러로 낸다
                villa = check_pyeong_numbers(client, complex_number, pyeong_numbers)
                if not villa:
                    return page
            # 첫 페이지가 비면 빌라 단지 목록으로 다시 묻는다. 이 1회도 요청 상한에 센다
            scan.page_requests += 1
        response = client.run_request_complex_villa_article_list_v1(
            NaverComplexVillaArticleListV1RequestPayloadModel(**payload.model_dump())
        )
        # 단지 종류를 모른 채 빌라로 다시 물었는데 빌라 단지도 아니면, 에러 대신 매물 0건으로 본다
        if villa is None:
            if not villa_fallback_found(response):
                return None
            villa = True
        return unwrap(response, '단지 매물')

    scan_pages(scan, fetch, listing_keeper(listings, None), page_size=COMPLEX_PAGE_SIZE)
    total, inspected, truncated = scan.total, scan.received, scan.truncated
    if pyeong_numbers and not inspected and known_at_start:
        # 단지 종류를 알아 빌라로 다시 묻지 않았어도, 0건이면 평형 번호가 틀린 것인지 확인한다. 모르고 시작했으면
        # 첫 페이지가 빌 때 fetch 안에서 이미 확인했다
        check_pyeong_numbers(client, complex_number, pyeong_numbers, villa=villa)
    elif not inspected and not known_at_start and not pyeong_numbers:
        _raise_if_missing_complex(client, complex_number)

    notes: list[str] = []
    if truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 단지 매물 목록을 {MAX_COMPLEX_ARTICLE_PAGE_REQUESTS}번까지만 받았습니다. '
            '조건에 맞는 매물이 더 있을 수 있으니 조건을 좁혀 다시 검색하세요',
        ))
    notes += price_sort_notes(sort_type, conditions.trade_types)
    result = list(listings.values())[:limit]
    notes += pagination_notes(total, len(result), limit, inspected, truncated=truncated)
    return NaverListingsResult(
        total=total,
        returned=len(result),
        # 단지 매물은 이어 받지 않는다 (next 없음). 더 있는지만 알린다
        has_more=scan.cursor is not None,
        listings=result,
        notes=notes,
    )


def _raise_if_missing_complex(client: NaverClient, complex_number: int) -> None:
    """단지 번호가 아파트·빌라 단지 어디에도 없으면 NOT_FOUND. 아파트 단지 정보를 먼저 묻고, 빈 결과면 빌라 단지 정보를 묻는다.

    단지 매물 목록은 아파트·빌라 모두 없는 단지 번호에도 빈 성공 응답을 줘서, 매물이 없는 단지와 구분되지 않는다
    (2026-10-23 실측: 빌라 목록이 99999999 와 아파트 단지 헬리오시티 111515 에 똑같이 `totalCount: 0`). 평형 번호를 주었으면
    평형 목록 확인(`check_pyeong_numbers`)이 같은 일을 한다.
    """
    if villa_by_complex_response(client.run_request_complex_v1(NaverComplexV1RequestParameterModel(complex_number=complex_number))):
        unwrap(client.run_request_complex_villa_v1(NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)), '단지')


def _loan_manwon(price: NaverPriceInfoModel | None) -> float | None:
    """융자금(만원). 금액이 있으면 그 값, 융자 없음이 명시(loanCode '0')면 0, 그 외는 모름(None).

    네이버는 융자를 입력하지 않은 매물도 `loan: 0` 으로 주고 loanCode 를 빼서 보낸다.
    """
    if price is None:
        return None
    if price.loan:
        return won_to_manwon(price.loan)
    if price.loan_code == '0':
        return 0.0
    return None


def _move_in_label(moving: NaverMovingInInfoModel | None) -> str | None:
    """입주 시기 코드를 읽을 수 있는 문구로 바꾼다.

    날짜 지정('MV004')·모르는 코드는 날짜만 쓰고, 날짜도 없으면 모름(None)이다. 코드('MV004')를 그대로 내보내지 않는다.
    """
    if moving is None:
        return None
    code = moving.moving_in_type
    date = moving.moving_in_date
    label: str | None
    if code in MOVING_IN_PERIOD_LABELS and date:
        month = (normalize_date(date) or date)[:7]
        label = f'{month} {MOVING_IN_PERIOD_LABELS[code]}'
        return f'{label} (협의 가능)' if moving.moving_in_negotiation else label
    return move_in_label(MOVING_IN_LABELS.get(code or '', date), negotiable=bool(moving.moving_in_negotiation))


def _manage_cost(fee: NaverArticleMaintenanceFeeModel | None) -> tuple[float | None, list[str] | None]:
    """월 관리비(만원)와 관리비에 포함된 항목. 모르면 None.

    합계형(typeCode '02')은 etcDetail, 정액 합계형('04')은 같은 모양의 fixNonDetailList 의 금액과 포함 항목(categoryList)을
    쓴다. 0 은 중개사가 0원으로 입력한 것이다. '04' 는 원룸·빌라·오피스텔 16건 중 7건일 만큼 흔하다 (신림동, 2026-10-11).
    항목별형('01')은 사이트처럼 정액 항목의 금액을 더해 합계로 보고, 정액 항목만 포함 항목으로 친다. 실비 항목은
    쓴 만큼 따로 내서 빠진다 (원룸 2653883790: 공용 10만원 정액, 전기~TV 실비 → 합계 10만원, 2026-10-10).
    그래서 항목이 모두 실비면 0만원·[] 이다. 정액으로 내는 관리비가 0원이고 공과금은 따로 낸다는 뜻이라 모름(None)이
    아니다 (docs/naver.md 의 manage_cost_includes 설명과 같은 규칙).
    미확인('03')은 etcDetail·fixNonDetailList 가 null 이고 uncheckDetail 로 와서 모름이다 (빌라 2654619539·2653716463,
    2026-10-11). 그래서 typeCode 를 따로 보지 않고 값이 온 키로 정한다. 세 키(etcDetail·fixNonDetailList·fixDetailList)
    중 하나만 오고 나머지는 null 이라(신림동 월세 29건: '04' 18·'02' 10·'01' 1, 2026-10-11) 객체가 있는지만 본다.
    금액 없는 빈 etcDetail 이 다른 키와 함께 오는 응답은 없었다.
    """
    if fee is None:
        return None, None
    summary = fee.etc_detail or fee.fix_non_detail_list
    if summary is not None:
        codes = summary.category_list
        includes = None if codes is None else [MANAGE_COST_ITEM_LABELS.get(code, code) for code in codes]
        return won_to_manwon(summary.amount), includes
    if fee.fix_detail_list:
        fixed = [item for item in fee.fix_detail_list if item.unit_type == '01' and item.amount is not None]
        includes = [MANAGE_COST_ITEM_LABELS.get(item.type, item.type) for item in fixed if item.amount and item.type]
        return won_to_manwon(sum(item.amount or 0 for item in fixed)), includes
    return None, None


def _parking_label(facility: NaverFacilityInfoModel | None, in_complex: bool) -> str | None:
    """주차 가능 여부와 총 주차 대수를 문구로 만든다 ('불가 (총 4대)', '단지 전체 398대').

    대수가 있어도 이 매물은 주차 불가일 수 있어(원룸 총 6대·불가, 2026-10-10) 가능 여부를 앞에 붙인다.
    단지가 없는 원룸·빌라에는 '단지 전체' 를 붙이지 않는다. 0대는 모름이 아니라 0대다.
    """
    if facility is None:
        return None
    count = facility.total_parking_count
    count_text = None if count is None else f'{"단지 전체" if in_complex else "총"} {count}대'
    return parking_label(facility.is_parking_possible, count_text)


def _complex_approved_at(client: NaverClient, complex_number: int | None, key: NaverArticleKeyModel) -> str | None:
    """단지의 사용승인일 (YYYY-MM-DD). 매물 상세에 건물 날짜가 없을 때만 단지 정보에서 받는다.

    빌라 단지(A05·A06·A07)는 아파트 단지 엔드포인트가 result=null 이라 빌라 동 목록에서 매물의 동
    (article/key 의 buildingNumber)을 찾아 그 동의 날짜를 쓴다. 빌라 단지 정보에는 날짜가 없는 단지가
    있고(진명하이츠 등), 동마다 날짜가 다른 단지도 있어서다 (성재하이빌 에이동 2003-08-11·비동
    2003-09-05, 2026-10-09 확인).

    단지 번호가 없거나 단지 조회가 실패하면(단지가 아닌 매물 등) 모름(None)이다.
    """
    if complex_number is None:
        return None
    if key.type.real_estate_type in VILLA_COMPLEX_CODES:
        building_number = key.key.building_number if key.key else None
        if building_number is None:
            return None
        buildings = result_or_none(lambda: client.run_request_complex_villa_building_list_v1(
            NaverComplexVillaBuildingListV1RequestParameterModel(complex_number=complex_number)
        ))
        building = next((item for item in buildings or [] if item.number == building_number), None)
        return normalize_date(building.use_approval_date) if building is not None else None
    complex_ = result_or_none(lambda: client.run_request_complex_v1(
        NaverComplexV1RequestParameterModel(complex_number=complex_number)
    ))
    return normalize_date(complex_.use_approval_date) if complex_ is not None else None


def get_listing(client: NaverClient, article_number: str) -> NaverListingDetail:
    """매물 상세: key → basicInfo → maintenanceFee → 좌표의 법정동 → 단지 (최대 5회 호출, 단지는 필요할 때만).

    매매 매물은 중개보수(agentFee)·세금(tax)을 더 조회한다 (2회 더). 주변 교통(지하철·버스)은 늘,
    배정 초등학교는 단지·동 번호가 있는 매물만 더 조회한다 (1~2회 더, 최대 9회).

    중개사 정보와 본문은 내보내지 않는다 (문의·상세 설명은 원 사이트에서). 지번 주소는 좌표로 얻은
    법정동 이름과 article/key 의 지번을 합쳐 만든다. 사용승인일은 상세의 건물 날짜(facilityInfo)를 쓰고, 없으면 단지 정보에서 받는다.

    key·basicInfo 밖의 부가 조회(관리비·법정동·단지·중개보수·세금·교통·학교)는 실패하면 그 값만 모름(None)이다.

    Raises:
        ListingUnavailableError: 없거나 내려간 매물이거나, 모르는 거래 유형·매물 유형 코드일 때
            (reason UNKNOWN_TRADE_TYPE·UNKNOWN_REAL_ESTATE_TYPE, listing_status 에 원래 코드).
    """
    key, trade_type = _article_key(client, article_number)
    basic = _article_basic(client, article_number, key)
    fee = result_or_none(lambda: client.run_request_article_maintenance_fee_v1(
        NaverArticleMaintenanceFeeV1RequestParameterModel(article_number=article_number)
    ))

    price = basic.price_info
    detail = basic.detail_info
    article = detail.article_detail_info if detail else None
    space = detail.space_info if detail else None
    size = detail.size_info if detail else None
    moving = detail.moving_in_info if detail else None
    facility = detail.facility_info if detail else None
    complex_info = basic.communal_complex_info

    title = _listing_title(complex_info, article)
    move_in = _move_in_label(moving)
    manage_cost, manage_cost_includes = _manage_cost(fee)

    exclusive = size.exclusive_space if size else None
    # 상세의 supplySpace 는 오피스텔이면 계약면적이다 (평형표의 contractArea 와 같고 supplyArea 보다 크다).
    # 다른 유형은 공급면적 그대로다. 오피스텔 공급면적은 평형표를 더 조회해야 해 모름(None)으로 둔다.
    is_officetel = key.type.real_estate_type == OFFICETEL_CODE
    listed_area = size.supply_space if size else None
    coordinates = article.coordinates if article else None

    address = _jibun_address(client, key, coordinates)

    # communalComplexInfo 는 단지 매물에만 오고, 오면 complexNumber 가 article/key 의 단지 번호와 같다. 단지가 없는
    # 매물은 둘 다 비어 있다 (단독·다가구·빌라·원룸·단지형 빌라·오피스텔·아파트 10건, 2026-10-10 확인)
    complex_number = complex_info.complex_number if complex_info else (key.key.complex_number if key.key else None)
    parking = _parking_label(facility, complex_number is not None)

    facility_codes = (facility.life + facility.security + facility.etc + facility.aircon) if facility else []

    return NaverListingDetail(
        source='naver',
        id=article_number,
        url=article_url(article_number),
        trade_type=trade_type,
        property_type=PROPERTY_NAME_BY_CODE.get(key.type.real_estate_type, key.type.real_estate_type),
        room_type=_room_type(space, detail.shape if detail else None),
        title=title or None,
        price_manwon=won_to_manwon(price.price) if price and trade_type == '매매' else None,
        deposit_manwon=(
            won_to_manwon(price.warranty_amount if price.warranty_amount is not None else price.price)
            if price and trade_type != '매매' else None
        ),
        rent_manwon=(
            won_to_manwon(price.rent_amount if price.rent_amount is not None else price.monthly_rent)
            if price and trade_type in ('월세', '단기임대') else None
        ),
        # 목록의 0 은 0원 입력과 미확인을 구분할 수 없어 모름으로 두고, 상세 관리비 API 로 구분한다 (`_manage_cost`)
        manage_cost_manwon=manage_cost,
        manage_cost_includes=manage_cost_includes,
        area_m2=exclusive,
        area_pyeong=m2_to_pyeong(exclusive),
        floor=known_floor(space.floor_info.target_floor) if space and space.floor_info else None,
        building_floor=known_floor(space.floor_info.total_floor) if space and space.floor_info else None,
        address=address,
        lat=coordinates.y_coordinate if coordinates else None,
        lng=coordinates.x_coordinate if coordinates else None,
        registered_at=normalize_date(article.exposure_start_date) if article else None,
        # 상세 응답의 건물 날짜를 먼저 쓰고, 없을 때만 단지 정보를 조회한다 (네이버 요청 1회 절약).
        approved_at=building_approved_at(facility) or _complex_approved_at(client, complex_number, key),
        complex_number=complex_number,
        complex_name=complex_info.complex_name if complex_info else None,
        dong=complex_info.dong_name if complex_info else None,
        pyeong_number=key.key.pyeong_type_number if key.key else None,
        supply_area_m2=None if is_officetel else listed_area,
        contract_area_m2=listed_area if is_officetel else None,
        room_count=space.room_count if space else None,
        bathroom_count=space.bath_room_count if space else None,
        direction=(
            f'{DIRECTION_BY_CODE.get(space.direction, space.direction)} ({space.direction_standard})'
            if space and space.direction and space.direction_standard
            else (DIRECTION_BY_CODE.get(space.direction, space.direction) if space and space.direction else None)
        ),
        move_in=move_in,
        parking=parking,
        # 엘리베이터는 중개사가 고르는 기타시설(etc) 항목 하나라 없으면 고르지 않은 것인지 없는 것인지 모른다. 그래서 False 를
        # 내지 않는다 (2026-10-14 실측: 신림동 원룸 상세 3건 중 1건이 시설 13개를 골랐지만 ELEVATOR 는 없었고, 다른 1건은
        # 보안시설을 비워 두었다. 엘리베이터 없음을 따로 알리는 필드는 없다)
        elevator=True if 'ELEVATOR' in facility_codes else None,
        options=[
            FACILITY_LABELS.get(code, code)
            for code in facility_codes
            if code != 'ELEVATOR'
        ] if facility is not None else None,
        loan_manwon=_loan_manwon(price),
        **(_sale_costs(client, article_number) if trade_type == '매매' else {}),
        **_surroundings(client, article_number, key),
    )


def _article_key(client: NaverClient, article_number: str) -> tuple[NaverArticleKeyModel, str]:
    """매물 키(유형·단지·주소)와 거래 유형 이름. 모르는 거래 유형·매물 유형이면 나머지 요청을 보내지 않는다.

    Raises:
        ListingUnavailableError: 없거나 내려간 매물이거나, 모르는 거래 유형·매물 유형 코드일 때.
    """
    try:
        key_response = client.run_request_article_key_v1(
            NaverArticleKeyV1RequestParameterModel(article_number=article_number)
        )
    except HTTPStatusError as exc:
        # 매물 번호 형식이 아니면(너무 짧은 번호 등) 400 FST_ERR_VALIDATION 이다. 그런 매물은 없다.
        if exc.response.status_code in (400, 404):
            raise ListingUnavailableError('naver', article_number) from None
        raise
    if not key_response.is_success or key_response.result is None:
        raise ListingUnavailableError('naver', article_number)
    key = key_response.result
    trade_type = TRADE_NAME_BY_CODE.get(key.type.trade_type)
    if trade_type is None:
        # 모르는 거래 유형이면 가격을 어느 필드로 옮길지 몰라 틀린 값을 내게 된다. 목록에서 빼는 것과
        # 맞추고, 나머지 요청(basicInfo 등)도 보내지 않는다.
        raise ListingUnavailableError(
            'naver', article_number, status=key.type.trade_type, reason='UNKNOWN_TRADE_TYPE'
        )
    if key.type.real_estate_type not in KNOWN_REAL_ESTATE_TYPES:
        # 응답 값을 요청 모델(Literal)에 넣다 실패하면 handle_errors 가 사용자 입력 오류(INVALID_ARGUMENT)로 낸다.
        # 서버가 받는 유형 코드 밖이라 basicInfo 도 400 이므로, 모르는 거래 유형처럼 볼 수 없는 매물로 낸다
        raise ListingUnavailableError(
            'naver', article_number, status=key.type.real_estate_type, reason='UNKNOWN_REAL_ESTATE_TYPE'
        )
    return key, trade_type


def _article_basic(client: NaverClient, article_number: str, key: NaverArticleKeyModel) -> NaverArticleBasicInfoModel:
    """매물 기본 정보 (가격·면적·층·시설·단지).

    Raises:
        ListingUnavailableError: 없거나 내려간 매물일 때.
    """
    basic_response = client.run_request_article_basic_info_v1(
        NaverArticleBasicInfoV1RequestParameterModel(
            article_number=article_number,
            real_estate_type=key.type.real_estate_type,
            trade_type=key.type.trade_type,
        )
    )
    # 없거나 내려간 매물, 유형이 맞지 않는 요청 모두 404 가 아니라 200 + isSuccess=false 로 온다
    # (실제 API 로 확인). 그래서 article/key 와 달리 HTTPStatusError 를 따로 잡지 않는다.
    if not basic_response.is_success or basic_response.result is None:
        raise ListingUnavailableError('naver', article_number)
    return basic_response.result


def _listing_title(
    complex_info: NaverCommunalComplexInfoModel | None,
    article: NaverArticleDetailInfoModel | None,
) -> str:
    """단지 이름(없으면 매물 이름)·동과 매물 특징으로 제목을 만든다."""
    title_parts = [
        (complex_info.complex_name if complex_info else None) or (article.article_name if article else None),
        dong_label(complex_info.dong_name) if complex_info and complex_info.dong_name else None,
    ]
    title = ' '.join(part for part in title_parts if part)
    if article and article.article_feature_description:
        title = f'{title} · {article.article_feature_description}' if title else article.article_feature_description
    return title


def _jibun_address(
    client: NaverClient,
    key: NaverArticleKeyModel,
    coordinates: NaverCoordinatesModel | None,
) -> str | None:
    """좌표로 얻은 법정동 이름과 article/key 의 지번을 합친 주소. 좌표가 없거나 법정동 조회가 실패하면 None.

    article/key 에는 법정동 코드만 있고 이름이 없어 좌표로 이름을 찾는다. 좌표로 찾은 동이 article/key 의 동과 달라
    옆 동 이름에 지번이 붙는 일은 실측으로 없었다 (2026-10-12 실측: 서울 중구 회현동·예장동·남학동, 종로구 운니동·낙원동·
    경운동 등 원룸·빌라·단독·다가구 20건 모두 두 법정동 코드가 같음). 2026-10-12 리뷰 오탐 확인
    """
    if coordinates is None:
        return None
    division = result_or_none(lambda: client.run_request_legal_division_search_by_coordinate_v1(
        NaverLegalDivisionSearchByCoordinateV1RequestParameterModel(
            latitude=coordinates.y_coordinate,
            longitude=coordinates.x_coordinate,
        )
    ))
    if division is None:
        return None
    return join_address(
        division.legal_division_name,
        key.address.jibun if key.address else None,
    )
