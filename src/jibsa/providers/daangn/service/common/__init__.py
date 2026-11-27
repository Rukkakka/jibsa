"""당근 service 공통: 여러 모듈이 쓰는 상수·결과 모델·GraphQL 응답 풀기·매물 변환·안내 문구.

constants(상수·코드표), models(결과·조건 모델), response(GraphQL 응답 풀기·커서·부분 실패 안내·code_label),
location(좌표·지도 범위·역 이름), listing(매물 카드 변환·노출 판정·조건 안내), nearby(주변 매물 연결·가려진 위치 안내),
complex(단지 공용)에 있다. 이 폴더 안 파일은 constants·models·response 만 아래층으로 가져다 쓰고, 서로는 가져다 쓰지 않는다.
"""
