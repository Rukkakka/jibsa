"""동네 후기 요약 (region-reviews)."""

import logging

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.review import (
    DaangnLivedReviewsByRegionRequestPayloadModel,
    DaangnMapReviewsRequestParameterModel,
    DaangnRegionByOriginalRegionIdRequestPayloadModel,
)
from jibsa.providers.daangn.service.common import (
    COMPLEX_TYPE_LABELS,
    OPTIONAL_LOOKUP_ERRORS,
    partial_failure_note,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    DaangnRealsaleRegion,
    resolve_realsale_region,
)

from typing import Annotated


logger = logging.getLogger(__name__)
# 당근 동네 요약은 후기를 이 수까지만 센다
REVIEW_SUMMARY_CAP: int = 60


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
        Field(description='동네 후기 수 (당근 동네 요약에 쓰인 수, 최대 60 이라 60 이면 60개 이상). 동만 있고 구는 당근이 주지 않아 null')
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
    city: str | None = None,
    top: int = 10,
) -> DaangnRegionReviews:
    """동·구의 거주 후기가 있는지, 몇 개인지, 후기가 많은 단지를 알려 준다. 후기 내용은 담지 않는다.

    동은 동네 요약(`regionByOriginalRegionId`)의 후기 수를, 구는 후기 목록(`livedReviewsByRegion`)으로
    후기가 있는지만 본다. 후기 많은 단지는 구의 후기 페이지에서 받는다 (구가 없는 시는 없다).

    후기 수는 덤 정보라 동네 요약이 실패하면(쿼리 변경·서버 오류) 수만 비우고 `notes` 로 알린다. 후기가
    있는지는 후기 목록으로 다시 본다. 요청 제한은 그 후기 목록도 같은 제한에 걸리므로 바로 올린다.

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        RateLimitedError: 요청 제한에 걸렸을 때.
        JibsaError: 후기 목록이 실패하면 UPSTREAM_ERROR.
    """
    region, notes = resolve_realsale_region(client, query, city=city)

    review_count = None
    if region.level == '동':
        try:
            response = client.run_request_region_by_original_region_id(
                DaangnRegionByOriginalRegionIdRequestPayloadModel(region_id=region.region_id)
            )
            summary = unwrap_graphql(
                response, response.data.region_by_original_region_id if response.data else None, '동네 요약'
            )
        except RateLimitedError:
            raise
        except OPTIONAL_LOOKUP_ERRORS as exc:
            logger.warning('daangn region summary failed (%s); continuing without review count', exc)
            notes.append(partial_failure_note(exc, '동네 요약', '동네 후기 수를'))
        else:
            if summary.lived_review_summary is not None:
                review_count = summary.lived_review_summary.source_review_count
    has_reviews = bool(review_count)
    if not has_reviews:
        reviews_response = client.run_request_lived_reviews_by_region(
            DaangnLivedReviewsByRegionRequestPayloadModel(region_id=region.region_id)
        )
        connection = unwrap_graphql(
            reviews_response, reviews_response.data.lived_reviews_by_region if reviews_response.data else None, '동네 후기'
        )
        has_reviews = bool(connection.edges)

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

    if review_count is not None and review_count >= REVIEW_SUMMARY_CAP:
        notes.append(f'동네 후기는 {REVIEW_SUMMARY_CAP}개 이상입니다 (당근이 {REVIEW_SUMMARY_CAP}개까지만 셉니다)')
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
