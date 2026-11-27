"""응답 모델: 지도 매물 검색 (search listings)."""


from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
    NaverResponseModel,
)


class NaverArticleLegalDivisionArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/article/legalDivisionArticleList` 응답. 지도 매물 목록과 같은 모양이다."""


class NaverArticleBoundedArticlesV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/article/boundedArticles` 응답."""
