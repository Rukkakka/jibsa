"""단지 기능(complex)의 상수: 단지 매물 종류·정렬 표·설립 구분 이름표·평형 허용 차·가까운 학교 수."""
from jibsa.providers.dabang.api.models.request.complex.common import (
    DabangComplexCategory,
)
from jibsa.providers.dabang.api.models.request.complex.listings import (
    DabangComplexRoomOrder,
)
from jibsa.providers.dabang.service.common.constants import (
    ComplexKind,
    ListingKind,
)

from typing import NamedTuple


LISTING_KIND_BY_CATEGORY: dict[DabangComplexCategory, ListingKind] = {'apt': 'apt', 'officetel': 'officetel'}

# 단지 응답의 설립 유형 글자를 다방 학군 화면(`search schools`·`school`)의 이름으로 맞춘다. 다방은 같은 시설을 화면마다 다르게
# 부른다 (2026-11-14 실측: 방배본동 행복한 어린이집은 단지 화면 '국공립'·상세 '공공', 서울서래초병설유치원은 단지 화면
# '공립'·상세 '국공립'). 표에 없는 글자는 그대로 낸다
# 리뷰 오탐 (2026-11-14): nurseries·kindergartens 는 v0.12.0 뒤 Unreleased 에 처음 생긴 필드라 값 정리가 호환 깨짐이 아니다
# (CHANGELOG 의 호환 깨짐 절에 적지 않는다)
NURSERY_ESTABLISHMENT_LABELS: dict[str, str] = {'국공립': '공공'}
KINDER_ESTABLISHMENT_LABELS: dict[str, str] = {'공립': '국공립'}
# 요약 면적('115.54㎡')과 평형표 면적이 같은지 볼 때 허용하는 차 (둘 다 소수 둘째 자리라 반올림 차만 둔다)
AREA_MATCH_TOLERANCE_M2: float = 0.01


class ComplexSort(NamedTuple):
    """단지 매물 정렬 하나."""

    # 다방 요청의 order 값
    order: DabangComplexRoomOrder
    # `[일부]` 안내에 쓰는 정렬 이름 ('… 순으로 앞 N건')
    text: str


# 단지 매물 정렬 (--sort). 다방 웹 단지 매물 탭의 정렬 메뉴 이름 그대로다 (complex 청크 `xt`, 2026-11-13. 기본 랭킹순). 은마
# 5건이 낮은가격순 30억7000 → 34억, 높은가격순은 그 반대로 왔다 (같은 날 실측). 다방이 정렬한 순서를 그대로 낸다
COMPLEX_SORT_BY_LABEL: dict[str, ComplexSort] = {
    '랭킹순': ComplexSort('RANKING', '다방 랭킹'),
    '최신순': ComplexSort('LATEST', '다방 최신'),
    '높은가격순': ComplexSort('SELLING_HIGHEST', '다방 높은 가격'),
    '낮은가격순': ComplexSort('SELLING_LOWEST', '다방 낮은 가격'),
    '면적넓은순': ComplexSort('ROOM_SIZE_LARGEST', '다방 넓은 면적'),
    '면적좁은순': ComplexSort('ROOM_SIZE_SMALLEST', '다방 좁은 면적'),
}


# 중·고등학교·어린이집·유치원은 가까운 순 3곳. 웹 '주변 보육/교육시설' 탭이 3곳씩 보이고 '더보기' 로 3곳씩 늘린다
# (education 청크 `Y`·`X`·`Q`·`$` = 3, 2026-11-13)
NEAREST_SCHOOLS: int = 3

DEFAULT_COMPLEX_SORT: str = '랭킹순'

CATEGORY_BY_COMPLEX_KIND: dict[ComplexKind, DabangComplexCategory] = {'아파트': 'apt', '오피스텔': 'officetel'}
