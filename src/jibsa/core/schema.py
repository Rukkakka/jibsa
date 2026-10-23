from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
)


class RequestModel(BaseModel):
    """Base request model with strict field validation."""
    model_config = ConfigDict(
        validate_by_name=True,
        extra='forbid',
    )


class ResponseModel(BaseModel):
    """Base response model allowing additional fields from APIs.

    비공식 API 는 예고 없이 필드를 추가하므로 모르는 필드는 버리지 않고 보존한다.
    """
    model_config = ConfigDict(
        validate_by_name=True,
        extra='allow',
    )


def is_request_validation_error(exc: ValidationError) -> bool:
    """요청 모델(`RequestModel`)을 만들다 난 검증 오류인지. 즉 사용자 입력이 잘못된 경우.

    응답 모델이나 `Listing` 검증 오류는 소스 응답이 예상과 달라진 것이라 입력 오류가 아니다.
    `ValidationError.title` 은 검증한 모델 클래스 이름이다.

    응답 값으로 요청 모델을 만들다 난 오류도 여기서는 입력 오류로 보인다. 이 구분을 여기서 바꾸지 않고, 응답 값이
    실제로 형식에서 벗어나는 곳만 그 자리에서 다른 에러로 바꾼다 (네이버 클러스터 ID·매물 유형). 실측으로 벗어나지
    않는 값은 막지 않고 그 자리에 근거를 적는다 (당근 `resolve_regions` 의 name1, 2026-10-11 리뷰 확인).
    service 경계 한 곳에서 바꾸지 않는 것은, 같은 요청 모델에 사용자 입력과 응답 값이 함께 들어가 오류만 보고는 어느
    쪽 값인지 알 수 없고 그 값을 넣는 자리만 알기 때문이다 (2026-10-12 리뷰에서 한 곳으로 모으자는 제안을 검토하고 유지).
    새 엔드포인트의 규칙은 references/provider-conventions.md '요청·응답 모델' 에 있다.
    """
    stack: list[type[BaseModel]] = [RequestModel]
    while stack:
        model = stack.pop()
        if model.__name__ == exc.title:
            return True
        stack.extend(model.__subclasses__())
    return False
