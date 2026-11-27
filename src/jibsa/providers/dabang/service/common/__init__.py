"""두 기능 이상이 쓰는 다방 상수·결과 모델·변환 (매물 목록은 search listings 와 단지 매물이 같이 쓴다).

constants(상수·코드표·선택지 별칭), models(결과·조건 모델), bbox(지도 범위),
text(금액·숫자·세대수·연차·계약일·층 글자 해석), error(400 사유·없는 ID 판정), room(방 매물 한 칸 변환·조건 필터·안내),
paging(쪽 넘김과 더 있다·멈췄다 안내), complex(단지 상세 조회·대표 평형·평당가). 바닥 파일(constants·models·bbox·text·error)은
constants 말고는 서로 가져다 쓰지 않고(매물·단지·분양 주소 틀은 constants 에 있다), 주제 파일(room·paging·complex)은 바닥 파일만 가져다 쓰며 서로 가져다 쓰지 않는다.
"""
