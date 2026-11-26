"""네이버 service 공통: 응답 봉투 풀기, 여러 모듈이 쓰는 결과 모델·URL·안내 문구·상수."""

import re
from collections.abc import Callable
from datetime import (
    date,
    datetime,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    box_around,
    haversine_km,
)
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.korean import (
    is_district_code,
    particle,
)
from jibsa.core.listing import (
    KST,
    NEXT_HINT,
    AmountRange,
    AmountSet,
    Listing,
    Result,
    format_manwon,
    holding_unread_dates,
    join_address,
    lookup_failure_note,
    m2_to_pyeong,
    more_hint,
    normalize_date,
    note,
    null_items_note,
    read_date,
    won_to_manwon,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverArticleSortType,
    NaverBoundingBoxModel,
    NaverComplexBuildingListV1RequestParameterModel,
    NaverComplexPyeongListV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaPyeongListV1RequestParameterModel,
    NaverEntranceType,
    NaverOneRoomShape,
    NaverRealEstateType,
)
from jibsa.providers.naver.api.response.common import (
    NaverArticleListItemModel,
    NaverArticlePageModel,
    NaverComplexArticleCountModel,
    NaverComplexArticlePriceModel,
    NaverComplexListPageModel,
    NaverDuplicatedArticleInfoModel,
    NaverFacilityInfoModel,
    NaverListBuildingInfoModel,
    NaverPriceRangeModel,
    NaverPyeongGroupModel,
    NaverPyeongModel,
    NaverRedevelopmentAreaCountModel,
    NaverRedevelopmentAreaPageModel,
    NaverResponseModel,
    NaverSchoolModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
    TypeVar,
)


T = TypeVar('T')

TRADE_CODE_BY_NAME: dict[str, str] = {
    '매매': 'A1',
    '전세': 'B1',
    '월세': 'B2',
    '단기임대': 'B3',
}
TRADE_NAME_BY_CODE: dict[str, str] = {code: name for name, code in TRADE_CODE_BY_NAME.items()}
# 매매·전세만 받는 조회의 거래 유형 이름 → 코드 (동네 추이·빌라 평당 실거래가. 네이버가 월세 값은 주지 않는다)
SALE_JEONSE_CODE_BY_NAME: dict[str, Literal['A1', 'B1']] = {'매매': 'A1', '전세': 'B1'}
OFFICETEL_CODE: str = 'A02'
# 지도 검색에 보내는 매물 유형 코드. 네이버는 단지로 등록된 빌라를 C02 가 아닌 A05(연립 단지)·A06(다세대 단지)로
# 따로 분류해, C02 만 보내면 빌라의 약 30% 가 빠진다 (역삼동 1km: C02 1124건, A05 33건, A06 408건).
# fin.land 지도의 빌라 필터와 같게 A07(도시형생활주택 단지)까지 함께 보낸다.
SEARCH_CODES_BY_PROPERTY: dict[str, tuple[NaverRealEstateType, ...]] = {
    '아파트': ('A01',),
    '오피스텔': ('A02',),
    '빌라': ('C02', 'A05', 'A06', 'A07'),
    '원룸': ('C01',),
    '단독·다가구': ('C03',),
    '전원주택': ('C04',),
    '상가주택': ('D05',),
    '한옥': ('C06',),
    '고시원': ('G01',),
    '재건축': ('A04',),
    '분양권': ('B01',),
    '오피스텔분양권': ('B02',),
    '재개발': ('F01',),
    '사무실': ('D01',),
    '상가': ('D02',),
    '건물': ('D03',),
    '상가건물': ('D04',),
    '숙박': ('E01',),
    '공장·창고': ('E02',),
    '토지': ('E03',),
    '지식산업센터': ('E04',),
    '기타': ('Z00',),
}
PROPERTY_NAME_BY_CODE: dict[str, str] = {
    code: name for name, codes in SEARCH_CODES_BY_PROPERTY.items() for code in codes
}
ONE_ROOM_SHAPE_CODE_BY_NAME: dict[str, NaverOneRoomShape] = {
    '오픈형': '10',
    '분리형': '20',
}
# 현관 구조 (검색 조건 이름 → 코드). 상세의 현관 구조 글자도 이 표의 반대 방향이다
ENTRANCE_CODE_BY_NAME: dict[str, NaverEntranceType] = {
    '계단식': '10',
    '복도식': '20',
    '복합식': '30',
}
# 확인 방식(verificationInfo.verificationType) → 확인 배지. 네이버 웹 번들 대조 (2026-11-17: 상수 VERIFICATION_TYPE,
# 목록 PropertyBadgeList.tsx, 이름표 함수 getOwnerLabel). 이 밖의 코드(NONE, DOC, TEL, DOCV2, NDOC2, LESR, LH, FT, JOINT)와
# 표에 없는 코드는 웹도 방식 배지를 붙이지 않는다 (날짜 배지와 'HUG 안심임대인' 은 따로 있어 여기서 다루지 않는다)
OWNER_VERIFICATION_TYPES: frozenset[str] = frozenset({'MOBL', 'OWNER', 'NDOC1'})
SITE_VERIFICATION_TYPES: frozenset[str] = frozenset({'SITE', 'S_VR'})
# 웹은 비주거 매물의 집주인 배지를 '소유자' 로 바꿔 보여 준다. 고시원(G01) 같이 이 열 개에 없는 유형은 '집주인' 이다
NON_RESIDENTIAL_TYPES: frozenset[str] = frozenset({'D01', 'D02', 'E04', 'D03', 'D04', 'E01', 'E02', 'Z00', 'E03', 'F01'})
# 면적 필터 기준. 전용이면 filtersExclusiveSpace 를 켠다. 결과의 area_m2 가 전용면적이라 기본은 전용
AREA_BASES: tuple[str, ...] = ('전용', '공급')
WON_PER_MANWON: int = 10_000
# 검색 모드(search listings·complexes·redevelopment, --complex·--redevelopment)의 --limit 최대값.
# CLI 옵션의 max 와 상한 안내(`pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120
# 매물 목록 정렬. 네이버 웹 정렬(ARTICLE_SORT_TYPE)의 여섯이고 거리순은 없다. 반경 검색은 반경을 감싼 사각형 안 매물
# 목록(boundedArticles)을, 동 전체는 동 매물 목록을 이 정렬 그대로 받는다
SORT_TYPE_BY_NAME: dict[str, NaverArticleSortType] = {
    '랭킹순': 'RANKING_DESC',
    '가격낮은순': 'PRICE_ASC',
    '가격높은순': 'PRICE_DESC',
    '최신순': 'DATE_DESC',
    '면적좁은순': 'SPACE_ASC',
    '면적넓은순': 'SPACE_DESC',
}
# 단지·재개발 구역 매물 목록 정렬. 지역 매물 검색과 같은 표라 별칭으로 둔다. 가까운순은 이쪽에 원래 없어 그 안내(cli 의
# NEAREST_SORT_HINT)는 search_command 가 지역 검색 모드에만 붙인다
COMPLEX_SORT_TYPE_BY_NAME: dict[str, NaverArticleSortType] = SORT_TYPE_BY_NAME


def article_url(article_number: str) -> str:
    return f'https://fin.land.naver.com/articles/{article_number}'


def complex_url(complex_number: int) -> str:
    return f'https://fin.land.naver.com/complexes/{complex_number}'


# 리뷰 오탐 (2026-11-24): hint 기본값은 번호 조회용이다. hint 없이 부르는 곳은 모두 평형·단지·구역·학교 번호로 부르고, 이름·좌표·목록 조회는 모두 hint 를 넘긴다
def unwrap(response: NaverResponseModel[T], what: str, *, hint: str | None = '번호가 맞는지 확인하세요') -> T:
    """봉투의 `result` 를 꺼낸다. 실패 응답이면 `JibsaError`.

    Args:
        hint: NOT_FOUND 에 붙일 안내 (UPSTREAM_ERROR 는 이 뒤에 스펙이 바뀌었을 수 있다는 말을 잇는다). 기본값은 번호를
            받는 호출용이다. 이름·좌표·목록을 받는 호출은 번호를 확인하라고 하지 않도록 그 입력에 맞는 안내를 넘기고,
            `None` 이면 번호를 말하지 않는 일반 안내를 쓴다.

    Raises:
        JibsaError: 성공 응답인데 `result` 가 비었으면 NOT_FOUND (없는 단지 번호 등),
            `isSuccess` 가 false 면 UPSTREAM_ERROR.
    """
    if response.is_success and response.result is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'네이버 {what} 결과가 없습니다',
            hint=hint or '네이버가 결과를 주지 않았습니다. 잠시 뒤 다시 시도하세요',
        )
    if not response.is_success or response.result is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'네이버 {what} 조회 실패: {response.detail_code or ""} {response.message or ""}'.strip(),
            hint=f'{hint}. 비공식 API 라 스펙이 바뀌었을 수 있습니다' if hint else '비공식 API 라 스펙이 바뀌었을 수 있습니다',
        )
    return response.result


