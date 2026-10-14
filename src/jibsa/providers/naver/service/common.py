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
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    box_around,
    haversine_km,
)
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.korean import particle
from jibsa.core.listing import (
    KST,
    Listing,
    join_address,
    m2_to_pyeong,
    normalize_date,
    won_to_manwon,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverArticleSortType,
    NaverBoundingBoxModel,
    NaverComplexBuildingListV1RequestParameterModel,
    NaverComplexPyeongListV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaPyeongListV1RequestParameterModel,
    NaverOneRoomShape,
    NaverRealEstateType,
)
from jibsa.providers.naver.api.response.common import (
    NaverArticleInfoModel,
    NaverArticleListItemModel,
    NaverArticlePageModel,
    NaverComplexArticleCountModel,
    NaverComplexListPageModel,
    NaverFacilityInfoModel,
    NaverListBuildingInfoModel,
    NaverPriceRangeModel,
    NaverPyeongModel,
    NaverRedevelopmentAreaCountModel,
    NaverRedevelopmentAreaPageModel,
    NaverResponseModel,
    NaverSchoolModel,
)

from typing import (
    Annotated,
    Any,
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
# 면적 필터 기준. 전용이면 filtersExclusiveSpace 를 켠다. 결과의 area_m2 가 전용면적이라 기본은 전용
AREA_BASES: tuple[str, ...] = ('전용', '공급')
WON_PER_MANWON: int = 10_000
# 검색 모드(search listings·complexes·redevelopment, --complex·--redevelopment)의 --limit 최대값.
# CLI 옵션의 max 와 상한 안내(`pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120
# 가까운 순이 아닌 정렬은 사각형 안 매물 목록(boundedArticles)을 네이버 정렬 그대로 받는다.
# limit 건까지만 받고, 반경 밖(사각형 모서리) 매물을 빼도 그만큼 다시 받지 않는다.
SORT_TYPE_BY_NAME: dict[str, NaverArticleSortType | None] = {
    '가까운순': None,
    '랭킹순': 'RANKING_DESC',
    '가격낮은순': 'PRICE_ASC',
    '가격높은순': 'PRICE_DESC',
    '최신순': 'DATE_DESC',
    '면적좁은순': 'SPACE_ASC',
    '면적넓은순': 'SPACE_DESC',
}
# 단지 매물 목록 정렬. 거리가 없어 가까운순은 뺀다
COMPLEX_SORT_TYPE_BY_NAME: dict[str, NaverArticleSortType] = {
    name: code for name, code in SORT_TYPE_BY_NAME.items() if code is not None
}


def article_url(article_number: str) -> str:
    return f'https://fin.land.naver.com/articles/{article_number}'


def complex_url(complex_number: int) -> str:
    return f'https://fin.land.naver.com/complexes/{complex_number}'


def unwrap(response: NaverResponseModel[T], what: str) -> T:
    """봉투의 `result` 를 꺼낸다. 실패 응답이면 `JibsaError`.

    Raises:
        JibsaError: 성공 응답인데 `result` 가 비었으면 NOT_FOUND (없는 단지 번호 등),
            `isSuccess` 가 false 면 UPSTREAM_ERROR.
    """
    if response.is_success and response.result is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'네이버 {what} 결과가 없습니다',
            hint='번호가 맞는지 확인하세요',
        )
    if not response.is_success or response.result is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'네이버 {what} 조회 실패: {response.detail_code or ""} {response.message or ""}'.strip(),
            hint='번호가 맞는지 확인하세요. 비공식 API 라 스펙이 바뀌었을 수 있습니다',
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
        Field(description='배정 방식 (배정, 선택)')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)')
    ] = None
    walking_minutes: Annotated[
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


class NaverListingsResult(BaseModel):
    """매물 목록 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    total_count: Annotated[
        int,
        Field(description='서버 집계 매물 수. search 는 반경을 감싸는 사각형 안, 동 경계로 찾았으면 동 안 정확한 수 (조건 적용 후, limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    listings: Annotated[
        list[Listing],
        Field(description='매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='요청 상한으로 일부 클러스터만 훑었다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


MARKET_PRICE_PROVIDER_NAMES: dict[str, str] = {'kab': '한국부동산원', 'kbstar': 'KB부동산', 'neonet': '부동산뱅크'}


# 부가 정보 조회에서 그 값만 모름(None)으로 두는 오류: 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`, 압축이 깨진
# 응답도 HTTPError)만 잡는다. 요청 제한(RateLimitedError)은 JibsaError 라 잡지 않아 그대로 올라간다.
# 제한을 끈 정책(RateLimitPolicy(enabled=False))이면 429 가 HTTPStatusError 로 와 여기서 모름이 되지만, 그 정책은
# 라이브러리로 직접 만들 때만 쓰이고 CLI 는 늘 켜 둔다 (core/ratelimit.py on_rate_limited, 2026-10-11 확인).
# ValidationError 는 람다 안에서 만드는 요청 모델 오류도 잡지만, 요청 값은 CLI 가 검증한 값이나 네이버 응답 값
# (법정동 코드 10자리, 단지 유형 코드 등)이라 사용자 입력으로는 생기지 않는다 (2026-10-10 확인)
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = OPTIONAL_LOOKUP_BASE_ERRORS


def result_or_none(request: Callable[[], NaverResponseModel[T]]) -> T | None:
    """부가 정보 조회. 실패하면 그 값만 모름(None)으로 둔다 (매물 상세·단지 요약 전체를 실패시키지 않는다)."""
    try:
        return request().result
    except OPTIONAL_LOOKUP_ERRORS:
        return None


# 단지형 빌라(연립·다세대·도시형생활주택 단지). 학교는 이 유형이면 villa 로 묻는다
VILLA_COMPLEX_CODES: frozenset[str] = frozenset({'A05', 'A06', 'A07'})
SCHOOL_ALLOCATION_LABELS: dict[str, str] = {'01': '배정', '02': '선택'}


def assigned_schools(schools: list[NaverSchoolModel]) -> list[NaverAssignedSchool]:
    """배정 초등학교 목록. 이름이 없는 항목은 뺀다."""
    return [
        NaverAssignedSchool(
            school_code=school.code,
            name=school.name,
            assignment=SCHOOL_ALLOCATION_LABELS.get(school.allocation_type or ''),
            operation_type=school.operation_type,
            walking_minutes=school.walking_minute,
            distance_m=school.distance,
            students_per_class=school.students_per_classroom,
            students_per_teacher=school.students_per_teacher,
        )
        for school in schools
        if school.name
    ]


def known_floor(value: str | None) -> str | None:
    """층 값. 층이 없다는 뜻으로 오는 '0'·'-'·빈 값은 모름(None)으로 둔다.

    건물 전체를 파는 재개발·단독 매물은 목록에서 해당 층·전체 층을 '0' 으로, 상세에서 '-' 로 준다
    (노량진6구역 매물: 목록 전체 층 '0', 상세 '-'/'-', 2026-10-10 확인).
    """
    return None if value in (None, '', '0', '-') else value


def _floor(info: NaverArticleInfoModel) -> tuple[str | None, str | None]:
    """목록 매물의 해당 층·전체 층. floorDetailInfo 가 있으면 그것만 본다.

    floorDetailInfo 가 '0'/null 인데 floorInfo 가 '-1/3' 인 매물은 건물 전체를 파는 단독·다가구(C03)·상가건물(D04)이고,
    floorInfo 는 해당 층/전체 층이 아니라 지하~지상 범위다 (봉천동 120건 중 7건, 상세도 층·전체 층 모두 null, 2026-10-11).
    그래서 floorInfo 로 대신 채우지 않는다.
    """
    detail = info.article_detail
    if detail is None:
        return None, None
    if detail.floor_detail_info is not None:
        return known_floor(detail.floor_detail_info.target_floor), known_floor(detail.floor_detail_info.total_floor)
    if detail.floor_info and '/' in detail.floor_info:
        target, total = detail.floor_info.split('/', 1)
        return known_floor(target), known_floor(total)
    return known_floor(detail.floor_info), None


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
) -> Listing | None:
    """목록 항목(대표 매물)을 공통 `Listing` 으로 바꾼다. 원 → 만원 환산.

    모르는 거래 유형 코드면 None 이다. 어느 가격 필드가 맞는지 몰라 틀린 값을 내보내게 되므로
    목록에서 뺀다 (직방이 전세·월세·매매 밖의 매물을 빼는 것과 같다).
    """
    info = item.representative_article_info
    price = info.price_info
    trade_type = TRADE_NAME_BY_CODE.get(info.trade_type)
    if trade_type is None:
        return None
    floor, building_floor = _floor(info)

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
    return Listing(
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
        registered_at=normalize_date(info.verification_info.exposure_start_date) if info.verification_info else None,
        approved_at=building_approved_at(info.building_info),
    )


def won_to_manwon_range(low: float | None, high: float | None) -> list[float | None] | None:
    """원 단위 범위(호가·시세)를 만원으로. 둘 다 없으면 None.

    그 거래 매물이 없으면 호가는 0 이 아니라 null 로 온다 (더힐 725113 전세 0건: rentMinPrice·rentMaxPrice null,
    2026-10-11). 0 도 없음으로 보는 것은 0원 범위가 뜻이 없어서다.
    """
    if not low and not high:
        return None
    return [won_to_manwon(low), won_to_manwon(high)]


def trade_article_counts(counts: NaverComplexArticleCountModel | NaverRedevelopmentAreaCountModel) -> dict[str, int]:
    """거래 유형별 매물 수 (단지·단지 목록·재개발 구역 목록·재개발 상세의 `article_counts`)."""
    return {
        '매매': counts.deal_count,
        '전세': counts.lease_deposit_count,
        '월세': counts.lease_monthly_count,
        '단기임대': counts.lease_short_term,
    }


def raise_missing_pyeongs(complex_number: int, pyeong_numbers: list[int] | None, pyeongs: list[NaverPyeongModel]) -> None:
    """단지 평형 목록에 없는 평형 번호가 있으면 이 단지의 평형 번호를 알려 주며 멈춘다.

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
            hint=f'이 단지의 평형 번호(이름): {available}' if available else '네이버에 평형 정보가 없는 단지입니다. --pyeong 없이 조회하세요',
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


def check_pyeong_numbers(
    client: NaverClient, complex_number: int, pyeong_numbers: list[int], *, villa: bool | None = None,
) -> bool:
    """결과가 비었을 때 평형 번호가 단지에 있는지 확인하고, 빌라 단지인지 돌려준다 (1~2회 호출).

    평형 번호가 틀려도 서버는 매물·실거래·시세를 0건으로 줘서 '없음' 과 구분되지 않는다
    (헬리오시티 평형 999: 단지 매물·실거래·시세 모두 0건, 2026-10-10). 단지 종류를 모르면(None) 아파트 평형 목록을
    먼저 묻고, 비었을 때만 빌라 평형 목록을 묻는다. 아파트 평형 목록은 빌라 단지(가람아트빌 673573)와 없는 단지 번호
    (99999999)에 빈 목록을 준다 (2026-10-11). 단지 정보로 종류를 먼저 정하면 대부분인 아파트에서 1회가 더 든다.

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
    raise_missing_pyeongs(complex_number, pyeong_numbers, pyeongs)
    return villa


def kst_today() -> date:
    """한국 시간 기준 오늘. 실거래·시세 기간은 한국 날짜라 실행하는 컴퓨터의 시간대와 상관없이 맞춘다.

    `date.today()` 는 컴퓨터 시간대를 따라 GMT-12 에서는 하루 전 날짜가 됐다 (시세 since 2025-10-09, 한국 기준 2025-10-10, 2026-10-10).
    """
    return datetime.now(KST).date()


def years_ago(today: date, years: int) -> str:
    """`years` 년 전 같은 날 (2월 29일이면 28일)."""
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def manwon_range(price_range: NaverPriceRangeModel | None, scale: bool = True) -> list[float | None] | None:
    """시세 범위(하한·상한)를 만원으로 (`won_to_manwon_range`). `scale` 이 False 면 비율(전세가율 %, 37~41)이라 그대로 둔다."""
    if price_range is None:
        return None
    if scale:
        return won_to_manwon_range(price_range.floor, price_range.ceiling)
    if price_range.floor is None and price_range.ceiling is None:
        return None
    return [price_range.floor, price_range.ceiling]


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
            hint=f'이 단지의 동: {available}' if available else '네이버에 동 정보가 없는 단지입니다. --dong 없이 조회하세요',
        )
    numbers: list[str] = []
    for name in dong_names:
        number = number_by_key[dong_key(name)]
        if number not in numbers:
            numbers.append(number)
    return numbers, bool(villa)


class PageScan(BaseModel):
    """페이지 넘김 조회 예산. 가까운순처럼 여러 번 이어 부르면 예산과 이미 본 항목을 함께 쓴다."""

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
        Field(description='지금까지 받은 항목 수 (할당량을 쓴 만큼)')
    ] = 0
    page_requests: Annotated[
        int,
        Field(description='지금까지 보낸 페이지 요청 수')
    ] = 0
    truncated: Annotated[
        bool,
        Field(description='받을 게 남았는데 요청 상한에 닿아 멈췄는지')
    ] = False
    total: Annotated[
        int,
        Field(description='서버 집계 (마지막 페이지의 totalCount)')
    ] = 0
    seen: Annotated[
        set[Any],
        Field(description='이미 받은 항목 번호. 처음 보는 항목이 없는 페이지면 커서가 멈춘 것으로 본다')
    ] = Field(default_factory=set)


_Page = NaverArticlePageModel | NaverComplexListPageModel | NaverRedevelopmentAreaPageModel


def scan_pages(
    scan: PageScan,
    fetch: Callable[[int, str | None, Any], _Page | None],
    keep: Callable[[Any], Any],
    *,
    page_size: int,
    max_pages: int | None = None,
) -> None:
    """`fetch(size, seed, last_info)` 로 페이지를 차례로 받아 항목마다 `keep(item)` 을 부른다.

    할당량(`scan.limit`)은 받은 개수로 센다. 받은 뒤 `keep` 이 버린 항목은 센 채로 두어 다시 채우지 않는다
    (references/output-contract.md 의 개수 상한). 할당량을 다 쓰거나, 다음 페이지가 없거나, 처음 보는 항목이
    없는 페이지(커서가 멈춤)가 오거나, `fetch` 가 None 을 주면 멈춘다. 받을 게 남았는데 요청이
    `scan.max_requests` 에 닿으면 `scan.truncated` 를 켠다. 다음 요청에는 앞 페이지의 seed·lastInfo 를 넘긴다
    (seed 가 빠지면 랭킹순이 페이지마다 다시 섞인다).

    Args:
        keep: 항목을 걸러 담고 그 항목의 번호를 돌려준다 (모르면 None).
        max_pages: 이번 호출에서 받을 페이지 상한 (가까운순의 클러스터 하나). 없으면 요청 상한까지.
    """
    seed: str | None = None
    last_info: Any = None
    pages = 0
    while max_pages is None or pages < max_pages:
        if scan.received >= scan.limit:
            return
        if scan.page_requests >= scan.max_requests:
            scan.truncated = True
            return
        scan.page_requests += 1
        pages += 1
        page = fetch(min(page_size, scan.limit - scan.received), seed, last_info)
        if page is None:
            return
        scan.received += len(page.items)
        scan.total = page.total_count
        new_ids = {keep(item) for item in page.items} - {None} - scan.seen
        scan.seen |= new_ids
        if not page.has_next_page or not new_ids:
            return
        # seed 는 첫 응답 값이 마지막 페이지까지 그대로 오고 null 로 온 적이 없어 응답 값을 그대로 넘긴다
        # (단지 매물·동 전체·최신순·가까운순·재개발 구역·단지 목록 6종 22쪽, 2026-10-10 확인)
        seed, last_info = page.seed, page.last_info


def listing_keeper(
    listings: dict[str, Listing],
    center: tuple[float, float] | None,
    radius_km: float | None = None,
) -> Callable[[NaverArticleListItemModel], str]:
    """`scan_pages` 의 `keep`. 매물로 바꿔 (반경 안이면) 담고, 매물 번호를 돌려준다.

    검색 조건은 서버가 걸었으므로 다시 거르지 않는다 (provider-conventions 의 서버 필터 절).
    `radius_km` 를 주면 반경 밖이거나 좌표를 모르는 매물은 반경 안인지 알 수 없어 뺀다.
    """
    def keep(item: NaverArticleListItemModel) -> str:
        listing = article_info_to_listing(item, center)
        if listing is not None and (
            radius_km is None or (listing.distance_km is not None and listing.distance_km <= radius_km)
        ):
            listings.setdefault(listing.id, listing)
        return item.representative_article_info.article_number

    return keep


# `pagination_notes` 의 제외 사유. 반경 밖은 사각형으로 받아 반경으로 거르는 검색(정렬 매물·단지·재개발 구역)에만 있다.
# 동 전체·단지·재개발 매물은 반경 없이 받고, 가까운순(지도 칸)은 반경 밖도 빼지 않고 `beyond_radius_notes` 로 알린다.
# 그런 검색에 '반경 밖' 이라고 하면 쓸 수 없는 --radius 를 바꾸게 만든다.
# 목록 응답에는 매물 상태·노출 여부 필드가 없어 거래 불가로 빼는 매물은 없다. 빼는 것은 번호가 같은 중복과 모르는 거래 유형
# 코드(`article_info_to_listing`)뿐이다 (2026-10-14 실측: 역삼동 동 전체 목록 20건의 모든 키에 상태 필드 없음)
EXCLUDED_REASON: str = '중복이거나 알 수 없는 거래 유형인'
RADIUS_EXCLUDED_REASON: str = '중복이거나 알 수 없는 거래 유형 또는 검색 범위(반경) 밖의'


def pagination_notes(
    total: int,
    returned: int,
    limit: int,
    inspected: int,
    *,
    subject: str = '매물',
    truncated: bool = False,
    excluded_reason: str = EXCLUDED_REASON,
) -> list[str]:
    """조회 예산과 실제 제외 결과에 맞춰 추가 조회 없이 안내한다.

    `truncated`(요청 상한에 걸려 멈춤)면 호출한 쪽의 상한 안내가 '더 있을 수 있다' 고 알리므로, 검색을 마쳤다는
    안내와 --limit·필터를 좁히라는 안내를 붙이지 않는다 (홍천 월세 120건 → 지도 칸 24/40개, 49건에서 둘이 함께
    나와 서로 어긋났다, 2026-10-10).

    Args:
        excluded_reason: 제외 안내에서 `subject` 앞에 붙는 제외 사유 (관형어). 반경으로 거르는 검색은
            `RADIUS_EXCLUDED_REASON`.
    """
    notes: list[str] = []
    excluded = min(inspected, limit) - returned
    if returned < limit and excluded > 0:
        notes.append(
            f"최대 {limit}건을 요청했지만, {excluded_reason} {subject}{particle(subject, '을/를')} 제외해 "
            f'{returned}건을 반환했습니다. 제외된 수만큼 추가 조회하지 않았습니다'
        )
    elif returned < limit and not truncated:
        notes.append(
            f'최대 {limit}건을 요청했지만 조회한 결과는 {returned}건입니다. '
            '요청한 조회 범위에서 검색을 마쳤습니다'
        )
    if truncated:
        return notes
    if limit >= MAX_LIST_LIMIT and (total > returned or inspected >= limit):
        notes.append(
            f'--limit의 최대값은 {MAX_LIST_LIMIT}입니다. 더 구체적인 결과를 보려면 '
            '거래 유형·가격·지역 등 지원되는 필터로 검색 범위를 좁혀 주세요'
        )
    elif returned >= limit and total > returned:
        notes.append(
            f'전체 집계 {total}건 중 {returned}건만 보여 줍니다. '
            '--limit을 늘리거나 지원되는 필터로 검색 범위를 좁혀 주세요'
        )
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


# real-price·market-price 의 --period
PERIOD_YEARS_BY_NAME: dict[str, int] = {'1년': 1, '3년': 3, '5년': 5}


def bounding_box(lat: float, lng: float, radius_km: float) -> NaverBoundingBoxModel:
    south, north, west, east = box_around(lat, lng, radius_km)
    return NaverBoundingBoxModel(left=west, right=east, top=north, bottom=south)
