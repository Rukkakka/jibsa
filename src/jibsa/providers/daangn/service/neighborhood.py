"""생활 방식에 맞는 동네 추천 (good-neighborhoods)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.core.listing import SIDO_OFFICIAL_NAMES
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.neighborhood import (
    DaangnLivableRegionScopesRequestPayloadModel,
    DaangnNeighborhoodIndicatorModel,
    DaangnRecommendNeighborhoodsInputModel,
    DaangnRecommendNeighborhoodsRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.neighborhood import DaangnLivableSidoModel
from jibsa.providers.daangn.service.common import unwrap_graphql

from typing import Annotated


# 웹이 쓰는 통계 기준 연도
NEIGHBORHOOD_BASE_YEAR: str = '2025'
# 웹의 라이프스타일 카드 (라벨 → 지표 코드, 지표 이름, 클수록 좋은지). 2026-10 웹 번들 기준
LIFESTYLE_INDICATORS: dict[str, list[tuple[str, str, bool]]] = {
    '직장인자취': [('C004', '1인 가구 많은', True), ('E007', '교통 편리한', True), ('E006', '외식하기 좋은', True)],
    '대학생자취': [('G009', '문화시설 많은', True), ('B008', '집값 저렴한', False), ('D006', '치안 좋은', True)],
    '부부': [('A006', '산책하기 좋은', True), ('E003', '대형마트 많은', True), ('B001', '아파트 많은', True)],
    '아이와함께': [('C001', '유소년인구 많은', True), ('F004', '초등학교 많은', True), ('E005', '식료품점 많은', True)],
    '반려동물과함께': [('A006', '산책하기 좋은', True), ('E008', '반려동물 시설 많은', True), ('B002', '주택 많은', True)],
    '은퇴후': [('A006', '산책하기 좋은', True), ('G006', '노인복지시설 많은', True), ('C003', '고령인구 많은', True)],
}


class DaangnNeighborhood(BaseModel):
    """추천 동 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int | None,
        Field(description='순위')
    ] = None
    sigungu: Annotated[
        str | None,
        Field(description='시·군·구')
    ] = None
    dong: Annotated[
        str | None,
        Field(description='행정동 (예: 역삼1동)')
    ] = None
    region_id: Annotated[
        int | None,
        Field(description='당근 동 ID (법정동)')
    ] = None
    description: Annotated[
        str | None,
        Field(description='한 줄 설명')
    ] = None


