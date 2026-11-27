"""요청 모델: 단기임대 검색(search)·상세(detail)이 같이 쓰는 날짜 검사·입주 퇴거일 믹스인·요약(by-ids) 요청."""

from datetime import (
    date,
    datetime,
)

from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.dates import KST
from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Self,
)


# 단기임대 검색(`stay/search`)과 상세(`stay/detail`)가 같이 쓰는 날짜 검사·입주 퇴거일 믹스인·요약(by-ids) 요청. 상세는 노출 시작일을 요약에서 받는다

# 단기임대 지도·지역 검색이 받는 기간 (입주일과 마지막 날을 모두 센 일수). 2026-10-10 실측: 두 API 모두
# 6일은 400 MIN_DURATION_VIOLATION, 85일은 400 MAX_DURATION_VIOLATION. 매물 59건의 최대 계약도 모두 12주였다
STAY_SEARCH_MIN_DAYS: int = 7
STAY_SEARCH_MAX_DAYS: int = 84


class ZigbangStayDatesMixin(RequestModel):
    """단기임대 검색(지도·지역)과 요약(by-ids)이 함께 받는 입주·퇴거일. 둘 다 검색 기간(7~84일)을 받는다."""

    check_in_date: Annotated[
        str | None,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='입주 희망일 (YYYY-MM-DD)', alias='checkInDate')
    ] = None
    check_out_date: Annotated[
        str | None,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='마지막으로 머무는 날 (YYYY-MM-DD, 이용일에 센다)', alias='checkOutDate')
    ] = None
    flexibility: Annotated[
        int | None,
        Field(ge=0, description='일정을 앞뒤로 며칠까지 유연하게 볼지')
    ] = None

    @model_validator(mode='after')
    def dates_together(self) -> Self:
        # 하나만 보내면 서버가 400 "입주일과 퇴거일을 모두 선택해주세요" 를 준다
        if (self.check_in_date is None) != (self.check_out_date is None):
            raise ValueError('입주일과 퇴거일은 함께 주어야 합니다')
        if self.flexibility is not None and self.check_in_date is None:
            raise ValueError('일정 유연성은 입주일·퇴거일과 함께 써야 합니다')
        if self.check_in_date is not None and self.check_out_date is not None:
            validate_stay_dates(self.check_in_date, self.check_out_date)
            # 이용 일수. 직방은 --check-out 을 마지막으로 머무는 날로 보고 이용일에 센다 (11-02~11-08 = 7일)
            days = (date.fromisoformat(self.check_out_date) - date.fromisoformat(self.check_in_date)).days + 1
            if not STAY_SEARCH_MIN_DAYS <= days <= STAY_SEARCH_MAX_DAYS:
                raise ValueError(
                    f'단기임대 검색 기간은 입주일과 마지막 날을 포함해 {STAY_SEARCH_MIN_DAYS}~{STAY_SEARCH_MAX_DAYS}일'
                    f'(1~12주)이어야 합니다 (지금 {days}일). 예: 1주 = 2026-11-02~2026-11-08'
                )
        return self


class ZigbangGuestItemsByIdsRequestParameterModel(ZigbangStayDatesMixin):
    """`GET stay-apis.zigbang.com/guest/items/by-ids` 쿼리. 단기임대 매물 요약."""

    item_ids: Annotated[
        list[int],
        Field(min_length=1, max_length=100, description='요약을 받을 매물 ID 목록 (같은 키 반복)', alias='itemIds')
    ]


def validate_stay_dates(check_in: str, check_out: str) -> None:
    """입주일·마지막 날이 실제 날짜이고, 입주일이 한국 날짜로 오늘 이후이며, 마지막 날이 입주일보다 뒤인지 본다.

    Raises:
        ValueError: 위 조건을 어길 때 (요청 모델 검증 안에서 불러 CLI 는 INVALID_ARGUMENT).
    """
    # 2026-10-09 비로그인 API 실측: 검색은 오늘 입주를 허용하고 과거는 400. 2027-02-30 은 검색에서 500 이므로 서버에 맡기지
    # 않고 달력을 검증한다. 상세(listing stay-…)는 날짜를 서버에 보내지 않지만, 웹 날짜 고르기 창도 지난 날을 고를 수 없어
    # 같은 검사를 한다. 기간이 매물 계약 범위에 맞는지는 매물마다 달라(최소 1~8주) 여기서 보지 않는다
    try:
        start = date.fromisoformat(check_in)
        end = date.fromisoformat(check_out)
    except ValueError:
        raise ValueError('입주일·마지막 날은 실제 존재하는 YYYY-MM-DD 날짜여야 합니다') from None
    if start < datetime.now(KST).date():
        raise ValueError('입주일은 한국 날짜 기준 오늘 이후여야 합니다')
    if end <= start:
        raise ValueError('마지막으로 머무는 날(--check-out)은 입주일보다 뒤여야 합니다')
