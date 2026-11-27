"""구 안 인기 매물 순위(popular-listings)의 상수: 순위 최대 수와 웹이 받는 매물 종류."""

# 당근 웹 인기 매물 순위 화면(`PopularArticleRankingPanel`)이 늘 30건(`limit:30`)을 받아 30위까지만 보여 준다. 서버는 구마다
# 100건쯤까지 순위를 주지만 웹에 없는 31위 뒤는 내지 않고, 기본값도 웹과 같은 30 으로 둔다 (#215, 2026-11-11 사용자 결정. 예전에는
# 최대 100·기본 20 이었다)
POPULAR_MAX_LIMIT: int = 30


# 웹 인기 매물 순위 화면이 받는 매물 종류 (`mapSearchSchema` 의 `Qe`: 그 밖의 종류가 URL 에 오면 순위 화면을 열지 않는다)
POPULAR_PROPERTY_TYPES: tuple[str, ...] = ('원룸', '투룸', '아파트', '오피스텔')
