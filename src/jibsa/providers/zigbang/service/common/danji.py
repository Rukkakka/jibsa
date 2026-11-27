"""직방 단지 조회: 단지 정보를 받고, 없으면 NOT_FOUND 에러로 바꾼다."""

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangDanjisResponseModel


def complex_not_found(complex_id: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f"직방에서 단지를 찾을 수 없습니다: '{complex_id}'",
        hint='jibsa zigbang search locations <단지 이름> 으로 단지를 다시 찾아 결과의 complexes[].complex_id 를 그대로 주세요',
        details={'complex_id': complex_id},
    )


# 상태 코드 → 에러 변환은 엔드포인트마다 코드·에러가 달라(상세 404 → 만료 `unavailable_on_404`, 단지 404 → NOT_FOUND,
# 오피스텔 건물 400·404 → NOT_FOUND) 공통 컨텍스트 매니저로 묶지 않는다
def fetch_danji(client: ZigbangClient, complex_id: str, danji_id: int) -> ZigbangDanjisResponseModel:
    try:
        return client.run_request_danjis(ZigbangDanjisRequestParameterModel(danji_id=danji_id))
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise complex_not_found(complex_id) from None
        raise
