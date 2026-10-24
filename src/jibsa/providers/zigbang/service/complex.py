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
    join_address,
    normalize_address,
    normalize_date,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.complex import (
    ZigbangDanjisSchoolsRequestParameterModel,
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangDanjisItemCatalogsResponseModel,
    ZigbangSearchItemModel,
)
from jibsa.providers.zigbang.api.response.complex import (
    ZigbangDanjisSchoolsResponseModel,
    ZigbangItemsOfficetelsBuildingV1ResponseModel,
)
from jibsa.providers.zigbang.service.common import (
    APT_TRAN_TYPE_BY_TRADE,
    DANJI_CATALOG_PAGE_SIZE,
    NEAREST_SCHOOLS,
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    SCHOOL_LOOKUP_ERRORS,
    TRADE_BY_APT_TRAN_TYPE,
    ComplexKind,
    ZigbangRoomConditions,
    apt_danji_url,
    apt_pagination_notes,
    catalog_to_listing,
    complex_not_found,
    excluded_notes,
    fetch_danji,
    parse_complex_id,
    room_filter_of,
    school_label,
    summary_to_listing,
    tradeable_summaries,
)
from jibsa.providers.zigbang.service.region import (
    search_regions,
    to_int,
)

from typing import (
    Annotated,
    Any,
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
})
OFFICETEL_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({'completed_at', 'elevator'})


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
    notes: Annotated[
        list[str],
        Field(exclude=True, description='후기가 있다는 안내. CLI 가 결과 위에 붙인다')
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
    officetel_items = search_regions(client, query, service_type='오피스텔')
    regions = [item for item in officetel_items if item.type not in COMPLEX_KIND_BY_SEARCH_TYPE]
    candidates: dict[str, ZigbangComplexCandidate] = {}
    for item in [*search_regions(client, query, service_type='아파트'), *officetel_items]:
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


def get_complex(client: ZigbangClient, complex_id: str) -> ZigbangComplex:
    """단지 정보와 지금 올라온 매물 수를 모은다 (아파트 3회: 단지·매물 수·학군, 오피스텔 1회 호출).

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
    try:
        schools = danji_schools(client.run_request_danjis_schools(ZigbangDanjisSchoolsRequestParameterModel(danji_id=number)))
    except SCHOOL_LOOKUP_ERRORS:
        # 학군을 못 받아도 단지 정보는 돌려준다 (모름)
        schools = None
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
        pyeongs=[
            ZigbangPyeong(
                id=room_type.id,
                name=room_type.room_type_title.m2 if room_type.room_type_title else None,
                pyeong_name=room_type.room_type_title.p if room_type.room_type_title else None,
            )
            for room_type in catalogs.room_types
        ],
        schools=schools,
        review_count=danji.review_count,
        url=apt_danji_url(number),
        notes=[
            f'이 단지에 거주 후기 {danji.review_count}개가 있습니다. 후기 내용은 직방 단지 페이지({apt_danji_url(number)})에서 확인하세요'
        ] if danji.review_count else [],
    )


def complex_limit_notes(total: int, returned: int, limit: int, inspected: int) -> list[str]:
    # 요약을 받은 핀 수(`inspected`)로 limit 에 닿았는지와 남은 핀이 있는지 본다. 받은 뒤 거래 불가로 뺀 만큼 다시 채우지 않아,
    # `returned` 로 보면 1건만 빠져도 안내가 사라지거나(limit) 핀을 다 받았는데 '더 있다' 고 한다(total)
    if inspected < limit or total <= inspected:
        return []
    return [
        f'조건에 맞는 매물이 {total}건이라 직방 목록 순서로 앞의 {returned}건만 보여 줍니다. '
        '--limit 을 늘리거나 거래 유형·평형·가격 조건을 좁히세요'
    ]


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
    오피스텔은 건물의 매물 핀을 받아 15개씩 요약을 받는다. 거래 유형·가격(만원)·평형 조건은 서버에서
    거른다. 평형은 아파트만 있다. 관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔만 받으며
    건물 API 에 그대로 보내 서버에서 거른다.

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나, 오피스텔에 평형 조건을 줬거나,
            아파트에 오피스텔 전용 조건을 줬을 때 (INVALID_ARGUMENT).
            없는 단지일 때 (NOT_FOUND).
    """
    conditions = conditions or ZigbangRoomConditions()
    kind, number = parse_complex_id(complex_id)
    if conditions.without_random and kind != 'officetel':
        raise JibsaError(
            code='INVALID_ARGUMENT', message='무작위 섞기 해제는 오피스텔 건물에만 지원됩니다',
            hint='officetel-... 건물 ID를 사용하거나 --without-random을 빼세요',
        )
    building_filters: dict[str, object] = {
        'without_random': True if conditions.without_random else None,
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
            _check_pyeong_ids(complex_id, response, pyeong_ids)
        total = response.total_count
        inspected += len(response.catalogs)
        for catalog in response.catalogs:
            listing = catalog_to_listing(catalog, local1)
            if listing is not None and listing.id not in seen:
                seen.add(listing.id)
                listings.append(listing)
        offset += len(response.catalogs)
        if not response.catalogs or offset >= total:
            break
    listings = listings[:limit]
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=offset < total,
        listings=listings,
        notes=apt_pagination_notes(len(listings), limit, inspected, has_more=offset < total),
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
    ids = [pin.id for pin in response.items]
    # 조회 예산은 요약을 받는 핀 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    scanned = ids[:limit]
    listings: list[Listing] = [
        summary_to_listing(summary, building_id=building_id) for summary in tradeable_summaries(client, scanned)
    ]
    if filters.get('without_random'):
        # 요약 응답의 순서가 달라도 서버가 반환한 핀 순서를 유지한 뒤 limit을 적용한다.
        rank = {str(item_id): index for index, item_id in enumerate(ids)}
        listings.sort(key=lambda listing: rank[listing.id])
    listings = listings[:limit]
    # 건물 핀은 서버가 거래 유형으로 이미 걸러 준 거래 중 매물뿐이라 핀 수가 곧 조건에 맞는 수다.
    total = len(ids)
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=len(scanned) < total,
        listings=listings,
        notes=(
            excluded_notes(limit, len(scanned), len(listings), order='직방 목록 순서로 앞의', has_more=len(scanned) < total)
            + complex_limit_notes(total, len(listings), limit, len(scanned))
        ),
    )
