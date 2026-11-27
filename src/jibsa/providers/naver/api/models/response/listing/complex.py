"""응답 모델: 단지 매물 목록 (search listings --complex)."""


from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
    NaverResponseModel,
)


class NaverComplexVillaArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/complex/villa/article/list` 응답."""


class NaverComplexArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/complex/article/list` 응답."""
