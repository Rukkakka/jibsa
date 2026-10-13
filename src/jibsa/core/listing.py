import re
from collections.abc import Sequence
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from jibsa.core.geo import within_radius

from typing import (
    Annotated,
    Any,
    Literal,
    overload,
)


SQUARE_METERS_PER_PYEONG: float = 3.305785
KST: timezone = timezone(timedelta(hours=9), 'KST')
# 구분자가 없으면 8자리만 받는다. 월·일을 한 자리로도 받으면 연월('202411')이 2024-01-01 로 읽힌다
DATE_DIGITS_PATTERN: re.Pattern[str] = re.compile(r'^(\d{4})(?:(\d{2})(\d{2})|[-./](\d{1,2})[-./](\d{1,2}))\.?$')

# 거래 유형별로 원래 존재하지 않는 가격 필드. 출력에서 키째 뺀다.
NOT_APPLICABLE_PRICE_FIELDS: dict[str, frozenset[str]] = {
    '매매': frozenset({'deposit_manwon', 'rent_manwon'}),
    '전세': frozenset({'price_manwon', 'rent_manwon'}),
    '월세': frozenset({'price_manwon'}),
    '단기임대': frozenset({'price_manwon'}),
}

# 시·도 줄임말 → 정식 명칭. 직방·네이버는 '서울시'·'강원도'·'제주도' 처럼 줄이거나 옛 이름을 쓰고
# 당근은 정식 명칭을 써서, 합친 결과에서 같은 지역이 달라 보이지 않도록 정식 명칭으로 맞춘다.
SIDO_OFFICIAL_NAMES: dict[str, str] = {
    '서울': '서울특별시',
    '서울시': '서울특별시',
    '부산': '부산광역시',
    '부산시': '부산광역시',
    '대구': '대구광역시',
    '대구시': '대구광역시',
    '인천': '인천광역시',
    '인천시': '인천광역시',
    # 광주광역시·전라남도는 전남광주통합특별시로 합쳐졌다 (2026-10-10 실측: 당근·직방·네이버 모두 이 이름).
    # 주소 첫 단어만 보므로 경기도 광주시('경기도 광주시 …')와 섞이지 않는다.
    '광주': '전남광주통합특별시',
    '광주시': '전남광주통합특별시',
    '광주광역시': '전남광주통합특별시',
    # 네이버 자동완성·시·도 목록과 직방은 '전남광주시 광산구' 처럼 줄인다 (2026-10-11 네이버 실측)
    '전남광주': '전남광주통합특별시',
    '전남광주시': '전남광주통합특별시',
    '대전': '대전광역시',
    '대전시': '대전광역시',
    '울산': '울산광역시',
    '울산시': '울산광역시',
    '세종': '세종특별자치시',
    '세종시': '세종특별자치시',
    '경기': '경기도',
    '강원': '강원특별자치도',
    '강원도': '강원특별자치도',
    '충북': '충청북도',
    '충남': '충청남도',
    '전북': '전북특별자치도',
    # 네이버 시·도 목록의 이름 (legalDivisionName, 2026-10-11)
    '전북도': '전북특별자치도',
    '전라북도': '전북특별자치도',
    '전남': '전남광주통합특별시',
    '전라남도': '전남광주통합특별시',
    '경북': '경상북도',
    '경남': '경상남도',
    '제주': '제주특별자치도',
    '제주도': '제주특별자치도',
}

NOTICE: str = '매물 확인·사진·문의·계약은 각 url 의 원 사이트에서 하세요. jibsa 는 탐색용입니다.'

Source = Literal['naver', 'zigbang', 'daangn']
TradeType = Literal['매매', '전세', '월세', '단기임대']


def m2_to_pyeong(m2: float | None) -> float | None:
    if m2 is None:
        return None
    return round(m2 / SQUARE_METERS_PER_PYEONG, 1)


def won_to_manwon(won: float | int | str | None) -> float | None:
    """원 단위 값을 만원 단위로 바꾼다. 빈 값이나 숫자가 아닌 문자열은 None."""
    if won is None or won == '':
        return None
    try:
        return round(float(won) / 10_000, 1)
    except (TypeError, ValueError):
        return None


