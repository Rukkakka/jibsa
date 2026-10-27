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
    TypeVar,
    get_args,
    overload,
)


SQUARE_METERS_PER_PYEONG: float = 3.305785
KST: timezone = timezone(timedelta(hours=9), 'KST')
# 구분자가 없으면 8자리만 받는다. 월·일을 한 자리로도 받으면 연월('202411')이 2024-01-01 로 읽힌다.
# '년 월 일' 은 직방 사용승인일에 섞여 온다 ('1984년 10월 26일', '일' 이 빠진 '2011년 7월 1', 2026-10-15 실측)
DATE_DIGITS_PATTERN: re.Pattern[str] = re.compile(
    r'^(\d{4})(?:(\d{2})(\d{2})|[-./](\d{1,2})[-./](\d{1,2})|년\s*(\d{1,2})월\s*(\d{1,2})일?)\.?$'
)
# 입주 가능일 문구 끝의 괄호 설명 ('2026.10.15 이후 입주 가능 (입주협의)')
MOVE_IN_PAREN_PATTERN: re.Pattern[str] = re.compile(r'^(.*?)\s*\(([^()]*)\)$')
ISO_DATE_PATTERN: re.Pattern[str] = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MOVE_IN_NOW: str = '즉시입주'
# 네이버 매물의 지하층 표기 ('B1' = 지하 1층)
BASEMENT_FLOOR_PATTERN: re.Pattern[str] = re.compile(r'^B(\d+)$')
RELATIVE_FLOOR_LABELS: dict[str, str] = {'저': '저층', '중': '중층', '고': '고층'}

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

Source = Literal['naver', 'zigbang', 'daangn', 'dabang']
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
    """숫자·B 로 온 지하층을 직방 표기에 맞추고 ('0.5' → '반지하', '-1'·'B1' → '지하1'), 저·중·고를 저층·중층·고층으로 맞춘다.

    당근은 반지하를 0.5, 지하를 음수로, 네이버는 지하를 음수나 'B1' 로 준다. 직방은 처음부터
    '반지하' 로 준다. 층을 숫자 대신 밝힌 매물은 직방·네이버가 '저'·'중'·'고', 당근이 '저층'·'중층'·'고층' 으로 준다
    (2026-10-20 실측: 강남역·역삼동 목록). 그 밖의 값('3', '옥탑방' ...)은 그대로 둔다.
    """
    if floor is None:
        return None
    if floor in RELATIVE_FLOOR_LABELS:
        return RELATIVE_FLOOR_LABELS[floor]
    basement = BASEMENT_FLOOR_PATTERN.match(floor)
    if basement is not None:
        return f'지하{int(basement.group(1))}'
    try:
        number = float(floor)
    except ValueError:
        return floor
    if number == 0.5:
        return '반지하'
    if number < 0 and number.is_integer():
        return f'지하{int(-number)}'
    return floor


def floor_number(floor: str | None) -> int | None:
    """정규화한 층(`normalize_floor`)의 숫자. 지상은 양수, 지하는 음수다 ('3' → 3, '지하1' → -1).

    반지하·저층·옥탑처럼 몇 층인지 모르는 표기는 None (모름)이다. 층으로 거르거나 정렬할 때 쓴다.
    """
    if floor is None:
        return None
    # isdigit 은 int() 가 못 읽는 위첨자('²')도 받아 직렬화 중에 ValueError 가 난다. isdecimal 은 int() 가 읽는 숫자만 받는다
    if floor.isdecimal():
        return int(floor)
    if floor.startswith('지하') and floor[2:].isdecimal():
        return -int(floor[2:])
    return None


def insert_after(data: dict[str, Any], anchor: str, key: str, value: Any) -> dict[str, Any]:
    """`anchor` 키 바로 뒤에 `key` 를 넣은 새 dict. `anchor` 가 없으면 맨 뒤에 넣는다 (출력 JSON 의 키 순서를 맞출 때)."""
    if anchor not in data:
        return {**data, key: value}
    result: dict[str, Any] = {}
    for name, item in data.items():
        result[name] = item
        if name == anchor:
            result[key] = value
    return result


