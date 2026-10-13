import json
import sys
from collections.abc import Iterator
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
    NOTICE,
)
from jibsa.core.schema import is_request_validation_error

from typing import (
    Any,
    TypeVar,
    cast,
)


ChoiceT = TypeVar('ChoiceT', bound=str)
TradeT = TypeVar('TradeT', bound=str)


def _dumps(data: Any, pretty: bool | None) -> str:
    if pretty is None:
        pretty = sys.stdout.isatty()
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (',', ':'),
    )


def emit(
    data: BaseModel | list[BaseModel] | dict[str, Any],
    pretty: bool | None = None,
    notice: bool = False,
    notes: list[str] | None = None,
) -> None:
    """결과를 JSON 으로 stdout 에 쓴다.

    값을 모르는 필드는 `null` 로 남기고, 매물에 해당 없는 필드는 `Listing` 이
    키째 뺀다 (`Listing.not_applicable_fields`).

    `notice` 가 True 면 맨 앞에 "확인·문의·계약은 원 사이트에서" 안내를 붙인다.
    매물을 내보내는 명령은 모두 켠다. `notes` 가 있으면 그 바로 아래에 붙이고,
    없으면 키를 뺀다 (모호하거나 넓은 지역 안내 등).
    """
    if isinstance(data, BaseModel):
        payload: Any = data.model_dump(mode='json')
    elif isinstance(data, list):
        payload = [item.model_dump(mode='json') for item in data]
    else:
        payload = data
    if not isinstance(payload, dict) and (notice or notes):
        payload = {'items': payload}
    if notes:
        payload = {'notes': notes, **payload}
    if notice:
        payload = {'notice': NOTICE, **payload}
    typer.echo(_dumps(payload, pretty))


def emit_error(code: str, message: str, hint: str | None = None, **extra: Any) -> None:
    """`{"error": {...}}` 를 stderr 에 쓴다. 터미널이면 들여쓰기, 아니면 한 줄."""
    error: dict[str, Any] = {'code': code, 'message': message}
    if hint:
        error['hint'] = hint
    error.update({key: value for key, value in extra.items() if value is not None})
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
def handle_errors(source: str) -> Iterator[None]:
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
            # 응답 모델 검증 실패는 소스 응답이 바뀐 것이다. 입력을 고쳐도 소용없다.
            emit_error(
                'PARSE_ERROR',
                f'{exc.title} 검증 실패: ' + '; '.join(error['msg'] for error in exc.errors()),
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
    except Exception as exc:
        emit_error(
            'INTERNAL_ERROR',
            f'{type(exc).__name__}: {exc}',
            'jibsa 내부 오류입니다. 다른 소스를 쓰거나 jibsa --verbose <명령> 처럼 jibsa 바로 뒤에 --verbose 를 붙여 다시 실행해 보세요',
            source=source,
        )
        raise typer.Exit(code=1)


def split_csv(values: list[str] | None, allowed: tuple[ChoiceT, ...], option: str) -> list[ChoiceT]:
    """`-t 원룸 -t 빌라` 와 `-t 원룸,빌라` 를 모두 받아 검증된 목록으로 만든다. 값의 타입은 `allowed` 를 따른다."""
    result: list[ChoiceT] = []
    for value in values or []:
        for part in value.split(','):
            part = part.strip()
            if not part:
                continue
            if part not in allowed:
                raise typer.BadParameter(
                    f"허용되지 않는 값입니다: '{part}'. 가능한 값: {', '.join(allowed)}",
                    param_hint=option,
                )
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
                applicable = [trade for trade, fields in NOT_APPLICABLE_PRICE_FIELDS.items() if field not in fields]
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
    note = (
        f"--trade 를 주지 않아 가격 조건에 맞춰 {'·'.join(inferred)}만 검색했습니다. "
        '다른 거래 유형도 보려면 --trade 로 지정하세요'
    )
    # 좁힌 값은 세 소스가 같이 쓰는 거래 유형 이름(매매·전세·월세·단기임대)이다
    return cast(list[TradeT], inferred), [note]


class HintedUsageError(UsageError):
    """기본 힌트('--help 로 확인') 대신 정해 둔 힌트를 싣는 사용법 오류."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
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
