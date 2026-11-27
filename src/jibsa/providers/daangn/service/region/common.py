"""당근 지역·역·대학·주소 해석이 함께 쓰는 에러와 좌표 확인."""

from jibsa.core.errors import RegionNotFoundError
from jibsa.providers.daangn.api.response.region.station import (
    DaangnSubwayStationPoiModel,
)
from jibsa.providers.daangn.api.response.region.university import DaangnSchoolPoiModel
from jibsa.providers.daangn.service.common.location import coordinate_point


class LocationMissingError(RegionNotFoundError):
    """웹 검색창이 보여 주는 후보(역·대학·주소)에 위치 정보가 없어 그 주변을 찾을 수 없을 때 (`REGION_NOT_FOUND`).

    웹은 그 후보를 보여 주지만 jibsa 는 위치가 있어야 주변 매물을 찾는다. 위치가 없는 후보 대신 다른 후보를 말없이 고르지 않고 이
    에러로 알린다 (`find_station`·`find_university`·`find_address`). 기본 message('지역을 찾지 못했습니다')는 후보는 있는데 위치만
    없는 이 경우에 맞지 않아 바꾼다.
    """

    def __init__(self, query: str, message: str, hint: str) -> None:
        super().__init__(query, hint=hint)
        self.message = message
        self.args = (message,)


def has_location(poi: DaangnSubwayStationPoiModel | DaangnSchoolPoiModel) -> bool:
    """역·대학 후보에 좌표가 있는지. 없으면 그 주변 매물을 찾을 수 없어 `--station`·`--university` 로 고를 수 없다."""
    return coordinate_point(poi.coordinate) is not None
