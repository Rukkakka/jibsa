"""당근 도로명 주소 해석."""

from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.region.address import (
    DaangnJusoAddressInputModel,
    DaangnSearchAddressRequestPayloadModel,
    DaangnUnitByAddressInputModel,
    DaangnUnitByAddressRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.region.base import DaangnQueryInputModel
from jibsa.providers.daangn.api.response.region.address import DaangnAddressModel
from jibsa.providers.daangn.service.common.location import coordinate_point
from jibsa.providers.daangn.service.common.response import unwrap_graphql
from jibsa.providers.daangn.service.region.common import LocationMissingError
from jibsa.providers.daangn.service.region.constants import (
    ADDRESS_CANDIDATES,
    AMBIGUOUS_CANDIDATES_SHOWN,
)
from jibsa.providers.daangn.service.region.models import DaangnAddress


def search_addresses(client: DaangnClient, query: str) -> tuple[list[DaangnAddressModel], bool]:
    """도로명 주소 글자로 주소 후보 첫 쪽과 다음 쪽이 있는지 (`searchAddress`, 요청 1회). 웹 검색창 주소 모드의 주소 칸이다.

    `unitByAddress` 에 보낼 건물 관리 번호·원본 도로명 주소가 없는 후보(실측에는 없었다)도 돌려준다 (`_address_usable`). 먼저 빼면
    후보가 하나뿐인 줄 알고 다른 후보를 말없이 고른다 (2026-11-19 리뷰). 모호한지와 정확히 같은 주소가 몇 곳인지는 이 후보까지
    센 수로 보고, 고른 하나가 쓸 수 없으면 에러다 (`find_address`, 2026-11-20 리뷰).
    """
    response = client.run_request_search_address(
        DaangnSearchAddressRequestPayloadModel(input=DaangnQueryInputModel(query=query), first=ADDRESS_CANDIDATES)
    )
    connection = unwrap_graphql(response, response.data.search_address if response.data else None, '주소 검색', conditions=False)
    candidates = [edge.node for edge in connection.edges if edge.node]
    return candidates, bool(connection.page_info and connection.page_info.has_next_page)


def _address_usable(candidate: DaangnAddressModel) -> bool:
    """`unitByAddress` 에 보낼 건물 관리 번호·원본 도로명 주소와 보여 줄 도로명 주소가 다 있는 후보인지."""
    return bool(candidate.road_address and candidate.bd_mgt_sn and candidate.original_road_address)


def find_address(client: DaangnClient, query: str) -> DaangnAddress:
    """도로명 주소를 웹 검색창 주소 모드처럼 후보 하나로 좁혀 좌표를 받는다 (`searchAddress` → `unitByAddress`, 요청 2회).

    웹은 주소 후보(도로명 주소, 아래에 지번 주소)를 보여 주고 사용자가 하나를 고르면 `unitByAddress` 로 좌표를 받아 지도를
    옮긴다 (MapShell `ys`·`_s`). jibsa 는 후보가 하나면 그것, 여럿이면 도로명·지번 주소가 입력과 정확히 같은 하나, 없으면
    `REGION_AMBIGUOUS` 로 도로명 주소 후보를 주어 그대로 다시 받는다. 좌표는 웹처럼 주소 좌표(`location`), 없으면 단지·건물
    좌표다.

    후보가 여럿인지(모호한지)와 정확히 같은 주소가 몇 곳인지는 쓸 수 없는 후보(건물 관리 번호·도로명 주소 없음)까지 센 수로 본다.
    쓸 수 있는 후보만 남기고 세면 웹에는 후보가 둘인데 남은 하나를 말없이 고른다. 정확히 같은 주소가 둘 이상이면 주소를 다시
    줘도 좁혀지지 않아 좌표를 권한다. 고른 하나(후보가 하나뿐일 때 그 후보 포함)가 쓸 수 없거나 모든 후보를 쓸 수 없으면 고르지
    않고 에러로 알린다 (2026-11-20 리뷰).

    Raises:
        RegionAmbiguousError: 후보가 여럿이고 정확히 같은 주소가 없거나 둘 이상일 때.
        RegionNotFoundError: 후보가 없거나 당근이 그 주소의 위치를 모를 때.
        LocationMissingError: 후보가 모두, 또는 고른 후보가 건물 정보가 없어 쓸 수 없을 때.
        JibsaError: 후보가 첫 쪽(`ADDRESS_CANDIDATES`)보다 많고 정확히 같은 주소가 없거나 둘 이상일 때 (REGION_AMBIGUOUS, 'N곳이 넘습니다'),
            GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 웹이 주소 쿼리를 바꿨을 때.
    """
    query = ' '.join(query.split())
    address_hint = "도로명 주소(예: '테헤란로 152', '서울특별시 강남구 테헤란로 152')로 다시 주세요. 후보는 당근 웹 검색창의 주소 검색과 같습니다"
    if not query:
        raise RegionNotFoundError(query, hint=address_hint)
    candidates, more = search_addresses(client, query)
    if not candidates:
        raise RegionNotFoundError(query, hint=address_hint)
    usable = [candidate for candidate in candidates if _address_usable(candidate)]

    def unusable_error() -> LocationMissingError:
        return LocationMissingError(
            query,
            f"당근이 '{query}' 의 건물 정보를 주지 않아 그 주소로 찾을 수 없습니다",
            hint='다른 주소나 --lat/--lng 로 좌표를 주세요',
        )

    if not usable:
        raise unusable_error()
    chosen = candidates[0]
    if len(candidates) > 1 or more:
        # 정확히 같은 후보도 쓸 수 없는 후보까지 센다. 쓸 수 있는 후보만 세면 같은 주소가 둘인데 하나를 말없이 고른다 (2026-11-20 리뷰)
        exact = [
            candidate for candidate in candidates
            if query in (' '.join((candidate.road_address or '').split()), ' '.join((candidate.region_address or '').split()))
        ]
        if len(exact) != 1:
            shown = [candidate.road_address or '' for candidate in usable[:AMBIGUOUS_CANDIDATES_SHOWN]]
            if len(exact) == 0:
                hint = f"후보의 도로명 주소 그대로 다시 주세요 (예: --address '{shown[0]}')"
                hint_more = f'{hint}. 시·구를 앞에 붙이면 후보가 줄어듭니다'
            else:
                # 후보의 도로명 주소는 시·도부터 쓴 전체 주소라 정확히 같으면 다시 줘도 시·구를 붙여도 좁혀지지 않는다
                hint = hint_more = f'입력과 같은 주소가 {len(exact)}곳이라 주소로는 하나로 좁힐 수 없습니다. --lat/--lng 로 좌표를 주세요'
            # 후보 목록에는 쓸 수 있는 후보만 있어 수와 달라 보일 수 있다. 센 수에는 든 쓸 수 없는 후보를 message 끝에 알린다
            unusable_count = len(candidates) - len(usable)
            unusable_note = f' (건물 정보가 없어 고를 수 없는 후보 {unusable_count}곳)' if unusable_count else ''
            if not more:
                error = RegionAmbiguousError(query, shown, len(candidates), hint=hint)
                error.message += unusable_note
                raise error
            # 첫 쪽 뒤에도 후보가 있으면 전체 수를 모른다. 받은 수를 전체처럼 알리면 고를 곳이 그만큼뿐인 줄 안다 (2026-11-12
            # 리뷰·실측: '중앙로 1' 은 20곳에 hasNextPage true 인데 '20곳입니다' 였다). 다 받아 세지 않는다 (웹도 4곳씩 '더 보기').
            # 시·구를 붙이면 준다 (같은 날 실측: '부산 중앙로 1' 10곳, '부산광역시 중구 중앙로 1' 1곳)
            raise JibsaError(
                code='REGION_AMBIGUOUS',
                message=f"'{query}' 에 해당하는 주소가 {len(candidates)}곳이 넘습니다{unusable_note}",
                hint=hint_more,
                # 후보가 더 남았는데 전체 수를 모르면 candidate_count 는 null 이다 (RegionAmbiguousError 공통 규약)
                details={'candidates': shown, 'candidate_count': None},
            )
        chosen = exact[0]
    if not _address_usable(chosen):
        raise unusable_error()
    assert chosen.bd_mgt_sn is not None and chosen.original_road_address is not None and chosen.road_address is not None
    response = client.run_request_unit_by_address(
        DaangnUnitByAddressRequestPayloadModel(
            input=DaangnUnitByAddressInputModel(
                juso_address=DaangnJusoAddressInputModel(
                    bd_mgt_sn=chosen.bd_mgt_sn, original_road_address=chosen.original_road_address,
                ),
            ),
        )
    )
    found = response.data.unit_by_address if response.data else None
    unit = found.unit if found else None
    if not response.errors and unit is None:
        # 웹도 이때 '주소를 찾지 못했어요' 로 끝낸다 (MapShell `ys`)
        raise RegionNotFoundError(
            query, hint=f"당근이 '{chosen.road_address}' 의 위치를 모릅니다. 다른 주소나 --lat/--lng 로 좌표를 주세요",
        )
    unit = unwrap_graphql(response, unit, '주소 위치', conditions=False)
    place = unit.complex or unit.building
    point = coordinate_point(unit.location) or coordinate_point(place.coordinate if place else None)
    if point is None:
        raise RegionNotFoundError(
            query, hint=f"당근이 '{chosen.road_address}' 의 좌표를 주지 않았습니다. 다른 주소나 --lat/--lng 로 좌표를 주세요",
        )
    return DaangnAddress(
        road_address=chosen.road_address,
        address=chosen.region_address,
        building_name=(place.name or place.building_name) if place else None,
        complex_id=unit.complex.original_id if unit.complex else None,
        lat=point[0],
        lng=point[1],
    )