def villa_fallback_found(response: NaverResponseModel[Any]) -> bool:
    """아파트 쪽이 비어 빌라 단지 엔드포인트로 다시 물은 응답이 쓸 만한지.

    아파트 단지는 매물·실거래가 없어도 아파트 쪽이 빈 목록으로 오므로 빌라로 다시 묻게 된다. 그때 빌라
    엔드포인트가 실패나 빈 `result` 를 주면 빌라 단지가 아닌 것이라, `unwrap` 처럼 에러를 내지 않고 0건으로 본다.
    """
    return response.is_success and response.result is not None


def villa_by_complex_response(response: NaverResponseModel[Any]) -> bool:
    """아파트 단지 정보(`complex`) 응답으로 빌라 단지인지 정한다.

    빌라 단지(A05·A06·A07)는 아파트 단지 엔드포인트가 성공 응답에 빈 결과(result=null)를 준다. 단지 종류를 정하는
    방법은 이것, 단지 이름 자동완성의 유형(`complex_is_villa`), 빌라 엔드포인트가 답하는지(`villa_fallback_found`)
    셋이다. 앞의 둘은 따로 묻는 1회가 들고, 셋째는 빌라 자료를 받는 요청이 곧 확인이라 아파트일 때만 1회가 헛돈다.
    판별을 명령 맨 앞에서 한 번에 하면 단지 종류를 모를 때마다(대부분 아파트) 1회가 늘어서, 일부러 아파트 쪽이
    비었을 때만 그 자리에서 정한다. 한 번 빌라로 정해지면 빌라 엔드포인트의 실패는 0건이 아니라 에러로 낸다.
    """
    return response.is_success and response.result is None


class NaverAssignedSchool(BaseModel):
    """배정 초등학교 한 곳. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str | None,
        Field(description='학교 코드. naver school 에 넘긴다')
    ] = None
    name: Annotated[
        str,
        Field(description='학교 이름')
    ]
    assignment: Annotated[
        str | None,
        Field(description='배정 방식 (배정, 선택. 모르는 코드면 알 수 없는 값 (코드), 없으면 null)')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)')
    ] = None
    walk_minutes: Annotated[
        int | None,
        Field(description='도보 시간 (분)')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None


BADGES_DESCRIPTION: str = (
    "네이버 화면의 확인 배지 (집주인·소유자·현장). 확인 정보가 있으면 그 뒤에 집주인이 HUG 안심임대인일 때 'HUG 안심임대인' 이 붙는다. "
    '방식 배지·HUG 배지가 모두 없으면 [], 모르면 null. 전화·서류로 확인한 매물과 확인하지 않은 매물도 HUG 안심임대인이면 '
    "['HUG 안심임대인'] 이라, 비어 있지 않다고 집주인·현장 확인 매물인 것은 아니다"
)
"""목록 매물(`NaverListing`)과 상세(`NaverListingDetail`)의 `badges` 설명. 두 모델은 상속이 갈려 필드를 함께 쓸 수 없다."""

CONFIRMED_AT_DESCRIPTION: str = (
    "네이버가 매물을 확인한 날 (YYYY-MM-DD). 웹 목록은 협회 매물이 아니면 이 날짜로 '25.11.17. 확인매물' 날짜 배지를, 협회 매물이면 "
    "노출 시작일(`registered_date`)로 '등록' 배지를 그린다. 목록과 상세의 글자 규칙이 달라 날짜만 낸다. 모르면 null"
)
ASKING_RANGES_DESCRIPTION: str = (
    '거래 유형별 호가 범위 {sale·jeonse·wolse·short_term: {lowest, highest}}. sale 은 price_manwon, jeonse 는 deposit_manwon, wolse·short_term 은 보증금·월세 짝 '
    '(deposit_manwon·rent_manwon). 월세·단기임대의 두 끝은 월세 최저·최고가 아니라 가격순 첫 매물의 짝이라 rent_manwon 이 거꾸로일 수 있다 '
    '(빌라 단지는 월세가 대개 없다). 그 거래 매물이 없거나(네이버가 값을 주지 않거나 0) 가격 정보가 없는 거래 유형은 키가 없고, 네이버가 호가 정보 '
    '자체를 주지 않으면 null. 한 끝만 비면 그 끝 금액만 null. 월세·단기임대는 한 짝의 월세만 0 이면 그 rent_manwon 만 null, '
    '한 짝이 보증금·월세 모두 0 이면 그 짝 두 값 모두 null'
)
"""`NaverComplexSummary`·`NaverAreaComplex`·`NaverSchoolComplex` 의 `asking_ranges` 설명. 모델끼리 필드를 함께 쓸 수 없어 상수로 공유한다. `confirmed_date` 설명(`CONFIRMED_AT_DESCRIPTION`)도 목록·상세가 함께 쓴다."""


# 매물 유형(realEstateType)마다 웹 화면이 칸을 아예 그리지 않는 필드. 키째 뺀다 (칸이 있는데 값을 모르면 null 이다). 상세(`NaverListingDetail`)와
# 목록(`NaverListing`)이 함께 쓴다. 목록 모델에 없는 필드 이름은 출력에서 그냥 지나간다.
# 2026-11-17 네이버 웹 번들 대조: 기본 정보 칸은 청크 0n-xsnd22pdxz 의 getBasicInfoSpaceTarget·면적 함수, 건축물 정보
# ArticleBuildingInfo 는 isBuildingRegistrationType 유형만, 시설 ArticleFacilityInfo 는 토지_임야(E03) 만 제외 (청크 0l4pkwg0qhg2t)
NOT_APPLICABLE_FIELDS_BY_TYPE: dict[str, frozenset[str]] = {
    # 토지
    'E03': frozenset({
        'room_count', 'bathroom_count', 'room_type', 'direction', 'floor', 'building_floor', 'area_m2', 'area_pyeong',
        'supply_area_m2', 'approved_date', 'heating', 'heating_fuel', 'entrance', 'parking', 'has_elevator', 'options',
    }),
    # 고시원: 시설 칸은 있어 has_elevator·options 는 남긴다
    'G01': frozenset({
        'room_count', 'bathroom_count', 'room_type', 'direction', 'floor', 'building_floor', 'area_m2', 'area_pyeong',
        'supply_area_m2', 'approved_date', 'heating', 'heating_fuel', 'entrance', 'parking', 'loan_manwon',
    }),
    # 재개발
    'F01': frozenset({'room_count', 'bathroom_count', 'room_type', 'area_m2', 'area_pyeong', 'supply_area_m2'}),
    # 사무실·상가·지식산업센터: 웹은 방/욕실 대신 '화장실 수' 만 그린다 (bathroom_count 는 남긴다)
    **dict.fromkeys(('D01', 'D02', 'E04'), frozenset({'room_count', 'room_type'})),
    # 건물·상가건물·숙박·공장창고·기타: 웹은 해당층 대신 지상/지하 층수만 그리고 공급면적 칸이 없다 (building_floor 는 그대로)
    **dict.fromkeys(('D03', 'D04', 'E01', 'E02', 'Z00'), frozenset({'room_count', 'room_type', 'floor', 'supply_area_m2'})),
}


class NaverListing(Listing):
    """네이버 목록 매물. 같은 집을 중개사 여럿이 올려 네이버가 한 매물로 묶었으면 묶음의 중개사 수와 호가 범위가 붙는다.

    가격 필드(`price_manwon` 등)는 묶음을 대표하는 매물 하나의 호가다. 네이버 가격순은 묶음의 호가 범위로 정렬해
    (가격높은순은 최고 호가) 대표 가격의 순서와 다를 수 있다. 2026-10-31 실측: 헬리오시티 84㎡ 매매 가격높은순 첫 매물이
    대표 30억, 같은 집(204동 22층)을 중개사 50곳이 30억~33억에 올린 묶음이었다. 범위를 버리면 33억 호가가 어디에도 안 보여
    에이전트 4명 모두 최고 호가를 32억으로 답했다.
    """

    realtor_count: Annotated[
        int | None,
        Field(description='같은 집을 올린 중개사 수 (네이버가 한 매물로 묶음). 묶음이 아니면 키가 없다')
    ] = None
    asking_range: Annotated[
        AmountRange | None,
        Field(description=(
            '묶음의 호가 범위 {lowest, highest}. 중개사마다 호가가 다를 때만 있다. 매매는 price_manwon, 전세는 deposit_manwon, '
            '월세·단기임대는 보증금·월세 짝(deposit_manwon·rent_manwon)이고, 월세 두 끝은 월세 최저·최고가 아니라 (보증금 순 첫·끝 매물의 짝이라) '
            'rent_manwon 이 거꾸로일 수 있다 (보증금이 같은 매물끼리는 lowest 가 월세 낮은 쪽, highest 가 높은 쪽). 보증금이 같고 월세만 다르면 '
            '두 끝의 deposit_manwon 이 같은 값이고, 월세가 같고 보증금만 다르면 두 끝의 rent_manwon 이 같은 값이다. 가운데 매물의 월세는 달라도 두 끝이 '
            '같을 수 있다. 네이버가 어느 금액의 범위를 주지 않거나 두 끝이 모두 비거나 0 과 null 이 섞이면 그 금액만 null 이고, 모든 금액을 모르면 '
            'asking_range 가 null 이다. 묶음이 아니거나 모든 금액의 두 끝이 같으면 키가 없다'
        ))
    ] = None
    unknown_group_fields: Annotated[
        frozenset[str],
        Field(exclude=True, description='묶음 호가 범위를 몰라 null 로 낼 칸')
    ] = frozenset()
    badges: Annotated[
        list[str] | None,
        Field(description=BADGES_DESCRIPTION)
    ] = None
    confirmed_date: Annotated[
        str | None,
        Field(description=CONFIRMED_AT_DESCRIPTION)
    ] = None
    real_estate_type: Annotated[
        str | None,
        Field(exclude=True, description='네이버 매물 유형 코드 (A01 …). 유형마다 웹에 없는 칸을 가리는 데만 쓴다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 유형마다 웹이 칸을 그리지 않는 필드 (토지의 방 수·층·면적 등). 값을 모르는 null 이 아니라 키째 뺀다
        return (
            super().not_applicable_fields()
            | ({name for name in GROUP_FIELDS if getattr(self, name) is None} - self.unknown_group_fields)
            | NOT_APPLICABLE_FIELDS_BY_TYPE.get(self.real_estate_type or '', frozenset())
        )


# 묶음이 아니거나 중개사마다 호가가 같으면 해당 없는(키를 빼는) 필드
GROUP_FIELDS: tuple[str, ...] = ('realtor_count', 'asking_range')


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


class NaverListingsResult(Result):
    """매물 목록 결과.

    `notes`: 요청 상한으로 일부만 훑었다는 안내 등
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int,
        Field(description='서버 집계 매물 수. search 는 반경을 감싸는 사각형 안, 동·시·군·구 경계로 찾았으면 그 경계 안 정확한 수 (조건 적용 후, limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description=(
            '같은 조건으로 더 받을 매물이 남았는지. 이어 받을 수 있으면 next_position 도 있어 CLI 가 이어 받기 표(next)를 붙인다. '
            '네이버가 더 있다면서 새 매물을 주지 않아 멈췄으면 이어 받을 수 없어도(next 없음) true 다'
        ))
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 (목록 커서 seed·last_info). 더 없으면 None')
    ] = None
    listings: Annotated[
        # 중복 묶음 필드(NaverListing)까지 내보낸다 (SerializeAsAny 가 없으면 공통 Listing 필드만 나간다)
        list[SerializeAsAny[Listing]],
        Field(description='매물')
    ]


