"""요청 모델: 대학 이름 검색 (search locations 의 대학)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


# 대학 검색의 학교 종류. 웹 검색창은 셋을 모두 보낸다 (MapShell 의 대학 칸)
DaangnSchoolPoiType = Literal['UNIVERSITY', 'UNIVERSITY_ETC', 'GRADUATE']
SCHOOL_POI_TYPES: tuple[DaangnSchoolPoiType, ...] = ('UNIVERSITY', 'UNIVERSITY_ETC', 'GRADUATE')


class DaangnSchoolPoiSearchInputModel(RequestModel):
    """`searchSchoolPois` 의 `input`."""

    name: Annotated[
        str,
        Field(min_length=1, description='대학 이름 (예: 연세대학교)')
    ]
    school_types: Annotated[
        list[DaangnSchoolPoiType],
        Field(description='학교 종류 (대학·그 밖의 대학·대학원)', alias='schoolTypes')
    ] = list(SCHOOL_POI_TYPES)


class DaangnSearchSchoolPoisRequestPayloadModel(RequestModel):
    """GraphQL `searchSchoolPois` 쿼리 변수 (웹 지도 검색창의 `fetchUniversitySearchResultQuery`, 대학 이름 검색).

    캠퍼스마다 따로 준다 (2026-11-11 실측: 연세대학교 → 국제·미래·신촌캠퍼스, `name` 은 셋 다 '연세대학교'). 웹의 이 쿼리는
    변수가 `input`·`first` 뿐이고 `pageInfo` 를 받지 않아 다음 쪽을 받을 수 없다 (2026-11-13 번들 대조: MapShell `Bo`).
    """

    input: Annotated[
        DaangnSchoolPoiSearchInputModel,
        Field(description='대학 이름과 학교 종류')
    ]
    first: Annotated[
        int,
        Field(
            ge=1, le=50,
            description=(
                '받을 대학 수. 웹 검색창은 4곳만 받는다. 다음 쪽이 없어 같은 이름 캠퍼스·대학원을 다 보려고 50곳을 받는다 '
                '(2026-11-13 실측: 고려대학교는 23곳이라 20곳이면 치의학대학원 안암캠퍼스 등 3곳이 빠졌다)'
            ),
        )
    ] = 50
