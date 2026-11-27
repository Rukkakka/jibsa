"""요청 모델: 순위 기능(ranking)의 지금 많이 보는 단지·거래가 많은 단지·범위 안 순위가 같이 쓰는 것: 단지 종류·단위."""


from typing import (
    Literal,
)


DabangRankingComplexType = Literal['APT', 'OFFICETEL']

DabangRankingUnit = Literal['region', 'complex']
