"""소스마다 모든 CLI 명령을 실제로 불러 비공식 API 가 깨졌는지 본다 (매일 새벽 `.github/workflows/api-monitor.yml`).

매일 실행은 `DAILY_GROUPS`(직방·당근·다방)만 돈다. 네이버는 GitHub 러너에서 응답을 받지 못해 매일 실행에서 빼고, 필요할 때 로컬에서
`run naver` 로 돌린다.

명령마다 셋으로 나눈다 (references/development.md '매일 API 감시').

- 정상: exit 0 이고 정한 칸(`Step.expect`)에 값이 있음. 빈 목록도 사이트의 평소 답인 칸(`Step.empty_ok`)은 비어도 정상
- 고장: 응답 형식 오류·서버 거절·내부 오류 같은 에러, 정한 칸이 비어 있음, JSON 이 아닌 출력, 대체 경로로 돌았거나 덤 조회가
  깨졌다는 안내(`UPDATE_NEEDED`·`UPDATE_MAYBE_NEEDED`). 결과가 0건일 리 없는 곳(역삼동·강남역·강남구 등)만 찾아서,
  비어 있으면 사이트가 바뀐 것으로 본다
- 확인 못 함: 요청 제한·네트워크 오류·서버 5xx·방금 내려간 매물·시간 초과, 앞 명령이 넘길 번호를 주지 않아 건너뛴 명령,
  사이트가 빈 목록을 줄 때가 있는 칸(`Step.may_be_empty`)이 빔, 덤 조회가 잠깐 실패해(업데이트 문구 없는 `[실패]`) 정한 칸이
  빔. 사이트가 바뀐 것인지 알 수 없다

    python scripts/monitor/api_check.py run zigbang --out result-zigbang.json
    python scripts/monitor/api_check.py report result-*.json [--issues] [--dry-run]

새 CLI 명령이나 매물을 찾는 새 방식(다른 API 를 쓰는 경로)을 만들면 GROUPS 에 넣는다. tests/test_cli.py 가 CLI 명령 목록과 대조한다.
"""

import argparse
import datetime
import json
import os
import string
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from typing import Any


@dataclass(frozen=True)
class Capture:
    """결과에서 뒤 명령에 넘길 값 하나. 목록 칸의 항목 중 조건에 맞는 첫 항목에서 꺼낸다.

    Args:
        name: 뒤 명령 인자의 `{name}` 에 채울 이름. 이미 담긴 이름이면 덮어쓰지 않는다.
        items: 결과의 목록 칸 (예: `listings`). 비우면 결과 맨 위 칸에서 꺼낸다 (이어 받기 표 `next`).
        field: 항목에서 꺼낼 칸 (예: `id`). 숫자면 문자열로 바꾼다.
        prefix: 이 글자로 시작하는 값만 (직방 단지 ID 의 `apt-`·`officetel-`).
        largest: 주면 이 칸이 가장 큰 항목에서 꺼낸다 (거래가 있을 평형을 고르려고 세대수가 가장 많은 평형).
        where: 주면 (칸, 값) 이 같은 항목만 본다 (단지 학교 중 중학교만).
    """

    name: str
    items: str
    field: str
    prefix: str = ''
    largest: str = ''
    where: tuple[str, str] | None = None


@dataclass(frozen=True)
class Step:
    """감시할 명령 하나.

    Args:
        label: 결과 표에 쓰는 이름.
        command: CLI 명령 경로 (예: `('zigbang', 'search', 'listings', 'room')`). 그룹 옵션으로 부르는 경로는 그룹까지
            (`('zigbang', 'search', 'listings')` + `--complex`).
        args: 인자. `{name}` 은 앞 명령의 `Capture` 값으로 채운다.
        expect: 값이 있어야 정상인 칸. 점으로 이어 안쪽 칸을 가리킨다 (`listing_count.weekly`).
        captures: 이 결과에서 뒤 명령에 넘길 값.
        may_be_empty: 사이트가 같은 지역에도 빈 목록을 줄 때가 있는 칸이면 True. 비어 있으면 고장 대신 확인 못 함이다
            (다방 청약 일정).
        empty_ok: 빈 목록도 사이트의 평소 답인 칸이면 True. 비어 있어도 정상이다 (당근 인기 단지는 이른 아침에 자주 빈다).
    """

    label: str
    command: tuple[str, ...]
    args: tuple[str, ...]
    expect: str
    captures: tuple[Capture, ...] = ()
    may_be_empty: bool = False
    empty_ok: bool = False


# 명령 하나가 요청 제한 대기(최대 60초)를 몇 번 거쳐도 끝날 시간
COMMAND_TIMEOUT_SECONDS: int = 300
# 결과·표·이슈에 쓰는 날짜의 시간대. 러너는 UTC 라 한국 04:17 실행이 전날 날짜로 찍혔다 (2026-10-18 실행이 2026-10-17).
# 정리 잡에는 jibsa 가 없어 jibsa 의 kst_today 를 가져오지 않는다
KST: datetime.timezone = datetime.timezone(datetime.timedelta(hours=9), 'KST')
# 단기임대 기간 비용(`listing --check-in/--check-out`)은 앞날 기간만 받아 실행하는 날로 정한다. 이만큼 뒤에 입주해 1주 머문다
STAY_CHECK_IN_DAYS: int = 14

ROOM: tuple[str, ...] = ('zigbang', 'search', 'listings', 'room')
APT: tuple[str, ...] = ('zigbang', 'search', 'listings', 'apt')
ZIGBANG_LISTINGS: tuple[str, ...] = ('zigbang', 'search', 'listings')
ZIGBANG_LISTING: tuple[str, ...] = ('zigbang', 'listing')
NAVER_LISTINGS: tuple[str, ...] = ('naver', 'search', 'listings')
DAANGN_LISTINGS: tuple[str, ...] = ('daangn', 'search', 'listings')
DABANG_LISTINGS: tuple[str, ...] = ('dabang', 'search', 'listings')

