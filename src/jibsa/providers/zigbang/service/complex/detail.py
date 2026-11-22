"""아파트 단지·오피스텔 건물 정보와 단지 매물 목록 (complex, search listings --complex)."""

import re

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    Listing,
    iso_date,
    join_address,
    limit_notes,
    normalize_address,
    normalize_date,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.complex.base import (
    ZigbangDanjisRoomTypesRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.complex.detail import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
    ZigbangDanjisSchoolsRequestParameterModel,
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangDanjiRankModel,
    ZigbangLandTradePermitModel,
    ZigbangRelateDanjiModel,
    ZigbangSearchItemModel,
)
from jibsa.providers.zigbang.api.response.complex.base import (
    ZigbangDanjiRoomTypeModel,
    ZigbangDanjisRoomTypesResponseModel,
)
from jibsa.providers.zigbang.api.response.complex.detail import (
    ZigbangDanjisItemCatalogsResponseModel,
    ZigbangDanjisSchoolsResponseModel,
    ZigbangItemsOfficetelsBuildingV1ResponseModel,
)
from jibsa.providers.zigbang.service.common.apt import (
    APT_TRAN_TYPE_BY_TRADE,
    TRADE_BY_APT_TRAN_TYPE,
    apt_pagination_notes,
    catalog_null_notes,
    catalog_to_listing,
)
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    NEAREST_SCHOOLS,
    SCHOOL_LOOKUP_ERRORS,
    ComplexKind,
    apt_danji_url,
    complex_not_found,
    failure_update_hint,
    fetch_danji,
    parse_complex_id,
    school_label,
    text_or_none,
)
from jibsa.providers.zigbang.service.common.room import (
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    ZigbangRoomConditions,
    excluded_notes,
    pin_null_notes,
    room_filter_of,
    section_ordered_ids,
    summary_to_listing,
    tradeable_summaries,
)
from jibsa.providers.zigbang.service.complex.base import (
    ZigbangRelatedComplex,
    related_complex_of,
)
from jibsa.providers.zigbang.service.region import (
    search_regions,
    to_int,
)

from typing import (
    Annotated,
    Any,
    TypeVar,
)


def danji_schools(response: ZigbangDanjisSchoolsResponseModel) -> list[str]:
    """아파트 단지 학군을 당근 `schools` 와 같은 문구로 바꾼다.

    초등은 통학구역 안 학교를 '배정' 으로, 중·고는 학교군 안에서 가까운 `NEAREST_SCHOOLS` 곳을 학교군 이름과 함께 준다.
    """
    labels: list[str | None] = []
    if response.elementary:
        labels += [school_label(school.name, '배정', school.distance) for school in response.elementary.schools]
    # 중·고교는 거리순으로 와서 정렬하지 않고 앞에서 자른다. 매물 학군(`building_schools`)은 거리 숫자를 받아 정렬한다
    # (2026-10-14 실측: 단지 6곳(apt-38487·946·33293·2873·2942·4567) 중학교 9~17곳·고등학교 21~26곳 모두 거리 오름차순)
    for level in (response.middle, response.high):
        if level:
            labels += [
                school_label(school.name, level.zone_name, school.distance)
                for school in level.schools[:NEAREST_SCHOOLS]
            ]
    return [label for label in labels if label]


COMPLEX_KIND_BY_SEARCH_TYPE: dict[str, ComplexKind] = {
    'apartment': 'apt',
    'officetel': 'officetel',
}
PROPERTY_TYPE_BY_COMPLEX_KIND: dict[ComplexKind, str] = {
    'apt': '아파트',
    'officetel': '오피스텔',
}
# 단지 정보에서 한쪽 유형에만 있는 필드. 다른 유형은 출력에서 키를 뺀다
APT_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({
    'dong_count', 'approved_at', 'construction_company', 'parking_per_household',
    'floor_area_ratio', 'heating', 'article_counts', 'pyeongs', 'review_count', 'schools',
    'estimated_sale_price_min_manwon', 'estimated_sale_price_max_manwon', 'estimated_sale_price_per_pyeong_manwon',
    'estimated_jeonse_price_per_pyeong_manwon', 'rank', 'related_complexes', 'land_trade_permits',
})
OFFICETEL_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({'completed_at', 'elevator'})
DANJI_CATALOG_PAGE_SIZE: int = 50


def officetel_building_url(building_id: int) -> str:
    # 웹은 건물 ID 를 이 경로의 area_danji_id 자리에 넣는다
    return f'https://www.zigbang.com/home/officetel/danjis/{building_id}/items'


class ZigbangComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (zigbang complex·items 에 넘긴다)')
    ]
    property_type: Annotated[
        str,
        Field(description='아파트 또는 오피스텔')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='단지가 있는 동까지의 주소')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None