@overload
def normalize_address(address: str) -> str: ...
@overload
def normalize_address(address: None) -> None: ...
@overload
def normalize_address(address: str | None) -> str | None: ...
def normalize_address(address: str | None) -> str | None:
    """주소 첫 단어(시·도)를 정식 명칭으로 바꾼다 ('서울시 강남구' → '서울특별시 강남구').

    세종은 시·군·구가 없는데 소스가 '세종시 세종 반곡동'·'세종시 세종시 반곡동' 처럼 시를 한 번 더
    넣으므로 그 단어를 뺀다. 첫 단어가 이미 정식 명칭이어도 뺀다 (2026-10-10 실측: 직방 아파트 목록은
    '세종특별자치시 세종 반곡동', 2026-10-11 실측: 직방 상가 목록·상세는 local1·local2 가 둘 다
    '세종특별자치시'). 모르는 시·도거나 공백뿐이면 그대로 둔다.
    """
    words = address.split() if address else []
    if not words:
        return address
    first, *rest = words
    sido = SIDO_OFFICIAL_NAMES.get(first) or (first if first in SIDO_OFFICIAL_NAMES.values() else None)
    if sido is None:
        return address
    if sido == '세종특별자치시' and rest and rest[0] in ('세종', '세종시', '세종특별자치시'):
        rest = rest[1:]
    return ' '.join([sido, *rest])


def join_address(*parts: str | None) -> str | None:
    """주소 조각(시/구/동/번지)을 빈 값 없이 이어 붙인다."""
    address = ' '.join(part for part in parts if part)
    return address or None


def normalize_floor(floor: str | None) -> str | None:
    """숫자로 온 지하층을 직방 표기에 맞춘다 ('0.5' → '반지하', '-1' → '지하1').

    당근은 반지하를 0.5, 지하를 음수로, 네이버는 지하를 음수로 준다. 직방은 처음부터
    '반지하' 로 준다. 그 밖의 값('3', '저', '옥탑방' ...)은 그대로 둔다.
    """
    if floor is None:
        return None
    try:
        number = float(floor)
    except ValueError:
        return floor
    if number == 0.5:
        return '반지하'
    if number < 0 and number.is_integer():
        return f'지하{int(-number)}'
    return floor


def normalize_date(value: str | None) -> str | None:
    """날짜를 한국 날짜 기준 `YYYY-MM-DD` 로 맞춘다.

    `20100706`, `2018.04.27`, `1995-10-26 ` 같은 날짜와, 시각이 붙은 일시도 받는다.
    일시는 시각을 버리고 날짜만 남긴다 (네이버가 날짜만 주므로 소스끼리 맞춘다).
    시간대가 없으면 한국 시간으로 보고, UTC(`...Z`)는 한국 시간으로 바꾼 뒤 날짜를
    뽑는다 (UTC 15시 이후는 한국 날짜로 다음 날). 읽을 수 없으면 앞뒤 공백만 지운
    원래 값을 돌려준다 (정보를 버리지 않는다). 연월만 있는 값(`202411`, `2024.11`)도 그대로 둔다.
    """
    if value is None:
        return None
    text = value.strip()
    match = DATE_DIGITS_PATTERN.match(text)
    if match is not None:
        year, month, day = (int(part) for part in match.groups() if part is not None)
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return text
    try:
        moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return text or None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    return moment.astimezone(KST).date().isoformat()


def by_distance(listing: 'Listing') -> tuple[bool, float]:
    """가까운 순 정렬 키. 거리를 모르는 매물은 가장 가깝다고 내보내지 않도록 맨 뒤로 보낸다."""
    return listing.distance_km is None, listing.distance_km or 0


