"""시·도·시·군·구·읍·면·동 목록 (`list_regions`)."""


from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.core.korean import (
    is_district_code,
    particle,
    quoted,
)
from jibsa.core.listing import (
    CITY_NAMES_NOT_SIDO,
    SIDO_OFFICIAL_NAMES,
    normalize_address,
    null_items_note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.region import (
    NaverLegalDivisionInfoListByLevelV1RequestParameterModel,
    NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.region import (
    NaverAutocompleteLegalDivisionModel,
    NaverAutocompletePageModel,
    NaverLegalDivisionInfoModel,
)
from jibsa.providers.naver.service.common.response import unwrap
from jibsa.providers.naver.service.region.common import (
    city_districts,
    collect_matching,
    only_district,
    sub_regions_response,
)
from jibsa.providers.naver.service.region.common import sub_regions as _sub_regions
from jibsa.providers.naver.service.region.constants import (
    FORMER_PROVINCE_NAME_HINTS,
    FORMER_PROVINCE_NAMES,
    MAX_CANDIDATE_NOTES,
    REGION_LEVEL_LABELS,
)
from jibsa.providers.naver.service.region.models.regions import (
    NaverRegionEntry,
    NaverRegionList,
)


def _region_entry(item: NaverLegalDivisionInfoModel, name: str | None = None) -> NaverRegionEntry:
    coordinates = item.coordinates
    return NaverRegionEntry(
        name=name or item.legal_division_name or item.legal_division_number,
        level=REGION_LEVEL_LABELS.get(item.legal_division_level_type or ''),
        legal_division_code=item.legal_division_number,
        lat=coordinates.y_coordinate if coordinates else None,
        lng=coordinates.x_coordinate if coordinates else None,
    )


def _find_province(provinces: list[NaverLegalDivisionInfoModel], name: str) -> NaverLegalDivisionInfoModel | None:
    """시·도를 부르는 이름(서울·서울시·서울특별시·충북·전라북도·광주 등)에 맞는 시·도. 시·도 이름이 아니면 None.

    줄임말·옛 이름은 매물 주소와 같은 `SIDO_OFFICIAL_NAMES` 로 정식 명칭(`cityFullName`)에 맞춘다. 네이버 이름
    (`legalDivisionName`: 서울시·전북도)도 받는다.
    """
    official = SIDO_OFFICIAL_NAMES.get(name, name)
    return next(
        (item for item in provinces if official == item.city_full_name or name == item.legal_division_name),
        None,
    )


def _is_district_level(item: NaverAutocompleteLegalDivisionModel) -> bool:
    """자동완성 항목이 시·군·구인지. 단위(`legal_division_level_type`)가 있으면 그것, null 이면 법정동 코드가 시·군·구인지로 본다."""
    if item.legal_division_level_type is not None:
        return item.legal_division_level_type == 'GUN'
    code = item.legal_division_number
    return is_district_code(code)


def list_regions(client: NaverClient, query: str | None = None) -> NaverRegionList:
    """지역 하나의 바로 아래 지역 (요청 1~5회: 시·도 목록 1회, 이름을 주면 자동완성 첫 쪽 1회에 같은 이름이 첫 쪽을 채우면 다음 쪽 최대 2회, 하위 지역 1회). 지역을 주지 않으면 시·도 전체 (1회).

    시·도 이름(서울, 경기도, 충북)이면 시·군·구, 시·군·구 이름(강남구, 부산시 중구)이면 읍·면·동을 준다. 시·군·구가 하나뿐인
    세종(세종·세종시)은 그 아래 읍·면·동을 준다.
    구가 있는 시(성남시)는 네이버가 시를 따로 두지 않아 시·도 목록에서 그 시의 구를 골라 준다.

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        JibsaError: 읍·면·동처럼 하위 지역이 없는 단위면 NOT_FOUND. 이름이 공백뿐이면 INVALID_ARGUMENT.
    """
    if query is not None and not query.strip():
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='지역 이름이 비었습니다',
            hint='시·도(서울, 경기도)나 시·군·구(강남구) 이름을 주거나, 이름 없이 불러 시·도 목록을 보세요',
        )
    provinces = unwrap(
        client.run_request_legal_division_info_list_by_level_v1(NaverLegalDivisionInfoListByLevelV1RequestParameterModel()),
        '시·도 목록',
        hint=None,
    )
    if query is None:
        return NaverRegionList(regions=[_region_entry(item, item.city_full_name) for item in provinces])
    query = query.strip()
    # `SIDO_OFFICIAL_NAMES` 에서는 옛 광주광역시지만 한 단어로 오면 경기도 광주시로 찾는다 (`CITY_NAMES_NOT_SIDO`). 시·도를
    # 붙인 '광주시 광산구' 는 경기도 광주시에 구가 없어 전남광주통합특별시로 본다
    province = None if query in CITY_NAMES_NOT_SIDO else _find_province(provinces, query)
    if province is not None:
        name = province.city_full_name or province.legal_division_name
        # _find_province 가 둘 중 하나의 이름으로 찾았다
        assert name is not None
        # 하위 지역 목록과, 그 목록에서 빈 항목(null)을 빼고 읽은 수. 실패하면 예외다
        response = sub_regions_response(client, 'GUN', province.legal_division_number)
        children, dropped = unwrap(response, '하위 지역', hint=None), response.null_items('result')
        notes = [
            f"{name} 의 하위 지역입니다. 네이버 시·도 목록에는 옛 이름 '{query}' 대신 {name} 만 있습니다"
            + (f'. {FORMER_PROVINCE_NAME_HINTS[query]}' if query in FORMER_PROVINCE_NAME_HINTS else '')
        ] if query in FORMER_PROVINCE_NAMES else []
        if dropped:
            notes.append(null_items_note('네이버 시·군·구 목록', dropped))
        # 빈 항목(null)을 뺐으면 빠진 곳이 시·군·구일 수 있어 하나뿐이라고 단정하지 않는다
        only = None if dropped else only_district(children)
        if only is not None:
            # 세종은 시·군·구가 '세종시' 하나뿐이고 그 이름이 시·도 별칭('세종시' → 세종특별자치시)이라, 시·군·구 목록을 주면
            # 'regions 세종시' 가 다시 같은 목록을 준다 (2026-10-11 실측). 하나뿐이면 그 아래 읍·면·동을 준다 (요청 1회 더)
            return NaverRegionList(
                parent=name,
                parent_legal_division_code=only.legal_division_number,
                regions=[_region_entry(item) for item in _sub_regions(client, 'EUP', only.legal_division_number)],
                notes=notes + [f"{name}{particle(name, '은/는')} 시·군·구가 {only.legal_division_name} 하나뿐이라 그 아래 읍·면·동입니다"],
            )
        return NaverRegionList(
            parent=name,
            parent_legal_division_code=province.legal_division_number,
            regions=[_region_entry(item) for item in children],
            notes=notes,
        )

    # 자동완성은 네이버식 시·도 이름('서울시 강남구')으로만 찾는다. 정식 명칭('서울특별시 강남구'·'부산광역시 중구')은
    # 빈 목록이고, '서울 강남구' 는 '서울시 강남구' 를 주지만 검색어와 이름이 달라 맞춰 볼 수 없다 (2026-10-10).
    # 옛 이름('광주 광산구')은 빈 목록이다 (2026-10-11). 그래서 첫 단어가 시·도 이름이면 시·도 목록의 네이버 이름
    # (legalDivisionName, '전남광주시')으로 바꿔 묻고 맞춰 본다
    words = query.split()
    named = _find_province(provinces, words[0]) if len(words) > 1 else None
    keyword = ' '.join([named.legal_division_name, *words[1:]]) if named and named.legal_division_name else query
    def fetch(number: int) -> NaverAutocompletePageModel[NaverAutocompleteLegalDivisionModel]:
        return unwrap(
            client.run_request_search_autocomplete_legal_divisions_v1(
                NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=keyword, page=number)
            ),
            '지역 검색',
            hint='이름이 맞는지 확인하세요',
        )

    def is_exact(item: NaverAutocompleteLegalDivisionModel) -> bool:
        return item.legal_division_name == keyword or item.legal_division_name.endswith(f' {keyword}')

    # 자동완성은 한 쪽에 다섯 곳만 줘서 첫 쪽이 모두 이름이 맞으면 같은 이름이 다음 쪽에 더 있을 수 있다 ('중구' 는 첫 쪽
    # 5곳이 모두 중구, 2026-11-17). 첫 쪽 수를 전체로 말하지 않게 이름이 맞는 곳이 끝날 때까지 다음 쪽을 받는다
    items, incomplete, dropped = collect_matching(fetch, fetch(0), is_exact)
    null_notes = [null_items_note('네이버 법정동 자동완성', dropped)] if dropped else []
    exact = [item for item in items if is_exact(item)]
    if not exact:
        # 구가 있는 시는 시 자신 대신 그 아래 구가 온다 ('성남시' → 경기도 성남시 수정구 …). 시·도 목록에서
        # '성남시 ' 로 시작하는 구를 모두 고른다 (자동완성은 한 쪽에 다섯 곳만 준다).
        # 시·도를 붙인 '경기도 성남시'·'경기 성남시' 도 자동완성이 같은 구를 주므로, 구 이름 앞의 단어들이
        # 검색어 단어들로 끝나는지 본다 (단어 하나씩 비교하면 여러 단어 검색어는 늘 REGION_NOT_FOUND, 2026-10-10)
        query_words = (normalize_address(keyword) or keyword).split()

        def city_words(item: NaverAutocompleteLegalDivisionModel) -> list[str]:
            return (normalize_address(item.legal_division_name) or '').split()[:-1]

        under = next(
            (
                item for item in items
                if _is_district_level(item) and city_words(item)[-len(query_words):] == query_words
            ),
            None,
        )
        if under is None:
            raise RegionNotFoundError(query, hint='시·도(서울, 경기도)나 시·군·구(강남구, 부산시 중구) 이름으로 다시 주세요')
        parent = city_words(under)
        # 구 코드가 속한 시·도 코드(앞 두 자리 + '00000000')에 GUN 을 보낸다. 사이트가 보내는 조합이다
        # (2026-11-17 실측: 수정구 코드 + SI 와 경기도 코드 + GUN 이 같은 47곳)
        # 리뷰 오탐 (2026-11-17): 법정동 코드 앞 두 자리가 시·도다. 시·도 16곳 모두 '앞 두 자리 + 00000000' 이다 (코드가 바뀐
        # 전북 52·강원 51·전남광주 12 포함, regions 전주시·청주시·창원시 실측)
        # 시의 구는 코드로 고른다 (`city_districts`). 시 코드는 구 코드 앞 네 자리 + '000000' 이다 (4113100000 → 4113000000)
        sub_regions = _sub_regions(client, 'GUN', under.legal_division_number[:2] + '00000000')
        entries = [_region_entry(item) for item in city_districts(sub_regions, under.legal_division_number[:4] + '000000')]
        return NaverRegionList(parent=' '.join(parent), regions=entries, notes=null_notes)

    # 시·군·구를 먼저 본다 (하위 지역이 있는 쪽)
    exact.sort(key=lambda item: not _is_district_level(item))
    best = exact[0]
    notes = null_notes
    if not _is_district_level(best) and not incomplete:
        # 읍·면·동은 같은 이름이 여럿이어도 하위 지역이 없어 후보를 묻지 않고 알린다 (신사동: 은평구·강남구, 2026-11-24).
        # 여럿이면 그중 한 곳을 고른 것처럼 보이지 않게 받은 이름으로 말한다
        name = best.legal_division_name if len(exact) == 1 else query
        raise JibsaError(
            code='NOT_FOUND',
            message=f"{quoted(name, '은/는')} 읍·면·동이라 하위 지역이 없습니다",
            hint='시·도(서울, 경기도)나 시·군·구(강남구) 이름을 주세요. 동은 search listings 등에 바로 넣으면 됩니다',
        )
    same = [
        item.legal_division_name or item.legal_division_number for item in exact
        if _is_district_level(item) == _is_district_level(best)
    ]
    if len(same) > 1 or incomplete:
        # 첫 곳으로 고르면 다른 곳의 동 목록이 나온다. search listings 처럼 후보를 알리고 멈춘다 (2026-10-15).
        # 쪽 상한에 닿아 다 받지 못했으면 하나뿐이어도 고르지 않고 수는 모름이다
        candidates = [normalize_address(name) or name for name in same[:MAX_CANDIDATE_NOTES]]
        # 고른 곳이 읍·면·동이면(다 받지 못해 `incomplete` 일 때만 온다) 시·도를 붙여도 바로 NOT_FOUND 라 예시를 주지 않는다
        raise RegionAmbiguousError(
            query, candidates, None if incomplete else len(same),
            hint=f"시·도 이름을 붙여 다시 주세요 (예: '{candidates[0]}')" if _is_district_level(best)
            else '읍·면·동은 하위 지역이 없습니다. 시·도(서울, 경기도)나 시·군·구(강남구) 이름을 주세요. 동은 search listings 등에 바로 넣으면 됩니다',
        )
    return NaverRegionList(
        parent=normalize_address(best.legal_division_name),
        parent_legal_division_code=best.legal_division_number,
        regions=[_region_entry(item) for item in _sub_regions(client, 'EUP', best.legal_division_number)],
        notes=notes,
    )
