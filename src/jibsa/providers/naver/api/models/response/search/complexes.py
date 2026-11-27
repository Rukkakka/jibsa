"""응답 모델: 지역 단지 목록 (search complexes)."""


from jibsa.providers.naver.api.models.response.common import (
    NaverComplexListPageModel,
    NaverResponseModel,
)


class NaverComplexLegalDivisionComplexListV1ResponseModel(NaverResponseModel[NaverComplexListPageModel]):
    """`POST /front-api/v1/complex/legalDivisionComplexList` 응답."""


class NaverComplexBoundedComplexesV1ResponseModel(NaverResponseModel[NaverComplexListPageModel]):
    """`POST /front-api/v1/complex/boundedComplexes` 응답."""