def limit_notes(
    total: int | None,
    returned: int,
    limit: int,
    *,
    order: str = '검색 중심에서 가까운',
    approximate: bool = False,
    basis: str = '',
    narrow: str = '거래 유형·매물 유형·가격 조건',
    radius: bool = False,
) -> list[str]:
    """조건에 맞는 매물이 `limit` 보다 많아 일부만 돌려줄 때의 안내.

    "역삼동" 처럼 넓게 찾으면 네이버만 4천 건이 넘는데, 몇십 건만 받은 LLM 이 그게 전부라고
    오해하지 않도록 알리고 조건이나 지역을 좁히게 한다.

    Args:
        total: 조건에 맞는 매물 수 (모르면 None).
        returned: 돌려준 매물 수.
        limit: 요청한 최대 결과 수.
        order: 돌려준 매물을 고른 기준 (예: '검색 중심에서 가까운', '최근 게시된').
        approximate: `total` 이 근사값이면 True ('약 N건').
        basis: `total` 이 어떤 조건까지 적용한 수인지 덧붙일 말 (예: '가격 조건 적용 전').
        narrow: 좁히라고 권할 조건. 그 명령에 있는 옵션만 적는다 (예: 상가 '업종·가격 조건').
        radius: 반경 검색이면 True. 역·좌표로 이미 좁게 찾았으니 역 이름 대신 `--radius` 를 줄이라고 권한다
            (동 경계·시군구 검색에 권하는 '역 이름처럼 더 좁은 지역' 을 강남역 검색에도 붙이던 문제).
    """
    if returned < limit:
        return []
    if total is None or total <= returned:
        return []
    lead = f"조건에 맞는 매물이 {'약 ' if approximate else ''}{total}건" + (f'({basis})' if basis else '') + '이라'
    area = '--radius 를 줄여' if radius else '역 이름처럼 더 좁은 지역으로'
    # 안내 문장은 끝에 마침표가 없어 다른 안내와 이어 붙일 수 있다
    return [
        f'{lead} {order} {returned}건만 보여 줍니다. '
        f'--limit 을 늘리거나, {narrow}을 좁히거나, {area} 다시 검색하세요'
    ]


def beyond_radius_notes(listings: Sequence['Listing'], radius_km: float, *, complete: bool = True) -> list[str]:
    """반경 안 매물이 모자라 반경 밖 매물까지 함께 돌려줄 때의 안내.

    반경 검색은 반경을 덮는 지도 칸 단위로 받아 오므로 반경 밖 매물도 받는다. 반경 안 매물이
    `limit` 보다 적으면 그 매물도 버리지 않고 가까운 순으로 이어 보여 준다 ("1km 안에는 없고
    가장 가까운 게 1.1km" 를 0건 대신 알 수 있게).

    Args:
        complete: 반경을 덮는 칸을 끝까지 받았는지. 조회 한도(`limit`·요청 상한)에 닿아 멈췄으면 False 로 주어
            "반경 안 매물이 N건뿐" 이라고 단정하지 않는다. 받지 않은 칸·페이지에 반경 안 매물이 더 있을 수 있다
            (네이버 강남역 반경 0.3km 120건: '116건뿐' 이라 했지만 목화밀라트만 9건이 더 있었다, 2026-10-10).
    """
    distances = [listing.distance_km for listing in listings if listing.distance_km is not None]
    beyond = [distance for distance in distances if not within_radius(distance, radius_km)]
    if not beyond:
        return []
    # 거리를 모르는 매물(distance_km=None)은 반경 안으로 세지 않는다
    inside = len(distances) - len(beyond)
    # 소수 한 자리로 깎으면 반경 0.1km 밖의 0.13km 가 '최대 0.1km' 로 보여 반경 안처럼 읽힌다
    farthest = f'{round(max(beyond), 2):g}km'
    if not complete:
        found = (
            f'받은 매물 중 반경 {radius_km:g}km 안 매물이 없어 반경 밖 가까운 매물 {len(beyond)}건(최대 {farthest})을'
            if inside == 0 else
            f'받은 매물 중 반경 {radius_km:g}km 안은 {inside}건이라 반경 밖 가까운 매물 {len(beyond)}건(최대 {farthest})도 함께'
        )
        return [f'{found} 보여 줍니다. 조회 한도에 닿아 멈췄으므로 반경 안 매물이 더 있을 수 있습니다']
    if inside == 0:
        return [
            f'반경 {radius_km:g}km 안에는 조건에 맞는 매물이 없어 '
            f'반경 밖 가까운 매물 {len(beyond)}건(최대 {farthest})을 보여 줍니다'
        ]
    return [
        f'반경 {radius_km:g}km 안에 조건에 맞는 매물이 {inside}건뿐이라 '
        f'반경 밖 가까운 매물 {len(beyond)}건(최대 {farthest})도 함께 보여 줍니다'
    ]


