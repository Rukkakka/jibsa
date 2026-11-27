from jibsa.core.listing import with_notes

from .api.client import DaangnClient
from .service.common.models import DaangnRegion
from .service.commute.commute import search_commute as _search_commute
from .service.commute.models import DaangnCommuteResult
from .service.complex.common import search_complexes as _search_complexes
from .service.complex.detail import get_complex as _get_complex
from .service.complex.listings import list_complex_listings as _list_complex_listings
from .service.complex.models.common import DaangnComplexCandidate
from .service.complex.models.detail import DaangnComplex
from .service.complex.models.listings import DaangnComplexListingsResult
from .service.complex.models.search import (
    DaangnBoundsComplexesResult,
    DaangnRegionComplexesResult,
)
from .service.complex.search import list_bounds_complexes as _list_bounds_complexes
from .service.complex.search import list_region_complexes as _list_region_complexes
from .service.listing.listing import get_listing as _get_listing
from .service.listing.models import DaangnListingDetail
from .service.real_price.complex import (
    get_listing_real_prices as _get_listing_real_prices,
)
from .service.real_price.complex import get_real_prices as _get_real_prices
from .service.real_price.models.complex import (
    DaangnListingRealPriceResult,
    DaangnRealPriceResult,
)
from .service.real_price.models.region import DaangnRegionRealPriceResult
from .service.real_price.models.trend import DaangnPriceTrendResult
from .service.real_price.region import (
    get_region_real_prices as _get_region_real_prices,
)
from .service.real_price.trend import get_price_trend as _get_price_trend
from .service.region.address import find_address as _find_address
from .service.region.area import resolve_area as _resolve_area
from .service.region.area import search_areas as _search_areas
from .service.region.models.address import DaangnAddress
from .service.region.models.area import DaangnArea
from .service.region.models.station import DaangnStation
from .service.region.models.university import DaangnUniversity
from .service.region.station import find_station as _find_station
from .service.region.university import find_university as _find_university
from .service.review.models import DaangnRegionReviews
from .service.review.review import get_region_reviews as _get_region_reviews
from .service.school.models.school import DaangnSchoolResult
from .service.school.school import get_school as _get_school
from .service.search.around import search_station as _search_station
from .service.search.around import search_university as _search_university
from .service.search.map import search_dong as _search_dong
from .service.search.map import search_map_area as _search_map_area
from .service.search.models.around import (
    DaangnStationSearchResult,
    DaangnUniversitySearchResult,
)
from .service.search.models.map import (
    DaangnDongSearchResult,
    DaangnMapSearchResult,
)


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
