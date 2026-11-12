from functools import cached_property
from urllib.parse import quote

from httpx import (
    AsyncClient,
    Client,
)
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from jibsa.core.browser import NAVIGATION_EXTENSION
from jibsa.core.http import (
    BaseHTTPClient,
    create_base_url,
    log_retry_before_sleep,
    raise_for_status,
    should_retry_idempotent,
    wait_retry_after,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.parser import (
    parse_articles_html,
    parse_complexes_html,
    parse_map_reviews_html,
)
from jibsa.providers.daangn.api.request.commute import (
    DaangnCommuteStationArticleConnectionRequestPayloadModel,
    DaangnCommuteStationsRequestPayloadModel,
    DaangnNearestCommuteStationRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.compare import (
    DaangnComplexCompareRequestPayloadModel,
    DaangnComplexesByOriginalComplexIdsRequestPayloadModel,
    DaangnComplexRegionRequestPayloadModel,
    DaangnNearbyComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.complex import (
    DaangnComplexArticlesRequestPayloadModel,
    DaangnComplexByClusterIdRequestPayloadModel,
    DaangnComplexesRequestParameterModel,
    DaangnSearchComplexesRequestPayloadModel,
    DaangnSearchComplexesViewportRequestPayloadModel,
    DaangnTrendingComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.listing import (
    DaangnArticlesRequestParameterModel,
)
from jibsa.providers.daangn.api.request.neighborhood import (
    DaangnLivableRegionScopesRequestPayloadModel,
    DaangnRecommendNeighborhoodsRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.popular import (
    DaangnGetViewRankingArticlesRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.real_price import (
    DaangnArticleByOriginalArticleIdRequestPayloadModel,
    DaangnComplexByOriginalIdRequestPayloadModel,
    DaangnComplexPriceChartRequestPayloadModel,
    DaangnRealsaleFeedRequestPayloadModel,
    DaangnRealsaleFeedSummaryRequestPayloadModel,
    DaangnRealsaleNewHighFeedRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.region import (
    DaangnGetRegionByCoordinateRequestPayloadModel,
    DaangnSearchAddressRequestPayloadModel,
    DaangnSearchRegionRequestPayloadModel,
    DaangnSearchSchoolPoisRequestPayloadModel,
    DaangnSearchSubwayStationPoisRequestPayloadModel,
    DaangnUnitByAddressRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.review import (
    DaangnLivedReviewsByRegionRequestPayloadModel,
    DaangnMapReviewsRequestParameterModel,
)
from jibsa.providers.daangn.api.request.school import (
    DaangnComplexSchoolsRequestPayloadModel,
    DaangnPreschoolByNoRequestPayloadModel,
    DaangnSchoolByCodeRequestPayloadModel,
    DaangnSearchSchoolsRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.search import (
    DaangnArticleByClusterIdRequestPayloadModel,
    DaangnArticleClustersRequestPayloadModel,
    DaangnArticleFeedRequestPayloadModel,
    DaangnArticlesCountRequestPayloadModel,
    DaangnSubwayStationArticleConnectionRequestPayloadModel,
    DaangnUniversityArticleConnectionRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.commute import (
    DaangnCommuteStationArticleConnectionResponseModel,
    DaangnCommuteStationsResponseModel,
    DaangnNearestCommuteStationResponseModel,
)
from jibsa.providers.daangn.api.response.compare import (
    DaangnComplexCompareResponseModel,
    DaangnComplexesByOriginalComplexIdsResponseModel,
    DaangnComplexRegionResponseModel,
    DaangnNearbyComplexesResponseModel,
)
from jibsa.providers.daangn.api.response.complex import (
    DaangnComplexArticlesResponseModel,
    DaangnComplexByClusterIdResponseModel,
    DaangnComplexesResponseModel,
    DaangnSearchComplexesResponseModel,
    DaangnSearchComplexesViewportResponseModel,
    DaangnTrendingComplexesResponseModel,
)
from jibsa.providers.daangn.api.response.listing import DaangnArticlesResponseModel
from jibsa.providers.daangn.api.response.neighborhood import (
    DaangnLivableRegionScopesResponseModel,
    DaangnRecommendNeighborhoodsResponseModel,
)
from jibsa.providers.daangn.api.response.popular import (
    DaangnGetViewRankingArticlesResponseModel,
)
from jibsa.providers.daangn.api.response.real_price import (
    DaangnArticleByOriginalArticleIdResponseModel,
    DaangnComplexByOriginalIdResponseModel,
    DaangnComplexPriceChartResponseModel,
    DaangnRealsaleFeedResponseModel,
    DaangnRealsaleFeedSummaryResponseModel,
    DaangnRealsaleNewHighFeedResponseModel,
)
from jibsa.providers.daangn.api.response.region import (
    DaangnGetRegionByCoordinateResponseModel,
    DaangnSearchAddressResponseModel,
    DaangnSearchRegionResponseModel,
    DaangnSearchSchoolPoisResponseModel,
    DaangnSearchSubwayStationPoisResponseModel,
    DaangnUnitByAddressResponseModel,
)
from jibsa.providers.daangn.api.response.review import (
    DaangnLivedReviewsByRegionResponseModel,
    DaangnMapReviewsResponseModel,
)
from jibsa.providers.daangn.api.response.school import (
    DaangnComplexSchoolsResponseModel,
    DaangnPreschoolByNoResponseModel,
    DaangnSchoolByCodeResponseModel,
    DaangnSearchSchoolsResponseModel,
)
from jibsa.providers.daangn.api.response.search import (
    DaangnArticleByClusterIdResponseModel,
    DaangnArticleClustersResponseModel,
    DaangnArticleFeedResponseModel,
    DaangnArticlesCountResponseModel,
    DaangnSubwayStationArticleConnectionResponseModel,
    DaangnUniversityArticleConnectionResponseModel,
)

from typing import ClassVar


daangn_retry = retry(
    retry=retry_if_exception(should_retry_idempotent),
    stop=stop_after_attempt(3),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""조회 전용 엔드포인트 공통 재시도: 최대 3회, 1초(또는 `Retry-After`) 간격, 5xx·429·timeout·transport 오류만."""

# 페이지 HTML 요청(매물 상세·단지·구 후기 페이지)에 다는 표시. 웹에서는 API 요청이 아니라 페이지 열기라, transport 가 크롬이
# 페이지를 열 때 붙이는 `accept`·`upgrade-insecure-requests` 를 붙인다 (`core/browser.py` 의 `NAVIGATION_EXTENSION`)
PAGE_REQUEST_EXTENSIONS: dict[str, object] = {NAVIGATION_EXTENSION: True}


class DaangnClient(BaseHTTPClient):
    """당근부동산 (realty.daangn.com) 비공식 클라이언트.

    매물 상세는 SSR HTML 에 박힌 라우터 상태의 Relay 스토어를 파싱한다. 매물 목록은 웹이 쓰는
    GraphQL(`realty.kr.karrotmarket.com/graphql`)로 받는다. 동 매물은 웹 지도에서 동을 누른 목록과 같은
    `articleByClusterId`(`REGION:<동 ID>`)로, 그 동의 매물 수는 동 거품 `articleClusters` 로 받는다. 지도 범위
    매물은 웹 지도 목록처럼 좌표 범위의 `articleFeed` 로, 그 수는 `articlesCount` 로 받는다. 좌표 → 동은
    `getRegionByCoordinate`. 단지 정보는 단지 페이지(`/complexes/{originalId}`)의 스토어를,
    단지 이름 검색은 `searchComplexes`, 단지 실거래가는 `complexByOriginalId`,
    매물 실거래가(매물이 있는 건물의 비슷한 면적 거래)는 `articleByOriginalArticleId`, 동·구의 최근
    실거래와 신고가는 `realsaleFeed`·`realsaleNewHighFeed`, 출퇴근 검색은 `nearestCommuteStation`
    (회사 → 가까운 역), `commuteStations` (그 역에서 갈 수 있는 역 전부), `commuteStationArticleConnection`
    (역 주변 매물), 동네 후기는 구의 후기 페이지(`/map/{name1}/{name2}/reviews`, 후기 많은 단지)와
    `livedReviewsByRegion` (후기 유무와 지역 후기 수) 를 쓴다. 후기 페이지는
    경로 세그먼트를 이어 `map_reviews` 로 부른다. 단지 매물 목록도 루트 필드가 단지
    실거래가와 같은 `complexByOriginalId` 라 `complex_articles` 로 부른다. 동·구 단지 목록(웹 지도 단지 탭)은
    `complexByClusterId` 다. 학교 이름 검색은 `searchSchools`,
    학교 정보와 배정 단지는 `schoolByCode`. 단지 시세 그래프는 루트가 `node(id:)` 라 `complex_price_chart` 로, 단지 근처
    어린이집·유치원(웹 단지 화면의 학군)은 루트 필드가 `complexByOriginalId` 라 `complex_schools` 로 부른다. 지역·역·대학 이름은 웹 지도 검색창과 같은 `searchRegion`·`searchSubwayStationPois`·`searchSchoolPois` 로
    찾고, 대학 주변 매물은 웹 대학 페이지의 `universityArticleConnection` 이다. 도로명 주소는 웹 검색창 주소 모드의
    `searchAddress` 로 후보를 찾고 `unitByAddress` 로 좌표를 받는다. 지도 범위 단지 목록(웹 지도 단지 탭의 '이 영역 단지')은
    루트 필드가 단지 이름 검색과 같은 `searchComplexes` 라 `search_complexes_viewport` 로 부른다. 지역 실거래 화면 머리의
    요약(공개일·매매 수·신고가 수)은 `realsaleFeedSummary`·`realsaleNewHighFeedSummary` 가 한 오퍼레이션이라
    `realsale_feed_summary` 로 부른다.
    인증은 필요 없다. 금액은 **만원** 단위이고, 다음만 **원** 단위라 service 가 만원으로 바꾼다: 시세 그래프의 월별 평균
    (`averageAmount`)과 최근 KB 매매 시세(`latestKbSale`), 매물 상세의 중개보수(`brokerCommissions`), 단지 비교 칸의
    ㎡당 관리비(`costPerSquareMeter`). 단지 비교 칸의 KB 시세(`kbPrices`)는 만원이다.

    action id 는 페이지 경로면 경로 파라미터를 뺀 첫 세그먼트를 쓴다 (`/articles/{...}` → `articles`). GraphQL 은 경로가 하나라
    루트 필드 이름을 쓴다 (`articleFeed` → `article_feed`).

    GraphQL 은 persisted query 만 받는다. 쿼리 본문을 보내면 `PersistedQueryOnly` 로
    거절하고, 웹 번들에 박힌 해시(`*_query_id`)를 보내야 한다. 웹이 쿼리를 바꾸면 해시가
    `PERSISTED_QUERY_NOT_IN_LIST` 로 거절된다. GraphQL 좌표는 문자열로 보내야 한다
    (숫자면 이유 없이 "알 수 없는 오류").

    Args:
        host: 부동산 호스트 (스킴 제외). Defaults to 'realty.daangn.com'.
        graphql_host: GraphQL 호스트. Defaults to 'realty.kr.karrotmarket.com'.
        rate_limit: 요청 제한 정책. Defaults to 0.5초 간격·분당 60회·429 후 5분 쿨다운.

    Attributes:
        base_url: `url_schema` 와 `host` 로 만든 베이스 URL.
        graphql_url: GraphQL 의 절대 URL.

    Example:
        >>> with DaangnClient() as client:
        ...     client.run_request_articles(DaangnArticlesRequestParameterModel(original_id=1000001))
    """

    articles_endpoint: ClassVar[str] = '/articles/{original_id}'
    complexes_endpoint: ClassVar[str] = '/complexes/{original_id}'
    map_reviews_endpoint: ClassVar[str] = '/map/{name1}/{name2}/reviews'
    graphql_endpoint: ClassVar[str] = '/graphql'
    # 아래 해시는 웹 번들에서 꺼냈다. 주석은 웹의 쿼리 이름과 번들 파일이고, 괄호 안의 2026-11 표시는 그 해시를 꺼냈거나
    # 다시 꺼내 맞춘 번들이다. 2026-11-v58·2026-11-v73 은 웹 배포 이름(번들 주소 `…/realty-web/2026-11-v73-cf23fe5/…` 의
    # 앞부분)이고, '2026-11-12 번들' 은 그날 받은 번들로 배포 이름을 적어 두지 않았다. 표시가 없는 해시는 2026-10-v58 번들에서
    # 꺼냈다
    # MapShell-*.js 의 RegionArticleListPanelPaginationQuery
    article_feed_query_id: ClassVar[str] = '530da3a4b31d9e972d6e4c28746b3870ddfaedbb6c2dbeb14f84a780811d95df'
    # MapView-*.js 의 MapFloatingControlsArticleCountQuery
    articles_count_query_id: ClassVar[str] = 'f2120ef2ef8147690d1036f7a44b7a77ba9bb24e27a1eab2e5fb9e3de1e6c4bc'
    # regionByCoordinateQuery-*.js 의 regionByCoordinateQuery
    get_region_by_coordinate_query_id: ClassVar[str] = '1c663788669807706f19ece384062e647238dc7c459298267c72234d6b6e381c'
    # fetchRegionResult-*.js 의 fetchComplexSearchResultQuery
    search_complexes_query_id: ClassVar[str] = 'd5c4d68d4e00b8d0e108ad0eff22975e957d4e10d707c3ddddbe8c3ced72a820'
    # ComplexTopicPanelQuery-*.js 의 useTransactionComplexPagination_Query (단지 실거래가, 2026-11-v58)
    complex_by_original_id_query_id: ClassVar[str] = '0759ba56316842fa18e7e3379d7c1c449ffa7591fbf22b6fcba6911a32535220'
    # ComplexArticleListPanel-*.js 의 ComplexArticleListPanelQuery (단지 매물 목록)
    complex_articles_query_id: ClassVar[str] = '0df6a807dedf33d8ab07ef486a9f1980a5652c41396eafc4237274913ab48f7a'
    # ComplexTopicPanelQuery-*.js 의 useTransactionArticlePagination_Query (매물 실거래가, 2026-11-v58)
    article_by_original_article_id_query_id: ClassVar[str] = (
        '92851d5818157db86f12ec367d39e8896eef0cd2c3ed6d9639c6aa7cad86c7d6'
    )
    # RealsaleFeedListQuery-*.js 의 RealsaleFeedListQuery (지역 최근 실거래, 2026-11-v58)
    realsale_feed_query_id: ClassVar[str] = '6df5d0f33b925944272fdea4f75f0329ea18ad14f59294dd128865d895249e70'
    # MapShell-*.js 의 NewHighFeedListQuery (지역 신고가)
    realsale_new_high_feed_query_id: ClassVar[str] = '2569f5b4127eb1c87cc5239f14ffe581caace14f1e3a9bd4cc809aad2ec1e439'
    # MapShell-*.js 의 RealsaleFeedTitleSummaryQuery (지역 실거래 화면 머리의 공개일·매매 수·신고가 수, 2026-11-12 번들)
    realsale_feed_summary_query_id: ClassVar[str] = '8a0629a1e9ff4e44cfebe75a74dc94243a8c08339621f0e133b75aae07cc3940'
    # useNearestStation-*.js 의 CommuteMapViewNearestQuery
    nearest_commute_station_query_id: ClassVar[str] = '3d03f833ea763d068a3bf71e3555b82947077f6ad92cec890eb5434996501781'
    # useNearestStation-*.js 의 CommuteMapViewPinsQuery (commuteStations: 회사 역에서 갈 수 있는 역 전부, 페이지 없음. 2026-11-v73)
    commute_stations_query_id: ClassVar[str] = '829225ee221a10220b3b27ffff768e29f200ac51caa1d14669fb32011196d675'
    # CommuteStationDetailView-*.js 의 CommuteStationDetailPaginationQuery (첫 페이지도 after 없이 같은 결과)
    commute_station_article_connection_query_id: ClassVar[str] = (
        '361740aa91f841a681d3bd7d954d4b4de96d89e629d4eec26d901248668ff97d'
    )
    # index-*.js 의 RegionLivedReviewListPanelQuery (동네 후기 목록, 2026-11-v58)
    lived_reviews_by_region_query_id: ClassVar[str] = '304737ba85360e2cc892063d12508accde16434cbb05f2cece753686696b46f6'
    # ComplexListPanel-*.js 의 ComplexListPanelClusterPaginationQuery (동·구 단지 목록, 2026-11-12 번들. 첫 쪽 쿼리
    # ComplexListPanelClusterQuery 3c3ed921… 와 변수가 같아 모든 쪽을 이것으로 받는다. 예전에 쓰던 지도 범위 쿼리
    # ComplexListPanelViewportQuery(searchComplexes, cd05a288…)는 웹이 동 ID 로 부르지 않는다)
    complex_by_cluster_id_query_id: ClassVar[str] = '1db2d2a0ba05c0068a93563aff1f224c01cb3cd7ddaf66e381ee63bd7c6cb10c'
    # ComplexListPanel-*.js 의 ComplexListPanelViewportQuery (지도 범위 단지 목록, 2026-11-12 번들. 다음 쪽 쿼리
    # ComplexListPanelViewportPaginationQuery 221b0d61… 와 변수가 같아 첫 쪽 쿼리로 모든 쪽을 받는다)
    search_complexes_viewport_query_id: ClassVar[str] = 'cd05a28829852db94c3d797d2da1bd51a7e3e1415622a37ef916d23a89545b24'
    # MapShell-*.js 의 fetchSchoolSearchResultQuery (학교 이름 검색)
    search_schools_query_id: ClassVar[str] = '223034a6d57e1155443f5560d116dc09839be868c3cda4d95e2434c0304e9731'
    # ComplexTopicPanelQuery-*.js 의 SchoolDetailQuery (학교 정보·배정 단지, 2026-11-v58)
    school_by_code_query_id: ClassVar[str] = 'c7d4ef1929ade503520753cab10982d7de78950bd16da913fdffcd43d8aead25'
    # ComplexTopicPanelQuery-*.js 의 useTransactionComplexRefetchQuery (단지 화면 시세 그래프, 2026-11-12 번들). 예전에 쓰던
    # 단지 비교 화면 차트 ComplexComparePriceChartQuery(be9955e8…)는 평형 타입 코드로 거를 수 없다
    complex_price_chart_query_id: ClassVar[str] = 'eab73987f6c8dc1ca3b90bd7342747a0a1141db667b6949bae83b3401d81e3c2'
    # index-*.js 의 fetchSubwayResultQuery (역 이름 검색)
    search_subway_station_pois_query_id: ClassVar[str] = (
        'f765b400e0498e4a4f0f7fe8adef1d2baffb46b5132227996cb4dbdb622c31cb'
    )
    # fetchRegionResult-*.js 의 fetchRegionResultQuery (지도 검색창 지역 검색, 2026-11-v58)
    search_region_query_id: ClassVar[str] = '0400d3772118e5cbdce1f81f3ef5c26e0164d92847f1cdb9e4dbc2756b11cf90'
    # MapShell-*.js 의 fetchUniversitySearchResultQuery (지도 검색창 대학 검색, 2026-11-v58)
    search_school_pois_query_id: ClassVar[str] = 'de3e603f06c8a9374f4c2bb183c8492aade4f7721eb770eab0b59b2e4c5ba604'
    # MapShell-*.js 의 fetchAddressResultQuery (검색창 주소 모드의 도로명 주소 검색, 2026-11-12 번들)
    search_address_query_id: ClassVar[str] = '681904380a1ddbca5e91d2323d7db3e812984685aabf62c2fa9b830b9565dab8'
    # MapShell-*.js 의 getPlaceByJusoAddressQuery (주소 후보 → 좌표·단지·건물, 2026-11-12 번들)
    unit_by_address_query_id: ClassVar[str] = '0bd0f71ca6dea94f68c0bef2a6afd3f392107294045374697558ed5f4000dd7b'
    # ArticleListPanel-*.js 의 ArticleListPanelPaginationQuery (지도 동 클러스터 매물 목록, 2026-11-v58)
    article_by_cluster_id_query_id: ClassVar[str] = (
        'efc299738ff3513c3ec35223e48fe3cd99788c69e3d932b217ca7bebf2803e12'
    )
    # MapView-*.js 의 MapViewRegionClustersQuery (지도 지역 거품의 매물 수, 2026-11-v58)
    article_clusters_query_id: ClassVar[str] = 'b7ad686faa8395b87280d7f72ae48f4ca165ea893bd3850a8507bd55c99715c9'
    # MapShell-*.js 의 UniversityArticleListPanelPaginationQuery (대학 주변 매물, 2026-11-v58)
    university_article_connection_query_id: ClassVar[str] = (
        '29cb85490d868a0170997a70fbac6c26e9b5f0f97d7874a98edb2dd5229c90f4'
    )
    # MapShell-*.js 의 SubwayArticleListPanelPaginationQuery (역 주변 매물)
    subway_station_article_connection_query_id: ClassVar[str] = (
        '246140eaaca77d3bcc264e76bc4feb013fe9c0b10fc91b077ef9f235658b0d27'
    )
    # ComplexSchoolListPanel-*.js 의 ComplexSchoolListPanelQuery (단지 근처 학교·어린이집, 2026-11-v58)
    complex_schools_query_id: ClassVar[str] = '94fe92d51a7ff59c79d2d17b050ab144c8eada7d40e933e69f660ef5a6ee4b20'
    # ComplexTopicPanelQuery-*.js 의 PreschoolDetailPanelQuery (어린이집·유치원 상세, 2026-11-v58)
    preschool_by_no_query_id: ClassVar[str] = '893707bfdc3578256c583daead160165736afc5b23579003885a7ba194f16738'
    # compare-*.js 의 ComplexCompareColumnQuery (단지 비교 칸)
    complex_compare_query_id: ClassVar[str] = '74b409fd6cc63f290120fe7ea8bca376653d37db0cf977a4227f1b2d5233ff0f'
    # ComplexTopicPanelQuery-*.js 의 ComplexNearbySectionQuery (같은 동 단지, 2026-11-v58)
    nearby_complexes_query_id: ClassVar[str] = '0239b1a589cb97132006385870cdad55dc496c21977dc540a47b28099a0f8258'
    # ComplexListPanel-*.js 의 ComplexListPanelMapPinsQuery (지도 단지 목록 카드, 2026-11-12 번들). 예전 단지 카드
    # ComplexNearbySectionCardsQuery(ba9845…)는 11월 번들에 없어 바꿨다
    complexes_by_original_complex_ids_query_id: ClassVar[str] = (
        'a0f16d6a55e8c814d7c4bf5d01c459bc6110e244e168a3e0b67e05b22d0fd2a7'
    )
    # index-*.js 의 ComplexIdSeoQuery (단지 페이지의 지역. 같은 동 단지의 동 ID 를 받는다, 2026-11-12 번들)
    complex_region_query_id: ClassVar[str] = '676e48897087fd0a6c6619e6e46a995b3a7f44089f50919fc91e47ef3b7afb68'
    # MapShell-*.js 의 GoodNeighborhoodRegionQuery (좋은 동네 추천 지역 목록)
    livable_region_scopes_query_id: ClassVar[str] = '73def70680c51b8b8c9911015b14fe721bb7aaf1a689b1c496693d7bc2003ba7'
    # useH3ZoomConfig-*.js 의 GoodNeighborhoodResultQuery (좋은 동네 추천)
    recommend_neighborhoods_query_id: ClassVar[str] = '84e6cc44b469600a004aa2bc97aad9e972258212585ed52171d14919d2b3d238'
    # ComplexTopicPanelQuery-*.js 의 TrendingComplexListPanelListQuery (인기 급상승 단지 더 보기 패널, first 50, 2026-11-12
    # 번들). 예전에 쓰던 홈 섹션 HomeTrendingComplexSectionListQuery(528cbae2…, first 5)와 필드가 같다
    trending_complexes_query_id: ClassVar[str] = '2be8a295c5539bc6a52076ad9864f51e42c47fcbbc9a3c657749138450067044'
    # PopularArticleRankingPanel-*.js 의 PopularArticleRankingPanelQuery (조회수 많은 매물)
    get_view_ranking_articles_query_id: ClassVar[str] = (
        '4f9f7ec5755d40d9903ae145b9343c74b9e46d914c0f5f1fcfac4864d6cc054d'
    )

    source_name: ClassVar[str] = 'daangn'
    default_rate_limit: ClassVar[dict[str, object]] = {
        'min_interval': 0.5,
        'max_per_minute': 60,
        'cooldown': 300,
    }

    # 당근 웹 지도 화면이다 (Referer 가 자연스럽다). 기다릴 쿠키가 없어 load 직후 떠나므로 첫 화면이 부르는 사이트
    # API 는 load 까지의 GraphQL 2건이다 (2026-11-10 실측: 홈도 1건. 페이지를 그대로 두면 10초에 94건이라, 예전에 적었던
    # '홈 55·지도 22'는 머문 시간에 따른 수였다). 한 동의 경로라 당근이 지도 주소 꼴을 바꾸면 첫 화면이 4xx 가 되어 모든 당근
    # 명령이 UPSTREAM_ERROR 로 끝난다. API 경로가 바뀔 때와 같아 매일 API 감시가 잡으면 이 주소를 고친다. 홈으로 다시 여는
    # 경로는 두지 않는다 (평소에 타지 않는 경로라 깨져도 알 수 없다)
    browser_entry_url: ClassVar[str] = 'https://realty.daangn.com/map/서울특별시/강남구/역삼동'
    # 첫 화면에서 생기는 쿠키는 분석용(_ga·_clck)뿐이고 당근 API 는 쿠키 없이 응답해 기다릴 쿠키가 없다 (같은 날 실측)
    browser_ready_cookie: ClassVar[str | None] = None

    host: str = 'realty.daangn.com'

    graphql_host: str = 'realty.kr.karrotmarket.com'

    @property
    def base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.host
        )

    @property
    def graphql_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.graphql_host
        ) + self.graphql_endpoint

    @property
    def browser_api_hosts(self) -> frozenset[str]:
        # 첫 화면(realty.daangn.com)이 스스로 부르는 GraphQL 도 요청 제한에 센다
        return frozenset({self.host, self.graphql_host})

    @property
    def graphql_header(self) -> dict[str, str]:
        # 웹 API 클라이언트(ky)가 보내기 전 훅에서 모든 요청에 붙이는 헤더. 로그인 토큰(`Authorization`)은 로그인했을 때만,
        # `x-realty-ip`·`x-realty-ssr-user-agent` 는 서버 렌더링 때만 붙는다 (2026-11-12 번들·실측). Accept 는 넣지 않아
        # fetch 기본값 `*/*` 이고 content-type 은 httpx 가 `json=` 으로 붙인다. 없으면 403 Forbidden 이다 (같은 날 실측).
        # UA·Origin·Referer 는 브라우저가 붙인다 (`core/browser.py`)
        return {
            'x-realty-platform': 'realty-web',
        }

    def _graphql_body(self, payload: RequestModel, query_id: str) -> dict[str, object]:
        return {
            'variables': payload.model_dump(by_alias=True, exclude_none=True),
            'extensions': {'persistedQuery': {'version': 1, 'sha256Hash': query_id}},
        }

    @cached_property
    def _client(self) -> Client:
        # 모든 요청에 붙일 헤더가 없어 기본 헤더를 두지 않는다. GraphQL 은 `graphql_header`, 페이지 HTML 은
        # `PAGE_REQUEST_EXTENSIONS` 로 요청마다 붙인다.
        # 리다이렉트는 브라우저 fetch 가 따라간다. 프록시는 브라우저가 쓴다 (httpx 에 넘기면 그 mount 가 transport 를 건너뛴다)
        return Client(
            base_url=self.base_url,
            event_hooks=self.rate_limit_hooks(),
            timeout=self.timeout,
            transport=self.browser_transport()
        )

    @cached_property
    def _async_client(self) -> AsyncClient:
        return AsyncClient(
            base_url=self.base_url,
            event_hooks=self.async_rate_limit_hooks(),
            timeout=self.timeout,
            transport=self.async_browser_transport()
        )

    @daangn_retry
    def run_request_articles(
        self,
        parameter: DaangnArticlesRequestParameterModel
    ) -> DaangnArticlesResponseModel:
        """Fetch one listing via `GET /articles/{originalId}`.

        Retries up to 3 attempts on HTTP 5xx/429 responses and httpx
        timeout/transport errors, waiting 1s between attempts or, on a 429,
        the server's `Retry-After` (capped at 60s); any other error, and the
        final failed attempt, is raised. 요청 제한이 켜져 있으면(기본) 429 는
        재시도 없이 곧바로 `RateLimitedError` (쿨다운) 로 끝난다. HTML 의
        Relay 스토어를 파싱한다. 없는 매물이면 404 로 `ResponseStatusError` 가 난다.

        Args:
            parameter: `original_id` (숫자 매물 ID).

        Returns:
            DaangnArticlesResponseModel: 제목(JSON-LD)과 본문·옵션·관리비가
                채워진 매물.

        Raises:
            RelayStoreNotFoundError: 페이지에 스토어가 없을 때 (구조 변경).
            RelayRecordNotFoundError: 스토어에 해당 매물이 없을 때 (구조 변경).
        """
        response = self._client.get(
            url=self.articles_endpoint.format(original_id=parameter.original_id),
            extensions=PAGE_REQUEST_EXTENSIONS
        )
        raise_for_status(response=response)
        return parse_articles_html(response.text, parameter.original_id)

    @daangn_retry
    async def arun_request_articles(
        self,
        parameter: DaangnArticlesRequestParameterModel
    ) -> DaangnArticlesResponseModel:
        """Async variant of `run_request_articles`."""
        response = await self._async_client.get(
            url=self.articles_endpoint.format(original_id=parameter.original_id),
            extensions=PAGE_REQUEST_EXTENSIONS
        )
        raise_for_status(response=response)
        return parse_articles_html(response.text, parameter.original_id)

    @daangn_retry
    def run_request_article_feed(
        self,
        payload: DaangnArticleFeedRequestPayloadModel
    ) -> DaangnArticleFeedResponseModel:
        """Fetch a filtered listing feed via `POST realty.kr.karrotmarket.com/graphql` (`articleFeed`).

        Same retry behaviour as `run_request_articles` (조회 전용이라 POST 라도
        재시도한다). GraphQL 실패(해시 거절, 잘못된 조건)도 HTTP 200 의 `errors` 로 오며
        여기서 판정하지 않는다. 웹 지도 화면의 매물 목록처럼 좌표 범위로 부른다.

        Args:
            payload: 지도 화면의 좌표 범위(`input.locationFilter`)와 H3 해상도(`input.resolution`),
                매물 조건(`input.propertyFilter`), 페이지 크기(`first`)와 커서(`after`).

        Returns:
            DaangnArticleFeedResponseModel: 최근 게시 순 매물 카드와 다음 페이지 커서, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleFeedResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_article_feed(
        self,
        payload: DaangnArticleFeedRequestPayloadModel
    ) -> DaangnArticleFeedResponseModel:
        """Async variant of `run_request_article_feed`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleFeedResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_articles_count(
        self,
        payload: DaangnArticlesCountRequestPayloadModel
    ) -> DaangnArticlesCountResponseModel:
        """Count listings matching a filter via `POST realty.kr.karrotmarket.com/graphql` (`articlesCount`).

        Same retry behaviour as `run_request_article_feed`. 웹 지도 화면의 '매물 N개' 다. `articleFeed` 와 같은
        좌표 범위·조건을 받는다. 1000 에서 잘린다 (웹은 '999+').

        Args:
            payload: 지도 화면의 좌표 범위(`input.locationFilter`)와 H3 해상도(`input.resolution`),
                매물 조건(`input.propertyFilter`).

        Returns:
            DaangnArticlesCountResponseModel: 조건에 맞는 매물 수, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.articles_count_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticlesCountResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_articles_count(
        self,
        payload: DaangnArticlesCountRequestPayloadModel
    ) -> DaangnArticlesCountResponseModel:
        """Async variant of `run_request_articles_count`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.articles_count_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticlesCountResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_get_region_by_coordinate(
        self,
        payload: DaangnGetRegionByCoordinateRequestPayloadModel
    ) -> DaangnGetRegionByCoordinateResponseModel:
        """Resolve a coordinate to a region via `POST realty.kr.karrotmarket.com/graphql` (`getRegionByCoordinate`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 좌표.

        Returns:
            DaangnGetRegionByCoordinateResponseModel: 좌표가 속한 지역 (시도/구/동, 지역 ID, 중심 좌표).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.get_region_by_coordinate_query_id)
        )
        raise_for_status(response=response)
        return DaangnGetRegionByCoordinateResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_get_region_by_coordinate(
        self,
        payload: DaangnGetRegionByCoordinateRequestPayloadModel
    ) -> DaangnGetRegionByCoordinateResponseModel:
        """Async variant of `run_request_get_region_by_coordinate`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.get_region_by_coordinate_query_id)
        )
        raise_for_status(response=response)
        return DaangnGetRegionByCoordinateResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complexes(
        self,
        parameter: DaangnComplexesRequestParameterModel
    ) -> DaangnComplexesResponseModel:
        """Fetch one complex via `GET /complexes/{originalId}`.

        Same retry behaviour as `run_request_articles`. 없는 단지면 404 로
        `ResponseStatusError` 가 난다. 페이지가 약 2MB 로 크다 (시세 그래프·학교 도보 경로가 들어 있다).

        Args:
            parameter: `original_id` (숫자 단지 ID).

        Returns:
            DaangnComplexesResponseModel: 단지 기본 정보·평형·역·학교·매물 수·후기 수.

        Raises:
            RelayStoreNotFoundError: 페이지에 스토어가 없을 때 (구조 변경).
        """
        response = self._client.get(
            url=self.complexes_endpoint.format(original_id=parameter.original_id),
            extensions=PAGE_REQUEST_EXTENSIONS
        )
        raise_for_status(response=response)
        return parse_complexes_html(response.text)

    @daangn_retry
    async def arun_request_complexes(
        self,
        parameter: DaangnComplexesRequestParameterModel
    ) -> DaangnComplexesResponseModel:
        """Async variant of `run_request_complexes`."""
        response = await self._async_client.get(
            url=self.complexes_endpoint.format(original_id=parameter.original_id),
            extensions=PAGE_REQUEST_EXTENSIONS
        )
        raise_for_status(response=response)
        return parse_complexes_html(response.text)

    @daangn_retry
    def run_request_search_complexes(
        self,
        payload: DaangnSearchComplexesRequestPayloadModel
    ) -> DaangnSearchComplexesResponseModel:
        """Search complexes by name via `POST realty.kr.karrotmarket.com/graphql` (`searchComplexes`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 단지 이름(`input.name`)과 페이지 크기(`first`)·커서(`after`).

        Returns:
            DaangnSearchComplexesResponseModel: 이름이 비슷한 단지 (전국).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_complexes(
        self,
        payload: DaangnSearchComplexesRequestPayloadModel
    ) -> DaangnSearchComplexesResponseModel:
        """Async variant of `run_request_search_complexes`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_by_original_id(
        self,
        payload: DaangnComplexByOriginalIdRequestPayloadModel
    ) -> DaangnComplexByOriginalIdResponseModel:
        """Fetch a complex's real transactions via `POST realty.kr.karrotmarket.com/graphql` (`complexByOriginalId`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 단지 ID, 매매·전월세 페이지 크기와 커서, 전용면적 묶음.

        Returns:
            DaangnComplexByOriginalIdResponseModel: 최근 계약 순 매매·전월세 실거래 (국토부 신고 기준).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_by_original_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexByOriginalIdResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_by_original_id(
        self,
        payload: DaangnComplexByOriginalIdRequestPayloadModel
    ) -> DaangnComplexByOriginalIdResponseModel:
        """Async variant of `run_request_complex_by_original_id`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_by_original_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexByOriginalIdResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_article_by_original_article_id(
        self,
        payload: DaangnArticleByOriginalArticleIdRequestPayloadModel
    ) -> DaangnArticleByOriginalArticleIdResponseModel:
        """Fetch a listing's building transactions via `POST realty.kr.karrotmarket.com/graphql` (`articleByOriginalArticleId`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다
        (없는 매물은 `recordNotFound`).

        Args:
            payload: 매물 ID, 매매·전월세 페이지 크기와 커서.

        Returns:
            DaangnArticleByOriginalArticleIdResponseModel: 매물이 있는 건물의 비슷한 면적 실거래 (최근 계약 순).
                당근이 건물을 찾지 못한 매물(빌라·주택 대부분)은 빈 목록이다.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_by_original_article_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleByOriginalArticleIdResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_article_by_original_article_id(
        self,
        payload: DaangnArticleByOriginalArticleIdRequestPayloadModel
    ) -> DaangnArticleByOriginalArticleIdResponseModel:
        """Async variant of `run_request_article_by_original_article_id`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_by_original_article_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleByOriginalArticleIdResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_realsale_feed(
        self,
        payload: DaangnRealsaleFeedRequestPayloadModel
    ) -> DaangnRealsaleFeedResponseModel:
        """Fetch recent real transactions of a region via `POST realty.kr.karrotmarket.com/graphql` (`realsaleFeed`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다
        (잘못된 거래 유형·정렬 값도 이유 없이 "알 수 없는 오류").

        Args:
            payload: 지역 ID(동·구), 거래 유형(SALE/BORROW), 정렬, 페이지 크기(`count`)와 커서(`cursor`).

        Returns:
            DaangnRealsaleFeedResponseModel: 공개일이 최근인 순의 국토부 실거래. 아파트 외에 빌라·오피스텔 등도 섞인다.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.realsale_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnRealsaleFeedResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_realsale_feed(
        self,
        payload: DaangnRealsaleFeedRequestPayloadModel
    ) -> DaangnRealsaleFeedResponseModel:
        """Async variant of `run_request_realsale_feed`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.realsale_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnRealsaleFeedResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_realsale_new_high_feed(
        self,
        payload: DaangnRealsaleNewHighFeedRequestPayloadModel
    ) -> DaangnRealsaleNewHighFeedResponseModel:
        """Fetch new-high sale transactions of a region via `POST realty.kr.karrotmarket.com/graphql` (`realsaleNewHighFeed`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다
        (잘못된 거래 유형·정렬 값도 이유 없이 "알 수 없는 오류").

        Args:
            payload: 지역 ID(동·구), 페이지 크기(`count`)와 커서(`cursor`).

        Returns:
            DaangnRealsaleNewHighFeedResponseModel: 이전 최고가를 넘은 매매 (가격 높은 순, 이전 최고가 포함).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.realsale_new_high_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnRealsaleNewHighFeedResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_realsale_new_high_feed(
        self,
        payload: DaangnRealsaleNewHighFeedRequestPayloadModel
    ) -> DaangnRealsaleNewHighFeedResponseModel:
        """Async variant of `run_request_realsale_new_high_feed`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.realsale_new_high_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnRealsaleNewHighFeedResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_realsale_feed_summary(
        self,
        payload: DaangnRealsaleFeedSummaryRequestPayloadModel
    ) -> DaangnRealsaleFeedSummaryResponseModel:
        """Fetch a region's realsale summary via `POST realty.kr.karrotmarket.com/graphql` (`realsaleFeedSummary` + `realsaleNewHighFeedSummary`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지역 ID (동·구) 둘 (`input`·`newHighInput`, 같은 지역).

        Returns:
            DaangnRealsaleFeedSummaryResponseModel: 가장 최근 공개일과 그날의 매매 수·신고가 수 (웹 실거래 화면 머리).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.realsale_feed_summary_query_id)
        )
        raise_for_status(response=response)
        return DaangnRealsaleFeedSummaryResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_realsale_feed_summary(
        self,
        payload: DaangnRealsaleFeedSummaryRequestPayloadModel
    ) -> DaangnRealsaleFeedSummaryResponseModel:
        """Async variant of `run_request_realsale_feed_summary`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.realsale_feed_summary_query_id)
        )
        raise_for_status(response=response)
        return DaangnRealsaleFeedSummaryResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_nearest_commute_station(
        self,
        payload: DaangnNearestCommuteStationRequestPayloadModel
    ) -> DaangnNearestCommuteStationResponseModel:
        """Find the subway station nearest to a coordinate via `POST realty.kr.karrotmarket.com/graphql` (`nearestCommuteStation`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 좌표 (문자열로 보낸다).

        Returns:
            DaangnNearestCommuteStationResponseModel: 가장 가까운 역과 도보 시간. 근처에 역이 없으면 null.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.nearest_commute_station_query_id)
        )
        raise_for_status(response=response)
        return DaangnNearestCommuteStationResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_nearest_commute_station(
        self,
        payload: DaangnNearestCommuteStationRequestPayloadModel
    ) -> DaangnNearestCommuteStationResponseModel:
        """Async variant of `run_request_nearest_commute_station`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.nearest_commute_station_query_id)
        )
        raise_for_status(response=response)
        return DaangnNearestCommuteStationResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_commute_stations(
        self,
        payload: DaangnCommuteStationsRequestPayloadModel
    ) -> DaangnCommuteStationsResponseModel:
        """List every station reachable from a station via `POST realty.kr.karrotmarket.com/graphql` (`commuteStations`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다. 페이지가 없다.

        Args:
            payload: 출발(회사) 역 이름, 매물 조건.

        Returns:
            DaangnCommuteStationsResponseModel: 갈 수 있는 역과 지하철 시간·환승 횟수·경로.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.commute_stations_query_id)
        )
        raise_for_status(response=response)
        return DaangnCommuteStationsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_commute_stations(
        self,
        payload: DaangnCommuteStationsRequestPayloadModel
    ) -> DaangnCommuteStationsResponseModel:
        """Async variant of `run_request_commute_stations`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.commute_stations_query_id)
        )
        raise_for_status(response=response)
        return DaangnCommuteStationsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_commute_station_article_connection(
        self,
        payload: DaangnCommuteStationArticleConnectionRequestPayloadModel
    ) -> DaangnCommuteStationArticleConnectionResponseModel:
        """List listings around a station via `POST realty.kr.karrotmarket.com/graphql` (`commuteStationArticleConnection`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 역 이름, 매물 조건, 받을 수.

        Returns:
            DaangnCommuteStationArticleConnectionResponseModel: 역 주변 매물 (카드 일부 필드).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.commute_station_article_connection_query_id)
        )
        raise_for_status(response=response)
        return DaangnCommuteStationArticleConnectionResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_commute_station_article_connection(
        self,
        payload: DaangnCommuteStationArticleConnectionRequestPayloadModel
    ) -> DaangnCommuteStationArticleConnectionResponseModel:
        """Async variant of `run_request_commute_station_article_connection`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.commute_station_article_connection_query_id)
        )
        raise_for_status(response=response)
        return DaangnCommuteStationArticleConnectionResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_search_subway_station_pois(
        self,
        payload: DaangnSearchSubwayStationPoisRequestPayloadModel
    ) -> DaangnSearchSubwayStationPoisResponseModel:
        """Search subway stations by name via `POST realty.kr.karrotmarket.com/graphql` (`searchSubwayStationPois`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 역 이름.

        Returns:
            DaangnSearchSubwayStationPoisResponseModel: 앞부분이 같은 역 (ID·노선·좌표, 최대 50).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_subway_station_pois_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchSubwayStationPoisResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_subway_station_pois(
        self,
        payload: DaangnSearchSubwayStationPoisRequestPayloadModel
    ) -> DaangnSearchSubwayStationPoisResponseModel:
        """Async variant of `run_request_search_subway_station_pois`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_subway_station_pois_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchSubwayStationPoisResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_search_region(
        self,
        payload: DaangnSearchRegionRequestPayloadModel
    ) -> DaangnSearchRegionResponseModel:
        """Search 법정동·구·시·도 by name via `POST realty.kr.karrotmarket.com/graphql` (`searchRegion`).

        웹 지도 검색창의 지역 칸이다. Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지역 이름, 받을 수, 커서.

        Returns:
            DaangnSearchRegionResponseModel: 시·도 → 구 → 동 순의 지역 (ID·중심 좌표·지도 레벨).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_region_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchRegionResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_region(
        self,
        payload: DaangnSearchRegionRequestPayloadModel
    ) -> DaangnSearchRegionResponseModel:
        """Async variant of `run_request_search_region`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_region_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchRegionResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_search_school_pois(
        self,
        payload: DaangnSearchSchoolPoisRequestPayloadModel
    ) -> DaangnSearchSchoolPoisResponseModel:
        """Search universities by name via `POST realty.kr.karrotmarket.com/graphql` (`searchSchoolPois`).

        웹 지도 검색창의 대학 칸이다. Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 대학 이름, 학교 종류, 받을 수.

        Returns:
            DaangnSearchSchoolPoisResponseModel: 캠퍼스마다 대학 (ID·캠퍼스 이름·주소·좌표).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_school_pois_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchSchoolPoisResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_school_pois(
        self,
        payload: DaangnSearchSchoolPoisRequestPayloadModel
    ) -> DaangnSearchSchoolPoisResponseModel:
        """Async variant of `run_request_search_school_pois`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_school_pois_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchSchoolPoisResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_search_address(
        self,
        payload: DaangnSearchAddressRequestPayloadModel
    ) -> DaangnSearchAddressResponseModel:
        """Search road addresses via `POST realty.kr.karrotmarket.com/graphql` (`searchAddress`, 웹 검색창 주소 모드).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 주소 글자(`input.query`)와 페이지.

        Returns:
            DaangnSearchAddressResponseModel: 도로명·지번 주소 후보와 건물 관리 번호, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_address_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchAddressResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_address(
        self,
        payload: DaangnSearchAddressRequestPayloadModel
    ) -> DaangnSearchAddressResponseModel:
        """Async variant of `run_request_search_address`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_address_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchAddressResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_unit_by_address(
        self,
        payload: DaangnUnitByAddressRequestPayloadModel
    ) -> DaangnUnitByAddressResponseModel:
        """Resolve an address candidate to its location via `POST realty.kr.karrotmarket.com/graphql` (`unitByAddress`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 주소 검색 후보의 건물 관리 번호와 원본 도로명 주소 (`input.jusoAddress`).

        Returns:
            DaangnUnitByAddressResponseModel: 주소 좌표와 그 주소의 당근 단지·건물. 못 찾으면 `unit` 이 null.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.unit_by_address_query_id)
        )
        raise_for_status(response=response)
        return DaangnUnitByAddressResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_unit_by_address(
        self,
        payload: DaangnUnitByAddressRequestPayloadModel
    ) -> DaangnUnitByAddressResponseModel:
        """Async variant of `run_request_unit_by_address`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.unit_by_address_query_id)
        )
        raise_for_status(response=response)
        return DaangnUnitByAddressResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_subway_station_article_connection(
        self,
        payload: DaangnSubwayStationArticleConnectionRequestPayloadModel
    ) -> DaangnSubwayStationArticleConnectionResponseModel:
        """List listings around a subway station via `POST realty.kr.karrotmarket.com/graphql` (`subwayStationArticleConnection`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 역 ID, 매물 조건, 받을 수, 커서.

        Returns:
            DaangnSubwayStationArticleConnectionResponseModel: 역 주변 매물 (카드 전체 필드와 역별 도보 시간).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.subway_station_article_connection_query_id)
        )
        raise_for_status(response=response)
        return DaangnSubwayStationArticleConnectionResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_subway_station_article_connection(
        self,
        payload: DaangnSubwayStationArticleConnectionRequestPayloadModel
    ) -> DaangnSubwayStationArticleConnectionResponseModel:
        """Async variant of `run_request_subway_station_article_connection`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.subway_station_article_connection_query_id)
        )
        raise_for_status(response=response)
        return DaangnSubwayStationArticleConnectionResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_article_by_cluster_id(
        self,
        payload: DaangnArticleByClusterIdRequestPayloadModel
    ) -> DaangnArticleByClusterIdResponseModel:
        """List one dong's listings like the web map's dong cluster panel via `POST realty.kr.karrotmarket.com/graphql` (`articleByClusterId`).

        Same retry behaviour as `run_request_articles`. 실패는 HTTP 200 의 `errors` 로 온다.

        Returns:
            DaangnArticleByClusterIdResponseModel: 그 동 매물 (최근 순, 카드 전체 필드).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_by_cluster_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleByClusterIdResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_article_by_cluster_id(
        self,
        payload: DaangnArticleByClusterIdRequestPayloadModel
    ) -> DaangnArticleByClusterIdResponseModel:
        """Async variant of `run_request_article_by_cluster_id`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_by_cluster_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleByClusterIdResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_article_clusters(
        self,
        payload: DaangnArticleClustersRequestPayloadModel
    ) -> DaangnArticleClustersResponseModel:
        """Count listings per region bubble on the web map via `POST realty.kr.karrotmarket.com/graphql` (`articleClusters`).

        Same retry behaviour as `run_request_articles`. 실패는 HTTP 200 의 `errors` 로 온다.

        Returns:
            DaangnArticleClustersResponseModel: 범위 안 지역 거품마다 조건에 맞는 매물 수.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_clusters_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleClustersResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_article_clusters(
        self,
        payload: DaangnArticleClustersRequestPayloadModel
    ) -> DaangnArticleClustersResponseModel:
        """Async variant of `run_request_article_clusters`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_clusters_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleClustersResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_university_article_connection(
        self,
        payload: DaangnUniversityArticleConnectionRequestPayloadModel
    ) -> DaangnUniversityArticleConnectionResponseModel:
        """List listings around a university via `POST realty.kr.karrotmarket.com/graphql` (`universityArticleConnection`).

        웹 대학 페이지의 매물 목록이다. Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 대학 ID, 매물 조건, 받을 수, 커서.

        Returns:
            DaangnUniversityArticleConnectionResponseModel: 대학 주변 매물 (카드 전체 필드).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.university_article_connection_query_id)
        )
        raise_for_status(response=response)
        return DaangnUniversityArticleConnectionResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_university_article_connection(
        self,
        payload: DaangnUniversityArticleConnectionRequestPayloadModel
    ) -> DaangnUniversityArticleConnectionResponseModel:
        """Async variant of `run_request_university_article_connection`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.university_article_connection_query_id)
        )
        raise_for_status(response=response)
        return DaangnUniversityArticleConnectionResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_schools(
        self,
        payload: DaangnComplexSchoolsRequestPayloadModel
    ) -> DaangnComplexSchoolsResponseModel:
        """Fetch schools and preschools near a complex via `POST realty.kr.karrotmarket.com/graphql` (`complexByOriginalId`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 숫자 단지 ID.

        Returns:
            DaangnComplexSchoolsResponseModel: 단지 좌표와 근처 어린이집·유치원 (초·중·고도 오지만 읽지 않는다).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_schools_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexSchoolsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_schools(
        self,
        payload: DaangnComplexSchoolsRequestPayloadModel
    ) -> DaangnComplexSchoolsResponseModel:
        """Async variant of `run_request_complex_schools`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_schools_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexSchoolsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_preschool_by_no(
        self,
        payload: DaangnPreschoolByNoRequestPayloadModel
    ) -> DaangnPreschoolByNoResponseModel:
        """Fetch one daycare or kindergarten via `POST realty.kr.karrotmarket.com/graphql` (`preschoolByNo`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 시설 번호 (숫자).

        Returns:
            DaangnPreschoolByNoResponseModel: 운영 시간·설립 유형·원아·교사 수.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.preschool_by_no_query_id)
        )
        raise_for_status(response=response)
        return DaangnPreschoolByNoResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_preschool_by_no(
        self,
        payload: DaangnPreschoolByNoRequestPayloadModel
    ) -> DaangnPreschoolByNoResponseModel:
        """Async variant of `run_request_preschool_by_no`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.preschool_by_no_query_id)
        )
        raise_for_status(response=response)
        return DaangnPreschoolByNoResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_compare(
        self,
        payload: DaangnComplexCompareRequestPayloadModel
    ) -> DaangnComplexCompareResponseModel:
        """Fetch one complex comparison column via `POST realty.kr.karrotmarket.com/graphql` (`complexByOriginalId`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 단지 ID.

        Returns:
            DaangnComplexCompareResponseModel: 단지 공공 정보·평형별 KB 시세·실거래·호가·관리비.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_compare_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexCompareResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_compare(
        self,
        payload: DaangnComplexCompareRequestPayloadModel
    ) -> DaangnComplexCompareResponseModel:
        """Async variant of `run_request_complex_compare`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_compare_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexCompareResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_nearby_complexes(
        self,
        payload: DaangnNearbyComplexesRequestPayloadModel
    ) -> DaangnNearbyComplexesResponseModel:
        """List complexes in a dong via `POST realty.kr.karrotmarket.com/graphql` (`complexes`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 동 ID, 받을 수.

        Returns:
            DaangnNearbyComplexesResponseModel: 동의 단지 (이름·유형).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.nearby_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnNearbyComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_nearby_complexes(
        self,
        payload: DaangnNearbyComplexesRequestPayloadModel
    ) -> DaangnNearbyComplexesResponseModel:
        """Async variant of `run_request_nearby_complexes`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.nearby_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnNearbyComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_region(
        self,
        payload: DaangnComplexRegionRequestPayloadModel
    ) -> DaangnComplexRegionResponseModel:
        """Fetch a complex's dong via `POST realty.kr.karrotmarket.com/graphql` (`complexByOriginalId`, 웹 `ComplexIdSeoQuery`).

        Same retry behaviour as `run_request_article_feed`. 루트 필드가 단지 실거래가와 같은 `complexByOriginalId` 라
        action id 는 `complex_region` 으로 구분한다. 없는 단지면 `complex` 가 null 이다.

        Args:
            payload: 단지 ID.

        Returns:
            DaangnComplexRegionResponseModel: 단지 유형과 동 (`region.originalId`).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_region_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexRegionResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_region(
        self,
        payload: DaangnComplexRegionRequestPayloadModel
    ) -> DaangnComplexRegionResponseModel:
        """Async variant of `run_request_complex_region`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_region_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexRegionResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complexes_by_original_complex_ids(
        self,
        payload: DaangnComplexesByOriginalComplexIdsRequestPayloadModel
    ) -> DaangnComplexesByOriginalComplexIdsResponseModel:
        """Fetch complex cards by IDs via `POST realty.kr.karrotmarket.com/graphql` (`complexesByOriginalComplexIds`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 단지 ID 목록, 카드 실거래의 거래 유형.

        Returns:
            DaangnComplexesByOriginalComplexIdsResponseModel: 단지별 세대수·거래 유형별 현재 매물 수.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complexes_by_original_complex_ids_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexesByOriginalComplexIdsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complexes_by_original_complex_ids(
        self,
        payload: DaangnComplexesByOriginalComplexIdsRequestPayloadModel
    ) -> DaangnComplexesByOriginalComplexIdsResponseModel:
        """Async variant of `run_request_complexes_by_original_complex_ids`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complexes_by_original_complex_ids_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexesByOriginalComplexIdsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_livable_region_scopes(
        self,
        payload: DaangnLivableRegionScopesRequestPayloadModel
    ) -> DaangnLivableRegionScopesResponseModel:
        """List regions for neighborhood recommendation via `POST realty.kr.karrotmarket.com/graphql` (`livableRegionScopes`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 기준 연도.

        Returns:
            DaangnLivableRegionScopesResponseModel: 시·도와 시·군·구 코드.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.livable_region_scopes_query_id)
        )
        raise_for_status(response=response)
        return DaangnLivableRegionScopesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_livable_region_scopes(
        self,
        payload: DaangnLivableRegionScopesRequestPayloadModel
    ) -> DaangnLivableRegionScopesResponseModel:
        """Async variant of `run_request_livable_region_scopes`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.livable_region_scopes_query_id)
        )
        raise_for_status(response=response)
        return DaangnLivableRegionScopesResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_recommend_neighborhoods(
        self,
        payload: DaangnRecommendNeighborhoodsRequestPayloadModel
    ) -> DaangnRecommendNeighborhoodsResponseModel:
        """Recommend neighborhoods by indicators via `POST realty.kr.karrotmarket.com/graphql` (`recommendNeighborhoods`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지표, 기준 연도, 지역 코드, 개수.

        Returns:
            DaangnRecommendNeighborhoodsResponseModel: 순위 순 추천 동과 한 줄 설명.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.recommend_neighborhoods_query_id)
        )
        raise_for_status(response=response)
        return DaangnRecommendNeighborhoodsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_recommend_neighborhoods(
        self,
        payload: DaangnRecommendNeighborhoodsRequestPayloadModel
    ) -> DaangnRecommendNeighborhoodsResponseModel:
        """Async variant of `run_request_recommend_neighborhoods`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.recommend_neighborhoods_query_id)
        )
        raise_for_status(response=response)
        return DaangnRecommendNeighborhoodsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_trending_complexes(
        self,
        payload: DaangnTrendingComplexesRequestPayloadModel
    ) -> DaangnTrendingComplexesResponseModel:
        """List nationwide / province / district trending complexes via `POST realty.kr.karrotmarket.com/graphql` (`trendingComplexes`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지역 ID (문자열, 전국은 'ALL'), 받을 수.

        Returns:
            DaangnTrendingComplexesResponseModel: 어제 대비 오늘 조회가 급상승한 순 단지 (2026-11-12 실측: 전국·서울 50곳, 강남구 13곳).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.trending_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnTrendingComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_trending_complexes(
        self,
        payload: DaangnTrendingComplexesRequestPayloadModel
    ) -> DaangnTrendingComplexesResponseModel:
        """Async variant of `run_request_trending_complexes`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.trending_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnTrendingComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_get_view_ranking_articles(
        self,
        payload: DaangnGetViewRankingArticlesRequestPayloadModel
    ) -> DaangnGetViewRankingArticlesResponseModel:
        """List most viewed listings in a district via `POST realty.kr.karrotmarket.com/graphql` (`getViewRankingArticles`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 동 ID, 매물 종류, 받을 수.

        Returns:
            DaangnGetViewRankingArticlesResponseModel: 구 전체 조회수 순위 매물.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.get_view_ranking_articles_query_id)
        )
        raise_for_status(response=response)
        return DaangnGetViewRankingArticlesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_get_view_ranking_articles(
        self,
        payload: DaangnGetViewRankingArticlesRequestPayloadModel
    ) -> DaangnGetViewRankingArticlesResponseModel:
        """Async variant of `run_request_get_view_ranking_articles`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.get_view_ranking_articles_query_id)
        )
        raise_for_status(response=response)
        return DaangnGetViewRankingArticlesResponseModel.model_validate(response.json())

    def _map_reviews_path(self, parameter: DaangnMapReviewsRequestParameterModel) -> str:
        return self.map_reviews_endpoint.format(name1=quote(parameter.name1), name2=quote(parameter.name2))

    @daangn_retry
    def run_request_map_reviews(
        self,
        parameter: DaangnMapReviewsRequestParameterModel
    ) -> DaangnMapReviewsResponseModel:
        """Fetch a district's neighborhood review page via `GET /map/{name1}/{name2}/reviews`.

        Same retry behaviour as `run_request_articles`. 구가 없는 시(세종)는 404 로
        `ResponseStatusError` 가 난다.

        Args:
            parameter: `name1`, `name2` (시도/구).

        Returns:
            DaangnMapReviewsResponseModel: 후기 많은 단지 20곳과 단지별 후기 수.

        Raises:
            RelayStoreNotFoundError: 페이지에 스토어가 없을 때 (구조 변경).
        """
        response = self._client.get(url=self._map_reviews_path(parameter), extensions=PAGE_REQUEST_EXTENSIONS)
        raise_for_status(response=response)
        return parse_map_reviews_html(response.text)

    @daangn_retry
    async def arun_request_map_reviews(
        self,
        parameter: DaangnMapReviewsRequestParameterModel
    ) -> DaangnMapReviewsResponseModel:
        """Async variant of `run_request_map_reviews`."""
        response = await self._async_client.get(url=self._map_reviews_path(parameter), extensions=PAGE_REQUEST_EXTENSIONS)
        raise_for_status(response=response)
        return parse_map_reviews_html(response.text)

    @daangn_retry
    def run_request_lived_reviews_by_region(
        self,
        payload: DaangnLivedReviewsByRegionRequestPayloadModel
    ) -> DaangnLivedReviewsByRegionResponseModel:
        """List neighborhood reviews of a region via `POST realty.kr.karrotmarket.com/graphql` (`livedReviewsByRegion`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지역 ID, 받을 수·커서.

        Returns:
            DaangnLivedReviewsByRegionResponseModel: 동네 후기 (본문은 읽지 않는다).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.lived_reviews_by_region_query_id)
        )
        raise_for_status(response=response)
        return DaangnLivedReviewsByRegionResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_lived_reviews_by_region(
        self,
        payload: DaangnLivedReviewsByRegionRequestPayloadModel
    ) -> DaangnLivedReviewsByRegionResponseModel:
        """Async variant of `run_request_lived_reviews_by_region`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.lived_reviews_by_region_query_id)
        )
        raise_for_status(response=response)
        return DaangnLivedReviewsByRegionResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_articles(
        self,
        payload: DaangnComplexArticlesRequestPayloadModel
    ) -> DaangnComplexArticlesResponseModel:
        """List a complex's listings via `POST realty.kr.karrotmarket.com/graphql` (`complexByOriginalId.complex.articles`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 단지 ID, 매물 조건(`input.propertyFilter`), 페이지 크기(`first`)와 커서(`after`).

        Returns:
            DaangnComplexArticlesResponseModel: 단지의 현재 매물 카드. 없는 단지면 `complex` 가 null.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_articles_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexArticlesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_articles(
        self,
        payload: DaangnComplexArticlesRequestPayloadModel
    ) -> DaangnComplexArticlesResponseModel:
        """Async variant of `run_request_complex_articles`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_articles_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexArticlesResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_by_cluster_id(
        self,
        payload: DaangnComplexByClusterIdRequestPayloadModel
    ) -> DaangnComplexByClusterIdResponseModel:
        """List a dong's or district's complexes via `POST realty.kr.karrotmarket.com/graphql` (`complexByClusterId`).

        Same retry behaviour as `run_request_article_feed`. 단지 조건은 매물 조건과 키가 달라
        (`DaangnComplexFilterModel`) 매물 조건을 그대로 보내면 "알 수 없는 오류" 가 난다. 예전에 쓰던 동 ID 의
        `searchComplexes` 와 첫 50곳이 순서·커서까지 같았다 (2026-11-12 실측: 역삼동).

        Args:
            payload: 지역 클러스터(`input.clusterId`), 단지 조건(`input.propertyFilter`), 정렬(`input.sort`),
                단지마다 보여 줄 실거래의 거래 유형(`tradeType`)과 면적(`exclusiveUseArea`), 페이지.

        Returns:
            DaangnComplexByClusterIdResponseModel: 정렬 순 단지 카드와 다음 페이지 커서, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_by_cluster_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexByClusterIdResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_by_cluster_id(
        self,
        payload: DaangnComplexByClusterIdRequestPayloadModel
    ) -> DaangnComplexByClusterIdResponseModel:
        """Async variant of `run_request_complex_by_cluster_id`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_by_cluster_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexByClusterIdResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_search_complexes_viewport(
        self,
        payload: DaangnSearchComplexesViewportRequestPayloadModel
    ) -> DaangnSearchComplexesViewportResponseModel:
        """List complexes inside a map view via `POST realty.kr.karrotmarket.com/graphql` (`searchComplexes`, 지도 범위).

        Same retry behaviour as `run_request_article_feed`. 단지 카드·조건·정렬은 동·구 단지 목록(`run_request_complex_by_cluster_id`)과
        같고 클러스터 ID 자리에 화면 범위(`input.locationFilter`)가 온다 (2026-11-12 실측: 역삼동 중심 줌 15 에 736세대
        오피스텔부터 세대수 순).

        Args:
            payload: 화면 범위(`input.locationFilter`), 단지 조건(`input.propertyFilter`), 정렬(`input.sort`),
                단지마다 보여 줄 실거래의 거래 유형(`tradeType`)과 면적(`exclusiveUseArea`), 페이지.

        Returns:
            DaangnSearchComplexesViewportResponseModel: 정렬 순 단지 카드와 다음 페이지 커서, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_complexes_viewport_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchComplexesViewportResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_complexes_viewport(
        self,
        payload: DaangnSearchComplexesViewportRequestPayloadModel
    ) -> DaangnSearchComplexesViewportResponseModel:
        """Async variant of `run_request_search_complexes_viewport`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_complexes_viewport_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchComplexesViewportResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_search_schools(
        self,
        payload: DaangnSearchSchoolsRequestPayloadModel
    ) -> DaangnSearchSchoolsResponseModel:
        """Search schools by name via `POST realty.kr.karrotmarket.com/graphql` (`searchSchools`).

        Same retry behaviour as `run_request_article_feed`.

        Args:
            payload: 학교 이름(`input.name`, 일부만 줘도 된다)과 페이지.

        Returns:
            DaangnSearchSchoolsResponseModel: 이름이 비슷한 학교 (전국), 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_schools_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchSchoolsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_search_schools(
        self,
        payload: DaangnSearchSchoolsRequestPayloadModel
    ) -> DaangnSearchSchoolsResponseModel:
        """Async variant of `run_request_search_schools`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.search_schools_query_id)
        )
        raise_for_status(response=response)
        return DaangnSearchSchoolsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_school_by_code(
        self,
        payload: DaangnSchoolByCodeRequestPayloadModel
    ) -> DaangnSchoolByCodeResponseModel:
        """Fetch a school and its assigned complexes via `POST realty.kr.karrotmarket.com/graphql` (`schoolByCode`).

        Same retry behaviour as `run_request_article_feed`.

        Args:
            payload: 학교 코드(`schCd`).

        Returns:
            DaangnSchoolByCodeResponseModel: 학교 정보와 배정 단지 (초등학교만), 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.school_by_code_query_id)
        )
        raise_for_status(response=response)
        return DaangnSchoolByCodeResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_school_by_code(
        self,
        payload: DaangnSchoolByCodeRequestPayloadModel
    ) -> DaangnSchoolByCodeResponseModel:
        """Async variant of `run_request_school_by_code`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.school_by_code_query_id)
        )
        raise_for_status(response=response)
        return DaangnSchoolByCodeResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_complex_price_chart(
        self,
        payload: DaangnComplexPriceChartRequestPayloadModel
    ) -> DaangnComplexPriceChartResponseModel:
        """Fetch a complex's monthly average prices via `POST realty.kr.karrotmarket.com/graphql` (`node(id:).priceChart`).

        Same retry behaviour as `run_request_article_feed`. 금액은 **원** 단위로 온다.

        Args:
            payload: 단지 노드 ID, 거래 유형(매매·전세), 평형 타입 코드 또는 전용면적 묶음.

        Returns:
            DaangnComplexPriceChartResponseModel: 15년치 월별 평균가, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_price_chart_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexPriceChartResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_complex_price_chart(
        self,
        payload: DaangnComplexPriceChartRequestPayloadModel
    ) -> DaangnComplexPriceChartResponseModel:
        """Async variant of `run_request_complex_price_chart`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.complex_price_chart_query_id)
        )
        raise_for_status(response=response)
        return DaangnComplexPriceChartResponseModel.model_validate(response.json())
