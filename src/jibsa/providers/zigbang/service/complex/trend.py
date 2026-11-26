"""아파트 단지 직방시세 추이 (price-trend): 단지 화면 '직방시세' 그래프(단지·비교 단지·구)와 평형 그래프(월별 시세·거래)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.korean import particle
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    AmountRange,
    AmountSet,
    Result,
    lookup_failure_note,
    note,
    null_items_note,
    read_date,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.complex.base import (
    ZigbangDanjisRoomTypesRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.complex.trend import (
    ZigbangDanjisPriceChartRelatedDanjisRequestParameterModel,
    ZigbangDanjisPriceChartRequestParameterModel,
    ZigbangDanjisRoomTypesPriceChartRequestParameterModel,
    ZigbangPriceChartDealType,
    ZigbangPriceChartPeriod,
)
from jibsa.providers.zigbang.api.response.complex.base import (
    ZigbangDanjisRoomTypesResponseModel,
)
from jibsa.providers.zigbang.api.response.complex.trend import (
    ZigbangDanjiPriceChartLineModel,
    ZigbangDanjisPriceChartRelatedDanjisResponseModel,
    ZigbangRoomTypePriceMonthModel,
)
from jibsa.providers.zigbang.service.common.base import (
    OPTIONAL_LOOKUP_ERRORS,
    UNEXPECTED_FORMAT_TEXT,
    UPSTREAM_RETRY_HINT,
    apt_complex_id,
    parse_complex_id,
    sale_price_range,
    text_or_none,
)
from jibsa.providers.zigbang.service.complex.base import (
    ZigbangRelatedComplex,
    related_complex_of,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


ZigbangPriceTrendPeriod = Literal['1년', '3년', '전체']
ZigbangPyeongTrendTrade = Literal['전체', '매매', '전월세']
# 웹 기간 탭 이름 (번들 `convertDueNameForZams`: 최근1년·최근3년·전체기간, 기본은 두 번째인 최근3년)을 jibsa 는 1년·3년·전체 로 쓴다 → 요청의 period
PRICE_TREND_PERIODS: tuple[ZigbangPriceTrendPeriod, ...] = ('1년', '3년', '전체')
DEFAULT_PRICE_TREND_PERIOD: ZigbangPriceTrendPeriod = '3년'
CHART_PERIOD_BY_LABEL: dict[ZigbangPriceTrendPeriod, ZigbangPriceChartPeriod] = {
    '1년': '1y',
    '3년': '3y',
    '전체': 'all',
}
# 웹 평형 그래프의 거래 탭 이름 (번들 `convertStatusForZams`) → 요청의 dealType
PYEONG_TREND_TRADES: tuple[ZigbangPyeongTrendTrade, ...] = ('전체', '매매', '전월세')
DEFAULT_PYEONG_TREND_TRADE: ZigbangPyeongTrendTrade = '전체'
DEAL_TYPE_BY_TRADE: dict[ZigbangPyeongTrendTrade, ZigbangPriceChartDealType] = {
    '전체': 'all',
    '매매': 'sales',
    '전월세': 'rent',
}
# 웹은 비교 단지를 하나만 고르게 하고 서버는 셋까지 실측했다 (2026-11-22 표본: 단지·비교 셋·구 다섯 줄)
MAX_COMPARE_DANJIS: int = 3
# 비교 후보 안내(hint)에 적는 후보 수. 후보는 보통 세 곳 안팎이다 (2026-11-19 캡처: 헬리오시티 3곳)
MAX_CANDIDATES_IN_HINT: int = 10
ZigbangPriceLineKind = Literal['단지', '비교 단지', '구']


class ZigbangComplexPricePoint(BaseModel):
    """직방시세 추이의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 직방이 날짜를 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    estimated_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 매매 직방시세 평당가 (만원/3.3㎡). 직방이 0 을 준 달은 시세가 없는 달이라 null (점은 남는다)')
    ]


