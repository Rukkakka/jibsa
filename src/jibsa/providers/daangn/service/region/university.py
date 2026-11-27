"""당근 대학 검색·해석."""

from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.core.listing import (
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.region.university import (
    DaangnSchoolPoiSearchInputModel,
    DaangnSearchSchoolPoisRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.region.university import DaangnSchoolPoiModel
from jibsa.providers.daangn.service.common.location import coordinate_point
from jibsa.providers.daangn.service.common.response import unwrap_graphql
from jibsa.providers.daangn.service.region.common import (
    LocationMissingError,
    has_location,
)
from jibsa.providers.daangn.service.region.constants import (
    AMBIGUOUS_CANDIDATES_SHOWN,
    NO_LOCATION,
    UNIVERSITY_CANDIDATES,
)
from jibsa.providers.daangn.service.region.models import DaangnUniversity


def same_university_notes(university: DaangnUniversity) -> list[str]:
    """대학 검색이 잘렸는데 맞는 캠퍼스가 하나라 그것을 골랐을 때의 안내 (`same_station_notes` 와 같은 길로 notes 에 붙인다).

    잘린 목록 뒤에 이름이 같은 캠퍼스가 더 있을 수 있어, 알리지 않으면 그 하나가 유일한 캠퍼스로 읽힌다 (2026-11-19 리뷰).
    """
    if not university.cut:
        return []
    return [note(
        '모호',
        f'대학 후보를 {UNIVERSITY_CANDIDATES}곳까지만 받아 이름이 같은 캠퍼스가 더 있을 수 있습니다. '
        '다르면 --university 에 캠퍼스 이름까지 주세요',
    )]


def search_universities(
    client: DaangnClient, name: str, notes: list[str] | None = None,
) -> tuple[list[DaangnSchoolPoiModel], bool]:
    """대학 이름으로 캠퍼스 후보와 뒤에 더 있을 수 있는지 (`searchSchoolPois`, 요청 1회). 웹 검색창의 대학 칸이다. 좌표가 없는
    곳도 돌려준다 (`has_location`).

    웹의 이 쿼리는 다음 쪽을 받을 수 없어 서버가 받는 50곳(`UNIVERSITY_CANDIDATES`)을 한 번에 받는다 (웹 검색창은 4곳). 50곳이 다
    오면 뒤에 더 있을 수 있다. 예전에는 20곳만 받아 고려대학교(23곳)의 치의학대학원 안암캠퍼스 등 3곳이 알림 없이 빠졌다
    (2026-11-13 리뷰·실측). 서버는 빈 항목(null)도 한 곳으로 세어 50곳까지 주므로, 빼고 읽은 수를 받은 자리에 더해 50곳이 다 왔는지
    본다. `notes` 를 주면 빈 항목을 뺐을 때 그 안내를 덧붙인다. 좌표 없는 곳을 먼저 빼면 이름이 같은 캠퍼스 수가 줄어 하나뿐인 줄
    알고 다른 캠퍼스를 말없이 고르므로 (2026-11-19 리뷰) 빼지 않고, 이름이 같은 캠퍼스 수는 좌표 없는 곳까지 센다 (`find_university`).
    """
    response = client.run_request_search_school_pois(
        DaangnSearchSchoolPoisRequestPayloadModel(
            input=DaangnSchoolPoiSearchInputModel(name=name), first=UNIVERSITY_CANDIDATES,
        )
    )
    connection = unwrap_graphql(response, response.data.search_school_pois if response.data else None, '대학 검색', conditions=False)
    pois = [edge.node for edge in connection.edges if edge.node]
    dropped = connection.null_items('edges')
    if dropped and notes is not None:
        notes.append(null_items_note('당근 대학', dropped))
    return pois, len(connection.edges) + dropped >= UNIVERSITY_CANDIDATES


def university_label(poi: DaangnSchoolPoiModel) -> str:
    """캠퍼스를 보여 주는 이름 (캠퍼스까지 붙인 `fullName`, 없으면 대학 이름). 웹 검색창의 대학 칸도 이 이름이다 (MapShell `uu`)."""
    return poi.full_name or poi.name


def _matching_universities(query: str, pois: list[DaangnSchoolPoiModel]) -> list[DaangnSchoolPoiModel]:
    """`find_university` 가 쓸 캠퍼스. 보여 주는 이름(`university_label`)이 같은 곳이 하나면 그곳, 아니면 대학 이름이나 캠퍼스까지
    붙인 이름이 같은 곳 모두다. 위치 정보가 없는 캠퍼스도 센다 (`search_universities`)."""
    labelled = [poi for poi in pois if university_label(poi) == query]
    if len(labelled) == 1:
        return labelled
    return [poi for poi in pois if query in (poi.name, poi.full_name)]


def find_university(client: DaangnClient, name: str) -> DaangnUniversity:
    """대학 이름을 웹 대학 검색(`searchSchoolPois`)으로 캠퍼스 하나로 바꾼다 (요청 1회. 후보가 잘렸는데 못 찾으면 1회 더).

    먼저 보여 주는 이름(`university_label`, `search locations` 의 `universities[].name`)이 같은 캠퍼스를 찾아 하나면 그곳을 쓴다.
    본교는 캠퍼스 이름(`fullName`)이 없기도 해서다 (2026-11-13 실측: 고려대학교는 세종캠퍼스가 `name` '고려대학교'·`fullName`
    '고려대학교 세종캠퍼스', 본교가 `name` '고려대학교'·`fullName` null). 예전에는 대학 이름으로만 맞춰 '고려대학교' 가 늘
    REGION_AMBIGUOUS 였고 후보 '고려대학교' 를 다시 넣어도 같았다. 없거나 여럿이면 대학 이름(`name`)이나 캠퍼스까지 붙인
    이름(`fullName`)이 같은 곳을 보고, 여럿이면 웹처럼 고르게 한다 (2026-11-11 실측: 연세대학교 → 국제·미래·신촌캠퍼스, 서울대학교 →
    관악·연건·시흥·평창캠퍼스). 대학원은 `name` 이 따로라 ('경영대학원') 대학 이름에 섞이지 않는다.

    캠퍼스 이름('연세대학교 신촌캠퍼스')은 대학 이름(첫 낱말)으로 찾아 맞춘다. 그 검색이 50곳에서 잘렸는데 못 찾으면 이름 전체로 한
    번 더 찾는다 (웹 검색창에 이름 전체를 넣은 것과 같고, `search locations` 도 통째로 보낸다).

    이름이 같은 캠퍼스 수는 위치(좌표)가 없는 캠퍼스까지 센다. 여럿이면 위치가 없는 후보에 `NO_LOCATION` 을 붙여 모호하다고 알리고,
    하나인데 위치가 없으면 고르지 않고 에러로 알린다. 후보가 잘렸는데 맞는 곳이 하나면 그것을 고르되 `cut` 으로 알려 부르는 쪽이
    안내를 붙이게 한다 (`same_university_notes`).

    Raises:
        RegionAmbiguousError: 이름이 같은 캠퍼스가 여러 곳일 때.
        JibsaError: 이름이 같은 캠퍼스가 여러 곳이고 후보가 잘려 전체 수를 모를 때 (REGION_AMBIGUOUS).
        LocationMissingError: 이름이 같은 캠퍼스 모두에 위치 정보가 없을 때 (하나뿐이어도).
        RegionNotFoundError: 이름이 같은 대학이 없을 때. 비슷한 대학을 힌트로 주고, 후보가 잘렸으면 그것도 알린다.
    """
    query = ' '.join(name.split())
    if not query:
        raise RegionNotFoundError(name, hint="대학 이름(예: '연세대학교')으로 다시 주세요")
    word = query.split()[0]
    pois, cut = search_universities(client, word)
    matched = _matching_universities(query, pois)
    if not matched and cut and query != word:
        pois, cut = search_universities(client, query)
        matched = _matching_universities(query, pois)
    located = [poi for poi in matched if has_location(poi)]
    if matched and not located:
        # 웹이 보여 주는 캠퍼스를 모두 쓸 수 없다. 다른 대학을 고를 수 없어 에러로 알린다
        raise LocationMissingError(
            query,
            f"당근이 '{university_label(matched[0]) if len(matched) == 1 else query}' 의 위치를 주지 않아 주변 매물을 찾을 수 없습니다",
            hint='그 대학이 있는 동 이름이나 --address, --lat/--lng 로 찾으세요',
        )
    if len(matched) > 1:
        # 위치 정보가 없는 후보는 이름 뒤에 표시하고 고르는 예시로 들지 않는다 (예시를 그대로 넣으면 찾혀야 한다)
        shown = [
            university_label(poi) + ('' if has_location(poi) else NO_LOCATION) for poi in matched[:AMBIGUOUS_CANDIDATES_SHOWN]
        ]
        hint = f"캠퍼스까지 붙인 이름으로 다시 주세요 (예: --university '{university_label(located[0])}')"
        if not cut:
            raise RegionAmbiguousError(query, shown, len(matched), hint=hint)
        # 받은 후보가 잘렸으면 이름이 같은 캠퍼스가 뒤에도 있을 수 있어 전체 수를 모른다 (`_choose_children` 과 같다)
        raise JibsaError(
            code='REGION_AMBIGUOUS',
            message=f"'{query}' 에 해당하는 곳이 {len(matched)}곳보다 많을 수 있습니다",
            hint=hint,
            details={'candidates': shown, 'candidate_count': None},
        )
    if not matched:
        # 위치 정보가 없는 대학은 그 이름을 그대로 넣어도 찾을 수 없어 비슷한 대학으로 권하지 않는다
        similar = [university_label(poi) for poi in pois if has_location(poi)][:AMBIGUOUS_CANDIDATES_SHOWN]
        hint = (
            f"이름이 같은 대학이 없습니다. 비슷한 대학: {', '.join(similar)}. 그 이름 그대로 다시 주세요"
            if similar else "대학 이름(예: '연세대학교')으로 다시 주세요"
        )
        if cut:
            hint += (
                f'. 대학 검색은 {UNIVERSITY_CANDIDATES}곳까지만 받아 찾는 캠퍼스·대학원이 그 뒤에 있을 수 있습니다. '
                "'jibsa daangn search locations <캠퍼스·대학원까지 붙인 이름>' 으로 이름을 확인해 그대로 주면 그 이름으로 다시 찾습니다"
            )
        raise RegionNotFoundError(query, hint=hint)
    poi = matched[0]
    point = coordinate_point(poi.coordinate)
    assert point is not None
    # 후보가 잘렸는데 맞는 곳이 하나면 뒤에 이름이 같은 캠퍼스가 더 있을 수 있다. 고르되 알린다 (`same_university_notes`)
    return DaangnUniversity(
        name=university_label(poi), address=poi.jibun_address, lat=point[0], lng=point[1], university_id=poi.id, cut=cut,
    )
