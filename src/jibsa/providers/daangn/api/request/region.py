"""요청 모델: 지역·역·대학·좌표 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel

from typing import (
    Annotated,
    Literal,
)


class DaangnGetRegionByCoordinateRequestPayloadModel(RequestModel):
    """GraphQL `getRegionByCoordinate` 쿼리 변수 (웹의 `regionByCoordinateQuery`)."""

    coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='찾을 좌표')
    ]


class DaangnQueryInputModel(RequestModel):
    """검색어 하나만 받는 `input` (지역·역·주소 검색)."""

    query: Annotated[
        str,
        Field(min_length=1, description='검색어')
    ]


class DaangnSearchSubwayStationPoisRequestPayloadModel(RequestModel):
    """GraphQL `searchSubwayStationPois` 쿼리 변수 (웹의 `fetchSubwayResultQuery`, 역 이름 검색).

    앞부분이 같은 역을 모두 준다 ('강남' → 강남, 강남구청, 강남대). 역 이름에는 '역' 이 붙지 않는다.
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description='역 이름 (예: 역삼역, 역삼)')
    ]


class DaangnSearchRegionRequestPayloadModel(RequestModel):
    """GraphQL `searchRegion` 쿼리 변수 (웹 지도 검색창의 `fetchRegionResultQuery`, 지역 이름 검색).

    법정동·구·시·도를 지역 중심 좌표와 함께 준다 ('서울' → 서울특별시, 그 구들, 동들 순). 행정동은 주지 않는다
    (2026-11-11 실측: 역삼1동 0건). 이름이 비슷한 곳도 섞여 와서(이도이동 → 외도이동·이호이동) 이름이 같은지는 부르는 쪽이 본다.
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description='지역 이름 (예: 역삼동, 강남구, 서울)')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=100, description='한 번에 받을 지역 수. 웹 검색창은 4곳씩 받고, 서버는 100 까지 준다 (2026-11-11 실측)')
    ] = 100
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None


class DaangnSearchAddressRequestPayloadModel(RequestModel):
    """GraphQL `searchAddress` 쿼리 변수 (웹 검색창 주소 모드의 `fetchAddressResultQuery`, 도로명 주소 검색).

    주소 글자(`input.query`)로 도로명·지번 주소 후보를 준다. 웹은 4곳씩 받고 '더 보기' 로 다음 쪽을 받는다 (MapShell `jo`).
    """

    input: Annotated[
        DaangnQueryInputModel,
        Field(description="주소 (예: '테헤란로 152')")
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 후보 수 (웹은 4)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None


class DaangnJusoAddressInputModel(RequestModel):
    """`unitByAddress` 의 `input.jusoAddress`. 주소 검색 후보의 건물 관리 번호와 원본 도로명 주소를 그대로 보낸다 (MapShell `_s`)."""

    bd_mgt_sn: Annotated[
        str,
        Field(min_length=1, description='건물 관리 번호 (주소 검색 결과의 bdMgtSn)', alias='bdMgtSn')
    ]
    original_road_address: Annotated[
        str,
        Field(min_length=1, description='원본 도로명 주소 (주소 검색 결과의 originalRoadAddress)', alias='originalRoadAddress')
    ]


class DaangnUnitByAddressInputModel(RequestModel):
    """`unitByAddress` 의 `input`."""

    juso_address: Annotated[
        DaangnJusoAddressInputModel,
        Field(description='주소 검색 후보', alias='jusoAddress')
    ]


class DaangnUnitByAddressRequestPayloadModel(RequestModel):
    """GraphQL `unitByAddress` 쿼리 변수 (웹의 `getPlaceByJusoAddressQuery`, 주소 → 좌표·단지·건물)."""

    input: Annotated[
        DaangnUnitByAddressInputModel,
        Field(description='주소 검색 후보')
    ]


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
