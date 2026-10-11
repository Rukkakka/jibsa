from collections.abc import Generator
from functools import cached_property

from httpx import (
    AsyncClient,
    Auth,
    Client,
    Request,
    Response,
)
from pydantic import Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from jibsa.core.http import (
    BaseHTTPClient,
    bearer_authorization,
    create_base_url,
    log_retry_before_sleep,
    raise_for_status,
    should_retry_idempotent,
    wait_retry_after,
)
from jibsa.providers.zigbang.api.request.apt import (
    ZigbangLocalsItemCatalogsRequestParameterModel,
    ZigbangNearbyDanjisRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
    ZigbangDanjisRequestParameterModel,
    ZigbangItemsListV1RequestPayloadModel,
)
from jibsa.providers.zigbang.api.request.complex import (
    ZigbangDanjisSchoolsRequestParameterModel,
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.request.listing import (
    ZigbangBlsSchoolZonesV1RequestParameterModel,
    ZigbangItemCatalogsItemsRequestParameterModel,
    ZigbangItemsDetailV1RequestParameterModel,
    ZigbangItemsOfficetelsV1RequestParameterModel,
    ZigbangItemsOneroomsV1RequestParameterModel,
    ZigbangItemsSubwaysOfficetelsV1RequestParameterModel,
    ZigbangItemsSubwaysOneroomsV1RequestParameterModel,
    ZigbangItemsSubwaysVillasV1RequestParameterModel,
    ZigbangItemsV3RequestParameterModel,
    ZigbangItemsVillasV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.request.real_price import (
    ZigbangDanjisRoomTypesRtPricesRequestParameterModel,
    ZigbangDanjisRtPricesRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.region import (
    ZigbangLocalPolygonV2RequestParameterModel,
    ZigbangSearchV2RequestParameterModel,
)
from jibsa.providers.zigbang.api.request.stay import (
    ZigbangGuestItemsByIdsRequestParameterModel,
    ZigbangGuestItemsMarkersRequestParameterModel,
    ZigbangGuestItemsPriceCalculationRequestPayloadModel,
    ZigbangGuestItemsRequestParameterModel,
    ZigbangGuestItemsSearchRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.store import (
    ZigbangStoreArticleStoresListV2RequestPayloadModel,
    ZigbangStoreArticleStoresV2RequestPayloadModel,
    ZigbangStoreArticleStoreV2RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.apt import (
    ZigbangLocalsItemCatalogsResponseModel,
    ZigbangNearbyDanjisResponseModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangDanjisItemCatalogsResponseModel,
    ZigbangDanjisResponseModel,
    ZigbangItemsListV1ResponseModel,
    ZigbangUnauthTokenV2ResponseModel,
)
from jibsa.providers.zigbang.api.response.complex import (
    ZigbangDanjisSchoolsResponseModel,
    ZigbangItemsOfficetelsBuildingV1ResponseModel,
)
from jibsa.providers.zigbang.api.response.listing import (
    ZigbangBlsSchoolZonesV1ResponseModel,
    ZigbangItemCatalogsItemsResponseModel,
    ZigbangItemsDetailV1ResponseModel,
    ZigbangItemsOfficetelsV1ResponseModel,
    ZigbangItemsOneroomsV1ResponseModel,
    ZigbangItemsSubwaysOfficetelsV1ResponseModel,
    ZigbangItemsSubwaysOneroomsV1ResponseModel,
    ZigbangItemsSubwaysVillasV1ResponseModel,
    ZigbangItemsV3ResponseModel,
    ZigbangItemsVillasV1ResponseModel,
)
from jibsa.providers.zigbang.api.response.real_price import (
    ZigbangDanjisRoomTypesRtPricesResponseModel,
    ZigbangDanjisRtPricesResponseModel,
)
from jibsa.providers.zigbang.api.response.region import (
    ZigbangLocalPolygonV2ResponseModel,
    ZigbangSearchV2ResponseModel,
)
from jibsa.providers.zigbang.api.response.stay import (
    ZigbangGuestItemsByIdsResponseModel,
    ZigbangGuestItemsMarkersResponseModel,
    ZigbangGuestItemsPriceCalculationResponseModel,
    ZigbangGuestItemsResponseModel,
    ZigbangGuestItemsSearchResponseModel,
)
from jibsa.providers.zigbang.api.response.store import (
    ZigbangStoreArticleStoresListV2ResponseModel,
    ZigbangStoreArticleStoresV2ResponseModel,
    ZigbangStoreArticleStoreV2ResponseModel,
)

from typing import (
    Annotated,
    ClassVar,
)


zigbang_retry = retry(
    retry=retry_if_exception(should_retry_idempotent),
    stop=stop_after_attempt(3),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""조회 전용 엔드포인트 공통 재시도: 최대 3회, 1초(또는 `Retry-After`) 간격, 5xx·429·timeout·transport 오류만."""


class ZigbangGuestAuth(Auth):
    """Attach a guest `Authorization: Bearer` token, issuing one on first use.

    토큰 발급 요청을 auth flow 안에서 yield 하므로 sync/async 클라이언트가 같은
    흐름을 쓰고, 토큰이 실제로 필요한 첫 요청 전까지는 발급하지 않는다. 401 을
    받으면 토큰을 한 번 재발급해 다시 보낸다. (직방은 잘못된 토큰에도 401 대신
    빈 200 을 주는 엔드포인트가 있어, 이 재발급은 401 을 주는 경우에만 동작한다.)

    Args:
        token_url: 익명 토큰 발급 URL.
        user_agent: 토큰 발급 요청에 쓸 `User-Agent`.
        token: 이미 가진 토큰. None 이면 첫 요청 때 발급한다. Defaults to None.
    """

    requires_response_body = True

    def __init__(
        self,
        token_url: str,
        user_agent: str,
        token: str | None = None
    ) -> None:
        self._token_url = token_url
        self._user_agent = user_agent
        self._token = token

    def _token_request(self) -> Request:
        return Request(
            method='POST',
            url=self._token_url,
            headers={
                'Accept': 'application/json',
                'User-Agent': self._user_agent,
            },
        )

    def _store_token(self, response: Response) -> str:
        raise_for_status(response=response)
        self._token = ZigbangUnauthTokenV2ResponseModel.model_validate(response.json()).token
        return self._token

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        issued_now = False
        token = self._token
        if token is None:
            token = self._store_token((yield self._token_request()))
            issued_now = True

        request.headers['Authorization'] = bearer_authorization(token)
        response = yield request

        # 401 만 보고 재발급한다. 2026-10-11 실측으로는 가짜 토큰·토큰 없이도 목록·요약·상세·단지·단기임대가 모두
        # 정상 200 이라, 토큰 오류가 빈 200 으로 숨어 재발급을 놓치는 API 는 없다
        if response.status_code == 401 and not issued_now:
            token = self._store_token((yield self._token_request()))
            request.headers['Authorization'] = bearer_authorization(token)
            yield request


class ZigbangClient(BaseHTTPClient):
    """직방 (apis.zigbang.com) 비공식 API 클라이언트.

    로그인 없이 익명 토큰만으로 원룸·오피스텔·빌라 매물 목록, 요약, 상세와 지역
    검색과 역 반경 매물, 아파트 지역 매물·상세, 상가, 단기임대(stay-apis.zigbang.com)를 조회한다. 토큰은
    `ZigbangGuestAuth` 가 첫 요청 때 발급해 붙인다. 금액은 대부분 **만원** 단위로 오지만,
    원룸·빌라 요약 응답의 `manage_cost`, 아파트 상세의 관리비, 단기임대 응답의 금액은 원 단위다.

    엔드포인트 action id 는 버전 앞의 서비스 접두(`/house/property`, `/apt`)와 경로
    파라미터를 빼고 남은 세그먼트를 `_` 로 잇고 버전을 끝으로 옮겨 만든다.
    (`/house/property/v1/items/onerooms` → `items_onerooms_v1`,
    `/v3/items/{itemId}` → `items_v3`, `/apt/locals/{localCode}/item-catalogs` →
    `locals_item_catalogs`) 상가 상세 `/v2/store/article/stores/{itemId}` 는 규칙대로면
    위치 조회 `/v2/store/article/stores` 와 이름이 겹쳐, 웹 클라이언트 이름(`articleStore`)을
    따라 `store_article_store_v2` 로 부른다. 오피스텔 건물 매물 `/house/property/v1/items/officetels/{buildingId}`
    도 지도 목록 `/house/property/v1/items/officetels` 와 이름이 겹쳐 `items_officetels_building_v1` 로
    부른다. 단기임대 엔드포인트는 `stay_host` 의 경로다.

    Args:
        host: API 호스트 (스킴 제외). Defaults to 'apis.zigbang.com'.
        account_host: 토큰 발급 호스트. Defaults to 'account.zigbang.com'.
        stay_host: 단기임대 API 호스트. Defaults to 'stay-apis.zigbang.com'.
        token: 이미 발급받은 익명 토큰. None 이면 자동 발급. Defaults to None.
        rate_limit: 요청 제한 정책. Defaults to 0.2초 간격·분당 120회·429 후 2분 쿨다운.

    Attributes:
        base_url: `url_schema` 와 `host` 로 만든 API 베이스 URL.
        token_url: 익명 토큰 발급 URL.
        stay_base_url: 단기임대 API 베이스 URL.

    Example:
        >>> with ZigbangClient() as client:
        ...     client.run_request_items_onerooms_v1(
        ...         ZigbangItemsOneroomsV1RequestParameterModel(geohash='wydm6')
        ...     )
    """

    unauth_token_v2_endpoint: ClassVar[str] = '/v2/unauth/token'
    search_v2_endpoint: ClassVar[str] = '/v2/search'
    local_polygon_v2_endpoint: ClassVar[str] = '/v2/local/polygon'
    items_onerooms_v1_endpoint: ClassVar[str] = '/house/property/v1/items/onerooms'
    items_subways_onerooms_v1_endpoint: ClassVar[str] = '/house/property/v1/items/subways/{subway_id}/onerooms'
    items_subways_officetels_v1_endpoint: ClassVar[str] = '/house/property/v1/items/subways/{subway_id}/officetels'
    items_subways_villas_v1_endpoint: ClassVar[str] = '/house/property/v1/items/subways/{subway_id}/villas'
    items_officetels_v1_endpoint: ClassVar[str] = '/house/property/v1/items/officetels'
    items_villas_v1_endpoint: ClassVar[str] = '/house/property/v1/items/villas'
    items_list_v1_endpoint: ClassVar[str] = '/house/property/v1/items/list'
    locals_item_catalogs_endpoint: ClassVar[str] = '/apt/locals/{local_code}/item-catalogs'
    item_catalogs_items_endpoint: ClassVar[str] = '/apt/item-catalogs/items/{item_id}'
    danjis_endpoint: ClassVar[str] = '/apt/danjis/{danji_id}'
    danjis_schools_endpoint: ClassVar[str] = '/apt/danjis/{danji_id}/schools'
    bls_school_zones_v1_endpoint: ClassVar[str] = '/house/property/v1/bls/{pnu}/school_zones'
    nearby_danjis_endpoint: ClassVar[str] = '/apt/nearby-danjis'
    danjis_item_catalogs_endpoint: ClassVar[str] = '/apt/danjis/{danji_id}/item-catalogs'
    danjis_rt_prices_endpoint: ClassVar[str] = '/apt/danjis/{danji_id}/rt-prices'
    danjis_room_types_rt_prices_endpoint: ClassVar[str] = '/apt/danjis/{danji_id}/room-types/{room_type_id}/rt-prices'
    items_officetels_building_v1_endpoint: ClassVar[str] = '/house/property/v1/items/officetels/{building_id}'
    store_article_stores_v2_endpoint: ClassVar[str] = '/v2/store/article/stores'
    store_article_stores_list_v2_endpoint: ClassVar[str] = '/v2/store/article/stores/list'
    store_article_store_v2_endpoint: ClassVar[str] = '/v2/store/article/stores/{item_id}'
    guest_items_search_endpoint: ClassVar[str] = '/guest/items/search'
    guest_items_markers_endpoint: ClassVar[str] = '/guest/items/markers'
    guest_items_by_ids_endpoint: ClassVar[str] = '/guest/items/by-ids'
    guest_items_endpoint: ClassVar[str] = '/guest/items/{item_id}'
    guest_items_price_calculation_endpoint: ClassVar[str] = '/guest/items/{item_id}/price-calculation'
    items_detail_v1_endpoint: ClassVar[str] = '/house/property/v1/items/{item_id}/detail'
    items_v3_endpoint: ClassVar[str] = '/v3/items/{item_id}'

    source_name: ClassVar[str] = 'zigbang'
    default_rate_limit: ClassVar[dict[str, object]] = {
        'min_interval': 0.2,
        'max_per_minute': 120,
        'cooldown': 120,
    }

    host: str = 'apis.zigbang.com'

    account_host: str = 'account.zigbang.com'

    stay_host: str = 'stay-apis.zigbang.com'

    token: Annotated[
        str | None,
        Field(repr=False)
    ] = None

    @property
    def base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.host
        )

    @property
    def stay_base_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.stay_host
        )

    @property
    def token_url(self) -> str:
        return create_base_url(
            schema=self.url_schema,
            host=self.account_host
        ) + self.unauth_token_v2_endpoint

    @property
    def base_header(self) -> dict[str, str]:
        return {
            'Accept': 'application/json',
            'User-Agent': self.user_agent,
            'Origin': 'https://www.zigbang.com',
            'Referer': 'https://www.zigbang.com/',
            # 없으면 일부 매물(오피스텔 등) 상세가 "x-zigbang-platform 를 확인해 주세요" 404 를 준다.
            'x-zigbang-platform': 'www',
        }

    @cached_property
    def _auth(self) -> ZigbangGuestAuth:
        # sync/async 클라이언트가 같은 토큰을 공유한다.
        return ZigbangGuestAuth(
            token_url=self.token_url,
            user_agent=self.user_agent,
            token=self.token
        )

    @cached_property
    def _client(self) -> Client:
        return Client(
            base_url=self.base_url,
            headers=self.base_header,
            auth=self._auth,
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
            auth=self._auth,
            event_hooks=self.async_rate_limit_hooks(),
            verify=self.verify,
            timeout=self.timeout,
            proxy=self.proxy
        )

    @zigbang_retry
    def run_request_search_v2(
        self,
        parameter: ZigbangSearchV2RequestParameterModel
    ) -> ZigbangSearchV2ResponseModel:
        """Search regions, stations and complexes via `GET /v2/search`.

        Retries up to 3 attempts on HTTP 5xx/429 responses and httpx
        timeout/transport errors, waiting 1s between attempts or, on a 429,
        the server's `Retry-After` (capped at 60s); any other error, and the
        final failed attempt, is raised. 요청 제한이 켜져 있으면(기본) 429 는
        재시도 없이 곧바로 `RateLimitedError` (쿨다운) 로 끝난다. 토큰이 필요 없는 엔드포인트라 익명
        토큰을 붙이지 않는다.

        Args:
            parameter: 검색 쿼리 — `q` (검색어) plus optional `service_type`
                and `lease_yn`.

        Returns:
            ZigbangSearchV2ResponseModel: 관련도 순 검색 결과. 지역 결과는
                `type='address'` 이며 중심 좌표와 법정동코드를 담는다.
        """
        response = self._client.get(
            url=self.search_v2_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            auth=None
        )
        raise_for_status(response=response)
        return ZigbangSearchV2ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_search_v2(
        self,
        parameter: ZigbangSearchV2RequestParameterModel
    ) -> ZigbangSearchV2ResponseModel:
        """Async variant of `run_request_search_v2` (`GET /v2/search`)."""
        response = await self._async_client.get(
            url=self.search_v2_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
            auth=None
        )
        raise_for_status(response=response)
        return ZigbangSearchV2ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_local_polygon_v2(
        self,
        parameter: ZigbangLocalPolygonV2RequestParameterModel
    ) -> ZigbangLocalPolygonV2ResponseModel:
        """Fetch the administrative area containing a geohash cell via `GET /v2/local/polygon`.

        Same retry behaviour as `run_request_items_onerooms_v1`. `polygon=true` 면 경계(GeoJSON
        MultiPolygon)를 함께 준다.

        Args:
            parameter: `geohash`, `level` (local1~3), `polygon`.

        Returns:
            ZigbangLocalPolygonV2ResponseModel: 지역 코드·이름과 경계.
        """
        response = self._client.get(
            url=self.local_polygon_v2_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangLocalPolygonV2ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_local_polygon_v2(
        self,
        parameter: ZigbangLocalPolygonV2RequestParameterModel
    ) -> ZigbangLocalPolygonV2ResponseModel:
        """Async variant of `run_request_local_polygon_v2`."""
        response = await self._async_client.get(
            url=self.local_polygon_v2_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangLocalPolygonV2ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_onerooms_v1(
        self,
        parameter: ZigbangItemsOneroomsV1RequestParameterModel
    ) -> ZigbangItemsOneroomsV1ResponseModel:
        """List one-room pins in a geohash tile via `GET /house/property/v1/items/onerooms`.

        Retries up to 3 attempts on HTTP 5xx/429 responses and httpx
        timeout/transport errors, waiting 1s between attempts or, on a 429,
        the server's `Retry-After` (capped at 60s); any other error, and the
        final failed attempt, is raised. 요청 제한이 켜져 있으면(기본) 429 는
        재시도 없이 곧바로 `RateLimitedError` (쿨다운) 로 끝난다.

        Args:
            parameter: `geohash` plus optional `sales_types` (전세/월세/단기) and
                만원 단위 가격 필터.

        Returns:
            ZigbangItemsOneroomsV1ResponseModel: 타일 안의 매물 핀(ID·좌표),
                노출 구역, 지하철역.
        """
        response = self._client.get(
            url=self.items_onerooms_v1_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsOneroomsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_onerooms_v1(
        self,
        parameter: ZigbangItemsOneroomsV1RequestParameterModel
    ) -> ZigbangItemsOneroomsV1ResponseModel:
        """Async variant of `run_request_items_onerooms_v1`."""
        response = await self._async_client.get(
            url=self.items_onerooms_v1_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsOneroomsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_officetels_v1(
        self,
        parameter: ZigbangItemsOfficetelsV1RequestParameterModel
    ) -> ZigbangItemsOfficetelsV1ResponseModel:
        """List officetel pins in a geohash tile via `GET /house/property/v1/items/officetels`.

        Same retry behaviour as `run_request_items_onerooms_v1`.

        Args:
            parameter: `geohash` plus optional `sales_types` (전세/월세/매매/단기)
                and 만원 단위 가격 필터.

        Returns:
            ZigbangItemsOfficetelsV1ResponseModel: 타일 안의 매물 핀, 노출
                구역, 지하철역.
        """
        response = self._client.get(
            url=self.items_officetels_v1_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsOfficetelsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_officetels_v1(
        self,
        parameter: ZigbangItemsOfficetelsV1RequestParameterModel
    ) -> ZigbangItemsOfficetelsV1ResponseModel:
        """Async variant of `run_request_items_officetels_v1`."""
        response = await self._async_client.get(
            url=self.items_officetels_v1_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsOfficetelsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_villas_v1(
        self,
        parameter: ZigbangItemsVillasV1RequestParameterModel
    ) -> ZigbangItemsVillasV1ResponseModel:
        """List villa pins in a geohash tile via `GET /house/property/v1/items/villas`.

        Same retry behaviour as `run_request_items_onerooms_v1`.

        Args:
            parameter: `geohash` plus optional `sales_types` (전세/월세/매매/단기)
                and 만원 단위 가격 필터.

        Returns:
            ZigbangItemsVillasV1ResponseModel: 타일 안의 매물 핀, 노출 구역,
                지하철역.
        """
        response = self._client.get(
            url=self.items_villas_v1_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsVillasV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_villas_v1(
        self,
        parameter: ZigbangItemsVillasV1RequestParameterModel
    ) -> ZigbangItemsVillasV1ResponseModel:
        """Async variant of `run_request_items_villas_v1`."""
        response = await self._async_client.get(
            url=self.items_villas_v1_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsVillasV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_list_v1(
        self,
        payload: ZigbangItemsListV1RequestPayloadModel
    ) -> ZigbangItemsListV1ResponseModel:
        """Fetch item summaries in a batch via `POST /house/property/v1/items/list`.

        POST 지만 조회 전용이라 idempotent 재시도를 쓴다. Retries up to 3
        attempts on HTTP 5xx/429 responses and httpx timeout/transport errors,
        waiting 1s between attempts or the server's `Retry-After` (capped at
        60s). 요청 제한이 켜져 있으면(기본) 429 는 재시도 없이 곧바로
        `RateLimitedError` (쿨다운) 로 끝난다.

        Args:
            payload: `item_ids` — 최대 15개.

        Returns:
            ZigbangItemsListV1ResponseModel: 가격·면적·층·주소가 담긴 요약.
                서버에서 내려간 매물은 결과에서 빠진다.
        """
        response = self._client.post(
            url=self.items_list_v1_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsListV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_list_v1(
        self,
        payload: ZigbangItemsListV1RequestPayloadModel
    ) -> ZigbangItemsListV1ResponseModel:
        """Async variant of `run_request_items_list_v1`."""
        response = await self._async_client.post(
            url=self.items_list_v1_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsListV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_detail_v1(
        self,
        parameter: ZigbangItemsDetailV1RequestParameterModel
    ) -> ZigbangItemsDetailV1ResponseModel:
        """Fetch the structured house detail via `GET /house/property/v1/items/{itemId}/detail`.

        Same retry behaviour as `run_request_items_onerooms_v1`. `/v3/items` 와 응답 구조가 다르다.
        없는 매물이면 404 로 `ResponseStatusError` 가 나고, 내려간 매물은 200 에 `status` 가 open 이 아니다.

        Args:
            parameter: `item_id` (경로).

        Returns:
            ZigbangItemsDetailV1ResponseModel: 주소·면적·층·입주일·관리비·옵션과 인근 지하철역.
                입주일(`moveInAt`)은 null 일 수 있다.
        """
        response = self._client.get(
            url=self.items_detail_v1_endpoint.format(item_id=parameter.item_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsDetailV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_detail_v1(
        self,
        parameter: ZigbangItemsDetailV1RequestParameterModel
    ) -> ZigbangItemsDetailV1ResponseModel:
        """Async variant of `run_request_items_detail_v1`."""
        response = await self._async_client.get(
            url=self.items_detail_v1_endpoint.format(item_id=parameter.item_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsDetailV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_v3(
        self,
        parameter: ZigbangItemsV3RequestParameterModel
    ) -> ZigbangItemsV3ResponseModel:
        """Fetch the full item detail via `GET /v3/items/{itemId}`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 없는 매물이면
        404 로 `ResponseStatusError` 가 난다.

        Args:
            parameter: `item_id` (경로) plus `domain`.

        Returns:
            ZigbangItemsV3ResponseModel: 매물 상세, 중개사, 인근 지하철역.
        """
        response = self._client.get(
            url=self.items_v3_endpoint.format(item_id=parameter.item_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsV3ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_v3(
        self,
        parameter: ZigbangItemsV3RequestParameterModel
    ) -> ZigbangItemsV3ResponseModel:
        """Async variant of `run_request_items_v3`."""
        response = await self._async_client.get(
            url=self.items_v3_endpoint.format(item_id=parameter.item_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsV3ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_locals_item_catalogs(
        self,
        parameter: ZigbangLocalsItemCatalogsRequestParameterModel
    ) -> ZigbangLocalsItemCatalogsResponseModel:
        """List apartment listings in a region via `GET /apt/locals/{localCode}/item-catalogs`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 웹 아파트 지도의 지역 매물 목록과
        같은 엔드포인트다. 지역 코드가 법정동코드 10자리면 에러 없이 0건이므로 8·5·2자리로 줄여 보낸다.

        Args:
            parameter: `local_code` (경로) plus 거래 유형(`tranTypeIn`), 만원 단위 가격,
                공급면적 필터와 `offset`/`limit` (최대 20).

        Returns:
            ZigbangLocalsItemCatalogsResponseModel: 전체 수(`count`)와 이번 페이지의 카탈로그.
        """
        response = self._client.get(
            url=self.locals_item_catalogs_endpoint.format(local_code=parameter.local_code),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangLocalsItemCatalogsResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_locals_item_catalogs(
        self,
        parameter: ZigbangLocalsItemCatalogsRequestParameterModel
    ) -> ZigbangLocalsItemCatalogsResponseModel:
        """Async variant of `run_request_locals_item_catalogs`."""
        response = await self._async_client.get(
            url=self.locals_item_catalogs_endpoint.format(local_code=parameter.local_code),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangLocalsItemCatalogsResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_item_catalogs_items(
        self,
        parameter: ZigbangItemCatalogsItemsRequestParameterModel
    ) -> ZigbangItemCatalogsItemsResponseModel:
        """Fetch an apartment item detail via `GET /apt/item-catalogs/items/{itemId}`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 웹 아파트 매물 페이지(v2)가 쓰는
        엔드포인트로, `/v3/items` 가 아파트에 대해 주지 않는 단지 이름·방 수·욕실 수·사용승인일과
        아파트 관리비를 준다. 없는 매물이면 404 다.

        Args:
            parameter: `item_id` (경로) plus `item_source`.

        Returns:
            ZigbangItemCatalogsItemsResponseModel: 아파트 매물 상세 (관리비는 원 단위).
        """
        response = self._client.get(
            url=self.item_catalogs_items_endpoint.format(item_id=parameter.item_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemCatalogsItemsResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_item_catalogs_items(
        self,
        parameter: ZigbangItemCatalogsItemsRequestParameterModel
    ) -> ZigbangItemCatalogsItemsResponseModel:
        """Async variant of `run_request_item_catalogs_items`."""
        response = await self._async_client.get(
            url=self.item_catalogs_items_endpoint.format(item_id=parameter.item_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemCatalogsItemsResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_danjis(
        self,
        parameter: ZigbangDanjisRequestParameterModel
    ) -> ZigbangDanjisResponseModel:
        """Fetch an apartment complex via `GET /apt/danjis/{danjiId}`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 없는 단지면 404 다.

        Args:
            parameter: `danji_id` (경로).

        Returns:
            ZigbangDanjisResponseModel: 단지 이름·주소·세대수·사용승인일·시공사 등.
        """
        response = self._client.get(
            url=self.danjis_endpoint.format(danji_id=parameter.danji_id)
        )
        raise_for_status(response=response)
        return ZigbangDanjisResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_danjis(
        self,
        parameter: ZigbangDanjisRequestParameterModel
    ) -> ZigbangDanjisResponseModel:
        """Async variant of `run_request_danjis`."""
        response = await self._async_client.get(
            url=self.danjis_endpoint.format(danji_id=parameter.danji_id)
        )
        raise_for_status(response=response)
        return ZigbangDanjisResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_nearby_danjis(
        self,
        parameter: ZigbangNearbyDanjisRequestParameterModel
    ) -> ZigbangNearbyDanjisResponseModel:
        """List apartment complexes around a point via `GET /apt/nearby-danjis`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 단지마다 거리(m)가 붙고 가까운 순이다.
        매물 수는 주지 않는다.

        Args:
            parameter: 중심 `lat`/`lng`, 반경 `radius` (km), `limit`.

        Returns:
            ZigbangNearbyDanjisResponseModel: 반경 안 단지 (가까운 순).
        """
        response = self._client.get(
            url=self.nearby_danjis_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangNearbyDanjisResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_nearby_danjis(
        self,
        parameter: ZigbangNearbyDanjisRequestParameterModel
    ) -> ZigbangNearbyDanjisResponseModel:
        """Async variant of `run_request_nearby_danjis`."""
        response = await self._async_client.get(
            url=self.nearby_danjis_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangNearbyDanjisResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_danjis_rt_prices(
        self,
        parameter: ZigbangDanjisRtPricesRequestParameterModel
    ) -> ZigbangDanjisRtPricesResponseModel:
        """List complex real-transaction prices via `GET /apt/danjis/{danjiId}/rt-prices`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 국토부 신고 실거래가, 최근 계약 순이다.
        `offset` 은 쪽 번호다.

        Args:
            parameter: `danji_id` (경로) plus `deal_type` (sales·rent·all), `offset`, `limit`.

        Returns:
            ZigbangDanjisRtPricesResponseModel: 이번 쪽의 실거래와 다음 쪽 여부.
        """
        response = self._client.get(
            url=self.danjis_rt_prices_endpoint.format(danji_id=parameter.danji_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangDanjisRtPricesResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_danjis_rt_prices(
        self,
        parameter: ZigbangDanjisRtPricesRequestParameterModel
    ) -> ZigbangDanjisRtPricesResponseModel:
        """Async variant of `run_request_danjis_rt_prices`."""
        response = await self._async_client.get(
            url=self.danjis_rt_prices_endpoint.format(danji_id=parameter.danji_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangDanjisRtPricesResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_danjis_room_types_rt_prices(
        self,
        parameter: ZigbangDanjisRoomTypesRtPricesRequestParameterModel
    ) -> ZigbangDanjisRoomTypesRtPricesResponseModel:
        """List real-transaction prices of one floor plan via `GET /apt/danjis/{danjiId}/room-types/{danjiRoomTypeId}/rt-prices`.

        Same retry behaviour as `run_request_danjis_rt_prices`.

        Args:
            parameter: `danji_id`·`room_type_id` (경로) plus `deal_type`, `offset`, `limit`.

        Returns:
            ZigbangDanjisRoomTypesRtPricesResponseModel: 이번 쪽의 실거래와 다음 쪽 여부.
        """
        response = self._client.get(
            url=self.danjis_room_types_rt_prices_endpoint.format(danji_id=parameter.danji_id, room_type_id=parameter.room_type_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangDanjisRoomTypesRtPricesResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_danjis_room_types_rt_prices(
        self,
        parameter: ZigbangDanjisRoomTypesRtPricesRequestParameterModel
    ) -> ZigbangDanjisRoomTypesRtPricesResponseModel:
        """Async variant of `run_request_danjis_room_types_rt_prices`."""
        response = await self._async_client.get(
            url=self.danjis_room_types_rt_prices_endpoint.format(danji_id=parameter.danji_id, room_type_id=parameter.room_type_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangDanjisRoomTypesRtPricesResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_danjis_schools(
        self,
        parameter: ZigbangDanjisSchoolsRequestParameterModel
    ) -> ZigbangDanjisSchoolsResponseModel:
        """Fetch the school zones of an apartment complex via `GET /apt/danjis/{danjiId}/schools`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 초등은 통학구역, 중·고는 학교군과 그 안의
        학교를 가까운 순으로 준다 (교육청 학구도 기준).

        Args:
            parameter: `danji_id` (경로).

        Returns:
            ZigbangDanjisSchoolsResponseModel: 초·중·고 학구와 학교.
        """
        response = self._client.get(url=self.danjis_schools_endpoint.format(danji_id=parameter.danji_id))
        raise_for_status(response=response)
        return ZigbangDanjisSchoolsResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_danjis_schools(
        self,
        parameter: ZigbangDanjisSchoolsRequestParameterModel
    ) -> ZigbangDanjisSchoolsResponseModel:
        """Async variant of `run_request_danjis_schools`."""
        response = await self._async_client.get(url=self.danjis_schools_endpoint.format(danji_id=parameter.danji_id))
        raise_for_status(response=response)
        return ZigbangDanjisSchoolsResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_bls_school_zones_v1(
        self,
        parameter: ZigbangBlsSchoolZonesV1RequestParameterModel
    ) -> ZigbangBlsSchoolZonesV1ResponseModel:
        """Fetch the school zones of a building lot via `GET /house/property/v1/bls/{pnu}/school_zones`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 원룸·빌라·오피스텔 매물 상세의 `pnu` 로
        조회한다. 거리는 m 정수다.

        Args:
            parameter: `pnu` (경로, 19자리).

        Returns:
            ZigbangBlsSchoolZonesV1ResponseModel: 초·중·고 학구와 학교.
        """
        response = self._client.get(url=self.bls_school_zones_v1_endpoint.format(pnu=parameter.pnu))
        raise_for_status(response=response)
        return ZigbangBlsSchoolZonesV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_bls_school_zones_v1(
        self,
        parameter: ZigbangBlsSchoolZonesV1RequestParameterModel
    ) -> ZigbangBlsSchoolZonesV1ResponseModel:
        """Async variant of `run_request_bls_school_zones_v1`."""
        response = await self._async_client.get(url=self.bls_school_zones_v1_endpoint.format(pnu=parameter.pnu))
        raise_for_status(response=response)
        return ZigbangBlsSchoolZonesV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_danjis_item_catalogs(
        self,
        parameter: ZigbangDanjisItemCatalogsRequestParameterModel
    ) -> ZigbangDanjisItemCatalogsResponseModel:
        """List apartment listings in a complex via `GET /apt/danjis/{danjiId}/item-catalogs`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 웹 단지 페이지의 매물 목록과 같은
        엔드포인트다.

        Args:
            parameter: `danji_id` (경로) plus 거래 유형(`tranTypeIn`), 평형 ID, 만원 단위 가격 필터와
                `offset`/`limit` (최대 50).

        Returns:
            ZigbangDanjisItemCatalogsResponseModel: 전체 수, 거래 유형별 수, 평형 목록과 이번 페이지의 카탈로그.
        """
        response = self._client.get(
            url=self.danjis_item_catalogs_endpoint.format(danji_id=parameter.danji_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangDanjisItemCatalogsResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_danjis_item_catalogs(
        self,
        parameter: ZigbangDanjisItemCatalogsRequestParameterModel
    ) -> ZigbangDanjisItemCatalogsResponseModel:
        """Async variant of `run_request_danjis_item_catalogs`."""
        response = await self._async_client.get(
            url=self.danjis_item_catalogs_endpoint.format(danji_id=parameter.danji_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangDanjisItemCatalogsResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_officetels_building_v1(
        self,
        parameter: ZigbangItemsOfficetelsBuildingV1RequestParameterModel
    ) -> ZigbangItemsOfficetelsBuildingV1ResponseModel:
        """List officetel pins in a building via `GET /house/property/v1/items/officetels/{buildingId}`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 없는 건물이면 400
        ("오피스텔 건물을 찾을 수 없습니다") 이다.

        Args:
            parameter: `building_id` (경로) plus `sales_types`, 가격·관리비(만원),
                구조·면적·층·욕실·옵션·시설 조건 (지도 목록과 같은 필터).

        Returns:
            ZigbangItemsOfficetelsBuildingV1ResponseModel: 건물 안 매물 핀과 건물 정보.
        """
        response = self._client.get(
            url=self.items_officetels_building_v1_endpoint.format(building_id=parameter.building_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsOfficetelsBuildingV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_officetels_building_v1(
        self,
        parameter: ZigbangItemsOfficetelsBuildingV1RequestParameterModel
    ) -> ZigbangItemsOfficetelsBuildingV1ResponseModel:
        """Async variant of `run_request_items_officetels_building_v1`."""
        response = await self._async_client.get(
            url=self.items_officetels_building_v1_endpoint.format(building_id=parameter.building_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsOfficetelsBuildingV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_store_article_stores_v2(
        self,
        payload: ZigbangStoreArticleStoresV2RequestPayloadModel
    ) -> ZigbangStoreArticleStoresV2ResponseModel:
        """List store locations in a geohash tile via `POST /v2/store/article/stores`.

        POST 지만 조회 전용이라 idempotent 재시도를 쓴다. Same retry behaviour as
        `run_request_items_onerooms_v1`. 응답 최상위가 배열이라 `sections` 로 감싸 검증한다.

        Args:
            payload: `geohash` plus 거래 유형, 1층 여부, 업종, 면적(㎡) 조건.

        Returns:
            ZigbangStoreArticleStoresV2ResponseModel: 위치 묶음(조건에 맞는 상가, 공실).
        """
        response = self._client.post(
            url=self.store_article_stores_v2_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangStoreArticleStoresV2ResponseModel.model_validate({'sections': response.json()})

    @zigbang_retry
    async def arun_request_store_article_stores_v2(
        self,
        payload: ZigbangStoreArticleStoresV2RequestPayloadModel
    ) -> ZigbangStoreArticleStoresV2ResponseModel:
        """Async variant of `run_request_store_article_stores_v2`."""
        response = await self._async_client.post(
            url=self.store_article_stores_v2_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangStoreArticleStoresV2ResponseModel.model_validate({'sections': response.json()})

    @zigbang_retry
    def run_request_store_article_stores_list_v2(
        self,
        payload: ZigbangStoreArticleStoresListV2RequestPayloadModel
    ) -> ZigbangStoreArticleStoresListV2ResponseModel:
        """Fetch store summaries in a batch via `POST /v2/store/article/stores/list`.

        POST 지만 조회 전용이라 idempotent 재시도를 쓴다. Same retry behaviour as
        `run_request_items_onerooms_v1`. 응답 최상위가 배열이라 `items` 로 감싸 검증한다.

        Args:
            payload: `item_ids`.

        Returns:
            ZigbangStoreArticleStoresListV2ResponseModel: 가격·면적·층·업종이 담긴 요약.
        """
        response = self._client.post(
            url=self.store_article_stores_list_v2_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangStoreArticleStoresListV2ResponseModel.model_validate({'items': response.json()})

    @zigbang_retry
    async def arun_request_store_article_stores_list_v2(
        self,
        payload: ZigbangStoreArticleStoresListV2RequestPayloadModel
    ) -> ZigbangStoreArticleStoresListV2ResponseModel:
        """Async variant of `run_request_store_article_stores_list_v2`."""
        response = await self._async_client.post(
            url=self.store_article_stores_list_v2_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangStoreArticleStoresListV2ResponseModel.model_validate({'items': response.json()})

    @zigbang_retry
    def run_request_store_article_store_v2(
        self,
        parameter: ZigbangStoreArticleStoreV2RequestParameterModel
    ) -> ZigbangStoreArticleStoreV2ResponseModel:
        """Fetch a store detail via `GET /v2/store/article/stores/{itemId}`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 없는 매물이면 404 다.

        Args:
            parameter: `item_id` (경로).

        Returns:
            ZigbangStoreArticleStoreV2ResponseModel: 상가 상세와 인근 지하철역.
        """
        response = self._client.get(
            url=self.store_article_store_v2_endpoint.format(item_id=parameter.item_id)
        )
        raise_for_status(response=response)
        return ZigbangStoreArticleStoreV2ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_store_article_store_v2(
        self,
        parameter: ZigbangStoreArticleStoreV2RequestParameterModel
    ) -> ZigbangStoreArticleStoreV2ResponseModel:
        """Async variant of `run_request_store_article_store_v2`."""
        response = await self._async_client.get(
            url=self.store_article_store_v2_endpoint.format(item_id=parameter.item_id)
        )
        raise_for_status(response=response)
        return ZigbangStoreArticleStoreV2ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_guest_items_search(
        self,
        parameter: ZigbangGuestItemsSearchRequestParameterModel
    ) -> ZigbangGuestItemsSearchResponseModel:
        """Search short-term stay IDs via `GET stay-apis.zigbang.com/guest/items/search`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 잘못된 필터 값은 400
        `VALIDATION_ERROR` 다 (허용 값은 요청 모델의 Literal). 요약은 by-ids 로 따로 받는다.

        Args:
            parameter: 검색 유형(`type`)과 지역(`local1~3`) 또는 역·학교 좌표(`lat`·`lng`),
                정렬, 그리고 지도 검색과 같은 요금·옵션·입주·퇴거일 조건.

        Returns:
            ZigbangGuestItemsSearchResponseModel: 조건에 맞는 매물 ID 목록 (노출 중인 매물만).
        """
        response = self._client.get(
            url=self.stay_base_url + self.guest_items_search_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsSearchResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_guest_items_search(
        self,
        parameter: ZigbangGuestItemsSearchRequestParameterModel
    ) -> ZigbangGuestItemsSearchResponseModel:
        """Async variant of `run_request_guest_items_search`."""
        response = await self._async_client.get(
            url=self.stay_base_url + self.guest_items_search_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsSearchResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_guest_items_markers(
        self,
        parameter: ZigbangGuestItemsMarkersRequestParameterModel
    ) -> ZigbangGuestItemsMarkersResponseModel:
        """List short-term stay pins via `GET stay-apis.zigbang.com/guest/items/markers`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 잘못된 필터 값은 400
        `VALIDATION_ERROR` 다 (허용 값은 요청 모델의 Literal).

        Args:
            parameter: `geohash` plus 주당 요금(만원), 방 수, 방 종류, 면적, 할인, 옵션,
                층, 입주·퇴거일 조건.

        Returns:
            ZigbangGuestItemsMarkersResponseModel: 칸 안의 매물 핀(ID·좌표·주당 요금).
        """
        response = self._client.get(
            url=self.stay_base_url + self.guest_items_markers_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsMarkersResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_guest_items_markers(
        self,
        parameter: ZigbangGuestItemsMarkersRequestParameterModel
    ) -> ZigbangGuestItemsMarkersResponseModel:
        """Async variant of `run_request_guest_items_markers`."""
        response = await self._async_client.get(
            url=self.stay_base_url + self.guest_items_markers_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsMarkersResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_guest_items_by_ids(
        self,
        parameter: ZigbangGuestItemsByIdsRequestParameterModel
    ) -> ZigbangGuestItemsByIdsResponseModel:
        """Fetch short-term stay summaries via `GET stay-apis.zigbang.com/guest/items/by-ids`.

        Same retry behaviour as `run_request_items_onerooms_v1`.

        Args:
            parameter: `item_ids` (같은 키 반복, 최대 100).

        Returns:
            ZigbangGuestItemsByIdsResponseModel: 주당 요금(원)·면적·층·할인이 담긴 요약.
        """
        response = self._client.get(
            url=self.stay_base_url + self.guest_items_by_ids_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsByIdsResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_guest_items_by_ids(
        self,
        parameter: ZigbangGuestItemsByIdsRequestParameterModel
    ) -> ZigbangGuestItemsByIdsResponseModel:
        """Async variant of `run_request_guest_items_by_ids`."""
        response = await self._async_client.get(
            url=self.stay_base_url + self.guest_items_by_ids_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsByIdsResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_guest_items(
        self,
        parameter: ZigbangGuestItemsRequestParameterModel
    ) -> ZigbangGuestItemsResponseModel:
        """Fetch a short-term stay detail via `GET stay-apis.zigbang.com/guest/items/{itemId}`.

        Same retry behaviour as `run_request_items_onerooms_v1`. 없는 매물이면 404 다.

        Args:
            parameter: `item_id` (경로).

        Returns:
            ZigbangGuestItemsResponseModel: 단기임대 매물 상세 (금액은 원 단위).
        """
        response = self._client.get(
            url=self.stay_base_url + self.guest_items_endpoint.format(item_id=parameter.item_id)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_guest_items(
        self,
        parameter: ZigbangGuestItemsRequestParameterModel
    ) -> ZigbangGuestItemsResponseModel:
        """Async variant of `run_request_guest_items`."""
        response = await self._async_client.get(
            url=self.stay_base_url + self.guest_items_endpoint.format(item_id=parameter.item_id)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_guest_items_price_calculation(
        self,
        payload: ZigbangGuestItemsPriceCalculationRequestPayloadModel
    ) -> ZigbangGuestItemsPriceCalculationResponseModel:
        """Calculate a short-term stay price via `POST stay-apis.zigbang.com/guest/items/{itemId}/price-calculation`.

        POST 지만 계산만 하는 조회라(예약을 만들지 않는다) idempotent 재시도를 쓴다. Same retry behaviour as
        `run_request_items_onerooms_v1`. 그 날짜에 예약이 비어 있는지는 보지 않는다. 지난 입주일이나
        계약 기간을 벗어난 기간은 400 이다.

        Args:
            payload: `item_id` (경로) plus 입주·퇴거일과 반려동물 동반 여부.

        Returns:
            ZigbangGuestItemsPriceCalculationResponseModel: 기간 임대료·관리비·할인·이용료·보증금과 총액 (원).
        """
        response = self._client.post(
            url=self.stay_base_url + self.guest_items_price_calculation_endpoint.format(item_id=payload.item_id),
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsPriceCalculationResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_guest_items_price_calculation(
        self,
        payload: ZigbangGuestItemsPriceCalculationRequestPayloadModel
    ) -> ZigbangGuestItemsPriceCalculationResponseModel:
        """Async variant of `run_request_guest_items_price_calculation`."""
        response = await self._async_client.post(
            url=self.stay_base_url + self.guest_items_price_calculation_endpoint.format(item_id=payload.item_id),
            json=payload.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangGuestItemsPriceCalculationResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_subways_onerooms_v1(
        self,
        parameter: ZigbangItemsSubwaysOneroomsV1RequestParameterModel
    ) -> ZigbangItemsSubwaysOneroomsV1ResponseModel:
        """List one-room pins around a station via `GET /house/property/v1/items/subways/{subwayId}/onerooms`.

        Same retry behaviour as `run_request_items_onerooms_v1`.

        Args:
            parameter: 경로의 `subway_id`, km 단위 `radius`, 선택 `sales_types` (전세/월세/단기) 와
                지도 목록과 같은 만원 단위 가격·관리비·상세 필터.

        Returns:
            ZigbangItemsSubwaysOneroomsV1ResponseModel: 역 반경 안의 매물 핀(ID·좌표). 지도 목록과
                같은 응답 모양이다.
        """
        response = self._client.get(
            url=self.items_subways_onerooms_v1_endpoint.format(subway_id=parameter.subway_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsSubwaysOneroomsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_subways_onerooms_v1(
        self,
        parameter: ZigbangItemsSubwaysOneroomsV1RequestParameterModel
    ) -> ZigbangItemsSubwaysOneroomsV1ResponseModel:
        """Async variant of `run_request_items_subways_onerooms_v1`."""
        response = await self._async_client.get(
            url=self.items_subways_onerooms_v1_endpoint.format(subway_id=parameter.subway_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsSubwaysOneroomsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_subways_officetels_v1(
        self,
        parameter: ZigbangItemsSubwaysOfficetelsV1RequestParameterModel
    ) -> ZigbangItemsSubwaysOfficetelsV1ResponseModel:
        """List officetel pins around a station via `GET /house/property/v1/items/subways/{subwayId}/officetels`.

        Same retry behaviour as `run_request_items_onerooms_v1`.

        Args:
            parameter: 경로의 `subway_id`, km 단위 `radius`, 선택 `sales_types` (전세/월세/매매/단기) 와
                지도 목록과 같은 만원 단위 가격·관리비·상세 필터.

        Returns:
            ZigbangItemsSubwaysOfficetelsV1ResponseModel: 역 반경 안의 매물 핀(ID·좌표). 지도 목록과
                같은 응답 모양이다.
        """
        response = self._client.get(
            url=self.items_subways_officetels_v1_endpoint.format(subway_id=parameter.subway_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsSubwaysOfficetelsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_subways_officetels_v1(
        self,
        parameter: ZigbangItemsSubwaysOfficetelsV1RequestParameterModel
    ) -> ZigbangItemsSubwaysOfficetelsV1ResponseModel:
        """Async variant of `run_request_items_subways_officetels_v1`."""
        response = await self._async_client.get(
            url=self.items_subways_officetels_v1_endpoint.format(subway_id=parameter.subway_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsSubwaysOfficetelsV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    def run_request_items_subways_villas_v1(
        self,
        parameter: ZigbangItemsSubwaysVillasV1RequestParameterModel
    ) -> ZigbangItemsSubwaysVillasV1ResponseModel:
        """List villa pins around a station via `GET /house/property/v1/items/subways/{subwayId}/villas`.

        Same retry behaviour as `run_request_items_onerooms_v1`.

        Args:
            parameter: 경로의 `subway_id`, km 단위 `radius`, 선택 `sales_types` (전세/월세/매매/단기) 와
                지도 목록과 같은 만원 단위 가격·관리비·상세 필터.

        Returns:
            ZigbangItemsSubwaysVillasV1ResponseModel: 역 반경 안의 매물 핀(ID·좌표). 지도 목록과
                같은 응답 모양이다.
        """
        response = self._client.get(
            url=self.items_subways_villas_v1_endpoint.format(subway_id=parameter.subway_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsSubwaysVillasV1ResponseModel.model_validate(response.json())

    @zigbang_retry
    async def arun_request_items_subways_villas_v1(
        self,
        parameter: ZigbangItemsSubwaysVillasV1RequestParameterModel
    ) -> ZigbangItemsSubwaysVillasV1ResponseModel:
        """Async variant of `run_request_items_subways_villas_v1`."""
        response = await self._async_client.get(
            url=self.items_subways_villas_v1_endpoint.format(subway_id=parameter.subway_id),
            params=parameter.model_dump(by_alias=True, exclude_none=True)
        )
        raise_for_status(response=response)
        return ZigbangItemsSubwaysVillasV1ResponseModel.model_validate(response.json())