MARKET_PRICE_PROVIDER_NAMES: dict[str, str] = {'kab': '한국부동산원', 'kbstar': 'KB부동산', 'neonet': '부동산뱅크'}


# 부가 정보 조회에서 그 값만 모름(None)으로 두는 오류: 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`, 압축이 깨진
# 응답도 HTTPError)만 잡는다. 요청 제한(RateLimitedError)은 JibsaError 라 잡지 않아 그대로 올라간다.
# 제한을 끈 정책(RateLimitPolicy(enabled=False))이면 429 가 HTTPStatusError 로 와 여기서 모름이 되지만, 그 정책은
# 라이브러리로 직접 만들 때만 쓰이고 CLI 는 늘 켜 둔다 (core/ratelimit.py on_rate_limited, 2026-10-11 확인).
# ValidationError 는 람다 안에서 만드는 요청 모델 오류도 잡지만, 요청 값은 CLI 가 검증한 값이나 네이버 응답 값
# (법정동 코드 10자리, 단지 유형 코드 등)이라 사용자 입력으로는 생기지 않는다 (2026-10-10 확인)
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = OPTIONAL_LOOKUP_BASE_ERRORS


def add_failure_note(notes: list[str] | None, exc: Exception | None, what: str, unknown: str) -> None:
    """`[실패]` 안내를 notes 에 더한다. notes 가 None 이면 호출부가 스스로 알리는 것이라 아무것도 안 하고, 같은 안내는 한 번만 낸다.

    한 명령에서 같은 조회를 여러 번 부르는 자리(평형마다 등)가 있어 같은 글자를 거듭 붙이지 않는다.

    갈래(네이버가 거절(4xx·`isSuccess` false)했거나 응답 형식이 바뀌면 업데이트 안내, 서버 오류·연결 실패면 붙이지 않음)와
    문구는 core/listing.py 의 `lookup_failure_note` 다. 요청 제한 `RateLimitedError` 는 덤 조회가 잡지 않아 여기 오지 않는다.

    Args:
        exc: 실패 예외. `None` 이면 `isSuccess` 가 false 였던 것이다.
        what: 받지 못한 조회 이름 ('관리비').
        unknown: 그 실패로 모름이 된 칸 (끝에 마침표 없음). '모름(null)으로 낸 칸: a, b' 꼴로 써 영어 필드 이름 뒤에 조사가 붙지 않게 한다.
    """
    if notes is None:
        return
    text = lookup_failure_note(exc, '네이버', what, unknown)
    if text not in notes:
        notes.append(text)


def result_or_none(
    request: Callable[[], NaverResponseModel[T]],
    *,
    notes: list[str] | None,
    what: str,
    unknown: str,
) -> T | None:
    """부가 정보 조회. 실패하면 그 값만 모름(None)으로 두고 `notes` 에 `[실패]` 안내를 붙인다 (매물 상세·단지 요약 전체를 실패시키지 않는다).

    예외면 `[실패]` 안내를 붙인다. `isSuccess` false·`result` null 은 안내 없이 None 이다.

    Args:
        notes: 안내를 붙일 목록. `None` 은 호출부가 실패를 스스로 알린다는 뜻이다 (지역 해석).
        what: 조회 이름 ('관리비'). core/listing.py 의 `lookup_failure_note` 를 보라.
        unknown: 모름이 된 칸 ('모름(null)으로 낸 칸: a, b').
    """
    return result_with_null_items(request, notes=notes, what=what, unknown=unknown)[0]


def result_with_null_items(
    request: Callable[[], NaverResponseModel[T]],
    *,
    notes: list[str] | None,
    what: str,
    unknown: str,
) -> tuple[T, int] | tuple[None, int]:
    """`result_or_none` 와 같되, `result` 가 객체 목록일 때 그 목록에서 빈 항목(null)을 빼고 읽은 수도 돌려준다.

    목록이 `result` 자리라 `result_or_none` 은 봉투를 버리면서 뺀 수도 버린다. 그 목록으로 계산하거나 자리를 세는 호출부가 쓴다.
    조회가 실패했거나 `result` 가 비었으면 `(None, 0)` 이다. 반환형이 `tuple[T | None, int]` 가 아닌 것은 mypy 가 그 꼴이면 T 를
    `T | None` 으로 잘못 풀어 호출부가 타입 오류를 내서다.
    """
    try:
        response = request()
    except OPTIONAL_LOOKUP_ERRORS as exc:
        add_failure_note(notes, exc, what, unknown)
        return None, 0
    # 리뷰 오탐 (2026-11-24): isSuccess false 를 [실패] 로 보지 않는다. 네이버는 고장이 아닌 응답에도 200 + isSuccess false 를 준다 (상가 2662726134·토지 2663300403 의 article/maintenanceFee 가 {isSuccess: false, result: {}}, 웹 ArticlePriceInfo 는 이를 무시하고 article/oldMaintenanceFee 로 넘어간다). 진짜 거절과 가릴 수 없어 값 없음으로 둔다
    result = response.result
    if result is None:
        return None, 0
    return result, response.null_items('result')


def result_or_empty(
    request: Callable[[], NaverResponseModel[T]],
    empty: Callable[[], T],
    *,
    notes: list[str] | None,
    what: str,
    unknown: str,
) -> T | None:
    """부가 정보 조회. 실패하면(예외·`isSuccess` false) 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다. 성공했는데 `result` 가 null 이면 네이버가 주지 않은 것이라 `empty()`.

    `result_or_none` 은 `result` null 도 None 으로 합쳐, 성공 응답을 '조회 실패(모름)' 로 내게 된다. 서버가 빈 목록·빈 객체를 주는 자리에
    `result: null` 이 와도 그 빈 응답과 같게 읽을 때 쓴다 (`empty` 는 `list` 나 빈 모델 클래스처럼 빈 값을 만드는 호출 가능한 것).

    Args:
        notes: 안내를 붙일 목록. `None` 은 호출부가 실패를 스스로 알린다는 뜻이다.
        what: 조회 이름. unknown: 모름이 된 칸. `result_or_none` 과 같다.
    """
    try:
        response = request()
    except OPTIONAL_LOOKUP_ERRORS as exc:
        add_failure_note(notes, exc, what, unknown)
        return None
    if not response.is_success:
        add_failure_note(notes, None, what, unknown)
        return None
    return empty() if response.result is None else response.result


