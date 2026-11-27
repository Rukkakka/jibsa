"""단지·재개발 구역 이름을 번호로 해석한다."""


from jibsa.core.errors import (
    JibsaError,
)
from jibsa.core.listing import normalize_address
from jibsa.core.notes import (
    note,
    null_items_note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.region import (
    NaverSearchAutocompleteRedevelopmentAreasV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.region import (
    NaverAutocompleteRedevelopmentAreaModel,
)
from jibsa.providers.naver.service.common.constants import VILLA_COMPLEX_CODES
from jibsa.providers.naver.service.common.response import unwrap
from jibsa.providers.naver.service.region.common import (
    has_more,
    pick_complex,
    search_complexes,
    stop_unless_only,
)


def resolve_complex_number(client: NaverClient, name: str) -> tuple[int, bool | None, list[str]]:
    """단지 이름을 단지 번호로 바꾼다. 이름이 똑같은 단지가 하나이거나 후보가 하나뿐일 때만 정한다 (`pick_complex`).
    다음 쪽 후보가 남았으면(hasNextPage 거나 전체 수가 받은 수보다 크면) 그때도 정하지 않는다.

    Returns:
        tuple[int, bool | None, list[str]]: 단지 번호, 빌라 단지인지 (`complex_is_villa`), 안내.

    Raises:
        JibsaError: 단지를 찾지 못하면 NOT_FOUND.
        RegionAmbiguousError: 후보가 여럿이라 정할 수 없을 때. 후보에 단지 번호를 붙여 번호로 다시 묻게 한다.
    """
    if not name.strip():
        raise JibsaError(code='INVALID_ARGUMENT', message='단지 이름이 비었습니다', hint='단지 번호나 이름을 주세요')
    items, total, has_next_page, dropped = search_complexes(client, name)
    if not items:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"'{name}' 에 해당하는 네이버 단지를 찾지 못했습니다",
            # 이름을 줄이라고 하면 흔한 이름('래미안' 303곳)이 되어 후보가 첫 쪽 10건을 넘어 고르지 않는다 (`pick_complex`)
            hint='단지 이름의 오타·띄어쓰기를 고치거나 단지 번호(fin.land.naver.com/complexes/{번호})로 다시 조회하세요. '
            '흔한 이름(예: 래미안)만 주면 후보가 많아 고르지 않습니다',
        )
    best, notes = pick_complex(
        name,
        items,
        total,
        has_next_page,
        # 단지 이름을 받는 명령(complex·market-price·school·search listings --complex)이 함께 써서 예시에 명령을 적지 않는다
        hint=lambda example: f'단지 이름 대신 후보의 단지 번호를 주세요 (예: {example.complex_number})',
        dropped=dropped,
    )
    return best.complex_number, complex_is_villa(best.type), notes


def complex_is_villa(code: str | None) -> bool | None:
    """단지 유형 코드로 빌라 단지인지 본다. 아파트·오피스텔 단지면 False, 모르는 코드면 None.

    자동완성의 유형은 빌라 단지가 A06, 아파트가 A01, 오피스텔이 A02 다. A01·A02 는 아파트 단지
    엔드포인트가 답한다 (2026-10-09 확인).
    """
    if code in VILLA_COMPLEX_CODES:
        return True
    if code in ('A01', 'A02'):
        return False
    return None


def _redevelopment_label(item: NaverAutocompleteRedevelopmentAreaModel) -> str:
    """재개발 구역 후보 글 ('한남제3재정비촉진구역 (서울특별시 용산구 한남동, 구역 번호 10017678)')."""
    address = normalize_address(item.legal_division_name)
    where = f'{address}, ' if address else ''
    return f'{item.name} ({where}구역 번호 {item.redevelopment_area_number})'


# 리뷰 오탐 (2026-11-18): pick_complex 와 판정이 비슷하지만 단지·구역은 이름 필드·후보 라벨·안내 문구·반환형이 달라 일부러 따로 둔다 (공통 부분은 stop_unless_only·has_more 로 이미 뺐다)
def resolve_redevelopment_number(client: NaverClient, name: str) -> tuple[int, list[str]]:
    """재개발 구역 이름을 구역 번호로 바꾼다. 이름이 똑같은 구역이 하나이거나 후보가 하나뿐일 때만 정한다 (`pick_complex` 와 같은 규칙).

    네이버 웹 검색창은 후보를 보여 주고 사람이 고른다. 한 구역을 법정동마다 따로 등록해 같은 이름이 번호를 달리해 여럿
    오기도 해서(한남제3재정비촉진구역: 한남동 10017678·보광동 1000208, 2026-11-18 실측) 이름이 정확히 같은 후보가 둘 이상이면
    고르지 않는다. 이름이 다른 구역 하나로 정했으면 어느 구역인지 안내한다. 다음 쪽 후보가 남았으면(hasNextPage 거나 전체 수가
    받은 수보다 크면) 뒤쪽에 같은 이름이 더 있을 수 있어 그때도 정하지 않는다 (다음 쪽은 부르지 않는다).
    웹은 size 를 보내지 않아 5건과 '더보기' 인데 여기서는 10건을 한 번에 받는다 (단지 이름과 같다).

    Returns:
        tuple[int, list[str]]: 구역 번호, 안내.

    Raises:
        JibsaError: 이름에 맞는 구역이 없으면 NOT_FOUND (단지 이름과 같다. 구역 번호로 조회하는 명령에서 없는 번호가 NOT_FOUND 인 것과 같은 코드).
        RegionAmbiguousError: 후보가 여럿이라 정할 수 없을 때. 후보에 구역 번호를 붙여 번호로 다시 묻게 한다.
    """
    if not name.strip():
        raise JibsaError(code='INVALID_ARGUMENT', message='재개발 구역 이름이 비었습니다', hint='재개발 구역 번호나 이름을 주세요')
    page = unwrap(
        client.run_request_search_autocomplete_redevelopment_areas_v1(
            NaverSearchAutocompleteRedevelopmentAreasV1RequestParameterModel(keyword=name)
        ),
        '재개발 구역 검색',
        hint='이름이 맞는지 확인하세요',
    )
    items = page.items or []
    if not items:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"'{name}' 에 해당하는 네이버 재개발 구역을 찾지 못했습니다",
            hint='구역 이름의 오타·띄어쓰기를 고쳐 다시 찾거나, jibsa naver search redevelopment <동 이름> 으로 그 동의 구역 목록을 보고 '
            '구역 번호로 조회하세요 (예: jibsa naver search redevelopment 한남동)',
        )
    exact = [item for item in items if item.name == name]
    # 빈 항목(null)이라 뺀 자리도 서버가 센 자리라 받은 수에 더한다
    dropped = page.null_items('items')
    more = has_more(page.total_count, page.has_next_page, len(items) + dropped)
    null_notes = [null_items_note('네이버 재개발 구역 자동완성', dropped)] if dropped else []
    if not more and len(exact) == 1:
        return exact[0].redevelopment_area_number, null_notes
    # 후보가 여럿이거나 다음 쪽이 남았으면 여기서 멈춘다. 돌아오면 후보가 하나뿐이다. 예시는 정확히 같은 이름의 후보가 있으면 그중
    # 첫 곳이다 (이름이 다른 구역을 예로 들지 않게)
    stop_unless_only(
        name,
        [_redevelopment_label(item) for item in items],
        more,
        page.total_count,
        hint=f'구역 이름 대신 후보의 구역 번호를 주세요 (예: {(exact or items)[0].redevelopment_area_number})',
        shown=len(items),
    )
    only = items[0]
    return only.redevelopment_area_number, [
        *null_notes, note('참고', f"'{name}': 구역 이름으로 {_redevelopment_label(only)} 구역을 찾았습니다"),
    ]
