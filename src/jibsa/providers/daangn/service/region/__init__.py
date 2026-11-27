"""지역·역·대학·주소 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석, 매물 카드의 시·도 채우기).

당근 부동산 웹 지도 검색창과 같은 API 로 찾는다. 지역은 `searchRegion`, 역은 `searchSubwayStationPois`, 대학은
`searchSchoolPois`, 도로명 주소(`--address`)는 검색창 주소 모드의 `searchAddress` → `unitByAddress` 다 (`find_address`).
웹은 이름의 종류를 짐작하지 않고 검색창이 칸별로 보여 준 후보를 사용자가 고르므로, jibsa 도 종류별 입력(지역 이름,
`--station`, `--university`, `--address`)을 따로 받고 이름이 정확히 같은 곳만 쓴다 (주소는 후보가 하나거나 입력과 정확히 같은
하나일 때만).

constants(상수), models(결과·조건 모델), common(LocationMissingError·has_location), area(지역), station(역),
university(대학), address(주소)에 있다. 명령·주제 모듈끼리는 서로 가져다 쓰지 않는다.
"""