class Listing(BaseModel):
    """소스와 무관하게 정규화한 매물 한 건 (목록 결과).

    jibsa 는 탐색용이라 매물을 고르는 데 필요한 정보만 담고, 사진·연락처·
    본문처럼 원 사이트를 대신하게 되는 정보는 담지 않는다. 확인과
    문의는 `url` 의 원 사이트에서 한다.

    소스마다 가격 단위가 다르므로(네이버: 원, 직방·당근: 만원) 모든 금액은
    **만원** 으로 통일한다. LLM 이 단위를 혼동하지 않도록 필드명에 단위를 붙인다.

    출력에서 값이 없는 필드는 의미에 따라 다르게 나타낸다.

    - 해당 없음 (그 거래 유형에 원래 없는 항목, 예: 월세의 `price_manwon`): 키를 뺀다
    - 모름 (해당은 되지만 소스가 알려 주지 않은 항목): `null`

    Args:
        source: 매물을 가져온 소스.
        id: 소스 안에서의 매물 ID. 상세 명령에 그대로 넘긴다.
        url: 원 사이트 매물 페이지 URL.
        trade_type: 거래 유형.
        property_type: 매물 유형 (원룸, 오피스텔, 빌라, 아파트 ...).
        room_type: 방 구조 (오픈형원룸 ... 포룸이상). 소스가 알려줄 때만.
            Defaults to None.
        title: 매물 한 줄 제목. Defaults to None.
        price_manwon: 매매가(만원). Defaults to None.
        deposit_manwon: 보증금 또는 전세금(만원). Defaults to None.
        rent_manwon: 월세(만원). Defaults to None.
        manage_cost_manwon: 월 관리비(만원). Defaults to None.
        area_m2: 전용면적(㎡). Defaults to None.
        area_pyeong: 전용면적(평). Defaults to None.
        floor: 해당 층 (예 '3', '반지하', '지하1', '옥탑'). 숫자로 온 지하층은
            `normalize_floor` 로 맞춘다. Defaults to None.
        building_floor: 건물 전체 층수. Defaults to None.
        address: 지번 주소. 소스가 번지를 주면 번지까지, 아니면 동까지. 시·도는 정식
            명칭으로 맞춘다 (`normalize_address`). Defaults to None.
        lat: 위도. 거리 계산용이며 출력하지 않는다. Defaults to None.
        lng: 경도. 거리 계산용이며 출력하지 않는다. Defaults to None.
        distance_km: 검색 중심점에서의 거리(km). Defaults to None.
        registered_at: 등록·노출 시작일 (YYYY-MM-DD). Defaults to None.
        approved_at: 사용승인일 (YYYY-MM-DD). 목록에서는 네이버만 준다.
            Defaults to None.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    source: Annotated[
        Source,
        Field(description='매물을 가져온 소스')
    ]
    id: Annotated[
        str,
        Field(description='소스 안에서의 매물 ID. 상세 명령에 그대로 넘긴다')
    ]
    url: Annotated[
        str,
        Field(description='원 사이트 매물 페이지 URL. 확인·문의·계약은 여기서')
    ]
    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형')
    ]
    property_type: Annotated[
        str,
        Field(description='매물 유형 (원룸, 오피스텔, 빌라, 아파트 ...)')
    ]
    room_type: Annotated[
        str | None,
        Field(description='방 구조 (오픈형원룸, 분리형원룸, 복층형원룸, 투룸, 쓰리룸, 포룸이상). 소스가 알려줄 때만. 당근 투룸 이상은 목록에 방 수가 없어 null')
    ] = None
    title: Annotated[
        str | None,
        Field(description='매물 한 줄 제목')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 또는 전세금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='월 관리비 (만원)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="해당 층 (예 '3', '반지하', '지하1', '옥탑')")
    ] = None
    building_floor: Annotated[
        str | None,
        Field(description='건물 전체 층수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소 (소스가 주면 번지까지, 아니면 동까지)')
    ] = None
    lat: Annotated[
        float | None,
        Field(exclude=True, description='위도. 거리 계산용, 출력 안 함')
    ] = None
    lng: Annotated[
        float | None,
        Field(exclude=True, description='경도. 거리 계산용, 출력 안 함')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='검색 중심점에서의 거리 (km)')
    ] = None
    registered_at: Annotated[
        str | None,
        Field(description='등록·노출 시작일 (YYYY-MM-DD, 한국 날짜)')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None

    @field_validator('address')
    @classmethod
    def official_sido_name(cls, value: str | None) -> str | None:
        return normalize_address(value)

    @field_validator('floor')
    @classmethod
    def unified_floor_label(cls, value: str | None) -> str | None:
        return normalize_floor(value)

    def not_applicable_fields(self) -> frozenset[str]:
        """이 매물에 원래 존재하지 않는 필드. 출력에서 키째 뺀다.

        거래 유형에 없는 가격 필드와, 검색 중심점 없이 조회해 거리가 없는
        경우(단지 매물 목록 등)의 `distance_km` 이다.
        """
        fields = NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset())
        if self.distance_km is None:
            fields = fields | {'distance_km'}
        return fields

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.not_applicable_fields():
            data.pop(field, None)
        return data


class ListingDetail(Listing):
    """상세 조회로 보강한 매물. 매물을 고르는 데 필요한 사실만 더한다.

    사진, 본문, 중개사 연락처, 도로명 주소, 조회수는 담지 않는다.

    `move_in`·`parking`·`nearby_subways` 는 중개사·작성자가 입력한 문구를 소스 표기대로
    옮긴 값이라 소스마다 형식이 다르다 ('주차 불가능' / '불가', '2026.10.28 이후 입주 가능' /
    '2026-10-07'). 사람이 쓴 문장이라 한 형식으로 바꿀 수 없어 정규화하지 않는다.

    Args:
        room_count: 방 수. Defaults to None.
        bathroom_count: 욕실 수. Defaults to None.
        direction: 방향. Defaults to None.
        move_in: 입주 가능일. Defaults to None.
        parking: 주차 가능 여부·대수. Defaults to None.
        elevator: 엘리베이터 유무. Defaults to None.
        options: 옵션·시설. 소스가 주지 않으면 None, 줬는데 없으면 []. Defaults to None.
        manage_cost_includes: 관리비 포함 항목. Defaults to None.
        nearby_subways: 인근 지하철역. Defaults to None.
    """

    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='방향')
    ] = None
    move_in: Annotated[
        str | None,
        Field(description='입주 가능일. 소스 표기 그대로라 형식이 소스마다 다르다')
    ] = None
    parking: Annotated[
        str | None,
        Field(description='주차 가능 여부·대수. 소스 표기 그대로라 형식이 소스마다 다르다')
    ] = None
    elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 유무')
    ] = None
    options: Annotated[
        list[str] | None,
        Field(description='옵션·시설 (에어컨, 세탁기 ...). 소스가 알려 주지 않으면 null')
    ] = None
    manage_cost_includes: Annotated[
        list[str] | None,
        Field(description='관리비 포함 항목. 소스가 알려 주지 않으면 null')
    ] = None
    nearby_subways: Annotated[
        list[str] | None,
        Field(description='인근 지하철역. 소스가 알려 주지 않으면 null. 직방은 노선, 당근은 도보 시간을 붙인다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 상세 조회에는 검색 중심점이 없어 거리가 해당 없다.
        return super().not_applicable_fields() | {'distance_km'}
