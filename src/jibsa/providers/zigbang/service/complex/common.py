"""아파트 단지 기능(complex)의 정보·단지 매물·시세 추이가 같이 쓰는 것: 직방이 단지끼리 이어 주는 관련 단지, 오피스텔 건물 조회, 세대수 문구."""

from httpx import HTTPStatusError

from jibsa.core.listing import (
    join_address,
    normalize_address,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.complex.base import (
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangRelatedDanjiModel
from jibsa.providers.zigbang.api.response.complex.base import (
    ZigbangItemsOfficetelsBuildingV1ResponseModel,
)
from jibsa.providers.zigbang.service.common.danji import complex_not_found
from jibsa.providers.zigbang.service.common.ids import apt_complex_id
from jibsa.providers.zigbang.service.complex.constants import HOUSEHOLD_TEXT_PATTERN
from jibsa.providers.zigbang.service.complex.models import ZigbangRelatedComplex


def related_complex_of(item: ZigbangRelatedDanjiModel) -> ZigbangRelatedComplex:
    """직방의 관련 단지 하나를 결과 한 줄로. 세대수 문구('6,864세대')는 정수로, 시·군·구·동은 빈 값 없이 이어 주소로 낸다."""
    return ZigbangRelatedComplex(
        complex_id=apt_complex_id(item.id) if item.id is not None else None,
        name=item.name,
        household_count=household_count(item.household),
        address=normalize_address(join_address(item.local1, item.local2, item.local3)),
    )


def fetch_building(
    client: ZigbangClient,
    complex_id: str,
    parameter: ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
) -> ZigbangItemsOfficetelsBuildingV1ResponseModel:
    try:
        return client.run_request_items_officetels_building_v1(parameter)
    except HTTPStatusError as exc:
        # 없는 건물이면 404 가 아니라 400 ("오피스텔 건물을 찾을 수 없습니다") 이다. 필터 값 오류도 400 이지만 요청 모델
        # Literal·ge=0 이 서버 허용값과 같아 보내기 전에 막히고, 범위 역전 같은 조합은 200 빈 목록이다 (2026-10-11 실측)
        if exc.response.status_code in (400, 404):
            raise complex_not_found(complex_id) from None
        raise


def household_count(text: str | None) -> int | None:
    """세대수 문구('1,161세대')를 정수로. 읽지 못하면 None."""
    match = HOUSEHOLD_TEXT_PATTERN.fullmatch((text or '').strip())
    return int(match.group(1).replace(',', '')) if match else None
