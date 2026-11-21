"""요청 모델: 단기임대 상세·후기·임대인의 다른 방 (listing stay-*)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class ZigbangGuestItemsRequestParameterModel(RequestModel):
    """`GET stay-apis.zigbang.com/guest/items/{itemId}` 경로."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단기임대 매물 ID. 경로에 들어간다')
    ]


class ZigbangGuestItemsReviewsRequestParameterModel(RequestModel):
    """`GET stay-apis.zigbang.com/guest/items/{itemId}/reviews` 경로 + 쿼리. 단기임대 후기와 평점 요약."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단기임대 매물 ID. 경로에 들어간다. 없는 매물도 200 에 빈 응답이다 (2026-11-19 실측)')
    ]
    limit: Annotated[
        int,
        Field(ge=1, le=50, description='받을 후기 수. 51 이상은 서버가 400 으로 거절한다 (2026-11-19 실측). 평점 요약만 필요하면 1')
    ] = 1


class ZigbangGuestItemsHostRequestParameterModel(RequestModel):
    """`GET stay-apis.zigbang.com/guest/items/host/{hostId}` 경로 + 쿼리. 같은 임대인의 다른 단기임대 매물."""

    host_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='임대인 ID (단기임대 상세의 hostId). 경로에 들어간다. 없는 임대인은 404 다 (2026-11-19 실측)')
    ]
    exclude_item_id: Annotated[
        int,
        Field(gt=0, description='목록에서 뺄 매물 ID (지금 보고 있는 매물)', alias='excludeItemId')
    ]
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호 (1부터). 웹은 page 를 보내지 않는다 (2026-11-20 캡처·번들 useGuestHostItems)')
    ] = 1
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=50,
            description=(
                '쪽 크기. 웹은 page·limit 을 보내지 않아 전체를 받고 300건에서 자른다 (2026-11-20 캡처·번들 useGuestHostItems). '
                'jibsa 는 앞 10건만 받으려고 보낸다'
            ),
        )
    ] = 10
