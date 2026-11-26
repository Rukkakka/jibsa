"""요청 모델: 학교 기능(school)의 상세·목록이 같이 쓰는 것: 학교 단계 경로·설립 구분."""


from typing import (
    Literal,
)


DabangSchoolLevelPath = Literal['elementary-school', 'middle-school', 'high-school']

# 설립 구분. 학교·유치원은 PUBLIC 국공립·PRIVATE 사립, 어린이집은 PUBLIC 공공·PRIVATE 민간·HOME 가정·WORKPLACE 직장·
# COOPERATIVE 협동이다 (school-regional 청크의 탭, 2026-11-13). 웹은 '전체' 면 값을 보내지 않는다
DabangSchoolEstablishmentType = Literal['PUBLIC', 'PRIVATE', 'HOME', 'WORKPLACE', 'COOPERATIVE']
