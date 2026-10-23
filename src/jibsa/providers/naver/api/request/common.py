"""여러 기능이 같이 쓰는 요청 모델·필터 값과 기반 모델."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


NaverTradeType = Literal['A1', 'B1', 'B2', 'B3']
"""A1 매매, B1 전세, B2 월세, B3 단기임대."""

NaverRealEstateType = Literal[
    'A01', 'A02', 'A04', 'A05', 'A06', 'A07', 'B01', 'B02',
    'C01', 'C02', 'C03', 'C04', 'C06',
    'D01', 'D02', 'D03', 'D04', 'D05',
    'E01', 'E02', 'E03', 'E04', 'F01', 'G01', 'Z00',
]
"""서버가 받는 매물 유형 코드 전부 (다른 값은 400, 2026-10-08). 뜻은 지역마다 매물 이름으로 확인했다.

A01 아파트, A02 오피스텔, A04 재건축, B01 아파트 분양권, B02 오피스텔·생활숙박시설 분양권,
C01 원룸(일반원룸·도시형생활주택), C02 빌라, C03 단독·다가구, C04 전원주택, D01 사무실, D02 상가,
D03 건물, D04 상가건물, D05 상가주택, E01 여관·모텔, E02 공장·창고, E03 토지, E04 지식산업센터,
F01 재개발 정비구역, Z00 기타. A07 도시형생활주택 단지, C06 한옥주택, G01 고시원은 매물을 찾지 못해
fin.land 프론트 JS 의 유형 정의(`REAL_ESTATE_TYPE`)로 확인했다 (2026-10-08).

빌라는 C02(일반 빌라) 외에 단지로 등록된 A05(연립 단지)·A06(다세대 단지)·A07(도시형생활주택 단지)이 따로 있다.
fin.land 지도의 빌라 필터는 A05·A06·A07·C02 를 함께 보낸다.
"""

NaverArticleSortType = Literal['RANKING_DESC', 'PRICE_ASC', 'PRICE_DESC', 'DATE_DESC', 'SPACE_ASC', 'SPACE_DESC']
"""매물 정렬. 랭킹순, 낮은·높은 가격순, 최신순, 좁은·넓은 면적순 (사이트 ARTICLE_SORT_TYPE, 2026-10-08)."""

NaverRoomCount = Literal['RCF01', 'RCF02', 'RCF03', 'RCF04']
"""방·욕실 수 RCF01 1개, RCF02 2개, RCF03 3개, RCF04 4개 이상. 다른 값은 400 (2026-10-08 확인)."""

NaverOptionType = Literal['OPF01', 'OPF02', 'OPF03', 'OPF04', 'OPF05', 'OPF06', 'OPF07', 'OPF08', 'OPF09']
"""시설. OPF01 엘리베이터, 02 주차 가능, 03 보안시설, 04 풀옵션, 05 에어컨, 06 테라스, 07 베란다, 08 마당, 09 복층.
여러 개면 모두 갖춘 매물만 (테라스+마당 → 테라스·마당 각각보다 적다)."""

NaverOneRoomShape = Literal['10', '20']
"""원룸 구조 10 오픈형, 20 분리형. 분리형에는 방이 여럿인 매물도 들어간다 (상세 shape 값).
상세에 shape 가 있는 매물만 걸린다. 단지 매물(아파트·오피스텔·단지형 빌라)은 shape 가 없어 모두 빠지고,
다른 매물도 구조를 입력하지 않아 shape 가 null 이면 빠진다 (2026-10-10 확인)."""

NaverMoveInType = Literal['MVF01', 'MVF02']
"""입주 가능일 MVF01 바로입주, MVF02 90일 내 입주."""

NaverLoanRatioType = Literal['00', '10']
"""융자금 00 없음(명시한 매물만), 10 시세 대비 30% 이하. 하나만 받는다."""

NaverParkingType = Literal['PKF01', 'PKF02', 'PKF03']
"""단지 주차 PKF01 세대당 1대 이상, PKF02 세대당 1.5대 이상, PKF03 전기차충전소. 여러 개면 모두 해당."""

NaverEntranceType = Literal['10', '20', '30']
"""단지 현관 구조 10 계단식, 20 복도식, 30 복합식 (사이트 ARTICLE_ENTRANCE_TYPE, 2026-10-10 확인).
매물 상세의 facilityInfo.entranceType 으로 거른다. 같은 단지라도 pyeongList 의 entranceType 과 다를 수 있다
(평형은 전부 계단식인 단지 매물이 복도식·복합식 필터에 걸린다)."""

NaverFloorType = Literal['FLF01', 'FLF02', 'FLF03', 'FLF04', 'FLF05', 'FLF06']
"""층 FLF01 1층, FLF02 저층, FLF03 중층, FLF04 고층, FLF05 탑층, FLF06 지하층. 분류가 겹친다 (꼭대기 층은 고층이자 탑층)."""

NaverDirectionType = Literal['EE', 'WW', 'SS', 'NN', 'EN', 'ES', 'WN', 'WS']
"""방향. 상세 응답은 SE·SW 처럼도 주지만 필터는 동·서를 앞에 둔 ES·WS 만 받는다 (SE 는 400)."""


class NaverComplexRequestParameterModel(RequestModel):
    """단지 계열 GET 엔드포인트가 공유하는 쿼리."""

    complex_number: Annotated[
        int,
        Field(gt=0, description='fin.land 단지 번호 (구 new.land 의 hscpNo 와 다름)', alias='complexNumber')
    ]


class NaverComplexV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex` 쿼리."""


