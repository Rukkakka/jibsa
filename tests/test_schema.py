import ast
import importlib
import pkgutil
from pathlib import Path

from pydantic import BaseModel

import jibsa


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


# --- pydantic 선언 (references/code-style.md 4절) ---

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


def test_aliased_models_accept_field_names() -> None:
    # Annotated 안의 별칭은 검사기가 읽지 않아 생성자를 필드 이름으로 본다. 런타임도 필드 이름을 받아야 둘이 맞는다
    rejecting = [
        f'{model.__module__}.{model.__qualname__}'
        for model in all_models()
        if any(field.alias for field in model.model_fields.values())
        and not model.model_config.get('validate_by_name')
    ]
    assert rejecting == []
