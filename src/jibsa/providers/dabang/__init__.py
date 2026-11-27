from jibsa.core.listing import with_notes

from .api.client import DabangClient
from .service.common.models import (
    DabangListing,
    DabangPlace,
)
from .service.listing.detail import get_listing as _get_listing
from .service.listing.models import (
    DabangListingDetail,
    DabangSearchResult,
)
from .service.listing.search import search_listings as _search_listings
from .service.region.region import resolve_places as _resolve_places


# 파이썬에서 부르는 정문 함수는 with_notes 로 감싸 결과 notes 에 못 읽은 날짜·뺀 빈 항목 안내를 넣는다.
# CLI 는 service 모듈의 감싸지 않은 함수를 쓴다 (core.listing.with_notes)
get_listing = with_notes('dabang')(_get_listing)
search_listings = with_notes('dabang')(_search_listings)
resolve_places = with_notes('dabang')(_resolve_places)
