"""직방 service 공통 상수: 여러 기능이 함께 쓰는 코드표·이름표·안내 문구·모델 설명 문구."""

import re

from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    TradeType,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.zigbang.api.client import ZIGBANG_WEB_URL
from jibsa.providers.zigbang.api.request.common import (
    ZigbangAptItemSource,
    ZigbangAptTranType,
    ZigbangFloorFilter,
    ZigbangOptionFilter,
    ZigbangRoomTypeFilter,
    ZigbangSalesType,
)

from typing import (
    Literal,
    get_args,
)


ComplexKind = Literal['apt', 'officetel']

WEB_PATH_BY_SERVICE_TYPE: dict[str, str] = {
    '원룸': 'oneroom',
    '오피스텔': 'officetel',
    '빌라': 'villa',
}
# 덤 조회(학군·건물 ID·--details 상세 등)는 이 실패들을 그 칸만 모름으로 둔다. 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`:
# 네트워크·상태 코드, 차단 페이지·응답 형식 변경·19자리가 아닌 pnu)에 요청 제한을 더한다
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, RateLimitedError)
# 매물 목록 명령의 --limit 최대값. CLI 옵션의 max 와 상한 안내(`common.apt` 의 `apt_pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120

# 방향 코드 → 라벨. 주거 상세(`room.detail`)와 아파트 상세(`apt`)가 함께 쓴다
DIRECTION_LABELS: dict[str, str] = {
    'N': '북향',
    'S': '남향',
    'E': '동향',
    'W': '서향',
    'NE': '북동향',
    'NW': '북서향',
    'SE': '남동향',
    'SW': '남서향',
}

# 학교군 안 중·고등학교는 10곳 넘게 오기도 해 가까운 곳만 (당근과 같은 수)
NEAREST_SCHOOLS: int = 2

# 응답 형식이 달라 값을 모를 때 안내 끝 문장. 매일 API 감시가 이 안의 UPDATE_MAYBE_NEEDED 로 고장을 잡는다
UNEXPECTED_FORMAT_TEXT: str = f'직방 응답이 예상한 형식과 달라 {UPDATE_MAYBE_NEEDED}'
# 본 조회 목록을 주지 않아 UPSTREAM_ERROR 로 멈출 때의 hint
UPSTREAM_RETRY_HINT: str = f'잠시 뒤 다시 시도하세요. 계속되면 직방 API 가 바뀐 것일 수 있어 {UPDATE_MAYBE_NEEDED}'

# 아파트 단지 ID 와 오피스텔 건물 ID 는 번호 체계가 달라 같은 숫자가 다른 단지일 수 있어 접두어로 구분한다
COMPLEX_ID_PATTERN: re.Pattern[str] = re.compile(r'^(apt|officetel)-(\d+)$')


