"""요청 모델: 지역·역·주소 검색어 입력 (search locations, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnQueryInputModel(RequestModel):
    """검색어 하나만 받는 `input` (지역·역·주소 검색)."""

    query: Annotated[
        str,
        Field(min_length=1, description='검색어')
    ]
