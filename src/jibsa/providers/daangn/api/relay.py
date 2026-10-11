import json
import re

from typing import Any


RELAY_STORE_PATTERN: re.Pattern[str] = re.compile(r'RELAY_STORE\s*=\s*"((?:\\.|[^"\\])*)"')
JSON_LD_PATTERN: re.Pattern[str] = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)

RelayStore = dict[str, dict[str, Any]]


# 두 예외는 api 층(소스 응답 그대로 옮기는 아래층)이라 JibsaError 가 아니라 ValueError 다. JibsaError 변환은 service 층에서
# 하고(references/architecture.md), api/ 아래 어떤 모듈도 JibsaError 를 쓰지 않는다. CLI 는 ValueError 를 PARSE_ERROR 로 낸다
class RelayStoreNotFoundError(ValueError):
    """HTML 에 `window.RELAY_STORE` 가 없을 때. 페이지 구조가 바뀌었다는 신호다."""


class RelayRecordNotFoundError(ValueError):
    """스토어에 찾는 레코드가 없을 때. 200 페이지인데 레코드가 없으면 구조가 바뀌었다는 신호다.

    `ValueError` 라 CLI 가 `PARSE_ERROR` 로 낸다. `LookupError` 로 던지면 jibsa 자체 버그의 KeyError·IndexError 와
    구별하지 못해 내부 오류까지 '응답 형식이 바뀜' 으로 안내하게 된다.
    """


def extract_relay_store(html: str) -> RelayStore:
    """SSR HTML 에 박힌 `window.RELAY_STORE` 를 꺼낸다.

    스토어는 JS 문자열로 이스케이프된 JSON 이라 두 번 디코드한다.

    Raises:
        RelayStoreNotFoundError: 스토어를 찾지 못했을 때.
    """
    match = RELAY_STORE_PATTERN.search(html)
    if match is None:
        raise RelayStoreNotFoundError('window.RELAY_STORE not found in HTML')
    return json.loads(json.loads(f'"{match.group(1)}"'))


def resolve(store: RelayStore, value: Any, depth: int = 4) -> Any:
    """`__ref` / `__refs` 참조를 실제 레코드로 바꿔 중첩 dict 로 만든다.

    Relay 정규화 스토어는 순환 참조(Region → parentRegion ...)가 있으므로
    `depth` 단계까지만 펼치고 그 아래 참조는 None 으로 둔다.
    """
    if isinstance(value, dict):
        if '__ref' in value:
            record = store.get(value['__ref'])
            if record is None or depth <= 0:
                return None
            return resolve(store, record, depth - 1)
        if '__refs' in value:
            if depth <= 0:
                return []
            return [
                resolve(store, store[ref], depth - 1)
                for ref in value['__refs']
                if ref in store
            ]
        return {
            key: resolve(store, item, depth)
            for key, item in value.items()
            if key != '__id'
        }
    if isinstance(value, list):
        return [resolve(store, item, depth) for item in value]
    return value


def records_of_type(store: RelayStore, typename: str) -> list[dict[str, Any]]:
    return [
        record
        for record in store.values()
        if isinstance(record, dict) and record.get('__typename') == typename
    ]


def root_field(store: RelayStore, prefix: str) -> Any:
    """`client:root` 에서 `prefix(` 로 시작하는 첫 필드 값을 꺼낸다.

    Relay 는 인자를 필드 키에 직렬화하므로(`articlesCount(input:{...})`)
    접두어로 찾는다.
    """
    root = store.get('client:root', {})
    for key, value in root.items():
        if key == prefix or key.startswith(f'{prefix}('):
            return value
    return None


def extract_json_ld(html: str) -> list[dict[str, Any]]:
    """`application/ld+json` 블록의 노드를 `@graph` 를 펼쳐 평탄한 목록으로 돌려준다."""
    nodes: list[dict[str, Any]] = []
    for block in JSON_LD_PATTERN.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in data.get('@graph', [data]) if isinstance(data, dict) else data:
            if isinstance(node, dict):
                nodes.append(node)
    return nodes
