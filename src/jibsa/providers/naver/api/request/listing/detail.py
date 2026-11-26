"""요청 모델: 매물 상세 (listing)."""

from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverRealEstateType,
    NaverTradeType,
)
from jibsa.providers.naver.api.request.listing.base import (
    NaverArticleRequestParameterModel,
)

from typing import (
    Annotated,
    Literal,
)


class NaverArticleKeyV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/key` 쿼리."""


class NaverArticleBasicInfoV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/basicInfo` 쿼리. 유형 두 개는 article/key 로 먼저 알아낸다."""

    real_estate_type: Annotated[
        NaverRealEstateType,
        Field(description='매물 유형 코드', alias='realEstateType')
    ]
    trade_type: Annotated[
        NaverTradeType,
        Field(description='거래 유형 코드', alias='tradeType')
    ]


class NaverArticleMaintenanceFeeV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/maintenanceFee` 쿼리."""


class NaverArticleOldMaintenanceFeeV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/oldMaintenanceFee` 쿼리."""


class NaverDevelopmentArticleV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/development/article` 쿼리. 매물 근처의 개발 예정 (예정 지하철역·개발 지구)."""


class NaverArticleTaxV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/tax` 쿼리."""


class NaverArticleAgentFeeV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/agentFee` 쿼리."""


class NaverDataServiceTransportV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/data-service/transport` 쿼리. 매물 상세 화면은 article 과 매물 번호로 부른다."""

    item_type: Annotated[
        Literal['article', 'complex', 'villa'],
        Field(description='대상 종류 (사이트 ITEM_TRANSPORT_TYPE: 매물, 단지, 빌라 단지)', alias='itemType')
    ] = 'article'
    item_id: Annotated[
        int,
        Field(gt=0, description='매물 번호 또는 단지 번호', alias='itemId')
    ]


class NaverComplexBuildingRegistrationV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/complex/buildingRegistration` 쿼리. 매물 상세 화면이 건축물대장 유형의 주차 대수를 얻을 때 부른다.

    `pnu` 는 article/key 의 `key.pnu` (필지 고유번호 19자리)다. 사이트는 pnu 가 없으면 이 요청을 보내지 않는다.
    """

    pnu: Annotated[
        str,
        Field(min_length=1, description='필지 고유번호 (article/key 의 key.pnu, 19자리 글자)')
    ]
    real_estate_type: Annotated[
        NaverRealEstateType,
        Field(description='매물 유형 코드 (article/key 의 type.realEstateType)', alias='realEstateType')
    ]


class NaverEducationBuildingSchoolV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/building/school` 쿼리. 단지의 동마다 배정 초등학교를 준다.

    단지형 빌라(A05·A06·A07)는 villa 로 물어야 한다 (complex 로 물으면 빈 목록, 2026-10-09 확인).
    사이트는 단지·동 번호가 있는 매물에만 학교를 보여 준다.
    """

    item_type: Annotated[
        Literal['complex', 'villa'],
        Field(description='단지 종류 (사이트 ArticleSchoolItemType)', alias='itemType')
    ]
    complex_number: Annotated[
        int,
        Field(gt=0, description='단지 번호', alias='complexNumber')
    ]
    building_number: Annotated[
        int,
        Field(gt=0, description='동 번호 (article/key 의 buildingNumber)', alias='buildingNumber')
    ]
