"""분양 단지 상세 (sale)."""
from datetime import (
    date,
)

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    AmountRange,
    AmountSet,
    add_unread_date,
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.sale.detail import (
    DabangSaleInLotsDetail2V3RequestParameterModel,
)
from jibsa.providers.dabang.service.common.constants import SALE_URL
from jibsa.providers.dabang.service.common.error import is_missing_id
from jibsa.providers.dabang.service.common.text import (
    count_of,
    manwon_from_text,
    number_of,
)
from jibsa.providers.dabang.service.sale.constants import (
    RENTAL_SUPPLY_TYPES,
    SALE_DAY_PATTERN,
    SALE_ISO_DAY_PATTERN,
    SALE_ISO_MONTH_PATTERN,
    SALE_MONTH_PATTERN,
)
from jibsa.providers.dabang.service.sale.models import (
    DabangSaleDetail,
    DabangSalePyeong,
    DabangSaleStep,
    DabangSubscriptionPyeong,
    DabangSubscriptionResult,
)

from typing import (
    Literal,
)


def sale_date(text: str | None) -> str | None:
    """다방 분양 날짜 글을 'YYYY-MM-DD' 나 'YYYY-MM' 으로 ('26.09.07' → '2026-09-07', '26.08월' → '2026-08').

    값이 없다는 표시 `-` 와 빈 글자는 None 이다. 다른 꼴과 달력에 없는 날·달('26.02.30')은 그대로 둔다.
    """
    if text is None or text.strip() in ('', '-'):
        return None
    value = text.strip()
    if (match := SALE_DAY_PATTERN.fullmatch(value)) is not None:
        try:
            return date(2000 + int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            return value
    if (match := SALE_MONTH_PATTERN.fullmatch(value)) is not None and 1 <= int(match.group(2)) <= 12:
        return f'20{match.group(1)}-{int(match.group(2)):02d}'
    return value


def sale_move_in(text: str | None) -> str | None:
    """분양 입주 예정을 'YYYY-MM-DD' 나 'YYYY-MM' 으로 (`sale_date`).

    날짜·연월로 읽지 못하면 받은 글자를 내지 않고 None 이고, 원래 글자는 `[참고]` 안내로 알린다 (`add_unread_date`,
    다른 소스의 입주일 `move_in_label` 과 같다, 2026-11-26 사용자 결정). 값이 없다는 `-` 와 빈 글자는 안내 없는 None 이다.
    """
    value = sale_date(text)
    if value is None or SALE_ISO_DAY_PATTERN.fullmatch(value) or SALE_ISO_MONTH_PATTERN.fullmatch(value):
        return value
    add_unread_date('입주일', value)
    return None


def _step_time(text: str | None, name: Literal['start', 'end'], unreadable: list[str]) -> dict[str, str | None]:
    """분양 단계 시작·끝 글자를 낼 칸 하나로 ('2026-09-07' → `<name>_date`, '2026-08' → `<name>_month`).

    시작이 비거나 `-` 면 `start_date` 가 None 이고(모름), 끝이 비거나 `-` 면 칸이 없다 (한 시점인 단계는 끝이 해당 없음). 두 꼴이 아닌 글자면
    `<name>_date` 를 None 으로 내고 `unreadable` 에 원래 글자를 모은다.
    """
    value = sale_date(text)
    if value is None:
        return {} if name == 'end' else {'start_date': None}
    if SALE_ISO_DAY_PATTERN.fullmatch(value):
        return {f'{name}_date': value}
    if SALE_ISO_MONTH_PATTERN.fullmatch(value):
        return {f'{name}_month': value}
    unreadable.append(value)
    return {f'{name}_date': None}


def get_sale(client: DabangClient, sale_id: str) -> DabangSaleDetail:
    """분양 단지 하나 (요청 1회).

    Raises:
        JibsaError: 없는 분양 ID (NOT_FOUND).
    """
    try:
        response = client.run_request_sale_in_lots_detail2_v3(DabangSaleInLotsDetail2V3RequestParameterModel(id=sale_id))
    except HTTPStatusError as exc:
        # 분양 ID 는 쿼리로 간다. 없는 ID 는 400 '존재하지 않는 분양정보입니다.' (2026-10-27 실측)
        if is_missing_id(exc, in_path=False):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방 분양 단지를 찾지 못했습니다: {sale_id}',
                hint='jibsa dabang search sales 나 search locations 결과의 presale_id 를 그대로 주세요',
            ) from None
        raise
    info = response.sale_in_lots
    # '12억9990 ~ 22억7680' (2026-10-26 실측 19곳 모두 이 꼴). '~' 가 없으면 한 가격이라 최고가도 같고, 있는데 뒤를 못 읽으면
    # 최고가를 모르는 것이라 null 로 둔다 (최저가로 채우면 범위가 정해진 것처럼 보인다)
    low, separator, high = ((info.price_info.price_str if info.price_info else None) or '').partition('~')
    subscription = response.subscription_result
    price_low, price_high = manwon_from_text(low), manwon_from_text(high if separator else low)
    # 일정 단계의 시작·끝 중 날·달 꼴로 읽지 못한 글자
    unreadable: list[str] = []
    schedules = [
        DabangSaleStep(
            step=step.type_str or '', **_step_time(step.from_str, 'start', unreadable), **_step_time(step.to_str, 'end', unreadable),
        )
        for step in response.schedules
    ]
    notes = [note(
        '참고',
        f"다방이 준 분양 일정 날짜를 읽지 못해 start_date·end_date 를 null 로 두었습니다 ({len(unreadable)}건, 원래 글자 예: '{unreadable[0]}')",
    )] if unreadable else []
    rental = info.supply_type in RENTAL_SUPPLY_TYPES
    amount_key = 'deposit_manwon' if rental else 'price_manwon'
    return DabangSaleDetail(
        presale_id=info.id,
        name=info.building_name,
        status=info.state_str,
        complex_type=info.building_types_str,
        supply_type=info.supply_type_str,
        address=normalize_address(info.jibun_address or info.address),
        road_address=normalize_address(info.road_address),
        household_count=info.total_household_num,
        presale_household_count=info.lots_household_num,
        dong_count=info.dong_count,
        building_floor=info.ground_floor,
        basement_floor=info.underground_floor,
        construction_company=info.provider_name,
        developer=info.constructor_name,
        price_kind='임대가' if rental else '분양가',
        price_range=None if price_low is None and price_high is None else AmountRange(
            lowest=AmountSet(**{amount_key: price_low}), highest=AmountSet(**{amount_key: price_high}),
        ),
        price_per_pyeong_manwon=manwon_from_text(info.price_info.pyeong_price) if info.price_info else None,
        region_price_per_pyeong_average_manwon=(
            manwon_from_text(info.price_info.region_average_pyeong_price) if info.price_info else None
        ),
        move_in=sale_move_in(info.moving_date_str),
        regulation_area=info.regulation_area_str,
        price_cap=info.is_price_cap,
        resalable=info.is_resalable,
        schedules=schedules,
        pyeongs=[
            DabangSalePyeong(
                name=space.space_name,
                area_m2=space.exclusive_space,
                supply_area_m2=space.supply_space,
                household_count=space.household_num,
                **{amount_key: manwon_from_text(space.price_str)},
            )
            for space in response.spaces
        ],
        subscription_result=None if subscription is None else DabangSubscriptionResult(
            lowest_winning_point=count_of(subscription.min_winning_point_str),
            highest_competition_ratio=number_of(subscription.max_competitive_rate_str),
            # 평형별 결과가 null 이면 모름이라 [] (없음) 로 바꾸지 않는다
            pyeongs=None if subscription.subscription_spaces is None else [
                DabangSubscriptionPyeong(
                    name=space.space_name,
                    presale_household_count=count_of(space.household_num_str),
                    competition_ratio=number_of(space.competitive_rate_str),
                    winning_point=count_of(space.winning_point_str),
                )
                for space in subscription.subscription_spaces
            ],
        ),
        notice_url=info.notice_url,
        applyhome_url=info.applyhome_link,
        url=SALE_URL.format(info.id),
        notes=notes,
    )
