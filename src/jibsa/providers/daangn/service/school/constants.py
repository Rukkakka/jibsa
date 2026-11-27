"""학교·어린이집(school, preschools, preschool)의 상수."""

import re

from jibsa.providers.daangn.api.client import DAANGN_WEB_URL


# 어린이집·유치원 종류 (당근 표기). 상세(preschoolByNo)에만 온다
PRESCHOOL_LABEL_BY_TYPE: dict[str, str] = {'DAYCARE': '어린이집', 'KINDERGARTEN': '유치원'}


# 당근이 단지 근처 어린이집·유치원을 주는 범위: 단지에서 1km 안을 가까운 순으로 20곳까지 (2026-11-11 실측, 예전 반경 쿼리
# educationMapPoints 와 대조: 역삼래미안 10697092 는 1km 안 31곳 중 0.6km 안의 20곳, 양평역한라비발디2단지 20839190 은
# 1km 안 11곳 모두이고 1.23km 부터 빠짐)
PRESCHOOL_SERVER_RADIUS_KM: float = 1.0


PRESCHOOL_SERVER_MAX: int = 20


# 당근 웹 거리 계산(services2 하버사인)의 지구 반지름 (km)
WEB_EARTH_RADIUS_KM: float = 6371.0


# 학교 (당근 웹 표기)
SCHOOL_TYPE_LABELS: dict[str, str] = {'ELEMENTARY': '초등학교', 'MIDDLE': '중학교', 'HIGH': '고등학교', 'ETC': '기타'}


COEDU_LABELS: dict[str, str] = {'MALE': '남학교', 'COED': '남녀공학', 'FEMALE': '여학교'}


# 학교 이름 검색이 한 번에 받는 후보 수. 웹 검색창은 4곳씩 넘기지만 한 번에 더 받는다 ('중앙초등학교' 는 전국에 86곳이다)
SCHOOL_CANDIDATE_LIMIT: int = 50


# 이름이 똑같은 학교가 하나뿐일 때 같은 이름이 더 있는지 보려고 검색어마다 받는 쪽 수 (첫 쪽 포함, 50곳씩 150곳). 같은 이름 학교는
# 첫 쪽 맨 앞에 오지만(2026-11-20 실측: '중앙초등학교' 86곳·2쪽에서 이름이 똑같은 6곳이 모두 첫 쪽 1~6번째, '중앙초' 도 86곳·2쪽)
# 서버가 늘 그렇게 준다는 보장은 없어, 다음 쪽이 있으면 3쪽까지 보고 그래도 남으면 고르지 않는다 (2026-11-20 사용자 결정)
SCHOOL_NAME_CHECK_MAX_PAGES: int = 3


# 학교 코드 (당근·학교알리미, 2026-11-12 실측: 52곳 모두 지역 글자 하나 + 숫자 9자리, 예: B100000749). 소문자로 줘도 코드로
# 보고 대문자로 바꾼다
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(r'[A-Za-z]\d{9}')


# 학교가 여럿일 때 에러에 실을 후보 수
SCHOOL_AMBIGUOUS_SHOWN: int = 10


# 학교 종류 이름과 그 줄임. 당근 검색은 '○○초등학교' 로 '서울○○초등학교' 를 찾기도 못 찾기도 해서 줄임으로 한 번 더 찾는다
# (2026-10-23 실측: '대치초등학교' 0건·'대치초' 서울대치초등학교, '도곡초등학교' 는 경기 광주·화순 도곡초등학교만이고
# '도곡초' 에는 서울도곡초등학교도 나온다, '역삼초등학교' 는 서울역삼초등학교. 진선여자고·숙명여자중·단국대학교사범대학부속중
# 처럼 줄인 이름은 시험한 학교 모두 원래 이름의 결과를 포함했다)
SCHOOL_KIND_SHORT_NAMES: tuple[tuple[str, str], ...] = (('초등학교', '초'), ('중학교', '중'), ('고등학교', '고'))
# 출력 url 칸의 학교 웹 페이지 주소 틀 (`.format(학교 코드)`)
SCHOOL_URL: str = f'{DAANGN_WEB_URL}/schools/{{}}'