class ZigbangComplexPriceLine(BaseModel):
    """직방시세 추이의 줄 하나 (조회 단지, 비교 단지, 그 구). 직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='줄 이름 (직방이 준 label: 단지 이름 또는 구 이름)')
    ]
    kind: Annotated[
        ZigbangPriceLineKind | None,
        Field(
            description=(
                "줄 종류. 이름이 --compare 로 준 단지의 이름이면 '비교 단지', 마지막 줄이면 '구', 남은 줄이면 '단지'(조회 단지). "
                '직방이 줄 순서를 단지 ID 순으로 줘서 위치로는 알 수 없다. 직방시세가 없는 단지는 조회 단지 줄 없이 (비교 단지와) 구 줄만 와서 '
                "그때도 마지막 줄이 '구' 다. 이름이 겹치거나 줄 수가 (조회 단지 + 비교 단지 + 구)·(비교 단지 + 구) 와 다르거나 "
                '빈 줄을 뺐으면 판정하지 않고 null'
            )
        )
    ]
    complex_id: Annotated[
        str | None,
        Field(description="비교 단지의 단지 ID (kind 가 '비교 단지' 인 줄에만 있고 그 밖은 키가 없다)")
    ] = None
    months: Annotated[
        list[ZigbangComplexPricePoint] | None,
        Field(description='월별 매매 직방시세 평당가 (오래된 달부터). 직방이 월 목록을 주지 않으면 null')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.kind != '비교 단지':
            data.pop('complex_id', None)
        return data


class ZigbangPriceTrendResult(Result):
    """단지 직방시세 추이 (웹 단지 화면 직방시세 그래프 '3.3㎡ 당 평균가격', 기간 탭·단지 비교).

    `notes`: 비교 후보를 받지 못했다는 [실패] 안내, 시세 추이가 없다·줄 목록을 주지 않았다·구 줄만 있다는 [참고] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 아파트 단지 ID')
    ]
    period: Annotated[
        ZigbangPriceTrendPeriod,
        Field(description='기간 (--period 값: 1년·3년·전체)')
    ]
    comparable_complexes: Annotated[
        list[ZigbangRelatedComplex] | None,
        Field(
            description=(
                "웹 '단지 비교하기' 의 '단지 선택' 창 후보 (같이 많이 본 단지, 직방이 준 순서). --compare 에는 이 목록의 단지만 받는다. "
                '후보가 없으면 [], 직방이 주지 않았거나 받지 못하면 모름(null)'
            )
        )
    ]
    lines: Annotated[
        list[ZigbangComplexPriceLine] | None,
        Field(
            description=(
                '직방시세 그래프의 줄 (직방 응답 순서 그대로). 값은 매매 직방시세(직방이 실거래를 분석한 추정값)의 평당가이고 실거래가가 아니다. '
                '직방은 줄을 단지 ID 오름차순으로 주고 구를 끝에 붙여, 첫 줄이 조회 단지가 아닐 수 있다 (줄 종류는 kind). '
                '직방이 줄 목록을 주지 않으면 null (줄 목록 null 의 [참고] 안내), 줄이 없으면 []. '
                '직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다 (구 줄만 있다는 [참고] 안내)'
            )
        )
    ]


class ZigbangPyeongSale(BaseModel):
    """평형 하나의 한 달 매매 시세·거래. 금액은 만원이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    estimated_price_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 매매 직방시세 (직방이 실거래를 분석한 추정값). 직방이 0 을 준 달(입주 전 등)은 시세가 없어 null')
    ]
    trade_range: Annotated[
        AmountRange | None,
        Field(description='그 달 매매 거래의 가격 범위 (lowest 최저가·highest 최고가, price_manwon). 시세가 없는 달과, 거래가 0건인 달(직방이 시세 값을 대신 채워 준다)은 null')
    ]
    trade_count: Annotated[
        int | None,
        Field(description='그 달 매매 거래 건수 (0 도 진짜 값)')
    ]
    estimated_price_change_manwon: Annotated[
        int | float | None,
        Field(description='전달 대비 직방시세 변화. 시세가 없는 달은 null (변화가 없으면 0)')
    ]


class ZigbangPyeongJeonseWolse(BaseModel):
    """평형 하나의 한 달 전월세 시세·거래. 금액은 만원이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    estimated_deposit_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 전세 직방시세 (직방이 실거래를 분석한 추정값). 직방이 0 을 준 달은 시세가 없어 null')
    ]
    trade_range: Annotated[
        AmountRange | None,
        Field(
            description=(
                '그 달 전세·월세 거래를 합친 가격 범위 (lowest 최저가·highest 최고가, 둘 다 converted_price_manwon 하나뿐). 월세는 직방이 '
                '보증금 + 월세 × 300 으로 환산한 값이고 (2026-11-22 실측) 보증금이 아니다. 시세가 없는 달과, 거래가 0건인 달은 null'
            )
        )
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="그 달 거래 건수. 늘 'jeonse'·'wolse' 두 키이고 값은 건수 (0 도 진짜 값, 직방이 주지 않으면 null)")
    ]
    estimated_deposit_change_manwon: Annotated[
        int | float | None,
        Field(description='전달 대비 전세 직방시세 변화. 시세가 없는 달은 null (변화가 없으면 0)')
    ]


