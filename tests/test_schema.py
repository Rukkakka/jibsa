import ast
import importlib
import pkgutil
from pathlib import Path

import pytest
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidatorFunctionWrapHandler,
    model_validator,
)

import jibsa
from jibsa.core.listing import null_items_note
from jibsa.core.schema import (
    ResponseModel,
    validate_dropping_nulls,
)

from typing import (
    Annotated,
    Any,
)


SOURCE = Path(jibsa.__file__).parent


def all_models() -> list[type[BaseModel]]:
    for module in pkgutil.walk_packages(jibsa.__path__, 'jibsa.'):
        importlib.import_module(module.name)
    found: list[type[BaseModel]] = []
    stack = [BaseModel]
    while stack:
        for model in stack.pop().__subclasses__():
            stack.append(model)
            if model.__module__.startswith('jibsa.'):
                found.append(model)
    return found


# --- pydantic 선언 (docs/development/code-style.md 4절) ---

def test_assignment_field_only_holds_default_factory() -> None:
    # 제약·설명·별칭은 Annotated 안, 단순 기본값은 `= 값` 이라 대입 위치의 Field() 에는 default_factory 만 남는다.
    # 별칭을 대입 위치에 두면 Pylance 가 생성자 인자를 별칭(camelCase)으로 보는데 ruff·mypy 는 잡지 못한다
    misplaced = []
    for path in sorted(SOURCE.rglob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == 'Field'
            ):
                continue
            if node.value.args or {keyword.arg for keyword in node.value.keywords} != {'default_factory'}:
                misplaced.append(f'{path.relative_to(SOURCE)}:{node.lineno}')
    assert misplaced == []



def test_defaults_are_not_inside_annotated() -> None:
    # Annotated 안 Field() 의 기본값은 검사기가 읽지 않아 필드를 필수로 본다. 런타임은 선택이라 둘이 어긋난다
    misplaced: set[str] = set()
    for path in sorted(SOURCE.rglob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'Annotated'):
                continue
            for call in ast.walk(node.slice):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == 'Field'
                    and (call.args or {keyword.arg for keyword in call.keywords} & {'default', 'default_factory'})
                ):
                    misplaced.add(f'{path.relative_to(SOURCE)}:{call.lineno}')
    assert sorted(misplaced) == []


def test_aliased_models_accept_field_names() -> None:
    # Annotated 안의 별칭은 검사기가 읽지 않아 생성자를 필드 이름으로 본다. 런타임도 필드 이름을 받아야 둘이 맞는다
    rejecting = [
        f'{model.__module__}.{model.__qualname__}'
        for model in all_models()
        if any(field.alias for field in model.model_fields.values())
        and not model.model_config.get('validate_by_name')
    ]
    assert rejecting == []


# --- 목록 안 null 원소 (core/schema.py validate_dropping_nulls, core/listing.py null_items_note) ---

def test_null_items_in_model_lists_are_dropped_and_counted() -> None:
    class Item(ResponseModel):
        name: Annotated[str, Field(description='이름')]

    class Base(ResponseModel):
        @model_validator(mode='wrap')
        @classmethod
        def drop_nulls(cls, data: Any, handler: ValidatorFunctionWrapHandler) -> Any:
            return validate_dropping_nulls(cls, data, handler)

    class Inner(Base):
        rows: Annotated[list[Item], Field(description='행', alias='rowList')] = []

    class Outer(Base):
        items: Annotated[list[Item], Field(description='항목')] = []
        maybe: Annotated[list[Item] | None, Field(description='없을 수 있는 목록')] = None
        numbers: Annotated[list[int], Field(description='숫자 목록')] = []
        inner: Annotated[Inner | None, Field(description='중첩 모델')] = None

    data = {'items': [{'name': 'a'}, None, {'name': 'b'}, None], 'inner': {'rowList': [None, {'name': 'c'}]}}
    outer = Outer.model_validate(data)
    assert [item.name for item in outer.items] == ['a', 'b']
    # 중첩 모델은 자기 칸만 센다. 바깥 모델의 합계에 안쪽 칸이 들어가지 않는다
    assert (outer.null_items('items'), outer.null_items('items', 'maybe'), outer.null_items()) == (2, 2, 2)
    assert outer.inner is not None
    assert [row.name for row in outer.inner.rows] == ['c']
    assert (outer.inner.null_items('rows'), outer.inner.null_items('items')) == (1, 0)
    # 입력 dict 는 제자리에서 바꾸지 않는다
    assert data['items'] == [{'name': 'a'}, None, {'name': 'b'}, None]

    # 칸 자체가 null 이면 그대로 모름이고, 뺄 것이 없으면 센 수 0 에 읽은 칸 집합도 그대로다
    assert Outer.model_validate({'maybe': None}).maybe is None
    clean = Outer.model_validate({'items': [{'name': 'a'}]})
    assert (clean.null_items(), clean.model_fields_set) == (0, {'items'})
    # 숫자 목록은 순서가 뜻일 수 있어 null 을 빼지 않고 지금처럼 검증 오류다
    with pytest.raises(ValidationError):
        Outer.model_validate({'numbers': [1, None, 3]})

    # 빼고 읽었다는 안내 글 (끝말은 매일 API 감시가 찾는 UPDATE_MAYBE_NEEDED)
    assert null_items_note('네이버 관리비 항목', 1, ('manage_cost_manwon', 'manage_cost_includes')) == (
        '[제외] 네이버 관리비 항목 목록에 빈 항목 1개가 와서 빼고 읽었습니다. '
        'manage_cost_manwon, manage_cost_includes 값은 알 수 없어 null 입니다. jibsa 업데이트가 필요할 수 있습니다'
    )
    assert null_items_note('직방 단지 매물', 2).endswith('빼고 읽었습니다. jibsa 업데이트가 필요할 수 있습니다')