def normalize_date(value: str | None) -> str | None:
    """날짜를 한국 날짜 기준 `YYYY-MM-DD` 로 맞춘다.

    `20100706`, `2018.04.27`, `1995-10-26 `, `1991년 6월 5일` 같은 날짜와, 시각이 붙은 일시도 받는다.
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


def move_in_label(value: str | None, *, negotiable: bool = False) -> str | None:
    """입주 가능일을 세 소스가 같은 꼴로 쓴다: 날짜는 `YYYY-MM-DD`, 날짜 없이 바로면 `즉시입주`, 협의 가능하면
    뒤에 ` (협의 가능)`.

    직방 옛 상세 API 의 문장('즉시 입주 가능 (협의 가능)', '2026.10.15 이후 입주 가능 (입주협의)')도 받는다. 괄호 안이
    협의·즉시입주가 아닌 다른 설명이면 뒤에 그대로 붙이고, 날짜를 읽지 못하면 원래 문구를 그대로 둔다 (정보를 버리지 않는다).
    """
    if value is None or not value.strip():
        return None
    text = value.strip()
    match = MOVE_IN_PAREN_PATTERN.match(text)
    head, extra = (match.group(1).strip(), match.group(2).strip()) if match else (text, '')
    if '협의' in extra:
        negotiable, extra = True, ''
    elif extra.replace(' ', '') == MOVE_IN_NOW:
        extra = ''
    head = head.replace('이후 입주 가능', '').strip()
    if '즉시' in head:
        label = MOVE_IN_NOW
    else:
        date = normalize_date(head)
        if date is None or not ISO_DATE_PATTERN.match(date):
            return text
        label = date
    if extra:
        label += f' ({extra})'
    return label + (' (협의 가능)' if negotiable else '')


def parking_label(available: bool | None, detail: str | None = None) -> str | None:
    """주차를 세 소스가 같은 꼴로 쓴다: `가능`·`불가`, 대수가 있으면 괄호로 붙인다 (`가능 (총 4대)`). 가능 여부를 모르면 대수만."""
    status = None if available is None else '가능' if available else '불가'
    if status and detail:
        return f'{status} ({detail})'
    return status or detail


def in_range(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    """범위 조건에 맞는지. 조건이 있는데 값을 모르면 맞지 않는다고 본다 (서버가 받지 않아 받은 뒤 거르는 조건에 쓴다).

    직방(면적·공급면적·상가 조건)과 당근(필터 API 대체 조회의 가격·면적)이 같은 규칙으로 거르게 한 곳에 둔다.
    """
    if minimum is None and maximum is None:
        return True
    return value is not None and (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


# 결과 notes 의 종류. 안내 앞에 '[일부] ' 처럼 붙여 LLM 이 문장을 다 읽지 않고도 무엇을 알리는지 가른다 (docs/llm.md).
# 일부: 더 받을 매물이 있다 / 범위: 찾은 범위가 요청과 다르다 / 제외: 받은 것 중 뺀 매물이 있다 / 모호: 이름이 여러 곳이라
# 하나를 골랐다 / 거래: 거래 유형을 짐작해 좁혔다 / 실패: 덤 조회가 실패했거나 대체 경로로 찾았다 / 참고: 그 밖에 읽을 때 알 것
NoteKind = Literal['일부', '범위', '제외', '모호', '거래', '실패', '참고']
NOTE_KINDS: tuple[str, ...] = get_args(NoteKind)
# 결과는 냈지만 소스가 바뀌어 jibsa 를 고쳐야 한다는 `notes` 끝말. 매일 API 감시(scripts/monitor/api_check.py)가 이 말로
# 고장을 찾으니 손으로 쓰지 않고 이 상수를 쓴다. 차단 페이지일 수도 있는 형식 오류·GraphQL 에러(당근)나 읽지 못한 글자(다방)처럼
# 단정하지 못하면 MAYBE 를 쓰고, 감시는 주된 조회의 PARSE_ERROR·상태 없는 UPSTREAM_ERROR 처럼 둘 다 고장으로 센다
UPDATE_NEEDED: str = 'jibsa 업데이트가 필요합니다'
UPDATE_MAYBE_NEEDED: str = 'jibsa 업데이트가 필요할 수 있습니다'


def note(kind: NoteKind, text: str) -> str:
    """종류 태그를 붙인 안내 (`'[일부] 조건에 맞는 매물 ...'`). 태그 없이 둔 안내는 출력할 때 [참고] 가 붙는다 (`tagged_notes`)."""
    return f'[{kind}] {text}'


def tagged_notes(notes: list[str]) -> list[str]:
    """출력할 안내마다 종류 태그를 붙인다. 이미 붙었으면 그대로, 없으면 [참고]. 같은 안내는 한 번만 남긴다."""
    tagged = [
        text if any(text.startswith(f'[{kind}] ') for kind in NOTE_KINDS) else note('참고', text)
        for text in notes
    ]
    return list(dict.fromkeys(tagged))


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
    narrow: str = '조건',
    radius: bool = False,
    inspected: int | None = None,
    offset: int = 0,
    resumable: bool = False,
    has_more: bool | None = None,
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
        radius: 반경 검색이면 True. 역·좌표로 이미 좁게 찾았으니 지역 대신 반경을 좁히라고 권한다
            (동 경계·시군구 검색에 권하는 '더 좁은 지역' 을 강남역 검색에도 붙이던 문제).
        inspected: 요약을 받아 확인한 매물 수 (조회 예산). 주면 `returned` 대신 이 값으로 `limit` 에 닿았는지 본다.
            받은 뒤 거래 불가로 뺀 매물만큼 다시 채우지 않으므로, 1건만 빠져도 `returned < limit` 이 되어 안내가
            사라지던 문제를 막는다 (직방 역삼동 원룸 --limit 15 에서 1건이 빠지면 '약 660건' 안내가 없었다).
        offset: 이어 받은 검색(`--next`)에서 앞서 받은 매물 수. 몇 번째부터인지 알린다.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        has_more: 결과의 `has_more`. False 면 안내하지 않는다. `total` 은 거래 불가로 빼기 전 수라 `returned` 와 견주면, 범위 안
            매물을 다 받고 1건만 빠져도 '더 보려면 --limit 을 늘리라' 고 했다 (직방 동 경계 안 15건을 --limit 15 로 다 받고 1건이
            빠진 경우, 2026-10-23 리뷰).
    """
    if (returned if inspected is None else inspected) < limit or has_more is False:
        return []
    if total is None or total <= offset + returned:
        return []
    lead = f"조건에 맞는 매물 {'약 ' if approximate else ''}{total}건" + (f'({basis})' if basis else '')
    picked = f'{order} {offset + 1}번째부터 {returned}건' if offset else f'{order} {returned}건'
    area = '반경' if radius else '지역'
    # 안내 문장은 끝에 마침표가 없어 다른 안내와 이어 붙일 수 있다
    if resumable:
        return [note('일부', f'{lead} 중 {picked}입니다. 이어 보려면 결과의 next 를 --next 로 주세요')]
    return [note('일부', f'{lead} 중 {picked}입니다. 더 보려면 --limit 을 늘리거나 {narrow}·{area}을 좁히세요')]


