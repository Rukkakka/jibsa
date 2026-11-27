"""요청 모델: 역·학교·동·구 주변 아파트 단지 (search complexes)."""


from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.models.request.common import index_arrays

from typing import (
    Annotated,
    Any,
    Literal,
)


# 아파트 단지 목록의 단지 종류. 웹은 늘 셋을 모두 보낸다 (2026-11-15 번들 `getAPTTypedListIds`: apt·offer(분양)·preOffer(분양 예정))
ZigbangDanjiServiceType = Literal['apt', 'offer', 'preOffer']
# 아파트 단지 목록(`ids`·`details`)이 무엇의 주변인지. 웹 아파트 지도의 역(`/home/apt/subways/{id}`)·학교(`/home/apt/schools/{학교코드}`)·
# 동(`/home/apt/locals/{법정동코드}`) 화면이 각각 보낸다 (2026-11-19 웹 캡처·번들)
ZigbangDanjiPlaceType = Literal['subway', 'school', 'local']
# 아파트 단지 목록의 순서. 웹 탭 이름: viewCount 많이 본 순(주변단지), newest 최근입주, priceChange 1주 시세 급변동, areaPrice 평당가 높은 순
ZigbangDanjiOrder = Literal['viewCount', 'newest', 'priceChange', 'areaPrice']


class ZigbangSubwaysRequestParameterModel(RequestModel):
    """`GET /apt/subways/{subwayId}` 경로. 역 정보와 역 주변 아파트 단지 (거리순)."""

    subway_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='직방 역 ID (지역 검색 결과의 역 id 와 같다). 경로에 들어간다')
    ]


class ZigbangSchoolsRequestParameterModel(RequestModel):
    """`GET /apt/schools/{schoolCode}` 경로 + 쿼리. 학교 정보와 학교 주변 아파트 단지 (웹 학교 화면 `/home/apt/schools/{학교코드}`)."""

    school_code: Annotated[
        str,
        Field(
            pattern=r'^[A-Za-z0-9]+$',
            exclude=True,
            description="학교 코드 (예: 'B100006434', 지역 검색 학교 결과의 `_source.school_code`). 경로에 들어간다"
        )
    ]
    gender_nullable: Annotated[
        bool,
        Field(description='웹이 늘 true 로 보낸다 (2026-11-19 웹 캡처)', alias='genderNullable')
    ] = True


class ZigbangDanjisIdsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/ids` 쿼리. 역·학교·동 주변 아파트 단지 ID 를 웹 목록 순서로.

    웹 아파트 지도의 '<역> 주변단지' 패널이 `type=subway&id=…&order=viewCount&limit=5` 와 단지 종류 셋으로 부른다
    (2026-11-15 캡처·번들 `getAPTTypedListIds`). 더보기 화면은 `limit` 없이 모든 ID 를 받아 15곳씩 카드 내용을 받는다.
    쪽 넘김(offset)은 없다. 웹 탭(`order`)은 viewCount 많이 본 순, newest 최근입주, priceChange 1주 시세 급변동,
    areaPrice 평당가 높은 순이다. 학교 화면(`/home/apt/schools/{학교코드}`)은 `type=school`, 동 화면
    (`/home/apt/locals/{법정동코드}`)의 최근입주 패널은 `type=local&order=newest` 로 부른다 (2026-11-19 캡처·번들).
    2026-11-19 실측: `type=school&id=1056&order=viewCount` → count 79, `type=local&id=11710107&order=newest&limit=5` →
    {count:1, ids:[88494]}. 학교 `id` 에 학교 코드('B100006434')를 넣으면 서버가 500 이다 (학교 상세 `detail.id` 를 쓴다).
    """

    search_type: Annotated[
        ZigbangDanjiPlaceType,
        Field(description='무엇의 주변 단지인지 (subway 역, school 학교, local 동·구)', alias='type')
    ]
    place_id: Annotated[
        int,
        Field(
            gt=0,
            description=(
                '`search_type` 에 맞는 ID. 역이면 직방 역 ID, 학교면 학교 상세의 `detail.id` (학교 코드가 아니다), 동·구면 법정동 코드 '
                '앞 8자리(동)나 5자리(구)를 정수로'
            ),
            alias='id'
        )
    ]
    order: Annotated[
        ZigbangDanjiOrder,
        Field(description='순서. 웹 탭: viewCount 많이 본 순, newest 최근입주, priceChange 1주 시세 급변동, areaPrice 평당가 높은 순')
    ] = 'viewCount'
    limit: Annotated[
        int | None,
        Field(ge=1, description='받을 단지 수. 없으면 모두')
    ] = None
    service_types: Annotated[
        list[ZigbangDanjiServiceType],
        Field(description='단지 종류. 웹처럼 셋을 모두 보낸다', alias='serviceType')
    ] = ['apt', 'offer', 'preOffer']

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return index_arrays(handler(self))


class ZigbangDanjisDetailsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/details` 쿼리. 단지 카드(이름·주소·세대수·탭별 둘째 줄)를 한 번에 최대 15곳.

    웹 더보기 화면이 `danjis/ids` 로 받은 ID 를 15곳씩 이 API 로 보내 카드를 그린다 (2026-11-19 캡처). `apts[0]=…&apts[1]=…`
    인덱스 표기로 보내고, `type`·`id`·`order` 는 ID 를 받은 `danjis/ids` 요청과 같은 값을 보낸다 (카드 둘째 줄 `desc2` 가
    `order` 탭마다 다른 뜻이다).
    """

    apt_ids: Annotated[
        list[int],
        Field(
            min_length=1,
            max_length=15,
            description='카드를 받을 단지 ID. 웹은 15곳씩 보낸다 (`apts[0]`·`apts[1]`… 로 직렬화)',
            alias='apts'
        )
    ]
    search_type: Annotated[
        ZigbangDanjiPlaceType,
        Field(description='무엇의 주변 단지인지. `danjis/ids` 요청과 같은 값', alias='type')
    ]
    place_id: Annotated[
        int,
        Field(gt=0, description='`search_type` 에 맞는 ID. `danjis/ids` 요청과 같은 값', alias='id')
    ]
    order: Annotated[
        ZigbangDanjiOrder,
        Field(description='순서 탭. 카드 둘째 줄(`desc2`)의 뜻을 정하므로 ID 를 받은 `danjis/ids` 요청의 `order` 와 같은 값을 보낸다')
    ]

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data = handler(self)
        # 웹과 같은 순서(apts 가 맨 앞)로 `apts[0]=…&apts[1]=…` 로 펼친다. `index_arrays` 는 serviceType 같은 정해진 키만 펼친다
        indexed = {f'apts[{index}]': apt_id for index, apt_id in enumerate(data.pop('apts'))}
        return {**indexed, **data}