# 단지형 빌라(연립·다세대·도시형생활주택 단지). 학교는 이 유형이면 villa 로 묻는다
VILLA_COMPLEX_CODES: frozenset[str] = frozenset({'A05', 'A06', 'A07'})
SCHOOL_ALLOCATION_LABELS: dict[str, str] = {'01': '배정', '02': '선택'}


def assigned_schools(schools: list[NaverSchoolModel], notes: list[str]) -> list[NaverAssignedSchool]:
    """배정 초등학교 목록. 이름이 없는 항목은 빼고 `notes` 에 `[제외]` 안내를 붙인다.

    배정 방식 코드가 `SCHOOL_ALLOCATION_LABELS` 에 없으면 `unknown_code_label` 글자로 낸다 (코드가 없거나 '-' 면 null).
    """
    named = [school for school in schools if school.name]
    if len(named) < len(schools):
        notes.append(note('제외', f'이름이 없는 배정 학교 {len(schools) - len(named)}곳은 넣지 않았습니다'))
    result: list[NaverAssignedSchool] = []
    for school in named:
        # 날짜·층 칸처럼 '-' 는 값 없음 표시다
        allocation = (school.allocation_type or '').strip()
        result.append(NaverAssignedSchool(
            school_code=school.code,
            name=school.name,
            assignment=(
                None if allocation in ('', '-')
                else SCHOOL_ALLOCATION_LABELS.get(allocation) or unknown_code_label('값', allocation)
            ),
            operation_type=school.operation_type,
            walk_minutes=school.walking_minute,
            distance_m=school.distance,
            students_per_class=school.students_per_classroom,
            students_per_teacher=school.students_per_teacher,
        ))
    return result


def unknown_code_label(kind: str, code: str) -> str:
    """jibsa 표에 없는 코드를 낼 글자 ('알 수 없는 시설 (XYZ01)').

    값은 응답에 있는데 jibsa 가 못 읽은 것이라, 값이 없다는 뜻의 null 도 코드 글자 그대로도 아니다. 사용자가 이 글자를 보고
    코드를 알려 주면 표에 더할 수 있다.

    Args:
        kind: 무엇의 코드인지 ('값' 하나짜리, '시설' 시설 목록 항목, '항목' 관리비 포함 항목).
        code: 응답의 코드.
    """
    return f'알 수 없는 {kind} ({code})'


HUG_SAFE_LESSOR_BADGE: str = 'HUG 안심임대인'


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
        url=article_url(info.article_number),
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


def won_to_manwon_range(low: float | None, high: float | None) -> list[float | None] | None:
    """원 단위 범위(호가·시세)를 만원으로. 둘 다 없으면 None.

    그 거래 매물이 없으면 호가는 0 이 아니라 null 로 온다 (더힐 725113 전세 0건: rentMinPrice·rentMaxPrice null,
    2026-10-11). 0 도 없음으로 보는 것은 0원 범위가 뜻이 없어서다.
    """
    if not low and not high:
        return None
    return [won_to_manwon(low), won_to_manwon(high)]


def amount_range(
    field: Literal['price_manwon', 'deposit_manwon'],
    low: float | None,
    high: float | None,
) -> AmountRange | None:
    """원 단위 호가 범위를 `field` 금액의 만원 범위로 (`won_to_manwon_range` 가 None 이면 그 거래 매물이 없어 None)."""
    values = won_to_manwon_range(low, high)
    if values is None:
        return None
    return AmountRange(lowest=AmountSet(**{field: values[0]}), highest=AmountSet(**{field: values[1]}))


def _rent_amount(deposit: int | None, rent: int | None) -> AmountSet:
    """한 짝의 보증금·월세(원)를 만원 짝으로. 월세만 0 이면 월세만 null, 보증금과 월세가 모두 0(또는 없음)이면 두 값 모두 null."""
    if not deposit and not rent:
        return AmountSet(deposit_manwon=None, rent_manwon=None)
    return AmountSet(deposit_manwon=won_to_manwon(deposit), rent_manwon=won_to_manwon(rent or None))


def rent_asking_range(
    price: NaverComplexArticlePriceModel | None,
    kind: Literal['monthly', 'short'],
) -> AmountRange | None:
    """단지 호가 범위(`NaverComplexArticlePriceModel`)의 월세·단기임대 짝을 만원으로 묶는다.

    웹 호가 범위가 '보증금min/월세min ~ 보증금max/월세max' 로 그리는 것과 같은 짝이다. 보증금이 낮은 매물이 월세는
    높을 수 있어 월세 lowest 가 highest 보다 클 수 있다. 그 종류의 네 값이 모두 없거나 0 이면 None 이다
    (단기임대 매물이 없으면 단기 키는 오지 않는다). 그 밖에 한 짝의 월세만 0 이면 서버가 비운 값이라 그 월세만 null 이고,
    한 짝의 보증금과 월세가 모두 0 이면 그 짝은 비어 있어 두 값 모두 null 이다. 월세가 있는 짝의 보증금 0 은 그대로 0 으로 낸다.

    Args:
        kind: 'monthly' 월세, 'short' 단기임대.
    """
    if price is None:
        return None
    if kind == 'monthly':
        values = (
            price.rent_monthly_lease_min_price, price.rent_monthly_min_price,
            price.rent_monthly_lease_max_price, price.rent_monthly_max_price,
        )
    else:
        values = (
            price.rent_short_lease_min_price, price.rent_short_min_price,
            price.rent_short_lease_max_price, price.rent_short_max_price,
        )
    # 월세 0원 매물은 없어 네 값이 모두 0 이면 서버가 0 으로 비운 것이라 그 거래 키가 없고, 한 짝의 월세만 0 이어도 비운 값이라
    # 그 월세만 null(모름)이다. 한 짝의 보증금과 월세가 모두 0 이면 그 짝이 비어 있어 두 값 모두 null 이다. 월세가 있는 짝의
    # 보증금 0 은 실제로 있을 수 있어 그대로 0 으로 낸다 (`won_to_manwon_range` 도 0 을 시세 없음으로 본다)
    if not any(values):
        return None
    low_deposit, low_rent, high_deposit, high_rent = values
    return AmountRange(
        lowest=_rent_amount(low_deposit, low_rent),
        highest=_rent_amount(high_deposit, high_rent),
    )


def asking_ranges(prices: NaverComplexArticlePriceModel | None) -> dict[str, AmountRange] | None:
    """단지의 거래 유형별 호가 범위 (`asking_ranges`). 키 순서는 sale·jeonse·wolse·short_term 이다.

    `prices` 가 없으면(서버가 호가를 주지 않음) None(모름)이고, 그 거래 매물이 없으면(값이 모두 없거나 0) 그 거래 키를 뺀다.
    """
    if prices is None:
        return None
    ranges: dict[str, AmountRange | None] = {
        'sale': amount_range('price_manwon', prices.deal_min_price, prices.deal_max_price),
        'jeonse': amount_range('deposit_manwon', prices.rent_min_price, prices.rent_max_price),
        'wolse': rent_asking_range(prices, 'monthly'),
        'short_term': rent_asking_range(prices, 'short'),
    }
    return {name: value for name, value in ranges.items() if value is not None}


def trade_article_counts(counts: NaverComplexArticleCountModel | NaverRedevelopmentAreaCountModel) -> dict[str, int]:
    """거래 유형별 매물 수 (단지·단지 목록·재개발 구역 목록·재개발 상세의 `listing_counts`)."""
    return {
        'sale': counts.deal_count,
        'jeonse': counts.lease_deposit_count,
        'wolse': counts.lease_monthly_count,
        'short_term': counts.lease_short_term,
    }


def complex_row_fields(
    *,
    type_code: str | None,
    households: int | None,
    dong_count: int | None,
    use_approval_date: str | None,
    counts: NaverComplexArticleCountModel | None,
    prices: NaverComplexArticlePriceModel | None,
) -> dict[str, Any]:
    """단지 한 곳의 공통 칸을 만든다: 단지 유형·세대수·동 수·사용승인일·거래 유형별 매물 수·거래 유형별 호가 범위.

    학교 배정 단지(`school`)·지역 단지 목록(`search complexes`)·단지 요약(`complex`)이 같은 값을 같은 식으로 내도록 한 곳에 둔다.
    호출부는 각 모델 생성자에 `**` 로 풀어 넣는다 (각 모델의 필드 순서와 `address`·`distance_km`·`url`·`assigned_dongs` 같은 자기 칸은
    호출부가 정한다). `counts`·`prices` 가 없으면(서버가 주지 않음) 그 칸은 `None`(모름)이다. 단지 요약의 두 값은 응답 모델이 빈 모델로 채워
    `None` 갈래에 닿지 않는다.

    Args:
        type_code: 단지 유형 코드. 표에 없는 코드는 코드 그대로 내고, 빈 글자는 모름(None)이다.
        dong_count: 동 수. 단지 목록 항목은 `buildingCount`, 단지 정보는 `dongCount` 라 호출부가 맞는 쪽을 넘긴다.
        use_approval_date: 사용승인일 (YYYYMMDD).
    """
    return {
        # 빈 글자는 단지 유형을 모르는 것이라 None 이다 (`complex` 의 시세·평당가 판정이 빈 글자를 모름으로 읽는 것과 같다)
        'complex_type': PROPERTY_NAME_BY_CODE.get(type_code or '', type_code or None),
        'household_count': households,
        'dong_count': dong_count,
        'approved_date': read_date(use_approval_date, '사용승인일'),
        'listing_counts': trade_article_counts(counts) if counts is not None else None,
        'asking_ranges': asking_ranges(prices),
    }


