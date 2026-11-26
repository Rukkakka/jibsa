"""재개발 구역 정보·매물·목록이 같이 쓰는 것."""




REDEVELOPMENT_PAGE_SIZE: int = 30


def redevelopment_url(area_number: int) -> str:
    return f'https://fin.land.naver.com/redevelopments/{area_number}'