# 목록 줄(`ZigbangListing`)과 상세가 함께 쓰는 HUG안심임대인·실매물 확인 필드 설명. 배지 코드는 아래 `HUG_BADGE`·`VERIFICATION_BADGE`
HUG_LESSOR_DESCRIPTION: str = (
    "HUG 안심임대인 (웹의 'HUG안심임대인' 꼬리표). 직방 배지에 HUG 가 있으면 true, 배지를 받았는데 없으면 false, 직방이 배지를 주지 않으면 null"
)
ACTUAL_LISTING_CHECKED_DESCRIPTION: str = (
    "직방 웹의 '실매물 확인' 꼬리표. 직방이 뜻을 설명하지 않는다. 직방 배지에 ITEM_VERIFICATION 이 있으면 true, 배지를 받았는데 없으면 false "
    '(확인 실패 ITEM_VERIFICATION_FAILED 도 false), 직방이 배지를 주지 않으면 null'
)
# 아파트 목록 줄(`common.models` 의 `ZigbangAptListing`)과 상세가 함께 쓰는 매물 종류 필드 설명. 종류 코드 표(`APT_LISTING_KIND_LABELS`)는 아래에 있다
APT_LISTING_KIND_DESCRIPTION: str = (
    '매물 종류: 신규분양(분양 매물, 가격은 분양가)·집주인(집주인이 내놓은 매물)·중개사(중개사무소가 등록한 매물). '
    '모르는 코드는 직방 코드 그대로, 직방이 주지 않으면 null (묶음 줄은 묶음 맨 앞 매물이 상세를 볼 수 없는 출처라 id 가 맨 앞 매물이 아닐 때도 null. '
    '묶인 매물 ID 목록에 직방이 빈 항목을 줘 맨 앞 매물을 알 수 없을 때도 null)'
)
# 아파트 매물 줄·상세가 함께 쓰는 평형 필드 설명. 이름 규칙은 real-price 의 pyeong_name(평 기준)과 같다
APT_PYEONG_ID_DESCRIPTION: str = (
    '평형 ID (complex 의 pyeongs[].pyeong_id 와 같은 번호). search listings --complex <단지> --pyeong·real-price <단지> --pyeong 에 넘긴다. 모르면 null'
)
APT_PYEONG_NAME_DESCRIPTION: str = '평형 이름 (평 기준, 예: 34A. complex 의 pyeongs[].pyeong_name 과 같다). 모르면 null'
# 단지·건물이 있는 유형(아파트·오피스텔)의 상세에만 있는 필드, 아파트 상세에만 있는 필드, 원룸·빌라·오피스텔 상세에만 있는 필드.
# 없는 유형은 키를 뺀다. 찜 수는 웹 www 의 원룸·빌라·오피스텔 화면에 보이지 않아 아파트만이다. 아파트 학군은 단지 정보
# (zigbang complex)에서 주고, 아파트 상세 응답에는 주변 시설·배송 업체가 없다
COMPLEX_DETAIL_FIELDS: frozenset[str] = frozenset({'complex_id', 'complex_name'})
APT_ONLY_DETAIL_FIELDS: frozenset[str] = frozenset({'supply_area_m2', 'listing_kind', 'pyeong_id', 'pyeong_name', 'favorite_count'})
ROOM_ONLY_DETAIL_FIELDS: frozenset[str] = frozenset({'schools', 'nearby_facilities', 'delivery_services', 'building_trades'})


TRADE_TYPES: tuple[TradeType, ...] = ('전세', '월세', '매매', '단기임대')
# jibsa 거래 유형 → 직방 거래 유형 필터 값. 단기임대만 이름이 다르다.
SALES_TYPE_BY_TRADE: dict[str, ZigbangSalesType] = {
    '전세': '전세',
    '월세': '월세',
    '매매': '매매',
    '단기임대': '단기',
}
SHORT_TERM_CONTRACT: str = '단기'
ITEMS_LIST_BATCH_SIZE: int = 15
# 웹 목록이 섹션을 잇는 순서: VIP → 안심추천 → 안심일반 → 추천(원룸 목록은 '이 지역 오피스텔') → 일반 (2026-11-15 번들 `_app` 의
# `createSectionsToUpdate`·`loadItemsV2`. 실측: 강남역 3km 지도 칸 18곳 모두 다섯 섹션을 이 순서로 주고 빈 섹션도 ids [] 로 둔다)
SECTION_ORDER: tuple[str, ...] = ('VIP', 'PREMIUM_RECOMMEND', 'PREMIUM', 'RECOMMEND', 'NORMAL')
ROOM_TYPE_BY_CODE: dict[str, str] = {
    '01': '오픈형원룸',
    '02': '분리형원룸',
    '03': '복층형원룸',
    '04': '투룸',
    '05': '쓰리룸',
    '06': '포룸이상',
}
ROOM_TYPES: tuple[str, ...] = tuple(ROOM_TYPE_BY_CODE.values())
# 방 구조 라벨 → 목록 API 의 방 구조 필터 값. 쓰리룸·포룸이상만 필터 이름이 다르다.
ROOM_TYPE_FILTER_BY_LABEL: dict[str, ZigbangRoomTypeFilter] = {
    '오픈형원룸': '오픈형원룸',
    '분리형원룸': '분리형원룸',
    '복층형원룸': '복층형원룸',
    '투룸': '투룸',
    '쓰리룸': '쓰리룸플러스',
    '포룸이상': '포룸플러스',
}
FLOOR_FILTERS: tuple[ZigbangFloorFilter, ...] = ('지상', '반지하', '옥탑방', '1층')
OPTION_FILTERS: tuple[ZigbangOptionFilter, ...] = (
    '에어컨', '냉장고', '세탁기', '가스레인지', '인덕션', '전자레인지',
    '책상', '책장', '침대', '옷장', '신발장', '싱크대',
)
# 기타 조건 라벨 → 목록 요청 모델의 참/거짓 필드.
CONDITION_FIELD_BY_LABEL: dict[str, str] = {
    '즉시입주': 'immediate_move',
    '남향': 'south_facing',
    '엘리베이터': 'elevator',
    '주차': 'parking',
    'CCTV': 'cctv',
    '반려동물': 'pet',
    '전세대출': 'loan_lease',
    '전기차충전': 'ev_station',
}
CONDITIONS: tuple[str, ...] = tuple(CONDITION_FIELD_BY_LABEL)
# 원룸·빌라·오피스텔 매물 요약·상세의 배지 코드. 웹은 배지 목록에 이 코드가 정확히 있는지로 꼬리표를 붙인다 (2026-11-19 번들
# `useVerifiedItemTag`·`useLessorHugTag`). 'ITEM_VERIFICATION_FAILED' 는 실매물 확인이 아니다
VERIFICATION_BADGE: str = 'ITEM_VERIFICATION'
HUG_BADGE: str = 'HUG'


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

