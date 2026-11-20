"""동네 후기 요약 (region-reviews)."""

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    join_address,
    more_hint,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.review import (
    DaangnLivedReviewsByRegionRequestPayloadModel,
    DaangnMapReviewsRequestParameterModel,
)
from jibsa.providers.daangn.api.response.review import (
    DaangnMapReviewsResponseModel,
    DaangnReviewComplexModel,
)
from jibsa.providers.daangn.service.common import (
    COMPLEX_TYPE_LABELS,
    code_label,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    DaangnRealsaleRegion,
    resolve_realsale_region,
)

from typing import (
    Annotated,
    Any,
)


# `--top`(후기 많은 단지·건물 수)의 기본값과 최대값. 동 후기 페이지가 단지를 500곳까지 준다
TOP_DEFAULT: int = 20
TOP_MAX: int = 500
# 당근 후기 페이지가 단지를 주는 수. 구 후기 페이지와 구가 없는 시(세종)의 동 페이지는 20곳(reviewsDistrictQuery first:20),
# 동 후기 페이지는 500곳이다 (2026-11-20 실측: 역삼동 260곳 중 후기가 있는 단지 154곳)
DISTRICT_PAGE_COMPLEXES: int = 20
DONG_PAGE_COMPLEXES: int = 500


def map_url(*names: str, suffix: str = '') -> str:
    """지도 페이지 URL. 구가 없는 시(세종)는 구 세그먼트를 뺀다.

    LLM 과 사람이 읽도록 한글은 그대로 두고 공백만 인코딩한다 (브라우저는 그대로 연다).
    """
    path = '/'.join(name.replace(' ', '%20') for name in names if name)
    return f'https://realty.daangn.com/map/{path}{suffix}'


class DaangnReviewComplex(BaseModel):
    """거주 후기가 많은 단지."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘기면 그 단지의 후기 수와 단지 페이지가 나온다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름. 당근이 주지 않으면 null')
    ] = None
    property_type: Annotated[
        str | None,
        Field(description='단지 유형. 당근이 주지 않으면 null. 동으로 찾으면 동 후기 페이지가 유형을 주지 않아 늘 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수')
    ] = None


class DaangnReviewDong(BaseModel):
    """거주 후기가 있는 동 (구의 후기 페이지)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동 이름 (예: 역삼동)')
    ]
    region_id: Annotated[
        int,
        Field(description='동의 당근 지역 ID')
    ]
    review_count: Annotated[
        int | None,
        Field(description='그 동의 거주 후기 수')
    ] = None
    url: Annotated[
        str,
        Field(description='그 동의 당근 동네 후기 페이지')
    ]


