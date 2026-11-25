from collections.abc import Iterable
from functools import cache
from types import UnionType

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    RootModel,
    ValidationError,
    ValidatorFunctionWrapHandler,
)

from typing import (
    Annotated,
    Any,
    Union,
    get_args,
    get_origin,
)


# 명령 하나가 도는 동안 응답에서 뺀 빈 항목(null 원소)의 합. CLI 는 한 프로세스가 명령 하나를 돌려 모듈 변수 하나로 센다.
# 테스트처럼 한 프로세스에서 명령을 여러 번 돌리면 명령 시작에 `reset_null_item_tally` 로 0 으로 돌린다
_null_item_tally: int = 0


def reset_null_item_tally() -> None:
    """뺀 빈 항목의 합을 0 으로 돌린다. 명령이 시작할 때 부른다 (`cli.output.handle_errors`)."""
    global _null_item_tally
    _null_item_tally = 0


def add_null_item_tally(count: int) -> None:
    """응답에서 빈 항목을 `count` 개 빼고 읽었다고 합에 더한다. `validate_dropping_nulls` 와 소스의 루트 목록 모델이 부른다."""
    global _null_item_tally
    _null_item_tally += count


def null_item_tally() -> int:
    """이 명령이 응답에서 뺀 빈 항목의 합. 어느 칸에서 빼 어디에 쓰이는지와 상관없이 센다.

    `cli.output.emit` 이 0 보다 크면 공통 안내를 붙인다. 소스가 따로 `null_items_note` 를 붙인 자리와 보여 주기만 하는 목록에서
    뺀 자리가 모두 들어 있어, 조용히 빼는 자리가 없게 한다.
    """
    return _null_item_tally


class RequestModel(BaseModel):
    """Base request model with strict field validation."""
    model_config = ConfigDict(
        validate_by_name=True,
        extra='forbid',
    )


class ResponseModel(BaseModel):
    """Base response model allowing additional fields from APIs.

    비공식 API 는 예고 없이 필드를 추가하므로 모르는 필드는 버리지 않고 보존한다.
    """
    model_config = ConfigDict(
        validate_by_name=True,
        extra='allow',
    )

    # 객체 목록 칸 안에 섞여 와서 뺀 null 원소의 수 (파이썬 필드 이름 -> 수). 뺀 것이 없으면 빈 dict (`validate_dropping_nulls`)
    _null_item_counts: dict[str, int] = PrivateAttr(default_factory=dict)

    def null_items(self, *names: str) -> int:
        """객체 목록 칸에서 null 원소를 빼고 읽은 수. 준 칸들(파이썬 필드 이름, alias 아님)의 합이고, 칸을 주지 않으면 이 모델의 모든 칸의 합이다.

        중첩 모델은 각자 자기 칸만 센다. 바깥 모델의 `null_items` 는 안쪽 모델이 뺀 수를 더하지 않는다.
        서비스가 그 목록으로 개수·합계를 계산하거나 서버가 세는 자리(offset 등)를 목록 길이로 세는 곳에서, 뺀 수가 있으면
        틀린 값을 완전한 값처럼 내지 않게 하는 데 쓴다.
        """
        if not names:
            return sum(self._null_item_counts.values())
        return sum(self._null_item_counts.get(name, 0) for name in names)


def drop_null_lists(model: type[BaseModel], data: Any) -> Any:
    """기본값이 목록인 칸에 온 null 을 키가 없는 것으로 지운다. 소스의 기반 응답 모델이 wrap 검증기에서 `validate_dropping_nulls` 로 부른다.

    서버가 비워 줄 수 있는 목록 칸 하나 때문에 조회 전체가 PARSE_ERROR 로 끝나지 않게 한다. 키가 없을 때와 같아서 기본값 [] 칸은
    빈 목록이 되고, 키가 왔는지(`model_fields_set`)로 모름을 가르는 칸은 모름이 된다. `| None` 칸은 기본값이 목록이어도
    건드리지 않는다 (null 이 모름이라 서비스가 갈라 읽는다. 예: 다방 단지 학교·어린이집, 네이버 재개발 역·지구). 쓸지는 소스마다 정한다 (소스 API 는 따로 바뀌어, 한 소스가 null 에 다른 뜻을 실으면 그 소스만 뺀다).
    객체 목록 안의 null 원소는 `drop_null_items` 가 뺀다.
    """
    if not isinstance(data, dict):
        return data
    keys = {
        key
        for name, field in model.model_fields.items()
        if (isinstance(field.default, list) or field.default_factory is list)
        and type(None) not in get_args(field.annotation)
        for key in (field.alias, name) if key is not None
    }
    return {key: value for key, value in data.items() if value is not None or key not in keys}


def _model_list_item(annotation: Any) -> type[BaseModel] | None:
    """칸 자료형이 `list[모델]` 이면 그 모델 (`list[모델] | None`·`Annotated` 는 벗긴다). 아니면 None.

    원소가 `모델 | None` 처럼 null 을 허용하면 null 원소에 뜻을 둔 칸이라 None 이다. `RootModel` 도 대상이 아니다.
    """
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if get_origin(annotation) in (Union, UnionType):
        rest = [arg for arg in get_args(annotation) if arg is not type(None)]
        return _model_list_item(rest[0]) if len(rest) == 1 else None
    if get_origin(annotation) is not list:
        return None
    item = get_args(annotation)[0]
    while get_origin(item) is Annotated:
        item = get_args(item)[0]
    if isinstance(item, type) and issubclass(item, BaseModel) and not issubclass(item, RootModel):
        return item
    return None