def beyond_radius_notes(
    listings: Sequence['Listing'], radius_km: float, *, complete: bool = True, resumed: bool = False,
) -> list[str]:
    """반경 안 매물이 모자라 반경 밖 매물까지 함께 돌려줄 때의 안내.

    반경 검색은 반경을 덮는 지도 칸 단위로 받아 오므로 반경 밖 매물도 받는다. 반경 안 매물이
    `limit` 보다 적으면 그 매물도 버리지 않고 가까운 순으로 이어 보여 준다 ("1km 안에는 없고
    가장 가까운 게 1.1km" 를 0건 대신 알 수 있게).

    Args:
        complete: 반경을 덮는 칸을 끝까지 받았는지. 조회 한도(`limit`·요청 상한)에 닿아 멈췄으면 False 로 주어
            "반경 안 매물이 N건뿐" 이라고 단정하지 않는다. 받지 않은 칸·페이지에 반경 안 매물이 더 있을 수 있다
            (네이버 강남역 반경 0.3km 120건: '116건뿐' 이라 했지만 목화밀라트만 9건이 더 있었다, 2026-10-10).
        resumed: 이어 받기(`--next`)로 받은 결과면 True. 반경 안 매물 수는 이번 결과만 센 것이라 '남은' 매물이라 한다
            (앞 결과에서 받은 반경 안 매물은 세지 않는다).
    """
    distances = [listing.distance_km for listing in listings if listing.distance_km is not None]
    beyond = [distance for distance in distances if not within_radius(distance, radius_km)]
    if not beyond:
        return []
    # 거리를 모르는 매물(distance_km=None)은 반경 안으로 세지 않는다
    inside = len(distances) - len(beyond)
    # 소수 한 자리로 깎으면 반경 0.1km 밖의 0.13km 가 '최대 0.1km' 로 보여 반경 안처럼 읽힌다
    farthest = f'{round(max(beyond), 2):g}km'
    # 반경을 덮는 범위(네이버·당근 사각형, 직방 지도 칸)에서 받은 것이라 모서리 쪽만 들어온다. '가까운 매물' 이라 하면 반경 밖을
    # 빠짐없이 가까운 순으로 고른 줄 안다 (2026-10-20 LLM 사용 시험: 네이버 1km 에 1.43km 모서리 매물은 있고 정북쪽 1.26km 는 없었다)
    found = f'반경을 덮어 받은 범위의 반경 밖 매물 {len(beyond)}건(최대 {farthest})'
    partial = '반경 밖은 받은 범위의 일부라 더 보려면 --radius 를 늘리세요'
    if not complete:
        head = (
            f'받은 매물 중 반경 {radius_km:g}km 안 매물이 없어 {found}을'
            if inside == 0 else
            f'받은 매물 중 반경 {radius_km:g}km 안은 {inside}건이라 {found}도 함께'
        )
        return [note('범위', f'{head} 보여 줍니다. 조회 한도에 닿아 멈췄으므로 반경 안 매물이 더 있을 수 있습니다')]
    remaining = '남은 매물 중 ' if resumed else ''
    if inside == 0:
        return [note(
            '범위', f'{remaining}반경 {radius_km:g}km 안에는 조건에 맞는 매물이 없어 {found}을 보여 줍니다. {partial}',
        )]
    return [note(
        '범위', f'{remaining}반경 {radius_km:g}km 안에 조건에 맞는 매물이 {inside}건뿐이라 {found}도 함께 보여 줍니다. {partial}',
    )]


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

    목록에서 소스가 늘 주지 않는 필드(직방·당근 `approved_at`, 당근 `manage_cost_manwon`·`registered_at`, 네이버
    `room_type`)도 키를 빼지 않고 `null` 이다. 키를 빼면 해당 없음으로 읽혀 관리비 없는 매물로 셈한다 (`null` 이면 상세를
    보라고 docs/llm.md 가 이른다). 결과 전체가 같은 값인 `source`·`trade_type` 도 소스를 섞어 비교할 때 매물 하나만 보고
    읽도록 남긴다. 출력을 줄이는 길은 `--fields` 다 (2026-10-23 실측: 직방 room 30건 14,424자 → docs/llm.md 권장 9필드
    7,540자, 48% 감소. 당근 목록에서 늘 null 인 세 필드는 매물 출력의 15%).

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
        Field(description="해당 층 (예 '3', '반지하', '지하1', '옥탑', '중층'). 출력에는 숫자 floor_number 가 뒤에 붙는다")
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
        # 층이 '3'·'지하1'·'중층' 처럼 섞여 와 층으로 거르거나 정렬하기 어려워 숫자를 floor 바로 뒤에 붙인다
        return insert_after(data, 'floor', 'floor_number', floor_number(self.floor))