# 러너 하나가 소스 하나를 돈다. 러너마다 IP 와 요청 제한 상태가 따로라 한 소스가 막혀도 다른 소스 검사는 그대로 된다.
# 매물 검색은 찾는 방식(동 이름 경계·역 반경·좌표 반경·단지)마다 쓰는 API 가 달라 방식별로 부른다. --limit 은 작게 준다
# (감시는 결과가 있는지만 보고, 네이버는 요청 제한이 가장 엄격하다). 이어 받기(--next)는 첫 결과에서 쓰지 않는 서버 커서·offset
# (직방 아파트 offset, 당근 피드·역 목록 after, 네이버 seed·lastInfo)을 보내 사이트가 바꾸면 따로 깨질 수 있어, 그 방식마다 앞 결과의
# next 로 한 번 더 부른다. 인자는 앞 명령과 같아야 한다 (다른 지역·조건의 next 는 INVALID_ARGUMENT)
GROUPS: dict[str, tuple[Step, ...]] = {
    'zigbang': (
        Step('지역 찾기 역삼동', ('zigbang', 'search', 'locations'), ('역삼동',), 'results'),
        Step(
            '원룸 동 경계 역삼동', ROOM, ('역삼동', '--limit', '2'), 'listings',
            (Capture('room', 'listings', 'id'), Capture('room_next', '', 'next')),
        ),
        Step('원룸 이어 받기 역삼동', ROOM, ('역삼동', '--limit', '2', '--next', '{room_next}'), 'listings'),
        Step('원룸 상세', ZIGBANG_LISTING, ('{room}',), 'id'),
        # 오피스텔 건물은 매물이 있는 건물이어야 해서 매물 목록에서 고른다
        Step(
            '원룸 역 반경 강남역', ROOM, ('강남역', '--limit', '5'), 'listings',
            (Capture('officetel', 'listings', 'complex_id', prefix='officetel-'),),
        ),
        Step(
            '아파트 동 목록 역삼동', APT, ('역삼동', '--limit', '2'), 'listings',
            (
                Capture('apt', 'listings', 'complex_id', prefix='apt-'), Capture('apt_listing', 'listings', 'id'),
                Capture('apt_next', '', 'next'),
            ),
        ),
        Step('아파트 이어 받기 역삼동', APT, ('역삼동', '--limit', '2', '--next', '{apt_next}'), 'listings'),
        Step('아파트 상세', ZIGBANG_LISTING, ('{apt_listing}',), 'id'),
        Step('아파트 역 반경 강남역', APT, ('강남역', '--radius', '1', '--limit', '2'), 'listings'),
        Step('아파트 단지', ('zigbang', 'complex'), ('{apt}',), 'name', (Capture('apt_pyeong', 'pyeongs', 'id'),)),
        Step('아파트 실거래가', ('zigbang', 'real-price'), ('{apt}', '--limit', '3'), 'transactions'),
        # 평형별 실거래는 다른 API 다. 고른 평형에 거래가 없을 수 있어 거래 칸 대신 평형 칸을 본다. API 가 바뀌면 첫 응답의 평형
        # 목록 확인(`_check_real_price_scope`)이 NOT_FOUND 를 내 고장으로 잡힌다
        Step('아파트 평형 실거래가', ('zigbang', 'real-price'), ('{apt}', '--pyeong', '{apt_pyeong}', '--limit', '3'), 'pyeong_id'),
        Step('아파트 단지 매물', ZIGBANG_LISTINGS, ('--complex', '{apt}', '--limit', '2'), 'listings'),
        Step('오피스텔 건물', ('zigbang', 'complex'), ('{officetel}',), 'name'),
        Step('오피스텔 건물 매물', ZIGBANG_LISTINGS, ('--complex', '{officetel}', '--limit', '2'), 'listings'),
        Step(
            '상가 역 반경 강남역', ('zigbang', 'search', 'listings', 'store'), ('강남역', '--limit', '2'), 'listings',
            (Capture('store', 'listings', 'id'),),
        ),
        Step('상가 상세', ZIGBANG_LISTING, ('{store}',), 'id'),
        Step(
            '단기임대 지역 강남구', ('zigbang', 'search', 'listings', 'stay'), ('강남구', '--limit', '2'), 'listings',
            (Capture('stay', 'listings', 'id'),),
        ),
        Step('단기임대 상세', ZIGBANG_LISTING, ('{stay}',), 'id'),
        # 기간 비용은 예약 가능 여부와 상관없이 온다 (예약된 기간이면 available false)
        Step(
            '단기임대 기간 비용', ZIGBANG_LISTING, ('{stay}', '--check-in', '{check_in}', '--check-out', '{check_out}'), 'period_cost',
        ),
        Step('단기임대 역 반경 강남역', ('zigbang', 'search', 'listings', 'stay'), ('강남역', '--radius', '1', '--limit', '2'), 'listings'),
    ),
    'naver': (
        Step('하위 지역 강남구', ('naver', 'regions'), ('강남구',), 'regions'),
        Step('동네 추이 역삼동', ('naver', 'trend'), ('역삼동',), 'listing_count.weekly'),
        Step(
            '매물 동 전체 역삼동', NAVER_LISTINGS, ('역삼동', '--limit', '2'), 'listings',
            (Capture('article', 'listings', 'id'), Capture('dong_next', '', 'next')),
        ),
        Step('매물 동 전체 이어 받기 역삼동', NAVER_LISTINGS, ('역삼동', '--limit', '2', '--next', '{dong_next}'), 'listings'),
        Step('매물 상세', ('naver', 'listing'), ('{article}',), 'id'),
        Step('매물 역 반경 강남역', NAVER_LISTINGS, ('강남역', '--limit', '2'), 'listings', (Capture('near_next', '', 'next'),)),
        # 가까운순은 지도 칸 번호와 그 칸의 커서로 이어 받는다
        Step('매물 역 반경 이어 받기 강남역', NAVER_LISTINGS, ('강남역', '--limit', '2', '--next', '{near_next}'), 'listings'),
        Step(
            '단지 목록 역삼동', ('naver', 'search', 'complexes'), ('역삼동', '--sort', '세대수순', '--limit', '1'), 'complexes',
            (Capture('complex', 'complexes', 'complex_number'),),
        ),
        Step(
            '단지', ('naver', 'complex'), ('{complex}',), 'pyeongs',
            (Capture('pyeong', 'pyeongs', 'number', largest='household_count'), Capture('school', 'schools', 'school_code')),
        ),
        Step('평형 실거래가', ('naver', 'real-price'), ('{complex}', '--pyeong', '{pyeong}'), 'transactions'),
        Step('평형 시세', ('naver', 'market-price'), ('{complex}', '--pyeong', '{pyeong}'), 'providers'),
        Step('학교', ('naver', 'school'), ('{school}',), 'school_code'),
        Step('단지 매물', NAVER_LISTINGS, ('--complex', '{complex}', '--limit', '2'), 'listings'),
        Step(
            '재개발 구역 한남동', ('naver', 'search', 'redevelopment'), ('한남동', '--limit', '1'), 'areas',
            (Capture('redevelopment', 'areas', 'redevelopment_number'),),
        ),
        Step('재개발 구역', ('naver', 'redevelopment'), ('{redevelopment}',), 'redevelopment_number'),
        Step('재개발 구역 매물', NAVER_LISTINGS, ('--redevelopment', '{redevelopment}', '--limit', '2'), 'listings'),
    ),
    'daangn': (
        Step('지역 찾기 역삼동', ('daangn', 'search', 'locations'), ('역삼동',), 'results'),
        # 지도 페이지(SSR)를 읽는 경로. 역삼동은 같은 이름 후보가 둘이라 후보마다 지도 페이지를 확인하는 경로도 지난다
        Step(
            '매물 동 역삼동', DAANGN_LISTINGS, ('역삼동', '--limit', '2'), 'listings',
            (Capture('article', 'listings', 'id'), Capture('map_next', '', 'next')),
        ),
        # 조건이 없으면 지도 페이지(SSR)의 커서로 피드를 이어 받는다
        Step('매물 동 이어 받기 역삼동', DAANGN_LISTINGS, ('역삼동', '--limit', '2', '--next', '{map_next}'), 'listings'),
        # 여러 동('○가')은 동 피드를 커서에 담긴 시각 순으로 합친다. 커서 형식이 바뀌면 next 가 없어 이어 받기가 '확인 못 함' 이 된다
        Step('매물 여러 동 성수동', DAANGN_LISTINGS, ('성수동', '--limit', '2'), 'listings', (Capture('ga_next', '', 'next'),)),
        Step('매물 여러 동 이어 받기 성수동', DAANGN_LISTINGS, ('성수동', '--limit', '2', '--next', '{ga_next}'), 'listings'),
        Step('매물 상세', ('daangn', 'listing'), ('{article}',), 'id'),
        # 조건이 있으면 지도 페이지 대신 필터 API(articleFeed·articlesCount)로 받는다
        Step(
            '매물 동 조건 역삼동 월세', DAANGN_LISTINGS, ('역삼동', '--trade', '월세', '--limit', '2'), 'listings',
            (Capture('feed_next', '', 'next'),),
        ),
        Step(
            '매물 동 조건 이어 받기 역삼동 월세', DAANGN_LISTINGS, ('역삼동', '--trade', '월세', '--limit', '2', '--next', '{feed_next}'),
            'listings',
        ),
        Step('매물 역 강남역', DAANGN_LISTINGS, ('강남역', '--limit', '2'), 'listings', (Capture('station_next', '', 'next'),)),
        Step('매물 역 이어 받기 강남역', DAANGN_LISTINGS, ('강남역', '--limit', '2', '--next', '{station_next}'), 'listings'),
        Step('매물 반경 강남역', DAANGN_LISTINGS, ('강남역', '--radius', '0.5', '--limit', '2'), 'listings'),
        Step('출퇴근 강남역', ('daangn', 'search', 'commute'), ('강남역', '--limit', '2'), 'stations'),
        Step(
            '단지 목록 역삼동', ('daangn', 'search', 'complexes'), ('역삼동', '--limit', '2'), 'complexes',
            (Capture('complex', 'complexes', 'complex_id'),),
        ),
        Step('단지', ('daangn', 'complex'), ('{complex}',), 'name'),
        # 단지 매물은 지도 피드가 아니라 단지 화면 쿼리(ComplexArticleListPanelQuery)로 받는다
        Step(
            '단지 매물', DAANGN_LISTINGS, ('--complex', '{complex}', '--limit', '2'), 'listings',
            (Capture('complex_article', 'listings', 'id'),),
        ),
        Step('단지 실거래가', ('daangn', 'real-price'), ('{complex}', '--limit', '3'), 'transactions'),
        # 매물 번호로 건물 실거래를 받는 쿼리(articleByOriginalArticleId). 동 매물은 사무실·빌라라 거래가 없을 수 있어 단지 매물로 본다
        Step('매물 건물 실거래가', ('daangn', 'real-price'), ('--item', '{complex_article}', '--limit', '3'), 'transactions'),
        Step('단지 시세 추이', ('daangn', 'price-trend'), ('{complex}',), 'points'),
        Step(
            '같은 동 단지', ('daangn', 'nearby-complexes'), ('{complex}', '--limit', '2'), 'complexes',
            (Capture('neighbor', 'complexes', 'complex_id'),),
        ),
        Step('단지 비교', ('daangn', 'compare'), ('{complex}', '{neighbor}'), 'complexes'),
        Step('학교 역삼초등학교', ('daangn', 'school'), ('역삼초등학교',), 'complexes'),
        Step('동 실거래 역삼동', ('daangn', 'region-real-price'), ('역삼동', '--limit', '3'), 'transactions'),
        # 신고가는 다른 쿼리(realsaleNewHighFeed)다. 동 하나는 신고가가 없을 수 있어 구로 본다
        Step('신고가 강남구', ('daangn', 'region-real-price'), ('강남구', '--new-high', '--limit', '3'), 'transactions'),
        Step('동네 후기 강남구', ('daangn', 'region-reviews'), ('강남구', '--top', '3'), 'top_complexes'),
        Step(
            '개발 호재 한남동', ('daangn', 'developments'), ('한남동', '--limit', '2'), 'developments',
            (Capture('development', 'developments', 'id'),),
        ),
        Step('개발 사업', ('daangn', 'development'), ('{development}',), 'name'),
        Step(
            '어린이집 역삼역', ('daangn', 'preschools'), ('역삼역', '--limit', '2'), 'preschools',
            (Capture('preschool', 'preschools', 'id'),),
        ),
        Step('어린이집', ('daangn', 'preschool'), ('{preschool}',), 'name'),
        Step(
            '좋은 동네 서울', ('daangn', 'good-neighborhoods'), ('--lifestyle', '직장인자취', '--region', '서울', '--limit', '3'),
            'neighborhoods',
        ),
        # 인기 단지는 같은 동에도 빈 목록을 줄 때가 있다 (역삼동 2026-10-11 4곳, 2026-10-20 아침 0곳, 같은 날 낮 12곳)
        # 같은 동도 때에 따라 빈 목록이고 감시가 도는 아침에 잦다 (2026-10-27 실측: 아침 7번 중 5번 0곳, 낮·저녁 10~22곳).
        # 확인 못 함으로 두면 사흘 연속 막힘으로 잘못 알린다 (#142). 쿼리 거절·응답 형식 변경은 그대로 고장이다
        Step('인기 단지 역삼동', ('daangn', 'trending-complexes'), ('역삼동',), 'complexes', empty_ok=True),
        Step('인기 매물 역삼동', ('daangn', 'popular-listings'), ('역삼동', '--limit', '3'), 'listings'),
    ),
    'dabang': (
        Step(
            '장소 찾기 은마', ('dabang', 'search', 'locations'), ('은마',), 'complexes',
            (Capture('complex', 'complexes', 'complex_id'),),
        ),
        # 찾는 방식마다 다른 목록 주소다: 동(region)·역(subway)·대학(univ)·좌표 반경(bbox)
        Step(
            '원룸 동 역삼동', DABANG_LISTINGS + ('room',), ('역삼동', '--limit', '2'), 'listings',
            (Capture('room', 'listings', 'id'), Capture('room_next', '', 'next')),
        ),
        # 이어 받기는 쪽 번호와 쪽 안 위치(24건씩)로 다시 묻는다
        Step('원룸 동 이어 받기 역삼동', DABANG_LISTINGS + ('room',), ('역삼동', '--limit', '2', '--next', '{room_next}'), 'listings'),
        Step('원룸 상세', ('dabang', 'listing'), ('{room}',), 'id'),
        Step('원룸 역 강남역', DABANG_LISTINGS + ('room',), ('강남역', '--limit', '2'), 'listings'),
        Step('원룸 대학 홍익대학교', DABANG_LISTINGS + ('room',), ('홍익대학교', '--limit', '2'), 'listings'),
        Step(
            '원룸 좌표 반경 강남역', DABANG_LISTINGS + ('room',),
            ('--lat', '37.4979', '--lng', '127.0276', '--radius', '0.5', '--limit', '2'), 'listings',
        ),
        # '○가' 로 나뉜 동은 동마다 목록을 받아 합친다
        Step(
            '빌라 여러 동 성수동', DABANG_LISTINGS + ('villa',), ('성수동', '--limit', '2'), 'listings',
            (Capture('villa', 'listings', 'id'),),
        ),
        Step('오피스텔 역 강남역', DABANG_LISTINGS + ('officetel',), ('강남역', '--limit', '2'), 'listings'),
        # 아파트는 동 검색이 없어 동 경계 파일(CDN)로 사각형을 만들어 받는다
        # --limit 은 사각형에서 받은 수라 다른 동을 빼면 줄어든다 (2026-10-25 실측: 대치동은 24건 중 12건). 3건이면 모두 다른 동인
        # 날(약 1/8)에 빈 목록이 되어 고장으로 잘못 알린다
        Step('아파트 동 경계 대치동', DABANG_LISTINGS + ('apt',), ('대치동', '--limit', '10'), 'listings'),
        # 다방 단지 매물은 적어(은마 3건, 2026-10-25) 단지 목록에서 매물이 가장 많은 단지로 단지 매물을 본다. --limit 은 받은
        # 단지 수라 경계 사각형의 다른 동을 빼면 남는 곳이 적다 (5곳 중 대치동 2곳). 한 쪽이 24곳이라 10 이어도 요청은 1회다
        Step(
            '단지 목록 대치동', ('dabang', 'search', 'complexes'), ('대치동', '--limit', '10'), 'complexes',
            (Capture('listed_complex', 'complexes', 'complex_id', largest='listing_count'),),
        ),
        # 최근 실거래 요약은 덤 조회라 실패해도 단지 정보가 나온다. 은마는 늘 거래가 있어 실패 안내 없이 비면 요약이 깨진 것이다
        # 단지 목록도 찾는 방식마다 다른 주소다: 아파트 동은 위의 경계 사각형(bbox), 오피스텔 동은 region, 역은 subway
        Step('오피스텔 단지 목록 역삼동', ('dabang', 'search', 'complexes'), ('역삼동', '-t', '오피스텔', '--limit', '2'), 'complexes'),
        Step('단지 목록 역 강남역', ('dabang', 'search', 'complexes'), ('강남역', '--limit', '2'), 'complexes'),
        Step(
            '단지', ('dabang', 'complex'), ('{complex}',), 'recent_sale',
            # 진학 인원이 모두 비어도 초등학교 코드를 고르지 않게 중학교만 본다 (단계가 틀리면 500 이라 확인 못 함으로 묻힌다)
            (Capture('middle_school', 'schools', 'school_code', largest='special_high_entrants', where=('level', '중학교')),),
        ),
        # 학교 상세는 옛 방식(/api/3/education/{단계}/{코드}). 단계가 코드와 다르면 500 이라 단지의 중학교로 본다
        Step('학교 상세 중학교', ('dabang', 'school'), ('{middle_school}', '--level', '중학교'), 'advancement'),
        Step('단지 매물', DABANG_LISTINGS, ('--complex', '{listed_complex}', '--limit', '2'), 'listings'),
        Step('단지 실거래가', ('dabang', 'real-price'), ('{complex}', '--limit', '3'), 'transactions'),
        # --listing 은 단지 없는 매물만 받는다. 원룸 목록에는 오피스텔이 섞여 빌라 목록의 매물을 쓴다
        Step('매물 실거래가', ('dabang', 'real-price'), ('--listing', '{villa}', '--trade', '전월세', '--limit', '3'), 'transactions'),
        Step('단지 시세 흐름', ('dabang', 'price-trend'), ('{complex}',), 'months'),
        # 동네정보는 탭마다 다른 주소다 (요약 3종·수 4종). 기본은 모든 주제
        Step('동네정보 역삼동', ('dabang', 'neighborhood'), ('역삼동',), 'safety'),
        Step('인기 매물 역삼동', ('dabang', 'popular-listings'), ('역삼동', '--limit', '3'), 'listings'),
        Step('매물 주변', ('dabang', 'nearby'), ('{room}',), 'stations'),
        Step('단지 주변', ('dabang', 'nearby'), ('{complex}',), 'stations'),
        # 역 둘레 평균 매물가는 원룸·투룸 지도 집계(markers)의 역 표시에 붙는다
        Step('역 평균 매물가 강남역', ('dabang', 'station-prices'), ('강남역',), 'prices'),
        # 분양은 시·군·구 경계 사각형에서 주소로 고른다. 동·역·좌표로 찾아도 같은 지도 범위 주소(sale-list/category/bbox)라
        # 시 하나로 본다 (동 경계 파일은 아파트 동 경계에서 본다). 분양이 적은 구는 빈 날이 있어(2026-10-27 실측: 강남구 2곳,
        # 송파구 0곳) 확인 못 함이 이어지면 막힘으로 잘못 알린다. 많은 곳(평택시 40곳)으로 본다. 경계 사각형에 이웃 시가 섞여
        # (앞 5곳 중 2곳이 평택시 밖) 한 쪽(24곳)을 다 본다. 요청은 1회다
        Step(
            '분양 찾기 평택시', DABANG_LISTINGS[:2] + ('sales',), ('평택시', '--limit', '24'), 'sales',
            (Capture('sale', 'sales', 'sale_id'),),
        ),
        Step('분양 상세', ('dabang', 'sale'), ('{sale}',), 'schedules'),
        Step('청약 일정', ('dabang', 'sale-schedule'), ('--limit', '3'), 'schedules', may_be_empty=True),
        Step('조회 순위 단지', ('dabang', 'trending-complexes'), ('--limit', '3'), 'rankings'),
        Step('조회 순위 동', ('dabang', 'trending-complexes'), ('--unit', '동', '--limit', '3'), 'rankings'),
        # 기본 기간 '이번주' 는 월요일 아침에 아직 집계가 없어 빈 목록이다 (2026-10-26 월 실측: 이번주 0곳, 지난주·이번달은 있음).
        # 새벽 감시가 월요일마다 고장으로 잘못 알리지 않게 지난주로 본다
        Step('거래 순위', ('dabang', 'trade-rankings'), ('--period', '지난주', '--limit', '3'), 'rankings'),
        # 동 순위와 단지 순위는 다른 주소다
        Step('구 안 동 순위 강남구', ('dabang', 'region-ranking'), ('강남구', '--by', '평균가', '--limit', '3'), 'rankings'),
        Step(
            '구 안 단지 순위 강남구', ('dabang', 'region-ranking'), ('강남구', '--by', '전세가율', '--unit', '단지', '--limit', '3'),
            'rankings',
        ),
        # 학교·학원·인구·시설 순위는 동네정보 순위 주소(region-info/{주제}/ranking/{항목})다
        Step('구 안 학원 순위 강남구', ('dabang', 'region-ranking'), ('강남구', '--by', '학원수', '--limit', '3'), 'rankings'),
    ),
}

