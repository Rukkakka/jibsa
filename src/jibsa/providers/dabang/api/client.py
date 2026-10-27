from functools import cached_property

from httpx import (
    AsyncClient,
    Client,
    HTTPStatusError,
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
from jibsa.providers.dabang.api.request.common import (
    DabangComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.complex import (
    DabangComplexListCategoryV5RequestParameterModel,
    DabangComplexSummaryV5RequestParameterModel,
    DabangRoomListCategoryComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.listing import (
    DabangNewRoomDetailV3RequestParameterModel,
    DabangRoomGetRoomIdV3RequestParameterModel,
    DabangRoomListCategoryV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.nearby import (
    DabangMarkersCategoryV5RequestParameterModel,
    DabangNearV5RequestParameterModel,
    DabangTransitNearV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.neighborhood import (
    DabangRegionInfoRegionalCountV5RequestParameterModel,
    DabangRegionInfoRegionalSummaryV5RequestParameterModel,
    DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.ranking import (
    DabangRealPriceTradeRankingsComplexV5RequestParameterModel,
    DabangRealTimeWatchRankingsV5RequestParameterModel,
    DabangRegionInfoRankingV5RequestParameterModel,
    DabangRegionInfoRealEstateRankingV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.real_price import (
    DabangRealPriceComplexChartsV5RequestParameterModel,
    DabangRealPriceComplexHistoriesV5RequestParameterModel,
    DabangRealPriceHouseHistoryV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.region import (
    DabangGeojsonRegionRequestParameterModel,
    DabangLocSearchV5RequestParameterModel,
    DabangRegionStatesV5RequestParameterModel,
    DabangRegionV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.sale import (
    DabangSaleInLotsDetail2V3RequestParameterModel,
    DabangSaleInLotsListScheduleV3RequestParameterModel,
    DabangSaleListCategoryBboxV5RequestParameterModel,
)
from jibsa.providers.dabang.api.request.school import (
    DabangEducationV3RequestParameterModel,
)
from jibsa.providers.dabang.api.response.common import DabangComplexV5ResponseModel
from jibsa.providers.dabang.api.response.complex import (
    DabangComplexListCategoryV5ResponseModel,
    DabangComplexSummaryV5ResponseModel,
    DabangRoomListCategoryComplexV5ResponseModel,
)
from jibsa.providers.dabang.api.response.listing import (
    DabangNewRoomDetailV3ResponseModel,
    DabangRoomGetRoomIdV3ResponseModel,
    DabangRoomListCategoryV5ResponseModel,
)
from jibsa.providers.dabang.api.response.nearby import (
    DabangMarkersCategoryV5ResponseModel,
    DabangNearV5ResponseModel,
    DabangTransitNearV5ResponseModel,
)
from jibsa.providers.dabang.api.response.neighborhood import (
    DabangRegionInfoRegionalCountV5ResponseModel,
    DabangRegionInfoRegionalSummaryV5ResponseModel,
    DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel,
)
from jibsa.providers.dabang.api.response.ranking import (
    DabangRealPriceTradeRankingsComplexV5ResponseModel,
    DabangRealTimeWatchRankingsV5ResponseModel,
    DabangRegionInfoRankingV5ResponseModel,
    DabangRegionInfoRealEstateRankingV5ResponseModel,
)
from jibsa.providers.dabang.api.response.real_price import (
    DabangRealPriceComplexChartsV5ResponseModel,
    DabangRealPriceComplexHistoriesV5ResponseModel,
    DabangRealPriceHouseHistoryV5ResponseModel,
)
from jibsa.providers.dabang.api.response.region import (
    DabangGeojsonRegionResponseModel,
    DabangLocSearchV5ResponseModel,
    DabangRegionStatesV5ResponseModel,
    DabangRegionV5ResponseModel,
)
from jibsa.providers.dabang.api.response.sale import (
    DabangSaleInLotsDetail2V3ResponseModel,
    DabangSaleInLotsListScheduleV3ResponseModel,
    DabangSaleListCategoryBboxV5ResponseModel,
)
from jibsa.providers.dabang.api.response.school import DabangEducationV3ResponseModel

from typing import ClassVar


dabang_retry = retry(
    retry=retry_if_exception(should_retry_idempotent),
    stop=stop_after_attempt(3),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""조회 전용 엔드포인트 공통 재시도: 최대 3회, 1초(또는 `Retry-After`) 간격, 5xx·429·timeout·transport 오류만."""


def should_retry_education(exc: BaseException) -> bool:
    """학교 상세 재시도 술어. 500 만 빼고 `should_retry_idempotent` 와 같다.

    학교 상세는 단계와 코드가 맞지 않거나 없는 코드면 늘 500 이다 (2026-10-25 실측: 휘문중 S010000736 을 고등학교로, 없는
    코드 S999999999 를 중학교로). 다시 보내도 같은 응답이라 요청 제한 몫과 대기만 쓴다.
    """
    if isinstance(exc, HTTPStatusError) and exc.response.status_code == 500:
        return False
    return should_retry_idempotent(exc)


dabang_education_retry = retry(
    retry=retry_if_exception(should_retry_education),
    stop=stop_after_attempt(3),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""학교 상세 전용 재시도: `dabang_retry` 와 같고 500 은 다시 보내지 않는다 (`should_retry_education`)."""

# 새 방식(`/api/v5/`) 요청에 웹이 붙이는 헤더 (fetch 청크 `requestHeaders`, 2026-10-25). 옛 방식(`/api/3/`)은 헤더 대신
# 쿼리에 버전을 붙인다 (`DabangV3RequestParameterModel`)
V5_HEADERS: dict[str, str] = {
    'D-Api-Version': '5.0.0',
    'D-App-Version': '1',
    'D-Call-Type': 'web',
}


class DabangClient(BaseHTTPClient):
    """다방 (www.dabangapp.com) 비공식 웹 API 클라이언트.

    로그인·토큰 없이 장소 검색, 매물 지도 목록(원룸·투룸, 주택·빌라, 오피스텔, 아파트), 매물 상세, 단지 목록·상세·요약,
    단지 매물, 실거래, 시세 흐름, 동네정보(요약·시설 수·인기 매물), 주변 교통·시설, 지도 집계(역 둘레 평균 매물가)와 동 경계
    파일, 분양(목록·상세·청약 일정), 학교 상세(학교알리미 공시), 전국 조회·거래 순위, 범위 안 동·단지 순위(부동산·학교·인구·시설)를 조회한다. 금액은 **만원** 이지만 상세 관리비(`maintenance_cost`)와 단지
    평형 관리비(`maintenanceTotalPrice`)는 원이다. 목록 가격은 숫자 없이 글자('1000/63', '3억9000')로만 온다.

    API 가 두 방식이다. 새 방식 `/api/v5/` 는 `D-Api-Version` 등 헤더(`V5_HEADERS`)를 붙이고 응답 봉투
    `{code, msg, result}` 에 camelCase 로 온다. 옛 방식 `/api/3/`(상세·매물번호)은 쿼리에 `api_version=3.0.1` 등을 붙이고
    봉투 없이 snake_case 로 온다. 없는 주소는 404 대신 **403 빈 응답** 이다 (아무 주소나 넣어도 같다, 2026-10-25 실측).
    그래서 403 은 요청 제한이 아니라 주소·경로 값이 틀린 것으로 본다.

    엔드포인트 action id 는 `/api` 를 버리고 경로 파라미터를 뺀 세그먼트를 `_` 로 이은 뒤 버전(`v5`, `3`)을 끝으로 옮긴다
    (`/api/v5/loc/search` → `loc_search_v5`, `/api/3/new-room/detail` → `new_room_detail_v3`,
    `/api/v5/room-list/category/{category}/{search_type}` → `room_list_category_v5`,
    `/api/v5/room-list/category/{category}/complex` → `room_list_category_complex_v5`, `/api/v5/{target}/{target_id}/near` →
    `near_v5`, `/api/3/education/{level}/{school_code}` → `education_v3`, `/api/v5/region-info/{topic}/ranking/{metric}` →
    `region_info_ranking_v5`). 동 경계는 지도 집계가 주는 CDN
    (`geojson_host`) 파일이라 버전이 없다 (`geojson_region`).

    Args:
        host: 웹·API 호스트 (스킴 제외). Defaults to 'www.dabangapp.com'.
        geojson_host: 동 경계 파일 CDN 호스트. Defaults to 'd2pi55cyzoqmrc.cloudfront.net'.
        rate_limit: 요청 제한 정책. Defaults to 0.5초 간격·분당 60회·429 후 5분 쿨다운.

    Attributes:
        base_url: `url_schema` 와 `host` 로 만든 베이스 URL.
        geojson_base_url: 동 경계 파일 베이스 URL.

    Example:
        >>> with DabangClient() as client:
        ...     client.run_request_loc_search_v5(DabangLocSearchV5RequestParameterModel(search_keyword='역삼동'))
    """

    loc_search_v5_endpoint: ClassVar[str] = '/api/v5/loc/search'
    room_list_category_v5_endpoint: ClassVar[str] = '/api/v5/room-list/category/{category}/{search_type}'
    room_list_category_complex_v5_endpoint: ClassVar[str] = '/api/v5/room-list/category/{category}/complex'
    complex_list_category_v5_endpoint: ClassVar[str] = '/api/v5/complex-list/category/{category}/{search_type}'
    complex_v5_endpoint: ClassVar[str] = '/api/v5/complex/{complex_id}'
    complex_summary_v5_endpoint: ClassVar[str] = '/api/v5/complex/{complex_type}/summary'
    real_price_complex_histories_v5_endpoint: ClassVar[str] = '/api/v5/real-price/complex/histories'
    real_price_house_history_v5_endpoint: ClassVar[str] = '/api/v5/real-price/house/history'
    real_price_complex_charts_v5_endpoint: ClassVar[str] = '/api/v5/real-price/complex/charts'
    new_room_detail_v3_endpoint: ClassVar[str] = '/api/3/new-room/detail'
    room_get_room_id_v3_endpoint: ClassVar[str] = '/api/3/room/get-room-id'
    education_v3_endpoint: ClassVar[str] = '/api/3/education/{level}/{school_code}'
    geojson_region_endpoint: ClassVar[str] = '/geojson/region/{code}'
    region_info_regional_summary_v5_endpoint: ClassVar[str] = '/api/v5/region-info/{topic}/regional/summary'
    region_info_regional_count_v5_endpoint: ClassVar[str] = '/api/v5/region-info/{topic}/regional/count'
    region_info_room_regional_popular_room_v5_endpoint: ClassVar[str] = '/api/v5/region-info/room/regional/popular-room'
    transit_near_v5_endpoint: ClassVar[str] = '/api/v5/transit/near/{target}'
    near_v5_endpoint: ClassVar[str] = '/api/v5/{target}/{target_id}/near'
    markers_category_v5_endpoint: ClassVar[str] = '/api/v5/markers/category/{category}'
    region_v5_endpoint: ClassVar[str] = '/api/v5/region'
    region_states_v5_endpoint: ClassVar[str] = '/api/v5/region/states'
    sale_list_category_bbox_v5_endpoint: ClassVar[str] = '/api/v5/sale-list/category/bbox'
    real_time_watch_rankings_v5_endpoint: ClassVar[str] = '/api/v5/real-time-watch-rankings/{unit}'
    real_price_trade_rankings_complex_v5_endpoint: ClassVar[str] = '/api/v5/real-price/trade/rankings/complex'
    region_info_real_estate_ranking_v5_endpoint: ClassVar[str] = '/api/v5/region-info/real-estate/ranking/{unit}/{metric}'
    region_info_ranking_v5_endpoint: ClassVar[str] = '/api/v5/region-info/{topic}/ranking/{metric}'
    sale_in_lots_detail2_v3_endpoint: ClassVar[str] = '/api/3/sale-in-lots/detail2'
    sale_in_lots_list_schedule_v3_endpoint: ClassVar[str] = '/api/3/sale-in-lots/list/schedule'

    source_name: ClassVar[str] = 'dabang'
    default_rate_limit: ClassVar[dict[str, object]] = {
        'min_interval': 0.5,
        'max_per_minute': 60,
        'cooldown': 300,
    }

    host: str = 'www.dabangapp.com'

    geojson_host: str = 'd2pi55cyzoqmrc.cloudfront.net'

    @property
    def base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.host
        )

    @property
    def geojson_base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.geojson_host
        )

    @property
    def base_header(self) -> dict[str, str]:
        return {
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': self.user_agent,
            'Referer': 'https://www.dabangapp.com/',
            # 웹의 axios 인스턴스가 모든 요청에 붙이는 헤더 (fetch 청크, 2026-10-25)
            'csrf': 'token',
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

    @dabang_retry
    def run_request_loc_search_v5(
        self,
        parameter: DabangLocSearchV5RequestParameterModel
    ) -> DabangLocSearchV5ResponseModel:
        """Search dongs, stations, universities and complexes via `GET /api/v5/loc/search`.

        Retries up to 3 attempts on HTTP 5xx/429 responses and httpx
        timeout/transport errors, waiting 1s between attempts or, on a 429,
        the server's `Retry-After` (capped at 60s); any other error, and the
        final failed attempt, is raised. 요청 제한이 켜져 있으면(기본) 429 는
        재시도 없이 곧바로 `RateLimitedError` (쿨다운) 로 끝난다.

        Args:
            parameter: 검색어와 찾을 종류.

        Returns:
            DabangLocSearchV5ResponseModel: 동(법정동 코드 8자리·동 번호)·역(번호·반경)·대학·단지 후보.
        """
        response = self._client.get(
            url=self.loc_search_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangLocSearchV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_loc_search_v5(
        self,
        parameter: DabangLocSearchV5RequestParameterModel
    ) -> DabangLocSearchV5ResponseModel:
        """Async variant of `run_request_loc_search_v5` (`GET /api/v5/loc/search`)."""
        response = await self._async_client.get(
            url=self.loc_search_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangLocSearchV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_geojson_region(
        self,
        parameter: DabangGeojsonRegionRequestParameterModel
    ) -> DabangGeojsonRegionResponseModel:
        """Fetch a dong boundary via `GET /geojson/region/{code}` on `geojson_host`.

        Same retry behaviour as `run_request_loc_search_v5`. 다방 지도 집계(`markers`)가 동마다 주는 경계 파일 주소다.
        다방 API 와 같은 요청 제한을 거친다.

        Args:
            parameter: 법정동 코드 앞 8자리.

        Returns:
            DabangGeojsonRegionResponseModel: 동 경계 (MultiPolygon).
        """
        response = self._client.get(
            url=self.geojson_base_url + self.geojson_region_endpoint.format(code=parameter.code)
        )
        raise_for_status(response=response)
        return DabangGeojsonRegionResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_geojson_region(
        self,
        parameter: DabangGeojsonRegionRequestParameterModel
    ) -> DabangGeojsonRegionResponseModel:
        """Async variant of `run_request_geojson_region` (`GET /geojson/region/{code}`)."""
        response = await self._async_client.get(
            url=self.geojson_base_url + self.geojson_region_endpoint.format(code=parameter.code)
        )
        raise_for_status(response=response)
        return DabangGeojsonRegionResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_room_list_category_v5(
        self,
        parameter: DabangRoomListCategoryV5RequestParameterModel
    ) -> DabangRoomListCategoryV5ResponseModel:
        """List one page (24) of listings via `GET /api/v5/room-list/category/{category}/{search_type}`.

        Same retry behaviour as `run_request_loc_search_v5`. 유형(`one-two`·`house-villa`·`officetel`·`apt`)마다 필터 항목이
        다르고, 아파트는 동·대학 검색이 없다 (요청 모델이 막는다).

        Args:
            parameter: 유형·찾는 방식·필터·쪽.

        Returns:
            DabangRoomListCategoryV5ResponseModel: 매물과 광고, 조건에 맞는 매물 수.
        """
        response = self._client.get(
            url=self.room_list_category_v5_endpoint.format(category=parameter.category, search_type=parameter.search_type),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRoomListCategoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_room_list_category_v5(
        self,
        parameter: DabangRoomListCategoryV5RequestParameterModel
    ) -> DabangRoomListCategoryV5ResponseModel:
        """Async variant of `run_request_room_list_category_v5`."""
        response = await self._async_client.get(
            url=self.room_list_category_v5_endpoint.format(category=parameter.category, search_type=parameter.search_type),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRoomListCategoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_room_list_category_complex_v5(
        self,
        parameter: DabangRoomListCategoryComplexV5RequestParameterModel
    ) -> DabangRoomListCategoryComplexV5ResponseModel:
        """List one page (24) of a complex's listings via `GET /api/v5/room-list/category/{category}/complex`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 단지 ID·유형 필터·거래 유형과 평형·쪽.

        Returns:
            DabangRoomListCategoryComplexV5ResponseModel: 단지 매물과 광고.
        """
        response = self._client.get(
            url=self.room_list_category_complex_v5_endpoint.format(category=parameter.category),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRoomListCategoryComplexV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_room_list_category_complex_v5(
        self,
        parameter: DabangRoomListCategoryComplexV5RequestParameterModel
    ) -> DabangRoomListCategoryComplexV5ResponseModel:
        """Async variant of `run_request_room_list_category_complex_v5`."""
        response = await self._async_client.get(
            url=self.room_list_category_complex_v5_endpoint.format(category=parameter.category),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRoomListCategoryComplexV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_complex_list_category_v5(
        self,
        parameter: DabangComplexListCategoryV5RequestParameterModel
    ) -> DabangComplexListCategoryV5ResponseModel:
        """List one page (24) of complexes via `GET /api/v5/complex-list/category/{category}/{search_type}`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 아파트·오피스텔, 찾는 방식, 필터, 쪽.

        Returns:
            DabangComplexListCategoryV5ResponseModel: 단지마다 거래 유형별 매물 수와 최근 실거래 글.
        """
        response = self._client.get(
            url=self.complex_list_category_v5_endpoint.format(category=parameter.category, search_type=parameter.search_type),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangComplexListCategoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_complex_list_category_v5(
        self,
        parameter: DabangComplexListCategoryV5RequestParameterModel
    ) -> DabangComplexListCategoryV5ResponseModel:
        """Async variant of `run_request_complex_list_category_v5`."""
        response = await self._async_client.get(
            url=self.complex_list_category_v5_endpoint.format(category=parameter.category, search_type=parameter.search_type),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangComplexListCategoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_complex_v5(
        self,
        parameter: DabangComplexV5RequestParameterModel
    ) -> DabangComplexV5ResponseModel:
        """Fetch a complex via `GET /api/v5/complex/{complex_id}`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 단지 ID.

        Returns:
            DabangComplexV5ResponseModel: 단지 정보·평형·평당가 비교·근처 학교·매물 수.
        """
        response = self._client.get(
            url=self.complex_v5_endpoint.format(complex_id=parameter.complex_id),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangComplexV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_complex_v5(
        self,
        parameter: DabangComplexV5RequestParameterModel
    ) -> DabangComplexV5ResponseModel:
        """Async variant of `run_request_complex_v5` (`GET /api/v5/complex/{complex_id}`)."""
        response = await self._async_client.get(
            url=self.complex_v5_endpoint.format(complex_id=parameter.complex_id),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangComplexV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_complex_summary_v5(
        self,
        parameter: DabangComplexSummaryV5RequestParameterModel
    ) -> DabangComplexSummaryV5ResponseModel:
        """Fetch a complex summary via `GET /api/v5/complex/{complex_type}/summary`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 단지 유형(경로)과 단지 ID.

        Returns:
            DabangComplexSummaryV5ResponseModel: 최근 매매·전세 실거래 한 건씩.
        """
        response = self._client.get(
            url=self.complex_summary_v5_endpoint.format(complex_type=parameter.complex_type),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangComplexSummaryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_complex_summary_v5(
        self,
        parameter: DabangComplexSummaryV5RequestParameterModel
    ) -> DabangComplexSummaryV5ResponseModel:
        """Async variant of `run_request_complex_summary_v5`."""
        response = await self._async_client.get(
            url=self.complex_summary_v5_endpoint.format(complex_type=parameter.complex_type),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangComplexSummaryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_real_price_complex_histories_v5(
        self,
        parameter: DabangRealPriceComplexHistoriesV5RequestParameterModel
    ) -> DabangRealPriceComplexHistoriesV5ResponseModel:
        """List a complex pyeong's real transactions via `GET /api/v5/real-price/complex/histories`.

        Same retry behaviour as `run_request_loc_search_v5`. 기간은 최대 36달이다 (요청 모델이 막는다).

        Args:
            parameter: 단지 ID·평형·기간·매매/전월세·쪽.

        Returns:
            DabangRealPriceComplexHistoriesV5ResponseModel: 최근 계약 순 실거래.
        """
        response = self._client.get(
            url=self.real_price_complex_histories_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceComplexHistoriesV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_real_price_complex_histories_v5(
        self,
        parameter: DabangRealPriceComplexHistoriesV5RequestParameterModel
    ) -> DabangRealPriceComplexHistoriesV5ResponseModel:
        """Async variant of `run_request_real_price_complex_histories_v5`."""
        response = await self._async_client.get(
            url=self.real_price_complex_histories_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceComplexHistoriesV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_real_price_house_history_v5(
        self,
        parameter: DabangRealPriceHouseHistoryV5RequestParameterModel
    ) -> DabangRealPriceHouseHistoryV5ResponseModel:
        """List real transactions around a non-complex listing via `GET /api/v5/real-price/house/history`.

        Same retry behaviour as `run_request_loc_search_v5`. 그 건물이 아니라 같은 동의 같은 건물 유형 거래다.

        Args:
            parameter: 매물 ID·기간·매매/전월세·쪽.

        Returns:
            DabangRealPriceHouseHistoryV5ResponseModel: 최근 계약 순 실거래와 모은 범위.
        """
        response = self._client.get(
            url=self.real_price_house_history_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceHouseHistoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_real_price_house_history_v5(
        self,
        parameter: DabangRealPriceHouseHistoryV5RequestParameterModel
    ) -> DabangRealPriceHouseHistoryV5ResponseModel:
        """Async variant of `run_request_real_price_house_history_v5`."""
        response = await self._async_client.get(
            url=self.real_price_house_history_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceHouseHistoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_real_price_complex_charts_v5(
        self,
        parameter: DabangRealPriceComplexChartsV5RequestParameterModel
    ) -> DabangRealPriceComplexChartsV5ResponseModel:
        """Fetch a pyeong's 36-month price trend via `GET /api/v5/real-price/complex/charts`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 단지 ID·평형.

        Returns:
            DabangRealPriceComplexChartsV5ResponseModel: 달마다 평균가·거래 수, 전세가율, 1년·3년 최고·최저.
        """
        response = self._client.get(
            url=self.real_price_complex_charts_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceComplexChartsV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_real_price_complex_charts_v5(
        self,
        parameter: DabangRealPriceComplexChartsV5RequestParameterModel
    ) -> DabangRealPriceComplexChartsV5ResponseModel:
        """Async variant of `run_request_real_price_complex_charts_v5`."""
        response = await self._async_client.get(
            url=self.real_price_complex_charts_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceComplexChartsV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_new_room_detail_v3(
        self,
        parameter: DabangNewRoomDetailV3RequestParameterModel
    ) -> DabangNewRoomDetailV3ResponseModel:
        """Fetch a listing via `GET /api/3/new-room/detail`.

        Same retry behaviour as `run_request_loc_search_v5`. 옛 방식이라 헤더 대신 쿼리에 버전을 붙인다. 없는 매물은
        400 `"존재하지 않는 매물입니다."` 다.

        Args:
            parameter: 매물 ID.

        Returns:
            DabangNewRoomDetailV3ResponseModel: 숫자 가격·관리비(원)·면적·층·옵션 등.
        """
        response = self._client.get(
            url=self.new_room_detail_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangNewRoomDetailV3ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_new_room_detail_v3(
        self,
        parameter: DabangNewRoomDetailV3RequestParameterModel
    ) -> DabangNewRoomDetailV3ResponseModel:
        """Async variant of `run_request_new_room_detail_v3` (`GET /api/3/new-room/detail`)."""
        response = await self._async_client.get(
            url=self.new_room_detail_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangNewRoomDetailV3ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_room_get_room_id_v3(
        self,
        parameter: DabangRoomGetRoomIdV3RequestParameterModel
    ) -> DabangRoomGetRoomIdV3ResponseModel:
        """Turn a listing number into a listing ID via `GET /api/3/room/get-room-id`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 매물번호.

        Returns:
            DabangRoomGetRoomIdV3ResponseModel: 매물 ID.
        """
        response = self._client.get(
            url=self.room_get_room_id_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangRoomGetRoomIdV3ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_room_get_room_id_v3(
        self,
        parameter: DabangRoomGetRoomIdV3RequestParameterModel
    ) -> DabangRoomGetRoomIdV3ResponseModel:
        """Async variant of `run_request_room_get_room_id_v3` (`GET /api/3/room/get-room-id`)."""
        response = await self._async_client.get(
            url=self.room_get_room_id_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangRoomGetRoomIdV3ResponseModel.model_validate(response.json())

    @dabang_education_retry
    def run_request_education_v3(
        self,
        parameter: DabangEducationV3RequestParameterModel
    ) -> DabangEducationV3ResponseModel:
        """Fetch a school's public disclosure via `GET /api/3/education/{level}/{school_code}`.

        Same retry behaviour as `run_request_loc_search_v5` except HTTP 500, which is raised at once. 옛 방식이라 쿼리에
        버전을 붙인다. 단계와 코드가 맞지 않거나 없는 코드면 늘 500 이라 다시 보내지 않는다 (`dabang_education_retry`).

        Args:
            parameter: 단계(초·중·고)와 학교 코드.

        Returns:
            DabangEducationV3ResponseModel: 학급당·교원당 학생 수(시·도·시·군·구 평균과 함께), 진학 수·비율.
        """
        response = self._client.get(
            url=self.education_v3_endpoint.format(level=parameter.level, school_code=parameter.school_code),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangEducationV3ResponseModel.model_validate(response.json())

    @dabang_education_retry
    async def arun_request_education_v3(
        self,
        parameter: DabangEducationV3RequestParameterModel
    ) -> DabangEducationV3ResponseModel:
        """Async variant of `run_request_education_v3` (`GET /api/3/education/{level}/{school_code}`)."""
        response = await self._async_client.get(
            url=self.education_v3_endpoint.format(level=parameter.level, school_code=parameter.school_code),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangEducationV3ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_info_regional_summary_v5(
        self,
        parameter: DabangRegionInfoRegionalSummaryV5RequestParameterModel
    ) -> DabangRegionInfoRegionalSummaryV5ResponseModel:
        """Fetch one neighbourhood-info summary via `GET /api/v5/region-info/{topic}/regional/summary`.

        Same retry behaviour as `run_request_loc_search_v5`. 탭(매물정보·시세정보·인구) 하나의 요약과 전국·시도·구 순위다.

        Args:
            parameter: 탭·동 번호·요약 항목.

        Returns:
            DabangRegionInfoRegionalSummaryV5ResponseModel: 매물 유형별 값 또는 인구, 순위, 기준 달.
        """
        response = self._client.get(
            url=self.region_info_regional_summary_v5_endpoint.format(topic=parameter.topic),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRegionalSummaryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_info_regional_summary_v5(
        self,
        parameter: DabangRegionInfoRegionalSummaryV5RequestParameterModel
    ) -> DabangRegionInfoRegionalSummaryV5ResponseModel:
        """Async variant of `run_request_region_info_regional_summary_v5`."""
        response = await self._async_client.get(
            url=self.region_info_regional_summary_v5_endpoint.format(topic=parameter.topic),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRegionalSummaryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_info_regional_count_v5(
        self,
        parameter: DabangRegionInfoRegionalCountV5RequestParameterModel
    ) -> DabangRegionInfoRegionalCountV5ResponseModel:
        """Fetch facility or school counts of a dong via `GET /api/v5/region-info/{topic}/regional/count`.

        Same retry behaviour as `run_request_loc_search_v5`. 탭(학군·편의시설·교통/차량·생활안전) 하나의 항목별 수를 한 번에 준다.

        Args:
            parameter: 탭·동 번호.

        Returns:
            DabangRegionInfoRegionalCountV5ResponseModel: 묶음별 시설·학교 수 (글자).
        """
        response = self._client.get(
            url=self.region_info_regional_count_v5_endpoint.format(topic=parameter.topic),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRegionalCountV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_info_regional_count_v5(
        self,
        parameter: DabangRegionInfoRegionalCountV5RequestParameterModel
    ) -> DabangRegionInfoRegionalCountV5ResponseModel:
        """Async variant of `run_request_region_info_regional_count_v5`."""
        response = await self._async_client.get(
            url=self.region_info_regional_count_v5_endpoint.format(topic=parameter.topic),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRegionalCountV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_info_room_regional_popular_room_v5(
        self,
        parameter: DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel
    ) -> DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel:
        """List popular listings in a dong via `GET /api/v5/region-info/room/regional/popular-room`.

        Same retry behaviour as `run_request_loc_search_v5`. 선호도(조회수·찜수·문의수를 합친 점수) 높은 순이다.

        Args:
            parameter: 동 번호·매물 유형·거래 유형·쪽.

        Returns:
            DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel: 인기 매물과 순위가 있는 매물 수.
        """
        response = self._client.get(
            url=self.region_info_room_regional_popular_room_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_info_room_regional_popular_room_v5(
        self,
        parameter: DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel
    ) -> DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel:
        """Async variant of `run_request_region_info_room_regional_popular_room_v5`."""
        response = await self._async_client.get(
            url=self.region_info_room_regional_popular_room_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_transit_near_v5(
        self,
        parameter: DabangTransitNearV5RequestParameterModel
    ) -> DabangTransitNearV5ResponseModel:
        """Fetch subway stations (1km) and bus routes (500m) around a listing or complex via `GET /api/v5/transit/near/{target}`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 대상(매물·단지)과 ID.

        Returns:
            DabangTransitNearV5ResponseModel: 가까운 순 역과 버스 노선.
        """
        response = self._client.get(
            url=self.transit_near_v5_endpoint.format(target=parameter.target),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangTransitNearV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_transit_near_v5(
        self,
        parameter: DabangTransitNearV5RequestParameterModel
    ) -> DabangTransitNearV5ResponseModel:
        """Async variant of `run_request_transit_near_v5`."""
        response = await self._async_client.get(
            url=self.transit_near_v5_endpoint.format(target=parameter.target),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangTransitNearV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_near_v5(
        self,
        parameter: DabangNearV5RequestParameterModel
    ) -> DabangNearV5ResponseModel:
        """Fetch the nearest facilities around a listing or complex via `GET /api/v5/{target}/{target_id}/near`.

        Same retry behaviour as `run_request_loc_search_v5`. 편의(편의점·카페·은행·공공기관·버스정류장)·안전(경찰·CCTV)·교육(어린이집~고등학교) 시설을 종류마다 가까운 순으로 준다.

        Args:
            parameter: 대상(매물·단지)과 ID.

        Returns:
            DabangNearV5ResponseModel: 종류별 가까운 시설과 거리.
        """
        response = self._client.get(
            url=self.near_v5_endpoint.format(target=parameter.target, target_id=parameter.target_id),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangNearV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_near_v5(
        self,
        parameter: DabangNearV5RequestParameterModel
    ) -> DabangNearV5ResponseModel:
        """Async variant of `run_request_near_v5`."""
        response = await self._async_client.get(
            url=self.near_v5_endpoint.format(target=parameter.target, target_id=parameter.target_id),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangNearV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_markers_category_v5(
        self,
        parameter: DabangMarkersCategoryV5RequestParameterModel
    ) -> DabangMarkersCategoryV5ResponseModel:
        """Fetch map markers via `GET /api/v5/markers/category/{category}`.

        Same retry behaviour as `run_request_loc_search_v5`. 원룸·투룸 집계의 역 표시에 역 둘레 평균 매물가(건물 유형 × 원룸·투룸)가 붙는다.

        Args:
            parameter: 유형·필터·지도 범위·확대 수준.

        Returns:
            DabangMarkersCategoryV5ResponseModel: 역 표시와 평균 매물가.
        """
        response = self._client.get(
            url=self.markers_category_v5_endpoint.format(category=parameter.category),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangMarkersCategoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_markers_category_v5(
        self,
        parameter: DabangMarkersCategoryV5RequestParameterModel
    ) -> DabangMarkersCategoryV5ResponseModel:
        """Async variant of `run_request_markers_category_v5`."""
        response = await self._async_client.get(
            url=self.markers_category_v5_endpoint.format(category=parameter.category),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangMarkersCategoryV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_v5(
        self,
        parameter: DabangRegionV5RequestParameterModel
    ) -> DabangRegionV5ResponseModel:
        """Fetch one region by legal-dong code prefix via `GET /api/v5/region`.

        Same retry behaviour as `run_request_loc_search_v5`. 시·도(2자리)·시·군·구(5자리)·동(8자리) 코드를 받는다.

        Args:
            parameter: 법정동 코드 앞자리.

        Returns:
            DabangRegionV5ResponseModel: 다방 지역 번호·이름·중심 좌표.
        """
        response = self._client.get(
            url=self.region_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_v5(
        self,
        parameter: DabangRegionV5RequestParameterModel
    ) -> DabangRegionV5ResponseModel:
        """Async variant of `run_request_region_v5`."""
        response = await self._async_client.get(
            url=self.region_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_states_v5(
        self,
        parameter: DabangRegionStatesV5RequestParameterModel
    ) -> DabangRegionStatesV5ResponseModel:
        """List provinces via `GET /api/v5/region/states`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 없음 (빈 모델).

        Returns:
            DabangRegionStatesV5ResponseModel: 시·도 목록.
        """
        response = self._client.get(
            url=self.region_states_v5_endpoint,
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionStatesV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_states_v5(
        self,
        parameter: DabangRegionStatesV5RequestParameterModel
    ) -> DabangRegionStatesV5ResponseModel:
        """Async variant of `run_request_region_states_v5`."""
        response = await self._async_client.get(
            url=self.region_states_v5_endpoint,
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionStatesV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_sale_list_category_bbox_v5(
        self,
        parameter: DabangSaleListCategoryBboxV5RequestParameterModel
    ) -> DabangSaleListCategoryBboxV5ResponseModel:
        """List sale-in-lots complexes in a map box via `GET /api/v5/sale-list/category/bbox`.

        Same retry behaviour as `run_request_loc_search_v5`. 24곳씩 준다. 항목에 좌표·동 번호가 없다.

        Args:
            parameter: 분양 필터·지도 범위·쪽.

        Returns:
            DabangSaleListCategoryBboxV5ResponseModel: 분양 단지와 범위 안 수.
        """
        response = self._client.get(
            url=self.sale_list_category_bbox_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangSaleListCategoryBboxV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_sale_list_category_bbox_v5(
        self,
        parameter: DabangSaleListCategoryBboxV5RequestParameterModel
    ) -> DabangSaleListCategoryBboxV5ResponseModel:
        """Async variant of `run_request_sale_list_category_bbox_v5`."""
        response = await self._async_client.get(
            url=self.sale_list_category_bbox_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangSaleListCategoryBboxV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_real_time_watch_rankings_v5(
        self,
        parameter: DabangRealTimeWatchRankingsV5RequestParameterModel
    ) -> DabangRealTimeWatchRankingsV5ResponseModel:
        """Rank complexes or dongs by recent views nationwide via `GET /api/v5/real-time-watch-rankings/{unit}`.

        Same retry behaviour as `run_request_loc_search_v5`. 늘 50곳이다.

        Args:
            parameter: 단지·동, 유형, 기간.

        Returns:
            DabangRealTimeWatchRankingsV5ResponseModel: 기준 기간과 순위.
        """
        response = self._client.get(
            url=self.real_time_watch_rankings_v5_endpoint.format(unit=parameter.unit),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealTimeWatchRankingsV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_real_time_watch_rankings_v5(
        self,
        parameter: DabangRealTimeWatchRankingsV5RequestParameterModel
    ) -> DabangRealTimeWatchRankingsV5ResponseModel:
        """Async variant of `run_request_real_time_watch_rankings_v5`."""
        response = await self._async_client.get(
            url=self.real_time_watch_rankings_v5_endpoint.format(unit=parameter.unit),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealTimeWatchRankingsV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_real_price_trade_rankings_complex_v5(
        self,
        parameter: DabangRealPriceTradeRankingsComplexV5RequestParameterModel
    ) -> DabangRealPriceTradeRankingsComplexV5ResponseModel:
        """Rank complexes by trades nationwide via `GET /api/v5/real-price/trade/rankings/complex`.

        Same retry behaviour as `run_request_loc_search_v5`.

        Args:
            parameter: 유형·매매/전세·기간·수.

        Returns:
            DabangRealPriceTradeRankingsComplexV5ResponseModel: 기준 기간과 순위.
        """
        response = self._client.get(
            url=self.real_price_trade_rankings_complex_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceTradeRankingsComplexV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_real_price_trade_rankings_complex_v5(
        self,
        parameter: DabangRealPriceTradeRankingsComplexV5RequestParameterModel
    ) -> DabangRealPriceTradeRankingsComplexV5ResponseModel:
        """Async variant of `run_request_real_price_trade_rankings_complex_v5`."""
        response = await self._async_client.get(
            url=self.real_price_trade_rankings_complex_v5_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRealPriceTradeRankingsComplexV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_info_real_estate_ranking_v5(
        self,
        parameter: DabangRegionInfoRealEstateRankingV5RequestParameterModel
    ) -> DabangRegionInfoRealEstateRankingV5ResponseModel:
        """Rank dongs or complexes inside a scope via `GET /api/v5/region-info/real-estate/ranking/{unit}/{metric}`.

        Same retry behaviour as `run_request_loc_search_v5`. 값은 항목마다 다른 글자 키로 온다.

        Args:
            parameter: 동·단지, 항목, 범위, 유형·거래 유형, 정렬, 쪽.

        Returns:
            DabangRegionInfoRealEstateRankingV5ResponseModel: 순위 한 쪽.
        """
        response = self._client.get(
            url=self.region_info_real_estate_ranking_v5_endpoint.format(unit=parameter.unit, metric=parameter.metric),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRealEstateRankingV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_info_real_estate_ranking_v5(
        self,
        parameter: DabangRegionInfoRealEstateRankingV5RequestParameterModel
    ) -> DabangRegionInfoRealEstateRankingV5ResponseModel:
        """Async variant of `run_request_region_info_real_estate_ranking_v5`."""
        response = await self._async_client.get(
            url=self.region_info_real_estate_ranking_v5_endpoint.format(unit=parameter.unit, metric=parameter.metric),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRealEstateRankingV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_region_info_ranking_v5(
        self,
        parameter: DabangRegionInfoRankingV5RequestParameterModel
    ) -> DabangRegionInfoRankingV5ResponseModel:
        """Rank dongs inside a scope by schools, population or facilities via `GET /api/v5/region-info/{topic}/ranking/{metric}`.

        Same retry behaviour as `run_request_loc_search_v5`. 한 쪽은 30곳까지다 (넘으면 400).

        Args:
            parameter: 주제·항목, 범위, 종류(진학 갈래·학원·설립·시설), 정렬, 쪽.

        Returns:
            DabangRegionInfoRankingV5ResponseModel: 순위 한 쪽.
        """
        response = self._client.get(
            url=self.region_info_ranking_v5_endpoint.format(topic=parameter.topic, metric=parameter.metric),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRankingV5ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_region_info_ranking_v5(
        self,
        parameter: DabangRegionInfoRankingV5RequestParameterModel
    ) -> DabangRegionInfoRankingV5ResponseModel:
        """Async variant of `run_request_region_info_ranking_v5`."""
        response = await self._async_client.get(
            url=self.region_info_ranking_v5_endpoint.format(topic=parameter.topic, metric=parameter.metric),
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            headers=V5_HEADERS
        )
        raise_for_status(response=response)
        return DabangRegionInfoRankingV5ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_sale_in_lots_detail2_v3(
        self,
        parameter: DabangSaleInLotsDetail2V3RequestParameterModel
    ) -> DabangSaleInLotsDetail2V3ResponseModel:
        """Fetch a sale-in-lots complex via `GET /api/3/sale-in-lots/detail2`.

        Same retry behaviour as `run_request_loc_search_v5`. 옛 방식이라 쿼리에 버전을 붙인다.

        Args:
            parameter: 분양 ID.

        Returns:
            DabangSaleInLotsDetail2V3ResponseModel: 단지·일정·평형.
        """
        response = self._client.get(
            url=self.sale_in_lots_detail2_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangSaleInLotsDetail2V3ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_sale_in_lots_detail2_v3(
        self,
        parameter: DabangSaleInLotsDetail2V3RequestParameterModel
    ) -> DabangSaleInLotsDetail2V3ResponseModel:
        """Async variant of `run_request_sale_in_lots_detail2_v3`."""
        response = await self._async_client.get(
            url=self.sale_in_lots_detail2_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangSaleInLotsDetail2V3ResponseModel.model_validate(response.json())

    @dabang_retry
    def run_request_sale_in_lots_list_schedule_v3(
        self,
        parameter: DabangSaleInLotsListScheduleV3RequestParameterModel
    ) -> DabangSaleInLotsListScheduleV3ResponseModel:
        """List subscription schedules by day via `GET /api/3/sale-in-lots/list/schedule`.

        Same retry behaviour as `run_request_loc_search_v5`. 최대 7일이다 (요청 모델이 막는다).

        Args:
            parameter: 시작·끝 날.

        Returns:
            DabangSaleInLotsListScheduleV3ResponseModel: 날마다 종류별 일정.
        """
        response = self._client.get(
            url=self.sale_in_lots_list_schedule_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangSaleInLotsListScheduleV3ResponseModel.model_validate(response.json())

    @dabang_retry
    async def arun_request_sale_in_lots_list_schedule_v3(
        self,
        parameter: DabangSaleInLotsListScheduleV3RequestParameterModel
    ) -> DabangSaleInLotsListScheduleV3ResponseModel:
        """Async variant of `run_request_sale_in_lots_list_schedule_v3`."""
        response = await self._async_client.get(
            url=self.sale_in_lots_list_schedule_v3_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return DabangSaleInLotsListScheduleV3ResponseModel.model_validate(response.json())