class ListingDetail(Listing):
    """상세 조회로 보강한 매물. 매물을 고르는 데 필요한 사실만 더한다.

    사진, 본문, 중개사 연락처, 도로명 주소, 조회수는 담지 않는다.

    `move_in`·`parking` 은 세 소스가 같은 꼴이다 (`move_in_label`·`parking_label`: '2026-10-24', '즉시입주',
    '2026-11 초순', 뒤에 ' (협의 가능)' / '가능', '불가', '가능 (총 4대)'). `nearby_subways` 는 소스 표기대로라
    괄호 안 내용이 소스마다 다르다 (노선 / 도보 분).

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
        Field(description="입주 가능일 ('2026-10-24', '즉시입주', '2026-11 초순', 협의 가능하면 뒤에 ' (협의 가능)')")
    ] = None
    parking: Annotated[
        str | None,
        Field(description="주차 ('가능', '불가', 대수가 있으면 '가능 (총 4대)'. 가능 여부를 모르면 대수만)")
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


def listing_field_names() -> frozenset[str]:
    """출력에 나올 수 있는 매물 필드 이름 (`Listing` 과 소스별 하위 모델·상세, `floor_number`). `--fields` 를 검증한다.

    하위 모델은 소스 모듈을 불러온 뒤에야 보이므로 명령을 모두 등록한 뒤(옵션을 읽을 때) 부른다.
    """
    names = {'floor_number'}
    models: list[type[Listing]] = [Listing]
    while models:
        model = models.pop()
        names.update(name for name, field in model.model_fields.items() if not field.exclude)
        models.extend(model.__subclasses__())
    return frozenset(names)


ListingT = TypeVar('ListingT', bound=Listing)


def listing_as(model: type[ListingT], listing: Listing, **extra: Any) -> ListingT:
    """`listing` 을 필드를 더한 하위 모델(역 도보 시간·통근 시간·순위·상세·건물 용도)로 옮긴다.

    `model_dump()` 는 출력에서 빼는 필드(`lat`·`lng` 처럼 `exclude=True`)를 버리므로 쓰지 않고 필드 값을 그대로 옮긴다.
    """
    return model(**{name: getattr(listing, name) for name in type(listing).model_fields}, **extra)