class ZigbangPyeong(BaseModel):
    """아파트 평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    id: Annotated[
        int,
        Field(description='평형 ID (zigbang search listings --complex --pyeong 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 ㎡ 기준, 예: 111A)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 평 기준, 예: 34A)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 직방 평형 정보를 받지 못했거나 그 평형이 없으면 모름(null)')
    ] = None
    supply_area_pyeong: Annotated[
        float | None,
        Field(description='공급면적 (평). 직방이 준 값 그대로')
    ] = None
    exclusive_area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    exclusive_area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평). 직방이 준 값 그대로')
    ] = None
    households: Annotated[
        int | None,
        Field(description='그 평형의 세대수 (웹 평형 이름 옆 괄호, 예: 107A㎡ (731세대))')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    entrance_type: Annotated[
        str | None,
        Field(description="현관 구조 (직방 글자 그대로, 예: '계단식'·'복도식'). 직방이 주지 않으면 null")
    ] = None
    manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='평균 월 관리비 (만원, 직방 정수 그대로). 웹 안내: K-apt 최소 3개월~최대 24개월 평균. 0 이거나 직방이 주지 않으면 null (웹은 이때 관리비 줄을 숨긴다)')
    ] = None
    manage_cost_summer_manwon: Annotated[
        int | float | None,
        Field(description='여름(6~8월) 월 관리비 (만원). 0 이거나 직방이 주지 않으면 null (웹은 이때 -)')
    ] = None
    manage_cost_winter_manwon: Annotated[
        int | float | None,
        Field(description='겨울(12~2월) 월 관리비 (만원). 0 이거나 직방이 주지 않으면 null (웹은 이때 -)')
    ] = None
    resale_available_from: Annotated[
        str | None,
        Field(description='전매제한이 풀려 매매할 수 있는 날 (직방 거래가능시점, YYYY-MM-DD). 이미 지난 날도 그대로 낸다 (웹은 오늘 뒤일 때만 안내). 직방이 주지 않으면 null')
    ] = None
    estimated_sale_price_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 매매 (만원, 직방 시세 범위의 최저값. 2026-11-19 표본 30개 평형은 최저 = 최고). 실거래를 머신러닝으로 분석한 직방 추정값이고 실거래 평균이 아니다. 0 이거나 없으면 null (웹 시세없음)')
    ] = None
    estimated_sale_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 매매의 평당 가격 (만원/3.3㎡, 공급면적 평 기준). 0 이거나 없으면 null')
    ] = None
    estimated_jeonse_price_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 전세 (만원). 직방 추정값이고 실거래 평균이 아니다. 0 이거나 없으면 null (웹 전세 시세없음)')
    ] = None
    estimated_jeonse_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 전세의 평당 가격 (만원/3.3㎡, 공급면적 평 기준). 0 이거나 없으면 null')
    ] = None


class ZigbangComplexRank(BaseModel):
    """단지 순위. 직방 웹 단지 화면의 '<동>에서 이 단지의 랭킹은?' 절."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='웹 제목 속 동 이름 (예: 가락동)')
    ]
    price_rank: Annotated[
        int | None,
        Field(description="웹 '시세 N위' 의 N (직방은 실거래가 순위로 준다). 순위 없음이면 null")
    ]
    popularity_rank: Annotated[
        int | None,
        Field(description="웹 '인기순 N위' 의 N (직방은 조회수 순위로 준다). 순위 없음이면 null")
    ]


