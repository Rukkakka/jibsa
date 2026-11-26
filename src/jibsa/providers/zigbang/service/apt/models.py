"""아파트 매물 검색·묶음의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
    TradeType,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.service.common.base import MAX_LIST_LIMIT
from jibsa.providers.zigbang.service.common.models import (
    ZigbangAptListing,
    ZigbangAptRegion,
    ZigbangEstimatedPrice,
    ZigbangListingDetail,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangAptSearchResult(Result):
    """아파트 지역 매물 검색 결과.

    `notes`: 일부만 보여 준다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangAptRegion,
        Field(description='검색한 동·구. 좌표(lat·lng)는 이름으로 찾았는데 직방이 주지 않았으면 모름(null)')
    ]
    total: Annotated[
        int,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='직방 목록에 아직 받지 않은 매물이 남았는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 (지역 코드 code, 앞서 받은 수 offset). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[ZigbangAptListing],
        Field(description='직방이 보여 주는 순서의 매물')
    ]


class ZigbangAptConditions(RequestModel):
    """아파트 매물 조건 (search listings apt). 금액은 만원, 면적은 ㎡.

    거래 유형·가격·공급면적·신규분양 제외는 서버에서 거른다. 전용면적은 직방이 받지 않아 받은 뒤에 거른다.
    """

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형 (APT_TRADE_TYPES). 비면 전체')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    area_min_m2: Annotated[
        float | None,
        Field(description='전용면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='전용면적 상한 (㎡)')
    ] = None
    supply_area_min_m2: Annotated[
        float | None,
        Field(description='공급면적 하한 (㎡)')
    ] = None
    supply_area_max_m2: Annotated[
        float | None,
        Field(description='공급면적 상한 (㎡)')
    ] = None
    exclude_new_sale: Annotated[
        bool,
        Field(description="신규분양 매물을 빼고 볼지 (웹의 '신규 분양 포함' 을 끈 목록). 거짓이면 서버 기본(분양 포함)이다")
    ] = False


class ZigbangPublicPrice(BaseModel):
    """호의 공시가격 한 해."""

    model_config = ConfigDict(
        extra='forbid',
    )

    year: Annotated[
        int,
        Field(description='공시 연도')
    ]
    public_price_manwon: Annotated[
        float | None,
        Field(description='공시가격 (만원, 직방이 원 단위로 준 값을 환산). 0 이거나 직방이 주지 않으면 null (모름)')
    ] = None
    change_percent: Annotated[
        float | None,
        Field(description='전년 대비 변동률 (%, 부호 있음. 예: 26.9, -28, 0. 웹은 절댓값과 색으로 그린다). 직방이 주지 않으면 null')
    ] = None


class ZigbangCatalogResult(Result):
    """같은 호·거래 유형의 아파트 매물 묶음 (catalog). 호의 직방시세·공시가격·분양가(호 정보)도 함께 준다.

    `notes`: 뺀 매물·일부만 받았다는 안내와, 호 정보를 받지 못해 직방시세·공시가격·분양가를 모른다는 [실패] 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    catalog_id: Annotated[
        str,
        Field(description='묶음 ID (검색 결과의 catalog_id)')
    ]
    url: Annotated[
        str,
        Field(description='직방 웹 묶음 화면 (중개사별 매물 목록)')
    ]
    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형')
    ]
    total: Annotated[
        int | None,
        Field(description='묶음의 매물 수 (직방 itemCount. 상세를 볼 수 없는 출처도 센다). 직방이 묶음 수를 주지 않으면 모름(null)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description=(
            f'직방이 알린 묶음 매물 수(total)보다 덜 받았는지 (앞 {MAX_LIST_LIMIT}건까지만 받고, 직방이 다음 쪽을 주지 않으면 거기서 멈춘다). '
            f'total 이 null 이면 {MAX_LIST_LIMIT}건에 닿아 멈췄고 마지막 쪽이 가득 찼을 때 true (더 있을 수 있음)'
        ))
    ] = False
    listings: Annotated[
        list[ZigbangListingDetail],
        Field(description='묶음 매물 (직방이 준 순서 그대로). 매물마다 listing 상세와 같은 필드')
    ]
    estimated_prices: Annotated[
        dict[str, ZigbangEstimatedPrice | None],
        Field(description=(
            "이 호의 직방시세® (웹 묶음 화면 '시세 정보' 탭). 늘 'sale'·'jeonse' 두 키이고, sale 은 price_manwon·price_per_pyeong_manwon, jeonse 는 "
            'deposit_manwon·price_per_pyeong_manwon (만원, 평당가는 3.3㎡당). 직방이 실거래를 분석해 낸 추정값이라 호가·실거래가가 아니다. '
            '거래의 안 칸을 직방이 주지 않거나 0 이라 모두 모르면 그 거래가 null, 일부만 그러면 그 칸만 null'
        ))
    ]
    public_prices: Annotated[
        list[ZigbangPublicPrice] | None,
        Field(description='공시가격 (직방 응답 순서, 최근 해부터). 공시가격이 없으면 [], 호 정보를 받지 못했거나 직방이 주지 않으면 null')
    ] = None
    presale_price_manwon: Annotated[
        float | None,
        Field(description=(
            "이 호의 분양가 (만원, 직방 `ho분양가`). 웹은 이 값이 있으면 이 값을 '이 매물 분양가' 로 보여 준다 (`ho분양가 ?? roomType분양가`). "
            '직방이 주지 않거나 0 이면 null'
        ))
    ] = None
    presale_price_average_manwon: Annotated[
        float | None,
        Field(description=(
            "같은 타입의 평균 분양가 (만원, 직방 `averageHo분양가`). 웹은 호 분양가(`presale_price_manwon`)가 있을 때만 "
            "'이 매물과 같은 타입의 평균 분양가는 …입니다' 로 함께 보여 준다. 직방이 주지 않거나 0 이면 null"
        ))
    ] = None
    type_presale_price_manwon: Annotated[
        float | None,
        Field(description=(
            "이 호가 속한 타입(평형)의 분양가 (만원, 직방 `roomType분양가`). 웹은 호 분양가가 없을 때 이 값을 '이 매물 분양가' 로 보여 주고 "
            "'호 분양가 정보를 확인할 수 없어서 이 타입의 평균 분양가를 표시합니다' 를 붙인다. 직방이 주지 않거나 0 이면 null"
        ))
    ] = None
    presale_price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description=(
            '분양가 평당가 (만원, 3.3㎡당, 직방 `pyeongPrice`). 웹이 이 매물 분양가로 보여 주는 값(호 분양가가 있으면 그 호, 없으면 타입 분양가)의 '
            '평당가다 (2026-11-19 표본 12966062: 타입 분양가 88,560 ÷ 공급 32.7평 = 2,712, 호 분양가는 null). 직방이 주지 않거나 0 이면 null'
        ))
    ] = None