# 매일 실행(워크플로 matrix)이 도는 소스. matrix 와 같게 둔다. 네이버는 GitHub 러너에서 응답을 받지 못해 로컬에서만 돌린다
DAILY_GROUPS: tuple[str, ...] = ('zigbang', 'daangn', 'dabang')

OK: str = 'ok'
BROKEN: str = 'broken'
UNKNOWN: str = 'unknown'
STATUS_LABELS: dict[str, str] = {OK: '✅ 정상', BROKEN: '❌ 고장', UNKNOWN: '⚠️ 확인 못 함'}
# 사이트가 바뀐 것인지 알 수 없는 에러. 그 밖의 에러 코드(PARSE_ERROR, INTERNAL_ERROR, NOT_FOUND, REGION_NOT_FOUND 등)는 고장이다
UNKNOWN_CODES: frozenset[str] = frozenset({'RATE_LIMITED', 'NETWORK_ERROR', 'LISTING_UNAVAILABLE'})

BROKEN_LABEL: str = 'api-broken'
BLOCKED_LABEL: str = 'api-blocked'
# 같은 소스가 이만큼 연속한 날 확인 못 함이면 알린다 (오늘 포함, 날마다 그날 마지막 실행으로 본다)
BLOCKED_STREAK: int = 3
WORKFLOW_FILE: str = 'api-monitor.yml'
REPORT_ARTIFACT: str = 'report'


