"""생활 방식에 맞는 동네 추천(good-neighborhoods)의 상수: 통계 기준 연도·동 수·기본 지역·라이프스타일 지표."""

# 웹이 쓰는 통계 기준 연도
NEIGHBORHOOD_BASE_YEAR: str = '2025'


# 당근 웹 좋은 동네 추천이 늘 받는 동 수 (useH3ZoomConfig `Ue` 의 limit: 5)
NEIGHBORHOOD_LIMIT: int = 5


# 지역을 주지 않았을 때. 웹 지역 고르기의 첫 줄이 '서울 · 전체' 다 (MapShell `kl`, 전국은 고를 수 없다)
NEIGHBORHOOD_DEFAULT_REGION: str = '서울'


# 웹의 라이프스타일 카드 (라벨 → 지표 코드, 지표 이름, 클수록 좋은지). 2026-10 웹 번들 기준
LIFESTYLE_INDICATORS: dict[str, list[tuple[str, str, bool]]] = {
    '직장인자취': [('C004', '1인 가구 많은', True), ('E007', '교통 편리한', True), ('E006', '외식하기 좋은', True)],
    '대학생자취': [('G009', '문화시설 많은', True), ('B008', '집값 저렴한', False), ('D006', '치안 좋은', True)],
    '부부': [('A006', '산책하기 좋은', True), ('E003', '대형마트 많은', True), ('B001', '아파트 많은', True)],
    '아이와함께': [('C001', '유소년인구 많은', True), ('F004', '초등학교 많은', True), ('E005', '식료품점 많은', True)],
    '반려동물과함께': [('A006', '산책하기 좋은', True), ('E008', '반려동물 시설 많은', True), ('B002', '주택 많은', True)],
    '은퇴후': [('A006', '산책하기 좋은', True), ('G006', '노인복지시설 많은', True), ('C003', '고령인구 많은', True)],
}
