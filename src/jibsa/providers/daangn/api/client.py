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
    parse_map_html,
    parse_map_reviews_html,
)
from jibsa.providers.daangn.api.request.commute import (
    DaangnCommuteFeedRequestPayloadModel,
    DaangnCommuteStationArticleConnectionRequestPayloadModel,
    DaangnNearestCommuteStationRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.compare import (
    DaangnComplexCompareRequestPayloadModel,
    DaangnComplexesByOriginalComplexIdsRequestPayloadModel,
    DaangnNearbyComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.complex import (
    DaangnComplexArticlesRequestPayloadModel,
    DaangnComplexesRequestParameterModel,
    DaangnRegionComplexesRequestPayloadModel,
    DaangnSearchComplexesRequestPayloadModel,
    DaangnTrendingComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.development import (
    DaangnDevelopmentByBusiNoRequestPayloadModel,
    DaangnDevelopmentDistrictsRequestPayloadModel,
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
    DaangnRealsaleNewHighFeedRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.region import (
    DaangnGeocodeAddressRequestPayloadModel,
    DaangnGetRegionByCoordinateRequestPayloadModel,
    DaangnRegionsKeywordV1RequestParameterModel,
    DaangnSearchAddressRequestPayloadModel,
    DaangnSearchSubwayStationPoisRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.review import (
    DaangnLivedReviewsByRegionRequestPayloadModel,
    DaangnMapReviewsRequestParameterModel,
    DaangnRegionByOriginalRegionIdRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.school import (
    DaangnEducationMapPointsRequestPayloadModel,
    DaangnPreschoolByNoRequestPayloadModel,
    DaangnSchoolByCodeRequestPayloadModel,
    DaangnSearchSchoolsRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.search import (
    DaangnArticleFeedRequestPayloadModel,
    DaangnArticleMapPointsRequestPayloadModel,
    DaangnArticlesByOriginalArticleIdsRequestPayloadModel,
    DaangnArticlesCountRequestPayloadModel,
    DaangnMapRequestParameterModel,
    DaangnSubwayStationArticleConnectionRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.commute import (
    DaangnCommuteFeedResponseModel,
    DaangnCommuteStationArticleConnectionResponseModel,
    DaangnNearestCommuteStationResponseModel,
)
from jibsa.providers.daangn.api.response.compare import (
    DaangnComplexCompareResponseModel,
    DaangnComplexesByOriginalComplexIdsResponseModel,
    DaangnNearbyComplexesResponseModel,
)
from jibsa.providers.daangn.api.response.complex import (
    DaangnComplexArticlesResponseModel,
    DaangnComplexesResponseModel,
    DaangnRegionComplexesResponseModel,
    DaangnSearchComplexesResponseModel,
    DaangnTrendingComplexesResponseModel,
)
from jibsa.providers.daangn.api.response.development import (
    DaangnDevelopmentByBusiNoResponseModel,
    DaangnDevelopmentDistrictsResponseModel,
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
    DaangnRealsaleNewHighFeedResponseModel,
)
from jibsa.providers.daangn.api.response.region import (
    DaangnGeocodeAddressResponseModel,
    DaangnGetRegionByCoordinateResponseModel,
    DaangnRegionsKeywordV1ResponseModel,
    DaangnSearchAddressResponseModel,
    DaangnSearchSubwayStationPoisResponseModel,
)
from jibsa.providers.daangn.api.response.review import (
    DaangnLivedReviewsByRegionResponseModel,
    DaangnMapReviewsResponseModel,
    DaangnRegionByOriginalRegionIdResponseModel,
)
from jibsa.providers.daangn.api.response.school import (
    DaangnEducationMapPointsResponseModel,
    DaangnPreschoolByNoResponseModel,
    DaangnSchoolByCodeResponseModel,
    DaangnSearchSchoolsResponseModel,
)
from jibsa.providers.daangn.api.response.search import (
    DaangnArticleFeedResponseModel,
    DaangnArticleMapPointsResponseModel,
    DaangnArticlesByOriginalArticleIdsResponseModel,
    DaangnArticlesCountResponseModel,
    DaangnMapResponseModel,
    DaangnSubwayStationArticleConnectionResponseModel,
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


class DaangnClient(BaseHTTPClient):
    """당근부동산 (realty.daangn.com) 비공식 클라이언트.

    동 정보·상세는 SSR HTML 에 박힌 라우터 상태의 Relay 스토어를 파싱한다. 조건을 건 매물
    목록과 다음 페이지는 웹이 쓰는 GraphQL(`realty.kr.karrotmarket.com/graphql`)의
    `articleFeed` 로, 조건에 맞는 매물 수는 `articlesCount` 로 받는다. 좌표 범위 검색은
    웹 지도처럼 `articleMapPoints` 로 핀(ID·좌표)을 받고 `articlesByOriginalArticleIds` 로
    20개씩 카드를 받는다. 좌표 → 동은
    `getRegionByCoordinate`. 단지 정보는 단지 페이지(`/complexes/{originalId}`)의 스토어를,
    단지 이름 검색은 `searchComplexes`, 단지 실거래가는 `complexByOriginalId`,
    매물 실거래가(매물이 있는 건물의 비슷한 면적 거래)는 `articleByOriginalArticleId`, 동·구의 최근
    실거래와 신고가는 `realsaleFeed`·`realsaleNewHighFeed`, 출퇴근 검색은 `nearestCommuteStation`
    (회사 → 가까운 역), `commuteFeed` (그 역에서 갈 수 있는 역), `commuteStationArticleConnection`
    (역 주변 매물), 동네 후기는 구의 후기 페이지(`/map/{name1}/{name2}/reviews`, 후기 많은 단지)와
    `regionByOriginalRegionId` (동 후기 수), `livedReviewsByRegion` (후기 유무) 를 쓴다. 후기 페이지는
    `map` 과 겹치지 않게 경로 세그먼트를 이어 `map_reviews` 로 부른다. 단지 매물 목록도 루트 필드가 단지
    실거래가와 같은 `complexByOriginalId` 라 `complex_articles` 로, 지역 단지 목록(웹 지도 단지 탭)도 루트 필드가
    이름 검색과 같은 `searchComplexes` 라 `region_complexes` 로 부른다. 학교 이름 검색은 `searchSchools`,
    학교 정보와 배정 단지는 `schoolByCode`. 단지 시세 차트도 루트 필드가 `complexByOriginalId` 라
    `complex_price_chart` 로 부른다. 지역명 해석은 `www.daangn.com` 의 JSON API 를 쓴다.
    인증은 필요 없다. 모든 금액은 **만원** 단위다.

    action id 는 `/api/` 아래 경로면 세그먼트를 잇고 버전을 끝으로 옮기고
    (`/kr/api/v1/regions/keyword` → `regions_keyword_v1`), 페이지 경로면 경로
    파라미터를 뺀 첫 세그먼트를 쓴다 (`/map/{...}` → `map`). GraphQL 은 경로가 하나라
    루트 필드 이름을 쓴다 (`articleFeed` → `article_feed`).

    GraphQL 은 persisted query 만 받는다. 쿼리 본문을 보내면 `PersistedQueryOnly` 로
    거절하고, 웹 번들에 박힌 해시(`*_query_id`)를 보내야 한다. 웹이 쿼리를 바꾸면 해시가
    `PERSISTED_QUERY_NOT_IN_LIST` 로 거절된다. GraphQL 좌표는 문자열로 보내야 한다
    (숫자면 이유 없이 "알 수 없는 오류").

    Args:
        host: 부동산 호스트 (스킴 제외). Defaults to 'realty.daangn.com'.
        region_host: 지역 API 호스트. Defaults to 'www.daangn.com'.
        graphql_host: GraphQL 호스트. Defaults to 'realty.kr.karrotmarket.com'.
        rate_limit: 요청 제한 정책. Defaults to 0.5초 간격·분당 60회·429 후 5분 쿨다운.

    Attributes:
        base_url: `url_schema` 와 `host` 로 만든 베이스 URL.
        regions_keyword_v1_url: 지역 API 의 절대 URL.
        graphql_url: GraphQL 의 절대 URL.

    Example:
        >>> with DaangnClient() as client:
        ...     client.run_request_map(
        ...         DaangnMapRequestParameterModel(name1='서울특별시', name2='강남구', name3='역삼동')
        ...     )
    """

    regions_keyword_v1_endpoint: ClassVar[str] = '/kr/api/v1/regions/keyword'
    # 구가 없는 시(세종)는 {name2} 세그먼트를 뺀다. 실제 경로는 `_map_path` 가 만든다.
    map_endpoint: ClassVar[str] = '/map/{name1}/{name2}/{name3}'
    articles_endpoint: ClassVar[str] = '/articles/{original_id}'
    complexes_endpoint: ClassVar[str] = '/complexes/{original_id}'
    map_reviews_endpoint: ClassVar[str] = '/map/{name1}/{name2}/reviews'
    graphql_endpoint: ClassVar[str] = '/graphql'
    # 아래 해시는 웹 번들(2026-10-v58)에서 꺼냈다. 주석은 웹의 쿼리 이름과 번들 파일
    # MapShell-*.js 의 RegionArticleListPanelPaginationQuery
    article_feed_query_id: ClassVar[str] = '530da3a4b31d9e972d6e4c28746b3870ddfaedbb6c2dbeb14f84a780811d95df'
    # MapView-*.js 의 MapFloatingControlsArticleCountQuery
    articles_count_query_id: ClassVar[str] = 'f2120ef2ef8147690d1036f7a44b7a77ba9bb24e27a1eab2e5fb9e3de1e6c4bc'
    # MapView-*.js 의 MapViewPinsQuery
    article_map_points_query_id: ClassVar[str] = '716ee2737a8cda97be76d6920fd3dbe213ba1821bbedee4ab774bd760c958b4b'
    # PinArticleListPanel-*.js 의 PinArticleListPanelChunkQuery
    articles_by_original_article_ids_query_id: ClassVar[str] = (
        '6f9a1b7f13d713421eec9da6905dc45f73c2c4e8cad3071e2280bc7aef5cf006'
    )
    # regionByCoordinateQuery-*.js 의 regionByCoordinateQuery
    get_region_by_coordinate_query_id: ClassVar[str] = '1c663788669807706f19ece384062e647238dc7c459298267c72234d6b6e381c'
    # fetchRegionResult-*.js 의 fetchComplexSearchResultQuery
    search_complexes_query_id: ClassVar[str] = 'd5c4d68d4e00b8d0e108ad0eff22975e957d4e10d707c3ddddbe8c3ced72a820'
    # ComplexReviewsPinnedReviewQuery-*.js 의 useTransactionComplexPagination_Query (단지 실거래가)
    complex_by_original_id_query_id: ClassVar[str] = '0759ba56316842fa18e7e3379d7c1c449ffa7591fbf22b6fcba6911a32535220'
    # ComplexArticleListPanel-*.js 의 ComplexArticleListPanelQuery (단지 매물 목록)
    complex_articles_query_id: ClassVar[str] = '0df6a807dedf33d8ab07ef486a9f1980a5652c41396eafc4237274913ab48f7a'
    # ComplexReviewsPinnedReviewQuery-*.js 의 useTransactionArticlePagination_Query (매물 실거래가)
    article_by_original_article_id_query_id: ClassVar[str] = (
        '92851d5818157db86f12ec367d39e8896eef0cd2c3ed6d9639c6aa7cad86c7d6'
    )
    # ComplexReviewsPinnedReviewQuery-*.js 의 RealsaleFeedListQuery (지역 최근 실거래)
    realsale_feed_query_id: ClassVar[str] = '6df5d0f33b925944272fdea4f75f0329ea18ad14f59294dd128865d895249e70'
    # MapShell-*.js 의 NewHighFeedListQuery (지역 신고가)
    realsale_new_high_feed_query_id: ClassVar[str] = '2569f5b4127eb1c87cc5239f14ffe581caace14f1e3a9bd4cc809aad2ec1e439'
    # useNearestStation-*.js 의 CommuteMapViewNearestQuery
    nearest_commute_station_query_id: ClassVar[str] = '3d03f833ea763d068a3bf71e3555b82947077f6ad92cec890eb5434996501781'
    # useNearestStation-*.js 의 CommuteMapViewFeedPaginationQuery (첫 페이지 쿼리는 after 를 무시한다)
    commute_feed_query_id: ClassVar[str] = 'de5d3564cf551789a7eed621b2e8b96f95a085d1f3bceaf9b5099378d63c3bb9'
    # CommuteStationDetailView-*.js 의 CommuteStationDetailPaginationQuery (첫 페이지도 after 없이 같은 결과)
    commute_station_article_connection_query_id: ClassVar[str] = (
        '361740aa91f841a681d3bd7d954d4b4de96d89e629d4eec26d901248668ff97d'
    )
    # index-*.js 의 MapDongNeighborhoodSummaryQuery (동네 후기 요약)
    region_by_original_region_id_query_id: ClassVar[str] = (
        'f40659715d8bb432fecfdab3a0093352f83abc491ad52b06fe5c52bb1eefd622'
    )
    # index-*.js 의 RegionLivedReviewListPanelQuery (동네 후기 목록)
    lived_reviews_by_region_query_id: ClassVar[str] = '13565a6be603cdb75e2590bbc8e977206e77fe41393c1aaad6fcfca04826667e'
    # ComplexListPanel-*.js 의 ComplexListPanelViewportQuery (지역 단지 목록)
    region_complexes_query_id: ClassVar[str] = 'cd05a28829852db94c3d797d2da1bd51a7e3e1415622a37ef916d23a89545b24'
    # MapShell-*.js 의 fetchSchoolSearchResultQuery (학교 이름 검색)
    search_schools_query_id: ClassVar[str] = '223034a6d57e1155443f5560d116dc09839be868c3cda4d95e2434c0304e9731'
    # ComplexReviewsPinnedReviewQuery-*.js 의 SchoolDetailQuery (학교 정보·배정 단지)
    school_by_code_query_id: ClassVar[str] = 'd8e3a2545d518396bb6d55c1357d818f5e0e56c6bb0f876d3310305591e1b127'
    # compare-*.js 의 ComplexComparePriceChartQuery (단지 시세 차트)
    complex_price_chart_query_id: ClassVar[str] = 'be9955e8766ef4de89bf208727497cd738bbf2eb1794fa91dc34bb3dc6f77c29'
    # index-*.js 의 fetchSubwayResultQuery (역 이름 검색)
    search_subway_station_pois_query_id: ClassVar[str] = (
        'f765b400e0498e4a4f0f7fe8adef1d2baffb46b5132227996cb4dbdb622c31cb'
    )
    # MapShell-*.js 의 fetchAddressResultQuery (주소·건물 이름 검색)
    search_address_query_id: ClassVar[str] = '681904380a1ddbca5e91d2323d7db3e812984685aabf62c2fa9b830b9565dab8'
    # SearchCorAddressResult-*.js 의 coordinateFinderQuery (주소 → 좌표)
    geocode_address_query_id: ClassVar[str] = 'd467d9bb003e978d551c1cbc524e6ca21a7039002fd0578f9390784c6203debd'
    # MapShell-*.js 의 SubwayArticleListPanelPaginationQuery (역 주변 매물)
    subway_station_article_connection_query_id: ClassVar[str] = (
        '246140eaaca77d3bcc264e76bc4feb013fe9c0b10fc91b077ef9f235658b0d27'
    )
    # MapView-*.js 의 DevelopmentDistrictOverlayQuery (지도 개발 호재)
    development_districts_query_id: ClassVar[str] = '769ce6f0243d3fcd834fe934c3c9feee3292de566c8386c1ca3e4c3821a6292f'
    # DevelopmentDetailPanel-*.js 의 DevelopmentDetailQuery (개발 사업 상세)
    development_by_busi_no_query_id: ClassVar[str] = '0cc5e4bcd24d29f8cf548c242346524ce342c24c1723b344f6fc7663d015e779'
    # MapView-*.js 의 EducationPoiLayerQuery (지도 교육 시설)
    education_map_points_query_id: ClassVar[str] = '7d17204f3da26c974ad6fbd597cb843231968b53f5652441e32616c83ec92259'
    # ComplexReviewsPinnedReviewQuery-*.js 의 PreschoolDetailPanelQuery (어린이집·유치원 상세)
    preschool_by_no_query_id: ClassVar[str] = 'de92e75df4d4bacddaf7518a3787850aa55b3d26b5302ce39b77a256efafb056'
    # compare-*.js 의 ComplexCompareColumnQuery (단지 비교 칸)
    complex_compare_query_id: ClassVar[str] = '74b409fd6cc63f290120fe7ea8bca376653d37db0cf977a4227f1b2d5233ff0f'
    # ComplexReviewsPinnedReviewQuery-*.js 의 ComplexNearbySectionQuery (같은 동 단지)
    nearby_complexes_query_id: ClassVar[str] = '0239b1a589cb97132006385870cdad55dc496c21977dc540a47b28099a0f8258'
    # ComplexReviewsPinnedReviewQuery-*.js 의 ComplexNearbySectionCardsQuery (단지 카드)
    complexes_by_original_complex_ids_query_id: ClassVar[str] = (
        'ba9845cb97917b80c472433940ce4921fc4f0739562188ae394a06a5e367e8eb'
    )
    # MapShell-*.js 의 GoodNeighborhoodRegionQuery (좋은 동네 추천 지역 목록)
    livable_region_scopes_query_id: ClassVar[str] = '73def70680c51b8b8c9911015b14fe721bb7aaf1a689b1c496693d7bc2003ba7'
    # useH3ZoomConfig-*.js 의 GoodNeighborhoodResultQuery (좋은 동네 추천)
    recommend_neighborhoods_query_id: ClassVar[str] = '84e6cc44b469600a004aa2bc97aad9e972258212585ed52171d14919d2b3d238'
    # ComplexReviewsPinnedReviewQuery-*.js 의 HomeTrendingComplexSectionListQuery (요즘 많이 보는 단지)
    trending_complexes_query_id: ClassVar[str] = '528cbae202c675d69f0cf92d39deb3b736439c130932f521b89bf85092cc5d78'
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

    host: str = 'realty.daangn.com'

    region_host: str = 'www.daangn.com'

    graphql_host: str = 'realty.kr.karrotmarket.com'

    @property
    def base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.host
        )

    @property
    def regions_keyword_v1_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.region_host
        ) + self.regions_keyword_v1_endpoint

    @property
    def graphql_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.graphql_host
        ) + self.graphql_endpoint

    @property
    def graphql_header(self) -> dict[str, str]:
        # 웹 클라이언트가 붙이는 헤더. 웹과 같은 요청으로 보이도록 맞춘다.
        return {
            'Accept': 'application/json',
            'Origin': create_base_url(schema=self.url_schema, host=self.host),
            'x-realty-platform': 'realty-web',
        }

    def _graphql_body(self, payload: RequestModel, query_id: str) -> dict[str, object]:
        return {
            'variables': payload.model_dump(by_alias=True, exclude_none=True),
            'extensions': {'persistedQuery': {'version': 1, 'sha256Hash': query_id}},
        }

    @property
    def base_header(self) -> dict[str, str]:
        return {
            'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
            'User-Agent': self.user_agent,
        }

    @cached_property
    def _client(self) -> Client:
        return Client(
            base_url=self.base_url,
            headers=self.base_header,
            follow_redirects=True,
            event_hooks=self.rate_limit_hooks(),
            verify=self.verify,
            timeout=self.timeout,
            proxy=self.proxy
        )

    @cached_property
    def _async_client(self) -> AsyncClient:
        return AsyncClient(
            base_url=self.base_url,
            headers=self.base_header,
            follow_redirects=True,
            event_hooks=self.async_rate_limit_hooks(),
            verify=self.verify,
            timeout=self.timeout,
            proxy=self.proxy
        )

    def _map_path(self, parameter: DaangnMapRequestParameterModel) -> str:
        names = (parameter.name1, parameter.name2, parameter.name3)
        return '/map/' + '/'.join(quote(name) for name in names if name)

    @daangn_retry
    def run_request_regions_keyword_v1(
        self,
        parameter: DaangnRegionsKeywordV1RequestParameterModel
    ) -> DaangnRegionsKeywordV1ResponseModel:
        """Resolve a region name via `GET www.daangn.com/kr/api/v1/regions/keyword`.

        Retries up to 3 attempts on HTTP 5xx/429 responses and httpx
        timeout/transport errors, waiting 1s between attempts or, on a 429,
        the server's `Retry-After` (capped at 60s); any other error, and the
        final failed attempt, is raised. 요청 제한이 켜져 있으면(기본) 429 는
        재시도 없이 곧바로 `RateLimitedError` (쿨다운) 로 끝난다.

        Args:
            parameter: `keyword` — 동 이름이면 그 동 후보들, 구 이름이면 그 구의 동들.

        Returns:
            DaangnRegionsKeywordV1ResponseModel: 후보 지역 (name1/2/3, depth).
        """
        response = self._client.get(
            url=self.regions_keyword_v1_url,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DaangnRegionsKeywordV1ResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_regions_keyword_v1(
        self,
        parameter: DaangnRegionsKeywordV1RequestParameterModel
    ) -> DaangnRegionsKeywordV1ResponseModel:
        """Async variant of `run_request_regions_keyword_v1`."""
        response = await self._async_client.get(
            url=self.regions_keyword_v1_url,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DaangnRegionsKeywordV1ResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_map(
        self,
        parameter: DaangnMapRequestParameterModel
    ) -> DaangnMapResponseModel:
        """Fetch a dong's listing feed via `GET /map/{name1}/{name2}/{name3}`.

        Same retry behaviour as `run_request_regions_keyword_v1`. HTML 의
        Relay 스토어를 파싱하며, SSR 이 담아 주는 첫 페이지(최근 20건)만 얻는다.

        Args:
            parameter: `name1`, `name2`, `name3` (시도/구/동).

        Returns:
            DaangnMapResponseModel: 동 정보와 매물 목록.

        Raises:
            RelayStoreNotFoundError: 페이지에 스토어가 없을 때 (구조 변경).
        """
        response = self._client.get(url=self._map_path(parameter))
        raise_for_status(response=response)
        return parse_map_html(response.text, parameter.name3)

    @daangn_retry
    async def arun_request_map(
        self,
        parameter: DaangnMapRequestParameterModel
    ) -> DaangnMapResponseModel:
        """Async variant of `run_request_map`."""
        response = await self._async_client.get(url=self._map_path(parameter))
        raise_for_status(response=response)
        return parse_map_html(response.text, parameter.name3)

    @daangn_retry
    def run_request_articles(
        self,
        parameter: DaangnArticlesRequestParameterModel
    ) -> DaangnArticlesResponseModel:
        """Fetch one listing via `GET /articles/{originalId}`.

        Same retry behaviour as `run_request_regions_keyword_v1`. 없는 매물이면
        404 로 `ResponseStatusError` 가 난다.

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
            url=self.articles_endpoint.format(original_id=parameter.original_id)
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
            url=self.articles_endpoint.format(original_id=parameter.original_id)
        )
        raise_for_status(response=response)
        return parse_articles_html(response.text, parameter.original_id)

    @daangn_retry
    def run_request_article_feed(
        self,
        payload: DaangnArticleFeedRequestPayloadModel
    ) -> DaangnArticleFeedResponseModel:
        """Fetch a filtered listing feed via `POST realty.kr.karrotmarket.com/graphql` (`articleFeed`).

        Same retry behaviour as `run_request_regions_keyword_v1` (조회 전용이라 POST 라도
        재시도한다). GraphQL 실패(해시 거절, 잘못된 조건)도 HTTP 200 의 `errors` 로 오며
        여기서 판정하지 않는다.

        Args:
            payload: 동 ID(`input.locationFilter`), 매물 조건(`input.propertyFilter`),
                페이지 크기(`first`)와 커서(`after`).

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

        Same retry behaviour as `run_request_article_feed`. 동으로 세면 `articleFeed` 가 섞어 주는
        주변 동 매물까지 센다 (피드를 끝까지 넘긴 매물 수와 같다).

        Args:
            payload: 동 ID(`input.locationFilter`)와 매물 조건(`input.propertyFilter`).

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
    def run_request_article_map_points(
        self,
        payload: DaangnArticleMapPointsRequestPayloadModel
    ) -> DaangnArticleMapPointsResponseModel:
        """Fetch map pins in a bounding box via `POST realty.kr.karrotmarket.com/graphql` (`articleMapPoints`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 좌표 범위(`input.locationFilter`)와 매물 조건(`input.propertyFilter`).

        Returns:
            DaangnArticleMapPointsResponseModel: 범위 안 핀(매물 ID·좌표). 넓은 범위는 10000 개에서
                잘린다 (2026-10 실측, 약 10km 사방).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_map_points_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleMapPointsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_article_map_points(
        self,
        payload: DaangnArticleMapPointsRequestPayloadModel
    ) -> DaangnArticleMapPointsResponseModel:
        """Async variant of `run_request_article_map_points`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.article_map_points_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticleMapPointsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_articles_by_original_article_ids(
        self,
        payload: DaangnArticlesByOriginalArticleIdsRequestPayloadModel
    ) -> DaangnArticlesByOriginalArticleIdsResponseModel:
        """Fetch listing cards by ID via `POST realty.kr.karrotmarket.com/graphql` (`articlesByOriginalArticleIds`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 매물 ID 목록 (최대 20개).

        Returns:
            DaangnArticlesByOriginalArticleIdsResponseModel: 매물 카드. 순서는 보장되지 않는다.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.articles_by_original_article_ids_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticlesByOriginalArticleIdsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_articles_by_original_article_ids(
        self,
        payload: DaangnArticlesByOriginalArticleIdsRequestPayloadModel
    ) -> DaangnArticlesByOriginalArticleIdsResponseModel:
        """Async variant of `run_request_articles_by_original_article_ids`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.articles_by_original_article_ids_query_id)
        )
        raise_for_status(response=response)
        return DaangnArticlesByOriginalArticleIdsResponseModel.model_validate(response.json())

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

        Same retry behaviour as `run_request_regions_keyword_v1`. 없는 단지면 404 로
        `ResponseStatusError` 가 난다. 페이지가 약 2MB 로 크다 (시세 그래프·학교 도보 경로가 들어 있다).

        Args:
            parameter: `original_id` (숫자 단지 ID).

        Returns:
            DaangnComplexesResponseModel: 단지 기본 정보·평형·역·학교·매물 수·후기 수.

        Raises:
            RelayStoreNotFoundError: 페이지에 스토어가 없을 때 (구조 변경).
        """
        response = self._client.get(
            url=self.complexes_endpoint.format(original_id=parameter.original_id)
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
            url=self.complexes_endpoint.format(original_id=parameter.original_id)
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
    def run_request_commute_feed(
        self,
        payload: DaangnCommuteFeedRequestPayloadModel
    ) -> DaangnCommuteFeedResponseModel:
        """List stations reachable from a station via `POST realty.kr.karrotmarket.com/graphql` (`commuteFeed`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 출발(회사) 역 이름, 매물 조건, 페이지 크기·커서.

        Returns:
            DaangnCommuteFeedResponseModel: 지하철 시간이 짧은 순의 역과 환승 횟수·경로.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.commute_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnCommuteFeedResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_commute_feed(
        self,
        payload: DaangnCommuteFeedRequestPayloadModel
    ) -> DaangnCommuteFeedResponseModel:
        """Async variant of `run_request_commute_feed`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.commute_feed_query_id)
        )
        raise_for_status(response=response)
        return DaangnCommuteFeedResponseModel.model_validate(response.json())

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
    def run_request_search_address(
        self,
        payload: DaangnSearchAddressRequestPayloadModel
    ) -> DaangnSearchAddressResponseModel:
        """Search addresses and building names via `POST realty.kr.karrotmarket.com/graphql` (`searchAddress`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 주소 또는 건물 이름, 받을 수, 커서.

        Returns:
            DaangnSearchAddressResponseModel: 지번·도로명 주소 (좌표 없음).
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
    def run_request_geocode_address(
        self,
        payload: DaangnGeocodeAddressRequestPayloadModel
    ) -> DaangnGeocodeAddressResponseModel:
        """Convert an address to a coordinate via `POST realty.kr.karrotmarket.com/graphql` (`geocodeAddress`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 주소.

        Returns:
            DaangnGeocodeAddressResponseModel: 좌표. 주소가 아니면 null.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.geocode_address_query_id)
        )
        raise_for_status(response=response)
        return DaangnGeocodeAddressResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_geocode_address(
        self,
        payload: DaangnGeocodeAddressRequestPayloadModel
    ) -> DaangnGeocodeAddressResponseModel:
        """Async variant of `run_request_geocode_address`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.geocode_address_query_id)
        )
        raise_for_status(response=response)
        return DaangnGeocodeAddressResponseModel.model_validate(response.json())

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
    def run_request_development_districts(
        self,
        payload: DaangnDevelopmentDistrictsRequestPayloadModel
    ) -> DaangnDevelopmentDistrictsResponseModel:
        """List development projects in a map range via `POST realty.kr.karrotmarket.com/graphql` (`developmentDistricts`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 좌표 범위, 분류.

        Returns:
            DaangnDevelopmentDistrictsResponseModel: 범위 안 개발 사업 (페이지 없음).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.development_districts_query_id)
        )
        raise_for_status(response=response)
        return DaangnDevelopmentDistrictsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_development_districts(
        self,
        payload: DaangnDevelopmentDistrictsRequestPayloadModel
    ) -> DaangnDevelopmentDistrictsResponseModel:
        """Async variant of `run_request_development_districts`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.development_districts_query_id)
        )
        raise_for_status(response=response)
        return DaangnDevelopmentDistrictsResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_development_by_busi_no(
        self,
        payload: DaangnDevelopmentByBusiNoRequestPayloadModel
    ) -> DaangnDevelopmentByBusiNoResponseModel:
        """Fetch one development project via `POST realty.kr.karrotmarket.com/graphql` (`developmentByBusiNo`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 사업 번호.

        Returns:
            DaangnDevelopmentByBusiNoResponseModel: 사업 단계·규모·인가 날짜.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.development_by_busi_no_query_id)
        )
        raise_for_status(response=response)
        return DaangnDevelopmentByBusiNoResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_development_by_busi_no(
        self,
        payload: DaangnDevelopmentByBusiNoRequestPayloadModel
    ) -> DaangnDevelopmentByBusiNoResponseModel:
        """Async variant of `run_request_development_by_busi_no`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.development_by_busi_no_query_id)
        )
        raise_for_status(response=response)
        return DaangnDevelopmentByBusiNoResponseModel.model_validate(response.json())

    @daangn_retry
    def run_request_education_map_points(
        self,
        payload: DaangnEducationMapPointsRequestPayloadModel
    ) -> DaangnEducationMapPointsResponseModel:
        """List schools and preschools in a map range via `POST realty.kr.karrotmarket.com/graphql` (`educationMapPoints`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 좌표 범위, 시설 종류.

        Returns:
            DaangnEducationMapPointsResponseModel: 범위 안 시설 (500개에서 잘림).
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.education_map_points_query_id)
        )
        raise_for_status(response=response)
        return DaangnEducationMapPointsResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_education_map_points(
        self,
        payload: DaangnEducationMapPointsRequestPayloadModel
    ) -> DaangnEducationMapPointsResponseModel:
        """Async variant of `run_request_education_map_points`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.education_map_points_query_id)
        )
        raise_for_status(response=response)
        return DaangnEducationMapPointsResponseModel.model_validate(response.json())

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
    def run_request_complexes_by_original_complex_ids(
        self,
        payload: DaangnComplexesByOriginalComplexIdsRequestPayloadModel
    ) -> DaangnComplexesByOriginalComplexIdsResponseModel:
        """Fetch complex cards by IDs via `POST realty.kr.karrotmarket.com/graphql` (`complexesByOriginalComplexIds`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 단지 ID 목록, 매물 종류.

        Returns:
            DaangnComplexesByOriginalComplexIdsResponseModel: 단지별 세대수·현재 매물 수.
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
        """List trending complexes around a region via `POST realty.kr.karrotmarket.com/graphql` (`trendingComplexes`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지역 ID (문자열), 받을 수.

        Returns:
            DaangnTrendingComplexesResponseModel: 인기 순 단지 (때마다 0~20여 곳).
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

        Same retry behaviour as `run_request_regions_keyword_v1`. 구가 없는 시(세종)는 404 로
        `ResponseStatusError` 가 난다.

        Args:
            parameter: `name1`, `name2` (시도/구).

        Returns:
            DaangnMapReviewsResponseModel: 후기 많은 단지 20곳과 단지별 후기 수.

        Raises:
            RelayStoreNotFoundError: 페이지에 스토어가 없을 때 (구조 변경).
        """
        response = self._client.get(url=self._map_reviews_path(parameter))
        raise_for_status(response=response)
        return parse_map_reviews_html(response.text)

    @daangn_retry
    async def arun_request_map_reviews(
        self,
        parameter: DaangnMapReviewsRequestParameterModel
    ) -> DaangnMapReviewsResponseModel:
        """Async variant of `run_request_map_reviews`."""
        response = await self._async_client.get(url=self._map_reviews_path(parameter))
        raise_for_status(response=response)
        return parse_map_reviews_html(response.text)

    @daangn_retry
    def run_request_region_by_original_region_id(
        self,
        payload: DaangnRegionByOriginalRegionIdRequestPayloadModel
    ) -> DaangnRegionByOriginalRegionIdResponseModel:
        """Fetch a dong's neighborhood review summary via `POST realty.kr.karrotmarket.com/graphql` (`regionByOriginalRegionId`).

        Same retry behaviour as `run_request_article_feed`. 실패는 HTTP 200 의 `errors` 로 온다.

        Args:
            payload: 지역 ID.

        Returns:
            DaangnRegionByOriginalRegionIdResponseModel: 동네 후기 요약 (요약에 쓰인 후기 수). 구는 null.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.region_by_original_region_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnRegionByOriginalRegionIdResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_region_by_original_region_id(
        self,
        payload: DaangnRegionByOriginalRegionIdRequestPayloadModel
    ) -> DaangnRegionByOriginalRegionIdResponseModel:
        """Async variant of `run_request_region_by_original_region_id`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.region_by_original_region_id_query_id)
        )
        raise_for_status(response=response)
        return DaangnRegionByOriginalRegionIdResponseModel.model_validate(response.json())

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
    def run_request_region_complexes(
        self,
        payload: DaangnRegionComplexesRequestPayloadModel
    ) -> DaangnRegionComplexesResponseModel:
        """List a region's complexes via `POST realty.kr.karrotmarket.com/graphql` (`searchComplexes`, 지역 단지 목록).

        Same retry behaviour as `run_request_article_feed`. 단지 조건은 매물 조건과 키가 달라
        (`DaangnComplexFilterModel`) 매물 조건을 그대로 보내면 "알 수 없는 오류" 가 난다.

        Args:
            payload: 동·구 ID(`input.locationFilter`), 단지 조건(`input.propertyFilter`), 정렬(`input.sort`),
                단지마다 보여 줄 실거래의 거래 유형(`tradeType`)과 면적(`exclusiveUseArea`), 페이지.

        Returns:
            DaangnRegionComplexesResponseModel: 정렬 순 단지 카드와 다음 페이지 커서, 또는 `errors`.
        """
        response = self._client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.region_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnRegionComplexesResponseModel.model_validate(response.json())

    @daangn_retry
    async def arun_request_region_complexes(
        self,
        payload: DaangnRegionComplexesRequestPayloadModel
    ) -> DaangnRegionComplexesResponseModel:
        """Async variant of `run_request_region_complexes`."""
        response = await self._async_client.post(
            url=self.graphql_url,
            headers=self.graphql_header,
            json=self._graphql_body(payload, self.region_complexes_query_id)
        )
        raise_for_status(response=response)
        return DaangnRegionComplexesResponseModel.model_validate(response.json())

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
        """Fetch a complex's monthly average prices via `POST realty.kr.karrotmarket.com/graphql` (`complexByOriginalId.complex.priceChart`).

        Same retry behaviour as `run_request_article_feed`. 금액은 **원** 단위로 온다.

        Args:
            payload: 단지 ID, 거래 유형(매매·전세), 월세 제외 여부, 전용면적 범위.

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
