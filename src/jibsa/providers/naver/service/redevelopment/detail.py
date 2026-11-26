"""재개발 구역 정보 (redevelopment)."""

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    TRADE_KEY_BY_NAME,
    normalize_address,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.redevelopment.detail import (
    NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel,
    NaverComplexRedevelopmentV1RequestParameterModel,
)
from jibsa.providers.naver.service.common.functions import (
    TRADE_CODE_BY_NAME,
    amount_range,
    trade_article_counts,
    unwrap,
)
from jibsa.providers.naver.service.redevelopment.base import (
    redevelopment_url,
)
from jibsa.providers.naver.service.redevelopment.models import (
    NaverRedevelopmentDetail,
)


def get_redevelopment(
    client: NaverClient,
    area_number: int,
    *,
    trade_types: list[str] | None = None,
) -> NaverRedevelopmentDetail:
    """재개발 구역 하나의 기본 정보와 현재 매물 수·호가 범위 (2회 호출).

    Args:
        trade_types: `TRADE_CODE_BY_NAME` 의 이름. 주면 매물 수·호가 범위를 그 거래 유형 매물로만 센다 (서버 필터).

    Raises:
        JibsaError: 없는 구역 번호면 NOT_FOUND.
    """
    info = unwrap(
        client.run_request_complex_redevelopment_v1(
            NaverComplexRedevelopmentV1RequestParameterModel(redevelopment_area_number=area_number)
        ),
        '재개발 구역',
    )
    # 없는 구역 번호도 성공 응답에 빈 객체를 준다 (2026-10-10 확인)
    if not info.name:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'네이버 재개발 구역을 찾지 못했습니다: {area_number}',
            hint='구역 번호는 naver search redevelopment 결과의 redevelopment_id 를 쓰세요',
        )
    stats = unwrap(
        client.run_request_complex_redevelopment_area_article_stats_v1(
            NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel(
                redevelopment_area_number=area_number,
                trade_types=[TRADE_CODE_BY_NAME[name] for name in trade_types or []],
            )
        ),
        '재개발 구역 매물 통계',
    )
    counts, prices = stats.count, stats.price
    ratio = info.building_ratio_info
    # 서버가 고른 거래 유형만 세고 나머지를 0 으로 준다. 세지 않은 유형은 0건이 아니라 해당 없음이라 호가 범위의 키도 없고, 0건 거래도 키가 없다
    selected_keys = {TRADE_KEY_BY_NAME[name] for name in trade_types or ()}
    asking_ranges = {
        TRADE_KEY_BY_NAME[name]: value for name, value in (
            ('매매', amount_range('price_manwon', prices.deal_min_price, prices.deal_max_price)),
            ('전세', amount_range('deposit_manwon', prices.rent_min_price, prices.rent_max_price)),
        )
        if value is not None and (not trade_types or name in trade_types)
    }
    return NaverRedevelopmentDetail(
        redevelopment_id=area_number,
        name=info.name,
        legal_division=normalize_address(info.legal_division_address) if info.legal_division_address else None,
        planned_household_count=info.total_household_number,
        business_step=info.business_step,
        construction_company=info.construction_company or None,
        floor_area_ratio_percent=ratio.floor_area_ratio if ratio else None,
        building_coverage_ratio_percent=ratio.building_coverage_ratio if ratio else None,
        # 서버가 고른 거래 유형만 세고 나머지를 0 으로 준다 (매매만 고르면 전세·월세 0). 세지 않은 유형은 0건이 아니라 해당 없음이다
        listing_counts={
            key: count for key, count in trade_article_counts(counts).items() if not trade_types or key in selected_keys
        },
        asking_ranges=asking_ranges,
        url=redevelopment_url(area_number),
    )
