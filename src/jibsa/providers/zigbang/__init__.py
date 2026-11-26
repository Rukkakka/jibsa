from jibsa.core.listing import with_notes

from .api.client import ZigbangClient
from .service.common.base import (
    ZigbangListingDetail,
    ZigbangRegion,
)
from .service.listing import get_listing as _get_listing
from .service.region import search_regions as _search_regions
from .service.room.search import ZigbangSearchResult
from .service.room.search import search_listings as _search_listings


# 파이썬에서 부르는 정문 함수는 with_notes 로 감싸 결과 notes 에 못 읽은 날짜·뺀 빈 항목 안내를 넣는다.
# CLI 는 service 모듈의 감싸지 않은 함수를 쓴다 (core.listing.with_notes)
get_listing = with_notes('zigbang')(_get_listing)
search_regions = with_notes('zigbang')(_search_regions)
search_listings = with_notes('zigbang')(_search_listings)