class ZigbangPyeongPriceMonth(BaseModel):
    """평형 시세 추이의 한 달. 고르지 않은 거래 탭의 키는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade: Annotated[
        ZigbangPyeongTrendTrade,
        Field(exclude=True, description='고른 거래 탭. 해당 없는 탭의 키를 빼는 데 쓰고 출력하지 않는다')
    ]
    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 직방이 날짜를 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    sale: Annotated[
        ZigbangPyeongSale | None,
        Field(description='매매 시세·거래. 직방이 그 달의 매매 기록을 주지 않았으면 null. --trade 전월세 에는 키가 없다')
    ]
    jeonse_wolse: Annotated[
        ZigbangPyeongJeonseWolse | None,
        Field(description='전월세 시세·거래. 직방이 그 달의 전월세 기록을 주지 않았으면 null. --trade 매매 에는 키가 없다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.trade == '매매':
            data.pop('jeonse_wolse', None)
        elif self.trade == '전월세':
            data.pop('sale', None)
        return data


class ZigbangPyeongPriceTrendResult(Result):
    """평형 하나의 월별 시세·거래 추이 (웹 단지 화면 평형 탭의 직방시세 그래프, 전체·매매·전월세 탭). 거래 점과 전세가율은 내지 않는다.

    `notes`: 평형 시세 기록이 없다는 [참고] 안내, 월 목록을 주지 않았다는 [참고] 안내, 빈 항목을 뺐다는 [제외] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 아파트 단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 ID (complex 결과의 pyeongs[].pyeong_id)')
    ]
    period: Annotated[
        ZigbangPriceTrendPeriod,
        Field(description='기간 (--period 값: 1년·3년·전체)')
    ]
    trade_tab: Annotated[
        ZigbangPyeongTrendTrade,
        Field(description='거래 탭 (--trade 값: 전체·매매·전월세)')
    ]
    months: Annotated[
        list[ZigbangPyeongPriceMonth] | None,
        Field(description='월별 시세·거래 (오래된 달부터). 매매·전월세 기록을 월로 맞춘 목록이고 기록이 없으면 [], 직방이 월 목록을 주지 않았으면 null')
    ]


class _LineKind(NamedTuple):
    """줄 하나의 종류 판정 결과."""

    kind: ZigbangPriceLineKind | None
    complex_id: str | None


class _Candidate(NamedTuple):
    """직방 비교 후보 단지 하나 (ID 가 있는 후보만)."""

    number: int
    name: str | None


def _apt_number(complex_id: str) -> int:
    """아파트 단지 ID 의 번호. 오피스텔 건물은 시세 추이가 없어 INVALID_ARGUMENT 다.

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나 (INVALID_ARGUMENT) 오피스텔일 때 (INVALID_ARGUMENT).
    """
    kind, number = parse_complex_id(complex_id)
    if kind != 'apt':
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"아파트 단지만 시세 추이가 있습니다: '{complex_id}'",
            hint=f'jibsa zigbang complex {complex_id.strip()} 로 건물 정보를 보세요',
        )
    return number


def _compare_numbers(number: int, compare: list[str]) -> list[int]:
    """`--compare` 의 단지 ID 를 번호로 바꾸고 요청 전에 막을 것을 막는다: 3곳 초과, 오피스텔, 조회 단지 자신, 같은 단지 두 번.

    Raises:
        JibsaError: 위에 걸릴 때 (INVALID_ARGUMENT).
    """
    if len(compare) > MAX_COMPARE_DANJIS:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'비교 단지가 너무 많습니다 (받은 수: {len(compare)}곳)',
            hint=f'비교 단지는 {MAX_COMPARE_DANJIS}곳까지 줄 수 있습니다 (직방 웹은 1곳). 줄여서 다시 부르세요',
        )
    numbers: list[int] = []
    for complex_id in compare:
        kind, other = parse_complex_id(complex_id)
        if kind != 'apt':
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"비교 단지는 아파트 단지만 고를 수 있습니다: '{complex_id}'",
                hint='--compare 에는 apt-… 단지 ID 를 주세요 (후보는 --compare 없이 부른 결과의 comparable_complexes)',
            )
        if other == number:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"조회 단지 자신은 비교 단지로 줄 수 없습니다: '{complex_id}'",
                hint='다른 단지를 --compare 에 주세요 (후보는 --compare 없이 부른 결과의 comparable_complexes)',
            )
        if other in numbers:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"같은 단지를 --compare 에 두 번 줬습니다: '{complex_id}'",
                hint='--compare 에는 서로 다른 단지를 주세요',
            )
        numbers.append(other)
    return numbers


