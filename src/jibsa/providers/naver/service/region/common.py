"""지역 해석이 같이 쓰는 도우미: 자동완성 후보 모으기·고르기와 하위 지역 목록 받기."""

from collections.abc import Callable

from jibsa.core.errors import (
    RegionAmbiguousError,
)
from jibsa.core.listing import normalize_address
from jibsa.core.notes import (
    note,
    null_items_note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.region import (
    NaverLegalDivisionSubInfoListV1RequestParameterModel,
    NaverSearchAutocompleteComplexesV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.region import (
    NaverAutocompleteComplexModel,
    NaverAutocompletePageModel,
    NaverLegalDivisionInfoModel,
    NaverLegalDivisionSubInfoListV1ResponseModel,
)
from jibsa.providers.naver.service.common.response import unwrap
from jibsa.providers.naver.service.region.constants import (
    MAX_AUTOCOMPLETE_PAGES,
    MAX_CANDIDATE_NOTES,
)

from typing import (
    Literal,
    TypeVar,
)


AutocompleteItemT = TypeVar('AutocompleteItemT')


def collect_matching(
    fetch: Callable[[int], NaverAutocompletePageModel[AutocompleteItemT]],
    first: NaverAutocompletePageModel[AutocompleteItemT],
    matches: Callable[[AutocompleteItemT], bool],
) -> tuple[list[AutocompleteItemT], bool, int]:
    """자동완성 첫 쪽 뒤로 이름이 맞는 후보가 이어지면 다음 쪽을 더 받아 모은다 (웹 검색창의 '더보기' 와 같은 요청).

    법정동·역 자동완성은 이름이 맞는 곳을 앞에, 이름 일부만 맞는 곳을 뒤에 준다 (2026-11-17 실측: '중구' 첫 쪽 5곳이 모두
    중구이고 둘째 쪽부터 중구 안의 동, '강남구' 는 강남구 다음에 그 안의 동, '시청역' 은 시청역 3곳 다음에 시청.용인대역).
    그래서 받은 쪽의 마지막 후보까지 이름이 맞고 다음 쪽이 남았을 때만 다음 쪽을 받는다. 마지막 후보가 이름이 다르면
    이름이 맞는 후보는 다 받은 것이다.

    Args:
        fetch: 쪽 번호(0부터)로 자동완성 한 쪽을 받는 함수.
        first: 이미 받은 첫 쪽.
        matches: 이름이 맞는 후보인지.

    Returns:
        tuple[list, bool, int]: 받은 후보 전체 (사이트 순서), 이름이 맞는 후보가 아직 남았을 수 있는지 (쪽 상한에 닿았거나
            다음 쪽이 있다면서 빈 쪽을 줬을 때), 빈 항목(null)이라 빼고 읽은 수 (받은 수를 셀 때 더한다).
    """
    items = list(first.items or [])
    dropped = first.null_items('items')
    page = first
    pages = 1
    while items and matches(items[-1]) and has_more(page.total_count, page.has_next_page, len(items) + dropped):
        if pages >= MAX_AUTOCOMPLETE_PAGES:
            return items, True, dropped
        page = fetch(pages)
        pages += 1
        if not page.items:
            return items, True, dropped
        items.extend(page.items)
        dropped += page.null_items('items')
    return items, False, dropped


def search_complexes(
    client: NaverClient,
    keyword: str,
) -> tuple[list[NaverAutocompleteComplexModel], int | None, bool | None, int]:
    """단지 이름 자동완성 첫 페이지(10건)와 전체 수(totalCount)·다음 쪽 여부(hasNextPage)·빈 항목(null)이라 빼고 읽은 수. 사이트 검색창과 같은 요청·순서다."""
    page = unwrap(
        client.run_request_search_autocomplete_complexes_v1(
            NaverSearchAutocompleteComplexesV1RequestParameterModel(keyword=keyword)
        ),
        '단지 검색',
        hint='이름이 맞는지 확인하세요',
    )
    return page.items or [], page.total_count, page.has_next_page, page.null_items('items')


def complex_label(item: NaverAutocompleteComplexModel) -> str:
    """단지 후보 글 ('래미안 (서울특별시 강남구 개포동, 단지 번호 12345)')."""
    address = normalize_address(item.legal_division_name)
    return f'{item.complex_name} ({address}, 단지 번호 {item.complex_number})' if address else (
        f'{item.complex_name} (단지 번호 {item.complex_number})'
    )


def has_more(total: int | None, has_next_page: bool | None, received: int) -> bool:
    """자동완성에 받은 쪽 뒤로 후보가 더 남았는지. hasNextPage 거나 전체 수(totalCount)가 받은 수보다 크면 남았다.

    totalCount 가 비어 와도 hasNextPage 로 안다 (웹 검색창의 '더보기' 도 hasNextPage 를 본다).
    """
    return bool(has_next_page) or (total is not None and total > received)


def candidate_count(found: int, total: int | None, more: bool) -> int | None:
    """REGION_AMBIGUOUS 의 candidate_count. 다음 쪽이 남았으면 전체 수(totalCount), 아니면 찾은 수.

    다음 쪽이 남았는데 전체 수가 비어 오면 모름(None)이다. 찾은 수를 쓰면 받은 첫 쪽이 전부인 것처럼 말한다.
    """
    if not more:
        return found
    return max(total, found) if total is not None else None


def stop_unless_only(
    query: str,
    labels: list[str],
    more: bool,
    total: int | None,
    *,
    hint: str | None = None,
    shown: int = MAX_CANDIDATE_NOTES,
) -> None:
    """이름이 맞는 후보가 없을 때. 후보가 둘 이상이거나 다음 쪽이 남았으면 고르지 않고 REGION_AMBIGUOUS 로 멈춘다.

    후보가 하나뿐이면 돌아오고, 부르는 쪽이 그 후보로 찾고 `[참고]` 로 알린다 (웹 검색창이 보여 줄 후보 하나 그대로다).

    Args:
        labels: 받은 후보 전체의 후보 글 (사이트 순서).
        shown: 에러 후보에 넣을 수. 단지는 받은 10건을 모두 넣는다.

    Raises:
        RegionAmbiguousError: 후보가 둘 이상이거나 다음 쪽이 남았을 때.
    """
    if len(labels) >= 2 or more:
        raise RegionAmbiguousError(query, labels[:shown], candidate_count(len(labels), total, more), hint=hint)


def pick_complex(
    query: str,
    items: list[NaverAutocompleteComplexModel],
    total: int | None,
    has_next_page: bool | None,
    hint: Callable[[NaverAutocompleteComplexModel], str],
    dropped: int = 0,
) -> tuple[NaverAutocompleteComplexModel, list[str]]:
    """단지 이름 자동완성 후보에서 단지 하나와 안내를 고른다. 고를 수 없으면 후보를 알린다.

    네이버 웹 검색창은 후보 목록을 보여 주고 사람이 고른다 (2026-11-16 웹 대조: '현대' 첫 10건 중 이름이 정확히 '현대' 인
    단지가 5곳, 전체 3,924건). 그래서 이름이 정확히 같은 후보가 하나이거나 후보가 하나뿐일 때만 그 단지로 정하고, 첫 후보를
    임의로 고르지 않는다. 이름이 다른 단지 하나로 정했으면 어느 단지인지 안내한다.
    다만 다음 쪽이 남았으면(hasNextPage 거나 전체 수가 받은 후보 수보다 크면) 웹이 '더보기' 로 다음 쪽(page=1, 2…)을 더
    보여 주는 경우라 뒤쪽에 이름이 같은 단지가 더 있을 수 있다 (2026-11-16 '한양' 실측: 전체 852건, 정확히 '한양' 인 단지가
    첫 쪽(page=0)에 1~2곳(첫 쪽 순서가 요청마다 달랐다), page=1 에 2곳, page=2 에 1곳). 다음 쪽을 더 부르지 않고, 이때는
    정확히 같은 이름이 하나여도 후보가 하나여도 고르지 않는다. totalCount 가 비어 와도 hasNextPage 로 다음 쪽을 안다
    (같은 모듈의 동·역 자동완성도 `has_more` 로 같게 본다).

    Args:
        query: 사용자가 준 단지 이름.
        items: 자동완성 후보 (사이트 순서).
        total: 자동완성 전체 수 (totalCount). 비어 올 수 있다 (다음 쪽이 남았는데 비면 `candidate_count` 는 null, `candidate_count`).
        has_next_page: 자동완성의 다음 쪽 여부 (hasNextPage).
        hint: 후보가 여럿일 때 다시 묻는 법을 만드는 함수 (부르는 명령마다 다르다). 예로 들 단지 후보를 받는다.
            정확히 같은 이름의 후보가 있으면 그중 첫 곳, 없으면 첫 후보다 (이름이 다른 단지를 예로 들지 않게).
        dropped: 빈 항목(null)이라 빼고 읽은 후보 수. 서버가 센 자리라 다음 쪽이 남았는지 셀 때 받은 수에 더하고, 있으면 안내를 붙인다.

    Raises:
        RegionAmbiguousError: 다음 쪽이 남았거나, 이름이 정확히 같은 후보가 여럿이거나, 정확히 같은 이름 없이 후보가 여럿일 때.
    """
    exact = [item for item in items if item.complex_name == query]
    more_pages = has_more(total, has_next_page, len(items) + dropped)
    null_notes = [null_items_note('네이버 단지 자동완성', dropped)] if dropped else []
    if not more_pages and len(exact) == 1:
        return exact[0], null_notes
    # 후보가 여럿이거나 다음 쪽이 남았으면 여기서 멈춘다 (받은 후보를 모두 알린다). 돌아오면 후보가 하나뿐이다
    stop_unless_only(
        query,
        [complex_label(item) for item in items],
        more_pages,
        total,
        hint=hint((exact or items)[0]),
        shown=len(items),
    )
    only = items[0]
    return only, [*null_notes, note('참고', f"'{query}': 단지 이름으로 {complex_label(only)} 단지를 찾았습니다")]


def sub_regions_response(
    client: NaverClient, level: Literal['GUN', 'EUP'], code: str
) -> NaverLegalDivisionSubInfoListV1ResponseModel:
    """받을 하위 지역 단위(GUN 시·군·구, EUP 읍·면·동)와 그 윗지역 코드로 하위 지역 목록 응답을 받는다. 사이트가 보내는 값이다."""
    return client.run_request_legal_division_sub_info_list_v1(
        NaverLegalDivisionSubInfoListV1RequestParameterModel(legal_division_level_type=level, legal_division_number=code)
    )


def sub_regions(client: NaverClient, level: Literal['GUN', 'EUP'], code: str) -> list[NaverLegalDivisionInfoModel]:
    """하위 지역 목록. 실패하면 예외다."""
    return unwrap(sub_regions_response(client, level, code), '하위 지역', hint=None)


def city_districts(sub_regions: list[NaverLegalDivisionInfoModel], city_code: str) -> list[NaverLegalDivisionInfoModel]:
    """시·도 아래 시·군·구 목록에서 그 시(코드 `city_code`)의 구. 코드 앞 네 자리가 같고 시 자신이 아닌 곳이다."""
    return [
        item for item in sub_regions
        if item.legal_division_number[:4] == city_code[:4] and item.legal_division_number != city_code
    ]


def only_district(children: list[NaverLegalDivisionInfoModel]) -> NaverLegalDivisionInfoModel | None:
    """시·도 아래 시·군·구 목록이 시·군·구 하나뿐이면 그것. 세종특별자치시가 그렇다 (시·군·구가 세종시 하나뿐)."""
    return children[0] if len(children) == 1 and children[0].legal_division_level_type == 'GUN' else None