class NaverComplexPyeongListV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/pyeongList` 쿼리."""


class NaverComplexBuildingListV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/buildingList` 쿼리."""


class NaverComplexVillaV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/villa` 쿼리. 단지로 등록된 빌라(A05 연립·A06 다세대·A07 도시형생활주택)용."""


class NaverComplexVillaPyeongListV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/villa/pyeongList` 쿼리."""


class NaverComplexVillaBuildingListV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/villa/buildingList` 쿼리."""


class NaverComplexPyeongRequestParameterModel(NaverComplexRequestParameterModel):
    """평형 단위 단지 엔드포인트 쿼리."""

    pyeong_type_number: Annotated[
        int,
        Field(gt=0, description='평형 번호 (pyeongList 의 number)', alias='pyeongTypeNumber')
    ]


class NaverLegalDivisionSearchByCoordinateV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/legalDivision/searchByCoordinate` 쿼리."""

    longitude: Annotated[
        float,
        Field(ge=-180, le=180, description='경도')
    ]
    latitude: Annotated[
        float,
        Field(ge=-90, le=90, description='위도')
    ]


class NaverPriceFilterModel(RequestModel):
    """단지 매물 목록·재개발 구역 매물 목록·구역 매물 집계가 공유하는 가격 키 (원, 경계 포함)."""

    min_deal_price: Annotated[
        int | None,
        Field(ge=0, description='매매가 하한 (원)', alias='minDealPrice')
    ] = None
    max_deal_price: Annotated[
        int | None,
        Field(ge=0, description='매매가 상한 (원)', alias='maxDealPrice')
    ] = None
    min_warranty_price: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 하한 (원)', alias='minWarrantyPrice')
    ] = None
    max_warranty_price: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 상한 (원)', alias='maxWarrantyPrice')
    ] = None
    min_rent_price: Annotated[
        int | None,
        Field(ge=0, description='월세 하한 (원)', alias='minRentPrice')
    ] = None
    max_rent_price: Annotated[
        int | None,
        Field(ge=0, description='월세 상한 (원)', alias='maxRentPrice')
    ] = None


class NaverBoundingBoxModel(RequestModel):
    """지도 뷰포트. left/right 는 경도, top/bottom 은 위도."""

    left: Annotated[
        float,
        Field(description='서쪽 경도')
    ]
    right: Annotated[
        float,
        Field(description='동쪽 경도')
    ]
    top: Annotated[
        float,
        Field(description='북쪽 위도')
    ]
    bottom: Annotated[
        float,
        Field(description='남쪽 위도')
    ]


class NaverRangeModel(RequestModel):
    """필터의 범위 값. 한쪽만 주면 그쪽만 제한한다 (값이 없는 쪽은 보내지 않는다)."""

    min: Annotated[
        float | None,
        Field(ge=0, description='하한 (포함)')
    ] = None
    max: Annotated[
        float | None,
        Field(ge=0, description='상한 (포함)')
    ] = None