def _compare_candidates(
    complex_id: str,
    numbers: list[int],
    related: ZigbangDanjisPriceChartRelatedDanjisResponseModel,
) -> list[_Candidate]:
    """`--compare` 의 단지가 모두 직방이 준 비교 후보인지 보고 그 후보를 준다 (웹은 후보 창에서만 고르게 한다).

    후보 목록에서 빈 항목·ID 없는 후보를 뺐어도 받아들이지 않고 hint 로 알린다. 웹도 그 후보는 고를 수 없어 받아들이면 웹에서 볼 수
    없는 비교가 된다 (평형 확인 `_check_pyeong` 이 확인을 건너뛰는 것과 다르다).

    직방은 후보가 없는 단지(없는 단지 번호 포함)에도 빈 목록 `[]` 을 준다 (2026-11-22 실측). 그래서 목록이 null 이거나 키가 없으면 후보가 없는
    것이 아니라 응답 형식이 바뀐 것이다.

    Raises:
        JibsaError: 후보에 없는 단지가 있을 때 (INVALID_ARGUMENT). hint 에 후보를 적고, 빼고 읽은 항목이 있으면 그것도 적는다.
            직방이 비교 후보 목록을 주지 않았을 때 (UPSTREAM_ERROR).
    """
    if related.danjis is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'직방이 {complex_id} 의 비교 후보 목록을 주지 않아 --compare 단지를 확인할 수 없습니다',
            hint=UPSTREAM_RETRY_HINT,
        )
    danjis = related.danjis
    candidates = [_Candidate(item.id, text_or_none(item.name)) for item in danjis if item.id is not None]
    by_number = {candidate.number: candidate for candidate in candidates}
    missing = [number for number in numbers if number not in by_number]
    if missing:
        if candidates:
            shown = ', '.join(
                f"{apt_complex_id(candidate.number)} {candidate.name or ''}".strip() for candidate in candidates[:MAX_CANDIDATES_IN_HINT]
            )
            hint = f'--compare 에는 직방이 준 비교 후보만 받습니다: {shown}'
        else:
            hint = '이 단지는 직방이 비교 후보를 주지 않습니다. --compare 를 빼고 단지 추이를 보세요'
        dropped = related.null_items('danjis')
        no_id = sum(1 for item in danjis if item.id is None)
        if dropped or no_id:
            skipped = [text for count, text in ((dropped, f'빈 항목 {dropped}개'), (no_id, f'단지 ID 가 없는 후보 {no_id}곳')) if count]
            # 끝 낱말이 '개'(받침 없음)면 '가', '곳'(받침 있음)이면 '이' 다
            hint += f" (직방 후보 목록에 {'와 '.join(skipped)}{particle(skipped[-1], '이/가')} 와서 빼고 읽었습니다. {UPDATE_MAYBE_NEEDED})"
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방이 {complex_id} 의 비교 후보로 주지 않은 단지입니다: {', '.join(apt_complex_id(number) for number in missing)}",
            hint=hint,
        )
    return [by_number[number] for number in numbers]


def _line_kinds(
    lines: list[ZigbangDanjiPriceChartLineModel],
    candidates: list[_Candidate],
    dropped: int,
) -> list[_LineKind]:
    """줄마다 종류와 (비교 단지의) 단지 ID 를 정한다.

    직방은 줄을 단지 ID 오름차순으로 주고 구를 끝에 붙여 (2026-11-19 표본: 파크리오 16629 → 헬리오시티 38487 → 올림픽파크포레온 68581 →
    송파구) 조회 단지가 첫 줄이 아니다. 그래서 위치 대신 이름으로 가른다: --compare 로 준 후보의 이름이면 비교 단지, 마지막 줄이고 후보
    이름이 아니면 구, 남은 줄이 조회 단지다.

    직방시세가 없는 단지(분양예정 등)는 조회 단지 줄 없이 구 줄만 온다 (2026-11-22 실측: apt-90913 `[서초구]`, apt-94457 `[송파구]`,
    apt-94457 + 헬리오시티 `[헬리오시티, 송파구]`, 구 줄은 늘 마지막). 그래서 줄 수가 (비교 수 + 1) 이고 마지막 줄이 후보 이름이 아니며
    나머지 줄 이름이 후보 이름과 같으면 마지막이 구이고 조회 단지 줄은 없다.

    이름이 겹치거나(같은 이름은 어느 단지인지 가를 수 없다) 줄 수가 (비교 수 + 1, 1 + 비교 수 + 1) 이 아니거나 빈 줄을 뺐거나 이름이 없으면
    판정하지 않는다 (모두 null).
    """
    unknown = [_LineKind(None, None) for _ in lines]
    labels = [text_or_none(line.label) for line in lines]
    names = [candidate.name for candidate in candidates]
    if (
        dropped
        or None in labels
        or None in names
        or len(set(labels)) != len(labels)
        or len(set(names)) != len(names)
    ):
        return unknown
    id_by_name = {name: apt_complex_id(candidate.number) for name, candidate in zip(names, candidates) if name is not None}
    if len(lines) == len(candidates) + 1:
        # 조회 단지 줄이 없는 모양: 줄이 모두 비교 단지이고 마지막만 구다
        if labels[-1] in id_by_name or set(labels[:-1]) != set(id_by_name):
            return unknown
        return [*(_LineKind('비교 단지', id_by_name[label]) for label in labels[:-1] if label is not None), _LineKind('구', None)]
    if len(lines) != len(candidates) + 2:
        return unknown
    others = [index for index, label in enumerate(labels) if label not in id_by_name]
    # 비교 단지 이름이 모두 줄에 있으면 남는 줄은 둘 (조회 단지, 구)이고 구가 마지막이다
    if len(others) != 2 or others[-1] != len(lines) - 1:
        return unknown
    kinds: list[_LineKind] = []
    for index, label in enumerate(labels):
        if label in id_by_name:
            kinds.append(_LineKind('비교 단지', id_by_name[label]))
        elif index == others[0]:
            kinds.append(_LineKind('단지', None))
        else:
            kinds.append(_LineKind('구', None))
    return kinds