# --- 조회 ---

def _error(stderr: str) -> dict[str, Any] | None:
    """stderr 의 에러 JSON (`--verbose` 로그 뒤 마지막 `{` 줄)."""
    for line in reversed(stderr.splitlines()):
        if line.startswith('{'):
            try:
                body = json.loads(line).get('error')
            except ValueError:
                return None
            return body if isinstance(body, dict) else None
    return None


def _is_unknown(error: dict[str, Any]) -> bool:
    code = error.get('code')
    if code in UNKNOWN_CODES:
        return True
    # 서버 5xx 는 사이트가 바뀐 것이 아니다. 4xx 와 상태 없는 UPSTREAM_ERROR(웹 쿼리 해시 거절 등)는 요청이 맞지 않게 된 것이라 고장이다
    status = error.get('status')
    return code == 'UPSTREAM_ERROR' and isinstance(status, int) and status >= 500


def _value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split('.'):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _present(value: Any) -> bool:
    return value is not None and value != '' and value != [] and value != {}


def _capture(data: dict[str, Any], capture: Capture) -> str | None:
    if not capture.items:
        value = data.get(capture.field)
        return str(value) if _present(value) else None
    items = data.get(capture.items)
    if not isinstance(items, list):
        return None
    found = [
        item for item in items
        if isinstance(item, dict) and _present(item.get(capture.field)) and str(item[capture.field]).startswith(capture.prefix)
        and (capture.where is None or item.get(capture.where[0]) == capture.where[1])
    ]
    if capture.largest:
        found.sort(key=lambda item: item[capture.largest] if isinstance(item.get(capture.largest), int | float) else -1, reverse=True)
    return str(found[0][capture.field]) if found else None


