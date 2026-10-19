import json
import re
from math import (
    inf,
    nan,
)

from typing import Any


# 당근 웹(TanStack Start)은 라우터 상태를 seroval 로 직렬화한 JS 식 `$_TSR.router=($R=>$R[0]={...})($R["tsr"])` 로 심고,
# Relay 정규화 스토어는 그 안의 `dehydratedData.relayRecords` 다 (2026-10-17 실측: 지도·상세·단지·동네 후기 페이지 모두.
# 그 전에는 JS 문자열로 이스케이프한 JSON `window.RELAY_STORE = "..."` 였다)
TSR_ROUTER_MARKER: str = '$_TSR.router=($R=>'
# seroval 이 데이터에 쓰는 문법만 읽는다: 문자열, `$R[n]=` 등록과 `$R[n]` 참조, 숫자, `!0`·`!1`(참·거짓), 이름(null 등), 기호.
# 무한·NaN 을 쓰는 `1/0`·`0/0` 은 읽지 않는다. 라우터 상태에 그런 값이 오지 않는다 (2026-10-18 실측: 역삼동 지도 페이지
# 라우터 상태에 `1/0`·`0/0`·`new` 모두 없음). 2026-10-18 리뷰 오탐 확인
SEROVAL_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    r'\s*(?:'
    r'(?P<string>"[^"\\]*(?:\\.[^"\\]*)*")'
    r'|\$R\[(?P<ref>\d+)\](?P<assign>=)?'
    r'|(?P<number>-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'
    r'|!(?P<flag>[01])'
    r'|(?P<name>[A-Za-z_$][\w$]*)'
    r'|(?P<punct>[{}\[\]:,])'
    r')',
    re.DOTALL,
)
JS_ESCAPE_PATTERN: re.Pattern[str] = re.compile(r'\\(?:x([0-9A-Fa-f]{2})|u\{([0-9A-Fa-f]+)\}|u([0-9A-Fa-f]{4})|(\r\n|.))', re.DOTALL)
JS_SIMPLE_ESCAPES: dict[str, str] = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', 'v': '\v', '0': '\0'}
JS_LINE_TERMINATORS: tuple[str, ...] = ('\n', '\r', '\r\n', '\u2028', '\u2029')
JS_CONSTANTS: dict[str, Any] = {'null': None, 'undefined': None, 'true': True, 'false': False, 'NaN': nan, 'Infinity': inf}
JSON_LD_PATTERN: re.Pattern[str] = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)

RelayStore = dict[str, dict[str, Any]]


# 두 예외는 api 층(소스 응답 그대로 옮기는 아래층)이라 JibsaError 가 아니라 ValueError 다. JibsaError 변환은 service 층에서
# 하고(references/architecture.md), api/ 아래 어떤 모듈도 JibsaError 를 쓰지 않는다. CLI 는 ValueError 를 PARSE_ERROR 로 낸다
class RelayStoreNotFoundError(ValueError):
    """HTML 에 Relay 스토어(라우터 상태의 `dehydratedData.relayRecords`)가 없거나 읽을 수 없을 때. 페이지 구조가 바뀌었다는 신호다."""


class RelayRecordNotFoundError(ValueError):
    """스토어에 찾는 레코드가 없을 때. 200 페이지인데 레코드가 없으면 구조가 바뀌었다는 신호다.

    `ValueError` 라 CLI 가 `PARSE_ERROR` 로 낸다. `LookupError` 로 던지면 jibsa 자체 버그의 KeyError·IndexError 와
    구별하지 못해 내부 오류까지 '응답 형식이 바뀜' 으로 안내하게 된다.
    """


def extract_relay_store(html: str) -> RelayStore:
    """SSR HTML 에 박힌 라우터 상태에서 Relay 스토어(`dehydratedData.relayRecords`)를 꺼낸다.

    라우터 상태는 JSON 이 아니라 seroval 의 JS 식이라 `_SerovalReader` 로 읽는다.

    Raises:
        RelayStoreNotFoundError: 라우터 상태나 스토어를 찾지 못했거나 읽을 수 없을 때.
    """
    start = html.find(TSR_ROUTER_MARKER)
    if start < 0:
        raise RelayStoreNotFoundError('TanStack router state ($_TSR.router) not found in HTML')
    state = _SerovalReader(html, start + len(TSR_ROUTER_MARKER)).value()
    dehydrated = state.get('dehydratedData') if isinstance(state, dict) else None
    records = dehydrated.get('relayRecords') if isinstance(dehydrated, dict) else None
    if not isinstance(records, dict):
        raise RelayStoreNotFoundError('dehydratedData.relayRecords not found in router state')
    return records


