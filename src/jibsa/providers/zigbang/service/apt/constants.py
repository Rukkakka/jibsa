"""직방 아파트 매물 검색·상세·묶음의 상수: 거래 유형·쪽 크기·동 geohash 정밀도·묶음 ID 형식."""

import re

from jibsa.core.listing import TradeType
from jibsa.providers.zigbang.service.common.constants import TRADE_BY_APT_TRAN_TYPE


APT_TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세')
# 한 번에 받는 아파트 매물 수. 지역 목록(locals)은 20 을 넘으면 400 이고, 단지 목록(danjis)은 50 도 같은 순서·내용으로
# 준다 (2026-10-10 실측: 헬리오시티 120건 20건씩 6회 = 50건씩 3회, 요청 모델 상한이 50)
LOCAL_CATALOG_PAGE_SIZE: int = 20
# 웹 묶음 화면이 한 번에 받는 매물 수 (`useItemCatalogDetail`, 2026-11-15 번들)
CATALOG_PAGE_SIZE: int = 20

# 좌표가 속한 동을 물을 geohash 정밀도. 칸이 크면 옆 동이 잡힌다 (2026-11-15 실측: 강남역은 정밀도 5 에 논현동, 6 에 역삼동,
# 7·8 에 서초동, 9·10·12 에 역 주소와 같은 역삼동. 역삼동 한가운데는 8~12 모두 역삼동)
APT_DONG_GEOHASH_PRECISION: int = 10

# 같은 호·거래 유형의 아파트 매물 묶음 ID (`<호 ID>-<거래 유형 코드>`, 예: 8260358-trade). 묶음 화면 API 가 이 둘을 받는다
CATALOG_ID_PATTERN: re.Pattern[str] = re.compile(rf"^([1-9]\d*)-({'|'.join(TRADE_BY_APT_TRAN_TYPE)})$")
# 묶음 ID 형식이 틀렸을 때 안내 (`parse_catalog_id` 의 INVALID_ARGUMENT hint)
CATALOG_ID_HINT: str = 'search listings apt·search listings --complex <apt-…> 결과의 catalog_id 를 그대로 주세요 (예: 8260358-trade)'
