"""응답 모델: 단지 매물 목록·매물 상세가 같이 쓰는 것."""

from pydantic import Field

from jibsa.providers.naver.api.response.common import (
    NaverBaseResponseModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverAgentPhoneModel(NaverBaseResponseModel):
    """중개사 연락처."""

    brokerage: Annotated[
        str | None,
        Field(description='사무소 대표번호')
    ] = None


class NaverArticleAgentModel(NaverBaseResponseModel):
    """중개사."""

    brokerage_name: Annotated[
        str | None,
        Field(description='중개사무소명', alias='brokerageName')
    ] = None
    broker_name: Annotated[
        str | None,
        Field(description='대표 중개사', alias='brokerName')
    ] = None
    address: Annotated[
        str | None,
        Field(description='사무소 주소')
    ] = None
    business_registration_number: Annotated[
        str | None,
        Field(description='중개사무소 등록번호', alias='businessRegistrationNumber')
    ] = None
    phone: Annotated[
        NaverAgentPhoneModel | None,
        Field(description='연락처')
    ] = None


class NaverArticleAgentV1ResponseModel(NaverResponseModel[NaverArticleAgentModel]):
    """`GET /front-api/v1/article/agent` 응답."""
