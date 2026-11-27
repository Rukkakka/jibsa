"""다방 지도 범위 모델 만들기."""
from jibsa.providers.dabang.api.request.common import (
    DabangBboxModel,
    DabangPointModel,
)


def bbox_of(south: float, north: float, west: float, east: float) -> DabangBboxModel:
    """(남, 북, 서, 동) 을 다방 지도 범위로."""
    return DabangBboxModel(sw=DabangPointModel(lat=south, lng=west), ne=DabangPointModel(lat=north, lng=east))
