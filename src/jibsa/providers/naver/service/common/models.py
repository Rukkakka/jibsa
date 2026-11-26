"""네이버 service 공통의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
)

from jibsa.core.listing import (
    AmountRange,
    Listing,
    Result,
)
from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Any,
)


BADGES_DESCRIPTION: str = (
    "네이버 화면의 확인 배지 (집주인·소유자·현장). 확인 정보가 있으면 그 뒤에 집주인이 HUG 안심임대인일 때 'HUG 안심임대인' 이 붙는다. "
    '방식 배지·HUG 배지가 모두 없으면 [], 모르면 null. 전화·서류로 확인한 매물과 확인하지 않은 매물도 HUG 안심임대인이면 '
    "['HUG 안심임대인'] 이라, 비어 있지 않다고 집주인·현장 확인 매물인 것은 아니다"
)


CONFIRMED_AT_DESCRIPTION: str = (
    "네이버가 매물을 확인한 날 (YYYY-MM-DD). 웹 목록은 협회 매물이 아니면 이 날짜로 '25.11.17. 확인매물' 날짜 배지를, 협회 매물이면 "
    "노출 시작일(`registered_date`)로 '등록' 배지를 그린다. 목록과 상세의 글자 규칙이 달라 날짜만 낸다. 모르면 null"
)


# 매물 유형(realEstateType)마다 웹 화면이 칸을 아예 그리지 않는 필드. 키째 뺀다 (칸이 있는데 값을 모르면 null 이다). 상세(`NaverListingDetail`)와
# 목록(`NaverListing`)이 함께 쓴다. 목록 모델에 없는 필드 이름은 출력에서 그냥 지나간다.
# 2026-11-17 네이버 웹 번들 대조: 기본 정보 칸은 청크 0n-xsnd22pdxz 의 getBasicInfoSpaceTarget·면적 함수, 건축물 정보
# ArticleBuildingInfo 는 isBuildingRegistrationType 유형만, 시설 ArticleFacilityInfo 는 토지_임야(E03) 만 제외 (청크 0l4pkwg0qhg2t)
NOT_APPLICABLE_FIELDS_BY_TYPE: dict[str, frozenset[str]] = {
    # 토지
    'E03': frozenset({
        'room_count', 'bathroom_count', 'room_type', 'direction', 'floor', 'building_floor', 'area_m2', 'area_pyeong',
        'supply_area_m2', 'approved_date', 'heating', 'heating_fuel', 'entrance', 'parking', 'has_elevator', 'options',
    }),
    # 고시원: 시설 칸은 있어 has_elevator·options 는 남긴다
    'G01': frozenset({
        'room_count', 'bathroom_count', 'room_type', 'direction', 'floor', 'building_floor', 'area_m2', 'area_pyeong',
        'supply_area_m2', 'approved_date', 'heating', 'heating_fuel', 'entrance', 'parking', 'loan_manwon',
    }),
    # 재개발
    'F01': frozenset({'room_count', 'bathroom_count', 'room_type', 'area_m2', 'area_pyeong', 'supply_area_m2'}),
    # 사무실·상가·지식산업센터: 웹은 방/욕실 대신 '화장실 수' 만 그린다 (bathroom_count 는 남긴다)
    **dict.fromkeys(('D01', 'D02', 'E04'), frozenset({'room_count', 'room_type'})),
    # 건물·상가건물·숙박·공장창고·기타: 웹은 해당층 대신 지상/지하 층수만 그리고 공급면적 칸이 없다 (building_floor 는 그대로)
    **dict.fromkeys(('D03', 'D04', 'E01', 'E02', 'Z00'), frozenset({'room_count', 'room_type', 'floor', 'supply_area_m2'})),
}

# 묶음이 아니거나 중개사마다 호가가 같으면 해당 없는(키를 빼는) 필드
GROUP_FIELDS: tuple[str, ...] = ('realtor_count', 'asking_range')


class NaverAssignedSchool(BaseModel):
    """배정 초등학교 한 곳. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str | None,
        Field(description='학교 코드. naver school 에 넘긴다')
    ] = None
    name: Annotated[
        str,
        Field(description='학교 이름')
    ]
    assignment: Annotated[
        str | None,
        Field(description='배정 방식 (배정, 선택. 모르는 코드면 알 수 없는 값 (코드), 없으면 null)')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)')
    ] = None
    walk_minutes: Annotated[
        int | None,
        Field(description='도보 시간 (분)')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None


class NaverListing(Listing):
    """네이버 목록 매물. 같은 집을 중개사 여럿이 올려 네이버가 한 매물로 묶었으면 묶음의 중개사 수와 호가 범위가 붙는다.

    가격 필드(`price_manwon` 등)는 묶음을 대표하는 매물 하나의 호가다. 네이버 가격순은 묶음의 호가 범위로 정렬해
    (가격높은순은 최고 호가) 대표 가격의 순서와 다를 수 있다. 2026-10-31 실측: 헬리오시티 84㎡ 매매 가격높은순 첫 매물이
    대표 30억, 같은 집(204동 22층)을 중개사 50곳이 30억~33억에 올린 묶음이었다. 범위를 버리면 33억 호가가 어디에도 안 보여
    에이전트 4명 모두 최고 호가를 32억으로 답했다.
    """

    realtor_count: Annotated[
        int | None,
        Field(description='같은 집을 올린 중개사 수 (네이버가 한 매물로 묶음). 묶음이 아니면 키가 없다')
    ] = None
    asking_range: Annotated[
        AmountRange | None,
        Field(description=(
            '묶음의 호가 범위 {lowest, highest}. 중개사마다 호가가 다를 때만 있다. 매매는 price_manwon, 전세는 deposit_manwon, '
            '월세·단기임대는 보증금·월세 짝(deposit_manwon·rent_manwon)이고, 월세 두 끝은 월세 최저·최고가 아니라 (보증금 순 첫·끝 매물의 짝이라) '
            'rent_manwon 이 거꾸로일 수 있다 (보증금이 같은 매물끼리는 lowest 가 월세 낮은 쪽, highest 가 높은 쪽). 보증금이 같고 월세만 다르면 '
            '두 끝의 deposit_manwon 이 같은 값이고, 월세가 같고 보증금만 다르면 두 끝의 rent_manwon 이 같은 값이다. 가운데 매물의 월세는 달라도 두 끝이 '
            '같을 수 있다. 네이버가 어느 금액의 범위를 주지 않거나 두 끝이 모두 비거나 0 과 null 이 섞이면 그 금액만 null 이고, 모든 금액을 모르면 '
            'asking_range 가 null 이다. 묶음이 아니거나 모든 금액의 두 끝이 같으면 키가 없다'
        ))
    ] = None
    unknown_group_fields: Annotated[
        frozenset[str],
        Field(exclude=True, description='묶음 호가 범위를 몰라 null 로 낼 칸')
    ] = frozenset()
    badges: Annotated[
        list[str] | None,
        Field(description=BADGES_DESCRIPTION)
    ] = None
    confirmed_date: Annotated[
        str | None,
        Field(description=CONFIRMED_AT_DESCRIPTION)
    ] = None
    real_estate_type: Annotated[
        str | None,
        Field(exclude=True, description='네이버 매물 유형 코드 (A01 …). 유형마다 웹에 없는 칸을 가리는 데만 쓴다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 유형마다 웹이 칸을 그리지 않는 필드 (토지의 방 수·층·면적 등). 값을 모르는 null 이 아니라 키째 뺀다
        return (
            super().not_applicable_fields()
            | ({name for name in GROUP_FIELDS if getattr(self, name) is None} - self.unknown_group_fields)
            | NOT_APPLICABLE_FIELDS_BY_TYPE.get(self.real_estate_type or '', frozenset())
        )


class NaverListingsResult(Result):
    """매물 목록 결과.

    `notes`: 요청 상한으로 일부만 훑었다는 안내 등
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int,
        Field(description='서버 집계 매물 수. search 는 반경을 감싸는 사각형 안, 동·시·군·구 경계로 찾았으면 그 경계 안 정확한 수 (조건 적용 후, limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description=(
            '같은 조건으로 더 받을 매물이 남았는지. 이어 받을 수 있으면 next_position 도 있어 CLI 가 이어 받기 표(next)를 붙인다. '
            '네이버가 더 있다면서 새 매물을 주지 않아 멈췄으면 이어 받을 수 없어도(next 없음) true 다'
        ))
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 (목록 커서 seed·last_info). 더 없으면 None')
    ] = None
    listings: Annotated[
        # 중복 묶음 필드(NaverListing)까지 내보낸다 (SerializeAsAny 가 없으면 공통 Listing 필드만 나간다)
        list[SerializeAsAny[Listing]],
        Field(description='매물')
    ]


class NaverMarketBand(BaseModel):
    """기관 시세 한 거래 유형의 평균과 하위·상위 띠 (만원). 띠는 범위가 아니라 기관이 준 하위·상위 값이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    average_manwon: Annotated[
        float | None,
        Field(description='시세 평균 (만원). 없으면(0 포함) null')
    ] = None
    low_manwon: Annotated[
        float | None,
        Field(description='시세 하위 (만원). 기관이 띠를 주지 않으면 null')
    ] = None
    high_manwon: Annotated[
        float | None,
        Field(description='시세 상위 (만원). 기관이 띠를 주지 않으면 null')
    ] = None


class PageScan(BaseModel):
    """페이지 넘김 조회 예산과 훑은 결과 (`scan_pages` 가 채운다)."""

    limit: Annotated[
        int,
        Field(description='조회 할당량 (--limit). 받은 개수로 센다')
    ]
    max_requests: Annotated[
        int,
        Field(description='네이버 차단을 피하려는 페이지 요청 상한')
    ]
    received: Annotated[
        int,
        Field(description='지금까지 받은 항목 수 (할당량을 쓴 만큼). 빈 항목(null)이라 빼고 읽은 자리도 서버가 센 자리라 들어 있다')
    ] = 0
    null_items: Annotated[
        int,
        Field(description='받은 쪽에서 빈 항목(null)이라 빼고 읽은 수 (`received` 에 이미 들어 있다). 있으면 `scan_null_items_notes` 로 알린다')
    ] = 0
    page_requests: Annotated[
        int,
        Field(description='지금까지 보낸 페이지 요청 수')
    ] = 0
    truncated: Annotated[
        bool,
        Field(description='받을 게 남았는데 요청 상한에 닿아 멈췄는지')
    ] = False
    stalled: Annotated[
        bool,
        Field(description='서버가 다음 쪽이 있다고 했는데 그 쪽이 준 항목이 모두 이미 받은 것이거나 쪽이 비어 멈췄는지')
    ] = False
    total: Annotated[
        int,
        Field(description='서버 집계 (마지막 페이지의 totalCount)')
    ] = 0
    seen: Annotated[
        set[Any],
        Field(description='이미 받은 항목 번호. 준 항목이 모두 이미 받은 번호면 커서가 멈춘 것으로 본다')
    ] = set()
    cursor: Annotated[
        tuple[str | None, Any] | None,
        Field(description=(
            '마지막으로 훑은 목록에서 다음 페이지를 받을 (seed, lastInfo). 다음 페이지가 없거나 커서가 멈췄으면 None. '
            '이어 받기(--next)에 쓴다'
        ))
    ] = None

    def stopped_short(self, *, resumed: bool) -> bool:
        """네이버가 다음 쪽이 있다면서 새 항목을 주지 않아 멈췄고(`stalled`) 받지 못한 항목이 남았는지.

        이어 받은 결과(`resumed`)의 `total` 은 앞 결과까지 센 수라 견주지 않고, 멈췄으면 남았다고 본다. 이어 받기가 아니면
        받은 수가 서버가 센 수에 닿았을 때 다 받은 것이다 (2026-11-24 리뷰: 30건 중 30건에 '일부만 받았다').
        `pagination_notes` 의 `stalled` 와 결과의 `has_more` 가 이 하나를 같이 쓴다.
        """
        return self.stalled and (resumed or self.total > self.received)

    @property
    def exhausted(self) -> bool:
        """서버가 다음 쪽이 없다고 해 끝까지 받았는지. `fetch` 가 None 을 줘 `cursor` 가 None 이 된 경우도 포함한다.

        마지막 쪽이 마침 `limit` 에 닿은 것을 '더 있다' 로 보지 않게 한다.
        """
        return self.cursor is None and not self.stalled


class NaverTradeConditions(RequestModel):
    """거래 유형·가격 조건 (단지·재개발 구역 매물 목록과 지도 검색 공통). 금액은 만원이고 원으로 바꿔 보낸다.

    가격 조건은 모두 서버 필터로 보내고 받은 뒤 다시 거르지 않는다. 그 금액이 없는 거래 유형은 서버도 거르지 않는다.
    """

    trade_types: Annotated[
        list[str],
        Field(description='거래 유형 (TRADE_CODE_BY_NAME 의 이름). 비면 전체')
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
