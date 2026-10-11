"""단지·평형별 실거래가 (real-price)."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    normalize_date,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.real_price import (
    NaverComplexPyeongRealPriceListV1RequestParameterModel,
    NaverComplexPyeongRealPriceV2RequestParameterModel,
    NaverComplexVillaRealPricePageV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.real_price import (
    NaverRealPriceModel,
    NaverVillaRealPriceModel,
)
from jibsa.providers.naver.service.common import (
    PERIOD_YEARS_BY_NAME,
    TRADE_CODE_BY_NAME,
    check_pyeong_numbers,
    kst_today,
    unwrap,
    years_ago,
)

from typing import (
    Annotated,
    Any,
)


class NaverRealPrice(BaseModel):
    """실거래 한 건 (만원). 거래 유형에 없는 가격 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 가격 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str,
        Field(description='계약일')
    ]
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    category: Annotated[
        str | None,
        Field(description='중개거래 / 직거래')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신 계약')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()):
            data.pop(field, None)
        # 갱신 계약은 전월세에만 있다
        if self.trade_type == '매매':
            data.pop('renewal', None)
        return data


class NaverRealPriceResult(BaseModel):
    """평형별 실거래 내역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_number: Annotated[
        int,
        Field(description='단지 번호')
    ]
    pyeong_number: Annotated[
        int,
        Field(description='평형 번호')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    period: Annotated[
        str | None,
        Field(description='--period 로 준 기간 (1년, 3년, 5년). 주지 않았으면 키가 없다')
    ] = None
    since: Annotated[
        str | None,
        Field(description='기간 시작일 (YYYY-MM-DD). --period 를 주지 않았으면 키가 없다')
    ] = None
    transactions: Annotated[
        list[NaverRealPrice],
        Field(description='최근 순 실거래')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='기간 안 거래를 다 받지 못했다는 안내 등. CLI 가 결과 위에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.period is None:
            data.pop('period', None)
            data.pop('since', None)
        return data


# 실거래가 한 페이지 크기. 예전 엔드포인트(complex/pyeong/realPrice)와 같은 10건으로 둬 --pages 의 뜻을 유지한다
REAL_PRICE_PAGE_SIZE: int = 10
# 기간 조회에서 빌라 단지 실거래를 받는 페이지 크기와 페이지 수 상한. 빌라 단지는 거래가 적어 보통 한 페이지로 끝난다
VILLA_PERIOD_PAGE_SIZE: int = 100
MAX_VILLA_PERIOD_PAGES: int = 5


def _real_price(item: NaverRealPriceModel, trade_type: str) -> NaverRealPrice:
    return NaverRealPrice(
        trade_type=trade_type,
        trade_date=normalize_date(item.trade_date) or item.trade_date,
        floor=item.floor,
        price_manwon=won_to_manwon(item.deal_price),
        deposit_manwon=won_to_manwon(item.deposit),
        rent_manwon=won_to_manwon(item.monthly_rent),
        category=item.trade_category,
        cancelled=item.is_delete,
        renewal=item.is_renew,
    )


def _villa_real_price(item: NaverVillaRealPriceModel, trade_type: str) -> NaverRealPrice:
    return NaverRealPrice(
        trade_type=trade_type,
        trade_date=normalize_date(item.trade_date) or item.trade_date,
        floor=item.floor,
        price_manwon=won_to_manwon(item.deal_price),
        deposit_manwon=won_to_manwon(item.deposit),
        rent_manwon=won_to_manwon(item.monthly_rent),
        category=item.trade_category,
        cancelled=item.is_canceled,
        # 빌라는 갱신 계약 여부 대신 계약갱신요구권 사용 여부만 준다. 썼으면 갱신이지만,
        # 안 썼어도 합의 갱신일 수 있어 그때는 모름(None)이다
        renewal=True if item.is_renew_request_right else None,
    )


def get_real_prices(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str = '매매',
    pages: int = 1,
    period: str | None = None,
    today: date | None = None,
) -> NaverRealPriceResult:
    """평형별 실거래가를 `pages` 페이지(페이지당 `REAL_PRICE_PAGE_SIZE` 건)까지 모아 만원으로 환산한다.

    빌라 단지는 아파트 단지 실거래가가 비어 오므로, 첫 페이지가 비면 평형 번호를 확인하면서 단지 종류를 정하고
    (1~2회 추가) 빌라 단지면 빌라 단지 실거래가로 다시 묻는다. 아파트 단지면 거래가 없는 평형으로 보고 0건이다.

    Args:
        period: `PERIOD_YEARS_BY_NAME` 의 이름. 주면 `pages` 대신 그 기간 안 거래를 모두 받는다
            (아파트 단지는 1회 호출).
        today: 기간의 기준일. Defaults to 오늘(한국 시간).

    Raises:
        JibsaError: 거래가 0건인데 평형 번호가 그 단지에 없으면 NOT_FOUND.
    """
    if period is not None:
        return _get_real_prices_in_period(
            client, complex_number, pyeong_number, trade_type=trade_type, period=period, today=today or kst_today(),
        )
    transactions: list[NaverRealPrice] = []
    for page in range(pages):
        result = unwrap(
            client.run_request_complex_pyeong_real_price_v2(
                NaverComplexPyeongRealPriceV2RequestParameterModel(
                    complex_number=complex_number,
                    pyeong_type_number=pyeong_number,
                    trade_type=TRADE_CODE_BY_NAME[trade_type],
                    page=page,
                    size=REAL_PRICE_PAGE_SIZE,
                )
            ),
            '실거래가',
        )
        if page == 0 and not result.items:
            if check_pyeong_numbers(client, complex_number, [pyeong_number]):
                transactions, _ = _villa_real_prices(
                    client, complex_number, pyeong_number, trade_type=trade_type, size=REAL_PRICE_PAGE_SIZE, max_pages=pages,
                )
            break
        if not result.items:
            break
        transactions.extend(_real_price(item, trade_type) for item in result.items)
        if result.has_next_page is False:
            break
    return NaverRealPriceResult(
        complex_number=complex_number,
        pyeong_number=pyeong_number,
        trade_type=trade_type,
        transactions=transactions,
    )


def _villa_real_prices(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str,
    size: int,
    max_pages: int,
    since: str | None = None,
) -> tuple[list[NaverRealPrice], bool]:
    """빌라 단지 실거래를 최근 순으로 `max_pages` 쪽까지 받는다. `since` 를 주면 그보다 오래된 거래가 나온 쪽에서 멈춘다.

    `check_pyeong_numbers` 로 빌라 단지임을 정한 뒤에만 부른다. 빌라 단지에 그 거래가 없으면 서버는 실패가 아니라
    빈 목록을 주므로(서진빌라 724112 월세: isSuccess true·0건, 2026-10-10) 실패 응답은 0건으로 보지 않고 에러로 낸다.

    Returns:
        tuple[list[NaverRealPrice], bool]: 거래, 쪽 수 상한에 걸려 멈췄는지 (더 있을 수 있음).
    """
    transactions: list[NaverRealPrice] = []
    for page in range(max_pages):
        result = unwrap(
            client.run_request_complex_villa_real_price_page_v1(
                NaverComplexVillaRealPricePageV1RequestParameterModel(
                    complex_number=complex_number,
                    pyeong_type_number=pyeong_number,
                    trade_type=TRADE_CODE_BY_NAME[trade_type],
                    page=page,
                    size=size,
                )
            ),
            '실거래가',
        )
        recent = [_villa_real_price(item, trade_type) for item in result.items]
        kept = recent if since is None else [item for item in recent if item.trade_date >= since]
        transactions.extend(kept)
        # 마지막 쪽을 넘겨도 result=null 이 아니라 빈 목록이 와서(hasNextPage false) unwrap 이 에러를 내지
        # 않는다 (2026-10-09 확인)
        if len(kept) < len(recent) or not result.items or result.has_next_page is False:
            return transactions, False
    return transactions, True


def _get_real_prices_in_period(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str,
    period: str,
    today: date,
) -> NaverRealPriceResult:
    """기간 안 실거래 전부. 아파트 단지는 기간 목록 1회, 비어 오면 평형 번호를 확인하면서 단지 종류를 정하고
    빌라 단지면 빌라 단지 페이지를 기간 시작일까지 넘긴다.

    기간 목록은 빌라 단지에 거래가 있어도 빈 목록을 준다 (서진빌라 전세 4건, 2026-10-10 확인).
    """
    since = years_ago(today, PERIOD_YEARS_BY_NAME[period])
    items = unwrap(
        client.run_request_complex_pyeong_real_price_list_v1(
            NaverComplexPyeongRealPriceListV1RequestParameterModel(
                complex_number=complex_number,
                pyeong_type_number=pyeong_number,
                trade_type=TRADE_CODE_BY_NAME[trade_type],
                start_date=since,
                end_date=today.isoformat(),
            )
        ),
        '실거래가',
    )
    transactions = [_real_price(item, trade_type) for item in items]
    notes: list[str] = []
    if not transactions and check_pyeong_numbers(client, complex_number, [pyeong_number]):
        transactions, truncated = _villa_real_prices(
            client, complex_number, pyeong_number,
            trade_type=trade_type, size=VILLA_PERIOD_PAGE_SIZE, max_pages=MAX_VILLA_PERIOD_PAGES, since=since,
        )
        if truncated:
            notes.append(
                f'빌라 단지 실거래를 {MAX_VILLA_PERIOD_PAGES * VILLA_PERIOD_PAGE_SIZE}건까지만 받았습니다. '
                '기간 안 거래가 더 있을 수 있으니 --period 를 줄여 보세요'
            )
    return NaverRealPriceResult(
        complex_number=complex_number,
        pyeong_number=pyeong_number,
        trade_type=trade_type,
        period=period,
        since=since,
        transactions=transactions,
        notes=notes,
    )
