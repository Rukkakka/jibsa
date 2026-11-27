"""매물 상세의 주변 (지하철역·버스 노선·배정 초등학교·개발 예정)."""

from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.listing.detail import (
    NaverDataServiceTransportV1RequestParameterModel,
    NaverDevelopmentArticleV1RequestParameterModel,
    NaverEducationBuildingSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.listing.detail import (
    NaverArticleKeyModel,
    NaverDevelopmentArticleModel,
    NaverTransportSubwayModel,
)
from jibsa.providers.naver.service.common.constants import VILLA_COMPLEX_CODES
from jibsa.providers.naver.service.common.response import result_or_none
from jibsa.providers.naver.service.common.schools import assigned_schools
from jibsa.providers.naver.service.listing.models.common import (
    NaverNearbyArea,
    NaverNearbyDevelopment,
    NaverNearbyRail,
)

from typing import Any


def _subway_label(station: NaverTransportSubwayModel) -> str | None:
    """'대청역 (3호선, 도보 9분)'. 노선마다 출구가 달라 도보 시간이 다르면 가장 짧은 것을 쓴다."""
    if not station.station_name:
        return None
    lines = list(dict.fromkeys(line.name for line in station.type_list if line.name))
    minutes = [line.walking_duration for line in station.type_list if line.walking_duration is not None]
    parts = ['·'.join(lines)] if lines else []
    if minutes:
        parts.append(f'도보 {min(minutes)}분')
    return f"{station.station_name} ({', '.join(parts)})" if parts else station.station_name


def surroundings(client: NaverClient, article_number: str, key: NaverArticleKeyModel, notes: list[str]) -> dict[str, Any]:
    """매물 주변의 지하철역·버스 노선·배정 초등학교 (1~2회 호출).

    학교는 사이트처럼 단지·동 번호가 있는 매물만 묻는다 (`has_school_lookup`. 없으면 출력에서 키를 뺀다).
    조회가 실패하거나 교통이 통째로 비어 있으면 그 값만 모름(None)으로 둔다. 조회가 실패했을 때만 `notes` 에 `[실패]` 안내를 붙인다
    (교통이 비어 온 것은 실패가 아니다).
    """
    result: dict[str, Any] = {'nearby_stations': None, 'bus_routes': None, 'schools': None, 'has_school_lookup': False}
    transport = result_or_none(
        lambda: client.run_request_data_service_transport_v1(
            NaverDataServiceTransportV1RequestParameterModel(item_id=int(article_number))
        ),
        notes=notes,
        what='교통 정보',
        unknown='모름(null)으로 낸 칸: nearby_stations, bus_routes',
    )
    # 역도 버스도 없으면 네이버에 교통 정보가 없는 매물이다 (역삼동 단지형 빌라에서 둘 다 빈 목록,
    # 2026-10-09 확인). 주변에 정말 아무것도 없다는 뜻이 아니라 모름(None)으로 둔다
    if transport is not None and (transport.subway_list or transport.bus_list):
        result['nearby_stations'] = [label for label in map(_subway_label, transport.subway_list) if label]
        # 버스 종류(간선·지선 등)는 네이버가 보내는 이름표 그대로 키로 쓴다. 거래 키(sale 등)와 달리 어떤 종류가 올지 미리 다 알 수
        # 없어, 영어로 바꾸려면 네이버에 없는 대응 표를 jibsa 가 지어야 한다 (출력 규약 '칸 이름 규칙' 의 예외)
        routes: dict[str, list[str]] = {}
        for bus in transport.bus_list:
            if bus.type_name and bus.routes:
                bucket = routes.setdefault(bus.type_name, [])
                bucket += [route for route in bus.routes if route not in bucket]
        result['bus_routes'] = routes

    ids = key.key
    if ids is None or not ids.complex_number or not ids.building_number:
        return result
    result['has_school_lookup'] = True
    schools = result_or_none(
        lambda: client.run_request_education_building_school_v1(
            NaverEducationBuildingSchoolV1RequestParameterModel(
                item_type='villa' if key.type.real_estate_type in VILLA_COMPLEX_CODES else 'complex',
                complex_number=ids.complex_number,
                building_number=ids.building_number,
            )
        ),
        notes=notes,
        what='주변 학교',
        unknown='모름(null)으로 낸 칸: schools',
    )
    if schools is not None:
        result['schools'] = assigned_schools(schools, notes)
    return result


def nearby_development(client: NaverClient, article_number: str, notes: list[str]) -> NaverNearbyDevelopment | None:
    """매물 근처의 예정 지하철역·개발 지구 (1회 호출). 웹은 매물 유형과 상관없이 늘 부른다. 조회가 실패하면 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다."""
    development: NaverDevelopmentArticleModel | None = result_or_none(
        lambda: client.run_request_development_article_v1(
            NaverDevelopmentArticleV1RequestParameterModel(article_number=article_number)
        ),
        notes=notes,
        what='주변 개발 예정',
        unknown='모름(null)으로 낸 칸: nearby_development',
    )
    if development is None:
        return None
    return NaverNearbyDevelopment(
        rail=[
            NaverNearbyRail(
                name=rail.station_name or None,
                line=rail.rail_name or None,
                # 개통 예정 연도 글자('2027')를 정수로. 비었거나 숫자가 아니면 None
                open_year=int(rail.open_date.strip()) if rail.open_date and rail.open_date.strip().isdecimal() else None,
                distance_m=rail.distance,
                walk_minutes=rail.walking_time,
            )
            for rail in development.rail_list
        ] if development.rail_list is not None else None,
        area=[
            NaverNearbyArea(
                name=area.name or None,
                type=area.type_name or None,
                # 단계는 숫자일 수 있어 `or None` 이면 0 이 모름으로 바뀐다. 빈 글자만 모름(None)으로 본다
                step=None if area.step == '' else area.step,
                project_period=area.period or None,
            )
            for area in development.jigu_list
        ] if development.jigu_list is not None else None,
    )