def _month_of(date_text: str | None) -> str | None:
    """직방 월 항목의 날짜('2026-01-01')를 'YYYY-MM' 으로. 읽지 못하면 None 이고 원래 글자를 [참고] 로 알린다 (`read_date`)."""
    date = read_date(date_text, '추이 월')
    return date[:7] if date else None


def get_price_trend(
    client: ZigbangClient,
    complex_id: str,
    *,
    period: ZigbangPriceTrendPeriod = DEFAULT_PRICE_TREND_PERIOD,
    compare: list[str] | None = None,
) -> ZigbangPriceTrendResult:
    """단지 직방시세 추이를 준다 (요청 2회: 직방시세 그래프와 비교 후보).

    `compare` 가 없으면 그래프(본 조회)를 먼저 받고 비교 후보는 덤 조회라 실패하면 `comparable_complexes` 만 null 이고 `[실패]` 로 알린다
    (목록을 주지 않아도 `[실패]`, 업데이트 문구).
    `compare` 가 있으면 후보(본 조회, 실패는 그대로 에러)를 먼저 받아 준 단지가 모두 후보인지 보고 그 단지들을 `addDanjiIds` 로
    그래프에 붙인다. 웹은 비교 단지를 하나만 고르게 하지만 서버는 여럿을 받는다 (웹과 다른 점, 소스 가이드).

    Args:
        complex_id: 아파트 단지 ID (apt-…).
        period: 웹 기간 탭 (1년·3년·전체, 기본 3년).
        compare: 함께 볼 비교 단지 ID (비교 후보 안에서, 최대 `MAX_COMPARE_DANJIS`곳).

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나 오피스텔일 때, 비교 단지가 `MAX_COMPARE_DANJIS`곳을 넘거나 오피스텔·조회 단지 자신·같은 단지
            두 번일 때 (INVALID_ARGUMENT, 요청 없이), 비교 단지가 비교 후보에 없을 때 (INVALID_ARGUMENT, 후보 조회 뒤),
            `--compare` 를 줬는데 직방이 비교 후보 목록을 주지 않았을 때 (UPSTREAM_ERROR).
    """
    number = _apt_number(complex_id)
    compare_numbers = _compare_numbers(number, compare or [])
    shown_id = apt_complex_id(number)
    notes: list[str] = []
    related: ZigbangDanjisPriceChartRelatedDanjisResponseModel | None = None
    candidates: list[_Candidate] = []
    if compare_numbers:
        related = client.run_request_danjis_price_chart_related_danjis(
            ZigbangDanjisPriceChartRelatedDanjisRequestParameterModel(danji_id=number)
        )
        candidates = _compare_candidates(shown_id, compare_numbers, related)
    chart = client.run_request_danjis_price_chart(ZigbangDanjisPriceChartRequestParameterModel(
        danji_id=number,
        period=CHART_PERIOD_BY_LABEL[period],
        add_danji_ids=compare_numbers,
    ))
    if related is None:
        # 비교 후보는 덤이라 그래프(본 조회) 뒤에 받고, 실패해도 그래프는 버리지 않는다
        try:
            related = client.run_request_danjis_price_chart_related_danjis(
                ZigbangDanjisPriceChartRelatedDanjisRequestParameterModel(danji_id=number)
            )
        except OPTIONAL_LOOKUP_ERRORS as exc:
            notes.append(lookup_failure_note(
                exc, '직방', '비교 단지 후보',
                'comparable_complexes 값을 모릅니다 (직방 웹 단지 화면의 단지 비교하기에서 확인)',
            ))
    comparable = None if related is None or related.danjis is None else [related_complex_of(item) for item in related.danjis]
    if related is not None and related.danjis is None:
        # 덤 조회가 예외 없이 끝났는데 목록이 없으면 후보가 없는 것([])이 아니라 응답 형식이 바뀐 것이다 (예외 실패와 같은 [실패])
        notes.append(note(
            '실패',
            f'직방이 비교 단지 후보 목록을 주지 않았습니다. {UNEXPECTED_FORMAT_TEXT}. '
            'comparable_complexes 값을 모릅니다 (직방 웹 단지 화면의 단지 비교하기에서 확인)',
        ))

    lines: list[ZigbangComplexPriceLine] | None = None
    dropped_lines = chart.null_items('lines')
    if chart.lines is not None:
        kinds = _line_kinds(chart.lines, candidates, dropped_lines)
        lines = [
            ZigbangComplexPriceLine(
                name=text_or_none(line.label),
                kind=kind.kind,
                complex_id=kind.complex_id,
                months=None if line.data is None else [
                    # 웹은 0 을 그리지 않는 '값 없음' 으로 본다. 점은 남기고 값만 모름이다
                    ZigbangComplexPricePoint(month=_month_of(point.date), estimated_price_per_pyeong_manwon=None if point.price == 0 else point.price)
                    for point in line.data
                ],
            )
            for line, kind in zip(chart.lines, kinds)
        ]
        if dropped_lines:
            notes.append(null_items_note('직방 시세 추이 줄', dropped_lines, ('lines[].kind',)))
        dropped_points = sum(line.null_items('data') for line in chart.lines)
        if dropped_points:
            notes.append(null_items_note('직방 시세 추이 월', dropped_points))
        # 직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다. 줄 종류를 판정하지 못한 경우(모두 null)에는 알리지 않는다
        kind_set = {kind.kind for kind in kinds}
        if '구' in kind_set and '단지' not in kind_set:
            only = '비교 단지와 구 줄만' if candidates else '구 줄만'
            notes.append(note(
                '참고',
                f'직방이 이 단지의 시세 줄을 주지 않아 lines 에 {only} 있습니다 '
                f'(분양 전이거나 직방시세가 없는 단지일 수 있습니다. jibsa zigbang complex {shown_id} 로 확인)',
            ))
    if chart.lines is None:
        # 목록이 없는 것은 줄이 없는 것([])이 아니라 응답 형식이 바뀐 것이다 (없는 단지 번호도 200 에 빈 `list` 가 온다)
        notes.append(note('참고', f'직방이 시세 추이 줄 목록을 주지 않아 lines 를 모릅니다. {UNEXPECTED_FORMAT_TEXT}'))
    # 빈 항목을 빼서 비었을 때는 [제외] 가 알린다 (직방이 줄을 주지 않은 것과 다르다)
    elif not lines and not dropped_lines:
        notes.append(note(
            '참고',
            f'직방이 이 단지의 시세 추이를 주지 않았습니다 (분양 전이거나 없는 단지일 수 있습니다. jibsa zigbang complex {shown_id} 로 확인)',
        ))
    return ZigbangPriceTrendResult(
        complex_id=shown_id,
        period=period,
        comparable_complexes=comparable,
        lines=lines,
        notes=notes,
    )


