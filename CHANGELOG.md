# Changelog

jibsa 의 버전별 변경 기록. 사용자(에이전트 포함)에게 보이는 변경만 적고, 아직 릴리스하지 않은 변경은
`Unreleased` 에 쌓는다. 번호 규칙과 쓰는 법은 [references/release.md](references/release.md) 에 있다.

## Unreleased

### 추가

- PyPI 에서 설치할 수 있다: `uv tool install jibsa`, `pipx install jibsa`, `pip install jibsa`, 설치 없이 `uvx jibsa`. `jibsa==0.2.0` 처럼 버전도 고를 수 있다 (#33)

## 0.1.1 — 2026-10-13

### 수정

- 직방 역·좌표 반경 검색에서 결과를 일부만 보여 줄 때 이미 역으로 찾았는데도 "역 이름처럼 더 좁은 지역으로 다시 검색하세요" 라고 안내하던 문제. 반경 검색은 "--radius 를 줄여 다시 검색하세요" 로 안내한다 (#8)
- 당근 `--city 광주시` 가 경기도 광주시와 전남광주통합특별시를 함께 골라 다른 지역으로 조회할 수 있던 문제. `광주시` 는 경기도 광주시만 가리키고, `--city` 를 줬는데도 여러 곳이 맞으면 구 이름으로 좁히라고 안내한다 (#14)
- 당근 장소 이름 검색에서 직방 지역 검색이 서버·네트워크 오류로 실패하면 당근 오류(`source: daangn`)로 끝나던 문제. 네이버로 다시 찾고, 그래도 못 찾으면 `source: zigbang` 으로 알린다 (#15)
- 직방 `search listings --complex apt-…` 에 단지에 없는 평형 ID 를 주면 0건으로 끝나던 문제. `INVALID_ARGUMENT` 로 알리고, 1 미만 평형 ID 는 조회 전에 막는다 (#16)
- 반경 검색의 `total_in_radius` 와 "반경 안 N건뿐" 안내의 건수가 반경 경계 근처 매물 때문에 어긋나던 문제 (직방 room·store·stay). 둘 다 출력한 `distance_km` 로 센다 (#17)
- 반경 밖 매물 안내가 거리를 모르는 매물(`distance_km: null`)을 반경 안으로 세던 문제 (#17)
- 직방 `search listings store --area-max 0` 이 요청을 보낸 뒤 영어 오류로 끝나던 문제. 조회 전에 `INVALID_ARGUMENT` 로 막는다 (#18)
- 직방 매물 상세와 단기임대 목록에서 응답에 옵션·인근 역·관리비 포함 항목·할인 정보가 빠지면 `[]`(없음)로 내보내던 것을 `null`(모름)로 바꿈 (#19)
- 당근 `search commute` 의 `WORKPLACE` 도움말이 직방으로만 위치를 찾는다고 설명하던 문서 오류 (#20)
- 라이브러리의 비동기 클라이언트가 요청 제한 상태 파일 잠금을 기다리는 동안 이벤트 루프 전체를 멈추던 문제 (#21)
- Windows 에서 요청 제한 상태 폴더 자리에 파일이 있어 상태를 쓸 수 없을 때 `jibsa limits` 가 에러 대신 빈 상태를 보여 주던 문제. macOS·Linux 처럼 `INTERNAL_ERROR` 로 알린다 (#30)

## 0.1.0 — 2026-10-11

### 추가

- 첫 릴리스: 직방·네이버·당근부동산의 현재 매물·실거래·단지 정보를 조회하는 CLI 와 `jibsa guide`
- `jibsa --version` — 설치한 버전과 커밋을 출력