class DaangnReviewBuilding(BaseModel):
    """거주 후기가 있는 건물. 단지가 아닌 건물(빌라·상가주택 등)도 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    building_id: Annotated[
        str,
        Field(description='당근 건물 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='건물 이름. 이름이 없는 건물이 많아 그때는 null (주소로 알아본다)')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소. 당근이 주지 않으면 null')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소. 당근이 주지 않으면 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='그 건물의 거주 후기 수')
    ] = None
    url: Annotated[
        str,
        Field(description='그 건물의 당근 후기 페이지 (건물 후기는 여기서 본다)')
    ]


class DaangnRegionReviews(BaseModel):
    """동네 거주 후기 안내. 후기 본문과 당근이 만든 요약 글은 담지 않는다 (url 의 원 사이트에서 본다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    has_reviews: Annotated[
        bool | None,
        Field(description='동네 후기가 있는지. 당근이 후기 수를 주지 않고 후기 미리보기·후기 많은 단지·건물·동 목록도 비어 있으면 null(모름)')
    ]
    review_count: Annotated[
        int | None,
        Field(description='동네 후기 수 (당근 웹 모바일 후기 화면의 "후기 N개"와 같은 실제 수). 동·구 모두 있다. 당근이 주지 않으면 null')
    ] = None
    dongs: Annotated[
        list[DaangnReviewDong] | None,
        Field(description='구로 찾았을 때 그 구에서 거주 후기가 있는 동과 동별 후기 수 (당근 순서인 후기 많은 순, 자르지 않는다). 동으로 찾으면 키가 없다. 당근 구 후기 페이지가 없어 모르면 null')
    ] = []
    top_complexes: Annotated[
        list[DaangnReviewComplex] | None,
        Field(description='후기가 있는 단지 (후기 많은 순, --top 개까지). 구로 찾으면 그 구의 단지 (당근 구 후기 페이지가 후기 많은 단지를 20곳까지만 줘 더 있을 수 있다), 동으로 찾으면 그 동의 단지 (동 후기 페이지가 500곳까지 주고 후기 없는 단지가 뒤에 붙어, 후기 있는 단지는 대개 다 온다), 구가 없는 시(세종)의 동은 그 동의 단지 (구 후기 페이지 모양이라 20곳까지). 단지 ID 가 없는 것은 뺀다. 후기 페이지가 없어 모르면 null')
    ] = []
    top_buildings: Annotated[
        list[DaangnReviewBuilding] | None,
        Field(description='후기가 있는 건물 (후기 많은 순, --top 개까지). 구로 찾으면 그 구의 건물, 동으로 찾으면 그 동의 건물 (당근은 개수를 제한하지 않는다). 후기 페이지가 없어 모르면 null')
    ] = []
    url: Annotated[
        str,
        Field(description='당근 동네 후기 페이지 (동이면 그 동의 후기 페이지, 구가 없는 시는 동 이름을 구 자리에 둔 후기 페이지). 후기 페이지가 없으면 당근 지도 페이지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='후기를 원 사이트에서 보라는 안내. CLI 가 결과 위에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 동별 후기 수는 구의 후기 페이지에만 있어 동으로 찾으면 해당 없음이라 키를 뺀다
        data: dict[str, Any] = handler(self)
        if self.region.level == '동':
            data.pop('dongs', None)
        return data


def _more_top_hint(top: int) -> str:
    """`--top` 을 늘리라는 안내 끝말 (이 명령은 `--limit` 이 아니라 `--top` 으로 개수를 정한다)."""
    return more_hint(top, TOP_MAX, None, option='--top')


def _cut_note(label: str, total: int, top: int, *, page_name: str | None = None) -> str | None:
    """`--top` 으로 잘랐을 때 [일부] 안내. 후기가 있는 `label`(단지·건물)이 `total` 곳이다.

    `page_name`(동·구)을 주면 당근 후기 페이지가 상한만큼만 준 수라는 뜻으로 '페이지가 준 단지 N곳' 이라 쓴다
    (그 수가 지역의 전체 단지 수로 읽히지 않게).
    """
    if total <= top:
        return None
    if page_name:
        return note('일부', f'당근 {page_name} 후기 페이지가 준 {label} {total}곳 중 앞 {top}곳입니다. {_more_top_hint(top)}')
    return note('일부', f'후기가 있는 {label} {total}곳 중 앞 {top}곳입니다. {_more_top_hint(top)}')


def _dong_guide(region: DaangnRealsaleRegion, dongs: list[DaangnReviewDong] | None, topic: str) -> str:
    """구로 찾아 더 못 볼 때 동으로 좁히라는 안내 끝말 (앞에 마침표를 붙인다). `topic` 은 조사까지 쓴 '건물은'·'단지는'. 구가 아니거나 동 목록이 없으면 빈 글자."""
    if region.level != '구' or not dongs:
        return ''
    # 그대로 다시 넣으면 찾히는 이름이다 (`DaangnArea.full_name` 과 같은 꼴)
    full_name = join_address(region.name1, region.name2, dongs[0].name)
    return f". 동의 {topic} jibsa daangn region-reviews '{full_name}' 으로 보세요"


def _review_dongs(region: DaangnRealsaleRegion, page: DaangnMapReviewsResponseModel, notes: list[str]) -> list[DaangnReviewDong] | None:
    """구 후기 페이지의 동별 후기 수. 당근 순서 그대로 자르지 않는다. 키가 없으면 None(모름)."""
    if page.dongs is None:
        return None
    dongs: list[DaangnReviewDong] = []
    nameless = 0
    for dong in page.dongs:
        # 웹은 동 이름을 못 찾은 동을 그리지 않는다 (번들 index 청크). 뺀 수는 알린다
        if not dong.name:
            nameless += 1
            continue
        dongs.append(
            DaangnReviewDong(
                name=dong.name,
                region_id=dong.region_id,
                review_count=dong.lived_review_count,
                url=map_url(region.name1, region.name2, dong.name, suffix='/reviews'),
            )
        )
    if nameless:
        notes.append(note('제외', f'동 이름을 찾지 못한 {nameless}곳은 뺐습니다'))
    return dongs


def _review_buildings(
    region: DaangnRealsaleRegion,
    page: DaangnMapReviewsResponseModel,
    dongs: list[DaangnReviewDong] | None,
    top: int,
    notes: list[str],
) -> list[DaangnReviewBuilding] | None:
    """후기가 있는 건물 `top` 곳까지 (당근 순서). 키가 없으면 None(모름)."""
    if page.buildings is None:
        return None
    cut = _cut_note('건물', len(page.buildings), top)
    if cut:
        # `--top` 이 이미 최대값이면 늘릴 수 없으니 구는 동으로 좁혀 보게 한다
        notes.append(cut + (_dong_guide(region, dongs, '건물은') if top >= TOP_MAX else ''))
    return [
        DaangnReviewBuilding(
            building_id=building.original_id,
            name=building.building_name,
            road_address=building.road_address,
            jibun_address=building.jibun_address,
            review_count=building.lived_review_count,
            url=f'https://realty.daangn.com/lived-reviews/buildings/{building.original_id}',
        )
        for building in page.buildings[:top]
    ]


def _review_complexes(
    region: DaangnRealsaleRegion,
    page: DaangnMapReviewsResponseModel,
    dongs: list[DaangnReviewDong] | None,
    *,
    dong_page: bool,
    top: int,
    notes: list[str],
) -> list[DaangnReviewComplex]:
    """후기가 있는 단지 `top` 곳까지 (당근 순서). 당근 페이지가 단지를 상한만큼 줬으면 알린다."""
    # 리뷰 오탐 (2026-11-19): 웹 후기 페이지 loader 도 livedReviewCount > 0 인 단지만 그린다 (번들 index 청크 reviewsDistrictQuery 뒤
    # filter). 영양군은 0·null 7곳이라 웹에도 단지 후기 모음이 없다. 동 후기 페이지(500곳)도 후기 없는 단지를 뒤에 null·0 으로 준다
    reviewed = [item for item in page.complexes if item.lived_review_count]
    # ID 가 없는 단지는 complex 로 이어 볼 수 없어 뺀다. 뺀 뒤의 수로 자르기 안내를 센다
    candidates: list[tuple[str, DaangnReviewComplexModel]] = []
    for item in reviewed:
        if item.original_id is not None and item.original_id.strip():
            candidates.append((item.original_id, item))
    no_id_count = len(reviewed) - len(candidates)
    page_name = '동' if region.level == '동' else '구'
    page_cap = DONG_PAGE_COMPLEXES if dong_page else DISTRICT_PAGE_COMPLEXES
    # 상한에 닿았어도 마지막 단지가 후기 없는 단지(0·null)면 후기 있는 단지는 다 받은 것이다. 후기 없는 단지가 뒤에 붙어서다
    # (2026-11-20 화곡동 실측 한 곳: 동 후기 페이지 500곳 중 후기 있는 298곳이 앞에, 0 뒤에 0 아닌 값 0건). 구 페이지는 20곳이 모두
    # 후기가 있어(강남구) 늘 상한에 닿는다
    capped = len(page.complexes) >= page_cap and bool(page.complexes[-1].lived_review_count)
    cut = _cut_note('단지', len(candidates), top, page_name=page_name if capped else None)
    if cut:
        notes.append(cut)
    if capped:
        # 당근이 단지를 상한만큼 줬으니 더 있을 수 있다. 구·세종 동 페이지의 20곳은 기본 `--top`(20)에서도 전부로 읽히지 않게 --top 과
        # 상관없이 알린다 (2026-11-20 사용자 결정)
        if dong_page:
            notes.append(note('일부', f'당근 동 후기 페이지는 단지를 {page_cap}곳까지만 줍니다. 후기가 있는 단지가 더 있을 수 있습니다'))
        else:
            dong_guide = _dong_guide(region, dongs, '단지는')
            notes.append(note('일부', f'당근 {page_name} 후기 페이지는 후기 많은 단지를 {page_cap}곳까지만 줍니다{dong_guide}'))
    if no_id_count:
        notes.append(note('제외', f'당근이 단지 ID 를 주지 않은 후기 단지 {no_id_count}곳은 뺐습니다'))
    return [
        DaangnReviewComplex(
            complex_id=complex_id,
            name=item.name if item.name and item.name.strip() else None,
            # 동 후기 페이지의 단지 레코드는 유형(type)이 일부에만 실려 있어(역삼동 260곳 중 9곳) 쓰지 않는다
            property_type=None if dong_page else code_label(COMPLEX_TYPE_LABELS, item.type),
            review_count=item.lived_review_count,
        )
        for complex_id, item in candidates[:top]
    ]


def get_region_reviews(
    client: DaangnClient,
    query: str,
    *,
    top: int = TOP_DEFAULT,
) -> DaangnRegionReviews:
    """동·구의 거주 후기가 있는지, 몇 개인지, 후기가 많은 단지·건물과 (구는) 동별 후기 수를 알려 준다. 후기 내용은 담지 않는다.

    후기 수는 당근 웹 후기 목록(`RegionLivedReviewListPanelQuery`)이 함께 받는 지역의 후기 수(`reviewRegion.livedReviewCount`)다.
    웹은 이 수를 모바일 화면의 '당근 앱에서 후기 N개 더 보기' 로 보여 준다. 예전에는 동네 요약(`regionByOriginalRegionId`)의
    요약에 쓰인 후기 수를 써서 60 에서 잘리고 구는 null 이었다 (2026-11-12 실측: 역삼동 1563·강남구 7132, #215). 단지·건물·동별 후기 수는
    그 지역의 후기 페이지에서 한 번에 받는다 (요청 1회): 구는 구 후기 페이지(단지 20곳까지, 동별 후기 수, 건물), 동은 동 후기 페이지
    (단지 500곳까지, 건물. 동이 속한 구의 페이지는 받지 않는다). 구가 없는 시(세종)의 동은 웹처럼 동 이름을 구 자리에 넣은 후기
    페이지(`/map/세종특별자치시/반곡동/reviews`, 구 후기 페이지 모양이라 단지 20곳까지)에서 받고, 세종 전체로 찾았거나 후기
    페이지가 404 면 받지 못한다 (404 는 `top_complexes`·`top_buildings`·구는 `dongs` 도 null).

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        RateLimitedError: 요청 제한에 걸렸을 때.
        JibsaError: 후기 목록이 실패하면 UPSTREAM_ERROR.
    """
    region, notes = resolve_realsale_region(client, query)

    reviews_response = client.run_request_lived_reviews_by_region(
        DaangnLivedReviewsByRegionRequestPayloadModel(region_id=region.region_id)
    )
    connection = unwrap_graphql(
        reviews_response, reviews_response.data.lived_reviews_by_region if reviews_response.data else None, '동네 후기', conditions=False
    )
    review_region = reviews_response.data.review_region if reviews_response.data else None
    review_count = review_region.lived_review_count if review_region else None

    dongs: list[DaangnReviewDong] | None = []
    top_complexes: list[DaangnReviewComplex] | None = []
    top_buildings: list[DaangnReviewBuilding] | None = []
    # 구가 없는 시(세종)는 동 이름이 구 자리에 온다 (웹 번들 index 청크 `cityDirectDong`). 세종 전체(동도 없음)는 후기 페이지가 없다
    district = region.name2 or region.name3
    reviews_page = False
    if region.name1 and district:
        # 동이면 그 동의 후기 페이지(`/map/{시·도}/{구}/{동}/reviews`), 구면 구의 후기 페이지. 세종 동은 구 자리에 동 이름을 둔 구 페이지 모양이라 동 페이지가 아니다
        dong_page = region.level == '동' and bool(region.name2)
        names = (region.name1, region.name2, region.name3) if region.level == '동' else (region.name1, region.name2)
        url = map_url(*names, suffix='/reviews')
        reviews_page = True
        try:
            page = client.run_request_map_reviews(
                DaangnMapReviewsRequestParameterModel(
                    name1=region.name1,
                    name2=district,
                    name3=region.name3 if dong_page else None,
                    region_id=region.region_id,
                )
            )
        except HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            url = map_url(region.name1, region.name2, region.name3)
            reviews_page = False
            dongs = top_complexes = top_buildings = None
            unknown = '후기 많은 단지·건물과 동별 후기 수는' if region.level == '구' else '후기 많은 단지·건물은'
            notes.append(note('실패', f'당근 동네 후기 페이지가 없어(404) {unknown} 모릅니다'))
        else:
            if region.level == '구':
                dongs = _review_dongs(region, page, notes)
            top_complexes = _review_complexes(region, page, dongs, dong_page=dong_page, top=top, notes=notes)
            top_buildings = _review_buildings(region, page, dongs, top, notes)
    else:
        url = map_url(region.name1, region.name2, region.name3)

    # 후기 수가 1 이상이거나 미리보기가 있으면 있음, 후기 수가 0 이면 없음. 당근이 후기 수를 주지 않으면(None) 후기가 있는 단지·건물·동이
    # 있을 때만 있음이고 그 밖에는 모름이다 (모름을 없음으로 말하지 않는다)
    has_reviews: bool | None
    if review_count or connection.edges:
        has_reviews = True
    elif review_count is None:
        has_reviews = True if (top_complexes or top_buildings or dongs) else None
    else:
        has_reviews = False

    if has_reviews or top_complexes or top_buildings or dongs:
        page_name = '당근 동네 후기 페이지' if reviews_page else '당근 지도 페이지'
        building_guide = ', 건물 후기는 top_buildings 의 url 에서' if top_buildings else ''
        notes.append(f'후기 내용은 {page_name}({url})에서 확인하세요. 단지 후기는 daangn complex 의 url 에서{building_guide} 봅니다')
    elif has_reviews is None:
        notes.append(note('실패', f'당근이 후기 수를 주지 않아 이 지역에 후기가 있는지 모릅니다. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'))
    else:
        # 리뷰 오탐 (2026-11-20): 후기 페이지 404 의 [실패] 와 이 안내가 함께 나가도 고치지 않는다. 이 안내는 has_reviews 가
        # False(후기 수가 0 이고 후기 미리보기도 빔)이면서 단지·건물·동 목록도 비어 있을 때만 나간다. 후기 수를 모르면 위의 [실패] 다
        # (404 는 후기 많은 단지·건물 목록을 모른다는 뜻이라 후기 수가 0 이라는 사실과 어긋나지 않는다)
        notes.append('이 지역에는 당근 동네 후기가 아직 없습니다')
    return DaangnRegionReviews(
        region=region,
        has_reviews=has_reviews,
        review_count=review_count,
        dongs=dongs,
        top_complexes=top_complexes,
        top_buildings=top_buildings,
        url=url,
        notes=notes,
    )
