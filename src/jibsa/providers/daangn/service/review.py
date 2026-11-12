"""동네 후기 요약 (region-reviews)."""

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.review import (
    DaangnLivedReviewsByRegionRequestPayloadModel,
    DaangnMapReviewsRequestParameterModel,
)
from jibsa.providers.daangn.service.common import (
    COMPLEX_TYPE_LABELS,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    DaangnRealsaleRegion,
    resolve_realsale_region,
)

from typing import Annotated


# 후기 많은 단지 수. 당근 구 후기 페이지가 20곳을 준다 (reviewsDistrictQuery first:20)
TOP_COMPLEXES_MAX: int = 20


def map_url(*names: str, suffix: str = '') -> str:
    """지도 페이지 URL. 구가 없는 시(세종)는 구 세그먼트를 뺀다.

    LLM 과 사람이 읽도록 한글은 그대로 두고 공백만 인코딩한다 (브라우저는 그대로 연다).
    """
    path = '/'.join(name.replace(' ', '%20') for name in names if name)
    return f'https://realty.daangn.com/map/{path}{suffix}'


class DaangnReviewComplex(BaseModel):
    """거주 후기가 많은 단지."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘기면 그 단지의 후기 수와 단지 페이지가 나온다)')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    property_type: Annotated[
        str | None,
        Field(description='단지 유형')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수')
    ] = None


class DaangnRegionReviews(BaseModel):
    """동네 거주 후기 안내. 후기 본문과 당근이 만든 요약 글은 담지 않는다 (url 의 원 사이트에서 본다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    has_reviews: Annotated[
        bool,
        Field(description='동네 후기가 있는지')
    ]
    review_count: Annotated[
        int | None,
        Field(description='동네 후기 수 (당근 웹 모바일 후기 화면의 "후기 N개"와 같은 실제 수). 동·구 모두 있다. 당근이 주지 않으면 null')
    ] = None
    top_complexes: Annotated[
        list[DaangnReviewComplex],
        Field(description='그 구에서 거주 후기가 많은 단지 (동이면 동이 속한 구 기준)')
    ] = []
    url: Annotated[
        str,
        Field(description='당근 동네 후기 페이지 (구가 없는 시는 동 지도 페이지)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='후기를 원 사이트에서 보라는 안내. CLI 가 결과 위에 붙인다')
    ] = []


def get_region_reviews(
    client: DaangnClient,
    query: str,
    *,
    top: int = TOP_COMPLEXES_MAX,
) -> DaangnRegionReviews:
    """동·구의 거주 후기가 있는지, 몇 개인지, 후기가 많은 단지를 알려 준다. 후기 내용은 담지 않는다.

    후기 수는 당근 웹 후기 목록(`RegionLivedReviewListPanelQuery`)이 함께 받는 지역의 후기 수(`reviewRegion.livedReviewCount`)다.
    웹은 이 수를 모바일 화면의 '당근 앱에서 후기 N개 더 보기' 로 보여 준다. 예전에는 동네 요약(`regionByOriginalRegionId`)의
    요약에 쓰인 후기 수를 써서 60 에서 잘리고 구는 null 이었다 (2026-11-12 실측: 역삼동 1563·강남구 7132, #215). 후기 많은 단지는
    구의 후기 페이지에서 받는다 (구가 없는 시는 없다).

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        RateLimitedError: 요청 제한에 걸렸을 때.
        JibsaError: 후기 목록이 실패하면 UPSTREAM_ERROR.
    """
    region, notes = resolve_realsale_region(client, query)

    reviews_response = client.run_request_lived_reviews_by_region(
        DaangnLivedReviewsByRegionRequestPayloadModel(region_id=region.region_id)
    )
    connection = unwrap_graphql(
        reviews_response, reviews_response.data.lived_reviews_by_region if reviews_response.data else None, '동네 후기'
    )
    review_region = reviews_response.data.review_region if reviews_response.data else None
    review_count = review_region.lived_review_count if review_region else None
    has_reviews = bool(review_count) or bool(connection.edges)

    top_complexes: list[DaangnReviewComplex] = []
    if region.name1 and region.name2:
        url = map_url(region.name1, region.name2, suffix='/reviews')
        try:
            page = client.run_request_map_reviews(
                DaangnMapReviewsRequestParameterModel(name1=region.name1, name2=region.name2)
            )
        except HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            url = map_url(region.name1, region.name2, region.name3)
        else:
            top_complexes = [
                DaangnReviewComplex(
                    complex_id=item.original_id,
                    name=item.name,
                    property_type=COMPLEX_TYPE_LABELS.get(item.type or '', item.type),
                    review_count=item.lived_review_count,
                )
                for item in page.complexes
                if item.lived_review_count
            ][:top]
    else:
        url = map_url(region.name1, region.name2, region.name3)

    if top_complexes and region.level == '동':
        # 후기 많은 단지는 구의 후기 페이지에서 받아 구 전체 순위다. 알리지 않으니 동의 단지로 읽었다 (2026-11-11 LLM 사용
        # 시험·실측: 잠실동·문정동·가락동 모두 헬리오시티·송파파크하비오푸르지오·파크리오)
        notes.append(f'후기 많은 단지(top_complexes)는 {region.name2} 전체 기준이라 {region.name3} 밖 단지도 들어 있습니다')
    if has_reviews or top_complexes:
        notes.append(f'후기 내용은 당근 동네 후기 페이지({url})에서 확인하세요. 단지 후기는 daangn complex 의 url 에서 봅니다')
    else:
        notes.append('이 지역에는 당근 동네 후기가 아직 없습니다')
    return DaangnRegionReviews(
        region=region,
        has_reviews=has_reviews,
        review_count=review_count,
        top_complexes=top_complexes,
        url=url,
        notes=notes,
    )
