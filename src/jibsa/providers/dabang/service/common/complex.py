"""다방 단지 상세 조회·대표 평형 고르기·평당가 한 칸 (단지 정보·단지 매물·실거래가가 같이 쓴다)."""
from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.notes import (
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.common import (
    DabangComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.common import (
    DabangAreaAveragePriceModel,
    DabangComplexResultModel,
)
from jibsa.providers.dabang.service.common.error import is_missing_id
from jibsa.providers.dabang.service.common.models import (
    DabangAreaPrice,
    DabangPricePerPyeong,
)


def complex_not_found(complex_id: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f'다방 단지를 찾지 못했습니다: {complex_id}',
        hint='jibsa dabang search locations <단지 이름> 이나 search complexes 결과의 complex_id 를 그대로 주세요',
    )


def fetch_complex(client: DabangClient, complex_id: str) -> DabangComplexResultModel:
    """단지 상세 (요청 1회, 단지 정보·평형·대표 평형). 없는 단지 ID 는 NOT_FOUND (단지 정보·단지 매물·실거래가 같이 쓴다)."""
    try:
        result = client.run_request_complex_v5(DabangComplexV5RequestParameterModel(complex_id=complex_id)).result
    except HTTPStatusError as exc:
        if is_missing_id(exc):
            raise complex_not_found(complex_id) from None
        raise
    if result is None:
        raise complex_not_found(complex_id)
    return result


def primary_space_of(result: DabangComplexResultModel) -> tuple[int, bool] | None:
    """`--pyeong` 이 없을 때 쓰는 평형 (평형 번호, 다방이 대표로 준 평형인지). 단지에 평형이 없으면 None.

    다방이 대표를 주지 않으면(없거나 0) 웹처럼 첫 평형이다. complex 의 representative_pyeong_id 와 real-price·price-trend·
    nearby-complexes 가 같이 써서 단지 정보가 알리는 대표 평형과 조회하는 평형이 같다.
    """
    if not result.spaces:
        return None
    # 웹은 단지 상세의 primarySpaceSeq 가 없으면 첫 평형을 연다 (complex-space-item 청크
    # `activeSpaceSeq = e?.primarySpaceSeq ?? r.spaces?.[0]?.spaceSeq`, 2026-11-14 번들). 웹은 None 일 때만 넘어가지만 다방은 값이
    # 없을 때 0 을 주는 칸이 많고 0 은 평형 번호가 될 수 없어(요청 모델이 1 이상만 받는다) 없음으로 본다 (2026-11-14 리뷰)
    primary = result.primary_space_seq
    if primary is not None and primary > 0:
        return primary, True
    return result.spaces[0].space_seq, False


def first_space_notes(result: DabangComplexResultModel) -> list[str]:
    """대표 평형을 다방이 주지 않아 첫 평형(`primary_space_of`)으로 대신하는데 평형 목록에서 빈 항목을 뺐으면 그 안내.

    뺀 항목이 다방 웹의 첫 평형일 수 있어 고른 평형이 웹과 다를 수 있다. 다방이 대표 평형을 줬거나 뺀 것이 없으면 빈 목록이다.
    """
    dropped = result.null_items('spaces')
    primary = result.primary_space_seq
    if not dropped or (primary is not None and primary > 0):
        return []
    return [
        null_items_note('다방 단지 평형', dropped),
        note('참고', '다방이 대표 평형을 주지 않아 평형 목록의 첫 평형을 골랐지만, 뺀 빈 항목이 다방 웹의 첫 평형이었다면 웹과 다른 평형입니다'),
    ]


def area_price(price: DabangAreaAveragePriceModel) -> DabangAreaPrice:
    """다방 평당 평균가 한 칸을 결과로 옮긴다. 'N평대 비교' 탭(nearby-complexes)과 '전체 평형 비교' 탭(complex)이 쓴다."""
    # 웹은 두 탭이 같은 막대 컴포넌트를 쓰고 값이 없거나 0 이면 '정보 없음' 으로 그린다 (complex 청크 `Yt`·`Wt`: `!e.price`,
    # 탭이 ALL 이면 단지 상세의 areaAveragePrice, 아니면 price-per-py 의 값, 2026-11-14). 0만원 평당가는 없으니 모름으로 둔다
    return DabangAreaPrice(
        scope=price.scope,
        price_per_pyeong={
            'sale': DabangPricePerPyeong(price_per_pyeong_manwon=sale) if (sale := price.trade_average_pyeong_price) else None,
            'jeonse': DabangPricePerPyeong(price_per_pyeong_manwon=lease) if (lease := price.lease_average_pyeong_price) else None,
        },
    )