def _check_pyeong(complex_id: str, pyeong_id: int, room_info: ZigbangDanjisRoomTypesResponseModel) -> list[str]:
    """평형이 그 단지의 것인지 본다. 직방은 평형 ID 를 검사하지 않아 없는 ID 는 빈 응답을, 다른 단지의 평형 ID 는 그 평형의 값을 준다 (2026-11-22 실측).

    웹은 그 단지의 평형 탭에서만 고르게 해서 단지의 평형 목록(`room_types`)에 있는 ID 만 받는다. 평형 목록에서 빈 항목을 뺐고 ID 가 목록에
    없으면 빠진 항목이 그 평형이었는지 알 수 없어 확인하지 않고 알린다 (`complex` 의 평형 확인과 같다). 평형이 없는 단지(분양예정)는 빈
    목록이고, 목록이 없거나 null 이면(모름) 평형이 없다고 하지 않고 응답 형식이 바뀐 것으로 알린다.

    Returns:
        알릴 안내 (빈 항목을 뺐을 때만).

    Raises:
        JibsaError: 단지에 없는 평형이거나 직방이 평형 정보를 주지 않는 단지일 때 (INVALID_ARGUMENT), 직방이 평형 목록(`room_types`)을 주지
            않았을 때 (UPSTREAM_ERROR).
    """
    if room_info.room_types is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'직방이 {complex_id} 단지의 평형 목록을 주지 않아 평형을 확인할 수 없습니다',
            hint=UPSTREAM_RETRY_HINT,
        )
    known = {room_type.id for room_type in room_info.room_types}
    if pyeong_id in known:
        return []
    dropped = room_info.null_items('room_types')
    if dropped:
        return [null_items_note('직방 단지 평형', dropped)]
    if not known:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'{complex_id} 단지는 직방에 평형 정보가 없습니다',
            hint=f'평형 시세 추이를 볼 수 없는 단지입니다. --pyeong 을 빼고 jibsa zigbang price-trend {complex_id} 로 단지 추이를 보세요',
        )
    raise JibsaError(
        code='INVALID_ARGUMENT',
        message=f'{complex_id} 단지에 없는 평형입니다 (평형 ID: {pyeong_id})',
        hint=f'jibsa zigbang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 --pyeong 에 주세요',
    )


def _gap_price(item: ZigbangRoomTypePriceMonthModel) -> int | float | None:
    return item.monthly_gap.price if item.monthly_gap else None


def _converted_price_range(lowest_manwon: float | None, highest_manwon: float | None) -> AmountRange | None:
    """전월세 거래 범위 (두 끝이 보증금이 아니라 환산가). 두 끝이 모두 없으면 모름(None)."""
    if lowest_manwon is None and highest_manwon is None:
        return None
    return AmountRange(
        lowest=AmountSet(converted_price_manwon=lowest_manwon), highest=AmountSet(converted_price_manwon=highest_manwon),
    )


