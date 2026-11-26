from jibsa.core.listing import with_notes

from .api.client import NaverClient
from .service.common import NaverListingsResult
from .service.complex import NaverComplexSummary
from .service.complex import get_complex as _get_complex
from .service.listing import NaverListingDetail
from .service.listing import get_listing as _get_listing
from .service.listing import list_complex_articles as _list_complex_articles
from .service.market_price import NaverMarketPriceHistory
from .service.market_price import get_market_price_history as _get_market_price_history
from .service.real_price import NaverRealPriceResult
from .service.real_price import get_real_prices as _get_real_prices
from .service.redevelopment import (
    NaverRedevelopmentAreasResult,
    NaverRedevelopmentDetail,
)
from .service.redevelopment import get_redevelopment as _get_redevelopment
from .service.redevelopment import list_redevelopment_areas as _list_redevelopment_areas
from .service.redevelopment import (
    list_redevelopment_articles as _list_redevelopment_articles,
)
from .service.region import (
    NaverRegion,
    NaverRegionList,
)
from .service.region import list_regions as _list_regions
from .service.region import resolve_complex_number as _resolve_complex_number
from .service.school import NaverSchoolDetail
from .service.school import get_school as _get_school
from .service.search import search_area as _search_area
from .service.trend import NaverDistrictTrend
from .service.trend import get_district_trend as _get_district_trend


# 파이썬에서 부르는 정문 함수는 with_notes 로 감싸 결과 notes 에 못 읽은 날짜·뺀 빈 항목 안내를 넣는다.
# CLI 는 service 모듈의 감싸지 않은 함수를 쓴다 (core.listing.with_notes)
get_complex = with_notes('naver')(_get_complex)
get_listing = with_notes('naver')(_get_listing)
list_complex_articles = with_notes('naver')(_list_complex_articles)
get_market_price_history = with_notes('naver')(_get_market_price_history)
get_real_prices = with_notes('naver')(_get_real_prices)
get_redevelopment = with_notes('naver')(_get_redevelopment)
list_redevelopment_areas = with_notes('naver')(_list_redevelopment_areas)
list_redevelopment_articles = with_notes('naver')(_list_redevelopment_articles)
list_regions = with_notes('naver')(_list_regions)
resolve_complex_number = with_notes('naver')(_resolve_complex_number)
get_school = with_notes('naver')(_get_school)
search_area = with_notes('naver')(_search_area)
get_district_trend = with_notes('naver')(_get_district_trend)
