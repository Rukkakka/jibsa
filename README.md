<p align="center">
  <img src="https://raw.githubusercontent.com/Rukkakka/jibsa/main/docs/logo.svg" alt="jibsa (집사)" width="280">
</p>

<p align="center">
  <a href="https://pypi.org/project/jibsa/"><img src="https://img.shields.io/pypi/v/jibsa" alt="PyPI"></a>
  <a href="https://pypi.org/project/jibsa/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://github.com/Rukkakka/jibsa/actions/workflows/ci.yml"><img src="https://github.com/Rukkakka/jibsa/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Rukkakka/jibsa/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center">
  직방·네이버 부동산·당근부동산의 원룸·오피스텔·빌라·아파트·상가 매물과 실거래가를 조회하는 LLM 에이전트용 CLI.<br>
  Korean real estate CLI for LLM agents: search current listings and real transaction prices on Zigbang, Naver Real Estate and Daangn.
</p>

<p align="center">
  <a href="https://github.com/Rukkakka/jibsa#기능">기능</a> ·
  <a href="https://github.com/Rukkakka/jibsa#빠른-시작">빠른 시작</a> ·
  <a href="https://github.com/Rukkakka/jibsa#설치">설치</a> ·
  <a href="https://github.com/Rukkakka/jibsa#llm-에이전트에-연결하기">LLM 에이전트에 연결하기</a> ·
  <a href="https://github.com/Rukkakka/jibsa#문서">문서</a>
</p>

> **집사**: 주인 곁에서 궂은일을 대신 맡아 주는 사람.
> **집 + 사(다)**: 집을 구하는 일.
>
> 집 구하는 수고를 대신 맡아 주는 집사라는 뜻으로 지은 이름이다.

Claude, ChatGPT 같은 LLM 에이전트가 집을 찾을 때 셸로 부르는 도구다. 무엇을 원하는지는 사용자와 LLM 이 정하고, 여러 사이트를 돌며 **지금 거래할 수 있는 매물**을 확인해 오는 심부름은 집사가 맡는다.

