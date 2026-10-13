"""README 데모 녹화용 jibsa. CLI 는 그대로 돌리고 직방 응답만 `zigbang.json` 의 가상 매물로 바꿔 준다.

`demo.tape` 가 설치한 jibsa 의 Python 으로 이 파일을 실행한다 (`jibsa --version` 이 설치한 버전을 보여 주도록).
데모 명령(`zigbang search listings room 강남역`)이 보내는 요청만 흉내 내고, 그 밖의 요청은 404 로 끝낸다.
"""

import json
import sys
from pathlib import Path

import httpx

from jibsa.cli.app import main


FAKE = json.loads((Path(__file__).parent / 'zigbang.json').read_text(encoding='utf-8'))


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.url.host == 'account.zigbang.com':
        return httpx.Response(201, json=FAKE['token'])
    if path == '/v2/search':
        return httpx.Response(200, json=FAKE['search'])
    if path == '/house/property/v1/items/list':
        ids = json.loads(request.content)['itemIds']
        return httpx.Response(200, json={'items': [FAKE['summaries'][str(item_id)] for item_id in ids]})
    # 역 반경 매물 핀: /house/property/v1/items/subways/<역 ID>/<onerooms|officetels|villas>
    kind = path.rsplit('/', 1)[-1]
    if path.startswith('/house/property/v1/items/subways/') and kind in FAKE['pins']:
        return httpx.Response(200, json={'items': FAKE['pins'][kind]})
    return httpx.Response(404, json={'message': f'데모에 없는 요청: {request.method} {request.url}'})


_init = httpx.Client.__init__


def _init_with_fake_transport(self: httpx.Client, *args: object, **kwargs: object) -> None:
    kwargs['transport'] = httpx.MockTransport(handler)
    _init(self, *args, **kwargs)  # type: ignore[arg-type]


httpx.Client.__init__ = _init_with_fake_transport  # type: ignore[method-assign]

if __name__ == '__main__':
    sys.argv[0] = 'jibsa'
    main()
