"""역 둘레 평균 매물가 (station-prices)."""


from jibsa.core.errors import JibsaError
from jibsa.core.geo import box_around
from jibsa.core.listing import (
    AmountSet,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import DabangOneTwoFiltersModel
from jibsa.providers.dabang.api.request.nearby.station import (
    DabangMarkersCategoryV5RequestParameterModel,
)
from jibsa.providers.dabang.service.common.functions import (
    BUILDING_LABEL_BY_CATEGORY,
    bbox_of,
    manwon_from_text,
)
from jibsa.providers.dabang.service.common.models import DabangPlace
from jibsa.providers.dabang.service.nearby.models import (
    DabangStationPrice,
    DabangStationPrices,
)


ROOM_LABELS: dict[str, str] = {'ONE_ROOM': '원룸', 'TWO_ROOM': '투룸'}

# 역 둘레 평균 매물가를 받으려고 역을 덮는 지도 범위 (km). 확대 수준 16 이면 범위 안 역 표시에 평균이 붙는다
STATION_BOX_KM: float = 0.3


def get_station_prices(client: DabangClient, place: DabangPlace) -> DabangStationPrices:
    """역 둘레 평균 매물가 (원룸·투룸 지도 집계 1회). 다방 화면의 '평균 매물가' 로, 실거래가가 아니라 지금 올라온 매물 가격의
    평균이다. 다방 원룸·투룸 목록(방 1~2개)으로 셈해 쓰리룸 이상은 없다.

    Raises:
        JibsaError: 역이 아니거나 (INVALID_ARGUMENT), 다방이 그 역의 평균을 주지 않을 때 (NOT_FOUND).
    """
    if place.kind != 'station' or place.place_id is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'역 이름이 아닙니다: {place.name}',
            hint="지하철역 이름(예: '강남역')을 주세요",
        )
    result = client.run_request_markers_category_v5(DabangMarkersCategoryV5RequestParameterModel(
        category='one-two',
        filters=DabangOneTwoFiltersModel(),
        bbox=bbox_of(*box_around(place.lat, place.lng, STATION_BOX_KM)),
    )).result
    station = next((item for item in (result.subway_list if result else []) if item.id == place.place_id), None)
    if station is None or station.average_price_list is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'다방이 {place.name}의 평균 매물가를 주지 않았습니다',
            hint='역 둘레 매물은 jibsa dabang search listings room <역> 으로 직접 보세요',
        )
    prices = []
    for item in station.average_price_list:
        deposit, _, rent = (item.monthly_rent or '').partition('/')
        monthly_deposit = manwon_from_text(deposit) if rent else None
        monthly_rent = manwon_from_text(rent) if rent else None
        prices.append(DabangStationPrice(
            property_type=BUILDING_LABEL_BY_CATEGORY.get(item.building_category or '', item.building_category or ''),
            room_type=ROOM_LABELS.get(item.room_type or '', item.room_type or ''),
            asking_averages={
                'jeonse': None if (lease := manwon_from_text(item.lease)) is None else AmountSet(deposit_manwon=lease),
                'wolse': None if monthly_deposit is None and monthly_rent is None else AmountSet(
                    deposit_manwon=monthly_deposit,
                    rent_manwon=monthly_rent,
                ),
            },
        ))
    return DabangStationPrices(
        station_name=station.name,
        radius_m=station.radius,
        basis="다방 '평균 매물가': 역 반경 안에 지금 올라온 원룸·투룸 목록 매물(방 1~2개)의 평균 (실거래가 아님)",
        prices=prices,
    )
