"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.service.common.models import (
    DaangnRegion,
    DaangnRegionComplex,
)
from jibsa.providers.daangn.service.region.models.area import DaangnRealsaleRegion

from typing import (
    Annotated,
)


class DaangnRegionComplexesResult(Result):
    """동·구의 단지 목록.

    `notes`: 지역을 고른 방법, 정렬·후기 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    trade_type: Annotated[
        str,
        Field(description='최근 실거래(recent_trades)와 가격 조건의 거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (세대수, 가격높은순, 가격낮은순, 입주최신순, 입주오래된순)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지가 더 있는지')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex],
        Field(description='정렬 순 단지')
    ]


class DaangnComplexConditions(RequestModel):
    """지역 단지 목록 조건 (search complexes). 웹 지도 단지 탭 필터와 같고 당근 서버에서 건다.

    가격 조건은 지금 매물 가격이 아니라 단지의 과거 실거래 가격으로 거른다 (`list_region_complexes`).
    """

    complex_types: Annotated[
        list[str],
        Field(description='단지 유형 (COMPLEX_TYPE_FILTER_BY_LABEL). 비면 전체 (도시형 생활주택도 섞인다)')
    ] = []
    # 리뷰 오탐 (2026-11-20): CLI(search complexes)는 --trade 없이 보증금·월세 조건을 막지만, 이 설명은 라이브러리로 직접 부를 때의
    # 동작이다 (complex.py 의 조건 만들기와 맞다)
    trade_type: Annotated[
        str | None,
        Field(description='가격 조건과 단지마다 붙는 최근 실거래의 거래 유형 (매매·전세·월세). 없으면 매매로 보여 주고, 필터로는 가격 조건(보증금·월세·매매가 중 하나)이 있을 때만 기본 매매를 보낸다')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원, 과거 실거래 기준)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원, 과거 실거래 기준)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원, 과거 실거래 기준)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원, 과거 실거래 기준)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원, 과거 실거래 기준)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원, 과거 실거래 기준)')
    ] = None
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡). 단지 조건과 최근 실거래 면적에 함께 건다')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡). 단지 조건과 최근 실거래 면적에 함께 건다')
    ] = None
    building_approval: Annotated[
        str | None,
        Field(description='사용승인일 (BUILDING_APPROVAL_FILTER_BY_LABEL)')
    ] = None
    household_min: Annotated[
        int | None,
        Field(description='세대수 하한')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='세대수 상한')
    ] = None
    parking_min: Annotated[
        float | None,
        Field(description='세대당 주차 대수 하한')
    ] = None


class DaangnBoundsComplexesResult(Result):
    """지도 화면 범위의 단지 목록 (웹 지도 단지 탭의 '이 영역 단지').

    `notes`: 범위·정렬·후기 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion | None,
        Field(description='화면 가운데가 속한 동. 모르면 null')
    ] = None
    zoom: Annotated[
        int,
        Field(description='웹 지도 줌. 범위는 데스크톱 지도 화면(1440×900 창에서 목록 패널을 뺀 영역) 기준이다')
    ]
    width_km: Annotated[
        float,
        Field(description='화면 범위의 가로 (km)')
    ]
    height_km: Annotated[
        float,
        Field(description='화면 범위의 세로 (km)')
    ]
    trade_type: Annotated[
        str,
        Field(description='최근 실거래(recent_trades)와 가격 조건의 거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (세대수, 가격높은순, 가격낮은순, 입주최신순, 입주오래된순)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지가 더 있는지')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex],
        Field(description='정렬 순 단지')
    ]