@cache
def _model_list_fields(model: type[BaseModel]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """모델의 객체 목록 칸마다 (파이썬 필드 이름, 데이터에서 찾을 키: alias 와 이름). 모든 인스턴스 검증이 부르므로 모델마다 한 번만 만든다."""
    return tuple(
        (name, tuple(dict.fromkeys(key for key in (field.alias, name) if key is not None)))
        for name, field in model.model_fields.items()
        if _model_list_item(field.annotation) is not None
    )


def drop_null_items(model: type[BaseModel], data: Any) -> tuple[Any, dict[str, int]]:
    """객체 목록(`list[모델]`) 칸 안에 섞여 온 null 원소를 뺀 새 dict 와, 칸마다 뺀 수(파이썬 필드 이름 -> 수)를 돌려준다.

    서버가 `[{...}, null, {...}]` 를 주면 목록 하나 때문에 조회 전체가 PARSE_ERROR 로 끝나지 않게 한다. 숫자·글자·dict 목록과
    원소가 `모델 | None` 인 목록은 순서나 null 이 뜻일 수 있어 건드리지 않는다. 칸 자체가 null 이면 그대로 둔다 (그 칸의 null 은
    `drop_null_lists` 와 모델 선언이 다룬다). `data` 는 제자리에서 바꾸지 않는다. dict 가 아니면 `(data, {})` 이다.
    뺀 수를 모델 인스턴스에 남기는 것은 `validate_dropping_nulls` 다.
    """
    if not isinstance(data, dict) or issubclass(model, RootModel):
        return data, {}
    result = dict(data)
    counts: dict[str, int] = {}
    for name, keys in _model_list_fields(model):
        for key in keys:
            value = result.get(key)
            if not isinstance(value, list) or None not in value:
                continue
            kept = [item for item in value if item is not None]
            result[key] = kept
            counts.setdefault(name, len(value) - len(kept))
    return result, counts


def validate_dropping_nulls(model: type[BaseModel], data: Any, handler: ValidatorFunctionWrapHandler) -> Any:
    """목록 칸의 null(`drop_null_lists`)과 객체 목록 안의 null 원소(`drop_null_items`)를 뺀 뒤 검증하고, 뺀 수를 인스턴스에 남긴다.

    소스의 기반 응답 모델이 `model_validator(mode='wrap')` 에서 부른다. 뺀 수는 `ResponseModel.null_items` 로 읽고,
    명령 전체의 합에도 더한다 (`null_item_tally`).
    `data` 가 dict 가 아니면 (이미 모델 인스턴스 등) 그대로 검증한다.
    """
    if not isinstance(data, dict):
        return handler(data)
    data, counts = drop_null_items(model, drop_null_lists(model, data))
    result = handler(data)
    if dropped := sum(counts.values()):
        # 중첩 모델도 각자 이 함수를 지나므로 따로 세지 않아도 모두 더해진다
        add_null_item_tally(dropped)
    if counts and isinstance(result, ResponseModel):
        result._null_item_counts = counts
    return result


def drop_unset_fields(model: BaseModel, data: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    """`fields` 중 모델을 만들 때 넘기지 않은 칸(`model_fields_set` 에 없는 칸)을 뺀 새 dict.

    직렬화 결과 `data` 에서 해당 없음을 키 없음으로 낸다. 넘긴 값이 None 이면 키는 남고 null(모름)이다.
    `fields` 밖의 칸은 넘겼는지와 상관없이 남긴다. `data` 는 제자리에서 바꾸지 않는다.
    """
    names = frozenset(fields)
    return {key: value for key, value in data.items() if key not in names or key in model.model_fields_set}


def is_request_validation_error(exc: ValidationError) -> bool:
    """요청 모델(`RequestModel`)을 만들다 난 검증 오류인지. 즉 사용자 입력이 잘못된 경우.

    응답 모델이나 `Listing` 검증 오류는 소스 응답이 예상과 달라진 것이라 입력 오류가 아니다.
    `ValidationError.title` 은 검증한 모델 클래스 이름이다.

    응답 값으로 요청 모델을 만들다 난 오류도 여기서는 입력 오류로 보인다. 이 구분을 여기서 바꾸지 않고, 응답 값이
    실제로 형식에서 벗어나는 곳만 그 자리에서 다른 에러로 바꾼다 (네이버 매물 유형). 실측으로 벗어나지
    않는 값은 막지 않고 그 자리에 근거를 적는다 (당근 `resolve_regions` 의 name1, 2026-10-11 리뷰 확인).
    service 경계 한 곳에서 바꾸지 않는 것은, 같은 요청 모델에 사용자 입력과 응답 값이 함께 들어가 오류만 보고는 어느
    쪽 값인지 알 수 없고 그 값을 넣는 자리만 알기 때문이다 (2026-10-12 리뷰에서 한 곳으로 모으자는 제안을 검토하고 유지).
    새 엔드포인트의 규칙은 docs/development/provider-conventions.md '요청·응답 모델' 에 있다.
    """
    stack: list[type[BaseModel]] = [RequestModel]
    while stack:
        model = stack.pop()
        if model.__name__ == exc.title:
            return True
        stack.extend(model.__subclasses__())
    return False