def _jeonse_wolse_of(item: ZigbangRoomTypePriceMonthModel) -> ZigbangPyeongJeonseWolse:
    """한 달 전월세 기록. 0 처리는 매매(`_merge_months`)와 같고, 거래 건수는 전세와 월세를 합쳐 0건인지 본다 (둘 다 모르면 0건이라 하지 않는다)."""
    no_price = item.average_price == 0
    # 리뷰 오탐 (2026-11-22): 월세 건수만 모를 때 전세 0건이면 최저·최고가를 null(모름)로 둔다. 건수를 모르는 달의 값은 직방이 거래 없는 달을 채운
    # 값일 수 있어 그대로 내지 않는다 (docs/zigbang.md 평형 추이 '아는 것의 합이 0')
    counts = [count for count in (item.volume, item.rent_volume) if count is not None]
    no_trades = bool(counts) and sum(counts) == 0
    return ZigbangPyeongJeonseWolse(
        estimated_deposit_manwon=None if no_price else item.average_price,
        # 두 끝이 환산가 하나뿐이라 보증금(deposit_manwon)이 아니라 converted_price_manwon 이다
        trade_range=None if no_price or no_trades else _converted_price_range(item.min_price, item.max_price),
        trade_counts={'jeonse': item.volume, 'wolse': item.rent_volume},
        estimated_deposit_change_manwon=None if no_price else _gap_price(item),
    )


def _merge_months(
    trade: ZigbangPyeongTrendTrade,
    sales: list[ZigbangRoomTypePriceMonthModel],
    rents: list[ZigbangRoomTypePriceMonthModel],
) -> list[ZigbangPyeongPriceMonth]:
    """매매·전월세 월 목록을 월로 맞춘다. 한쪽에만 있는 달은 다른 쪽이 null 이다. 월을 읽지 못한 항목은 맞출 수 없어 따로 한 줄이고 맨 뒤에 둔다."""
    rows: list[ZigbangPyeongPriceMonth] = []
    by_month: dict[str, ZigbangPyeongPriceMonth] = {}
    for item in sales:
        month = _month_of(item.date)
        # 한 달 매매 기록. 직방시세(average_price)가 0 인 달은 웹이 그리지 않는 '값 없음' 이라 값 칸이 모두 모름이고, 거래가 0건인 달은 최저·최고가만 모름이다.
        # 입주 전 달은 average·min·max·monthly_gap.price 가 모두 0 이고 건수만 양수다 (2026-11-22 표본). 거래가 0건인 달은 직방이 min·max 에
        # 시세 값을 채워 주는데 그 달에 거래가 있었던 것처럼 읽히지 않게 거래 범위를 비운다. 건수는 0 도 진짜 값이다.
        no_price = item.average_price == 0
        no_trades = item.volume == 0
        sale = ZigbangPyeongSale(
            estimated_price_manwon=None if no_price else item.average_price,
            trade_range=None if no_price or no_trades else sale_price_range(item.min_price, item.max_price),
            trade_count=item.volume,
            estimated_price_change_manwon=None if no_price else _gap_price(item),
        )
        row = ZigbangPyeongPriceMonth(trade=trade, month=month, sale=sale, jeonse_wolse=None)
        rows.append(row)
        if month is not None:
            by_month.setdefault(month, row)
    for item in rents:
        month = _month_of(item.date)
        same_month = by_month.get(month) if month is not None else None
        if same_month is not None and same_month.jeonse_wolse is None:
            same_month.jeonse_wolse = _jeonse_wolse_of(item)
        else:
            rows.append(ZigbangPyeongPriceMonth(trade=trade, month=month, sale=None, jeonse_wolse=_jeonse_wolse_of(item)))
    rows.sort(key=lambda row: (row.month is None, row.month or ''))
    return rows


def _no_records_text(period: ZigbangPriceTrendPeriod, trade: ZigbangPyeongTrendTrade) -> str:
    """평형에 시세·거래 기록이 없다는 안내. 탭과 기간을 넣는다 (한 탭만 비는 평형이 있어 탭을 빼면 거짓이 된다)."""
    span = '전체 기간' if period == '전체' else f'{period} 동안'
    if trade == '전체':
        return f'이 평형에 {span} 직방 시세·거래 기록이 없습니다'
    return f'이 평형에 {span} 직방 {trade} 시세·거래 기록이 없습니다'