class NaverArticleFilterModel(RequestModel):
    """지도 매물 필터. 서버가 모든 키를 요구하므로 기본값을 빈 값으로 채워 보낸다.

    가격·면적 범위는 키째 빼면 제한이 없다. 서버는 모르는 키를 400 없이 무시하므로 키 이름이 틀리면
    조용히 필터가 빠진다. 아래 키는 매물 수가 줄어드는 것으로 확인했다 (2026-10-08). 가격은 그 금액이
    없는 거래 유형을 거르지 않는다 (보증금 상한을 걸어도 매매는 그대로, 월세 상한을 걸어도 전세는 그대로).
    """

    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형', alias='tradeTypes')
    ] = ['A1', 'B1', 'B2']
    real_estate_types: Annotated[
        list[NaverRealEstateType],
        Field(description='매물 유형', alias='realEstateTypes')
    ] = ['A01', 'A02', 'A05', 'A06', 'A07', 'C02']
    deal_price: Annotated[
        NaverRangeModel | None,
        Field(description='매매가 범위 (원)', alias='dealPrice')
    ] = None
    warranty_price: Annotated[
        NaverRangeModel | None,
        Field(description='보증금·전세금 범위 (원)', alias='warrantyPrice')
    ] = None
    rent_price: Annotated[
        NaverRangeModel | None,
        Field(description='월세 범위 (원)', alias='rentPrice')
    ] = None
    space: Annotated[
        NaverRangeModel | None,
        Field(description='면적 범위 (㎡). filters_exclusive_space 가 True 면 전용면적, 아니면 공급면적 기준')
    ] = None
    management_fee: Annotated[
        NaverRangeModel | None,
        Field(description='관리비 범위 (원)', alias='managementFee')
    ] = None
    household_number: Annotated[
        NaverRangeModel | None,
        Field(description='단지 세대수 범위. 단지가 없는 매물(대부분의 빌라)은 빠진다', alias='householdNumber')
    ] = None
    approval_elapsed_year: Annotated[
        NaverRangeModel | None,
        Field(description='사용승인 후 지난 햇수 범위', alias='approvalElapsedYear')
    ] = None
    loan_ratio_type: Annotated[
        NaverLoanRatioType | None,
        Field(description='융자금 조건', alias='loanRatioType')
    ] = None
    room_count: Annotated[
        list[NaverRoomCount],
        Field(description='방 수. 비우면 제한 없음', alias='roomCount')
    ] = []
    bath_room_count: Annotated[
        list[NaverRoomCount],
        Field(description='욕실 수 (방 수와 같은 코드). 비우면 제한 없음', alias='bathRoomCount')
    ] = []
    option_types: Annotated[
        list[NaverOptionType],
        Field(description='시설. 모두 갖춘 매물만', alias='optionTypes')
    ] = []
    one_room_shape_types: Annotated[
        list[NaverOneRoomShape],
        Field(description='원룸 구조', alias='oneRoomShapeTypes')
    ] = []
    move_in_types: Annotated[
        list[NaverMoveInType],
        Field(description='입주 가능일', alias='moveInTypes')
    ] = []
    filters_exclusive_space: Annotated[
        bool,
        Field(description='space 를 전용면적 기준으로 비교', alias='filtersExclusiveSpace')
    ] = False
    floor_types: Annotated[
        list[NaverFloorType],
        Field(description='층. 비우면 제한 없음', alias='floorTypes')
    ] = []
    direction_types: Annotated[
        list[NaverDirectionType],
        Field(description='방향. 비우면 제한 없음', alias='directionTypes')
    ] = []
    has_article_photo: Annotated[
        bool,
        Field(description='사진 있는 매물만', alias='hasArticlePhoto')
    ] = False
    is_authorized_by_owner: Annotated[
        bool,
        Field(description='집주인 확인 매물만', alias='isAuthorizedByOwner')
    ] = False
    parking_types: Annotated[
        list[NaverParkingType],
        Field(description='단지 주차 조건. 모두 해당하는 매물만', alias='parkingTypes')
    ] = []
    entrance_types: Annotated[
        list[NaverEntranceType],
        Field(description='단지 현관 구조', alias='entranceTypes')
    ] = []
    walking_minute_to_subway_station: Annotated[
        NaverRangeModel | None,
        Field(description='지하철역까지 걸어서 걸리는 시간 범위 (분). 사이트는 min 0 으로 상한만 보낸다', alias='walkingMinuteToSubwayStation')
    ] = None
    has_article: Annotated[
        bool,
        Field(description="매물 있는 단지만 (사이트 '매물 있는 단지만'). 단지 목록이 쓴다", alias='hasArticle')
    ] = False
    legal_division_numbers: Annotated[
        list[str],
        Field(description='법정동 코드. 비우면 동으로 거르지 않고 bounding_box 안 전체', alias='legalDivisionNumbers')
    ] = []
    legal_division_type: Annotated[
        Literal['EUP', 'SI', 'GU'],
        Field(description='법정동 단위. EUP 이면 동/읍/면', alias='legalDivisionType')
    ] = 'EUP'