![Claude Code 가 jibsa guide 를 읽고 직방에서 강남역 근처 월세 원룸을 조회해 표로 정리하는 터미널 데모. 매물은 데모용 가상 데이터다](https://raw.githubusercontent.com/Rukkakka/jibsa/main/docs/demo/claude.gif)

Claude Code 에 "직방에서 강남역 근처 월세 70만원 이하 원룸 찾아줘" 라고 시킨 실제 화면이다. Claude 가 `jibsa guide` 를 읽고 명령을 골라 조회한 뒤 결과를 표로 정리한다. **매물은 데모용 가상 데이터다.** 에이전트에 연결하는 방법은 [LLM 에이전트에 연결하기](https://github.com/Rukkakka/jibsa#llm-에이전트에-연결하기)에 있다.

> 비공식 API 를 쓴다. 스펙이 예고 없이 바뀔 수 있고, 자동수집은 각 서비스 약관과 상충할 소지가 있으니 개인 조회 용도로만 쓴다.

## 기능

- **매물 찾기** — 원룸·오피스텔·빌라·아파트·상가를 동·역 이름이나 좌표로 찾는다 (직방·네이버·당근). 주 단위 단기임대도 찾는다 (직방)
- **매물 상세** — 관리비·옵션·입주일·주차·건물 용도처럼 계약 전에 볼 정보를 준다. 사진·연락처는 원 사이트 링크로 안내한다
- **단지와 가격** — 단지 정보, 실거래가, 기관 시세, 월별·주별 가격 흐름
- **동네 고르기** — 회사까지 지하철 통근 기준으로 매물 찾기, 학교 배정, 동네 후기·개발 호재·어린이집 (당근)

세 사이트를 한 번에 찾는 통합 검색은 아직 없어서 사이트마다 따로 부른다 (`jibsa zigbang …`, `jibsa naver …`, `jibsa daangn …`). 하려는 일별 명령 표는 [LLM 사용 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md#무엇을-하려면)에 있다.

- **로그인·API 키·설정 파일이 없다.** 로그인하지 않은 사람이 사이트에서 볼 수 있는 정보만 조회한다 ([원칙](https://github.com/Rukkakka/jibsa#원칙-로그인-없는-기능만))
- **금액은 전부 만원**(`*_manwon`)이다. 원 단위로 주는 네이버도 만원으로 바꿔 준다
- 거래가 끝난 매물은 내보내지 않는다
- 사진·중개사 연락처·매물 설명·매물 좌표는 내보내지 않는다. 확인·문의는 결과의 `url` 에서 한다
- 조회 범위·제한·조건 해석은 결과의 `notes` 로 알린다
- 모든 요청이 사이트별 요청 제한을 지나고, 그 상태를 모든 jibsa 프로세스가 함께 쓴다

## 빠른 시작

```bash
uv tool install jibsa        # 또는 pipx install jibsa
jibsa zigbang search listings room 강남역 --trade 월세 --rent-max 70 --limit 1
```

![uv 로 jibsa 를 설치하고 직방에서 강남역 근처 월세 원룸을 직접 조회하는 터미널 데모. 조회 결과의 매물은 데모용 가상 데이터다](https://raw.githubusercontent.com/Rukkakka/jibsa/main/docs/demo/demo.gif)

uv 로 설치하고 직접 조회해 본 장면이다. 설치는 실제 PyPI 설치 화면이고, **조회 결과의 매물은 데모용 가상 데이터다.**

결과는 stdout 에 JSON 하나로 나온다 (에러는 stderr 에 JSON). 아래는 위 명령의 출력 모양이다. 데모 영상과 같은 **가상 매물**(`[가상] 예시 원룸 1`)을 넣어 돌린 것이라 값은 모두 지어낸 것이고, 실제로 조회하면 지금 직방에 올라온 매물이 나온다.

```json
{
  "notes": [
    "조건에 맞는 매물 약 12건 중 검색 중심에서 가까운 1건입니다. 더 보려면 --limit 을 늘리거나 조건·반경을 좁히세요"
  ],
  "region": {
    "name": "강남역",
    "address": "서울특별시 강남구 역삼동",
    "lat": 37.497942,
    "lng": 127.027621,
    "legal_division_code": null
  },
  "radius_km": 1.0,
  "total": 12,
  "returned": 1,
  "listings": [
    {
      "source": "zigbang",
      "id": "99990001",
      "url": "https://www.zigbang.com/home/oneroom/items/99990001",
      "trade_type": "월세",
      "property_type": "원룸",
      "room_type": "분리형원룸",
      "title": "[가상] 예시 원룸 1",
      "deposit_manwon": 1.0,
      "rent_manwon": 1.0,
      "manage_cost_manwon": 1.0,
      "area_m2": 1.0,
      "area_pyeong": 0.3,
      "floor": "1",
      "building_floor": "1",
      "address": "서울특별시 강남구 역삼동 000-1",
      "distance_km": 0.15,
      "registered_at": "2026-10-09",
      "approved_at": null
    }
  ]
}
```

이어서 `jibsa zigbang listing <id>` 로 관리비·옵션·입주일 같은 상세를 본다. 명령별 옵션과 반환 필드는 [직방](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md)·[네이버](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md)·[당근](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md) 사용법에 있다.

## 설치

Python 3.11 이상이 필요하고 (uv 로 설치하면 없어도 된다), macOS·Linux·Windows 에서 쓸 수 있다. 셋 중 하나만 하면 된다.

| 방법 | 설치 | 업데이트 |
| --- | --- | --- |
| **uv** (권장) | `uv tool install jibsa` | `uv tool upgrade jibsa` |
| pipx | `pipx install jibsa` | `pipx upgrade jibsa` |
| pip + 가상환경 | `python3 -m venv ~/.venvs/jibsa && ~/.venvs/jibsa/bin/pip install jibsa` | `~/.venvs/jibsa/bin/pip install -U jibsa` |

```bash
jibsa --help      # 명령 목록이 나오면 성공
jibsa limits      # 요청 제한 상태 JSON. 네트워크 요청은 보내지 않는다
```

설치하지 않고 한 번 써 보려면 `uvx jibsa --help` 로 부른다. 아직 릴리스하지 않은 최신 수정은 `uv tool install git+https://github.com/Rukkakka/jibsa` 로 받는다.

**준비물(Python·git) 설치, Windows·PowerShell 명령, `command not found` 일 때 PATH 설정, 특정 버전 설치, 삭제**는 [설치 문서](https://github.com/Rukkakka/jibsa/blob/main/docs/install.md)에 있다. 버전마다 바뀐 점은 [변경 기록](https://github.com/Rukkakka/jibsa/blob/main/CHANGELOG.md)에 있다.

## LLM 에이전트에 연결하기

에이전트에게는 사용 문서 전체 대신 [LLM 사용 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md) 하나만 먼저 읽게 한다. 명령 고르는 법, 출력 읽는 법, 에러 대응을 짧게 모은 문서로, 설치본에 들어 있어 `jibsa guide` 로 바로 출력된다 (설치한 버전과 내용이 같고 네트워크를 쓰지 않는다). 더 자세한 설명이 필요하면 에이전트가 `jibsa guide zigbang listing` 처럼 사이트별 문서에서 필요한 절만 골라 읽는다. 에이전트 지침 파일(`CLAUDE.md`, `AGENTS.md` 등)에 이렇게 적어 두면 된다.

```text
집을 찾을 때는 jibsa CLI 를 쓴다. 처음 쓰기 전에 `jibsa guide` 를 실행해 읽고 그 규칙을 따른다.
```

[맨 위 영상](https://github.com/Rukkakka/jibsa#readme)이 이 한 줄을 적어 둔 폴더에서 Claude Code 에 매물을 찾게 한 장면이다. 지침 파일의 두 번째 줄("이 폴더의 jibsa 는 데모용 가상 매물을 돌려준다")은 데모용이다.

## 설정

로그인·API 키·설정 파일은 없다. 환경 변수 세 개만 쓴다.

| 환경 변수 | 하는 일 |
| --- | --- |
| `JIBSA_STATE_DIR` | 요청 제한 상태 파일을 둘 디렉터리. 기본은 `~/.cache/jibsa`. 기본 위치에 쓸 수 없는 환경(샌드박스 등)이면 쓸 수 있는 폴더로 바꾼다 |
| `XDG_CACHE_HOME` | 설정해 두었으면 그 아래 `jibsa` 를 쓴다 (`JIBSA_STATE_DIR` 이 우선) |
| `PYTHONUTF8` | Windows 에서 `1` 로 설정한다 (아래) |

### Windows 에서 쓸 때

Windows 의 Python 은 출력 인코딩이 기본으로 UTF-8 이 아니다 (한국어 Windows 는 cp949). LLM 에이전트가 jibsa 를 부르면 출력이 파이프로 넘어가는데, 이때 한글이 깨지거나 cp949 에 없는 문자(이모지 등)에서 오류가 날 수 있다. 아래처럼 사용자 환경 변수를 설정하고 새 터미널을 연다. macOS·Linux 는 따로 할 것이 없다.

```powershell
setx PYTHONUTF8 1
```

## 왜 만들었나

LLM이 검색 결과만으로 집을 찾으면 이미 내려간 매물을 소개하거나, API를 추측해서 호출하다 차단되거나, 원과 만원을 혼동할 수 있다. 집사는 소스별 조회 절차와 요청 제한을 지키고, 현재 거래 가능한 매물을 공통 JSON 형식과 만원 단위로 돌려준다. 확인·사진·문의·계약은 결과의 `url`에서 한다.

## 원칙: 로그인 없는 기능만

집사는 **로그인하지 않은 사람도 사이트에서 볼 수 있는 정보만** 제공한다. 계정·쿠키·API 키를 받지 않고, 로그인이 필요한 API는 쓰지 않는다.

그래서 각 사이트에 있더라도 다음 기능은 넣지 않는다.

- 관심 단지·관심 매물, 최근 본 단지, 내 집 인증처럼 로그인해야 쓰는 기능
- 문의·예약·신고처럼 사용자를 대신해 무언가를 보내는 기능

새 API를 추가할 때도 로그인 없이 호출되는지 먼저 확인하고, 로그인이 필요하면 추가하지 않는다.

## 문서

사용 문서

- [LLM 사용 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md): 에이전트용 요약. 처음 읽을 문서
- [설치](https://github.com/Rukkakka/jibsa/blob/main/docs/install.md): 준비물, 설치 방법 세 가지, PATH, 업데이트·삭제
- [공통 사용 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md): JSON 출력, 금액·누락값, 오류 대응, 요청 제한과 `limits`
- [당근 CLI 사용법](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md)
- [네이버 CLI 사용법](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md)
- [직방 CLI 사용법](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md)
- [변경 기록](https://github.com/Rukkakka/jibsa/blob/main/CHANGELOG.md): 버전별로 바뀐 점

개발 문서

- [공통 개발 규약](https://github.com/Rukkakka/jibsa/blob/main/AGENTS.md) · [개발 환경](https://github.com/Rukkakka/jibsa/blob/main/references/development.md) · [버전·릴리스](https://github.com/Rukkakka/jibsa/blob/main/references/release.md)
- [당근 개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/references/providers/daangn.md)
- [네이버 개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/references/providers/naver.md)
- [직방 개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/references/providers/zigbang.md)

## 기여

버그·기능 제안은 [이슈](https://github.com/Rukkakka/jibsa/issues/new/choose)로 열고, 코드를 고치기 전에 [개발 규약](https://github.com/Rukkakka/jibsa/blob/main/AGENTS.md)의 "꼭 지킬 것"(로그인 없는 기능만, 금액은 만원, 출력 규약 등)을 읽는다. 개발 환경 설치와 검사는 [개발 환경](https://github.com/Rukkakka/jibsa/blob/main/references/development.md), 이슈 → 브랜치 → 커밋 → PR 절차는 [작업 절차](https://github.com/Rukkakka/jibsa/blob/main/references/workflow.md)에 있다. 모든 변경은 PR 로 들어가고 CI(ruff·mypy·pytest·설치 확인)를 통과해야 한다.

## 라이선스

[MIT](https://github.com/Rukkakka/jibsa/blob/main/LICENSE)
