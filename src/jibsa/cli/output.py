import json
import sys
from collections.abc import (
    Generator,
    Mapping,
)
from contextlib import contextmanager
from math import isfinite

import typer
from httpx import (
    HTTPError,
    HTTPStatusError,
)
from pydantic import (
    BaseModel,
    ValidationError,
)
from typer._click.exceptions import (  # Typer 가 내장한 Click 의 예외. 비공개 경로라 Typer 업그레이드 시 확인 필요.
    ClickException,
    UsageError,
)
from typer._click.globals import get_current_context

from jibsa.core.errors import JibsaError
from jibsa.core.geo import in_korea
from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    note,
    tagged_notes,
)
from jibsa.core.schema import is_request_validation_error

from typing import (
    Any,
    NamedTuple,
    TypeVar,
    cast,
)


# 출력 좌표의 소수 자리. 일곱째 자리가 약 1cm 라 원본 정밀도를 잃지 않는다
COORDINATE_DECIMALS: int = 7
ChoiceT = TypeVar('ChoiceT', bound=str)
TradeT = TypeVar('TradeT', bound=str)


def _dumps(data: Any, pretty: bool | None) -> str:
    if pretty is None:
        pretty = sys.stdout.isatty()
    # allow_nan 을 끄지 않는다. 끄면 NaN 하나에 출력 전체가 실패하는데, 당근 숫자 문자열(_to_float)·seroval 상수로 NaN 이
    # 들어온 적이 없다 (2026-10-18 실측: 역삼동 지도 페이지에 NaN·Infinity 0개). 2026-10-18 리뷰 오탐 확인
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (',', ':'),
    )


