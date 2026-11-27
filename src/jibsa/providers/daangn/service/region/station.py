"""당근 역 검색·해석."""

from jibsa.core.korean import (
    LINE_NAME_PATTERN,
    quoted,
)
from jibsa.core.notes import note
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.region.common import (
    DaangnQueryInputModel,
)
from jibsa.providers.daangn.api.models.request.region.station import (
    DaangnSearchSubwayStationPoisRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.region.station import (
    DaangnSubwayStationPoiModel,
)
from jibsa.providers.daangn.service.common.location import (
    coordinate_point,
    station_name,
)
from jibsa.providers.daangn.service.common.response import unwrap_graphql
from jibsa.providers.daangn.service.region.common import (
    LocationMissingError,
    has_location,
)
from jibsa.providers.daangn.service.region.constants import (
    NO_LOCATION,
    NUMBER_ONLY_LINE_PATTERN,
)
from jibsa.providers.daangn.service.region.models.station import DaangnStation


def _station_label(lines: list[str], name: str) -> str:
    """노선을 붙인 역 이름 ('서울5호선 양평역'). 같은 이름의 역을 노선으로 구분하고, `find_station` 이 이 이름을 그대로 받는다."""
    return ' '.join(part for part in ('·'.join(lines), station_name(name)) if part)


def same_station_notes(station: DaangnStation) -> list[str]:
    """같은 이름의 역이 여러 곳이라 첫 역으로 찾았을 때의 안내. 다른 역은 노선을 붙인 이름으로 고른다.

    위치 정보가 없는 다른 역(`NO_LOCATION`)은 이름만 알리고 고르는 예시로 들지 않는다. `--station` 으로 찾을 수 없다.
    """
    if not station.others:
        return []
    located = next((other for other in station.others if not other.endswith(NO_LOCATION)), None)
    retry = (
        f"다른 역이면 노선을 붙여 주세요 (예: --station '{located}')" if located
        else '다른 곳은 위치 정보가 없어 --station 으로 찾을 수 없습니다'
    )
    return [note(
        '모호',
        f"{quoted(station.name, '이/가')} 여러 곳이라 {_station_label(station.lines, station.name)} 기준으로 찾았습니다 "
        f"(다른 곳: {', '.join(station.others)}). {retry}",
    )]


def search_stations(client: DaangnClient, query: str) -> list[DaangnSubwayStationPoiModel]:
    """역 이름 앞부분이 같은 역 (`searchSubwayStationPois`, 요청 1회). 웹 검색창의 지하철 칸이다. '역' 을 떼고 묻는다.

    검색어가 '역' 하나면 떼지 않고 그대로 묻는다. 떼면 빈 검색어가 요청 모델의 최소 길이에 걸려 `ValueError` 가 되고,
    `search locations` 가 이것을 응답 형식이 바뀐 실패로 알렸다 (2026-11-12 리뷰). 당근은 '역' 에 역을 주지 않아 빈 칸이다
    (같은 날 실측).
    """
    response = client.run_request_search_subway_station_pois(
        DaangnSearchSubwayStationPoisRequestPayloadModel(
            input=DaangnQueryInputModel(query=query.removesuffix('역') or query),
        )
    )
    return unwrap_graphql(response, response.data.search_subway_station_pois if response.data else None, '역 검색', conditions=False)


def station_label(station: DaangnSubwayStationPoiModel) -> str:
    """노선을 붙인 역 이름 ('서울2호선 역삼역'). `--station` 이 그대로 받는다."""
    return _station_label(station.line_names, station.station_name)


def station_argument(name: str) -> str:
    """지역 자리에 준 역 이름을 `--station` 에 그대로 넣으면 찾히는 꼴로 바꾼다 (역 이름을 권하는 안내의 예시).

    `find_station` 은 마지막 낱말 앞의 낱말을 모두 노선으로 읽는다. 앞 낱말이 모두 노선 이름이면('서울5호선 양평역',
    '경의중앙선·서울5호선 양평') 그대로 두고, 아니면(시·도·구 이름: '서울 강남역') 마지막 낱말(역 이름)만 남긴다. 입력 전체를 넣으면
    '서울' 을 노선으로 읽어 못 찾는다 (2026-11-19 리뷰).

    숫자만 쓴 노선('2호선 강남역', '2호선·신분당선 강남역')도 마지막 낱말만 남긴다. 당근은 숫자 노선에 늘 지역을 붙여('서울2호선')
    `2호선` 은 당근 노선 이름이 아니라 그대로 넣으면 못 찾는다 (2026-11-20 리뷰). 노선 번호를 버리면 이름이 같은 역(예: '4호선 중앙역'
    → '중앙역', 서울4호선·부산1호선)은 `find_station` 이 웹처럼 첫 역을 고르고, 다른 역은 같은 이름 역 안내(`others`)로 알린다.
    jibsa 가 노선 번호로 짐작해 고르지 않는다.

    '강남 역' 처럼 '역' 을 띄어 쓰면 앞 낱말에 붙인다. 그대로 두면 마지막 낱말 '역' 만 남아 `find_station` 이 찾지 못한다 (2026-11-20 리뷰).
    """
    # 리뷰 오탐 (2026-11-22): 빈 이름·공백뿐인 이름도 IndexError 가 나지 않는다. words 가 [] 면 lines 도 [] 라 all([]) 이 참이어서
    # ' '.join([]) = '' 를 돌려주고 words[-1] 에 닿지 않는다 (그 뒤 resolve_area 가 빈 이름을 REGION_NOT_FOUND 로 끝낸다)
    words = name.split()
    if len(words) >= 2 and words[-1] == '역':
        words = [*words[:-2], words[-2] + '역']
    lines = [line for word in words[:-1] for line in word.split('·') if line]
    if any(NUMBER_ONLY_LINE_PATTERN.fullmatch(line) for line in lines):
        return words[-1]
    if all(LINE_NAME_PATTERN.fullmatch(line) for line in lines):
        return ' '.join(words)
    return words[-1]


def find_station(client: DaangnClient, name: str) -> DaangnStation | None:
    """이름이 지하철역이면 그 역을 돌려준다 (`searchSubwayStationPois`). 이름이 정확히 같은 역만 본다.

    역 검색은 앞부분이 같은 역을 모두 주므로 ('강남' → 강남구청, 강남대), '역' 을 뗀 이름이 같은 역만 고른다.
    같은 이름의 역이 여러 곳이면 (2026-10-11 실측: 양평 → 경의중앙선·서울5호선, 중앙 → 서울4호선·부산1호선) 처음 것을
    쓰고 (당근 웹 역 화면도 이름이 같은 첫 역으로 연다) 다른 역을 `others` 에 담는다. 노선을 붙여 주면
    ('서울5호선 양평역', 같은 이름 역 안내의 이름 그대로) 그 노선이 다 있는 역만 본다.

    같은 이름 역 목록은 위치 정보가 없는 역까지 센다. 웹이 고르는 첫 역에 위치가 없는데 그 역을 빼고 둘째 역을 고르면 같은 이름 역이
    여럿인 것을 알리지 않고 다른 역을 찾게 된다 (2026-11-19 리뷰). 그래서 첫 역에 위치가 없으면 고르지 않고 에러로 알린다.

    Raises:
        LocationMissingError: 고른 첫 역에 위치 정보가 없을 때. 위치가 있는 같은 이름 역이 있으면 노선을 붙인 이름을 알린다.
    """
    *line_words, last = name.split() or ['']
    query = last.removesuffix('역')
    if not query:
        return None
    wanted = [line for word in line_words for line in word.split('·') if line]
    stations = search_stations(client, query)
    same = [
        station for station in stations
        if station.station_name == query and all(line in station.line_names for line in wanted)
    ]
    if not same:
        return None
    chosen = same[0]
    point = coordinate_point(chosen.coordinate)
    if point is None:
        located = next((station for station in same[1:] if has_location(station)), None)
        raise LocationMissingError(
            name,
            f"당근이 '{station_label(chosen)}' 의 위치를 주지 않아 주변 매물을 찾을 수 없습니다",
            hint=(
                f"위치가 있는 같은 이름 역은 노선을 붙여 찾으세요 (예: --station '{station_label(located)}')" if located
                else '그 역이 있는 동 이름이나 --lat/--lng 로 찾으세요'
            ),
        )
    return DaangnStation(
        name=station_name(chosen.station_name),
        lines=chosen.line_names,
        lat=point[0],
        lng=point[1],
        station_id=chosen.id,
        others=[
            station_label(station) + ('' if has_location(station) else NO_LOCATION) for station in same[1:]
        ],
    )
