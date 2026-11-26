"""매물 상세 (listing)."""

import re
from decimal import (
    ROUND_FLOOR,
    Decimal,
)

from httpx import HTTPStatusError

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    iso_date,
    join_address,
    m2_to_pyeong,
    move_in_label,
    normalize_address,
    normalize_date,
    note,
    null_items_note,
    parking_label,
    read_date,
    with_negotiable,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongV1RequestParameterModel,
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
    NaverRealEstateType,
)
from jibsa.providers.naver.api.request.listing.detail import (
    NaverArticleAgentFeeV1RequestParameterModel,
    NaverArticleBasicInfoV1RequestParameterModel,
    NaverArticleKeyV1RequestParameterModel,
    NaverArticleMaintenanceFeeV1RequestParameterModel,
    NaverArticleOldMaintenanceFeeV1RequestParameterModel,
    NaverArticleTaxV1RequestParameterModel,
    NaverComplexBuildingRegistrationV1RequestParameterModel,
    NaverDataServiceTransportV1RequestParameterModel,
    NaverDevelopmentArticleV1RequestParameterModel,
    NaverEducationBuildingSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.region import (
    NaverLegalDivisionInfoListV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import (
    NaverComplexModel,
    NaverFacilityInfoModel,
    NaverResponseModel,
)
from jibsa.providers.naver.api.response.listing.detail import (
    NaverArticleBasicInfoModel,
    NaverArticleDetailInfoModel,
    NaverArticleKeyModel,
    NaverArticleMaintenanceFeeModel,
    NaverArticleOldMaintenanceFeeModel,
    NaverDevelopmentArticleModel,
    NaverMovingInInfoModel,
    NaverPriceInfoModel,
    NaverSpaceInfoModel,
    NaverTransportSubwayModel,
)
from jibsa.providers.naver.service.common.functions import (
    ENTRANCE_CODE_BY_NAME,
    OFFICETEL_CODE,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
    OPTIONAL_LOOKUP_ERRORS,
    PROPERTY_NAME_BY_CODE,
    TRADE_NAME_BY_CODE,
    VILLA_COMPLEX_CODES,
    add_failure_note,
    article_url,
    assigned_schools,
    building_approved_at,
    dong_label,
    known_floor,
    listing_badges,
    result_or_empty,
    result_or_none,
    unknown_code_label,
)
from jibsa.providers.naver.service.common.models import (
    NOT_APPLICABLE_FIELDS_BY_TYPE,
)
from jibsa.providers.naver.service.listing.models import (
    ALL_TAX_TYPES,
    SALE_TAX_FIELDS,
    NaverListingDetail,
    NaverNearbyArea,
    NaverNearbyDevelopment,
    NaverNearbyRail,
    _draws_sale_taxes,
)

from typing import (
    Any,
    NamedTuple,
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


# 입주 시기 코드 (네이버 웹 번들의 ARTICLE_MOVING_IN_TYPE 과 대조, 2026-11-16): MV001 즉시입주, MV002 이내입주,
# MV003 이후입주, MV004 지정날짜. EARLY / MID / LATE 는 movingInDate 의 달 초순·중순·하순이다.
MOVING_IN_LABELS: dict[str, str] = {
    'MV001': '즉시입주',
}


# 웹은 '2026년 12월 01일 이내입주' 처럼 날짜 뒤에 이내·이후를 붙여 보여 준다. 날짜만 내면 둘이 구분되지 않는다
MOVING_IN_BOUND_LABELS: dict[str, str] = {
    'MV002': '이내',
    'MV003': '이후',
}


MOVING_IN_PERIOD_LABELS: dict[str, str] = {
    'EARLY': '초순',
    'MID': '중순',
    'LATE': '하순',
}


# 기간 코드(초순·중순·하순)는 달만 있으면 돼 연월만 온 날짜(2026-11·202611·2026.11)도 받는다
YEAR_MONTH_PATTERN: re.Pattern[str] = re.compile(r'^(\d{4})[-./]?(\d{2})$')


# 관리비 확인 불가 사유 코드 중 '없음' (웹 번들의 UNABLE_CHECK_DETAIL_CODE_TYPE, 2026-11-16)
MANAGE_COST_NONE_REASON: str = '99'


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


# 시설 코드 이름. 2026-11-17 네이버 웹 번들의 시설 이름 표와 똑같이 화면 글자 그대로 쓴다. 그 뒤 네이버가 더한 코드는 이 표에
# 없어 '알 수 없는 시설 (코드)' 로 낸다 (2026-10-24: 사설경비·에어컨·가스오븐·소파가 빠져 PRIVATE_SECURITY 같은 영어 코드가 options 에 그대로 나갔다).
# ELEVATOR 는 options 가 아니라 has_elevator 로 낸다
# 리뷰 오탐 (2026-11-17): 직방·당근의 options 글자(인덕션 등)와 다르다. options 는 소스끼리 글자를 맞추는 약속이 없고
# 네이버는 화면 글자를 따른다
# 리뷰 오탐 (2026-11-17): 표에서 지운 DRESSING_TABLE·DRYER·GAS_RANGE·OVEN·ROOF_TOP·CENTRAL·DOOR_LOCK 은 첫 커밋의 추정 이름이고 웹 시설 표(ARTICLE_FACILITY_*)에 없다
FACILITY_LABELS: dict[str, str] = {
    # 생활시설
    'AIRCON': '에어컨',
    'BATHTUB': '욕조',
    'BED': '침대',
    'BIDET': '비데',
    'BUILT_IN_CLOSET': '붙박이장',
    'CLOSET': '옷장',
    'CLOTHES_DRYER': '건조기',
    'DESK': '책상',
    'DINING_TABLE': '식탁',
    'DISH_WASHER': '식기세척기',
    'GAS_OVEN': '가스오븐',
    'GAS_STOVE': '가스레인지',
    'INDUCTION_RANGE': '인덕션레인지',
    'MICROWAVE': '전자레인지',
    'REFRIGERATOR': '냉장고',
    'SHOE_RACK': '신발장',
    'SOFA': '소파',
    'SHOWER_BOOTH': '샤워부스',
    'SINK': '싱크대',
    'TV': 'TV',
    'WASHING_MACHINE': '세탁기',
    # 보안시설
    'GUARD': '경비원',
    'VIDEO_PHONE': '비디오폰',
    'INTER_PHONE': '인터폰',
    'PRIVATE_SECURITY': '사설경비',
    'CARD_KEY': '카드키',
    'CCTV': 'CCTV',
    'ENTRANCE_SECURITY': '현관보안',
    'SECURITY_WINDOW': '방범창',
    # 기타시설
    'FIRE_ALARM': '화재경보기',
    'VERANDA': '베란다',
    'TERRACE': '테라스',
    'YARD': '마당',
    'DELIVERY_BOX': '무인택배함',
    # 냉방시설
    'WALL': '벽걸이에어컨',
    'STAND': '스탠드에어컨',
    'CEILING': '천장에어컨',
}


# 난방 방식·난방 연료·현관 구조 코드 (네이버 웹 번들 대조, 2026-11-17). 웹은 난방 한 칸에 '개별난방 / 도시가스' 로 이어 보여 주지만
# jibsa 는 방식(heating)과 연료(heating_fuel)를 따로 낸다
HEATING_LABELS: dict[str, str] = {
    'HT001': '개별난방',
    'HT002': '중앙난방',
    'HT003': '개별냉난방',
    'HT004': '중앙냉난방',
    'HT005': '지역난방',
    'HT006': '지역냉난방',
}


HEATING_FUEL_LABELS: dict[str, str] = {
    'HF001': '도시가스',
    'HF002': '열병합',
    'HF003': '기름',
    'HF004': '전기',
    'HF005': '심야전기',
    'HF006': '태양열',
    'HF007': 'LPG',
    'HF008': '지열',
}


# 네이버 표의 이름이 '미노출' 인 난방 코드. 중개사가 알리지 않은 것이라 값이 없는 것과 같아 모름(null)으로 낸다
UNDISCLOSED_HEATING_CODES: frozenset[str] = frozenset({'HT000', 'HF000'})


ENTRANCE_LABELS: dict[str, str] = {code: name for name, code in ENTRANCE_CODE_BY_NAME.items()}


# 웹이 난방·현관·주차를 매물이 아니라 단지 값으로 채우는 단지 유형: 아파트 A01·오피스텔 A02·재건축 A04·아파트분양권 B01·
# 오피스텔분양권 B02 (웹 isComplexType, 2026-11-17 번들 청크 0l4pkwg0qhg2t 의 ArticleComplexInfo). 단지형 빌라(A05~A07,
# `VILLA_COMPLEX_CODES`)는 다른 화면(ArticleVillaBuildingInfo)이라 규칙이 다르다 (`_facility_values`)
COMPLEX_INFO_TYPES: frozenset[str] = frozenset({'A01', 'A02', 'A04', 'B01', 'B02'})


# 웹이 건축물 정보 칸을 그리는 건축물대장 유형 15개 (웹 isBuildingRegistrationType, 2026-11-18 번들 청크 0l4pkwg0qhg2t 의
# ArticleBuildingInfo, 번들 REAL_ESTATE_TYPE 대조). 매물에 주차 대수가 없을 때 건축물대장 대수로 채우는 유형이다 (`_building_parking`)
BUILDING_REGISTRATION_TYPES: frozenset[str] = frozenset({
    'C01', 'C02', 'C03', 'C04', 'C06',
    'D01', 'D02', 'D03', 'D04', 'D05',
    'E01', 'E02', 'E04', 'F01', 'Z00',
})


# 건물 세부 유형 코드 (articleDetailInfo.buildingType). 네이버 웹 번들의 ARTICLE_BUILDING_TYPE_MAP 과 같다 (2026-11-17 대조)
BUILDING_TYPE_LABELS: dict[str, str] = {
    'C0101': '일반원룸',
    'C0102': '빌라다세대',
    'C0103': '다가구',
    'C0104': '오피스텔',
    'C0105': '원룸형 아파트',
    'C0106': '기타',
    'C0107': '도시형생활주택',
    'C0108': '일반원룸',
    'C0109': '빌라다세대',
    'C0110': '다가구',
    'C0111': '오피스텔',
    'C0112': '도시형생활주택',
    'C0113': '기타',
    'C0201': '다세대',
    'C0202': '연립',
    'C0203': '빌라',
    'C0204': '기타',
    'C0301': '단독',
    'C0302': '다가구',
    'C0401': '전원주택',
    'C0402': '농가',
    'C0403': '별장',
    'C0404': '펜션',
    'C0601': '한옥주택',
    'C0602': '한옥주택',
    'D0101': '대형사무실',
    'D0102': '중소형사무실',
    'D0103': '공동사무실',
    'D0104': '오피스텔',
    'D0105': '일반사무실',
    'D0201': '단지내상가',
    'D0202': '지하상가',
    'D0203': '일반상가',
    'D0204': '복합상가',
    'D0301': '빌딩',
    'D0302': '상가건물',
    'D0303': '상가주택',
    'D0304': '숙박시설',
    'D0305': '상업시설',
    'D0306': '레저/스포츠/위락',
    'D0307': '특수시설',
    'D0308': '기타',
    'E0101': '여관/모텔',
    'E0102': '호텔',
    'E0103': '콘도',
    'E0104': '펜션',
    'E0105': '기타',
    'E0106': '모텔',
    'E0107': '여관/모텔/호텔',
    'E0201': '공장',
    'E0202': '창고',
    'E0203': '지식산업센터',
    'E0204': '기타',
    'E0301': '전',
    'E0302': '답',
    'E0303': '과수원',
    'E0304': '목장용지',
    'E0305': '임야',
    'E0306': '광천지',
    'E0307': '염전',
    'E0308': '대',
    'E0309': '공장용지',
    'E0310': '학교용지',
    'E0311': '주차장',
    'E0312': '주유소용지',
    'E0313': '창고용지',
    'E0314': '도로',
    'E0315': '철도용지',
    'E0316': '제방',
    'E0317': '하천',
    'E0318': '구거',
    'E0319': '유지',
    'E0320': '양어장',
    'E0321': '수도용지',
    'E0322': '공원',
    'E0323': '체육용지',
    'E0324': '유원지',
    'E0325': '종교용지',
    'E0326': '사적지',
    'E0327': '묘지',
    'E0328': '잡종지',
    'E0329': '기타',
    'F0101': '단독',
    'F0102': '다가구',
    'F0103': '다세대',
    'F0104': '연립빌라',
    'F0105': '기타',
    'F0106': '단독/다가구',
    'F0107': '다세대/연립',
}


# 웹 제목은 건물 이름 뒤에 건물 하위 이름(nonComplexBuildingSubName)을 붙이는 매물이 정해져 있다 (getArticleNameParts, 2026-11-17
# 번들 대조). 매물 유형이 C01·D05 이거나, 매물 유형과 건물 세부 유형이 이 표의 짝일 때뿐이고 그 밖에는 건물 이름만 쓴다
BUILDING_SUB_NAME_REAL_ESTATE_TYPES: frozenset[str] = frozenset({'C01', 'D05'})


BUILDING_SUB_NAME_BUILDING_TYPES: dict[str, frozenset[str]] = {
    'C02': frozenset({'C0202', 'C0203'}),
    'C03': frozenset({'C0302'}),
}


# 웹 매물 화면의 위치 칸(ArticleBuildingInfo, 번들 청크 0l4pkwg0qhg2t)은 매물 유형이 이 표에 있으면 지번을 articleDetailInfo.isJibunAddressExposed
# 가 true 일 때만 보인다 (없으면 숨김). 표에 없는 유형은 건물 세부 유형이 단독(C0301)일 때만 그 값을 따르고 나머지는 늘 보인다
JIBUN_EXPOSURE_REAL_ESTATE_TYPES: frozenset[str] = frozenset({
    'D01', 'D02', 'D03', 'D04', 'E01', 'E02', 'E03', 'E04', 'F01', 'Z00', 'C04', 'C06',
})


JIBUN_EXPOSURE_BUILDING_TYPE: str = 'C0301'


class _FacilityValues(NamedTuple):
    """난방·난방 연료·현관 구조·주차 (`NaverListingDetail` 의 같은 이름 필드)."""

    heating: str | None
    heating_fuel: str | None
    entrance: str | None
    parking: str | None


def _sum_manwon(*amounts: int | None) -> float | None:
    """원 단위 금액들의 합을 만원으로. 모두 모르면 None.

    아는 항목만 더한다. 네이버 세금 응답은 면제 항목도 null 이 아니라 0 으로 줘서 일부만 null 인 응답은 없다
    (헬리오시티 39~150㎡·일신동 빌라 6건, 2026-10-11). 일부만 null 이 오면 응답 형식이 바뀐 것이다.
    """
    known = [amount for amount in amounts if amount is not None]
    return won_to_manwon(sum(known)) if known else None


def _agent_fee(client: NaverClient, article_number: str, notes: list[str]) -> dict[str, Any]:
    """중개보수 상한(`broker_fee_manwon`, 만원)과 '개별확인' 여부 (1회 호출). 직거래가 아니면 모든 거래 유형에서 조회한다 (웹도 월세 매물에 '최대 28만원' 을 보여 준다).

    네이버 웹은 `isIndividualCheckRequired` 가 참이면 금액 대신 '개별확인' 을 그리므로 금액은 None 이고 여부가 True 다.
    플래그가 없거나 거짓이면 웹도 금액을 그린다. 조회가 실패하면 둘 다 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다.
    금액(fee)이 비어 오고 플래그가 참이 아니면 broker_fee_manwon 만 None 이고 여부는 False 다. 웹(ArticleRealtorFee)도
    그때 '개별확인' 이 아니라 금액 줄을 그린다 (리뷰 오탐, 2026-11-17).
    """
    fee = result_or_none(
        lambda: client.run_request_article_agent_fee_v1(
            NaverArticleAgentFeeV1RequestParameterModel(article_number=article_number)
        ),
        notes=notes,
        what='중개보수',
        unknown='모름(null)으로 낸 칸: broker_fee_manwon, broker_fee_individual_check_required',
    )
    if fee is None:
        return {'broker_fee_manwon': None, 'broker_fee_individual_check_required': None}
    individual = fee.is_individual_check_required is True
    return {
        'broker_fee_manwon': None if individual else won_to_manwon(fee.fee),
        'broker_fee_individual_check_required': individual,
    }


def _sale_taxes(
    client: NaverClient,
    article_number: str,
    real_estate_type: str,
    notes: list[str],
) -> dict[str, float | None]:
    """매매 매물의 세금 (1회 호출). 조회가 실패하면 그 값만 모름(None)으로 두고 `notes` 에 `[실패]` 안내를 붙인다.

    안내에 적는 칸은 출력에 남는 칸이다. 세 세금을 모두 그리는 유형(`ALL_TAX_TYPES`) 밖은 취득세만 남고 나머지 둘은 키를 뺀다
    (`NaverListingDetail.not_applicable_fields`).
    """
    costs: dict[str, float | None] = dict.fromkeys(SALE_TAX_FIELDS)
    unknown = (
        '모름(null)으로 낸 칸: acquisition_tax_manwon, property_tax_manwon, comprehensive_real_estate_tax_manwon'
        if real_estate_type in ALL_TAX_TYPES else '모름(null)으로 낸 칸: acquisition_tax_manwon'
    )
    tax = result_or_none(
        lambda: client.run_request_article_tax_v1(
            NaverArticleTaxV1RequestParameterModel(article_number=article_number)
        ),
        notes=notes,
        what='세금',
        unknown=unknown,
    )
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


def _surroundings(client: NaverClient, article_number: str, key: NaverArticleKeyModel, notes: list[str]) -> dict[str, Any]:
    """매물 주변의 지하철역·버스 노선·배정 초등학교 (1~2회 호출).

    학교는 사이트처럼 단지·동 번호가 있는 매물만 묻는다 (`has_school_lookup`. 없으면 출력에서 키를 뺀다).
    조회가 실패하거나 교통이 통째로 비어 있으면 그 값만 모름(None)으로 둔다. 조회가 실패했을 때만 `notes` 에 `[실패]` 안내를 붙인다
    (교통이 비어 온 것은 실패가 아니다).
    """
    result: dict[str, Any] = {'nearby_stations': None, 'bus_routes': None, 'schools': None, 'has_school_lookup': False}
    transport = result_or_none(
        lambda: client.run_request_data_service_transport_v1(
            NaverDataServiceTransportV1RequestParameterModel(item_id=int(article_number))
        ),
        notes=notes,
        what='교통 정보',
        unknown='모름(null)으로 낸 칸: nearby_stations, bus_routes',
    )
    # 역도 버스도 없으면 네이버에 교통 정보가 없는 매물이다 (역삼동 단지형 빌라에서 둘 다 빈 목록,
    # 2026-10-09 확인). 주변에 정말 아무것도 없다는 뜻이 아니라 모름(None)으로 둔다
    if transport is not None and (transport.subway_list or transport.bus_list):
        result['nearby_stations'] = [label for label in map(_subway_label, transport.subway_list) if label]
        # 버스 종류(간선·지선 등)는 네이버가 보내는 이름표 그대로 키로 쓴다. 거래 키(sale 등)와 달리 어떤 종류가 올지 미리 다 알 수
        # 없어, 영어로 바꾸려면 네이버에 없는 대응 표를 jibsa 가 지어야 한다 (출력 규약 '칸 이름 규칙' 의 예외)
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
    schools = result_or_none(
        lambda: client.run_request_education_building_school_v1(
            NaverEducationBuildingSchoolV1RequestParameterModel(
                item_type='villa' if key.type.real_estate_type in VILLA_COMPLEX_CODES else 'complex',
                complex_number=ids.complex_number,
                building_number=ids.building_number,
            )
        ),
        notes=notes,
        what='주변 학교',
        unknown='모름(null)으로 낸 칸: schools',
    )
    if schools is not None:
        result['schools'] = assigned_schools(schools, notes)
    return result


def _nearby_development(client: NaverClient, article_number: str, notes: list[str]) -> NaverNearbyDevelopment | None:
    """매물 근처의 예정 지하철역·개발 지구 (1회 호출). 웹은 매물 유형과 상관없이 늘 부른다. 조회가 실패하면 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다."""
    development: NaverDevelopmentArticleModel | None = result_or_none(
        lambda: client.run_request_development_article_v1(
            NaverDevelopmentArticleV1RequestParameterModel(article_number=article_number)
        ),
        notes=notes,
        what='주변 개발 예정',
        unknown='모름(null)으로 낸 칸: nearby_development',
    )
    if development is None:
        return None
    return NaverNearbyDevelopment(
        rail=[
            NaverNearbyRail(
                name=rail.station_name or None,
                line=rail.rail_name or None,
                # 개통 예정 연도 글자('2027')를 정수로. 비었거나 숫자가 아니면 None
                open_year=int(rail.open_date.strip()) if rail.open_date and rail.open_date.strip().isdecimal() else None,
                distance_m=rail.distance,
                walk_minutes=rail.walking_time,
            )
            for rail in development.rail_list
        ] if development.rail_list is not None else None,
        area=[
            NaverNearbyArea(
                name=area.name or None,
                type=area.type_name or None,
                # 단계는 숫자일 수 있어 `or None` 이면 0 이 모름으로 바뀐다. 빈 글자만 모름(None)으로 본다
                step=None if area.step == '' else area.step,
                project_period=area.period or None,
            )
            for area in development.jigu_list
        ] if development.jigu_list is not None else None,
    )


def _coded_label(labels: dict[str, str], code: str | None) -> str | None:
    """값 하나짜리 코드(방향·난방·현관·건물 세부 유형)의 글자. 코드가 없으면 모름(None), 표에 없으면 '알 수 없는 값 (코드)'.

    '미노출'(`UNDISCLOSED_HEATING_CODES`)은 중개사가 알리지 않은 것이라 모름(None)이다.
    """
    if not code or code in UNDISCLOSED_HEATING_CODES:
        return None
    return labels.get(code) or unknown_code_label('값', code)


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


def _year_month(value: str | None) -> str | None:
    """연월만 있는 글자(`2026-11`·`202611`·`2026.11`)를 `YYYY-MM` 으로 읽는다. 월이 1~12 가 아니거나 못 읽으면 None."""
    match = YEAR_MONTH_PATTERN.match((value or '').strip())
    if match is None or not 1 <= int(match.group(2)) <= 12:
        return None
    return f'{match.group(1)}-{match.group(2)}'


def _move_in_label(moving: NaverMovingInInfoModel | None, notes: list[str]) -> str | None:
    """입주 시기 코드를 읽을 수 있는 문구로 바꾼다.

    이내입주('MV002')·이후입주('MV003')는 날짜 뒤에 '이내'·'이후' 를 붙인다 (웹과 같다). 날짜 지정('MV004')·모르는 코드는
    날짜만 쓰고, 연월만 오면 연월('2026-12')을 쓴다. 코드('MV004')를 그대로 내보내지 않는다. 초순·중순·하순과 이내·이후는 연월만
    와도 만든다 ('2026-12 초순'·'2026-12 이내'. 이내·이후는 전체 날짜면 '2026-12-01 이내'). 날짜가 없으면('-'·빈 글자)
    웹처럼 협의 가능일 때만 '협의 가능', 아니면 모름(None)이다. 날짜는 있는데 못 읽으면 같은 값을 내고 `notes` 에 `[참고]` 안내를 붙인다
    (못 읽는 글자를 입주일로 내지 않는다).
    """
    if moving is None:
        return None
    code = moving.moving_in_type or ''
    date = (moving.moving_in_date or '').strip() or None
    if date == '-':
        # 날짜 자리의 '-' 는 값이 없다는 표시라 모름이다 (층의 '-' 와 같다, `known_floor`)
        date = None
    negotiable = moving.moving_in_negotiation
    day = iso_date(date)
    # 연월은 두 갈래가 같게 읽는다 (이내·이후만 전체 날짜를 요구하면 연월만 온 이내·이후입주가 '이내'·'이후' 를 잃는다)
    month = day[:7] if day is not None else _year_month(date)
    if code in MOVING_IN_PERIOD_LABELS and month is not None:
        return with_negotiable(f'{month} {MOVING_IN_PERIOD_LABELS[code]}', negotiable)
    if code in MOVING_IN_BOUND_LABELS and month is not None:
        return with_negotiable(f'{day or month} {MOVING_IN_BOUND_LABELS[code]}', negotiable)
    if code in MOVING_IN_LABELS:
        return move_in_label(MOVING_IN_LABELS[code], negotiable=bool(negotiable))
    if date is None:
        return '협의 가능' if negotiable else None
    label = day or month
    if label is None:
        if code in MOVING_IN_BOUND_LABELS:
            kind = f'{MOVING_IN_BOUND_LABELS[code]}입주'
        elif code == 'MV004':
            kind = '날짜 지정'
        else:
            kind = f'{MOVING_IN_PERIOD_LABELS[code]}입주' if code in MOVING_IN_PERIOD_LABELS else f'입주 유형 {code}' if code else '입주 유형 모름'
        notes.append(note('참고', f"네이버가 준 입주일을 읽지 못했습니다 ({kind}, 날짜 '{date}'). url 의 매물 화면에서 확인하세요"))
        return '협의 가능' if negotiable else None
    # 연월('2026-12')은 날짜로 읽지 못하는 꼴이라 `move_in_label` 에 넘기면 못 읽은 입주일로 모아 None 이 된다. day·month 는 이미 읽은 값이라 협의만 붙인다
    return with_negotiable(label, bool(negotiable))


def _manage_cost_item_label(code: str) -> str:
    """관리비 포함 항목 코드의 글자. 표에 없으면 '알 수 없는 항목 (코드)'."""
    return MANAGE_COST_ITEM_LABELS.get(code) or unknown_code_label('항목', code)


def _manage_cost(fee: NaverArticleMaintenanceFeeModel | None, notes: list[str]) -> tuple[float | None, list[str] | None]:
    """월 관리비(만원)와 관리비에 포함된 항목. 모르면 None.

    합계형(typeCode '02')은 etcDetail, 정액 합계형('04')은 같은 모양의 fixNonDetailList 의 금액과 포함 항목(categoryList)을
    쓴다. 0 은 중개사가 0원으로 입력한 것이다. '04' 는 원룸·빌라·오피스텔 16건 중 7건일 만큼 흔하다 (신림동, 2026-10-11).
    항목별형('01')은 웹처럼(번들 getMaintenanceFeeLabel: `fixDetailList.reduce((s, e) => s + (e.amount ?? 0), 0)`, 2026-11-18)
    정액·실비를 가리지 않고 모든 항목의 금액을 더해 합계로 본다. 실비 항목은 쓴 만큼 따로 내서 지금까지 본 응답에서는 모두 금액이
    null 이라 합계가 정액 항목의 합과 같다 (원룸 2653883790: 공용 10만원 정액, 전기~TV 실비 → 합계 10만원, 2026-10-10).
    포함 항목은 정액 항목(unitType '01')만 친다. 그래서 실비 금액이 모두 null 이고 항목이 모두 실비면 0만원·[] 이다.
    정액으로 내는 관리비가 0원이고 공과금은 따로 낸다는 뜻이라 모름(None)이 아니다 (docs/naver.md 의 manage_cost_includes 설명과 같은 규칙).
    미확인('03')은 etcDetail·fixNonDetailList 가 null 이고 uncheckDetail 로 사유가 와서 대개 모름이다 (빌라 2654619539·
    2653716463, 2026-10-11). 다만 사유가 '99'(없음)이면 웹이 관리비 '없음' 으로 보여 주므로 0만원·[] 이다 (직방의 '관리비
    없음' 과 같은 꼴, 웹 번들 getMaintenanceFeeLabel 대조 2026-11-16). 다른 사유('01'~'04')는 웹도 '확인 어려움' 이라 모름이다.
    사유가 없으면 웹이 옛 형식 관리비로 넘어가(`_has_fee_cell` 이 False) 호출부가 옛 형식 금액을 쓰고, 거기에도 금액이 없으면
    모름이다. 그래서 금액은 typeCode 를 따로 보지 않고 값이 온 키로 정한다. 세 키(etcDetail·fixNonDetailList·fixDetailList)
    중 하나만 오고 나머지는 null 이라(신림동 월세 29건: '04' 18·'02' 10·'01' 1, 2026-10-11) 객체가 있는지만 본다.
    금액 없는 빈 etcDetail 이 다른 키와 함께 오는 응답은 없었다.
    항목별형 목록에서 빈 항목(null)을 빼고 읽었으면 합계도 포함 항목도 모자랄 수 있어 둘 다 모름(None)이고 `notes` 에 `[제외]` 안내를 붙인다.
    """
    if fee is None:
        return None, None
    summary = fee.etc_detail or fee.fix_non_detail_list
    # 합계 객체는 금액이 수일 때만 쓴다. 금액이 없으면 웹도 이 값으로 칸을 그리지 않고 옛 형식 관리비로 넘어가므로(`_has_fee_cell`)
    # 포함 항목만 내지 않는다 (2026-11-24 리뷰: 금액 null·항목 목록이 온 응답에서 항목만 나가고 [실패] 안내와 어긋났다)
    if summary is not None and summary.amount is not None:
        codes = summary.category_list
        includes = None if codes is None else [_manage_cost_item_label(code) for code in codes]
        return won_to_manwon(summary.amount), includes
    dropped = fee.null_items('fix_detail_list')
    if dropped:
        notes.append(null_items_note('네이버 관리비 항목', dropped, ('manage_cost_manwon', 'manage_cost_includes')))
        return None, None
    if fee.fix_detail_list:
        fixed = [item for item in fee.fix_detail_list if item.unit_type == '01' and item.amount is not None]
        includes = [_manage_cost_item_label(item.type) for item in fixed if item.amount and item.type]
        return won_to_manwon(sum(item.amount or 0 for item in fee.fix_detail_list)), includes
    if fee.type_code == '03' and fee.uncheck_detail is not None and fee.uncheck_detail.type == MANAGE_COST_NONE_REASON:
        return 0.0, []
    return None, None


def _has_fee_cell(fee: NaverArticleMaintenanceFeeModel | None) -> bool:
    """웹이 maintenanceFee 만으로 '관리비' 칸을 그리는 응답인가 (`_manage_cost` 의 갈래와 같다).

    미확인('03')이면서 사유(uncheckDetail.type)가 있으면 사유 글자, 항목별형은 fixDetailList(빈 항목을 뺐으면 그 자리)가 있으면 합계,
    합계형('02')·정액 합계형('04')은 금액이 수일 때다. 못 만들면 웹은 옛 형식 관리비(`oldMaintenanceFee`)로 넘어간다.
    """
    if fee is None:
        return False
    if fee.type_code == '03' and fee.uncheck_detail is not None and fee.uncheck_detail.type:
        return True
    summary = fee.etc_detail or fee.fix_non_detail_list
    if summary is not None and summary.amount is not None:
        return True
    return bool(fee.fix_detail_list) or bool(fee.null_items('fix_detail_list'))


def _parking_label(facility: NaverFacilityInfoModel | None, in_complex: bool) -> str | None:
    """매물 상세(facilityInfo)의 주차 가능 여부와 총 주차 대수를 문구로 만든다 ('불가 (총 4대)', '단지 전체 398대').

    아파트·오피스텔·재건축·분양권(`COMPLEX_INFO_TYPES`)은 웹이 매물 주차 값을 쓰지 않아 이 함수를 거치지 않고, 단지형 빌라는
    매물 대수가 0 보다 클 때만 이 함수를 쓴다 (`_facility_values`). 단지 조회가 실패했고 매물 대수가 0 이거나 없으면
    이 함수를 거치지 않고 가능 여부만 낸다.
    건축물대장 유형(원룸·빌라·단독 등 `BUILDING_REGISTRATION_TYPES`)은 `_building_parking` 으로 가 이 함수를 거치지 않는다.
    이 함수는 단지형 빌라와, 마지막 갈래에 오는 단지 번호 없는 단지 유형·토지·고시원 등이 쓴다.
    대수가 있어도 이 매물은 주차 불가일 수 있어(2026-10-10 실측: 총 6대·불가) 가능 여부를
    앞에 붙인다. 단지 안(`in_complex`)일 때만 '단지 전체' 를 붙이고 아니면 '총' 이다. 0대는 모름이 아니라 0대다.
    """
    if facility is None:
        return None
    count = facility.total_parking_count
    count_text = None if count is None else f'{"단지 전체" if in_complex else "총"} {count}대'
    return parking_label(facility.is_parking_possible, count_text)


def _complex_overview(
    client: NaverClient,
    complex_number: int | None,
    real_estate_type: str,
    notes: list[str],
) -> NaverComplexModel | None:
    """난방·주차·사용승인일에 쓸 단지 정보. 단지 유형은 `/complex`, 단지형 빌라는 `/complex/villa` 를 한 번 받는다 (1회).

    그 밖의 유형이거나 단지 번호가 없으면 요청하지 않고 None, 조회가 실패해도 None 이다 (그 값만 모름). 실패하면 `notes` 에 `[실패]` 안내를
    붙인다. 안내에 적는 칸은 단지 값이 없어 달라지는 칸이다: 단지 유형은 사용승인일·주차가 null, 난방·난방 연료는 매물 값만 남고,
    단지형 빌라는 난방·난방 연료가 null, 주차는 매물 값만 남는다 (사용승인일은 동 목록을 따로 받아 그대로다, `_facility_values`·`_complex_approved_at`).
    """
    if complex_number is None:
        return None
    if real_estate_type in COMPLEX_INFO_TYPES:
        return result_or_none(
            lambda: client.run_request_complex_v1(
                NaverComplexV1RequestParameterModel(complex_number=complex_number)
            ),
            notes=notes,
            what='단지 정보',
            unknown='모름(null)으로 낸 칸: approved_date, parking. 단지 값 없이 낸 칸: heating, heating_fuel',
        )
    if real_estate_type in VILLA_COMPLEX_CODES:
        return result_or_none(
            lambda: client.run_request_complex_villa_v1(
                NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)
            ),
            notes=notes,
            what='단지 정보',
            unknown='모름(null)으로 낸 칸: heating, heating_fuel. 단지 값 없이 낸 칸: parking',
        )
    return None


def _complex_approved_at(
    client: NaverClient,
    complex_number: int | None,
    key: NaverArticleKeyModel,
    complex_: NaverComplexModel | None,
    notes: list[str],
) -> str | None:
    """단지의 사용승인일 (YYYY-MM-DD). 단지 유형은 늘, 그 밖의 유형은 매물 상세에 건물 날짜가 없을 때만 부른다 (`get_listing`. 사용승인일 칸이 없는 토지·고시원은 부르지 않는다).

    단지 유형(`COMPLEX_INFO_TYPES`)은 `_complex_overview` 가 받은 단지 정보(`complex_`)의 날짜를 쓴다 (같은 요청을 두 번 하지 않는다).
    빌라 단지(A05·A06·A07)는 아파트 단지 엔드포인트가 result=null 이라 빌라 동 목록에서 매물의 동
    (article/key 의 buildingNumber)을 찾아 그 동의 날짜를 쓴다. 빌라 단지 정보에는 날짜가 없는 단지가
    있고(진명하이츠 등), 동마다 날짜가 다른 단지도 있어서다 (성재하이빌 에이동 2003-08-11·비동
    2003-09-05, 2026-10-09 확인).

    단지 번호가 없거나 단지 조회가 실패하면(단지가 아닌 매물 등) 모름(None)이다. 이 함수가 보내는 조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다
    (단지 유형이 쓰는 `complex_` 의 실패 안내는 `_complex_overview` 가 붙인다).
    """
    if complex_number is None:
        return None
    if key.type.real_estate_type in VILLA_COMPLEX_CODES:
        building_number = key.key.building_number if key.key else None
        if building_number is None:
            return None
        buildings = result_or_none(
            lambda: client.run_request_complex_villa_building_list_v1(
                NaverComplexVillaBuildingListV1RequestParameterModel(complex_number=complex_number)
            ),
            notes=notes,
            what='사용승인일',
            unknown='모름(null)으로 낸 칸: approved_date',
        )
        building = next((item for item in buildings or [] if item.number == building_number), None)
        return normalize_date(building.use_approval_date) if building is not None else None
    if key.type.real_estate_type in COMPLEX_INFO_TYPES:
        return normalize_date(complex_.use_approval_date) if complex_ is not None else None
    other_complex = result_or_none(
        lambda: client.run_request_complex_v1(
            NaverComplexV1RequestParameterModel(complex_number=complex_number)
        ),
        notes=notes,
        what='사용승인일',
        unknown='모름(null)으로 낸 칸: approved_date',
    )
    return normalize_date(other_complex.use_approval_date) if other_complex is not None else None


def _complex_parking_text(complex_: NaverComplexModel | None, *, with_parentheses: bool) -> str | None:
    """단지 주차 대수 글자 ('단지 전체 12602대 (세대당 1.32대)'). 대수를 모르거나 단지 조회가 실패했으면 None.

    세대당 대수는 불필요한 0 없이 낸다 (1.32·0.5). 버려 0 이 되는 값(0.009)·0 은 '세대당 0대' 로 낸다 (웹 단지 쪽은 0 이어도 붙이고,
    건축물대장 쪽 `_building_parking` 은 붙이지 않는다). 세대당 대수가 없으면 대수만. `with_parentheses` 가 거짓이면 가능 여부 뒤 괄호 안에
    들어갈 꼴('단지 전체 8대, 세대당 0.5대')이다.
    """
    info = complex_.parking_info if complex_ else None
    if info is None or info.total_parking_count is None:
        return None
    text = f'단지 전체 {info.total_parking_count}대'
    per_household = info.parking_count_per_household
    if per_household is None:
        return text
    # 웹 ComplexParkingInfo(청크 00-c-lsvp5jax, 2026-11-25 번들 확인)는 floor(parkingCountPerHousehold ?? 0, 2) 를 조건 없이 '(세대당 N대)' 로 그리고,
    # 호출하는 ArticleComplexInfo 도 주차 칸을 조건 없이 넣는다. 그래서 버려 0 이 되는 값(0.009)·0 도 '세대당 0대' 로 낸다
    per_household = _floor_per_household(per_household) or 0
    return f'{text} ({_per_household_text(per_household)})' if with_parentheses else f'{text}, {_per_household_text(per_household)}'


def _per_household_text(per_household: float) -> str:
    """세대당 주차 대수 글자 ('세대당 0.5대'·'세대당 1대'). 불필요한 0 없이 낸다."""
    return f'세대당 {per_household:g}대'


def _floor_per_household(per_household: float | None) -> float | None:
    """세대당 주차 대수를 소수 둘째 자리 아래를 버려 정한다 (웹 lodash `floor(값 || 0, 2)`). 0 이거나 없으면 None.

    건축물대장 쪽 웹(ArticleBuildingInfo)은 이 값이 0 이면 '(세대당 N대)' 를 붙이지 않는다. 단지 쪽(`_complex_parking_text`)은 웹이 0 이어도 붙여
    이 함수가 None 을 주면 0 으로 쓴다. 버림은 십진 글자로 계산해 1.33 이 1.32 가 되지 않게 한다.
    """
    if not per_household:
        return None
    return float(Decimal(str(per_household)).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)) or None


def _building_parking(
    client: NaverClient,
    key: NaverArticleKeyModel,
    facility: NaverFacilityInfoModel | None,
    notes: list[str],
) -> str | None:
    """건축물대장 유형(`BUILDING_REGISTRATION_TYPES`)의 주차 ('가능 (총 8대, 세대당 0.5대)', 가능 여부를 모르면 '총 8대 (세대당 0.5대)').

    웹처럼 매물 주차 대수가 참(0 이 아닌 수)이면 매물 대수와 매물 세대당 대수를, 아니면 건축물대장 값을 쓴다 (대장은 1회 호출).
    대장에도 대수가 없으면 대수는 모름이라 가능 여부만 낸다. 세대당 대수가 0 이거나 없으면 붙이지 않는다.
    """
    possible = facility.is_parking_possible if facility else None
    # 총 주차 대수와 세대당 대수 (웹 ArticleBuildingInfo 의 `[W, J]`)
    if facility is not None and facility.total_parking_count:
        total = facility.total_parking_count
        per_household = _floor_per_household(facility.parking_count_per_household)
    else:
        # 건축물대장 조회가 실패했을 때만 `notes` 에 `[실패]` 안내를 붙인다 (pnu 가 없거나 대장에 대수가 없는 것은 실패가 아니다).
        # 웹(ArticleBuildingInfo)은 pnu 가 없으면 이 요청을 보내지 않는다 (`enabled: !!pnu`). 0 대도 대수라 그대로 쓴다.
        pnu = key.key.pnu if key.key else None
        registration = None
        if pnu:
            registration = result_or_none(
                lambda: client.run_request_complex_building_registration_v1(
                    NaverComplexBuildingRegistrationV1RequestParameterModel(pnu=pnu, real_estate_type=key.type.real_estate_type)
                ),
                notes=notes,
                what='건축물대장 주차 대수',
                unknown='주차 대수 없이 낸 칸: parking',
            )
        info = registration.parking_info if registration else None
        if info is None or info.total_parking_count is None:
            return parking_label(possible)
        total = info.total_parking_count
        per_household = _floor_per_household(info.parking_count_per_household)
    # 웹 건축물 정보(ArticleBuildingInfo)는 '주차 N대' 하나뿐이라 매물 대수도 '단지 전체' 없이 늘 '총' 이다
    detail = f'총 {total}대'
    if per_household is not None:
        # 가능 여부가 있으면 그 뒤 괄호 안에 함께 넣고, 없으면 대수가 앞이라 세대당을 괄호로 붙인다
        per_household_text = _per_household_text(per_household)
        detail = f'{detail}, {per_household_text}' if possible is not None else f'{detail} ({per_household_text})'
    return parking_label(possible, detail)


def _facility_values(
    client: NaverClient,
    key: NaverArticleKeyModel,
    facility: NaverFacilityInfoModel | None,
    complex_number: int | None,
    complex_: NaverComplexModel | None,
    notes: list[str],
) -> _FacilityValues:
    """난방·난방 연료·현관 구조·주차. 웹 화면이 매물 유형마다 값을 가져오는 곳이 달라 같은 곳에서 가져온다 (0~1회 호출).

    웹 근거 (2026-11-17 번들 청크 0l4pkwg0qhg2t, 화면 실측):
    - 단지 유형(`COMPLEX_INFO_TYPES`, ArticleComplexInfo): 난방·연료는 `facilityInfo?.heatingAndCoolingSystemType ||
      complex.heatingAndCoolingInfo?.heatingAndCoolingSystemType` (연료도 따로 같은 꼴)이라 매물 값이 비면(빈 글자도, JS `||`)
      단지 값을 쓴다. 현관은 `facilityInfo?.entranceType || complexPyeong.entranceType` 이라 매물 값이 비어 있고 평형 번호가 있을 때만
      `/complex/pyeong` 을 부른다. 주차는 단지 parkingInfo 만 쓰고 매물 주차 값과 '주차가능여부' 칸은 없어 가능 여부를 붙이지
      않는다. 헬리오시티 2662350994 는 매물 난방이 비고 단지(111515)의 heatingAndCoolingInfo 가 {HT005, HF002} 라 웹이
      '지역난방 / 열병합', 주차 '12,602대 (세대당 1.32대)' (매물 값은 12456). 오피스텔 2661748606 은 매물 현관이 비고
      평형(189377, 4)의 entranceType 이 '10' 이라 웹 '계단식'이다.
    - 단지형 빌라(`VILLA_COMPLEX_CODES`, ArticleVillaBuildingInfo): 난방·연료는 `/complex/villa` 의 heatingAndCoolingInfo 만 쓴다
      (매물 facilityInfo 는 보지 않는다). 주차는 매물 totalParkingCount 가 0 보다 크면 매물 값, 아니면 단지 parkingInfo 이고
      주차가능여부 칸은 매물 값이다. 2661158391(A06, 단지 479920)은 매물이 0대·가능이라 웹이 '주차 8대 (세대당 0.5대)',
      '주차가능여부 가능' 이고 jibsa 는 '가능 (단지 전체 8대, 세대당 0.5대)' 로 낸다. 현관 구조는 건드리지 않는다.
    - 건축물대장 유형(`BUILDING_REGISTRATION_TYPES` 15개, ArticleBuildingInfo): 주차 대수는 매물 totalParkingCount 가 참(0 이 아닌 수)이면
      매물 값, 아니면(0·null·facilityInfo 없음) `GET /complex/buildingRegistration?pnu=&realEstateType=` 의 parkingInfo.totalParkingCount
      이고, 그 값이 수(0 포함)일 때만 '주차 N대' 칸을 그린다. 세대당 대수도 같은 쪽의 `parkingCountPerHousehold` 를 소수 둘째 자리까지 버린 값
      (lodash `floor(값 || 0, 2)`)이고, 0 이면 '(세대당 N대)' 를 붙이지 않는다 (번들 `L` 은 lodash floor 다, 2026-11-18).
      웹은 '주차가능여부'(매물 값)와 '주차 N대 (세대당 M대)' 두 칸으로 그리고 jibsa 는 '가능 (총 8대, 세대당 0.5대)' 로 합친다
      (가능 여부를 모르면 '총 8대 (세대당 0.5대)', 세대당이 0·없음이면 '가능 (총 8대)').
      pnu 는 article/key 의 key.pnu 고, 없으면 웹도 요청하지 않는다. 원룸 2661724695 는 매물이 0대·불가이고 대장이 0대라 웹이 '주차 0대',
      2661862868 은 매물이 8대라 대장을 부르지 않는다. 대장 조회가 실패하거나 대수가 없으면 대수는 모름이라 가능 여부만 낸다 (`_building_parking`).
    그 밖의 유형은 매물 값 그대로다. 단지 조회(`complex_`)가 실패하면 그 값만 모름이다 (단지형 빌라 주차는 매물 대수가 0 보다 클 때만 매물 값이고, 0 이거나 없으면 대수 없이 가능 여부만 낸다).
    이 함수가 보내는 조회(평형·건축물대장)가 실패하면 `notes` 에 `[실패]` 안내를 붙인다 (`complex_` 의 실패 안내는 `_complex_overview` 가 붙인다).
    """
    real_estate_type = key.type.real_estate_type
    system = facility.heating_and_cooling_system_type if facility else None
    energy = facility.heating_energy_type if facility else None
    entrance = facility.entrance_type if facility else None
    heating_info = complex_.heating_and_cooling_info if complex_ else None
    complex_system = heating_info.heating_and_cooling_system_type if heating_info else None
    complex_energy = heating_info.heating_energy_type if heating_info else None

    if complex_number is not None and real_estate_type in COMPLEX_INFO_TYPES:
        pyeong_number = key.key.pyeong_type_number if key.key else None
        if not entrance and pyeong_number:
            pyeong = result_or_none(
                lambda: client.run_request_complex_pyeong_v1(
                    NaverComplexPyeongV1RequestParameterModel(complex_number=complex_number, pyeong_type_number=pyeong_number)
                ),
                notes=notes,
                what='현관 구조',
                unknown='모름(null)으로 낸 칸: entrance',
            )
            entrance = pyeong.entrance_type if pyeong else None
        return _FacilityValues(
            heating=_coded_label(HEATING_LABELS, system or complex_system),
            heating_fuel=_coded_label(HEATING_FUEL_LABELS, energy or complex_energy),
            entrance=_coded_label(ENTRANCE_LABELS, entrance),
            parking=_complex_parking_text(complex_, with_parentheses=True),
        )
    if complex_number is not None and real_estate_type in VILLA_COMPLEX_CODES:
        if facility is not None and (facility.total_parking_count or 0) > 0:
            parking = _parking_label(facility, True)
        elif complex_ is None:
            # 매물 대수 0 은 웹이 단지 대수로 바꿔 그리는 '모름' 이라, 단지 값도 없으면 대수 없이 가능 여부만 낸다 (2026-11-24 리뷰: '가능 (단지 전체 0대)' 가 나갔다)
            parking = parking_label(facility.is_parking_possible if facility else None)
        else:
            # 가능 여부를 모르면 parking_label 이 대수 글자만 돌려주므로 단지 유형과 같은 괄호 꼴로 낸다
            possible = facility.is_parking_possible if facility else None
            parking = parking_label(possible, _complex_parking_text(complex_, with_parentheses=possible is None))
        return _FacilityValues(
            heating=_coded_label(HEATING_LABELS, complex_system),
            heating_fuel=_coded_label(HEATING_FUEL_LABELS, complex_energy),
            entrance=_coded_label(ENTRANCE_LABELS, entrance),
            parking=parking,
        )
    # 건축물대장 유형은 웹이 매물 대수가 0 이어도 쓰지 않고 대장 대수만 '주차 N대' 로 그린다. 대장에 대수가 없으면 칸이 없어 가능 여부만 낸다 ('총 0대' 를 내지 않는다)
    parking = (
        _building_parking(client, key, facility, notes)
        if real_estate_type in BUILDING_REGISTRATION_TYPES
        # 여기 오는 유형 중 단지 번호가 있는 것은 토지·고시원뿐이고 둘은 나중에 parking 키를 지운다 (common.py). 그래서 단지 안이 아니다
        # (근거: 2026-11-18 가산동·신림동 목록 160건과 지식산업센터 2662172371 에는 단지 번호가 없었다)
        else _parking_label(facility, False)
    )
    return _FacilityValues(
        heating=_coded_label(HEATING_LABELS, system),
        heating_fuel=_coded_label(HEATING_FUEL_LABELS, energy),
        entrance=_coded_label(ENTRANCE_LABELS, entrance),
        parking=parking,
    )


def get_listing(client: NaverClient, article_number: str) -> NaverListingDetail:
    """매물 상세: key → basicInfo → maintenanceFee → 법정동 코드의 지역 이름 → 단지·중개보수·세금·교통·학교·개발 예정 (최대 12회 호출, 단지부터는 필요할 때만).

    관리비는 maintenanceFee 로 '관리비' 칸을 못 만들 때(응답이 비었거나 실패, 금액·사유 없음)만 옛 형식 관리비(`oldMaintenanceFee`)를 1회 더 받아
    금액을 채운다 (상가 등, 웹도 그렇게 그린다). 포함 항목은 몰라 null 이다.

    단지는 아파트·오피스텔·재건축·분양권이면 단지 정보(`/complex`)를, 단지형 빌라면 `/complex/villa` 를 늘 받아 난방·주차를 웹처럼
    단지 값으로 채우고, 거기에 아파트·오피스텔·재건축·분양권은 매물에 현관 구조가 없을 때
    평형(`/complex/pyeong`), 단지형 빌라는 건물 날짜가 없을 때 동 목록(buildingList)을 더 받는다 (1~2회, `_facility_values`).
    그 밖의 유형은 단지 번호가 있고 건물 날짜가 없을 때만 단지 정보를 받는다 (사용승인일 칸이 없는 토지·고시원은 받지 않는다).

    중개보수(agentFee)는 직거래가 아니면(직거래이거나 직거래인지 모를 때는 조회하지 않는다) 모든 거래 유형에서, 세금(tax)은 매매 매물만 더 조회한다
    (원룸·고시원 매매, 일반분양권이 아니거나 분양 상태를 모르는 분양권은 조회하지 않는다) (1회 더, 매매는 2회 더). 주변 교통(지하철·버스)은 늘,
    배정 초등학교는 단지·동 번호가 있는 매물만 더 조회한다 (1~2회 더). 주변 개발 예정(`development/article`)은 유형과 상관없이 늘
    1회 더 조회한다 (웹도 모든 매물 상세에 그린다). 최대 12회.
    건축물대장 유형(원룸·빌라 등 15개)은 매물 주차 대수가 0 이거나 없고 article/key 에 pnu 가 있을 때만 건축물대장(`/complex/buildingRegistration`)을
    1회 더 조회하고, 그 대수와 세대당 대수로 주차를 채운다 (`_facility_values`). 이 유형은 단지 정보를 받아도 1회뿐이라 최대 12회를 넘지 않는다.

    중개사 정보와 본문은 내보내지 않는다 (문의·상세 설명은 원 사이트에서). 주소는 웹 위치 칸처럼 article/key 의 법정동 코드로 받은
    지역 이름(`legalDivision/infoList`)에 리와 지번을 붙여 만든다 (`_jibun_address`). 이 조회는 article/key 에 법정동 코드가 있으면 좌표와
    상관없이 1회다 (전에는 좌표가 없으면 0회). 사용승인일은 단지 유형(아파트·오피스텔·재건축·분양권)이면 단지 정보(`/complex`)의
    날짜만 쓰고(웹처럼 매물 날짜는 보지 않는다), 단지형 빌라와 그 밖의 유형은 상세의 건물 날짜(facilityInfo)를 쓰되 없으면 단지형 빌라는
    동 목록(buildingList), 그 밖의 유형은 단지 정보에서 받는다.

    key·basicInfo 밖의 부가 조회(관리비·법정동·단지·중개보수·세금·교통·학교·개발 예정)는 실패하면 그 값만 모름(None)이고, 실패한 조회마다
    결과 `notes` 에 `[실패]` 안내가 붙는다 (같은 안내는 한 번만).

    Raises:
        ListingUnavailableError: 없거나 내려간 매물이거나, 모르는 거래 유형·매물 유형 코드일 때
            (reason UNKNOWN_TRADE_TYPE·UNKNOWN_REAL_ESTATE_TYPE, listing_status 에 원래 코드).
    """
    key, trade_type = _article_key(client, article_number)
    basic = _article_basic(client, article_number, key)
    notes: list[str] = []
    # 관리비 조회 실패 안내는 옛 형식 관리비로 금액을 얻으면 사실과 달라지므로(모름이 된 칸이 다르다) 바로 붙이지 않는다.
    # maintenanceFee 의 예외는 남겨 두고 옛 형식 조회가 끝난 뒤 붙인다
    fee_errors: list[Exception] = []

    def request_fee() -> NaverResponseModel[NaverArticleMaintenanceFeeModel]:
        try:
            return client.run_request_article_maintenance_fee_v1(
                NaverArticleMaintenanceFeeV1RequestParameterModel(article_number=article_number)
            )
        except OPTIONAL_LOOKUP_ERRORS as exc:
            fee_errors.append(exc)
            raise

    unknown_both = '모름(null)으로 낸 칸: manage_cost_manwon, manage_cost_includes'
    fee = result_or_none(request_fee, notes=None, what='관리비', unknown=unknown_both)
    # 웹 ArticlePriceInfo(청크 0l4pkwg0qhg2t)와 상가 2662726134 실측 (2026-11-24): 웹은 maintenanceFee·oldMaintenanceFee 를 늘 둘 다 부르고
    # 앞의 것으로 칸을 못 만들 때 뒤의 amount 로 '관리비 <금액>' 칸을 그린다. jibsa 는 앞의 것으로 칸을 못 만들 때만 부른다 (요청을 아낀다)
    old_fee: NaverArticleOldMaintenanceFeeModel | None = None
    old_notes: list[str] = []
    if not _has_fee_cell(fee):
        old_fee = result_or_none(
            lambda: client.run_request_article_old_maintenance_fee_v1(
                NaverArticleOldMaintenanceFeeV1RequestParameterModel(article_number=article_number)
            ),
            notes=old_notes,
            what='관리비',
            unknown=unknown_both,
        )
    # 리뷰 오탐 (2026-11-24): 옛 형식 금액 0 도 칸으로 낸다. 웹 isValidNumber(amount)(청크 414mp5_jlfont)는 0 도 수로 봐 '관리비 0원' 을 그린다
    # 리뷰 오탐 (2026-11-24): 두 조회가 서로 다른 이유로 실패하면 [실패] 가 두 줄이다. 두 요청의 실패를 각각 맞게 알리는 것이라 합치지 않는다
    old_amount = old_fee.amount if old_fee else None
    # maintenanceFee 가 예외로 실패했으면 안내를 먼저 붙인다. 옛 형식 금액을 받았으면 금액 칸은 채워졌고 포함 항목만 모름이다
    if fee_errors:
        add_failure_note(
            notes,
            fee_errors[0],
            '관리비',
            unknown_both if old_amount is None else '모름(null)으로 낸 칸: manage_cost_includes',
        )
    # 옛 형식 조회의 실패 안내는 금액을 못 얻었을 때만 붙인다 (금액을 얻었으면 실패가 아닌 것으로 읽힌다)
    if old_amount is None:
        for text in old_notes:
            if text not in notes:
                notes.append(text)

    price = basic.price_info
    detail = basic.detail_info
    article = detail.article_detail_info if detail else None
    space = detail.space_info if detail else None
    size = detail.size_info if detail else None
    moving = detail.moving_in_info if detail else None
    facility = detail.facility_info if detail else None
    complex_info = basic.communal_complex_info

    # 단지 이름(없으면 매물 이름)·동과 매물 특징으로 제목을 만든다
    title_parts = [
        (complex_info.complex_name if complex_info else None) or (article.article_name if article else None),
        dong_label(complex_info.dong_name) if complex_info and complex_info.dong_name else None,
    ]
    title = ' '.join(part for part in title_parts if part)
    if article and article.article_feature_description:
        title = f'{title} · {article.article_feature_description}' if title else article.article_feature_description
    move_in = _move_in_label(moving, notes)
    if old_amount is None:
        manage_cost, manage_cost_includes = _manage_cost(fee, notes)
    else:
        # 옛 형식은 금액뿐이라 포함 항목은 모른다 (웹도 항목을 보여 주지 않는다)
        manage_cost, manage_cost_includes = won_to_manwon(old_amount), None

    exclusive = size.exclusive_space if size else None
    # 상세의 supplySpace 는 오피스텔이면 계약면적이다 (평형표의 contractArea 와 같고 supplyArea 보다 크다).
    # 다른 유형은 공급면적 그대로다. 오피스텔 공급면적은 평형표를 더 조회해야 해 모름(None)으로 둔다.
    is_officetel = key.type.real_estate_type == OFFICETEL_CODE
    listed_area = size.supply_space if size else None
    coordinates = article.coordinates if article else None

    address = _jibun_address(client, key, article, notes)

    # communalComplexInfo 는 단지 매물에만 오고, 오면 complexNumber 가 article/key 의 단지 번호와 같다. 단지가 없는
    # 매물은 둘 다 비어 있다 (단독·다가구·빌라·원룸·단지형 빌라·오피스텔·아파트 10건, 2026-10-10 확인)
    complex_number = complex_info.complex_number if complex_info else (key.key.complex_number if key.key else None)

    facility_codes = (facility.life + facility.security + facility.etc + facility.aircon) if facility else []
    real_estate_type = key.type.real_estate_type
    verification = detail.verification_info if detail else None
    # 직거래 여부를 모르면(상세 정보를 못 읽었거나 값이 없으면) None 이다. 직거래에도 agentFee 가 금액을 주므로 모를 때는 요청하지 않는다
    is_direct_trade = article.is_direct_trade if article else None
    pre_sale_status_type = detail.pre_sale_status_type if detail else None
    # 단지 유형은 단지 정보를 한 번 받아 사용승인일·난방·주차가, 단지형 빌라는 난방·주차가 함께 쓴다 (단지형 빌라 사용승인일은 동 목록을 따로 받는다) (요청 순서: 법정동, 단지, 동 목록·평형, 건축물대장, agentFee ...)
    complex_ = _complex_overview(client, complex_number, real_estate_type, notes)
    if complex_number is not None and real_estate_type in COMPLEX_INFO_TYPES:
        # 웹(ArticleComplexInfo)은 단지 유형의 사용승인일을 단지 정보(useApprovalDate)에서만 그리고 매물 facilityInfo 날짜는 보지 않는다.
        # 단지 조회가 실패해 complex_ 가 None 이면 모름이다 (매물 날짜로 대신하지 않는다)
        approved_at = _complex_approved_at(client, complex_number, key, complex_, notes)
    elif 'approved_date' in NOT_APPLICABLE_FIELDS_BY_TYPE.get(real_estate_type or '', frozenset()):
        # 토지·고시원은 사용승인일 칸이 없어(출력에서 키를 뺀다) 받을 값이 없다. 단지 조회를 부르면 요청만 쓰고, 실패하면
        # 출력에 없는 칸을 모름이라고 안내하게 된다 (2026-11-19 사용자 결정)
        approved_at = None
    else:
        approved_at = building_approved_at(facility) or _complex_approved_at(client, complex_number, key, complex_, notes)
    approved_at = read_date(approved_at, '사용승인일')
    facility_values = _facility_values(client, key, facility, complex_number, complex_, notes)

    # 웹 제목의 건물 이름. 건물 이름이 없으면 None. 건물 하위 이름은 매물 유형이 C01·D05 이거나
    # (유형, 건물 세부 유형)이 `BUILDING_SUB_NAME_BUILDING_TYPES` 의 짝일 때만 띄어 붙이고, 그 밖에는 건물 이름만 쓴다.
    building_name: str | None = None
    if article is not None:
        name = (article.non_complex_building_name or '').strip()
        if name:
            sub_name = (article.non_complex_building_sub_name or '').strip()
            joins_sub_name = real_estate_type in BUILDING_SUB_NAME_REAL_ESTATE_TYPES or (
                article.building_type in BUILDING_SUB_NAME_BUILDING_TYPES.get(real_estate_type, frozenset())
            )
            building_name = f'{name} {sub_name}' if sub_name and joins_sub_name else name

    # 방향 ('남향', 기준이 있으면 '남향 (거실 기준)'). 표에 없는 코드는 괄호를 한 번만 써서 '알 수 없는 값 (XY, 거실 기준)' 으로 낸다
    direction = _coded_label(DIRECTION_BY_CODE, space.direction if space else None)
    if direction is not None and space is not None and space.direction_standard:
        direction = (
            unknown_code_label('값', f'{space.direction}, {space.direction_standard}')
            if space.direction not in DIRECTION_BY_CODE
            else f'{direction} ({space.direction_standard})'
        )

    return NaverListingDetail(
        source='naver',
        id=article_number,
        url=article_url(article_number),
        trade_type=trade_type,
        property_type=PROPERTY_NAME_BY_CODE.get(real_estate_type, real_estate_type),
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
        registered_date=read_date(article.exposure_start_date, '등록일') if article else None,
        # 상세 응답의 건물 날짜를 먼저 쓰고, 없을 때만 단지 정보를 쓴다 (단지 유형은 이미 받은 단지 정보, 그 밖은 필요할 때만 조회)
        approved_date=approved_at,
        complex_id=complex_number,
        complex_name=complex_info.complex_name if complex_info else None,
        building_dong=complex_info.dong_name if complex_info else None,
        pyeong_id=key.key.pyeong_type_number if key.key else None,
        building_name=building_name,
        building_type=_coded_label(BUILDING_TYPE_LABELS, article.building_type if article else None),
        has_article_detail=article is not None,
        is_direct_trade=is_direct_trade is True,
        pre_sale_status_type=pre_sale_status_type,
        real_estate_type=real_estate_type,
        supply_area_m2=None if is_officetel else listed_area,
        contract_area_m2=listed_area if is_officetel else None,
        room_count=space.room_count if space else None,
        bathroom_count=space.bath_room_count if space else None,
        direction=direction,
        move_in=move_in,
        parking=facility_values.parking,
        # 엘리베이터는 중개사가 고르는 기타시설(etc) 항목 하나라 없으면 고르지 않은 것인지 없는 것인지 모른다. 그래서 False 를
        # 내지 않는다 (2026-10-14 실측: 신림동 원룸 상세 3건 중 1건이 시설 13개를 골랐지만 ELEVATOR 는 없었고, 다른 1건은
        # 보안시설을 비워 두었다. 엘리베이터 없음을 따로 알리는 필드는 없다)
        has_elevator=True if 'ELEVATOR' in facility_codes else None,
        options=[
            FACILITY_LABELS.get(code) or unknown_code_label('시설', code)
            for code in facility_codes
            if code != 'ELEVATOR'
        ] if facility is not None else None,
        heating=facility_values.heating,
        heating_fuel=facility_values.heating_fuel,
        entrance=facility_values.entrance,
        badges=listing_badges(
            verification.verification_type if verification else None,
            real_estate_type,
            article.is_safe_lessor_of_hug if article else None,
        ),
        confirmed_date=read_date(verification.article_confirm_date, '매물 확인일') if verification else None,
        loan_manwon=_loan_manwon(price),
        # 중개보수는 직거래가 아님이 확인된 매물만 모든 거래 유형에서 조회하고(모르면 둘 다 null, 직거래면 키를 뺀다), 세금은 웹이
        # 세금 칸을 그리는 매매(원룸·고시원·일반분양권이 아닌 분양권·분양 상태를 모르는 분양권 제외)만 조회한다 (요청 순서: agentFee, tax, 교통·학교, 개발 예정)
        **(
            {'broker_fee_manwon': None, 'broker_fee_individual_check_required': None} if is_direct_trade is None
            else {} if is_direct_trade
            else _agent_fee(client, article_number, notes)
        ),
        **(
            _sale_taxes(client, article_number, real_estate_type, notes)
            if _draws_sale_taxes(trade_type, real_estate_type, pre_sale_status_type) is True else {}
        ),
        **_surroundings(client, article_number, key, notes),
        nearby_development=_nearby_development(client, article_number, notes),
        notes=notes,
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


def _jibun_address(
    client: NaverClient,
    key: NaverArticleKeyModel,
    article: NaverArticleDetailInfoModel | None,
    notes: list[str],
) -> str | None:
    """웹 위치 칸과 같게 만든 주소: article/key 의 법정동 코드로 받은 지역 이름 + 리 + 지번(보일 때만).

    웹은 좌표가 아니라 매물의 법정동 코드로 `legalDivision/infoList` 를 불러 `regionName` 을 얻고 `[regionName, address.li, 지번]` 을
    공백으로 잇는다 (지번을 붙일지는 아래 주석). 같은 방법을 쓰므로 경계 근처 매물에 옆 동 이름이 붙지 않고, 읍·면 매물의 리가 빠지지 않는다.
    article/key 에 주소나 법정동 코드가 없으면 None 이다 (요청 없음). 있으면 좌표와 상관없이 1회 요청한다. 조회가 실패하거나
    응답에 그 코드의 이름이 없으면 None 이고 `notes` 에 `[실패]` 안내가 붙는다.
    """
    address = key.address
    if address is None or not address.legal_division_number:
        return None
    unknown = '모름(null)으로 낸 칸: address'
    divisions = result_or_empty(
        lambda: client.run_request_legal_division_info_list_v1(
            NaverLegalDivisionInfoListV1RequestParameterModel(legal_division_numbers=address.legal_division_number)
        ),
        dict,
        notes=notes,
        what='지번 주소',
        unknown=unknown,
    )
    if divisions is None:
        return None
    division = divisions.get(address.legal_division_number)
    if division is None or not division.region_name:
        # 성공 응답인데 그 코드의 이름이 없다. 거절·형식 변경과 같게 알린다
        add_failure_note(notes, None, '지번 주소', unknown)
        return None
    # 주소에 지번을 붙일지. 웹 위치 칸(ArticleBuildingInfo, 번들 청크 0l4pkwg0qhg2t)과 같은 규칙이다.
    # `JIBUN_EXPOSURE_REAL_ESTATE_TYPES` 유형은 `isJibunAddressExposed` 를, 그 밖의 유형은 건물 세부 유형이 단독(C0301)일 때만 그 값을
    # 따르고 나머지는 늘 보인다. 상세(articleDetailInfo)나 `isJibunAddressExposed` 가 없으면 숨기는 쪽이고, 건물 세부 유형이 없으면 단독이 아니다.
    building_type = article.building_type if article else None
    jibun_shown = (
        (bool(article.is_jibun_address_exposed) if article else False)
        if key.type.real_estate_type in JIBUN_EXPOSURE_REAL_ESTATE_TYPES or building_type == JIBUN_EXPOSURE_BUILDING_TYPE
        else True
    )
    jibun = address.jibun if jibun_shown else None
    return normalize_address(join_address(division.region_name, address.li, jibun))
