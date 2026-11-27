"""매물 상세(listing)의 상수: 상세를 붙이는 매물 수와 옵션·방향·관리비 항목 이름표."""

# --details 로 상세를 붙이는 매물 수. 한 건에 요청 1회라 목록이 길면 오래 걸린다
DETAILS_MAX: int = 30


OPTION_LABELS: dict[str, str] = {
    'PARKING': '주차',
    'WASHER': '세탁기',
    'AIRCON': '에어컨',
    'GAS_RANGE': '가스레인지',
    'INDUCTION': '인덕션',
    'ELEC_RANGE': '전기레인지',
    'FRIDGE': '냉장고',
    'REFRIGERATOR': '냉장고',
    'BED': '침대',
    'CLOSET': '옷장',
    'ELEVATOR': '엘리베이터',
    'PET': '반려동물',
    'BALCONY': '베란다',
    'MICROWAVE': '전자레인지',
    'TV': 'TV',
    'DESK': '책상',
    # 융자(근저당)가 아니라 전세자금대출 가능 여부다. 당근 웹은 필터에서 '대출 가능', 상세 JSON-LD 에서
    # mortgageAvailable(가능/불가능)로 보여 주고, YES 매물 본문에는 '전세자금대출 가능' 이라고 적혀 있다.
    # 시설은 아니지만 YES 일 때 알려야 하는 항목. README 가 options 에 섞여 나온다고 안내한다
    'MORTGAGE': '대출 가능',
    # MORTGAGE 처럼 시설이 아니라 YES 일 때 알릴 항목. 당근 웹 상세의 '전입신고 | 가능' 칸이다 (2026-10-24 실측: 4437264 가
    # MOVE_IN_REGISTRATION=YES 이고 페이지에 '전입신고 가능'. 이름표가 없어 영어 코드 그대로 options 에 나갔다)
    'MOVE_IN_REGISTRATION': '전입신고 가능',
}


DIRECTION_LABELS: dict[str, str] = {
    'SOUTH_FACING': '남향',
    'NORTH_FACING': '북향',
    'EAST_FACING': '동향',
    'WEST_FACING': '서향',
    'SOUTH_EAST_FACING': '남동향',
    'SOUTH_WEST_FACING': '남서향',
    'NORTH_EAST_FACING': '북동향',
    'NORTH_WEST_FACING': '북서향',
}


# 관리비 항목 (당근 웹 표기에서 '료'·'비' 를 뗐다. 직방 manage_cost_includes 의 '수도'·'전기'·'가스' 와 맞춘다)
MANAGE_COST_OPTION_LABELS: dict[str, str] = {
    'COMMON': '공용',
    'ELECTRIC': '전기',
    'WATERWORKS': '수도',
    'GAS': '가스',
    'BOILER': '난방',
    'INTERNET': '인터넷',
    'TV': 'TV',
    'PARKING': '주차',
    'CLEANING': '청소',
    'ELEVATOR': '승강기',
    'ETC': '기타',
}
