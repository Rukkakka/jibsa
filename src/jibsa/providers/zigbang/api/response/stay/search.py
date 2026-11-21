"""응답 모델: 단기임대 매물 검색 (search listings stay): 지도 핀과 지역·역·학교 검색 ID 목록."""

from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/markers
# ---------------------------------------------------------------------------

class ZigbangStayMarkerModel(ResponseModel):
    """단기임대 매물 위치 핀. 웹 지도 목록은 화면 안 핀을 이 값들로 세운다 (번들 `sortStayMarkers`)."""

    id: Annotated[
        int,
        Field(description='단기임대 매물 ID')
    ]
    lat: Annotated[
        float,
        Field(description='위도 (요약 by-ids 의 좌표와 같다. 2026-11-15 실측 71건)')
    ]
    lng: Annotated[
        float,
        Field(description='경도')
    ]
    weekly_price: Annotated[
        int | None,
        Field(
            description='주당 임대료+관리비 (만원, 만원 미만 버림. 2026-11-15 실측 71건 모두). 웹 지도 목록 가격순의 기준',
            alias='weeklyPrice'
        )
    ] = None
    has_discount: Annotated[
        bool | None,
        Field(description='할인 여부', alias='hasDiscount')
    ] = None
    reviewed_at: Annotated[
        str | None,
        Field(description='검수 완료(노출 시작) 일시 (UTC ISO 8601, 요약과 같다). 웹 지도 목록 최신순의 기준', alias='reviewedAt')
    ] = None
    total_score: Annotated[
        float | None,
        Field(description='직방 추천 점수 (예: 0.85). 웹 지도 목록 추천순의 기준 (높을수록 앞)', alias='totalScore')
    ] = None


class ZigbangGuestItemsSearchResponseModel(ResponseModel):
    """지역·역·학교 조건에 맞는 단기임대 ID 목록. 요청한 정렬(`sort`) 순서이고, 웹 검색 결과 목록이 이 순서 그대로다."""

    item_ids: Annotated[
        list[int],
        Field(description='조건에 맞는 단기임대 매물 ID', alias='itemIds')
    ]
    total_count: Annotated[
        int,
        Field(
            description='서버 검색 결과 수. itemIds 를 자르지 않아 늘 itemIds 수와 같다 '
            '(페이지 인자 없음. 2026-10-11 실측: 서울시 1,491·경기도 568건)',
            alias='totalCount'
        )
    ]


class ZigbangGuestItemsMarkersResponseModel(ResponseModel):
    """단기임대 매물 위치 응답."""

    markers: Annotated[
        list[ZigbangStayMarkerModel],
        Field(description='geohash 칸 안의 매물 핀')
    ] = []