def raise_missing_pyeongs(
    complex_number: int,
    pyeong_numbers: list[int] | None,
    pyeongs: list[NaverPyeongModel],
    *,
    no_pyeong_hint: str = '네이버에 평형 정보가 없는 단지입니다. --pyeong 없이 조회하세요',
) -> None:
    """단지 평형 목록에 없는 평형 번호가 있으면 이 단지의 평형 번호를 알려 주며 멈춘다.

    Args:
        no_pyeong_hint: 평형 목록이 비었을 때의 hint. 기본값은 단지가 있다고 확인했고 `--pyeong` 을 뺄 수 있는 명령(complex)용.

    Raises:
        JibsaError: NOT_FOUND.
    """
    known_numbers = {pyeong.number for pyeong in pyeongs}
    missing = [number for number in pyeong_numbers or [] if number not in known_numbers]
    if missing:
        available = ', '.join(f'{pyeong.number}({pyeong.name})' for pyeong in pyeongs)
        raise JibsaError(
            code='NOT_FOUND',
            message=f"단지 {complex_number} 에 없는 평형 번호입니다: {', '.join(map(str, missing))}",
            hint=f'이 단지의 평형 번호(이름): {available}' if available else no_pyeong_hint,
        )


def pyeong_list(client: NaverClient, complex_number: int, villa: bool) -> list[NaverPyeongModel]:
    """단지 평형 목록. 빌라 단지는 빌라 평형 목록을 묻는다 (1회)."""
    if villa:
        return unwrap(
            client.run_request_complex_villa_pyeong_list_v1(
                NaverComplexVillaPyeongListV1RequestParameterModel(complex_number=complex_number)
            ),
            '평형',
        )
    return unwrap(
        client.run_request_complex_pyeong_list_v1(NaverComplexPyeongListV1RequestParameterModel(complex_number=complex_number)),
        '평형',
    )


def group_pyeong_numbers(group: NaverPyeongGroupModel) -> list[int] | None:
    """평형 묶음에 든 평형 번호 (번호순). 대표 번호가 `pyeongTypes` 의 첫 항목이 아닐 수 있어 순서를 믿지 않고 정렬한다.

    네이버가 평형 목록을 주지 않거나(`pyeongTypes` null) 번호가 빈 평형이 있으면 묶음의 번호를 다 알 수 없어 모름(None)이다.
    """
    if group.pyeong_types is None:
        return None
    numbers = {pyeong.number for pyeong in group.pyeong_types}
    if None in numbers:
        return None
    return sorted(number for number in numbers if number is not None)


def check_pyeong_numbers(
    client: NaverClient,
    complex_number: int,
    pyeong_numbers: list[int],
    *,
    villa: bool | None = None,
    pyeong_required: bool = False,
) -> bool:
    """결과가 비었을 때 평형 번호가 단지에 있는지 확인하고, 빌라 단지인지 돌려준다 (1~2회 호출).

    평형 번호가 틀려도 서버는 매물·실거래·시세를 0건으로 줘서 '없음' 과 구분되지 않는다
    (헬리오시티 평형 999: 단지 매물·실거래·시세 모두 0건, 2026-10-10). 단지 종류를 모르면(None) 아파트 평형 목록을
    먼저 묻고, 비었을 때만 빌라 평형 목록을 묻는다. 아파트 평형 목록은 빌라 단지(가람아트빌 673573)와 없는 단지 번호
    (99999999)에 빈 목록을 준다 (2026-10-11). 단지 정보로 종류를 먼저 정하면 대부분인 아파트에서 1회가 더 든다.

    Args:
        pyeong_required: `--pyeong` 이 필수인 명령(real-price·market-price)인지. 평형 목록이 비었을 때 hint 가
            '--pyeong 없이 조회하세요' 대신 단지를 확인하게 한다.

    Raises:
        JibsaError: 평형 목록에 없는 번호가 있으면 NOT_FOUND.
    """
    if villa is None:
        pyeongs = pyeong_list(client, complex_number, False)
        villa = not pyeongs
        if villa:
            pyeongs = pyeong_list(client, complex_number, True)
    else:
        pyeongs = pyeong_list(client, complex_number, villa)
    # 없는 단지 번호도 아파트·빌라 평형 목록이 모두 빈 성공 응답이라(99999999, 2026-10-28 실측) 평형 정보가 없는 단지와
    # 가르려면 단지 정보를 1~2회 더 물어야 한다. 요청을 늘리지 않고 두 경우를 함께 알린다. real-price·market-price 는
    # --pyeong 이 필수라 '--pyeong 없이 조회하세요' 를 따를 수 없었다 (2026-10-28 리뷰)
    action = (
        f"'jibsa naver complex {complex_number}' 로 단지가 있는지와 평형 번호(pyeongs)를 확인하세요"
        if pyeong_required else '--pyeong 없이 조회하세요'
    )
    raise_missing_pyeongs(
        complex_number, pyeong_numbers, pyeongs,
        no_pyeong_hint=f'없는 단지 번호이거나 네이버에 평형 정보가 없는 단지입니다. {action}',
    )
    return villa


def kst_today() -> date:
    """한국 시간 기준 오늘. 실거래·시세 기간은 한국 날짜라 실행하는 컴퓨터의 시간대와 상관없이 맞춘다.

    `date.today()` 는 컴퓨터 시간대를 따라 GMT-12 에서는 하루 전 날짜가 됐다 (시세 since 2025-10-09, 한국 기준 2025-10-10, 2026-10-10).
    """
    return datetime.now(KST).date()