def _names(step: Step) -> list[str]:
    """인자에 채워야 하는 `{name}` 들."""
    return [name for arg in step.args for _, name, _, _ in string.Formatter().parse(arg) if name]


def _run_step(step: Step, values: dict[str, str]) -> tuple[str, str, dict[str, Any] | None]:
    """(판정, 내용, stdout JSON)."""
    command = [*step.command, *(arg.format(**values) for arg in step.args)]
    print(f"::group::jibsa {' '.join(command)}", flush=True)
    try:
        done = subprocess.run(
            [sys.executable, '-m', 'jibsa', '--verbose', *command],
            capture_output=True, text=True, encoding='utf-8', timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print('::endgroup::', flush=True)
        return UNKNOWN, f'{COMMAND_TIMEOUT_SECONDS}초 안에 끝나지 않음', None
    # 요청 로그만 남긴다. 결과(매물 제목·주소)는 공개 실행 기록에 남기지 않고, 고장일 때만 앞부분을 남긴다
    print(done.stderr.strip())
    status, detail, data = _judge(step, done)
    if status != OK:
        print(done.stdout.strip()[:1000])
    print('::endgroup::', flush=True)
    return status, detail, data


def _judge(step: Step, done: subprocess.CompletedProcess[str]) -> tuple[str, str, dict[str, Any] | None]:
    # 결과는 나오지만 고쳐야 한다는 안내. 웹 쿼리가 바뀌어 예전 방식으로 돌았거나(당근 FEED_FALLBACK_NOTE), 덤 조회·대체 경로
    # (단지 후보·매물 수·역 검색 등)의 쿼리가 거절되거나 응답 형식이 바뀌어 그 값만 받지 못했다(당근 partial_failure_note).
    # 문구를 베끼면 jibsa 쪽 문구가 바뀔 때 감시만 조용히 멈춰 상수를 가져온다. jibsa 는 조회 잡에만 설치돼(정리 잡은 표만
    # 만든다) 여기서 가져온다
    from jibsa.core.listing import (
        UPDATE_MAYBE_NEEDED,
        UPDATE_NEEDED,
    )

    if done.returncode == 0:
        try:
            data = json.loads(done.stdout)
        except ValueError:
            return BROKEN, 'stdout 이 JSON 이 아님', None
        if not isinstance(data, dict):
            return BROKEN, 'stdout 이 JSON 객체가 아님', None
        degraded = [
            note for note in data.get('notes') or []
            if isinstance(note, str) and (UPDATE_NEEDED in note or UPDATE_MAYBE_NEEDED in note)
        ]
        if degraded:
            return BROKEN, f'대체 경로로 돌았거나 일부를 받지 못함: {degraded[0][:200]}', data
        value = _value(data, step.expect)
        if not _present(value):
            # 칸이 아예 없거나 목록이 아니면 응답 형식이 바뀐 것이라 empty_ok 여도 아래에서 고장으로 본다
            if step.empty_ok and value == []:
                return OK, '0건 (빈 목록도 정상인 칸)', data
            # 하루 비었다고 고장으로 보지 않는다. 계속 비면 사흘 연속 확인 못 함(api-blocked)으로 알린다
            if step.may_be_empty:
                return UNKNOWN, f'{step.expect} 칸이 비어 있음 (사이트가 빈 목록을 줄 때가 있음)', data
            # 덤 조회가 요청 제한·서버 오류·연결 실패로 그 칸만 못 받았다. 응답 형식이 바뀌었거나 요청이 거절된 실패는 안내에
            # 업데이트 문구가 있어 위에서 고장으로 본다 (당근 partial_failure_note, 다방 단지 최근 실거래 요약)
            failed = next((note for note in data.get('notes') or [] if isinstance(note, str) and note.startswith('[실패] ')), None)
            if failed is not None:
                return UNKNOWN, f'{step.expect} 칸이 비어 있음 (덤 조회 실패: {failed[:200]})', data
            return BROKEN, f'{step.expect} 칸이 비어 있음', data
        return OK, f'{len(value)}건' if isinstance(value, list) else f'{step.expect} 있음', data
    error = _error(done.stderr)
    if error is None:
        return BROKEN, f'exit {done.returncode}, 에러 JSON 없음', None
    detail = ' '.join(str(part) for part in (error.get('code'), error.get('status')) if part)
    message = str(error.get('message') or '').replace('\n', ' ')
    return (UNKNOWN if _is_unknown(error) else BROKEN), f'{detail}: {message[:200]}', None


def _today() -> datetime.date:
    """한국 날짜 (`KST`)."""
    return datetime.datetime.now(KST).date()


def run_group(name: str) -> dict[str, Any]:
    """소스 하나의 명령을 차례로 부른다. 앞 명령이 넘길 번호를 주지 않은 명령은 건너뛴다 (확인 못 함)."""
    check_in = _today() + datetime.timedelta(days=STAY_CHECK_IN_DAYS)
    values: dict[str, str] = {'check_in': check_in.isoformat(), 'check_out': (check_in + datetime.timedelta(days=6)).isoformat()}
    steps: list[dict[str, str]] = []
    for step in GROUPS[name]:
        line = ' '.join(step.command)
        missing = [field for field in _names(step) if field not in values]
        if missing:
            steps.append({
                'label': step.label, 'command': line, 'status': UNKNOWN,
                'detail': f"앞 명령 결과에 {', '.join(missing)} 값이 없어 건너뜀",
            })
            continue
        status, detail, data = _run_step(step, values)
        for capture in step.captures:
            found = _capture(data, capture) if data else None
            if found is not None:
                values.setdefault(capture.name, found)
        steps.append({'label': step.label, 'command': line, 'status': status, 'detail': detail})
    return {'group': name, 'date': _today().isoformat(), 'status': _overall([step['status'] for step in steps]), 'steps': steps}


def _overall(statuses: list[str]) -> str:
    if BROKEN in statuses:
        return BROKEN
    return UNKNOWN if UNKNOWN in statuses else OK


# --- 결과 정리 ---

def _table(results: list[dict[str, Any]]) -> str:
    rows = ['| 소스 | 명령 | 결과 | 내용 |', '| --- | --- | --- | --- |']
    for result in results:
        for step in result['steps']:
            detail = step['detail'].replace('|', '\\|')
            rows.append(f"| {result['group']} | {step['label']} (`{step['command']}`) | {STATUS_LABELS[step['status']]} | {detail} |")
    return '\n'.join(rows)


def _run_link(text: str = '실행 기록') -> str:
    server, repository, run_id = (os.environ.get(key) for key in ('GITHUB_SERVER_URL', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID'))
    return f' ([{text}]({server}/{repository}/actions/runs/{run_id}))' if server and repository and run_id else ''


def _gh(*args: str, write: bool = False, dry_run: bool = False) -> str:
    """gh CLI. `dry_run` 이면 이슈·라벨을 바꾸는 명령은 보내지 않고 출력만 한다."""
    if write and dry_run:
        print('[dry-run] gh', ' '.join(args))
        return ''
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True, encoding='utf-8').stdout


def _open_issue(label: str) -> int | None:
    issues = json.loads(_gh('issue', 'list', '--label', label, '--state', 'open', '--json', 'number', '--limit', '1'))
    return issues[0]['number'] if issues else None


def _previous_reports(days: int) -> list[dict[str, Any]]:
    """어제부터 하루씩 거꾸로 `days` 일의 소스별 판정 (날마다 그날 마지막 예약·수동 실행 하나, 가까운 날부터).

    실행 수로 세면 막힌 날 손으로 두 번 다시 돌려도 같은 날에 '사흘 연속' 이 되고, PR 실행이 많으면 목록에서 앞날이 밀려났다.
    실행이 없거나 결과 파일이 없는 날(만료·실패)을 만나면 거기서 멈춘다.
    """
    try:
        runs = json.loads(_gh(
            'run', 'list', '--workflow', WORKFLOW_FILE, '--status', 'completed', '--limit', '50',
            '--json', 'databaseId,event,conclusion,createdAt',
        ))
    except subprocess.CalledProcessError:
        # 워크플로가 아직 기본 브랜치에 없으면(첫 실행 전) 실행 목록을 묻지 못한다
        return []
    current = os.environ.get('GITHUB_RUN_ID')
    latest: dict[datetime.date, int] = {}
    for run in runs:
        # 취소한 실행은 정리 잡이 돌지 않아 결과 파일이 없다
        if run['event'] not in ('schedule', 'workflow_dispatch') or run['conclusion'] == 'cancelled' or str(run['databaseId']) == current:
            continue
        # 목록은 최근 실행부터라 그날 처음 만난 실행이 그날 마지막 실행이다
        latest.setdefault(datetime.datetime.fromisoformat(run['createdAt']).astimezone(KST).date(), run['databaseId'])
    reports: list[dict[str, Any]] = []
    for back in range(1, days + 1):
        run_id = latest.get(_today() - datetime.timedelta(days=back))
        if run_id is None:
            break
        with tempfile.TemporaryDirectory() as folder:
            try:
                _gh('run', 'download', str(run_id), '--name', REPORT_ARTIFACT, '--dir', folder)
            except subprocess.CalledProcessError:
                break
            reports.append(json.loads((Path(folder) / 'report.json').read_text(encoding='utf-8')))
    return reports


def _update_issues(results: list[dict[str, Any]], dry_run: bool) -> None:
    """고장은 api-broken, 사흘 연속 확인 못 함은 api-blocked 이슈로 알린다. 다시 모두 괜찮아지면 닫는다."""
    table, link = _table(results), _run_link()
    statuses = {result['group']: result['status'] for result in results}
    broken = [group for group, status in statuses.items() if status == BROKEN]
    _gh('label', 'create', BROKEN_LABEL, '--color', 'd73a4a', '--description', '매일 API 감시가 찾은 고장', '--force', write=True, dry_run=dry_run)
    _gh('label', 'create', BLOCKED_LABEL, '--color', 'fbca04', '--description', '매일 API 감시가 며칠째 확인하지 못함', '--force', write=True, dry_run=dry_run)

    number = _open_issue(BROKEN_LABEL)
    if broken:
        body = f"{_today()} 감시에서 고장: {', '.join(broken)}{link}\n\n{table}"
        if number is None:
            _gh('issue', 'create', '--label', BROKEN_LABEL, '--title', f"API 감시: 고장 ({', '.join(broken)})", '--body', body,
                write=True, dry_run=dry_run)
        else:
            _gh('issue', 'comment', str(number), '--body', body, write=True, dry_run=dry_run)
    elif number is not None and all(status == OK for status in statuses.values()):
        _gh('issue', 'close', str(number), '--comment', f'{_today()} 감시에서 모두 정상이다{link}', write=True, dry_run=dry_run)

    previous = [{result['group']: result['status'] for result in report['results']} for report in _previous_reports(BLOCKED_STREAK - 1)]
    streak = [
        group for group, status in statuses.items()
        if status == UNKNOWN and len(previous) == BLOCKED_STREAK - 1 and all(report.get(group) == UNKNOWN for report in previous)
    ]
    number = _open_issue(BLOCKED_LABEL)
    if streak and number is None:
        body = (f"{BLOCKED_STREAK}일 연속 확인 못 함: {', '.join(streak)}{_run_link('오늘 실행 기록')}. 요청 제한·서버 오류 등으로 "
                f'고장인지 알 수 없는 상태가 이어진다. 막힘이 계속되면 그 소스를 덜 자주 돌리는 것을 검토한다.\n\n{table}')
        _gh('issue', 'create', '--label', BLOCKED_LABEL, '--title', f"API 감시: {BLOCKED_STREAK}일째 확인 못 함 ({', '.join(streak)})",
            '--body', body, write=True, dry_run=dry_run)
    elif number is not None and UNKNOWN not in statuses.values():
        _gh('issue', 'close', str(number), '--comment', f'{_today()} 감시에서 확인 못 함이 없다{link}', write=True, dry_run=dry_run)


def report(paths: list[str], *, issues: bool, dry_run: bool) -> int:
    """소스별 결과 파일을 모아 표를 남기고, 고장이 있으면 1 을 돌려준다 (실행이 실패로 끝나 GitHub 이 메일로 알린다)."""
    found = {}
    for path in paths:
        # 결과 파일이 하나도 없으면 셸이 글롭(result-*.json)을 그대로 넘긴다
        if not Path(path).is_file():
            continue
        result = json.loads(Path(path).read_text(encoding='utf-8'))
        found[result['group']] = result
    # 매일 도는 소스 중 결과 파일이 없는 것은 조회 잡이 감시 코드나 설치에서 실패한 것이다. 로컬에서 돌린 다른 소스 결과도 함께 싣는다
    results = [
        found.get(group) or {
            'group': group, 'status': BROKEN,
            'steps': [{'label': '조회 잡', 'command': '-', 'status': BROKEN, 'detail': '결과 파일 없음 (조회 잡 실패)'}],
        }
        for group in [*DAILY_GROUPS, *(group for group in found if group not in DAILY_GROUPS)]
    ]
    text = f'## API 감시 {_today()}\n\n{_table(results)}\n'
    print(text)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as file:
            file.write(text)
    Path('report.json').write_text(json.dumps({'results': results}, ensure_ascii=False), encoding='utf-8')
    if issues:
        _update_issues(results, dry_run)
    return 1 if any(result['status'] == BROKEN for result in results) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='action', required=True)
    run = commands.add_parser('run', help='소스 하나의 명령을 부르고 결과를 JSON 파일로 쓴다')
    run.add_argument('group', choices=list(GROUPS))
    run.add_argument('--out', required=True)
    collect = commands.add_parser('report', help='결과 파일을 모아 표를 남기고 이슈를 고친다')
    collect.add_argument('paths', nargs='*')
    collect.add_argument('--issues', action='store_true', help='고장·연속 확인 못 함을 이슈로 알린다 (예약·수동 실행만)')
    collect.add_argument('--dry-run', action='store_true', help='이슈·라벨을 바꾸지 않고 보낼 gh 명령만 출력한다')
    options = parser.parse_args()
    if options.action == 'run':
        result = run_group(options.group)
        Path(options.out).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        print(_table([result]))
        return 0
    return report(options.paths, issues=options.issues, dry_run=options.dry_run)


if __name__ == '__main__':
    sys.exit(main())
