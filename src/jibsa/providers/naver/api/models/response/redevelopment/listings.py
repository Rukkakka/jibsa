"""응답 모델: 재개발 구역 매물 (search listings --redevelopment)."""


from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
    NaverResponseModel,
)


class NaverComplexRedevelopmentAreaArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/complex/redevelopmentArea/articleList` 응답."""