def get_pyeong_price_trend(
    client: ZigbangClient,
    complex_id: str,
    pyeong_id: int,
    *,
    period: ZigbangPriceTrendPeriod = DEFAULT_PRICE_TREND_PERIOD,
    trade: ZigbangPyeongTrendTrade = DEFAULT_PYEONG_TREND_TRADE,
) -> ZigbangPyeongPriceTrendResult:
    """평형 하나의 월별 시세·거래 추이를 준다 (요청 2회: 단지 평형 정보로 평형 확인, 평형 시세 그래프).

    직방이 평형 ID 를 검사하지 않아 단지의 평형 목록에 있는지 먼저 본다 (`_check_pyeong`). 고른 거래 탭의 목록만 읽고(전체는 매매·전월세
    모두) 월로 맞춰 낸다. 월 목록이 비었을 때:
    - `list` 객체가 없거나 null 이면 응답 형식이 바뀐 것이라 `months` 는 null 이고 [참고] 로 알린다 (평형을 확인하지 못했으면 단지에 없는
      평형 ID 일 수 있다고 알린다).
    - `list` 는 있는데 고른 탭의 키가 모두 없으면, 평형을 확인했을 때는 그 탭에 기록이 없는 것이라 `[]` 와 '기록이 없다' [참고] 다.
      평형을 확인하지 못했으면(빈 항목을 빼서 평형 목록에서 찾지 못함) 없는 평형 ID 와 응답이 같아 기록 없음이라 하지 않고 `months` 는 null 이다
      (2026-11-22 실측: apt-94091 평형 442794 `--trade 전월세` 와 없는 평형 ID 999999999 모두 `list` 에 탭 키가 없다).
    - 키가 있는데 비었으면 빈 항목을 뺀 것이면 `[]` 와 [제외] 만, 진짜 빈 목록이면 `[]` 와 '기록이 없다' [참고] 다.

    Args:
        complex_id: 아파트 단지 ID (apt-…).
        pyeong_id: 평형 ID (complex 결과의 pyeongs[].pyeong_id).
        period: 웹 기간 탭 (1년·3년·전체, 기본 3년).
        trade: 웹 거래 탭 (기본 전체).

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나 오피스텔이거나, 단지에 없는 평형이거나 평형 정보가 없는 단지일 때 (INVALID_ARGUMENT),
            직방이 단지 평형 목록을 주지 않았을 때 (UPSTREAM_ERROR).
    """
    number = _apt_number(complex_id)
    shown_id = apt_complex_id(number)
    room_info = client.run_request_danjis_room_types(ZigbangDanjisRoomTypesRequestParameterModel(danji_id=number))
    notes = _check_pyeong(shown_id, pyeong_id, room_info)
    chart = client.run_request_danjis_room_types_price_chart(ZigbangDanjisRoomTypesPriceChartRequestParameterModel(
        danji_id=number,
        room_type_id=pyeong_id,
        deal_type=DEAL_TYPE_BY_TRADE[trade],
        period=CHART_PERIOD_BY_LABEL[period],
    ))
    by_type = chart.months_by_type
    # 서버가 고른 탭만 주지만 읽는 쪽도 고른 탭의 키만 본다 (출력에서 다른 탭의 키를 뺀다)
    names = [name for name, shown in (('trade', trade != '전월세'), ('deposit', trade != '매매')) if shown]
    # 기록이 없는 탭과 없는 평형 ID 는 `list` 안의 탭 키가 없는 같은 모양이다 (2026-11-22 apt-94091 평형 442794 rent·없는 평형 999999999 실측).
    # 둘은 응답으로 가를 수 없고 평형 확인(notes 가 비었으면 확인함)으로만 가른다. `list` 자체가 없으면 응답 형식이 바뀐 것이다
    months: list[ZigbangPyeongPriceMonth] | None
    if by_type is not None and not notes and all(getattr(by_type, name) is None for name in names):
        months = []
        notes.append(note('참고', _no_records_text(period, trade)))
    elif by_type is None or all(getattr(by_type, name) is None for name in names):
        if notes:
            reason = (
                '위 [제외] 때문에 평형을 확인하지 못해 단지에 없는 평형 ID 일 수 있습니다 '
                f'(jibsa zigbang complex {shown_id} 결과의 pyeongs[].pyeong_id 로 확인하세요)'
            )
        else:
            reason = UNEXPECTED_FORMAT_TEXT
        notes.append(note('참고', f'직방이 이 평형의 시세 월 목록을 주지 않아 months 를 모릅니다. {reason}'))
        months = None
    else:
        sales = (by_type.trade or []) if trade != '전월세' else []
        rents = (by_type.deposit or []) if trade != '매매' else []
        months = _merge_months(trade, sales, rents)
        dropped = by_type.null_items(*names)
        if dropped:
            notes.append(null_items_note('직방 평형 시세 월', dropped))
        # 빈 항목을 빼서 비었을 때는 [제외] 가 알린다 (직방이 기록을 주지 않은 것과 다르다)
        elif not months:
            notes.append(note('참고', _no_records_text(period, trade)))
    return ZigbangPyeongPriceTrendResult(
        complex_id=shown_id,
        pyeong_id=pyeong_id,
        period=period,
        trade_tab=trade,
        months=months,
        notes=notes,
    )
