"""두 기능 이상이 쓰는 다방 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Listing,
    TradeType,
)
from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


# 목록 면적이 전용이 아니라 공급면적인 매물 유형 (`room_item_to_listing`)
APARTMENT_TYPE: str = '아파트'
# 다방이 계약면적을 주는 매물 유형 (`DabangListingDetail.contract_area_m2`)
OFFICETEL_TYPE: str = '오피스텔'
# 단지가 있는 매물 유형. 상세 유형은 '오피스텔(분리형)' 처럼 뒤에 구조를 붙여 와서 앞부분으로 본다
COMPLEX_PROPERTY_TYPES: tuple[str, ...] = (OFFICETEL_TYPE, APARTMENT_TYPE)


class DabangListing(Listing):
    """다방 매물 (목록). 가격·층·면적·관리비는 다방 목록 글자를 읽은 값이다.

    목록의 주소는 동 이름뿐이다 (찾은 동의 매물만 시·구까지). 단기임대는 따로 있는 거래가 아니라 월세 매물에 붙는
    표시라 `trade_type` 은 '월세' 이고 `short_term` 으로 알린다. 아파트 면적은 공급면적이라 `supply_area_m2` 에 둔다.
    """

    listing_number: Annotated[
        int | None,
        Field(description='다방 화면의 매물번호 (listing 에 id 대신 줄 수 있다)')
    ] = None
    short_term: Annotated[
        bool,
        Field(description='단기임대(1개월 이상) 계약도 받는 월세 매물. 보증금이 월세 한두 달치(예 95/95)면 단기 계약 가격일 수 있다')
    ] = False
    complex_name: Annotated[
        str | None,
        Field(description='단지·건물 이름 (오피스텔·아파트)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 다방 목록은 아파트 면적을 공급면적으로만 줘서 아파트에만 있고 area_m2 는 null 이다 (전용은 listing)')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.trade_type != '월세':
            fields = fields | {'short_term'}
        if self.complex_name is None and not is_complex_type(self.property_type):
            fields = fields | {'complex_name'}
        if self.supply_area_m2 is None and (self.property_type is None or not self.property_type.startswith(APARTMENT_TYPE)):
            fields = fields | {'supply_area_m2'}
        return fields


class DabangListingConditions(RequestModel):
    """다방 매물 검색 조건 (한국어 라벨·만원). 모두 다방 서버가 거른다."""

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형 (비면 그 유형의 전체)')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(ge=0, description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(ge=0, description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(ge=0, description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(ge=0, description='매매가 상한 (만원)')
    ] = None
    rent_includes_manage_cost: Annotated[
        bool,
        Field(description='월세 범위를 월세 + 관리비로 볼지')
    ] = False
    area_pyeong_min: Annotated[
        int | None,
        Field(ge=0, description='방 크기 하한 (평)')
    ] = None
    area_pyeong_max: Annotated[
        int | None,
        Field(ge=0, description='방 크기 상한 (평)')
    ] = None
    built_within_years: Annotated[
        int | None,
        Field(ge=0, description='사용승인 뒤 이 햇수 이내')
    ] = None
    floors: Annotated[
        list[str],
        Field(description='층 라벨 (1층, 2층이상, 반지하, 옥탑)')
    ] = []
    rooms: Annotated[
        list[str],
        Field(description='방 개수 라벨 (원룸, 투룸, 쓰리룸, 포룸이상)')
    ] = []
    conditions: Annotated[
        list[str],
        Field(description='기타 조건 라벨 (주차, 엘리베이터, 단기임대, 분리형, 복층, 세안고)')
    ] = []
    parking_per_household_min: Annotated[
        int | None,
        Field(ge=0, description='세대당 주차 대수 하한 (대, 오피스텔·아파트)')
    ] = None
    households_min: Annotated[
        int | None,
        Field(ge=0, description='세대수 하한 (아파트)')
    ] = None
    households_max: Annotated[
        int | None,
        Field(ge=0, description='세대수 상한 (아파트)')
    ] = None


class DabangPlace(BaseModel):
    """찾은 위치 (동·역·대학·좌표). 동 번호·코드·역 번호는 다방 요청에만 쓰고 출력하지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    kind: Annotated[
        Literal['dong', 'station', 'university', 'point'],
        Field(description='위치 종류')
    ]
    name: Annotated[
        str,
        Field(description='이름')
    ]
    # 역·대학·좌표도 어느 동 안에 있어 주소·법정동코드는 해당 없음(키 삭제)이 아니라 다방이 주지 않은 모름(null)이다.
    # 네이버(역은 null)·직방 역 검색의 region 과 같다
    address: Annotated[
        str | None,
        Field(description='시·도부터 이은 이름 (동). 역·대학·좌표는 다방이 주지 않아 null')
    ] = None
    lat: Annotated[
        float,
        Field(description='중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='중심 경도')
    ]
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리). 역·대학·좌표는 다방이 주지 않아 null')
    ] = None
    code: Annotated[
        str | None,
        Field(exclude=True, description='다방 동 코드 (법정동코드 앞 8자리)')
    ] = None
    gid: Annotated[
        int | None,
        Field(exclude=True, description='다방 동 번호')
    ] = None
    place_id: Annotated[
        int | None,
        Field(exclude=True, description='다방 역·대학 번호')
    ] = None
    radius_m: Annotated[
        int | None,
        Field(exclude=True, description='다방 역 검색 반경 (m)')
    ] = None


class DabangPricePerPyeong(BaseModel):
    """거래 하나의 평당 평균가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='거래별 평당 평균가 (만원/3.3㎡)')
    ]


class DabangAreaPrice(BaseModel):
    """평당 평균가 비교 한 칸."""

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        str,
        Field(description="범위 ('해당 단지', 동 이름, 구 이름)")
    ]
    price_per_pyeong: Annotated[
        dict[str, DabangPricePerPyeong | None],
        Field(description="거래별 평당 평균가. 키는 'sale'·'jeonse' 늘 두 개이고, 값이 없으면(0 포함) 그 거래가 null")
    ]


def is_complex_type(property_type: str | None) -> bool:
    """단지가 있는 유형인지 ('오피스텔', '오피스텔(분리형)', '아파트'). 유형이 없으면(None) 아니다."""
    return property_type is not None and property_type.startswith(COMPLEX_PROPERTY_TYPES)