class _SerovalReader:
    """seroval 이 직렬화한 JS 식에서 값 하나를 읽는다.

    `$R[n]={...}` 로 등록한 값은 뒤에서 `$R[n]` 로 다시 가리킨다 (2026-10-17 실측: 지도 페이지의 피드 edge 들이 앞
    edge 의 `node` 객체를 `node:$R[1028]` 처럼 가리킨다). 객체·배열은 채우기 전에 등록해 안에서 자신을 가리켜도 읽는다.
    """

    def __init__(self, text: str, pos: int) -> None:
        self.text = text
        self.pos = pos
        self.refs: dict[int, Any] = {}

    def _next(self) -> re.Match[str]:
        match = SEROVAL_TOKEN_PATTERN.match(self.text, self.pos)
        if match is None:
            raise self._error('unexpected syntax')
        self.pos = match.end()
        return match

    def _error(self, reason: str) -> RelayStoreNotFoundError:
        return RelayStoreNotFoundError(f'cannot read router state: {reason} at {self.pos}')

    def value(self, match: re.Match[str] | None = None) -> Any:
        match = match or self._next()
        if (raw := match.group('string')) is not None:
            return _js_string(raw[1:-1])
        if (ref := match.group('ref')) is not None:
            index = int(ref)
            if match.group('assign'):
                return self._assign(index)
            if index not in self.refs:
                raise self._error(f'unknown reference $R[{index}]')
            return self.refs[index]
        if (number := match.group('number')) is not None:
            return float(number) if any(char in number for char in '.eE') else int(number)
        if (flag := match.group('flag')) is not None:
            # 줄인 참거짓: !0 은 true, !1 은 false
            return flag == '0'
        if (name := match.group('name')) is not None:
            if name == 'void':
                # `void 0` 은 undefined
                self.value()
                return None
            if name not in JS_CONSTANTS:
                raise self._error(f'unsupported name {name}')
            return JS_CONSTANTS[name]
        punct = match.group('punct')
        if punct == '{':
            return self._object({})
        if punct == '[':
            return self._array([])
        raise self._error(f'unexpected {punct!r}')

    def _assign(self, index: int) -> Any:
        match = self._next()
        punct = match.group('punct')
        if punct == '{':
            target: dict[str, Any] = {}
            self.refs[index] = target
            return self._object(target)
        if punct == '[':
            items: list[Any] = []
            self.refs[index] = items
            return self._array(items)
        self.refs[index] = value = self.value(match)
        return value

    def _object(self, target: dict[str, Any]) -> dict[str, Any]:
        match = self._next()
        while match.group('punct') != '}':
            raw = match.group('string')
            # 키는 따옴표 없는 이름·숫자(`608:`)로도 온다. JS 처럼 문자열 키로 둔다
            key = _js_string(raw[1:-1]) if raw is not None else match.group('name') or match.group('number')
            if key is None or self._next().group('punct') != ':':
                raise self._error('bad object key')
            target[key] = self.value()
            match = self._next()
            if match.group('punct') == ',':
                match = self._next()
            elif match.group('punct') != '}':
                raise self._error('expected , or }')
        return target

    def _array(self, target: list[Any]) -> list[Any]:
        match = self._next()
        while match.group('punct') != ']':
            if match.group('punct') == ',':
                # 희소 배열의 빈 칸 (`[,1]`)
                target.append(None)
                match = self._next()
                continue
            target.append(self.value(match))
            match = self._next()
            if match.group('punct') == ',':
                match = self._next()
            elif match.group('punct') != ']':
                raise self._error('expected , or ]')
        return target


def _js_string(raw: str) -> str:
    """JS 문자열 리터럴의 따옴표 안쪽을 실제 문자열로 바꾼다."""
    if '\\' not in raw:
        return raw
    text = JS_ESCAPE_PATTERN.sub(_js_escape, raw)
    if any('\ud800' <= char <= '\udfff' for char in text):
        # 서로게이트 쌍으로 이스케이프한 글자(`😀` 같은 이모지)를 한 글자로 합친다. 짝 없는 서로게이트면 decode 가 실패하지만,
        # seroval 은 한글 같은 글자를 `\u` 로 이스케이프하지 않고 글자 그대로 실어 그런 이스케이프가 오지 않는다 (2026-10-18 실측:
        # 역삼동 지도 페이지 라우터 상태에 `\u` 이스케이프 0개). 2026-10-18 리뷰 오탐 확인
        text = text.encode('utf-16', 'surrogatepass').decode('utf-16')
    return text


def _js_escape(match: re.Match[str]) -> str:
    code = match.group(1) or match.group(2) or match.group(3)
    if code is not None:
        return chr(int(code, 16))
    char = match.group(4)
    if char in JS_LINE_TERMINATORS:
        # 줄 끝 앞의 역슬래시는 줄 이음이라 글자가 아니다
        return ''
    return JS_SIMPLE_ESCAPES.get(char, char)


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
