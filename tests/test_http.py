import pytest
from httpx import (
    HTTPStatusError,
    Request,
    Response,
)

from jibsa.core.http import raise_for_status


# --- error body -------------------------------------------------------------

@pytest.mark.parametrize(
    'body',
    [
        '<html><script>window.__S={"accessToken":"SECRET","x":1}</script></html>',
        '<html><script>var s = "{\\"token\\":\\"SECRET\\"}"</script></html>',
        '<html><script>var s = "\\\\\\"token\\\\\\":\\\\\\"SECRET\\\\\\""</script></html>',
        '{"data": "{\\"token\\": \\"SECRET\\"}"}',
        '<p>"token":"ab\\/SECRET"</p>',
        "{'api_key': 'SECRET'}",
        '<p>"password":"correct horse SECRET"</p>',
        'error token=SECRET here',
        'token=["SECRET"]',
        '<p>"token":["A","SECRET"]</p>',
        '{token:{"v":"SECRET"}}',
        'Authorization: Bearer SECRET',
        'Authorization: KakaoAK SECRET',
        'Cookie: a=1; b=2; SESSION=SECRET',
        '<p>"cookie":"NNB=a; JSESSIONID=SECRET"</p>',
    ],
)
def test_error_body_hides_secret_values(body: str) -> None:
    # 에러 message 에 싣는 응답 본문은 키·값을 감싼 따옴표 모양과 상관없이 비밀 값을 가린다
    response = Response(500, text=body, request=Request('GET', 'https://example.invalid/x'))
    with pytest.raises(HTTPStatusError) as caught:
        raise_for_status(response)
    assert 'SECRET' not in str(caught.value)