class NaverMarketBand(BaseModel):
    """기관 시세 한 거래 유형의 평균과 하위·상위 띠 (만원). 띠는 범위가 아니라 기관이 준 하위·상위 값이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    average_manwon: Annotated[
        float | None,
        Field(description='시세 평균 (만원). 없으면(0 포함) null')
    ] = None
    low_manwon: Annotated[
        float | None,
        Field(description='시세 하위 (만원). 기관이 띠를 주지 않으면 null')
    ] = None
    high_manwon: Annotated[
        float | None,
        Field(description='시세 상위 (만원). 기관이 띠를 주지 않으면 null')
    ] = None


def market_band(average: float | None, price_range: list[float | None] | None) -> NaverMarketBand | None:
    """시세 평균(만원)과 [하한, 상한] 목록(`manwon_range`)을 한 거래 유형의 시세로. 목록이 None 이면 하위·상위 둘 다 null.

    평균·하위·상위를 모두 모르면 None(거래 값 null)이고, 하나라도 있으면 모르는 칸만 null 인 객체다.
    """
    low, high = price_range if price_range is not None else (None, None)
    if average is None and low is None and high is None:
        return None
    return NaverMarketBand(average_manwon=average, low_manwon=low, high_manwon=high)


def manwon_range(price_range: NaverPriceRangeModel | None, scale: bool = True) -> list[float | None] | None:
    """시세 범위(하한·상한)를 만원으로 (`won_to_manwon_range`). `scale` 이 False 면 비율(전세가율 %, 37~41)이라 그대로 둔다.

    둘 다 0·None 이면 없음이다 (기관이 0 을 주면 시세 없음이라 전세가율 0% 를 내지 않는다, 시세 평균·범위와 같은 규칙).
    """
    if price_range is None:
        return None
    if scale:
        return won_to_manwon_range(price_range.floor, price_range.ceiling)
    if not price_range.floor and not price_range.ceiling:
        return None
    return [price_range.floor, price_range.ceiling]


def market_price_fields(
    deal_average_won: int | float | None,
    deal_range: NaverPriceRangeModel | None,
    deposit_average_won: int | float | None,
    deposit_range: NaverPriceRangeModel | None,
    lease_per_deal_rate: NaverPriceRangeModel | None,
) -> dict[str, Any]:
    """기관 시세 한 점의 매매·전세 띠와 전세가율 하한·상한 (`NaverMarketPrice`·`NaverMarketPricePoint` 의 같은 칸).

    평균 0 은 범위(`manwon_range`)처럼 없음(None)으로 본다 (네이버 웹도 0 이면 시세를 그리지 않는다).
    """
    ratio = manwon_range(lease_per_deal_rate, scale=False)
    return {
        'sale': market_band(won_to_manwon(deal_average_won) or None, manwon_range(deal_range)),
        'jeonse': market_band(won_to_manwon(deposit_average_won) or None, manwon_range(deposit_range)),
        'jeonse_ratio_low_percent': ratio[0] if ratio is not None else None,
        'jeonse_ratio_high_percent': ratio[1] if ratio is not None else None,
    }


DONG_LETTER_BY_SPELLING: dict[str, str] = {
    '에이': 'A', '비': 'B', '씨': 'C', '디': 'D', '이': 'E', '에프': 'F', '지': 'G', '에이치': 'H',
}
"""한글로 쓴 영문 동 이름. 단지마다 'A' 로도 '에이' 로도 온다 (성재하이빌 '에이'·'비', 2026-10-09 확인)."""


def dong_key(name: str) -> str:
    """'104동'·'104 동'·'104' 를 같은 동으로 본다. 'A'·'a'·'에이'·'에이동' 도 같은 동이다."""
    name = name.strip().replace(' ', '')
    name = name[:-1] if name.endswith('동') and len(name) > 1 else name
    return DONG_LETTER_BY_SPELLING.get(name, name.upper())


def dong_label(name: str) -> str:
    """제목·안내에 쓰는 동 표기. '101'·'가'·'A'·'에이' 는 뒤에 '동' 을 붙이고, 건물 이름은 그대로 둔다.

    네이버 동 이름은 '동' 없이 온다 (매물 410건 중 '동' 으로 끝나는 이름 없음). 빌라 단지 일부는 동
    이름 자리에 건물 이름('가람아트빌', '청림빌라1차')이 와서 '동' 을 붙이면 어색하다. 한글이 세 자 넘게
    이어지면 건물 이름으로 본다 (2026-10-09 확인).
    """
    if name in DONG_LETTER_BY_SPELLING or not re.search('[가-힣]{3,}', name):
        return f'{name}동'
    return name


def resolve_dong_numbers(
    client: NaverClient,
    complex_number: int,
    dong_names: list[str],
    *,
    villa: bool | None = None,
) -> tuple[list[str], bool]:
    """동 이름을 단지 매물 필터가 받는 동 번호로 바꾼다. 빌라 단지인지도 함께 돌려준다.

    `villa` 를 모르면(None) 아파트 단지 동 목록부터 묻고, 비면 빌라 동 목록을 다시 묻는다. 빌라 엔드포인트가
    답하지 않으면 동 정보가 없는 아파트 단지다 (`villa_fallback_found`). 알면 그쪽 목록만 묻는다.

    Raises:
        JibsaError: 단지에 없는 동 이름이면 NOT_FOUND (힌트에 그 단지의 동 이름).
    """
    buildings = []
    if not villa:
        # 빌라 단지에도 아파트 동 목록은 result=null 이 아니라 빈 목록이 와서 unwrap 이 에러를 내지 않고 아래 빌라 동
        # 목록으로 넘어간다 (서진빌라 724112 → 빌라 동 목록 '1동', 2026-10-10)
        buildings = unwrap(
            client.run_request_complex_building_list_v1(
                NaverComplexBuildingListV1RequestParameterModel(complex_number=complex_number)
            ),
            '단지 동 목록',
        )
    # 아파트 단지라고 이미 알면 빈 동 목록이어도 빌라로 다시 묻지 않는다
    if not buildings and villa is not False:
        response = client.run_request_complex_villa_building_list_v1(
            NaverComplexVillaBuildingListV1RequestParameterModel(complex_number=complex_number)
        )
        if villa or villa_fallback_found(response):
            villa = True
            buildings = unwrap(response, '단지 동 목록')
    number_by_key = {dong_key(building.name): str(building.number) for building in buildings}
    missing = [name for name in dong_names if dong_key(name) not in number_by_key]
    if missing:
        available = ', '.join(dong_label(building.name) for building in buildings)
        # 동 표기는 건물 이름('청림빌라1차')일 수도 있어 조사를 끝 글자로 고른다
        labels = ', '.join(dong_label(dong_key(name)) for name in missing)
        raise JibsaError(
            code='NOT_FOUND',
            message=f"단지 {complex_number} 에 {labels}{particle(labels, '이/가')} 없습니다",
            hint=f'이 단지의 동: {available}' if available else '없는 단지 번호이거나 네이버에 동 정보가 없는 단지입니다. 단지 번호를 확인하고, 맞으면 --dong 없이 조회하세요',
        )
    numbers: list[str] = []
    for name in dong_names:
        number = number_by_key[dong_key(name)]
        if number not in numbers:
            numbers.append(number)
    return numbers, bool(villa)


class PageScan(BaseModel):
    """페이지 넘김 조회 예산과 훑은 결과 (`scan_pages` 가 채운다)."""

    limit: Annotated[
        int,
        Field(description='조회 할당량 (--limit). 받은 개수로 센다')
    ]
    max_requests: Annotated[
        int,
        Field(description='네이버 차단을 피하려는 페이지 요청 상한')
    ]
    received: Annotated[
        int,
        Field(description='지금까지 받은 항목 수 (할당량을 쓴 만큼). 빈 항목(null)이라 빼고 읽은 자리도 서버가 센 자리라 들어 있다')
    ] = 0
    null_items: Annotated[
        int,
        Field(description='받은 쪽에서 빈 항목(null)이라 빼고 읽은 수 (`received` 에 이미 들어 있다). 있으면 `scan_null_items_notes` 로 알린다')
    ] = 0
    page_requests: Annotated[
        int,
        Field(description='지금까지 보낸 페이지 요청 수')
    ] = 0
    truncated: Annotated[
        bool,
        Field(description='받을 게 남았는데 요청 상한에 닿아 멈췄는지')
    ] = False
    stalled: Annotated[
        bool,
        Field(description='서버가 다음 쪽이 있다고 했는데 그 쪽이 준 항목이 모두 이미 받은 것이거나 쪽이 비어 멈췄는지')
    ] = False
    total: Annotated[
        int,
        Field(description='서버 집계 (마지막 페이지의 totalCount)')
    ] = 0
    seen: Annotated[
        set[Any],
        Field(description='이미 받은 항목 번호. 준 항목이 모두 이미 받은 번호면 커서가 멈춘 것으로 본다')
    ] = set()
    cursor: Annotated[
        tuple[str | None, Any] | None,
        Field(description=(
            '마지막으로 훑은 목록에서 다음 페이지를 받을 (seed, lastInfo). 다음 페이지가 없거나 커서가 멈췄으면 None. '
            '이어 받기(--next)에 쓴다'
        ))
    ] = None

    def stopped_short(self, *, resumed: bool) -> bool:
        """네이버가 다음 쪽이 있다면서 새 항목을 주지 않아 멈췄고(`stalled`) 받지 못한 항목이 남았는지.

        이어 받은 결과(`resumed`)의 `total` 은 앞 결과까지 센 수라 견주지 않고, 멈췄으면 남았다고 본다. 이어 받기가 아니면
        받은 수가 서버가 센 수에 닿았을 때 다 받은 것이다 (2026-11-24 리뷰: 30건 중 30건에 '일부만 받았다').
        `pagination_notes` 의 `stalled` 와 결과의 `has_more` 가 이 하나를 같이 쓴다.
        """
        return self.stalled and (resumed or self.total > self.received)

    @property
    def exhausted(self) -> bool:
        """서버가 다음 쪽이 없다고 해 끝까지 받았는지. `fetch` 가 None 을 줘 `cursor` 가 None 이 된 경우도 포함한다.

        마지막 쪽이 마침 `limit` 에 닿은 것을 '더 있다' 로 보지 않게 한다.
        """
        return self.cursor is None and not self.stalled


def resume_cursor(position: dict[str, Any] | None) -> tuple[str | None, Any] | None:
    """이어 받기 위치에 담긴 (seed, lastInfo). 목록 처음부터면 None."""
    if not position or position.get('seed') is None and position.get('last_info') is None:
        return None
    return position.get('seed'), position.get('last_info')


def cursor_position(cursor: tuple[str | None, Any] | None) -> dict[str, Any]:
    """`resume_cursor` 가 되읽을 수 있게 (seed, lastInfo) 를 이어 받기 위치로 담는다."""
    if cursor is None:
        return {}
    return {'seed': cursor[0], 'last_info': cursor[1]}


_Page = NaverArticlePageModel | NaverComplexListPageModel | NaverRedevelopmentAreaPageModel


def scan_pages(
    scan: PageScan,
    fetch: Callable[[int, str | None, Any], _Page | None],
    keep: Callable[[Any], Any],
    *,
    page_size: int,
    start: tuple[str | None, Any] | None = None,
) -> None:
    """`fetch(size, seed, last_info)` 로 페이지를 차례로 받아 항목마다 `keep(item)` 을 부른다.

    할당량(`scan.limit`)은 받은 개수로 센다. 받은 뒤 `keep` 이 버린 항목은 센 채로 두어 다시 채우지 않는다
    (docs/development/output-contract.md 의 개수 상한). 빈 항목(null)이라 빼고 읽은 자리도 서버가 센 자리라 센다
    (`scan.null_items`). 할당량을 다 쓰거나, 다음 페이지가 없거나, 다음 페이지가 있다는데 준 항목이 모두
    이미 받은 번호이거나 쪽이 완전히 빈 페이지(커서가 멈춤)가 오거나(`scan.stalled` 를 켜고 그 쪽은 세지 않는다), `fetch` 가 None 을 주면 멈춘다. 받을 게 남았는데 요청이
    `scan.max_requests` 에 닿으면 `scan.truncated` 를 켠다. 다음 요청에는 앞 페이지의 seed·lastInfo 를 넘긴다
    (seed 가 빠지면 랭킹순이 페이지마다 다시 섞인다).

    멈출 때 다음 페이지를 받을 커서를 `scan.cursor` 에 남긴다 (다음 페이지가 없으면 None). 다음 호출에서 `start` 로
    주면 그 페이지부터 받는다 (이어 받기). 네이버 커서는 마지막 항목의 정렬 값이라 페이지 크기가 달라도 이어진다.

    Args:
        keep: 항목을 걸러 담고 그 항목의 번호를 돌려준다 (모르면 None).
        start: 이어 받을 (seed, lastInfo). 없으면 첫 페이지부터.
    """
    seed, last_info = start if start is not None else (None, None)
    scan.cursor = start
    while True:
        if scan.received >= scan.limit:
            return
        if scan.page_requests >= scan.max_requests:
            scan.truncated = True
            return
        scan.page_requests += 1
        page = fetch(min(page_size, scan.limit - scan.received), seed, last_info)
        if page is None:
            scan.cursor = None
            return
        scan.total = page.total_count
        ids = [keep(item) for item in page.items]
        new_ids = set(ids) - {None} - scan.seen
        dropped = page.null_items('items')
        # 다음 쪽이 있다는데 준 항목이 모두 이미 받은 번호이거나 쪽이 완전히 빈 쪽이면 되풀이된 쪽이라 세기 전에 멈추고 호출부가
        # 일부만 받았다고 알리게 한다. 번호를 모르는 항목(keep 이 None)·빈 항목(null)은 되풀이인지 알 수 없어 세고 넘어간다
        # (되풀이면 요청 상한에서 truncated 로 멈춘다)
        if page.has_next_page and not new_ids and None not in ids and not dropped:
            scan.stalled = True
            scan.cursor = None
            return
        # 빈 항목(null)을 뺐어도 서버는 그 자리를 센 쪽이라 받은 수에 더한다 (쪽 넘김이 일찍 멈추거나 같은 매물을 다시 받지 않게)
        scan.received += len(page.items) + dropped
        scan.null_items += dropped
        scan.seen |= new_ids
        if not page.has_next_page:
            scan.cursor = None
            return
        # seed 는 첫 응답 값이 마지막 페이지까지 그대로 오고 null 로 온 적이 없어 응답 값을 그대로 넘긴다
        # (단지 매물·동 전체·최신순·지도 칸 매물(clusteredArticles)·재개발 구역·단지 목록 6종 22쪽, 2026-10-10 확인)
        seed, last_info = page.seed, page.last_info
        scan.cursor = (seed, last_info)


def scan_null_items_notes(scan: PageScan, what: str) -> list[str]:
    """`scan_pages` 가 빈 항목(null)을 빼고 읽었으면 그 안내 한 줄. 없으면 빈 목록.

    받은 수(`scan.received`)에는 뺀 자리가 이미 들어 있어 쪽 넘김 판정은 맞다. 이 안내는 받은 매물·단지가 서버가 센 수보다 적게
    보이는 까닭을 알린다.

    Args:
        what: 사이트 이름을 붙인 목록 이름 ('네이버 단지 매물').
    """
    return [null_items_note(what, scan.null_items)] if scan.null_items else []


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


# `pagination_notes` 의 제외 사유. 반경 밖은 사각형으로 받아 반경으로 거르는 검색(반경 매물·단지·재개발 구역)에만 있다.
# 동 전체·단지·재개발 구역 매물은 반경 없이 받아, '반경 밖' 이라고 하면 쓸 수 없는 --radius 를 바꾸게 만든다.
# 목록 응답에는 매물 상태·노출 여부 필드가 없어 거래 불가로 빼는 매물은 없다. 빼는 것은 번호가 같은 중복과 모르는 거래 유형
# 코드(`article_info_to_listing`)뿐이다 (2026-10-14 실측: 역삼동 동 전체 목록 20건의 모든 키에 상태 필드 없음)
# 단지 목록(`search.py` `list_area_complexes`)은 거래 유형으로 빼지 않고 본문(단지 정보)이 없는 단지를 뺀다. 위치가 없는 단지는
# 반경 안인지 알 수 없는 반경 검색에서만 빼고, 경계 검색은 위치로 빼지 않는다 (2026-11-24 리뷰)
EXCLUDED_REASON: str = '중복이거나 알 수 없는 거래 유형인'
RADIUS_EXCLUDED_REASON: str = '중복이거나 알 수 없는 거래 유형 또는 검색 범위(반경) 밖의'
COMPLEX_EXCLUDED_REASON: str = '중복이거나 단지 정보를 알 수 없는'
COMPLEX_RADIUS_EXCLUDED_REASON: str = '중복이거나 단지 정보·위치를 알 수 없거나 검색 범위(반경) 밖의'
# 반경 검색의 서버 집계(total)가 센 범위. 반경 원이 아니라 그 원을 감싼 사각형 안이라 반경 안 수보다 크다
RADIUS_TOTAL_BASIS: str = '반경을 감싼 사각형 안'


def boundary_filter(filter_: NaverArticleFilterModel, legal_division_code: str) -> NaverArticleFilterModel:
    """경계 검색 필터. 법정동 코드 하나를 넣는다. 시·군·구 코드면 시·군·구 단위(GUN), 아니면 읍·면·동 단위(EUP)다.

    동 매물·단지·재개발 구역 목록이 같은 꼴을 받는다 (성동구 + GUN 도 같은 API 다, 2026-11-18 실측). 단위는 코드로 정한다
    (`is_district_code`). 리 코드는 `is_dong_code` 가 아니라서 `not is_dong_code` 로 가르면 시·군·구로 잘못 읽힌다.
    """
    unit = 'GUN' if is_district_code(legal_division_code) else 'EUP'
    return filter_.model_copy(update={'legal_division_numbers': [legal_division_code], 'legal_division_type': unit})


class AreaScope(NamedTuple):
    """지역 안을 찾는 검색(매물·단지·재개발 구역)이 동·시·군·구 경계인지 반경인지에 따라 달라지는 안내 말 (`area_scope`)."""

    scope: str  # pagination_notes 의 scope ('전부'·'없습니다' 가 어느 범위인지)
    total_basis: str  # pagination_notes 의 total_basis
    narrow: str  # pagination_notes 의 narrow
    narrow_action: str  # 요청 상한 안내 끝의 좁히는 법 ('조건을 좁혀' / '반경을 줄이거나 조건을 좁혀')


def area_scope(legal_division_code: str | None, radius_km: float) -> AreaScope:
    """법정동 코드가 있으면 동·시·군·구 경계, 없으면 반경 검색의 안내 말."""
    if legal_division_code is not None:
        return AreaScope(scope='', total_basis='', narrow='조건·지역', narrow_action='조건을 좁혀')
    return AreaScope(
        scope=f'반경 {radius_km:g}km 안에서 ', total_basis=RADIUS_TOTAL_BASIS, narrow='조건·반경',
        narrow_action='반경을 줄이거나 조건을 좁혀',
    )


def pagination_notes(
    total: int,
    returned: int,
    limit: int,
    inspected: int,
    *,
    subject: str = '매물',
    truncated: bool = False,
    excluded_reason: str = EXCLUDED_REASON,
    resumable: bool = False,
    resumed: bool = False,
    scope: str = '',
    total_basis: str = '',
    null_items: int = 0,
    stalled: bool,
    exhausted: bool,
    narrow: str,
) -> list[str]:
    """조회 예산과 실제 제외 결과에 맞춰 추가 조회 없이 안내한다.

    `truncated`(요청 상한에 걸려 멈춤)면 호출한 쪽의 상한 안내가 '더 있을 수 있다' 고 알리므로, 검색을 마쳤다는
    안내와 --limit·필터를 좁히라는 안내를 붙이지 않는다 (홍천 월세 120건 → 지도 칸 24/40개, 49건에서 둘이 함께
    나와 서로 어긋났다, 2026-10-10).

    Args:
        excluded_reason: 제외 안내에서 `subject` 앞에 붙는 제외 사유 (관형어). 반경으로 거르는 검색은
            `RADIUS_EXCLUDED_REASON`.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        resumed: 이어 받기(`--next`)로 받은 결과면 True. 앞 결과에서 받은 매물이 있어 '전부' 대신 '남은 매물' 이라 한다.
        scope: '전부' 가 어느 범위인지 앞에 붙일 말 (예: '반경 1km 안에서 '). 반경을 넓히면 더 나오는데 '전부' 만 쓰면
            찾은 범위의 전부인지 알 수 없다 (2026-10-20 LLM 사용 시험: 1km '26건이 전부' 뒤 2km 85건).
        total_basis: `total` 이 정확한 범위의 수가 아니면 그 범위 (반경 검색은 `RADIUS_TOTAL_BASIS`). 주면 '약 N건(범위)' 으로
            쓴다. 반경 검색에 '조건에 맞는 매물이 1197건' 이라고 하면 사각형 모서리까지 센 수를 반경 안의 수로 읽는다
            (2026-11-11 LLM 사용 시험: 합정역 1km 상가).
        null_items: `inspected` 에 든 빈 항목(null) 수 (`PageScan.null_items`). 서버가 센 자리라 `inspected` 에는 들어 있어 남은 매물을 셀 때 쓰지만,
            중복·거래 유형으로 뺀 수에서는 뺀다 (빈 항목은 따로 안내하므로 그 이유로 뺐다고 하지 않는다).
        stalled: 호출부가 `scan.stopped_short(resumed=...)` 를 넘긴다. 켜지면 '전부' 대신 확인한 데까지만 알린다.
        exhausted: 호출부가 `scan.exhausted` 를 넘긴다.
        narrow: 더 남았을 때 좁히라고 권할 것 (`more_hint`). 동·구 검색은 '조건·지역', 반경 검색은 '조건·반경', 단지·재개발
            구역 하나의 매물은 좁힐 지역이 없어 그 매물의 조건만 준다 (2026-11-10 리뷰·실측: 헬리오시티 111515 2,257건
            --limit 120 에 '조건·지역을 좁히세요'). 기본값을 두지 않는다. 두었더니 재개발 구역 반경 검색이 값을 빠뜨려
            '조건·지역' 이 나갔다 (2026-11-10 리뷰).
    """
    notes: list[str] = []
    excluded = min(inspected - null_items, limit) - returned
    # 단지·구역은 다른 소스처럼 '곳' 으로 센다 (2026-11-10 리뷰: 재개발 구역이 '전체 45건 중 2건입니다')
    unit = '곳' if subject in ('단지', '구역') else '건'
    # 할당량을 다 써서 멈췄으면 서버 수가 받은 수보다 클 때 더 받을 매물이 남았다. 서버가 더 주지 않고 끝났으면(할당량 전에 멈춤)
    # 서버 수가 커도 남은 매물이 아니다. 이어 받을 수 있거나, 요청 상한에서 멈췄거나, 다음 쪽이 있다며 새 항목을 주지 않았으면(stalled)
    # 더 있다. 이어 받은 결과의 total 은 앞 결과까지 센 수라 받은 수와 견주지 않는다 (next 가 없으면 남은 매물이 없다)
    reached = inspected >= limit and not exhausted
    more = resumable or truncated or stalled or (not resumed and reached and total > inspected)
    if returned < limit and excluded > 0:
        notes.append(note(
            '제외',
            f"{excluded_reason} {subject}{particle(subject, '을/를')} 빼고 {returned}{unit}입니다 "
            + ('(뺀 만큼 다시 채우지 않음)' if more else f'(더 받을 {subject} 없음)'),
        ))
    elif returned < limit and not truncated and not stalled:
        what = scope + (f'남은 {subject}' if resumed else f'조건에 맞는 {subject}')
        # 0건이면 '이 0건이 전부입니다' 대신 없다고 한다 (2026-11-11 LLM 사용 시험: 수완동 아파트 전세 3억 이하)
        notes.append(
            f"{what}{particle(subject, '은/는')} 이 {returned}{unit}이 전부입니다" if returned
            else f"{what}{particle(subject, '이/가')} 없습니다"
        )
    # 다른 소스의 [일부](`limit_notes`)처럼 전체 수를 먼저 말하고 그중 몇 건을 보여 주는지 잇는다. 네이버만 '전체 38건 중
    # 일부입니다' 라 몇 건을 보여 주는지 없었고, --limit 이 최대값이면 수 없이 '--limit 의 최대값은 …' 만 나갔다 (2026-11-11
    # LLM 사용 시험: 역삼역 원룸·강남역 단지)
    found = f"조건에 맞는 {subject}{particle(subject, '이/가')} {'약 ' if total_basis else ''}{total}{unit}" + (
        f'({total_basis})' if total_basis else ''
    )
    if not returned:
        shown = f"{found} 있지만, 확인한 {subject}{particle(subject, '이/가')} 모두 빠져 보여 줄 {subject}{particle(subject, '이/가')} 없습니다"
    else:
        shown = f"{found} 있고, {'이어서' if resumed else '그중'} {returned}{unit}{'을' if resumed else '만'} 보여 줍니다"
    if resumable:
        notes.append(note('일부', f'{shown}. {NEXT_HINT}'))
        return notes
    if stalled:
        got = inspected - null_items
        stall = f"네이버가 더 있다면서 새 {subject}{particle(subject, '을/를')} 주지 않아"
        narrow_hint = f"더 보려면 {narrow}{particle(narrow, '을/를')} 좁혀 다시 찾으세요"
        if resumed:
            notes.append(note('일부', f'{stall} 이번에는 {got}{unit}까지만 받았습니다. {narrow_hint}'))
        else:
            notes.append(note('일부', f'{stall} {got}{unit}까지만 받았습니다 ({found}). {narrow_hint}'))
        return notes
    # 이어 받은 결과의 returned 는 이번 몫이라 전체 수와 견주면 앞 결과에서 받은 매물을 빼먹는다
    if truncated or resumed:
        return notes
    # 더 받을 것이 남았는지는 받은 수(inspected)로 본다. 돌려준 수와 견주면 다 받고 뺐을 뿐인데 '더 있다' 고 하거나, 1건만
    # 빠져도 더 있다는 안내가 사라졌다 (2026-10-23 리뷰: 반경 단지 --limit 1 이 전체 89건에 '[제외] … 0건' 만 냈다)
    # 서버가 더 주지 않고 끝났으면(할당량 전에 멈춤) '더 보려면' 을 권하지 않는다. 반경 검색은 total 이 반경을 감싼 사각형 기준이라
    # 받은 수보다 큰 것이 정상이므로 아무것도 더하지 않고, 경계 검색·단지·구역 매물만 총수가 다르다는 것을 알린다
    if total > inspected and not reached:
        if not total_basis:
            notes.append(note('참고', f'네이버가 센 수는 {total}{unit}이지만 더 주지 않아 받은 {inspected - null_items}{unit}까지입니다'))
        return notes
    if total > inspected and reached:
        notes.append(note('일부', f'{shown}. {more_hint(limit, MAX_LIST_LIMIT, narrow)}'))
    return notes


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


class NaverTradeConditions(RequestModel):
    """거래 유형·가격 조건 (단지·재개발 구역 매물 목록과 지도 검색 공통). 금액은 만원이고 원으로 바꿔 보낸다.

    가격 조건은 모두 서버 필터로 보내고 받은 뒤 다시 거르지 않는다. 그 금액이 없는 거래 유형은 서버도 거르지 않는다.
    """

    trade_types: Annotated[
        list[str],
        Field(description='거래 유형 (TRADE_CODE_BY_NAME 의 이름). 비면 전체')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None


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


# real-price·market-price 의 --period (이름 → 달 수). 웹 실거래·시세 기간 선택지는 startDate 로 보내는 3개월·3년·5년이고 1년은 jibsa 가 더한 값이다
PERIOD_MONTHS_BY_NAME: dict[str, int] = {'3개월': 3, '1년': 12, '3년': 36, '5년': 60}


def bounding_box(lat: float, lng: float, radius_km: float) -> NaverBoundingBoxModel:
    south, north, west, east = box_around(lat, lng, radius_km)
    return NaverBoundingBoxModel(left=west, right=east, top=north, bottom=south)


def bounded_precision(radius_km: float) -> int:
    """정렬 목록(boundedArticles·boundedComplexes)에 보낼 지도 줌. 반경을 다 덮는 가장 높은 줌이다.

    줌이 높을수록 사각형을 다 주지 않고 중심 근처만 준다. 모델 기본값 16 이면 반경 2km 부터 가장자리 매물이 빠져,
    빠진 매물만 조건에 맞을 때 '0건이 전부' 라고 냈다 (2026-10-31 강남역 2km 아파트 전세 5억 이하 + 500세대 이상:
    줌 16 0건, 지도 칸 매물(clusteredArticles) 6건). 같은 날 강남역 아파트 전세 4~5억의 반경 안 매물 수:
    1.5km 줌 16·15 모두 10건, 2km 줌 16 21건·15 33건·14 33건, 3km 줌 15 60건·14 62건·13 62건.
    단지 목록도 같다 (3km 아파트 단지 total 줌 16 242곳, 14 1,048곳). 줌을 더 낮추면 반경 밖 매물이 섞여 `--limit`
    몫을 쓴다 (1km 줌 14 는 51건 중 22건이 반경 밖, 줌 16 과 반경 안 수가 같음). 재개발 구역 목록은 따로 14 를 쓴다.
    """
    if radius_km <= 1.5:
        return 16
    if radius_km <= 2:
        return 15
    return 14
