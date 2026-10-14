from functools import cached_property

from httpx import (
    AsyncClient,
    Client,
    HTTPStatusError,
)
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from jibsa.core.http import (
    RETRYABLE_TRANSPORT_ERRORS,
    BaseHTTPClient,
    create_base_url,
    log_retry_before_sleep,
    raise_for_status,
    wait_retry_after,
)
from jibsa.providers.naver.api.request.common import (
    NaverComplexBuildingListV1RequestParameterModel,
    NaverComplexPyeongListV1RequestParameterModel,
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaPyeongListV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
    NaverLegalDivisionSearchByCoordinateV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.complex import (
    NaverComplexArticleStatsV1RequestParameterModel,
    NaverComplexDeclaredValuePyeongTypeV1RequestParameterModel,
    NaverComplexHoldingTaxV1RequestParameterModel,
    NaverComplexMaintenanceFeeV1RequestParameterModel,
    NaverComplexMarketPriceRecentV1RequestParameterModel,
    NaverComplexPyeongRealPriceSummaryV1RequestParameterModel,
    NaverComplexReconstructionV1RequestParameterModel,
    NaverComplexVillaArticleStatsV1RequestParameterModel,
    NaverEducationComplexSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.listing import (
    NaverArticleAgentFeeV1RequestParameterModel,
    NaverArticleAgentV1RequestParameterModel,
    NaverArticleBasicInfoV1RequestParameterModel,
    NaverArticleKeyV1RequestParameterModel,
    NaverArticleMaintenanceFeeV1RequestParameterModel,
    NaverArticleTaxV1RequestParameterModel,
    NaverComplexArticleListV1RequestPayloadModel,
    NaverComplexVillaArticleListV1RequestPayloadModel,
    NaverDataServiceTransportV1RequestParameterModel,
    NaverEducationBuildingSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.market_price import (
    NaverComplexMarketPriceListV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.real_price import (
    NaverComplexPyeongRealPriceListV1RequestParameterModel,
    NaverComplexPyeongRealPriceV2RequestParameterModel,
    NaverComplexVillaRealPricePageV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.redevelopment import (
    NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel,
    NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaListV1RequestPayloadModel,
    NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel,
    NaverComplexRedevelopmentV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.region import (
    NaverLegalDivisionInfoListByLevelV1RequestParameterModel,
    NaverLegalDivisionSubInfoListV1RequestParameterModel,
    NaverMapsSearchAddressV1RequestParameterModel,
    NaverSearchAutocompleteComplexesV1RequestParameterModel,
    NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel,
    NaverSearchAutocompleteSubwayStationsV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.school import (
    NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel,
    NaverEducationSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.search import (
    NaverArticleBoundedArticlesV1RequestPayloadModel,
    NaverArticleClusteredArticlesV1RequestPayloadModel,
    NaverArticleLegalDivisionArticleListV1RequestPayloadModel,
    NaverArticleMapArticleClustersV1RequestPayloadModel,
    NaverComplexBoundedComplexesV1RequestPayloadModel,
    NaverComplexLegalDivisionComplexListV1RequestPayloadModel,
)
from jibsa.providers.naver.api.request.trend import (
    NaverLegalDivisionArticleCountWeeklyInfoV1RequestParameterModel,
    NaverLegalDivisionPyeongPriceWeeklyListV1RequestParameterModel,
    NaverLegalDivisionRealTradeCountWeeklyListV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import (
    NaverComplexBuildingListV1ResponseModel,
    NaverComplexPyeongListV1ResponseModel,
    NaverComplexV1ResponseModel,
    NaverComplexVillaBuildingListV1ResponseModel,
    NaverComplexVillaPyeongListV1ResponseModel,
    NaverComplexVillaV1ResponseModel,
    NaverLegalDivisionSearchByCoordinateV1ResponseModel,
)
from jibsa.providers.naver.api.response.complex import (
    NaverComplexArticleStatsV1ResponseModel,
    NaverComplexDeclaredValuePyeongTypeV1ResponseModel,
    NaverComplexHoldingTaxV1ResponseModel,
    NaverComplexMaintenanceFeeV1ResponseModel,
    NaverComplexMarketPriceRecentV1ResponseModel,
    NaverComplexPyeongRealPriceSummaryV1ResponseModel,
    NaverComplexReconstructionV1ResponseModel,
    NaverComplexVillaArticleStatsV1ResponseModel,
    NaverEducationComplexSchoolV1ResponseModel,
)
from jibsa.providers.naver.api.response.listing import (
    NaverArticleAgentFeeV1ResponseModel,
    NaverArticleAgentV1ResponseModel,
    NaverArticleBasicInfoV1ResponseModel,
    NaverArticleKeyV1ResponseModel,
    NaverArticleMaintenanceFeeV1ResponseModel,
    NaverArticleTaxV1ResponseModel,
    NaverComplexArticleListV1ResponseModel,
    NaverComplexVillaArticleListV1ResponseModel,
    NaverDataServiceTransportV1ResponseModel,
    NaverEducationBuildingSchoolV1ResponseModel,
)
from jibsa.providers.naver.api.response.market_price import (
    NaverComplexMarketPriceListV1ResponseModel,
)
from jibsa.providers.naver.api.response.real_price import (
    NaverComplexPyeongRealPriceListV1ResponseModel,
    NaverComplexPyeongRealPriceV2ResponseModel,
    NaverComplexVillaRealPricePageV1ResponseModel,
)
from jibsa.providers.naver.api.response.redevelopment import (
    NaverComplexRedevelopmentAreaArticleListV1ResponseModel,
    NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel,
    NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel,
    NaverComplexRedevelopmentAreaListV1ResponseModel,
    NaverComplexRedevelopmentAreaMarkersV1ResponseModel,
    NaverComplexRedevelopmentV1ResponseModel,
)
from jibsa.providers.naver.api.response.region import (
    NaverLegalDivisionInfoListByLevelV1ResponseModel,
    NaverLegalDivisionSubInfoListV1ResponseModel,
    NaverMapsSearchAddressV1ResponseModel,
    NaverSearchAutocompleteComplexesV1ResponseModel,
    NaverSearchAutocompleteLegalDivisionsV1ResponseModel,
    NaverSearchAutocompleteSubwayStationsV1ResponseModel,
)
from jibsa.providers.naver.api.response.school import (
    NaverEducationComplexSchoolAllocationDongsV1ResponseModel,
    NaverEducationSchoolV1ResponseModel,
)
from jibsa.providers.naver.api.response.search import (
    NaverArticleBoundedArticlesV1ResponseModel,
    NaverArticleClusteredArticlesV1ResponseModel,
    NaverArticleLegalDivisionArticleListV1ResponseModel,
    NaverArticleMapArticleClustersV1ResponseModel,
    NaverComplexBoundedComplexesV1ResponseModel,
    NaverComplexLegalDivisionComplexListV1ResponseModel,
)
from jibsa.providers.naver.api.response.trend import (
    NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel,
    NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel,
    NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel,
)

from typing import (
    ClassVar,
    TypeVar,
)


_R = TypeVar('_R', bound=BaseModel)


def should_retry_naver(exc: BaseException) -> bool:
    """5xx 와 다시 보내면 나을 수 있는 전송 오류(`RETRYABLE_TRANSPORT_ERRORS`)만 재시도한다.

    네이버의 429(`TOO_MANY_REQUESTS`)는 짧은 rate limit 이 아니라 수 분 이상
    이어지는 봇 차단이라, 1초 뒤 재시도는 차단을 연장할 뿐이다.
    """
    if isinstance(exc, HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, RETRYABLE_TRANSPORT_ERRORS)


naver_retry = retry(
    retry=retry_if_exception(should_retry_naver),
    stop=stop_after_attempt(3),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""조회 전용 엔드포인트 공통 재시도: 최대 3회, 1초 간격, 5xx·timeout·transport 오류만."""


class NaverClient(BaseHTTPClient):
    """네이버페이 부동산 (fin.land.naver.com) 비공식 front-api 클라이언트.

    공개 데이터(단지·매물·시세·실거래가)를 로그인 없이 조회한다. 모든 응답은
    `{isSuccess, detailCode, message, result}` 봉투이고 금액은 **원** 단위다.
    봇 차단을 피하려고 프로세스 간 공유 요청 제한(`rate_limit`)을 건다. 429 를
    받으면 쿨다운 동안 요청 자체를 보내지 않는다.

    action id 는 `/front-api/` 뒤 세그먼트를 snake_case 로 잇고 버전을 끝으로
    옮겨 만든다 (`/front-api/v1/complex/pyeongList` → `complex_pyeong_list_v1`,
    `/front-api/v1/maps-search/address` → `maps_search_address_v1`).
    경로 가운데에 버전이 또 있으면 그 버전을 쓴다 (`/front-api/v1/complex/v2/pyeong/realPrice` →
    `complex_pyeong_real_price_v2`).

    Args:
        host: 호스트 (스킴 제외). Defaults to 'fin.land.naver.com'.
        rate_limit: 요청 제한 정책. Defaults to 1초 간격·분당 30회·429 후 15분 쿨다운.

    Attributes:
        base_url: `url_schema` 와 `host` 로 만든 베이스 URL.

    Example:
        >>> with NaverClient() as client:
        ...     client.run_request_complex_v1(
        ...         NaverComplexV1RequestParameterModel(complex_number=8928)
        ...     )
    """

    complex_v1_endpoint: ClassVar[str] = '/front-api/v1/complex'
    complex_article_stats_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/article/stats'
    complex_pyeong_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/pyeongList'
    complex_building_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/buildingList'
    complex_pyeong_real_price_v2_endpoint: ClassVar[str] = '/front-api/v1/complex/v2/pyeong/realPrice'
    complex_declared_value_pyeong_type_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/declaredValue/pyeongType'
    complex_villa_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/villa'
    complex_villa_article_stats_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/villa/article/stats'
    complex_villa_pyeong_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/villa/pyeongList'
    complex_villa_building_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/villa/buildingList'
    complex_villa_article_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/villa/article/list'
    complex_villa_real_price_page_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/villa/realPricePage'
    complex_holding_tax_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/holdingTax'
    complex_maintenance_fee_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/maintenanceFee'
    complex_market_price_recent_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/marketPrice/recent'
    complex_pyeong_real_price_summary_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/pyeong/realPrice/summary'
    legal_division_search_by_coordinate_v1_endpoint: ClassVar[str] = '/front-api/v1/legalDivision/searchByCoordinate'
    data_service_transport_v1_endpoint: ClassVar[str] = '/front-api/v1/data-service/transport'
    education_building_school_v1_endpoint: ClassVar[str] = '/front-api/v1/education/building/school'
    search_autocomplete_legal_divisions_v1_endpoint: ClassVar[str] = '/front-api/v1/search/autocomplete/legalDivisions'
    search_autocomplete_subway_stations_v1_endpoint: ClassVar[str] = '/front-api/v1/search/autocomplete/subwayStations'
    search_autocomplete_complexes_v1_endpoint: ClassVar[str] = '/front-api/v1/search/autocomplete/complexes'
    maps_search_address_v1_endpoint: ClassVar[str] = '/front-api/v1/maps-search/address'
    article_key_v1_endpoint: ClassVar[str] = '/front-api/v1/article/key'
    article_basic_info_v1_endpoint: ClassVar[str] = '/front-api/v1/article/basicInfo'
    article_agent_v1_endpoint: ClassVar[str] = '/front-api/v1/article/agent'
    article_maintenance_fee_v1_endpoint: ClassVar[str] = '/front-api/v1/article/maintenanceFee'
    article_tax_v1_endpoint: ClassVar[str] = '/front-api/v1/article/tax'
    article_agent_fee_v1_endpoint: ClassVar[str] = '/front-api/v1/article/agentFee'
    complex_article_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/article/list'
    complex_legal_division_complex_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/legalDivisionComplexList'
    complex_bounded_complexes_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/boundedComplexes'
    article_map_article_clusters_v1_endpoint: ClassVar[str] = '/front-api/v1/article/map/articleClusters'
    article_clustered_articles_v1_endpoint: ClassVar[str] = '/front-api/v1/article/clusteredArticles'
    article_bounded_articles_v1_endpoint: ClassVar[str] = '/front-api/v1/article/boundedArticles'
    article_legal_division_article_list_v1_endpoint: ClassVar[str] = '/front-api/v1/article/legalDivisionArticleList'
    education_complex_school_v1_endpoint: ClassVar[str] = '/front-api/v1/education/complex/school'
    legal_division_article_count_weekly_info_v1_endpoint: ClassVar[str] = '/front-api/v1/legalDivision/articleCountWeeklyInfo'
    legal_division_pyeong_price_weekly_list_v1_endpoint: ClassVar[str] = '/front-api/v1/legalDivision/pyeongPriceWeeklyList'
    legal_division_real_trade_count_weekly_list_v1_endpoint: ClassVar[str] = '/front-api/v1/legalDivision/realTradeCountWeeklyList'
    complex_redevelopment_area_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/redevelopmentArea/list'
    complex_redevelopment_area_legal_division_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/redevelopmentArea/legalDivisionList'
    complex_redevelopment_area_markers_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/redevelopmentArea/markers'
    complex_redevelopment_area_article_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/redevelopmentArea/articleList'
    complex_reconstruction_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/reconstruction'
    complex_redevelopment_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/redevelopment'
    complex_redevelopment_area_article_stats_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/redevelopmentArea/articleStats'
    complex_pyeong_real_price_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/pyeong/realPrice/list'
    complex_market_price_list_v1_endpoint: ClassVar[str] = '/front-api/v1/complex/marketPrice/list'
    legal_division_info_list_by_level_v1_endpoint: ClassVar[str] = '/front-api/v1/legalDivision/infoListByLevel'
    legal_division_sub_info_list_v1_endpoint: ClassVar[str] = '/front-api/v1/legalDivision/subInfoList'
    education_school_v1_endpoint: ClassVar[str] = '/front-api/v1/education/school'
    education_complex_school_allocation_dongs_v1_endpoint: ClassVar[str] = '/front-api/v1/education/complex/school/allocation-dongs'

    source_name: ClassVar[str] = 'naver'
    default_rate_limit: ClassVar[dict[str, object]] = {
        'min_interval': 1.0,
        'max_per_minute': 30,
        'cooldown': 900,
    }

    host: str = 'fin.land.naver.com'

    @property
    def base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.host
        )

    @property
    def base_header(self) -> dict[str, str]:
        return {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
            'Origin': 'https://fin.land.naver.com',
            'Referer': 'https://fin.land.naver.com/',
            'User-Agent': self.user_agent,
        }

    @cached_property
    def _client(self) -> Client:
        return Client(
            base_url=self.base_url,
            headers=self.base_header,
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
            event_hooks=self.async_rate_limit_hooks(),
            verify=self.verify,
            timeout=self.timeout,
            proxy=self.proxy
        )

    def _get(self, endpoint: str, parameter: BaseModel, model: type[_R]) -> _R:
        response = self._client.get(
            url=endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return model.model_validate(response.json())

    async def _aget(self, endpoint: str, parameter: BaseModel, model: type[_R]) -> _R:
        response = await self._async_client.get(
            url=endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return model.model_validate(response.json())

    def _post(self, endpoint: str, payload: BaseModel, model: type[_R]) -> _R:
        response = self._client.post(
            url=endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return model.model_validate(response.json())

    async def _apost(self, endpoint: str, payload: BaseModel, model: type[_R]) -> _R:
        response = await self._async_client.post(
            url=endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return model.model_validate(response.json())

    # --- 단지 ---------------------------------------------------------------

    @naver_retry
    def run_request_complex_v1(
        self,
        parameter: NaverComplexV1RequestParameterModel
    ) -> NaverComplexV1ResponseModel:
        """Fetch complex overview via `GET /front-api/v1/complex`.

        Retries up to 3 attempts, 1s apart, on HTTP 5xx and httpx
        timeout/transport errors. 429 는 봇 차단이라 재시도하지 않고 바로 올린다.
        이하 모든 `run_request_*` 가 같은 재시도 규칙을 따른다.

        Args:
            parameter: `complex_number`.

        Returns:
            NaverComplexV1ResponseModel: 단지명·주소·좌표·세대수·준공일·주차.
        """
        return self._get(self.complex_v1_endpoint, parameter, NaverComplexV1ResponseModel)

    @naver_retry
    async def arun_request_complex_v1(
        self,
        parameter: NaverComplexV1RequestParameterModel
    ) -> NaverComplexV1ResponseModel:
        """Async variant of `run_request_complex_v1`."""
        return await self._aget(self.complex_v1_endpoint, parameter, NaverComplexV1ResponseModel)

    @naver_retry
    def run_request_complex_article_stats_v1(
        self,
        parameter: NaverComplexArticleStatsV1RequestParameterModel
    ) -> NaverComplexArticleStatsV1ResponseModel:
        """Count listings and asking-price range via `GET /front-api/v1/complex/article/stats`.

        사이트가 쓰는 엔드포인트다. 예전 `complex/article/count` 와 `complex/article/price` 를 합친 응답이다.

        Args:
            parameter: `complex_number`.

        Returns:
            NaverComplexArticleStatsV1ResponseModel: 매매/전세/월세/단기 건수와 매매·전세 호가 최저/최고 (원).
        """
        return self._get(
            self.complex_article_stats_v1_endpoint, parameter, NaverComplexArticleStatsV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_article_stats_v1(
        self,
        parameter: NaverComplexArticleStatsV1RequestParameterModel
    ) -> NaverComplexArticleStatsV1ResponseModel:
        """Async variant of `run_request_complex_article_stats_v1`."""
        return await self._aget(
            self.complex_article_stats_v1_endpoint, parameter, NaverComplexArticleStatsV1ResponseModel
        )

    @naver_retry
    def run_request_complex_pyeong_list_v1(
        self,
        parameter: NaverComplexPyeongListV1RequestParameterModel
    ) -> NaverComplexPyeongListV1ResponseModel:
        """List floor-plan types via `GET /front-api/v1/complex/pyeongList`.

        Args:
            parameter: `complex_number`.

        Returns:
            NaverComplexPyeongListV1ResponseModel: 평형 번호·이름·공급/전용면적·방 수.
        """
        return self._get(
            self.complex_pyeong_list_v1_endpoint, parameter, NaverComplexPyeongListV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_pyeong_list_v1(
        self,
        parameter: NaverComplexPyeongListV1RequestParameterModel
    ) -> NaverComplexPyeongListV1ResponseModel:
        """Async variant of `run_request_complex_pyeong_list_v1`."""
        return await self._aget(
            self.complex_pyeong_list_v1_endpoint, parameter, NaverComplexPyeongListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_building_list_v1(
        self,
        parameter: NaverComplexBuildingListV1RequestParameterModel
    ) -> NaverComplexBuildingListV1ResponseModel:
        """List a complex's buildings (동) via `GET /front-api/v1/complex/buildingList`.

        단지 매물 목록의 `dongNumbers` 필터는 동 이름이 아니라 이 응답의 `number` 를 받는다.

        Args:
            parameter: `complex_number`.

        Returns:
            NaverComplexBuildingListV1ResponseModel: 동 번호·이름 (빌라 단지는 빈 목록).
        """
        return self._get(
            self.complex_building_list_v1_endpoint, parameter, NaverComplexBuildingListV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_building_list_v1(
        self,
        parameter: NaverComplexBuildingListV1RequestParameterModel
    ) -> NaverComplexBuildingListV1ResponseModel:
        """Async variant of `run_request_complex_building_list_v1`."""
        return await self._aget(
            self.complex_building_list_v1_endpoint, parameter, NaverComplexBuildingListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_pyeong_real_price_v2(
        self,
        parameter: NaverComplexPyeongRealPriceV2RequestParameterModel
    ) -> NaverComplexPyeongRealPriceV2ResponseModel:
        """Fetch actual transactions via `GET /front-api/v1/complex/v2/pyeong/realPrice`.

        Args:
            parameter: `complex_number`, `pyeong_type_number`, `trade_type`, `page` (0부터), `size`.

        Returns:
            NaverComplexPyeongRealPriceV2ResponseModel: 최근 순 실거래 (원)와 다음 페이지 여부.
        """
        return self._get(
            self.complex_pyeong_real_price_v2_endpoint, parameter, NaverComplexPyeongRealPriceV2ResponseModel
        )

    @naver_retry
    async def arun_request_complex_pyeong_real_price_v2(
        self,
        parameter: NaverComplexPyeongRealPriceV2RequestParameterModel
    ) -> NaverComplexPyeongRealPriceV2ResponseModel:
        """Async variant of `run_request_complex_pyeong_real_price_v2`."""
        return await self._aget(
            self.complex_pyeong_real_price_v2_endpoint, parameter, NaverComplexPyeongRealPriceV2ResponseModel
        )

    @naver_retry
    def run_request_complex_declared_value_pyeong_type_v1(
        self,
        parameter: NaverComplexDeclaredValuePyeongTypeV1RequestParameterModel
    ) -> NaverComplexDeclaredValuePyeongTypeV1ResponseModel:
        """Fetch official assessed values via `GET /front-api/v1/complex/declaredValue/pyeongType`.

        Args:
            parameter: `complex_number`, `pyeong_type_number`.

        Returns:
            NaverComplexDeclaredValuePyeongTypeV1ResponseModel: 공시가격 범위 (원).
        """
        return self._get(
            self.complex_declared_value_pyeong_type_v1_endpoint,
            parameter,
            NaverComplexDeclaredValuePyeongTypeV1ResponseModel,
        )

    @naver_retry
    async def arun_request_complex_declared_value_pyeong_type_v1(
        self,
        parameter: NaverComplexDeclaredValuePyeongTypeV1RequestParameterModel
    ) -> NaverComplexDeclaredValuePyeongTypeV1ResponseModel:
        """Async variant of `run_request_complex_declared_value_pyeong_type_v1`."""
        return await self._aget(
            self.complex_declared_value_pyeong_type_v1_endpoint,
            parameter,
            NaverComplexDeclaredValuePyeongTypeV1ResponseModel,
        )

    @naver_retry
    def run_request_complex_holding_tax_v1(
        self,
        parameter: NaverComplexHoldingTaxV1RequestParameterModel
    ) -> NaverComplexHoldingTaxV1ResponseModel:
        """Estimate holding taxes via `GET /front-api/v1/complex/holdingTax`.

        Args:
            parameter: `complex_number`, `pyeong_type_number`.

        Returns:
            NaverComplexHoldingTaxV1ResponseModel: 재산세·종부세 최소/최대 (원).
        """
        return self._get(
            self.complex_holding_tax_v1_endpoint, parameter, NaverComplexHoldingTaxV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_holding_tax_v1(
        self,
        parameter: NaverComplexHoldingTaxV1RequestParameterModel
    ) -> NaverComplexHoldingTaxV1ResponseModel:
        """Async variant of `run_request_complex_holding_tax_v1`."""
        return await self._aget(
            self.complex_holding_tax_v1_endpoint, parameter, NaverComplexHoldingTaxV1ResponseModel
        )

    @naver_retry
    def run_request_complex_maintenance_fee_v1(
        self,
        parameter: NaverComplexMaintenanceFeeV1RequestParameterModel
    ) -> NaverComplexMaintenanceFeeV1ResponseModel:
        """Fetch a floor plan's monthly maintenance fee via `GET /front-api/v1/complex/maintenanceFee`.

        Args:
            parameter: `complex_number`, `pyeong_type_number`.

        Returns:
            NaverComplexMaintenanceFeeV1ResponseModel: 최근 달·월평균·여름·겨울 평균 관리비 (원). 자료가 없으면 빈 객체.
        """
        return self._get(
            self.complex_maintenance_fee_v1_endpoint, parameter, NaverComplexMaintenanceFeeV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_maintenance_fee_v1(
        self,
        parameter: NaverComplexMaintenanceFeeV1RequestParameterModel
    ) -> NaverComplexMaintenanceFeeV1ResponseModel:
        """Async variant of `run_request_complex_maintenance_fee_v1`."""
        return await self._aget(
            self.complex_maintenance_fee_v1_endpoint, parameter, NaverComplexMaintenanceFeeV1ResponseModel
        )

    @naver_retry
    def run_request_complex_market_price_recent_v1(
        self,
        parameter: NaverComplexMarketPriceRecentV1RequestParameterModel
    ) -> NaverComplexMarketPriceRecentV1ResponseModel:
        """Fetch the latest estimated prices via `GET /front-api/v1/complex/marketPrice/recent`.

        Args:
            parameter: `complex_number`, `pyeong_type_number`, `real_estate_type`, `cp_list`.

        Returns:
            NaverComplexMarketPriceRecentV1ResponseModel: 제공처별 기준일·매매/전세 시세 범위·전세가율 (원).
                시세가 없는 단지(빌라 등)는 빈 목록.
        """
        return self._get(
            self.complex_market_price_recent_v1_endpoint, parameter, NaverComplexMarketPriceRecentV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_market_price_recent_v1(
        self,
        parameter: NaverComplexMarketPriceRecentV1RequestParameterModel
    ) -> NaverComplexMarketPriceRecentV1ResponseModel:
        """Async variant of `run_request_complex_market_price_recent_v1`."""
        return await self._aget(
            self.complex_market_price_recent_v1_endpoint, parameter, NaverComplexMarketPriceRecentV1ResponseModel
        )

    @naver_retry
    def run_request_complex_pyeong_real_price_summary_v1(
        self,
        parameter: NaverComplexPyeongRealPriceSummaryV1RequestParameterModel
    ) -> NaverComplexPyeongRealPriceSummaryV1ResponseModel:
        """Summarise actual transactions since a date via `GET /front-api/v1/complex/pyeong/realPrice/summary`.

        Args:
            parameter: `complex_number`, `pyeong_type_number`, `trade_type`, `start_date`.

        Returns:
            NaverComplexPyeongRealPriceSummaryV1ResponseModel: 최저·최고 거래와 평균 (원). 거래가 없으면 빈 객체.
        """
        return self._get(
            self.complex_pyeong_real_price_summary_v1_endpoint,
            parameter,
            NaverComplexPyeongRealPriceSummaryV1ResponseModel,
        )

    @naver_retry
    async def arun_request_complex_pyeong_real_price_summary_v1(
        self,
        parameter: NaverComplexPyeongRealPriceSummaryV1RequestParameterModel
    ) -> NaverComplexPyeongRealPriceSummaryV1ResponseModel:
        """Async variant of `run_request_complex_pyeong_real_price_summary_v1`."""
        return await self._aget(
            self.complex_pyeong_real_price_summary_v1_endpoint,
            parameter,
            NaverComplexPyeongRealPriceSummaryV1ResponseModel,
        )

    @naver_retry
    def run_request_complex_villa_v1(
        self,
        parameter: NaverComplexVillaV1RequestParameterModel
    ) -> NaverComplexVillaV1ResponseModel:
        """Fetch a villa 단지 (연립·다세대) summary via `GET /front-api/v1/complex/villa`.

        단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 빈 결과를 줘 이쪽으로 따로 묻는다.

        Returns:
            NaverComplexVillaV1ResponseModel: 이름·주소·세대수·사용승인일·주차.
        """
        return self._get(self.complex_villa_v1_endpoint, parameter, NaverComplexVillaV1ResponseModel)

    @naver_retry
    async def arun_request_complex_villa_v1(
        self,
        parameter: NaverComplexVillaV1RequestParameterModel
    ) -> NaverComplexVillaV1ResponseModel:
        """Async variant of `run_request_complex_villa_v1`."""
        return await self._aget(self.complex_villa_v1_endpoint, parameter, NaverComplexVillaV1ResponseModel)

    @naver_retry
    def run_request_complex_villa_article_stats_v1(
        self,
        parameter: NaverComplexVillaArticleStatsV1RequestParameterModel
    ) -> NaverComplexVillaArticleStatsV1ResponseModel:
        """Count villa 단지 listings and asking prices via `GET /front-api/v1/complex/villa/article/stats`.

        단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 빈 결과를 줘 이쪽으로 따로 묻는다.

        Returns:
            NaverComplexVillaArticleStatsV1ResponseModel: 거래 유형별 건수와 호가 범위 (원).
        """
        return self._get(self.complex_villa_article_stats_v1_endpoint, parameter, NaverComplexVillaArticleStatsV1ResponseModel)

    @naver_retry
    async def arun_request_complex_villa_article_stats_v1(
        self,
        parameter: NaverComplexVillaArticleStatsV1RequestParameterModel
    ) -> NaverComplexVillaArticleStatsV1ResponseModel:
        """Async variant of `run_request_complex_villa_article_stats_v1`."""
        return await self._aget(self.complex_villa_article_stats_v1_endpoint, parameter, NaverComplexVillaArticleStatsV1ResponseModel)

    @naver_retry
    def run_request_complex_villa_pyeong_list_v1(
        self,
        parameter: NaverComplexVillaPyeongListV1RequestParameterModel
    ) -> NaverComplexVillaPyeongListV1ResponseModel:
        """List villa 단지 floor-plan types via `GET /front-api/v1/complex/villa/pyeongList`.

        단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 빈 결과를 줘 이쪽으로 따로 묻는다.

        Returns:
            NaverComplexVillaPyeongListV1ResponseModel: 평형 번호·이름·공급/전용면적.
        """
        return self._get(self.complex_villa_pyeong_list_v1_endpoint, parameter, NaverComplexVillaPyeongListV1ResponseModel)

    @naver_retry
    async def arun_request_complex_villa_pyeong_list_v1(
        self,
        parameter: NaverComplexVillaPyeongListV1RequestParameterModel
    ) -> NaverComplexVillaPyeongListV1ResponseModel:
        """Async variant of `run_request_complex_villa_pyeong_list_v1`."""
        return await self._aget(self.complex_villa_pyeong_list_v1_endpoint, parameter, NaverComplexVillaPyeongListV1ResponseModel)

    @naver_retry
    def run_request_complex_villa_building_list_v1(
        self,
        parameter: NaverComplexVillaBuildingListV1RequestParameterModel
    ) -> NaverComplexVillaBuildingListV1ResponseModel:
        """List a villa 단지's buildings (동) via `GET /front-api/v1/complex/villa/buildingList`.

        단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 빈 결과를 줘 이쪽으로 따로 묻는다.
        응답은 아파트 단지 동 목록과 같은 `number`·`name` 이다 (2026-10-09 더원스타빌 482441 로 확인).

        Returns:
            NaverComplexVillaBuildingListV1ResponseModel: 동 번호·이름.
        """
        return self._get(self.complex_villa_building_list_v1_endpoint, parameter, NaverComplexVillaBuildingListV1ResponseModel)

    @naver_retry
    async def arun_request_complex_villa_building_list_v1(
        self,
        parameter: NaverComplexVillaBuildingListV1RequestParameterModel
    ) -> NaverComplexVillaBuildingListV1ResponseModel:
        """Async variant of `run_request_complex_villa_building_list_v1`."""
        return await self._aget(self.complex_villa_building_list_v1_endpoint, parameter, NaverComplexVillaBuildingListV1ResponseModel)

    @naver_retry
    def run_request_complex_villa_article_list_v1(
        self,
        payload: NaverComplexVillaArticleListV1RequestPayloadModel
    ) -> NaverComplexVillaArticleListV1ResponseModel:
        """List villa 단지 listings via `POST /front-api/v1/complex/villa/article/list`.

        단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 빈 결과를 줘 이쪽으로 따로 묻는다.

        Returns:
            NaverComplexVillaArticleListV1ResponseModel: 매물 페이지와 다음 커서(`lastInfo`).
        """
        return self._post(self.complex_villa_article_list_v1_endpoint, payload, NaverComplexVillaArticleListV1ResponseModel)

    @naver_retry
    async def arun_request_complex_villa_article_list_v1(
        self,
        payload: NaverComplexVillaArticleListV1RequestPayloadModel
    ) -> NaverComplexVillaArticleListV1ResponseModel:
        """Async variant of `run_request_complex_villa_article_list_v1`."""
        return await self._apost(self.complex_villa_article_list_v1_endpoint, payload, NaverComplexVillaArticleListV1ResponseModel)

    @naver_retry
    def run_request_complex_villa_real_price_page_v1(
        self,
        parameter: NaverComplexVillaRealPricePageV1RequestParameterModel
    ) -> NaverComplexVillaRealPricePageV1ResponseModel:
        """Fetch villa 단지 actual transactions via `GET /front-api/v1/complex/villa/realPricePage`.

        단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 빈 결과를 줘 이쪽으로 따로 묻는다.

        Returns:
            NaverComplexVillaRealPricePageV1ResponseModel: 최근 순 실거래 (원)와 다음 페이지 여부.
        """
        return self._get(self.complex_villa_real_price_page_v1_endpoint, parameter, NaverComplexVillaRealPricePageV1ResponseModel)

    @naver_retry
    async def arun_request_complex_villa_real_price_page_v1(
        self,
        parameter: NaverComplexVillaRealPricePageV1RequestParameterModel
    ) -> NaverComplexVillaRealPricePageV1ResponseModel:
        """Async variant of `run_request_complex_villa_real_price_page_v1`."""
        return await self._aget(self.complex_villa_real_price_page_v1_endpoint, parameter, NaverComplexVillaRealPricePageV1ResponseModel)

    # --- 주변 (교통·학교) -----------------------------------------------------

    @naver_retry
    def run_request_data_service_transport_v1(
        self,
        parameter: NaverDataServiceTransportV1RequestParameterModel
    ) -> NaverDataServiceTransportV1ResponseModel:
        """Fetch nearby subway stations and bus routes via `GET /front-api/v1/data-service/transport`.

        매물 상세 화면의 교통 정보다. 단지가 없는 매물도 매물 번호로 받는다.

        Args:
            parameter: `item_type` (매물은 article), `item_id`.

        Returns:
            NaverDataServiceTransportV1ResponseModel: 역 이름·노선·도보 거리/시간, 버스 종류별 노선.
        """
        return self._get(
            self.data_service_transport_v1_endpoint, parameter, NaverDataServiceTransportV1ResponseModel
        )

    @naver_retry
    async def arun_request_data_service_transport_v1(
        self,
        parameter: NaverDataServiceTransportV1RequestParameterModel
    ) -> NaverDataServiceTransportV1ResponseModel:
        """Async variant of `run_request_data_service_transport_v1`."""
        return await self._aget(
            self.data_service_transport_v1_endpoint, parameter, NaverDataServiceTransportV1ResponseModel
        )

    @naver_retry
    def run_request_education_building_school_v1(
        self,
        parameter: NaverEducationBuildingSchoolV1RequestParameterModel
    ) -> NaverEducationBuildingSchoolV1ResponseModel:
        """Fetch a building's assigned elementary schools via `GET /front-api/v1/education/building/school`.

        Args:
            parameter: `item_type` (complex, 단지형 빌라는 villa), `complex_number`, `building_number`.

        Returns:
            NaverEducationBuildingSchoolV1ResponseModel: 학교 이름·운영 구분·배정 방식·학급당 학생 수·도보 거리/시간.
        """
        return self._get(
            self.education_building_school_v1_endpoint, parameter, NaverEducationBuildingSchoolV1ResponseModel
        )

    @naver_retry
    async def arun_request_education_building_school_v1(
        self,
        parameter: NaverEducationBuildingSchoolV1RequestParameterModel
    ) -> NaverEducationBuildingSchoolV1ResponseModel:
        """Async variant of `run_request_education_building_school_v1`."""
        return await self._aget(
            self.education_building_school_v1_endpoint, parameter, NaverEducationBuildingSchoolV1ResponseModel
        )

    # --- 지역 ---------------------------------------------------------------

    @naver_retry
    def run_request_legal_division_search_by_coordinate_v1(
        self,
        parameter: NaverLegalDivisionSearchByCoordinateV1RequestParameterModel
    ) -> NaverLegalDivisionSearchByCoordinateV1ResponseModel:
        """Resolve a coordinate to its 법정동 via `GET /front-api/v1/legalDivision/searchByCoordinate`.

        Args:
            parameter: `longitude`, `latitude`.

        Returns:
            NaverLegalDivisionSearchByCoordinateV1ResponseModel: 법정동 코드와 이름.
        """
        return self._get(
            self.legal_division_search_by_coordinate_v1_endpoint,
            parameter,
            NaverLegalDivisionSearchByCoordinateV1ResponseModel,
        )

    @naver_retry
    async def arun_request_legal_division_search_by_coordinate_v1(
        self,
        parameter: NaverLegalDivisionSearchByCoordinateV1RequestParameterModel
    ) -> NaverLegalDivisionSearchByCoordinateV1ResponseModel:
        """Async variant of `run_request_legal_division_search_by_coordinate_v1`."""
        return await self._aget(
            self.legal_division_search_by_coordinate_v1_endpoint,
            parameter,
            NaverLegalDivisionSearchByCoordinateV1ResponseModel,
        )

    @naver_retry
    def run_request_search_autocomplete_legal_divisions_v1(
        self,
        parameter: NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel
    ) -> NaverSearchAutocompleteLegalDivisionsV1ResponseModel:
        """Search 법정동 (시·구·동) by name via `GET /front-api/v1/search/autocomplete/legalDivisions`.

        사이트 검색창의 자동완성과 같은 결과다. 로그인 없이 쓴다.

        Args:
            parameter: `keyword`, `page`.

        Returns:
            NaverSearchAutocompleteLegalDivisionsV1ResponseModel: 법정동 코드·이름·단위·중심 좌표.
        """
        return self._get(
            self.search_autocomplete_legal_divisions_v1_endpoint,
            parameter,
            NaverSearchAutocompleteLegalDivisionsV1ResponseModel,
        )

    @naver_retry
    async def arun_request_search_autocomplete_legal_divisions_v1(
        self,
        parameter: NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel
    ) -> NaverSearchAutocompleteLegalDivisionsV1ResponseModel:
        """Async variant of `run_request_search_autocomplete_legal_divisions_v1`."""
        return await self._aget(
            self.search_autocomplete_legal_divisions_v1_endpoint,
            parameter,
            NaverSearchAutocompleteLegalDivisionsV1ResponseModel,
        )

    @naver_retry
    def run_request_search_autocomplete_subway_stations_v1(
        self,
        parameter: NaverSearchAutocompleteSubwayStationsV1RequestParameterModel
    ) -> NaverSearchAutocompleteSubwayStationsV1ResponseModel:
        """Search subway stations by name via `GET /front-api/v1/search/autocomplete/subwayStations`.

        사이트 검색창의 자동완성과 같은 결과다. 로그인 없이 쓴다.

        Args:
            parameter: `keyword`, `page`.

        Returns:
            NaverSearchAutocompleteSubwayStationsV1ResponseModel: 역 이름·좌표·노선.
        """
        return self._get(
            self.search_autocomplete_subway_stations_v1_endpoint,
            parameter,
            NaverSearchAutocompleteSubwayStationsV1ResponseModel,
        )

    @naver_retry
    async def arun_request_search_autocomplete_subway_stations_v1(
        self,
        parameter: NaverSearchAutocompleteSubwayStationsV1RequestParameterModel
    ) -> NaverSearchAutocompleteSubwayStationsV1ResponseModel:
        """Async variant of `run_request_search_autocomplete_subway_stations_v1`."""
        return await self._aget(
            self.search_autocomplete_subway_stations_v1_endpoint,
            parameter,
            NaverSearchAutocompleteSubwayStationsV1ResponseModel,
        )

    @naver_retry
    def run_request_search_autocomplete_complexes_v1(
        self,
        parameter: NaverSearchAutocompleteComplexesV1RequestParameterModel
    ) -> NaverSearchAutocompleteComplexesV1ResponseModel:
        """Search 단지 by name via `GET /front-api/v1/search/autocomplete/complexes`.

        사이트 검색창의 자동완성과 같은 결과다. 로그인 없이 쓴다.

        Args:
            parameter: `keyword`, `page`.

        Returns:
            NaverSearchAutocompleteComplexesV1ResponseModel: 단지 번호·이름·유형·법정동·좌표.
        """
        return self._get(
            self.search_autocomplete_complexes_v1_endpoint,
            parameter,
            NaverSearchAutocompleteComplexesV1ResponseModel,
        )

    @naver_retry
    async def arun_request_search_autocomplete_complexes_v1(
        self,
        parameter: NaverSearchAutocompleteComplexesV1RequestParameterModel
    ) -> NaverSearchAutocompleteComplexesV1ResponseModel:
        """Async variant of `run_request_search_autocomplete_complexes_v1`."""
        return await self._aget(
            self.search_autocomplete_complexes_v1_endpoint,
            parameter,
            NaverSearchAutocompleteComplexesV1ResponseModel,
        )

    @naver_retry
    def run_request_maps_search_address_v1(
        self,
        parameter: NaverMapsSearchAddressV1RequestParameterModel
    ) -> NaverMapsSearchAddressV1ResponseModel:
        """Search an address via `GET /front-api/v1/maps-search/address`.

        사이트 검색창의 주소 검색이다. 로그인 없이 쓴다. 못 찾으면 성공 응답에 type 이 null 이다.

        Args:
            parameter: `query`.

        Returns:
            NaverMapsSearchAddressV1ResponseModel: 지번·도로명 주소 후보와 좌표·법정동 코드·주소 단위.
        """
        return self._get(
            self.maps_search_address_v1_endpoint, parameter, NaverMapsSearchAddressV1ResponseModel
        )

    @naver_retry
    async def arun_request_maps_search_address_v1(
        self,
        parameter: NaverMapsSearchAddressV1RequestParameterModel
    ) -> NaverMapsSearchAddressV1ResponseModel:
        """Async variant of `run_request_maps_search_address_v1`."""
        return await self._aget(
            self.maps_search_address_v1_endpoint, parameter, NaverMapsSearchAddressV1ResponseModel
        )

    # --- 매물 ---------------------------------------------------------------

    @naver_retry
    def run_request_article_key_v1(
        self,
        parameter: NaverArticleKeyV1RequestParameterModel
    ) -> NaverArticleKeyV1ResponseModel:
        """Fetch a listing's keys and type codes via `GET /front-api/v1/article/key`.

        Args:
            parameter: `article_number`.

        Returns:
            NaverArticleKeyV1ResponseModel: 단지·평형 번호와 basicInfo 에 넘길
                `real_estate_type` / `trade_type`.
        """
        return self._get(self.article_key_v1_endpoint, parameter, NaverArticleKeyV1ResponseModel)

    @naver_retry
    async def arun_request_article_key_v1(
        self,
        parameter: NaverArticleKeyV1RequestParameterModel
    ) -> NaverArticleKeyV1ResponseModel:
        """Async variant of `run_request_article_key_v1`."""
        return await self._aget(self.article_key_v1_endpoint, parameter, NaverArticleKeyV1ResponseModel)

    @naver_retry
    def run_request_article_basic_info_v1(
        self,
        parameter: NaverArticleBasicInfoV1RequestParameterModel
    ) -> NaverArticleBasicInfoV1ResponseModel:
        """Fetch listing detail via `GET /front-api/v1/article/basicInfo`.

        Args:
            parameter: `article_number`, `real_estate_type`, `trade_type`.

        Returns:
            NaverArticleBasicInfoV1ResponseModel: 가격(원)·면적·층·시설·입주일.
        """
        return self._get(
            self.article_basic_info_v1_endpoint, parameter, NaverArticleBasicInfoV1ResponseModel
        )

    @naver_retry
    async def arun_request_article_basic_info_v1(
        self,
        parameter: NaverArticleBasicInfoV1RequestParameterModel
    ) -> NaverArticleBasicInfoV1ResponseModel:
        """Async variant of `run_request_article_basic_info_v1`."""
        return await self._aget(
            self.article_basic_info_v1_endpoint, parameter, NaverArticleBasicInfoV1ResponseModel
        )

    @naver_retry
    def run_request_article_agent_v1(
        self,
        parameter: NaverArticleAgentV1RequestParameterModel
    ) -> NaverArticleAgentV1ResponseModel:
        """Fetch the listing agent via `GET /front-api/v1/article/agent`.

        Args:
            parameter: `article_number`.

        Returns:
            NaverArticleAgentV1ResponseModel: 중개사무소명·주소·등록번호·연락처.
        """
        return self._get(self.article_agent_v1_endpoint, parameter, NaverArticleAgentV1ResponseModel)

    @naver_retry
    async def arun_request_article_agent_v1(
        self,
        parameter: NaverArticleAgentV1RequestParameterModel
    ) -> NaverArticleAgentV1ResponseModel:
        """Async variant of `run_request_article_agent_v1`."""
        return await self._aget(self.article_agent_v1_endpoint, parameter, NaverArticleAgentV1ResponseModel)

    @naver_retry
    def run_request_article_tax_v1(
        self,
        parameter: NaverArticleTaxV1RequestParameterModel
    ) -> NaverArticleTaxV1ResponseModel:
        """Estimate taxes for a listing via `GET /front-api/v1/article/tax`.

        사이트 매물 상세의 계산값이다.

        Args:
            parameter: `article_number`.

        Returns:
            NaverArticleTaxV1ResponseModel: 취득세·재산세·종부세 (원).
        """
        return self._get(self.article_tax_v1_endpoint, parameter, NaverArticleTaxV1ResponseModel)

    @naver_retry
    async def arun_request_article_tax_v1(
        self,
        parameter: NaverArticleTaxV1RequestParameterModel
    ) -> NaverArticleTaxV1ResponseModel:
        """Async variant of `run_request_article_tax_v1`."""
        return await self._aget(self.article_tax_v1_endpoint, parameter, NaverArticleTaxV1ResponseModel)

    @naver_retry
    def run_request_article_agent_fee_v1(
        self,
        parameter: NaverArticleAgentFeeV1RequestParameterModel
    ) -> NaverArticleAgentFeeV1ResponseModel:
        """Estimate the brokerage fee for a listing via `GET /front-api/v1/article/agentFee`.

        사이트 매물 상세의 계산값이다.

        Args:
            parameter: `article_number`.

        Returns:
            NaverArticleAgentFeeV1ResponseModel: 중개보수 상한과 요율.
        """
        return self._get(self.article_agent_fee_v1_endpoint, parameter, NaverArticleAgentFeeV1ResponseModel)

    @naver_retry
    async def arun_request_article_agent_fee_v1(
        self,
        parameter: NaverArticleAgentFeeV1RequestParameterModel
    ) -> NaverArticleAgentFeeV1ResponseModel:
        """Async variant of `run_request_article_agent_fee_v1`."""
        return await self._aget(self.article_agent_fee_v1_endpoint, parameter, NaverArticleAgentFeeV1ResponseModel)

    @naver_retry
    def run_request_article_maintenance_fee_v1(
        self,
        parameter: NaverArticleMaintenanceFeeV1RequestParameterModel
    ) -> NaverArticleMaintenanceFeeV1ResponseModel:
        """Fetch the maintenance fee via `GET /front-api/v1/article/maintenanceFee`.

        Args:
            parameter: `article_number`.

        Returns:
            NaverArticleMaintenanceFeeV1ResponseModel: 월 관리비 (원).
        """
        return self._get(
            self.article_maintenance_fee_v1_endpoint, parameter, NaverArticleMaintenanceFeeV1ResponseModel
        )

    @naver_retry
    async def arun_request_article_maintenance_fee_v1(
        self,
        parameter: NaverArticleMaintenanceFeeV1RequestParameterModel
    ) -> NaverArticleMaintenanceFeeV1ResponseModel:
        """Async variant of `run_request_article_maintenance_fee_v1`."""
        return await self._aget(
            self.article_maintenance_fee_v1_endpoint, parameter, NaverArticleMaintenanceFeeV1ResponseModel
        )

    # --- 매물 목록 (POST, 조회 전용) ------------------------------------------

    @naver_retry
    def run_request_complex_article_list_v1(
        self,
        payload: NaverComplexArticleListV1RequestPayloadModel
    ) -> NaverComplexArticleListV1ResponseModel:
        """List a complex's listings via `POST /front-api/v1/complex/article/list`.

        조회 전용이라 GET 과 같은 재시도 규칙을 쓴다. 다음 페이지는 응답의
        `last_info` 를 그대로 `payload.last_info` 에 넣어 요청한다.

        Args:
            payload: `complex_number`, 거래 유형·평형·동 필터, 정렬, `size`, `last_info`.

        Returns:
            NaverComplexArticleListV1ResponseModel: 매물 페이지와 다음 커서.
        """
        return self._post(
            self.complex_article_list_v1_endpoint, payload, NaverComplexArticleListV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_article_list_v1(
        self,
        payload: NaverComplexArticleListV1RequestPayloadModel
    ) -> NaverComplexArticleListV1ResponseModel:
        """Async variant of `run_request_complex_article_list_v1`."""
        return await self._apost(
            self.complex_article_list_v1_endpoint, payload, NaverComplexArticleListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_legal_division_complex_list_v1(
        self,
        payload: NaverComplexLegalDivisionComplexListV1RequestPayloadModel
    ) -> NaverComplexLegalDivisionComplexListV1ResponseModel:
        """List a 법정동's complexes via `POST /front-api/v1/complex/legalDivisionComplexList`.

        조회 전용이라 POST 지만 재시도한다. 다음 페이지는 응답의 `seed`·`last_info` 를 그대로 넘긴다.

        Args:
            payload: 법정동 코드를 넣은 필터, 정렬·커서.

        Returns:
            NaverComplexLegalDivisionComplexListV1ResponseModel: 단지 페이지 (전체 수 포함)와 다음 커서.
        """
        return self._post(
            self.complex_legal_division_complex_list_v1_endpoint,
            payload,
            NaverComplexLegalDivisionComplexListV1ResponseModel,
        )

    @naver_retry
    async def arun_request_complex_legal_division_complex_list_v1(
        self,
        payload: NaverComplexLegalDivisionComplexListV1RequestPayloadModel
    ) -> NaverComplexLegalDivisionComplexListV1ResponseModel:
        """Async variant of `run_request_complex_legal_division_complex_list_v1`."""
        return await self._apost(
            self.complex_legal_division_complex_list_v1_endpoint,
            payload,
            NaverComplexLegalDivisionComplexListV1ResponseModel,
        )

    @naver_retry
    def run_request_complex_bounded_complexes_v1(
        self,
        payload: NaverComplexBoundedComplexesV1RequestPayloadModel
    ) -> NaverComplexBoundedComplexesV1ResponseModel:
        """List complexes in a viewport via `POST /front-api/v1/complex/boundedComplexes`.

        조회 전용이라 POST 지만 재시도한다.

        Args:
            payload: 필터·사각형·정렬·커서.

        Returns:
            NaverComplexBoundedComplexesV1ResponseModel: 단지 페이지와 다음 커서.
        """
        return self._post(
            self.complex_bounded_complexes_v1_endpoint, payload, NaverComplexBoundedComplexesV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_bounded_complexes_v1(
        self,
        payload: NaverComplexBoundedComplexesV1RequestPayloadModel
    ) -> NaverComplexBoundedComplexesV1ResponseModel:
        """Async variant of `run_request_complex_bounded_complexes_v1`."""
        return await self._apost(
            self.complex_bounded_complexes_v1_endpoint, payload, NaverComplexBoundedComplexesV1ResponseModel
        )

    @naver_retry
    def run_request_article_map_article_clusters_v1(
        self,
        payload: NaverArticleMapArticleClustersV1RequestPayloadModel
    ) -> NaverArticleMapArticleClustersV1ResponseModel:
        """Cluster listings in a viewport via `POST /front-api/v1/article/map/articleClusters`.

        Args:
            payload: `filter` (유형·법정동), `bounding_box`, `precision`.

        Returns:
            NaverArticleMapArticleClustersV1ResponseModel: 클러스터 ID·중심·매물 수.
        """
        return self._post(
            self.article_map_article_clusters_v1_endpoint, payload, NaverArticleMapArticleClustersV1ResponseModel
        )

    @naver_retry
    async def arun_request_article_map_article_clusters_v1(
        self,
        payload: NaverArticleMapArticleClustersV1RequestPayloadModel
    ) -> NaverArticleMapArticleClustersV1ResponseModel:
        """Async variant of `run_request_article_map_article_clusters_v1`."""
        return await self._apost(
            self.article_map_article_clusters_v1_endpoint, payload, NaverArticleMapArticleClustersV1ResponseModel
        )

    @naver_retry
    def run_request_article_bounded_articles_v1(
        self,
        payload: NaverArticleBoundedArticlesV1RequestPayloadModel
    ) -> NaverArticleBoundedArticlesV1ResponseModel:
        """List listings in a viewport in a server sort order via `POST /front-api/v1/article/boundedArticles`.

        조회 전용이라 POST 지만 재시도한다.

        Args:
            payload: 필터·사각형·정렬·커서.

        Returns:
            NaverArticleBoundedArticlesV1ResponseModel: 정렬된 매물 페이지와 다음 커서(`lastInfo`).
        """
        return self._post(
            self.article_bounded_articles_v1_endpoint, payload, NaverArticleBoundedArticlesV1ResponseModel
        )

    @naver_retry
    async def arun_request_article_bounded_articles_v1(
        self,
        payload: NaverArticleBoundedArticlesV1RequestPayloadModel
    ) -> NaverArticleBoundedArticlesV1ResponseModel:
        """Async variant of `run_request_article_bounded_articles_v1`."""
        return await self._apost(
            self.article_bounded_articles_v1_endpoint, payload, NaverArticleBoundedArticlesV1ResponseModel
        )

    @naver_retry
    def run_request_article_legal_division_article_list_v1(
        self,
        payload: NaverArticleLegalDivisionArticleListV1RequestPayloadModel
    ) -> NaverArticleLegalDivisionArticleListV1ResponseModel:
        """List a 법정동's listings in a server sort order via `POST /front-api/v1/article/legalDivisionArticleList`.

        조회 전용이라 POST 지만 재시도한다. 다음 페이지는 응답의 `seed`·`last_info` 를 그대로 넘긴다.

        Args:
            payload: 법정동 코드를 넣은 필터, 정렬·커서.

        Returns:
            NaverArticleLegalDivisionArticleListV1ResponseModel: 동 안 매물 페이지 (전체 건수 포함)와 다음 커서.
        """
        return self._post(
            self.article_legal_division_article_list_v1_endpoint,
            payload,
            NaverArticleLegalDivisionArticleListV1ResponseModel,
        )

    @naver_retry
    async def arun_request_article_legal_division_article_list_v1(
        self,
        payload: NaverArticleLegalDivisionArticleListV1RequestPayloadModel
    ) -> NaverArticleLegalDivisionArticleListV1ResponseModel:
        """Async variant of `run_request_article_legal_division_article_list_v1`."""
        return await self._apost(
            self.article_legal_division_article_list_v1_endpoint,
            payload,
            NaverArticleLegalDivisionArticleListV1ResponseModel,
        )

    @naver_retry
    def run_request_article_clustered_articles_v1(
        self,
        payload: NaverArticleClusteredArticlesV1RequestPayloadModel
    ) -> NaverArticleClusteredArticlesV1ResponseModel:
        """List a cluster's listings via `POST /front-api/v1/article/clusteredArticles`.

        응답이 매물당 수십 KB(중복 매물 묶음 포함)라 `size` 를 작게 유지한다.
        다음 페이지는 응답의 `seed`·`last_info` 를 그대로 넘긴다.

        Args:
            payload: `cluster_id`, `filter`, `article_paging_request`.

        Returns:
            NaverArticleClusteredArticlesV1ResponseModel: 매물 페이지와 다음 커서.
        """
        return self._post(
            self.article_clustered_articles_v1_endpoint, payload, NaverArticleClusteredArticlesV1ResponseModel
        )

    @naver_retry
    async def arun_request_article_clustered_articles_v1(
        self,
        payload: NaverArticleClusteredArticlesV1RequestPayloadModel
    ) -> NaverArticleClusteredArticlesV1ResponseModel:
        """Async variant of `run_request_article_clustered_articles_v1`."""
        return await self._apost(
            self.article_clustered_articles_v1_endpoint, payload, NaverArticleClusteredArticlesV1ResponseModel
        )

    @naver_retry
    def run_request_education_complex_school_v1(
        self,
        parameter: NaverEducationComplexSchoolV1RequestParameterModel
    ) -> NaverEducationComplexSchoolV1ResponseModel:
        """Fetch a complex's assigned elementary schools via `GET /front-api/v1/education/complex/school`.

        Args:
            parameter: `complex_number`, `item_type` (complex, 단지형 빌라는 villa).

        Returns:
            NaverEducationComplexSchoolV1ResponseModel: 학교 이름·운영 구분·배정 방식·학급당 학생 수·도보 거리/시간.
        """
        return self._get(
            self.education_complex_school_v1_endpoint, parameter, NaverEducationComplexSchoolV1ResponseModel
        )

    @naver_retry
    async def arun_request_education_complex_school_v1(
        self,
        parameter: NaverEducationComplexSchoolV1RequestParameterModel
    ) -> NaverEducationComplexSchoolV1ResponseModel:
        """Async variant of `run_request_education_complex_school_v1`."""
        return await self._aget(
            self.education_complex_school_v1_endpoint, parameter, NaverEducationComplexSchoolV1ResponseModel
        )

    @naver_retry
    def run_request_legal_division_article_count_weekly_info_v1(
        self,
        parameter: NaverLegalDivisionArticleCountWeeklyInfoV1RequestParameterModel
    ) -> NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel:
        """Fetch a district's weekly apartment listing counts via `GET /front-api/v1/legalDivision/articleCountWeeklyInfo`.

        Args:
            parameter: 법정동 코드·거래 유형(매매·전세)·기간·평형대.

        Returns:
            NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel: 기간 평균·최소·최대·최근 주 매물 수, 증감률, 주별 값.
        """
        return self._get(
            self.legal_division_article_count_weekly_info_v1_endpoint, parameter, NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel
        )

    @naver_retry
    async def arun_request_legal_division_article_count_weekly_info_v1(
        self,
        parameter: NaverLegalDivisionArticleCountWeeklyInfoV1RequestParameterModel
    ) -> NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel:
        """Async variant of `run_request_legal_division_article_count_weekly_info_v1`."""
        return await self._aget(
            self.legal_division_article_count_weekly_info_v1_endpoint, parameter, NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel
        )

    @naver_retry
    def run_request_legal_division_pyeong_price_weekly_list_v1(
        self,
        parameter: NaverLegalDivisionPyeongPriceWeeklyListV1RequestParameterModel
    ) -> NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel:
        """Fetch a district's weekly average asking price per pyeong via `GET /front-api/v1/legalDivision/pyeongPriceWeeklyList`.

        Args:
            parameter: 법정동 코드·거래 유형(매매·전세)·기간·평형대.

        Returns:
            NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel: 주별 평균 평당 호가 (원).
        """
        return self._get(
            self.legal_division_pyeong_price_weekly_list_v1_endpoint, parameter, NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel
        )

    @naver_retry
    async def arun_request_legal_division_pyeong_price_weekly_list_v1(
        self,
        parameter: NaverLegalDivisionPyeongPriceWeeklyListV1RequestParameterModel
    ) -> NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel:
        """Async variant of `run_request_legal_division_pyeong_price_weekly_list_v1`."""
        return await self._aget(
            self.legal_division_pyeong_price_weekly_list_v1_endpoint, parameter, NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel
        )

    @naver_retry
    def run_request_legal_division_real_trade_count_weekly_list_v1(
        self,
        parameter: NaverLegalDivisionRealTradeCountWeeklyListV1RequestParameterModel
    ) -> NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel:
        """Fetch a district's weekly actual-transaction counts via `GET /front-api/v1/legalDivision/realTradeCountWeeklyList`.

        Args:
            parameter: 법정동 코드·거래 유형(매매·전세)·기간·평형대.

        Returns:
            NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel: 기간 평균·최근 주 거래 건수와 주별 값.
        """
        return self._get(
            self.legal_division_real_trade_count_weekly_list_v1_endpoint, parameter, NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel
        )

    @naver_retry
    async def arun_request_legal_division_real_trade_count_weekly_list_v1(
        self,
        parameter: NaverLegalDivisionRealTradeCountWeeklyListV1RequestParameterModel
    ) -> NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel:
        """Async variant of `run_request_legal_division_real_trade_count_weekly_list_v1`."""
        return await self._aget(
            self.legal_division_real_trade_count_weekly_list_v1_endpoint, parameter, NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_redevelopment_area_list_v1(
        self,
        payload: NaverComplexRedevelopmentAreaListV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaListV1ResponseModel:
        """List redevelopment areas in a viewport via `POST /front-api/v1/complex/redevelopmentArea/list`.

        조회 전용이라 POST 지만 재시도한다.

        Args:
            payload: 필터·사각형·줌(13 이상)·정렬·커서.

        Returns:
            NaverComplexRedevelopmentAreaListV1ResponseModel: 구역 페이지 (이름·세대수·사업 단계·매물 수·호가)와 다음 커서.
        """
        return self._post(
            self.complex_redevelopment_area_list_v1_endpoint, payload, NaverComplexRedevelopmentAreaListV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_redevelopment_area_list_v1(
        self,
        payload: NaverComplexRedevelopmentAreaListV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaListV1ResponseModel:
        """Async variant of `run_request_complex_redevelopment_area_list_v1`."""
        return await self._apost(
            self.complex_redevelopment_area_list_v1_endpoint, payload, NaverComplexRedevelopmentAreaListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_redevelopment_area_legal_division_list_v1(
        self,
        payload: NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel:
        """List redevelopment areas in a 법정동 via `POST /front-api/v1/complex/redevelopmentArea/legalDivisionList`.

        조회 전용이라 POST 지만 재시도한다.

        Args:
            payload: 필터(법정동 코드)·정렬·커서.

        Returns:
            NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel: 구역 페이지와 다음 커서.
        """
        return self._post(
            self.complex_redevelopment_area_legal_division_list_v1_endpoint, payload, NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_redevelopment_area_legal_division_list_v1(
        self,
        payload: NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel:
        """Async variant of `run_request_complex_redevelopment_area_legal_division_list_v1`."""
        return await self._apost(
            self.complex_redevelopment_area_legal_division_list_v1_endpoint, payload, NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_redevelopment_area_markers_v1(
        self,
        payload: NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaMarkersV1ResponseModel:
        """Fetch redevelopment area map pins via `POST /front-api/v1/complex/redevelopmentArea/markers`.

        조회 전용이라 POST 지만 재시도한다.

        Args:
            payload: 필터·사각형·줌 (목록과 같은 값).

        Returns:
            NaverComplexRedevelopmentAreaMarkersV1ResponseModel: 구역 번호·대표 좌표·법정동.
        """
        return self._post(
            self.complex_redevelopment_area_markers_v1_endpoint, payload, NaverComplexRedevelopmentAreaMarkersV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_redevelopment_area_markers_v1(
        self,
        payload: NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaMarkersV1ResponseModel:
        """Async variant of `run_request_complex_redevelopment_area_markers_v1`."""
        return await self._apost(
            self.complex_redevelopment_area_markers_v1_endpoint, payload, NaverComplexRedevelopmentAreaMarkersV1ResponseModel
        )

    @naver_retry
    def run_request_complex_redevelopment_area_article_list_v1(
        self,
        payload: NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaArticleListV1ResponseModel:
        """List a redevelopment area's listings via `POST /front-api/v1/complex/redevelopmentArea/articleList`.

        조회 전용이라 POST 지만 재시도한다.

        Args:
            payload: 구역 번호·거래 유형·가격(원)·정렬·커서.

        Returns:
            NaverComplexRedevelopmentAreaArticleListV1ResponseModel: 매물 페이지와 다음 커서.
        """
        return self._post(
            self.complex_redevelopment_area_article_list_v1_endpoint, payload, NaverComplexRedevelopmentAreaArticleListV1ResponseModel
        )

    @naver_retry
    async def arun_request_complex_redevelopment_area_article_list_v1(
        self,
        payload: NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel
    ) -> NaverComplexRedevelopmentAreaArticleListV1ResponseModel:
        """Async variant of `run_request_complex_redevelopment_area_article_list_v1`."""
        return await self._apost(
            self.complex_redevelopment_area_article_list_v1_endpoint, payload, NaverComplexRedevelopmentAreaArticleListV1ResponseModel
        )

    @naver_retry
    def run_request_complex_reconstruction_v1(
        self,
        parameter: NaverComplexReconstructionV1RequestParameterModel
    ) -> NaverComplexReconstructionV1ResponseModel:
        """Fetch a 재건축 complex's business steps via `GET /front-api/v1/complex/reconstruction`.

        Args:
            parameter: `complex_number` (재건축 A04 단지).

        Returns:
            NaverComplexReconstructionV1ResponseModel: 시공사·현재 단계·단계별 날짜·계획 세대수·계획 용적률.
        """
        return self._get(self.complex_reconstruction_v1_endpoint, parameter, NaverComplexReconstructionV1ResponseModel)

    @naver_retry
    async def arun_request_complex_reconstruction_v1(
        self,
        parameter: NaverComplexReconstructionV1RequestParameterModel
    ) -> NaverComplexReconstructionV1ResponseModel:
        """Async variant of `run_request_complex_reconstruction_v1`."""
        return await self._aget(self.complex_reconstruction_v1_endpoint, parameter, NaverComplexReconstructionV1ResponseModel)

    @naver_retry
    def run_request_complex_redevelopment_v1(
        self,
        parameter: NaverComplexRedevelopmentV1RequestParameterModel
    ) -> NaverComplexRedevelopmentV1ResponseModel:
        """Fetch a redevelopment area's basic info via `GET /front-api/v1/complex/redevelopment`.

        Args:
            parameter: `redevelopment_area_number`.

        Returns:
            NaverComplexRedevelopmentV1ResponseModel: 구역 이름·대표 법정동·계획 세대수·시공사·용적률·건폐율·사업 단계.
        """
        return self._get(self.complex_redevelopment_v1_endpoint, parameter, NaverComplexRedevelopmentV1ResponseModel)

    @naver_retry
    async def arun_request_complex_redevelopment_v1(
        self,
        parameter: NaverComplexRedevelopmentV1RequestParameterModel
    ) -> NaverComplexRedevelopmentV1ResponseModel:
        """Async variant of `run_request_complex_redevelopment_v1`."""
        return await self._aget(self.complex_redevelopment_v1_endpoint, parameter, NaverComplexRedevelopmentV1ResponseModel)

    @naver_retry
    def run_request_complex_redevelopment_area_article_stats_v1(
        self,
        parameter: NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel
    ) -> NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel:
        """Count a redevelopment area's listings via `GET /front-api/v1/complex/redevelopmentArea/articleStats`.

        Args:
            parameter: 구역 번호·거래 유형·가격(원).

        Returns:
            NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel: 거래 유형별 매물 수와 호가 범위 (원).
        """
        return self._get(self.complex_redevelopment_area_article_stats_v1_endpoint, parameter, NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel)

    @naver_retry
    async def arun_request_complex_redevelopment_area_article_stats_v1(
        self,
        parameter: NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel
    ) -> NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel:
        """Async variant of `run_request_complex_redevelopment_area_article_stats_v1`."""
        return await self._aget(self.complex_redevelopment_area_article_stats_v1_endpoint, parameter, NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel)

    @naver_retry
    def run_request_complex_pyeong_real_price_list_v1(
        self,
        parameter: NaverComplexPyeongRealPriceListV1RequestParameterModel
    ) -> NaverComplexPyeongRealPriceListV1ResponseModel:
        """List a pyeong's transactions in a period via `GET /front-api/v1/complex/pyeong/realPrice/list`.

        Args:
            parameter: 단지·평형 번호, 거래 유형, 시작·끝일.

        Returns:
            NaverComplexPyeongRealPriceListV1ResponseModel: 기간 안 실거래 전부 (최근 순, 페이지 없음). 빌라 단지는 빈 목록.
        """
        return self._get(self.complex_pyeong_real_price_list_v1_endpoint, parameter, NaverComplexPyeongRealPriceListV1ResponseModel)

    @naver_retry
    async def arun_request_complex_pyeong_real_price_list_v1(
        self,
        parameter: NaverComplexPyeongRealPriceListV1RequestParameterModel
    ) -> NaverComplexPyeongRealPriceListV1ResponseModel:
        """Async variant of `run_request_complex_pyeong_real_price_list_v1`."""
        return await self._aget(self.complex_pyeong_real_price_list_v1_endpoint, parameter, NaverComplexPyeongRealPriceListV1ResponseModel)

    @naver_retry
    def run_request_complex_market_price_list_v1(
        self,
        parameter: NaverComplexMarketPriceListV1RequestParameterModel
    ) -> NaverComplexMarketPriceListV1ResponseModel:
        """Fetch weekly market prices in a period via `GET /front-api/v1/complex/marketPrice/list`.

        Args:
            parameter: 단지·평형 번호, 시작·끝일, 시세 제공처.

        Returns:
            NaverComplexMarketPriceListV1ResponseModel: 제공처별 기준일마다 매매·전세 시세 평균·범위와 전세가율 (원).
        """
        return self._get(self.complex_market_price_list_v1_endpoint, parameter, NaverComplexMarketPriceListV1ResponseModel)

    @naver_retry
    async def arun_request_complex_market_price_list_v1(
        self,
        parameter: NaverComplexMarketPriceListV1RequestParameterModel
    ) -> NaverComplexMarketPriceListV1ResponseModel:
        """Async variant of `run_request_complex_market_price_list_v1`."""
        return await self._aget(self.complex_market_price_list_v1_endpoint, parameter, NaverComplexMarketPriceListV1ResponseModel)

    @naver_retry
    def run_request_legal_division_info_list_by_level_v1(
        self,
        parameter: NaverLegalDivisionInfoListByLevelV1RequestParameterModel
    ) -> NaverLegalDivisionInfoListByLevelV1ResponseModel:
        """List every region of a level via `GET /front-api/v1/legalDivision/infoListByLevel`.

        Args:
            parameter: `region_level_type` (SI).

        Returns:
            NaverLegalDivisionInfoListByLevelV1ResponseModel: 시·도 이름·정식 이름·법정동 코드·중심 좌표.
        """
        return self._get(self.legal_division_info_list_by_level_v1_endpoint, parameter, NaverLegalDivisionInfoListByLevelV1ResponseModel)

    @naver_retry
    async def arun_request_legal_division_info_list_by_level_v1(
        self,
        parameter: NaverLegalDivisionInfoListByLevelV1RequestParameterModel
    ) -> NaverLegalDivisionInfoListByLevelV1ResponseModel:
        """Async variant of `run_request_legal_division_info_list_by_level_v1`."""
        return await self._aget(self.legal_division_info_list_by_level_v1_endpoint, parameter, NaverLegalDivisionInfoListByLevelV1ResponseModel)

    @naver_retry
    def run_request_legal_division_sub_info_list_v1(
        self,
        parameter: NaverLegalDivisionSubInfoListV1RequestParameterModel
    ) -> NaverLegalDivisionSubInfoListV1ResponseModel:
        """List a region's child regions via `GET /front-api/v1/legalDivision/subInfoList`.

        Args:
            parameter: 단위 (SI 시·도, GUN 시·군·구)와 법정동 코드.

        Returns:
            NaverLegalDivisionSubInfoListV1ResponseModel: 바로 아래 지역의 이름·단위·법정동 코드·중심 좌표.
        """
        return self._get(self.legal_division_sub_info_list_v1_endpoint, parameter, NaverLegalDivisionSubInfoListV1ResponseModel)

    @naver_retry
    async def arun_request_legal_division_sub_info_list_v1(
        self,
        parameter: NaverLegalDivisionSubInfoListV1RequestParameterModel
    ) -> NaverLegalDivisionSubInfoListV1ResponseModel:
        """Async variant of `run_request_legal_division_sub_info_list_v1`."""
        return await self._aget(self.legal_division_sub_info_list_v1_endpoint, parameter, NaverLegalDivisionSubInfoListV1ResponseModel)

    @naver_retry
    def run_request_education_school_v1(
        self,
        parameter: NaverEducationSchoolV1RequestParameterModel
    ) -> NaverEducationSchoolV1ResponseModel:
        """Fetch a school's details via `GET /front-api/v1/education/school`.

        Args:
            parameter: `school_code`.

        Returns:
            NaverEducationSchoolV1ResponseModel: 주소·운영 구분·설립 형태·개교일·학생 수·학급당/교원당 학생 수와 시·구 평균.
        """
        return self._get(self.education_school_v1_endpoint, parameter, NaverEducationSchoolV1ResponseModel)

    @naver_retry
    async def arun_request_education_school_v1(
        self,
        parameter: NaverEducationSchoolV1RequestParameterModel
    ) -> NaverEducationSchoolV1ResponseModel:
        """Async variant of `run_request_education_school_v1`."""
        return await self._aget(self.education_school_v1_endpoint, parameter, NaverEducationSchoolV1ResponseModel)

    @naver_retry
    def run_request_education_complex_school_allocation_dongs_v1(
        self,
        parameter: NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel
    ) -> NaverEducationComplexSchoolAllocationDongsV1ResponseModel:
        """Fetch which buildings of a complex are assigned to a school via `GET /front-api/v1/education/complex/school/allocation-dongs`.

        Args:
            parameter: 단지 번호·학교 코드·단지 종류 (complex, 단지형 빌라는 villa).

        Returns:
            NaverEducationComplexSchoolAllocationDongsV1ResponseModel: 전체 동 배정 여부와 배정되는 동 이름 묶음.
        """
        return self._get(self.education_complex_school_allocation_dongs_v1_endpoint, parameter, NaverEducationComplexSchoolAllocationDongsV1ResponseModel)

    @naver_retry
    async def arun_request_education_complex_school_allocation_dongs_v1(
        self,
        parameter: NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel
    ) -> NaverEducationComplexSchoolAllocationDongsV1ResponseModel:
        """Async variant of `run_request_education_complex_school_allocation_dongs_v1`."""
        return await self._aget(self.education_complex_school_allocation_dongs_v1_endpoint, parameter, NaverEducationComplexSchoolAllocationDongsV1ResponseModel)
