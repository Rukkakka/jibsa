"""평형대 평당가와 주변 단지 비교 (nearby-complexes)."""


from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.real_price.nearby import (
    DabangRealPriceComplexPricePerPyV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.real_price.nearby import DabangNearComplexModel
from jibsa.providers.dabang.service.common.complex import area_price
from jibsa.providers.dabang.service.common.constants import (
    COMPLEX_KIND_BY_TYPE,
    COMPLEX_URL,
)
from jibsa.providers.dabang.service.common.text import building_years
from jibsa.providers.dabang.service.real_price.common import (
    fetch_complex_space,
    primary_space,
)
from jibsa.providers.dabang.service.real_price.models import (
    DabangNearbyComplex,
    DabangNearbyComplexes,
)


def _nearby_complex(row: DabangNearComplexModel) -> DabangNearbyComplex | None:
    # 웹은 단지 ID 가 없는 줄을 그리지 않는다 (complex 청크 `nn`: `if(!e.complexId)return null`)
    if not row.complex_id:
        return None
    return DabangNearbyComplex(
        complex_id=row.complex_id,
        name=row.complex_name,
        complex_type=COMPLEX_KIND_BY_TYPE.get(row.complex_type or ''),
        address=normalize_address(row.address),
        # 리뷰 오탐 (2026-11-14): 주변 단지 평당가는 0 을 null 로 바꾸지 않는다. 웹 complex 청크 `nn` 은 `averagePyeongPrice ?? ''` 를
        # 가격 글자로 바꿔 null 은 '-', 0 은 '0원' 으로 그린다 (area_prices 막대 `Yt` 와 다르다)
        price_per_pyeong_manwon=row.average_pyeong_price,
        household_count=row.household_num,
        occupancy_years=building_years(row.complex_desc),
        distance_m=row.distance,
    )


def get_nearby_complexes(client: DabangClient, complex_id: str, *, space_seq: int | None) -> DabangNearbyComplexes:
    """평형대 평당가와 반경 1km 주변 단지 비교 (요청 1회, 평형을 안 주면 대표 평형을 찾느라 +1).

    다방 웹 단지 화면 평당가 칸의 기본 탭('N평대 비교')이다. 다방이 탭 이름을 비워 주면 웹은 이 탭을 그리지 않고 '전체 평형
    비교'(complex 결과 area_prices)만 보여 주므로 area_prices 와 nearby 의 sale·jeonse 를 모름(null)으로 두고 안내를 낸다.

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    notes: list[str] = []
    if space_seq is None:
        space_seq, space_notes = primary_space(client, complex_id, verb='비교했습니다')
        notes += space_notes
    result = fetch_complex_space(
        lambda: client.run_request_real_price_complex_price_per_py_v5(
            DabangRealPriceComplexPricePerPyV5RequestParameterModel(complex_id=complex_id, space_seq=space_seq)
        ).result,
        complex_id,
        space_seq,
    )
    tab = (result.pyeong_range_tab_name or '').strip() if result else ''
    if result is None or not tab:
        notes.append(note(
            '참고',
            f"다방이 이 평형(pyeong_id {space_seq})에는 'N평대 비교' 를 주지 않습니다 (다방 웹도 이 탭 없이 '전체 평형 비교' 만 "
            f'보여 줍니다). 단지 전체 평형의 평당가 비교는 jibsa dabang complex {complex_id} 의 area_prices 로 보세요',
        ))
        return DabangNearbyComplexes(
            complex_id=complex_id, pyeong_id=space_seq, nearby={'sale': None, 'jeonse': None}, url=COMPLEX_URL.format(complex_id), notes=notes,
        )
    near = result.near_complexes
    # 매매·전월세 쪽이 null 이면 그 쪽은 모름(null), 비어 있으면 []
    sale_rows = [_nearby_complex(row) for row in near.trade] if near and near.trade is not None else None
    lease_rows = [_nearby_complex(row) for row in near.lease] if near and near.lease is not None else None
    skipped = (sale_rows or []).count(None) + (lease_rows or []).count(None)
    if skipped:
        notes.append(note('제외', f'단지 ID 가 없는 주변 단지 {skipped}줄은 다방 웹처럼 넣지 않았습니다'))
    return DabangNearbyComplexes(
        complex_id=complex_id,
        pyeong_id=space_seq,
        pyeong_range=tab.removesuffix('비교').strip(),
        area_prices=None if result.area_average_price is None else [area_price(price) for price in result.area_average_price],
        nearby={
            'sale': None if sale_rows is None else [row for row in sale_rows if row is not None],
            'jeonse': None if lease_rows is None else [row for row in lease_rows if row is not None],
        },
        url=COMPLEX_URL.format(complex_id),
        notes=notes,
    )