# 상세를 볼 수 있는 아파트 매물 출처
APT_ITEM_SOURCES: tuple[ZigbangAptItemSource, ...] = get_args(ZigbangAptItemSource)


# 아파트 카드·상세의 매물 종류 코드(`itemType`) → 웹 카드가 보여 주는 말. 신규분양은 가격이 분양가다. 필드 설명
# (`APT_LISTING_KIND_DESCRIPTION`)은 상세 결과 모델(`common.models` 의 `ZigbangListingDetail`)도 써 이 파일에 있다
APT_LISTING_KIND_LABELS: dict[str, str] = {'offer': '신규분양', 'partner': '집주인', 'self_ad': '중개사'}

# 아파트 매물 ID 앞에 출처를 붙이는 출처 (`apt_listing_id`). 직방 매물은 접두어 없이 숫자만이다
APT_ID_PREFIXES: tuple[ZigbangAptItemSource, ...] = tuple(source for source in APT_ITEM_SOURCES if source != 'zigbang')
# 출력 url 칸의 웹 페이지 주소 틀 (`.format(...)`)
APT_DANJI_URL: str = f'{ZIGBANG_WEB_URL}/home/apt/danjis/{{}}'
# 웹 아파트 매물 페이지(v2): 매물 번호, 출처. 옛 경로 /home/apt/item/{id} 는 /error 로 보낸다.
# 마지막 칸은 대표로 띄울 중개사 번호인데 빠지면 404 라, 0 을 넣어 직방이 고르게 한다.
APT_ITEM_URL: str = f'{ZIGBANG_WEB_URL}/home/apt/item/v2/{{}}/{{}}/0'
# 같은 호를 여러 중개사가 올린 묶음 화면: 호 번호, 거래 유형. 웹 아파트 카드를 누르면 가격 범위(isPriceRange)와 상관없이 가는 곳이다
# (2026-11-15 번들 ItemCard_AptItemCatalogCard 의 onPress). 신규분양 카드는 누르면 그 매물 상세 화면으로 가지만
# (`onPressOfferItem` → `HomeAptItemDetail`), 이 묶음 화면도 그 매물 1건과 '일반 매매가 아닌 신규분양 매물입니다' 를 보여 준다
APT_CATALOG_URL: str = f'{ZIGBANG_WEB_URL}/home/apt/item-catalog?areaHoId={{}}&tranType={{}}'
