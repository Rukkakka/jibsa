"""매물 상세 코드(방향·난방·현관·건물 세부 유형)를 글자로 바꾸는 공용 함수."""

from jibsa.providers.naver.service.common.labels import unknown_code_label
from jibsa.providers.naver.service.listing.constants import UNDISCLOSED_HEATING_CODES


def coded_label(labels: dict[str, str], code: str | None) -> str | None:
    """값 하나짜리 코드(방향·난방·현관·건물 세부 유형)의 글자. 코드가 없으면 모름(None), 표에 없으면 '알 수 없는 값 (코드)'.

    '미노출'(`UNDISCLOSED_HEATING_CODES`)은 중개사가 알리지 않은 것이라 모름(None)이다.
    """
    if not code or code in UNDISCLOSED_HEATING_CODES:
        return None
    return labels.get(code) or unknown_code_label('값', code)