class ZigbangLandTradePermitDay(BaseModel):
    """토지거래허가 일별 건수 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    date: Annotated[
        str | None,
        Field(description='날짜 (YYYY-MM-DD). 직방이 준 날짜를 읽지 못하면 모름(null)')
    ]
    count: Annotated[
        int | None,
        Field(description='그날의 토지거래허가 건수. 직방이 주지 않으면 모름(null)')
    ]


class ZigbangComplex(BaseModel):
    """직방 단지 정보. 아파트와 오피스텔 건물은 직방이 주는 정보가 달라 한쪽에만 있는 필드는 키를 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    property_type: Annotated[
        str,
        Field(description='아파트 또는 오피스텔')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소 (오피스텔은 동까지)')
    ] = None
    households: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    max_floor: Annotated[
        int | None,
        Field(description='최고 층수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수 (아파트만)')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD, 아파트만)')
    ] = None
    completed_at: Annotated[
        str | None,
        Field(description='준공 연월 (YYYY-MM, 오피스텔만)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사 (아파트만)')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수 (아파트만)')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%, 아파트만)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 방식 (아파트만)')
    ] = None
    elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 (오피스텔만). 있다고 확인되면 true, 그 밖에는 모름(null). 매물 상세의 elevator 가 정확하다')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수. 아파트는 같은 호·거래 유형을 묶은 수. 직방이 주지 않으면 모름(null)')
    ]
    article_counts: Annotated[
        dict[str, int | None],
        Field(description='거래 유형별 매물 수 (아파트만). 직방이 주지 않은 유형은 모름(null)')
    ] = {}
    pyeongs: Annotated[
        list[ZigbangPyeong],
        Field(description='평형 목록 (아파트만)')
    ] = []
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 학교군 안 가까운 중·고등학교 2곳씩 (아파트만, 예: 서울개원초등학교 (배정, 180m)). 모르면 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수 (아파트만). 후기 내용은 url 의 직방 단지 페이지에서 본다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    estimated_sale_price_min_manwon: Annotated[
        int | None,
        Field(description='단지 직방시세 매매 최저 (만원, 아파트만). 웹 전체 탭 "매매 18억 8,000 ~ 61억 1,000" 의 앞. 직방 추정값이고 실거래 평균이 아니다. 평형 정보를 받지 못했거나 0 이거나 없으면 null')
    ] = None
    estimated_sale_price_max_manwon: Annotated[
        int | None,
        Field(description='단지 직방시세 매매 최고 (만원, 아파트만). 웹 전체 탭 범위의 뒤. 0 이거나 없으면 null')
    ] = None
    estimated_sale_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='단지 평균 직방시세 매매의 평당 가격 (만원/3.3㎡, 아파트만). 웹 전체 탭 "평균 1억 235/3.3㎡". 0 이거나 없으면 null')
    ] = None
    estimated_jeonse_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='단지 평균 직방시세 전세의 평당 가격 (만원/3.3㎡, 아파트만). 0 이거나 없으면 null')
    ] = None
    rank: Annotated[
        ZigbangComplexRank | None,
        Field(description="단지 순위 (아파트만, 웹 '<동>에서 이 단지의 랭킹은?'). 직방이 구·동 순위를 주지 않으면 웹이 절을 숨기므로 null")
    ] = None
    related_complexes: Annotated[
        list[ZigbangRelatedComplex] | None,
        Field(description="웹 '함께 보면 좋은 단지' (아파트만, 직방이 준 순서). 직방이 주지 않으면 모름(null), 없으면 []")
    ] = None
    land_trade_permits: Annotated[
        list[ZigbangLandTradePermitDay] | None,
        Field(description="최근 7일 토지거래허가 일별 건수 (아파트만, 직방이 준 순서). 웹 '토지거래허가 총 N건 (최근 7일)' 과 날짜별 그래프. 직방이 주지 않으면 모름(null)")
    ] = None
    notes: Annotated[
        list[str],
        Field(exclude=True, description='후기가 있다는 안내와, 학군·평형 정보를 받지 못해 그 값을 모른다는 [실패] 안내. CLI 가 결과 위에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = OFFICETEL_ONLY_COMPLEX_FIELDS if self.property_type == '아파트' else APT_ONLY_COMPLEX_FIELDS
        for field in fields:
            data.pop(field, None)
        return data


class ZigbangComplexListingsResult(BaseModel):
    """단지 하나의 매물 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 단지 ID')
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
        Field(description='단지 목록에 아직 받지 않은 매물이 남았는지 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        # 아파트는 ZigbangAptListing 이라 서브클래스 필드(complex_id 등)까지 내보낸다
        list[SerializeAsAny[Listing]],
        Field(description='직방 목록 순서의 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def complex_candidate_of(item: ZigbangSearchItemModel) -> ZigbangComplexCandidate | None:
    """검색 결과 한 건을 단지 후보로 바꾼다. 아파트·오피스텔이 아니면 None."""
    kind = COMPLEX_KIND_BY_SEARCH_TYPE.get(item.type)
    if kind is None:
        return None
    source = item.source
    return ZigbangComplexCandidate(
        complex_id=f'{kind}-{item.id}',
        property_type=PROPERTY_TYPE_BY_COMPLEX_KIND[kind],
        name=item.name,
        address=normalize_address(item.description),
        households=source.household if source else None,
        approved_at=normalize_date(source.approval_date) if source else None,
    )


def search_regions_and_complexes(
    client: ZigbangClient,
    query: str,
) -> tuple[list[ZigbangSearchItemModel], list[ZigbangComplexCandidate]]:
    """이름으로 지역·역·학교와 아파트 단지·오피스텔 건물 후보를 함께 찾는다 (2회 호출, 관련도 순).

    직방 검색은 서비스 유형마다 다른 결과를 준다. 오피스텔로 찾으면 원룸으로 찾을 때와 같은
    지역·역·학교·대학교에 오피스텔 건물이 더해지고, 아파트로 찾아야 아파트 단지가 나온다
    (아파트로 찾으면 대학교가 빠진다). 그래서 오피스텔·아파트로 한 번씩 찾는다.
    예전 이름·별칭으로도 맞추므로 이름이 달라 보이는 후보가 섞일 수 있다.

    Returns:
        (지역 결과, 단지 후보). 지역 결과에는 단지가 없다.
    """
    # 후보 목록이라 하나를 고르지 않고 좌표(`search locations` 가 지역마다 lat·lng 로 낸다)를 그대로 내보낸다. 좌표 없는 후보는
    # 위치를 줄 수 없어 지금처럼 뺀다
    officetel_items = search_regions(client, query, service_type='오피스텔', require_coordinates=True)
    regions = [item for item in officetel_items if item.type not in COMPLEX_KIND_BY_SEARCH_TYPE]
    candidates: dict[str, ZigbangComplexCandidate] = {}
    for item in [*search_regions(client, query, service_type='아파트', require_coordinates=True), *officetel_items]:
        candidate = complex_candidate_of(item)
        if candidate is not None:
            candidates.setdefault(candidate.complex_id, candidate)
    return regions, list(candidates.values())


def _fetch_building(
    client: ZigbangClient,
    complex_id: str,
    parameter: ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
) -> ZigbangItemsOfficetelsBuildingV1ResponseModel:
    try:
        return client.run_request_items_officetels_building_v1(parameter)
    except HTTPStatusError as exc:
        # 없는 건물이면 404 가 아니라 400 ("오피스텔 건물을 찾을 수 없습니다") 이다. 필터 값 오류도 400 이지만 요청 모델
        # Literal·ge=0 이 서버 허용값과 같아 보내기 전에 막히고, 범위 역전 같은 조합은 200 빈 목록이다 (2026-10-11 실측)
        if exc.response.status_code in (400, 404):
            raise complex_not_found(complex_id) from None
        raise


NumberT = TypeVar('NumberT', bound=float)


def _positive_or_none(value: NumberT | None) -> NumberT | None:
    """0 이하이거나 빠진 값은 모름(None). 웹이 0 을 '시세없음'·'-' 로 그리고 관리비 줄을 숨기는 값에 쓴다 (평형 시세·관리비)."""
    return value if value is not None and value > 0 else None


def pyeong_of(room_type: ZigbangDanjiRoomTypeModel, detail: ZigbangDanjiRoomTypeModel | None) -> ZigbangPyeong:
    """단지 매물 목록의 평형(`room_type`: 목록의 출처·순서)에 평형 정보 조회(`detail`: 같은 ID)의 값을 붙인다. 없으면 새 값은 모름(null)."""
    title = room_type.room_type_title
    supply = detail.supply_area if detail else None
    exclusive = detail.exclusive_area if detail else None
    cost = detail.manage_cost if detail else None
    sales = detail.sales_price if detail else None
    rent = detail.rent_price if detail else None
    return ZigbangPyeong(
        id=room_type.id,
        name=title.m2 if title else None,
        pyeong_name=text_or_none(title.p) if title else None,
        supply_area_m2=supply.m2 if supply else None,
        supply_area_pyeong=supply.p if supply else None,
        exclusive_area_m2=exclusive.m2 if exclusive else None,
        exclusive_area_pyeong=exclusive.p if exclusive else None,
        households=detail.household_count if detail else None,
        room_count=detail.room_count if detail else None,
        bathroom_count=detail.bathroom_count if detail else None,
        entrance_type=text_or_none(detail.entrance_type) if detail else None,
        # 웹 ManageCost 는 평균 관리비가 0 이나 null 이면 여름·겨울이 든 줄 전체를 숨기고, 평균이 있을 때 여름·겨울이 0 이나 null 이면 '-' 로
        # 그린다 (2026-11-19 번들). jibsa 는 평균이 없어도 직방이 준 여름·겨울 값을 내므로 셋을 따로 거른다 (웹과 다른 점, 소스 가이드)
        manage_cost_manwon=_positive_or_none(cost.average) if cost else None,
        manage_cost_summer_manwon=_positive_or_none(cost.summer) if cost else None,
        manage_cost_winter_manwon=_positive_or_none(cost.winter) if cost else None,
        resale_available_from=iso_date(detail.resale_available_from) if detail else None,
        estimated_sale_price_manwon=_positive_or_none(sales.min) if sales else None,
        estimated_sale_price_per_pyeong_manwon=_positive_or_none(sales.per_area) if sales else None,
        estimated_jeonse_price_manwon=_positive_or_none(rent.min) if rent else None,
        estimated_jeonse_price_per_pyeong_manwon=_positive_or_none(rent.per_area) if rent else None,
    )


def complex_rank_of(rank: ZigbangDanjiRankModel | None) -> ZigbangComplexRank | None:
    """단지 상세의 순위를 웹 '<동>에서 이 단지의 랭킹은?' 절 값으로. 웹처럼 구·동 순위 중 하나라도 없으면 None.

    웹은 `!순위 || !순위.local2 || !순위.local3` 이면 절을 그리지 않는다 (2026-11-19 번들 `Components_Rank`). 순위 값 -1 은
    웹이 '순위 없음' 으로 그리는 값이다.
    """
    if rank is None or rank.local2 is None or rank.local3 is None:
        return None
    return ZigbangComplexRank(
        region=text_or_none(rank.local3.name),
        price_rank=None if rank.trade_price_rank == -1 else rank.trade_price_rank,
        popularity_rank=None if rank.view_count_rank == -1 else rank.view_count_rank,
    )


def _related_complexes_of(related: ZigbangRelateDanjiModel | None) -> list[ZigbangRelatedComplex] | None:
    """단지 상세의 관련 단지('함께 보면 좋은 단지')를 직방이 준 순서대로. 목록을 주지 않았으면(키 없음·null) 모름(None), 빈 목록이면 []."""
    if related is None or related.list is None:
        return None
    return [related_complex_of(item) for item in related.list]


def _land_trade_permits_of(permit: ZigbangLandTradePermitModel | None) -> list[ZigbangLandTradePermitDay] | None:
    """단지 상세의 최근 7일 토지거래허가 일별 건수를 직방이 준 순서대로. 일별 건수를 주지 않았으면(키 없음·null) 모름(None)."""
    if permit is None or permit.daily_counts is None:
        return None
    return [ZigbangLandTradePermitDay(date=iso_date(day.date), count=day.count) for day in permit.daily_counts]


def _fetch_room_types(
    client: ZigbangClient, danji_id: int,
) -> tuple[ZigbangDanjisRoomTypesResponseModel | None, list[str]]:
    """평형 정보 조회(덤)를 받는다. 실패(요청 제한 포함)하면 None 과 `[실패]` 안내를 준다."""
    try:
        return client.run_request_danjis_room_types(ZigbangDanjisRoomTypesRequestParameterModel(danji_id=danji_id)), []
    except SCHOOL_LOOKUP_ERRORS as exc:
        return None, [note(
            '실패',
            f'직방 평형 정보를 받지 못해({type(exc).__name__}) 평형별 면적·관리비·직방시세와 단지 직방시세를 모릅니다 '
            f'(url 의 직방 단지 페이지에서 확인){failure_update_hint(exc)}',
        )]


def get_complex(client: ZigbangClient, complex_id: str) -> ZigbangComplex:
    """단지 정보와 지금 올라온 매물 수를 모은다 (아파트 4회: 단지·매물 수·학군·평형 정보, 오피스텔 1회 호출).

    학군과 평형 정보(`room_types`, 평형 목록(매물 목록 응답의 `danjiRoomTypes`, 출처·순서는 그대로)에 면적·관리비·직방시세를
    붙인다)는 덤 조회라, 실패하면 그 값만 모름(null)이고 `[실패]` 안내가 붙는다. 순위·관련 단지·토지거래허가는 단지 정보 응답에 있어
    요청이 늘지 않는다.

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나 (INVALID_ARGUMENT) 없는 단지일 때 (NOT_FOUND).
    """
    kind, number = parse_complex_id(complex_id)
    if kind == 'officetel':
        building = _fetch_building(
            client, complex_id, ZigbangItemsOfficetelsBuildingV1RequestParameterModel(building_id=number)
        ).building
        established = building.established or ''
        return ZigbangComplex(
            complex_id=complex_id,
            name=building.name,
            property_type='오피스텔',
            # 건물 주소는 시·도를 줄여 주기도 한다 (2026-10-11 실측: '서울시 강남구 역삼동', '제주도 제주시 연동')
            address=normalize_address(building.address.full_text if building.address else None),
            households=to_int(building.household),
            max_floor=to_int(building.floor),
            completed_at=f'{established[:4]}-{established[4:6]}' if re.fullmatch(r'\d{6}', established) else None,
            # 건물 API 의 false 는 믿을 수 없어 모름으로 둔다. 2026-10-10 실측: 건물 53곳 중 false 30곳(6~41층)이
            # 모두 그 건물 매물 상세에서는 엘리베이터 있음이었고, false 가 맞은 곳은 없었다 (true 23곳은 모두 일치)
            elevator=True if building.elevator else None,
            # 매물이 없으면 itemCount 0 이 온다 (2026-10-10 실측 29곳). 빠지면 0 이 아니라 모름이다
            listing_count=building.item_count,
            url=officetel_building_url(number),
        )

    danji = fetch_danji(client, complex_id, number)
    catalogs = client.run_request_danjis_item_catalogs(
        ZigbangDanjisItemCatalogsRequestParameterModel(danji_id=number, limit=1)
    )
    school_notes: list[str] = []
    try:
        schools = danji_schools(client.run_request_danjis_schools(ZigbangDanjisSchoolsRequestParameterModel(danji_id=number)))
    except SCHOOL_LOOKUP_ERRORS as exc:
        # 학군을 못 받아도 단지 정보는 돌려준다 (모름)
        schools = None
        school_notes = [note(
            '실패',
            f'직방 단지 학군 정보를 받지 못해({type(exc).__name__}) schools 값을 모릅니다 (url 의 직방 단지 페이지에서 확인)'
            f'{failure_update_hint(exc)}',
        )]
    room_info, lookup_notes = _fetch_room_types(client, number)
    details = {room_type.id: room_type for room_type in room_info.room_types or []} if room_info else {}
    return ZigbangComplex(
        complex_id=complex_id,
        name=danji.name,
        # 아파트 API 로 받은 단지다. real_type('연립' 등)을 쓰면 오피스텔로 보고 아파트 필드를 지운다
        property_type='아파트',
        address=normalize_address(join_address(danji.local1, danji.jibun_address)),
        households=danji.households,
        max_floor=danji.max_floor,
        dong_count=danji.dong_count,
        approved_at=normalize_date(danji.approval_date),
        construction_company=danji.construction_company,
        parking_per_household=danji.parking_per_household,
        floor_area_ratio=danji.floor_area_ratio,
        heating=danji.heating,
        # 응답 모델은 totalCount 가 빠지면 페이지 계산용으로 0 을 채우지만, 여기서는 모름(null)이다 (실측 40곳 모두 왔다)
        listing_count=catalogs.total_count if 'total_count' in catalogs.model_fields_set else None,
        # 매물 없는 유형도 0 으로 온다 (2026-10-10 실측 40곳 모두 세 유형). 빠진 유형은 모름이다
        article_counts={
            trade: catalogs.count_by_tran_type.get(tran_type)
            for tran_type, trade in TRADE_BY_APT_TRAN_TYPE.items()
        },
        pyeongs=[pyeong_of(room_type, details.get(room_type.id)) for room_type in catalogs.room_types],
        schools=schools,
        review_count=danji.review_count,
        url=apt_danji_url(number),
        estimated_sale_price_min_manwon=_positive_or_none(room_info.min_sales_price) if room_info else None,
        estimated_sale_price_max_manwon=_positive_or_none(room_info.max_sales_price) if room_info else None,
        estimated_sale_price_per_pyeong_manwon=_positive_or_none(room_info.average_sales_price) if room_info else None,
        estimated_jeonse_price_per_pyeong_manwon=_positive_or_none(room_info.average_rent_price) if room_info else None,
        rank=complex_rank_of(danji.rank),
        related_complexes=_related_complexes_of(danji.relate_danji),
        land_trade_permits=_land_trade_permits_of(danji.land_trade_permit),
        notes=school_notes + lookup_notes + (
            [f'이 단지에 거주 후기 {danji.review_count}개가 있습니다. 후기 내용은 직방 단지 페이지({apt_danji_url(number)})에서 확인하세요']
            if danji.review_count else []
        ),
    )


def list_complex_listings(
    client: ZigbangClient,
    complex_id: str,
    *,
    conditions: ZigbangRoomConditions | None = None,
    pyeong_ids: list[int] | None = None,
    limit: int = 20,
) -> ZigbangComplexListingsResult:
    """단지 하나의 매물을 직방이 보여 주는 순서로 `limit` 건 조회한다.

    아파트는 단지 정보(시·도 주소용)와 단지 매물 목록(같은 호·거래 유형을 묶은 카탈로그)을 50건씩,
    오피스텔은 건물의 매물 핀·섹션을 받아 웹 건물 화면처럼 섹션 순서로 세운 뒤 15개씩 요약을 받는다
    (`_list_officetel_building_listings`). 거래 유형·가격(만원)·평형 조건은 서버에서
    거른다. 평형은 아파트만 있다. 관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔만 받으며
    건물 API 에 그대로 보내 서버에서 거른다.

    응답 목록에 빈 항목(null)이 섞여 오면 빼고 읽되 아파트는 직방 offset 이 그 자리도 세므로 받은 수(`offset`·`inspected`)에 더해 센다.
    오피스텔 건물은 핀·섹션의 빈 항목을 `[제외]` 로만 알린다 (`catalog_null_notes`·`pin_null_notes`).

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나, 오피스텔에 평형 조건을 줬거나,
            아파트에 오피스텔 전용 조건을 줬을 때 (INVALID_ARGUMENT).
            없는 단지일 때 (NOT_FOUND).
    """
    conditions = conditions or ZigbangRoomConditions()
    kind, number = parse_complex_id(complex_id)
    building_filters: dict[str, object] = {
        # 오피스텔 건물 매물은 섞지 않은 순서로 받는다 (지도 목록과 같다, room.search_listings). 아파트는 이 값을 쓰지 않는다
        'without_random': True if kind == 'officetel' else None,
        'room_types': [ROOM_TYPE_FILTER_BY_LABEL[room] for room in conditions.room_types],
        **room_filter_of(conditions),
    }
    if kind == 'apt' and any(value is not None and value != [] for value in building_filters.values()):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔 건물에서만 사용할 수 있습니다',
            hint='해당 조건을 빼거나 officetel-... 건물 ID 를 사용하세요',
        )
    trade_types = conditions.trade_types
    if kind == 'officetel':
        if pyeong_ids:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message='오피스텔 건물에는 평형 조건이 없습니다',
                hint='--pyeong 을 빼고 다시 조회하세요. 평형은 아파트 단지(apt-...)에만 있습니다',
            )
        return _list_officetel_building_listings(
            client, complex_id, number, conditions=conditions, limit=limit, filters=building_filters,
        )

    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    # 단지 매물 목록에는 시·도가 없어 단지 정보에서 받는다 (없는 단지도 여기서 알 수 있다)
    local1 = fetch_danji(client, complex_id, number).local1
    if trade_types and not tran_types:
        # 아파트에는 단기임대가 없다 (CLI 가 먼저 막는다). 조건을 비워 보내면 전체가 오므로 조회하지 않는다.
        # 없는 단지가 0건 성공으로 보이지 않도록 단지를 확인한 뒤에 돌려준다
        return ZigbangComplexListingsResult(complex_id=complex_id, total=0, returned=0, listings=[])
    listings: list[Listing] = []
    total = 0
    offset = 0
    inspected = 0
    # 목록에서 뺀 빈 항목 수와, 카탈로그의 묶인 매물 ID 목록에서 뺀 빈 항목 수 (`catalog_null_notes`)
    dropped_catalogs = 0
    dropped_id_lists = 0
    # 평형 목록(`danjiRoomTypes`)에서 뺀 빈 항목 수. 평형 ID 를 확인할 수 없을 때만 안내한다
    dropped_room_types = 0
    seen: set[str] = set()
    while inspected < limit:
        page_size = min(DANJI_CATALOG_PAGE_SIZE, limit - inspected)
        response = client.run_request_danjis_item_catalogs(
            ZigbangDanjisItemCatalogsRequestParameterModel(
                danji_id=number,
                tran_types=tran_types,
                room_type_ids=pyeong_ids or [],
                sales_price_min=conditions.price_min,
                sales_price_max=conditions.price_max,
                deposit_min=conditions.deposit_min,
                deposit_max=conditions.deposit_max,
                rent_min=conditions.rent_min,
                rent_max=conditions.rent_max,
                offset=offset,
                limit=page_size,
            )
        )
        if offset == 0:
            if response.null_items('room_types'):
                # 평형 목록에서 빈 항목을 뺐으면 준 평형 ID 가 그 항목이었을 수 있어 단지에 있는지 확인하지 않는다
                dropped_room_types = response.null_items('room_types') if pyeong_ids else 0
            else:
                _check_pyeong_ids(complex_id, response, pyeong_ids)
        total = response.total_count
        # 직방 offset 은 빈 항목(null)도 한 자리로 센다. 빈 항목을 빼고 읽었어도 받은 자리 수에 더해야 같은 매물을 다시 받거나 일찍 멈추지 않는다
        received = len(response.catalogs) + response.null_items('catalogs')
        dropped_catalogs += response.null_items('catalogs')
        dropped_id_lists += sum(catalog.null_items('item_id_list') for catalog in response.catalogs)
        inspected += received
        for catalog in response.catalogs:
            listing = catalog_to_listing(catalog, local1)
            if listing is not None and listing.id not in seen:
                seen.add(listing.id)
                listings.append(listing)
        offset += received
        if not received or offset >= total:
            break
    listings = listings[:limit]
    notes = apt_pagination_notes(
        # 단지 하나라 지역 대신 단지 매물의 조건만 좁히라고 한다 (오피스텔 건물·다방 단지 매물과 같다)
        len(listings), limit, inspected, has_more=offset < total, narrow='거래 유형·평형·가격 조건',
    ) + catalog_null_notes('직방 단지', dropped_catalogs, dropped_id_lists)
    if dropped_room_types:
        # 평형 ID 가 단지에 있는지 볼 수 없어 확인하지 않고 그 평형으로 찾았다
        notes.append(null_items_note('직방 단지 평형', dropped_room_types))
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=offset < total,
        listings=listings,
        notes=notes,
    )


def _check_pyeong_ids(complex_id: str, response: ZigbangDanjisItemCatalogsResponseModel, pyeong_ids: list[int] | None) -> None:
    """단지에 없는 평형이면 0건 대신 에러로 알린다. 단지 매물 목록은 없는 평형에도 빈 성공을 준다.

    평형 조건을 줘도 응답의 평형 목록(danjiRoomTypes)은 단지 전체라 첫 페이지로 확인한다 (2026-10-12 실측:
    apt-68579 에 평형 999 를 주면 0건과 평형 30개, 조건 없이도 같은 30개). 평형 목록이 비어 오면(평형이 아직 없는
    단지) 확인하지 않는다.

    Raises:
        JibsaError: 단지에 없는 평형 (INVALID_ARGUMENT).
    """
    known = {room_type.id for room_type in response.room_types}
    unknown = [pyeong_id for pyeong_id in pyeong_ids or [] if pyeong_id not in known]
    if known and unknown:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"{complex_id} 단지에 없는 평형 ID 입니다: {', '.join(map(str, unknown))}",
            hint=f'jibsa zigbang complex {complex_id} 결과의 pyeongs[].id 를 --pyeong 에 주세요',
        )


def _list_officetel_building_listings(
    client: ZigbangClient,
    complex_id: str,
    building_id: int,
    *,
    conditions: ZigbangRoomConditions,
    limit: int,
    filters: dict[str, object],
) -> ZigbangComplexListingsResult:
    """오피스텔 건물 하나의 매물을 웹 건물 화면 순서로 `limit` 건 조회한다 (건물 핀 1회 + 요약 15개에 1회).

    웹 건물 화면처럼 섹션 순서대로 매물 ID 를 잇는다 (2026-11-15 번들 `loadItemsV2`: `sections.flatMap(ids)`. 실측
    officetel-20227: 핀 순서는 51154972·51094170·51155651 인데 섹션은 안심추천 51094170·51155651, 안심일반 51154972). 핀
    순서는 이 순서와 달라 쓰지 않고, 어느 섹션에도 없는 핀만 잃지 않게 맨 뒤에 핀 순서로 붙인다 (지도 목록과 같은
    `section_ordered_ids`). 섹션 안은 서버가 섞지 않은 순서(`withoutRandom`)로 받는다. 앞 `limit` 개의 요약을 받아 그 순서대로 낸다.
    """
    response = _fetch_building(
        client,
        complex_id,
        ZigbangItemsOfficetelsBuildingV1RequestParameterModel(
            building_id=building_id,
            sales_types=[SALES_TYPE_BY_TRADE[trade] for trade in conditions.trade_types],
            deposit_min=conditions.deposit_min,
            deposit_max=conditions.deposit_max,
            rent_min=conditions.rent_min,
            rent_max=conditions.rent_max,
            sales_price_min=conditions.price_min,
            sales_price_max=conditions.price_max,
            **filters,
        )
    )
    ids = section_ordered_ids([response])
    # 조회 예산은 요약을 받는 매물 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    scanned = ids[:limit]
    tradeable = tradeable_summaries(client, scanned)
    summaries = {summary.item_id: summary for summary in tradeable.items}
    # 요약 응답 순서에 기대지 않고 섹션 순서로 세운다
    listings: list[Listing] = [
        summary_to_listing(summaries[item_id], building_id=building_id) for item_id in scanned if item_id in summaries
    ]
    # 건물 매물은 서버가 거래 유형으로 이미 걸러 준 거래 중 매물뿐이라 매물 수가 곧 조건에 맞는 수다.
    total = len(ids)
    has_more = len(scanned) < total
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=(
            # 아래 [일부] 안내의 '직방 목록 순으로' 와 같은 말로 쓴다 (한 응답에 '순서로'·'순으로' 가 섞였다, 2026-11-10 리뷰)
            excluded_notes(
                limit, len(scanned), len(listings), order='직방 목록 순으로 앞의', has_more=has_more,
                null_items=tradeable.null_items,
            )
            # 요약을 받은 핀 수(inspected)로 limit 에 닿았는지 본다. 받은 뒤 거래 불가로 뺀 만큼 다시 채우지 않아, 돌려준 수로
            # 보면 1건만 빠져도 안내가 사라진다. 단지 하나라 지역·반경 대신 단지 매물의 조건만 좁히라고 한다. 오피스텔 건물에는
            # 평형 조건이 없어(--pyeong 은 INVALID_ARGUMENT) 오피스텔에만 있는 방 구조·면적 조건을 권한다 (2026-11-10 실측:
            # officetel-2795 --limit 5 에 '평형' 을 권했다)
            + limit_notes(
                total, len(listings), limit, max_limit=MAX_LIST_LIMIT, order='직방 목록',
                narrow='거래 유형·방 구조·면적·가격 조건', inspected=len(scanned), has_more=has_more,
            )
            + pin_null_notes('직방 오피스텔 건물 매물 핀·섹션', [response])
        ),
    )