def _round_coordinates(value: Any) -> Any:
    """`lat`·`lng` 값을 소수 일곱째 자리(약 1cm)로 반올림한다. 원본 좌표의 부동소수점 찌꺼기(127.04934499999999)를 지운다."""
    if isinstance(value, dict):
        return {
            key: round(item, COORDINATE_DECIMALS) if key in ('lat', 'lng') and isinstance(item, float)
            else _round_coordinates(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_round_coordinates(item) for item in value]
    return value


def emit(
    data: BaseModel | list[BaseModel] | dict[str, Any],
    pretty: bool | None = None,
    notes: list[str] | None = None,
) -> None:
    """결과를 JSON 으로 stdout 에 쓴다.

    값을 모르는 필드는 `null` 로 남기고, 매물에 해당 없는 필드는 `Listing` 이
    키째 뺀다 (`Listing.not_applicable_fields`). `notes` 가 있으면 맨 앞에 붙이고,
    없으면 키를 뺀다 (모호하거나 넓은 지역 안내 등).
    """
    if isinstance(data, BaseModel):
        payload: Any = data.model_dump(mode='json')
    elif isinstance(data, list):
        payload = [item.model_dump(mode='json') for item in data]
    else:
        payload = data
    if not isinstance(payload, dict) and notes:
        payload = {'items': payload}
    if notes:
        payload = {'notes': tagged_notes(notes), **payload}
    typer.echo(_dumps(_round_coordinates(payload), pretty))


def emit_error(code: str, message: str, hint: str | None = None, /, **extra: Any) -> None:
    """`{"error": {...}}` 를 stderr 에 쓴다. 터미널이면 들여쓰기, 아니면 한 줄.

    `code`·`message`·`hint` 는 위치 인자로만 받아, `JibsaError.details` 에 같은 이름의 키가 있어도 인자가 겹쳐
    (TypeError) 에러 JSON 대신 traceback 으로 끝나지 않는다. 겹친 키는 앞의 세 값을 덮어쓰지 않는다.
    """
    error: dict[str, Any] = {'code': code, 'message': message}
    if hint:
        error['hint'] = hint
    error.update({
        key: value for key, value in extra.items()
        if value is not None and key not in ('code', 'message', 'hint')
    })
    # 들여쓰기는 stdout 이 아니라 에러를 쓰는 stderr 가 터미널인지로 정한다 (`jibsa ... | jq` 도 에러는 터미널에 보인다)
    typer.echo(_dumps({'error': error}, sys.stderr.isatty()), err=True)


def _validation_message(error: Any) -> str:
    """요청 모델 검증 오류 문구. 검증 함수가 던진 ValueError 는 pydantic 이 붙이는 'Value error, ' 를 뗀다."""
    if error.get('type') == 'value_error' and 'error' in error.get('ctx', {}):
        return str(error['ctx']['error'])
    return error['msg']


def _usage_hint() -> str:
    """사용법 오류(jibsa.cli.app.run)와 같은 '<명령> --help' 힌트. 명령 밖이면 일반 문구."""
    context = get_current_context(silent=True)
    if context is None:
        return '옵션 값을 확인하세요'
    return f"'{context.command_path} --help' 로 사용법을 확인하세요"


@contextmanager
def handle_errors(source: str) -> Generator[None, None, None]:
    """예외를 `{"error": {...}}` JSON 으로 stderr 에 쓰고 exit code 1 (입력 검증 실패는 2) 로 끝낸다.

    LLM 이 실패 원인을 읽고 다음 행동(재시도, 조건 수정)을 고를 수 있도록
    코드와 힌트를 함께 남긴다. 예상하지 못한 예외도 traceback 대신 INTERNAL_ERROR 로 쓴다.
    """
    try:
        yield
    except JibsaError as exc:
        # 다른 소스 때문에 난 에러(지역 조회를 맡은 직방의 요청 제한 등)는 details 의 source 가 이긴다
        emit_error(exc.code, exc.message, exc.hint, **{'source': source, **exc.details})
        # 조회 중에야 알 수 있는 입력 오류(오피스텔에 평형 조건 등)도 사용법 오류와 같은 exit code 2 로 맞춘다
        raise typer.Exit(code=2 if exc.code == 'INVALID_ARGUMENT' else 1)
    except ValidationError as exc:
        if not is_request_validation_error(exc):
            # 응답 모델 검증 실패는 소스 응답이 바뀐 것이다. 입력을 고쳐도 소용없다. 어느 필드인지 없으면 원인을 못 찾는다
            emit_error(
                'PARSE_ERROR',
                f'{exc.title} 검증 실패: ' + '; '.join(
                    f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()
                ),
                '비공식 API 응답 형식이 바뀌었을 수 있습니다. 다른 소스를 쓰세요',
                source=source,
            )
            raise typer.Exit(code=1)
        emit_error(
            'INVALID_ARGUMENT',
            '; '.join(_validation_message(error) for error in exc.errors()),
            _usage_hint(),
            source=source,
        )
        # 사용법 오류와 같은 종류라 exit code 도 2 로 맞춘다.
        raise typer.Exit(code=2)
    except HTTPStatusError as exc:
        status = exc.response.status_code
        code = {
            404: 'NOT_FOUND',
            429: 'RATE_LIMITED',
        }.get(status, 'UPSTREAM_ERROR')
        # 요청 제한이 켜져 있으면(CLI 는 늘) 429 는 응답 훅이 쿨다운을 걸고 RateLimitedError 로 바꿔 여기 오지 않는다.
        # 제한을 끈 정책(RateLimitPolicy(enabled=False))만 여기 오고, 그때는 쿨다운을 걸지 않으므로 막아 두었다고 하지 않는다
        hint = {
            404: 'ID 가 맞는지, 매물이 내려가지 않았는지 확인하세요',
            429: (
                '네이버 봇 차단입니다. 몇 분 기다리고, 그사이 다른 소스를 쓰세요'
                if source == 'naver'
                else '요청이 너무 잦습니다. 잠시 후 다시 시도하세요'
            ),
        }.get(status, '비공식 API 라 스펙이 바뀌었을 수 있습니다')
        emit_error(code, str(exc), hint, source=source, status=status)
        raise typer.Exit(code=1)
    except HTTPError as exc:
        emit_error(
            'NETWORK_ERROR',
            f'{type(exc).__name__}: {exc}',
            '네트워크 상태를 확인하고 다시 시도하세요',
            source=source,
        )
        raise typer.Exit(code=1)
    except ValueError as exc:
        # JSON 이 아닌 응답(차단 페이지 등)의 JSONDecodeError, 당근 RelayStoreNotFoundError·RelayRecordNotFoundError 포함.
        # LookupError(KeyError·IndexError)는 jibsa 자체 버그라 INTERNAL_ERROR 로 보낸다. 응답 모양 때문에 인덱스가 어긋날
        # 수 있는 값은 응답 모델에서 막는다 (직방 경계 꼭짓점 `GeoJsonPoint`)
        emit_error(
            'PARSE_ERROR',
            f'{type(exc).__name__}: {exc}',
            '응답이 예상한 형식이 아닙니다. 차단 페이지이거나 구조가 바뀌었을 수 있으니 다른 소스를 쓰세요',
            source=source,
        )
        raise typer.Exit(code=1)
    except (ClickException, typer.Exit):
        # 사용법 오류와 정상 종료는 jibsa.cli.app.run 이 처리한다
        raise
    except BrokenPipeError:
        # 출력을 받는 쪽(`| head` 등)이 먼저 닫았다. jibsa 오류가 아니라 INTERNAL_ERROR 로 내지 않는다. Typer 가 EPIPE 를
        # 받아 stdout 을 감싸고 exit 1 로 끝낸다 (잡으면 에러 JSON 과 'Exception ignored ... BrokenPipeError' 가 함께 나왔다)
        raise
    except Exception as exc:
        emit_error(
            'INTERNAL_ERROR',
            f'{type(exc).__name__}: {exc}',
            'jibsa 내부 오류입니다. 다른 소스를 쓰거나 jibsa --verbose <명령> 처럼 jibsa 바로 뒤에 --verbose 를 붙여 다시 실행해 보세요',
            source=source,
        )
        raise typer.Exit(code=1)


class UsageHints(NamedTuple):
    """다른 소스의 옵션·값을 옮겨 써 틀린 사용법에, 이 명령에서 주는 법을 알리는 표. 값을 바꿔 받지는 않는다.

    같은 조건이 소스마다 옵션·값이 달라(직방 `--condition 반려동물`, 당근 `--option 반려동물가능`) 다른 소스 명령을
    옮겨 쓰다 틀리기 쉽다. 목록 옵션의 틀린 값은 `split_csv` 가, 없는 옵션·숫자로 못 바꾸는 값은 `jibsa.cli.app.run` 이
    이 표로 찾는다. 안내는 옵션(`--condition 반려동물`), 다른 명령(`jibsa zigbang search listings apt`), 그 조건이
    이 명령에 없다는 문장 중 하나다. 뜻이 조금 다른 조건(네이버 `탑층` 과 직방 `옥탑방`)은 넣지 않는다.

    Attributes:
        by_value: 옵션과 상관없이 값만으로 정해지는 안내 (`'반려동물가능': '--condition 반려동물'`). 이 명령 옵션의 값도
            넣어, 없는 옵션에 준 값(`--facility 엘리베이터`)을 맞는 옵션으로 안내한다.
        by_option_value: 옵션마다 뜻이 다른 값 (`'--room': {'2': '--room 투룸'}`). `by_value` 보다 먼저 본다.
        by_option: 이 명령에 없는 옵션의 안내 (`'--move-in-now': '--condition 즉시입주'`). 값으로 못 정할 때 쓴다.
    """

    by_value: Mapping[str, str] = {}
    by_option_value: Mapping[str, Mapping[str, str]] = {}
    by_option: Mapping[str, str] = {}

    def hint(self, option: str, value: str | None) -> str | None:
        """`option` 에 `value`(쉼표로 여럿)를 줘 틀렸을 때의 힌트. 표에 없으면 None."""
        option_values = self.by_option_value.get(option, {})
        parts = [part.strip() for part in (value or '').split(',') if part.strip()]
        usages = list(dict.fromkeys(
            usage for part in parts if (usage := option_values.get(part) or self.by_value.get(part))
        ))
        if not usages and option in self.by_option:
            usages = [self.by_option[option]]
        if not usages:
            return None
        if all(usage.startswith('-') for usage in usages):
            # 여러 값이 각각 다른 옵션이면 이어 붙여 그대로 쓸 수 있는 옵션 줄로 준다
            return f"이 명령에서는 이렇게 주세요: {' '.join(usages)}"
        return ' / '.join(
            f'이 명령에서는 이렇게 주세요: {usage}' if usage.startswith('-')
            else f'{usage} 로 찾으세요' if usage.startswith('jibsa ')
            else usage
            for usage in usages
        )


def split_csv(
    values: list[str] | None,
    allowed: tuple[ChoiceT, ...],
    option: str,
    hints: UsageHints | None = None,
) -> list[ChoiceT]:
    """`-t 원룸 -t 빌라` 와 `-t 원룸,빌라` 를 모두 받아 검증된 목록으로 만든다. 값의 타입은 `allowed` 를 따른다.

    허용 밖의 값이 `hints` 에 있으면 이 명령에서 주는 법을 에러 힌트로 알린다 (`UsageHints`). 값을 바꿔 받지는 않는다.
    """
    result: list[ChoiceT] = []
    for value in values or []:
        for part in value.split(','):
            part = part.strip()
            if not part:
                continue
            if part not in allowed:
                message = f"허용되지 않는 값입니다: '{part}'. 가능한 값: {', '.join(allowed)}"
                # 틀린 값 하나만 본다. 쉼표로 함께 준 맞는 값까지 다른 옵션으로 안내하지 않게
                hint = hints.hint(option, part) if hints else None
                if hint:
                    raise HintedBadParameter(message, option, hint)
                raise typer.BadParameter(message, param_hint=option)
            if part not in result:
                result.append(part)
    return result


def _number_text(value: float) -> str:
    # 면적처럼 소수인 값만 줄여 쓴다. 금액(int)에 :g 를 쓰면 1000000 이 1e+06 이 된다
    return f'{value:g}' if isinstance(value, float) else str(value)


def require_finite(option: str, value: float | None) -> None:
    """유한하지 않은 숫자(inf·nan)를 거절한다. typer 의 min·max 검사는 nan 을 통과시킨다."""
    if value is not None and not isfinite(value):
        raise typer.BadParameter('유한한 숫자를 주세요 (inf·nan 은 받지 않습니다)', param_hint=option)


def validate_ranges(*ranges: tuple[str, float | None, float | None]) -> None:
    """`(이름, 하한, 상한)` 마다 유한하지 않은 값과 --이름-min 이 --이름-max 보다 큰 범위를 조회 전에 거절한다.

    세 소스가 같은 입력에 같은 오류(INVALID_ARGUMENT)를 내도록 여기 한 곳에서 검사한다. inf 는 typer 의 min=0 을
    통과해 서버로 나가 400 을 받고, nan 은 요청 모델의 영어 메시지로 끝났다 (2026-10-11 실측: 직방 `--area-min inf`
    → sizeMinM2=inf 400 → UPSTREAM_ERROR).
    """
    for name, low, high in ranges:
        for value in (low, high):
            require_finite(f'--{name}-min / --{name}-max', value)
        if low is not None and high is not None and low > high:
            raise typer.BadParameter(
                f'--{name}-min({_number_text(low)}) 이 --{name}-max({_number_text(high)}) 보다 큽니다',
                param_hint=f'--{name}-min',
            )


def infer_trade_types(
    trade_types: list[TradeT],
    *,
    rent: bool = False,
    price: bool = False,
    deposit: bool = False,
    allowed: tuple[str, ...] | None = None,
) -> tuple[list[TradeT], list[str]]:
    """`--trade` 없이 월세·매매가 조건만 주면 그 조건이 뜻하는 거래 유형으로 좁힌다.

    가격 조건은 그 금액이 있는 매물에만 걸리므로, 월세 상한만 주면 월세가 없는 매매·전세가
    그대로 통과한다. "월세 50 이하" 를 `--rent-max 50` 으로만 옮겨도 월세만 나오도록 한다.
    보증금 조건만 주면 보증금이 없는 매매가 통과하므로 보증금이 있는 전세·월세·단기임대로 좁힌다.
    매매가와 보증금을 함께 주면 어느 쪽인지 알 수 없어 좁히지 않는다.

    `--trade` 를 줬는데 가격 조건이 걸릴 거래 유형이 하나도 없으면(전세 + 월세 상한 등) 사용법 오류로
    막는다. 세 소스 모두 서버가 그 조건을 조용히 무시해 조건 없는 결과가 나온다 (2026-10-10 실측).
    일부만 겹치면(전세·월세 + 월세 상한) 서버가 해당 거래에만 걸어 그대로 둔다.

    Args:
        trade_types: 사용자가 준 거래 유형. 있으면 그대로 쓴다.
        rent: 월세 조건(하한·상한)을 줬는지.
        price: 매매가 조건을 줬는지.
        deposit: 보증금 조건을 줬는지.
        allowed: 이 검색이 다루는 거래 유형. 주면 좁힌 결과와 안내에서 그 밖의 유형을 뺀다 (직방 아파트에는
            단기임대가 없다).

    Returns:
        tuple[list[str], list[str]]: 검색할 거래 유형과, 좁혔으면 결과에 붙일 안내.

    Raises:
        typer.BadParameter: 가격 조건이 `--trade` 의 어느 거래 유형에도 해당하지 않을 때.
    """
    if trade_types:
        for given, field, option in (
            (rent, 'rent_manwon', '--rent-min/--rent-max'),
            (price, 'price_manwon', '--price-min/--price-max'),
            (deposit, 'deposit_manwon', '--deposit-min/--deposit-max'),
        ):
            if given and all(field in NOT_APPLICABLE_PRICE_FIELDS.get(trade, frozenset()) for trade in trade_types):
                # 이 검색이 다루지 않는 거래 유형은 권하지 않는다 (직방 아파트에 '단기임대에만 쓰세요' 라고 하던 문제)
                applicable = [
                    trade for trade, fields in NOT_APPLICABLE_PRICE_FIELDS.items()
                    if field not in fields and (allowed is None or trade in allowed)
                ]
                raise typer.BadParameter(
                    f"--trade {','.join(trade_types)} 에는 해당 금액이 없어 {option} 를 적용할 수 없습니다. "
                    f"이 조건은 {'·'.join(applicable)} 거래에만 쓰세요",
                    param_hint='--trade',
                )
        return trade_types, []
    if rent and price:
        inferred = ['매매', '월세']
    elif rent:
        inferred = ['월세']
    elif price and not deposit:
        inferred = ['매매']
    elif deposit and not price:
        inferred = ['전세', '월세', '단기임대']
    else:
        return trade_types, []
    if allowed is not None:
        inferred = [trade for trade in inferred if trade in allowed]
    narrowed = note(
        '거래',
        f"--trade 를 주지 않아 가격 조건에 맞춰 {'·'.join(inferred)}만 검색했습니다. "
        '다른 거래 유형도 보려면 --trade 로 지정하세요',
    )
    # 좁힌 값은 세 소스가 같이 쓰는 거래 유형 이름(매매·전세·월세·단기임대)이다
    return cast(list[TradeT], inferred), [narrowed]


class HintedUsageError(UsageError):
    """기본 힌트('--help 로 확인') 대신 정해 둔 힌트를 싣는 사용법 오류."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.hint = hint


class HintedBadParameter(typer.BadParameter):
    """`HintedUsageError` 처럼 정해 둔 힌트를 싣는 옵션 값 오류. 메시지는 'Invalid value for --옵션: …' 꼴이다."""

    def __init__(self, message: str, option: str, hint: str) -> None:
        super().__init__(message, param_hint=option)
        self.hint = hint


def require_korea(lat: float | None, lng: float | None) -> None:
    """--lat/--lng 가 하나만 왔거나 한국 밖이면 사용법 오류(INVALID_ARGUMENT, exit 2)로 막는다.

    하나만 주면 지역명으로만 검색되어 준 좌표가 조용히 무시되므로 둘 다 요구한다.
    """
    if (lat is None) != (lng is None):
        raise HintedUsageError(
            '--lat 과 --lng 는 함께 주어야 합니다',
            '좌표로 검색하려면 --lat 과 --lng 를 둘 다 주고, 아니면 둘 다 빼고 지역 이름으로 검색하세요',
        )
    if lat is None or lng is None or in_korea(lat, lng):
        return
    raise HintedUsageError(
        f'좌표 ({lat}, {lng}) 는 한국 밖입니다. jibsa 는 한국 매물만 조회합니다',
        '한국 안의 좌표를 주거나 지역 이름으로 검색하세요',
    )
