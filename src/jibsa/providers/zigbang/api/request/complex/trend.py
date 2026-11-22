"""요청 모델: 단지 직방시세 추이 (price-trend)."""


from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Any,
    Literal,
)


# 웹 단지 화면 직방시세 그래프의 기간 탭 (최근1년·최근3년·전체, 기본 3년)
ZigbangPriceChartPeriod = Literal['1y', '3y', 'all']
# 평형 그래프의 거래 탭. all 전체, sales 매매, rent 전세·월세
ZigbangPriceChartDealType = Literal['all', 'sales', 'rent']


class ZigbangDanjisPriceChartRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/price-chart` 경로 + 쿼리. 단지 직방시세 추이 (웹 단지 화면의 직방시세 그래프).

    웹 '+ 단지 비교하기' 는 비교할 단지 ID 를 `addDanjiIds[0]=…` 인덱스 표기로 붙이고 응답에 그 단지의 구 줄이 더해진다 (2026-11-19 캡처).
    웹 화면은 한 곳만 고르게 하지만 서버는 둘 이상도 받는다 (2026-11-22 표본: 비교 셋 → 단지·비교 셋·구 다섯 줄).
    """

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]
    period: Annotated[
        ZigbangPriceChartPeriod,
        Field(description='기간 (1y 최근 1년, 3y 최근 3년, all 전체). 웹 기본은 3y')
    ]
    add_danji_ids: Annotated[
        list[int],
        Field(description='함께 볼 비교 단지 ID (`addDanjiIds[0]`·`addDanjiIds[1]`… 로 직렬화). 비우면 키째 뺀다', alias='addDanjiIds')
    ] = []

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data = handler(self)
        # 웹과 같은 순서(period 다음)로 `addDanjiIds[0]=…` 로 펼친다. `_index_arrays` 는 정해진 키만 펼쳐 쓰지 않는다
        add_danji_ids = data.pop('addDanjiIds', None) or []
        return {**data, **{f'addDanjiIds[{index}]': danji_id for index, danji_id in enumerate(add_danji_ids)}}


class ZigbangDanjisPriceChartRelatedDanjisRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/price-chart/related-danjis` 경로. 직방시세 그래프에서 비교할 만한 단지."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]


class ZigbangDanjisRoomTypesPriceChartRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/room-types/{danjiRoomTypeId}/price-chart` 경로 + 쿼리. 평형 하나의 월별 시세 추이.

    다른 단지의 평형 ID 를 줘도 서버는 그 평형의 값을 준다 (2026-11-22 실측: 단지 16629 + 평형 161661). 평형 ID 가 틀리면 200 에
    빈 `list` 가 온다.
    """

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]
    room_type_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='평형 ID (complex 의 pyeongs[].id). 경로에 들어간다')
    ]
    deal_type: Annotated[
        ZigbangPriceChartDealType,
        Field(description='거래 탭 (all 전체, sales 매매, rent 전세·월세)', alias='dealType')
    ]
    period: Annotated[
        ZigbangPriceChartPeriod,
        Field(description='기간 (1y 최근 1년, 3y 최근 3년, all 전체)')
    ]