class DaangnNeighborhoodsResult(BaseModel):
    """좋은 동네 추천 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    lifestyle: Annotated[str, Field(description='라이프스타일')]
    indicators: Annotated[list[str], Field(description='쓴 지표')]
    regions: Annotated[list[str], Field(description='찾은 지역 (비어 있으면 전국)')]
    returned: Annotated[int, Field(description='반환한 동 수')]
    neighborhoods: Annotated[list[DaangnNeighborhood], Field(description='순위 순 동')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='동 이름 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def _scope_sidos(scopes: list[DaangnLivableSidoModel], name: str) -> list[DaangnLivableSidoModel]:
    """시·도 이름 한 마디에 맞는 추천 지역 시·도. 앞부분이 같은 시·도('서울')가 없으면 정식 명칭으로 맞춘다.

    추천 지역은 통계 기준 연도의 시·도 이름이라 광주광역시·전라남도가 아직 따로다 (2026-10-10 실측: 코드 24·36).
    그래서 양쪽을 `SIDO_OFFICIAL_NAMES` 로 바꿔 비교하고, 전남광주통합특별시('전남')는 두 곳 모두 맞다.
    옛 이름('광주'·'광주광역시'·'전라남도')은 앞부분이 같은 시·도가 있어 그 한 곳만 찾는다. 추천 데이터가 둘을 나눠
    주니 사용자가 쓴 옛 지역으로 좁히는 것이다. 주소가 통합 이름뿐이라 둘을 가를 수 없는 `--city`(`place_in`)와
    다른 건 의도다 (2026-10-11 실측: '전남' → 광주광역시·전라남도, '전라남도'·'광주' → 그 한 곳. 결과 `regions` 에 찾은 곳이 나온다).
    """
    prefixed = [sido for sido in scopes if sido.name.startswith(name)]
    if prefixed:
        return prefixed
    official = SIDO_OFFICIAL_NAMES.get(name, name)
    return [sido for sido in scopes if SIDO_OFFICIAL_NAMES.get(sido.name, sido.name) == official]


def _region_codes(client: DaangnClient, names: list[str]) -> list[tuple[str, str]]:
    """지역 이름을 추천 지역 코드로 바꾼다 ('서울' → 11, '강남구' → 11230, '서울 중구'). (코드, 이름) 목록.

    여러 시·도에 있는 시·군·구 이름(중구·서구 등)은 시·도를 앞에 붙여야 한다. 시·도는 다른 명령의 `--city` 처럼
    줄임말·옛 이름('서울시'·'충북')과 전남광주통합특별시도 받는다 (`_scope_sidos`).

    구가 있는 시의 구는 추천 지역에 '성남시 분당구' 처럼 두 단어로 온다 (2026-10-11 실측: 경기 20곳·충북 4곳·충남 2곳·
    전북 2곳·경북 2곳·경남 5곳). 그래서 '성남시 분당구' 전체, 구 이름('분당구'), 시 이름('성남시' → 그 시의 구 모두)으로
    맞춘다.

    Raises:
        JibsaError: 이름이 여러 곳이면 REGION_AMBIGUOUS, 없으면 REGION_NOT_FOUND.
    """
    if not names:
        return []
    response = client.run_request_livable_region_scopes(
        DaangnLivableRegionScopesRequestPayloadModel(base_year=NEIGHBORHOOD_BASE_YEAR)
    )
    scopes = unwrap_graphql(response, response.data.livable_region_scopes if response.data else None, '추천 지역')
    codes: list[tuple[str, str]] = []
    for name in names:
        words = name.split()
        # 첫 단어가 시·도면 그 안에서 나머지를 찾는다 ('서울 중구', '경기 성남시 분당구')
        in_sido = _scope_sidos(scopes, words[0]) if len(words) > 1 else []
        sidos, rest = (in_sido, ' '.join(words[1:])) if in_sido else (scopes, name)
        matches = [(sido.code, sido.name) for sido in sidos if len(words) == 1 and sido.name.startswith(rest)]
        if not matches:
            matches = [
                (sigungu.code, f'{sido.name} {sigungu.name}')
                for sido in sidos for sigungu in sido.sigungus
                if rest in (sigungu.name, sigungu.name.split()[0], sigungu.name.split()[-1])
            ]
        if not matches and len(words) == 1:
            # 줄임말·옛 이름은 시·군·구 이름을 본 뒤에 맞춘다 ('광주시' 는 경기도 광주시다). 통합특별시는
            # 추천 지역에서 두 시·도로 나뉘어 있어 같은 이름이 여러 곳인 게 아니라 둘 다 넣는다
            merged = [(sido.code, sido.name) for sido in _scope_sidos(scopes, rest)]
            if merged:
                codes += merged
                continue
        if not matches:
            raise RegionNotFoundError(
                name, hint="시·도(예: '서울'), 시·군·구(예: '강남구'·'수원시'), 구가 있는 시의 구(예: '분당구') 이름으로 다시 주세요",
            )
        if len(matches) > 1 and all(label.split()[-2:-1] == [rest] for _, label in matches):
            # 구가 있는 시('수원시')는 같은 이름이 여러 곳인 게 아니라 그 시의 구들이라 모두 넣는다. 시·도 앞부분('경상' →
            # 경상북도·경상남도)은 label 이 한 낱말이라 [-2] 로 읽으면 IndexError 였다 (2026-10-11 실측). 그때는 아래 후보 안내로 간다
            codes += matches
            continue
        if len(matches) > 1:
            # 입력이 틀린 게 아니라 같은 이름이 여러 곳이라, 다른 소스처럼 후보를 주는 REGION_AMBIGUOUS 로 알린다
            raise RegionAmbiguousError(name, [label for _, label in matches], len(matches))
        codes.append(matches[0])
    return codes


def recommend_neighborhoods(
    client: DaangnClient,
    lifestyle: str,
    *,
    regions: list[str] | None = None,
    limit: int = 10,
) -> DaangnNeighborhoodsResult:
    """라이프스타일 지표로 살기 좋은 동을 순위대로 추천한다 (`recommendNeighborhoods`, 지역을 주면 요청 2회).

    당근 웹의 좋은 동네 추천과 같다. 동 상세(후기 요약 글)는 jibsa 원칙대로 읽지 않는다.

    Raises:
        JibsaError: 지역 이름이 여러 곳 (REGION_AMBIGUOUS), 없음 (REGION_NOT_FOUND), GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    indicators = LIFESTYLE_INDICATORS[lifestyle]
    codes = _region_codes(client, regions or [])
    response = client.run_request_recommend_neighborhoods(
        DaangnRecommendNeighborhoodsRequestPayloadModel(
            input=DaangnRecommendNeighborhoodsInputModel(
                indicators=[
                    DaangnNeighborhoodIndicatorModel(id=code, prefer_high=prefer_high)
                    for code, _, prefer_high in indicators
                ],
                base_year=NEIGHBORHOOD_BASE_YEAR,
                region_cd_prefixes=[code for code, _ in codes],
                limit=limit,
            )
        )
    )
    found = unwrap_graphql(response, response.data.recommend_neighborhoods if response.data else None, '좋은 동네 추천')
    neighborhoods = [
        DaangnNeighborhood(
            rank=item.rank,
            sigungu=item.sgg_nm,
            dong=item.emd_nm,
            region_id=int(item.region_id) if item.region_id and item.region_id.isdigit() else None,
            description=item.one_line_description,
        )
        for item in found[:limit]
    ]
    return DaangnNeighborhoodsResult(
        lifestyle=lifestyle,
        indicators=[label for _, label, _ in indicators],
        regions=[label for _, label in codes],
        returned=len(neighborhoods),
        neighborhoods=neighborhoods,
        notes=['dong 은 행정동(예: 역삼1동)입니다. 매물은 법정동 이름(예: 역삼동)으로 search listings 에서 찾으세요'],
    )
