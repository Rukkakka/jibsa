from jibsa.core.listing import with_notes

from .api.client import DaangnClient
from .service.common import DaangnRegion
from .service.commute import DaangnCommuteResult
from .service.commute import search_commute as _search_commute
from .service.complex import (
    DaangnBoundsComplexesResult,
    DaangnComplex,
    DaangnComplexCandidate,
    DaangnComplexListingsResult,
    DaangnRegionComplexesResult,
)
from .service.complex import get_complex as _get_complex
from .service.complex import list_bounds_complexes as _list_bounds_complexes
from .service.complex import list_complex_listings as _list_complex_listings
from .service.complex import list_region_complexes as _list_region_complexes
from .service.complex import search_complexes as _search_complexes
from .service.listing import DaangnListingDetail
from .service.listing import get_listing as _get_listing
from .service.real_price import (
    DaangnListingRealPriceResult,
    DaangnPriceTrendResult,
    DaangnRealPriceResult,
    DaangnRegionRealPriceResult,
)
from .service.real_price import get_listing_real_prices as _get_listing_real_prices
from .service.real_price import get_price_trend as _get_price_trend
from .service.real_price import get_real_prices as _get_real_prices
from .service.real_price import get_region_real_prices as _get_region_real_prices
from .service.region import (
    DaangnAddress,
    DaangnArea,
    DaangnStation,
    DaangnUniversity,
)
from .service.region import find_address as _find_address
from .service.region import find_station as _find_station
from .service.region import find_university as _find_university
from .service.region import resolve_area as _resolve_area
from .service.region import search_areas as _search_areas
from .service.review import DaangnRegionReviews
from .service.review import get_region_reviews as _get_region_reviews
from .service.school import DaangnSchoolResult
from .service.school import get_school as _get_school
from .service.search import (
    DaangnDongSearchResult,
    DaangnMapSearchResult,
    DaangnStationSearchResult,
    DaangnUniversitySearchResult,
)
from .service.search import search_dong as _search_dong
from .service.search import search_map_area as _search_map_area
from .service.search import search_station as _search_station
from .service.search import search_university as _search_university


# 파이썬에서 부르는 정문 함수는 with_notes 로 감싸 결과 notes 에 못 읽은 날짜·뺀 빈 항목 안내를 넣는다.
# CLI 는 service 모듈의 감싸지 않은 함수를 쓴다 (core.listing.with_notes)
search_commute = with_notes('daangn')(_search_commute)
get_complex = with_notes('daangn')(_get_complex)
list_bounds_complexes = with_notes('daangn')(_list_bounds_complexes)
list_complex_listings = with_notes('daangn')(_list_complex_listings)
list_region_complexes = with_notes('daangn')(_list_region_complexes)
search_complexes = with_notes('daangn')(_search_complexes)
get_listing = with_notes('daangn')(_get_listing)
get_listing_real_prices = with_notes('daangn')(_get_listing_real_prices)
get_price_trend = with_notes('daangn')(_get_price_trend)
get_real_prices = with_notes('daangn')(_get_real_prices)
get_region_real_prices = with_notes('daangn')(_get_region_real_prices)
find_address = with_notes('daangn')(_find_address)
find_station = with_notes('daangn')(_find_station)
find_university = with_notes('daangn')(_find_university)
resolve_area = with_notes('daangn')(_resolve_area)
search_areas = with_notes('daangn')(_search_areas)
get_region_reviews = with_notes('daangn')(_get_region_reviews)
get_school = with_notes('daangn')(_get_school)
search_dong = with_notes('daangn')(_search_dong)
search_map_area = with_notes('daangn')(_search_map_area)
search_station = with_notes('daangn')(_search_station)
search_university = with_notes('daangn')(_search_university)
