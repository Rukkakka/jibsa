# jibsa (집사)

직방·네이버 부동산·당근부동산의 원룸·오피스텔·빌라·아파트·상가 매물과 실거래가를 조회하는 LLM 에이전트용 CLI.
Korean real estate CLI for LLM agents: search current listings and real transaction prices on Zigbang, Naver Real Estate and Daangn.

> **집사**: 주인 곁에서 궂은일을 대신 맡아 주는 사람.
> **집 + 사(다)**: 집을 구하는 일.
>
> 집 구하는 수고를 대신 맡아 주는 집사라는 뜻으로 지은 이름이다.

직방·네이버 부동산·당근부동산의 **현재 거래 가능한 매물**을 조회하는 CLI. Claude, ChatGPT 같은 LLM 에이전트가 집을 찾을 때 셸로 호출하는 도구로 쓰려고 만들었다. 무엇을 원하는지는 사용자와 LLM 이 정하고, 여러 사이트를 돌며 조건에 맞는 매물을 확인해 오는 심부름은 집사가 맡는다.

![Claude Code 가 jibsa guide 를 읽고 직방에서 강남역 근처 월세 원룸을 조회해 표로 정리하는 터미널 데모. 매물은 데모용 가상 데이터다](https://raw.githubusercontent.com/Rukkakka/jibsa/main/docs/demo/claude.gif)

Claude Code 에 "직방에서 강남역 근처 월세 70만원 이하 원룸 찾아줘" 라고 시킨 실제 화면이다. Claude 가 `jibsa guide` 를 읽고 명령을 골라 조회한 뒤 결과를 표로 정리한다. **매물은 데모용 가상 데이터다** ([무엇이 실제이고 무엇이 가상인지](https://github.com/Rukkakka/jibsa#데모-영상의-가상-데이터)). 에이전트에 연결하는 방법은 [LLM 에이전트에 연결하기](https://github.com/Rukkakka/jibsa#llm-에이전트에-연결하기)에 있다.

> 비공식 API 를 쓴다. 스펙이 예고 없이 바뀔 수 있고, 자동수집은 각 서비스 약관과 상충할 소지가 있으니 개인 조회 용도로만 쓴다.

명령별 인자·옵션·사용 예시는 아래 [사용 문서](https://github.com/Rukkakka/jibsa#사용-문서)에 있다.

## 왜 만들었나

LLM이 검색 결과만으로 집을 찾으면 이미 내려간 매물을 소개하거나, API를 추측해서 호출하다 차단되거나, 원과 만원을 혼동할 수 있다. 집사는 소스별 조회 절차와 요청 제한을 지키고, 현재 거래 가능한 매물을 공통 JSON 형식과 만원 단위로 돌려준다. 확인·사진·문의·계약은 결과의 `url`에서 한다.

## 원칙: 로그인 없는 기능만

집사는 **로그인하지 않은 사람도 사이트에서 볼 수 있는 정보만** 제공한다. 계정·쿠키·API 키를 받지 않고, 로그인이 필요한 API는 쓰지 않는다.

그래서 각 사이트에 있더라도 다음 기능은 넣지 않는다.

- 관심 단지·관심 매물, 최근 본 단지, 내 집 인증처럼 로그인해야 쓰는 기능
- 문의·예약·신고처럼 사용자를 대신해 무언가를 보내는 기능

새 API를 추가할 때도 로그인 없이 호출되는지 먼저 확인하고, 로그인이 필요하면 추가하지 않는다.

## 설치

macOS·Linux·Windows 에서 쓸 수 있다. 운영체제마다 명령이 다른 곳은 나눠 적었다. Windows 명령은 PowerShell 기준이고 (명령 프롬프트 cmd 는 아님), WSL 안에서 쓴다면 Linux 를 따른다.

![uv 로 jibsa 를 설치하고 직방에서 강남역 근처 월세 원룸을 직접 조회하는 터미널 데모. 조회 결과의 매물은 데모용 가상 데이터다](https://raw.githubusercontent.com/Rukkakka/jibsa/main/docs/demo/demo.gif)

uv 로 설치하고 직접 조회해 본 장면이다. 설치는 실제 PyPI 설치 화면이고, **조회 결과의 매물은 데모용 가상 데이터다** ([무엇이 실제이고 무엇이 가상인지](https://github.com/Rukkakka/jibsa#데모-영상의-가상-데이터)).

### 1. 준비물

- **Python 3.11 이상** — 아래 A(uv)로 설치하면 없어도 된다. uv 가 알아서 받아 쓴다
- **git** — PyPI 로 설치하면 필요 없다. 아직 릴리스하지 않은 최신 수정을 GitHub 에서 받을 때만 쓴다
- 로그인·API 키는 필요 없다

| 운영체제 | Python 버전 확인 | Python 설치 | git 설치 |
|---|---|---|---|
| macOS | `python3 --version` | `brew install python@3.11`, `pyenv install 3.11`, [python.org](https://www.python.org/downloads/) 중 하나 | `xcode-select --install` 또는 `brew install git` |
| Linux | `python3 --version` | Ubuntu·Debian `sudo apt install python3 python3-venv`, Fedora `sudo dnf install python3` | `sudo apt install git` / `sudo dnf install git` |
| Windows | `py --version` | `winget install Python.Python.3.13` 또는 [python.org](https://www.python.org/downloads/) 설치 파일 | `winget install Git.Git` |

- Linux 배포판에 들어 있는 Python 이 3.11 보다 낮으면 (예: Ubuntu 22.04 는 3.10) 따로 올리지 말고 uv 로 설치한다
- Windows 에서 `python3` 를 치면 Microsoft Store 가 열릴 수 있다. python.org·winget 으로 설치했으면 `py` 를 쓴다

### 2. `jibsa` 명령 설치

어느 디렉터리에서든 `jibsa` 를 부를 수 있도록 전역 명령으로 설치한다. 셋 중 하나만 하면 된다. 도구 전용 가상환경을 따로 만들어 주는 **uv** 나 **pipx** 를 권장한다.

**A. uv (권장)**

uv 가 없으면 먼저 설치한다. 설치 뒤 `uv` 를 못 찾으면 새 터미널을 연다.

```bash
# macOS·Linux
curl -LsSf https://astral.sh/uv/install.sh | sh     # macOS 는 brew install uv 도 된다
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # 또는 winget install astral-sh.uv
```

그다음은 모든 운영체제에서 같다.

```bash
uv tool install jibsa
uv tool update-shell     # ~/.local/bin 을 PATH 에 추가 (처음 한 번). 새 터미널을 연다
```

uv 는 Python 3.11 이 없으면 알아서 받아 쓴다. 설치하지 않고 한 번 써 보려면 `uvx jibsa --help` 처럼 `uvx` 로 부른다.

**B. pipx**

pipx 를 설치하고 PATH 를 설정한다 (처음 한 번). 끝나면 새 터미널을 연다.

```bash
# macOS
brew install pipx
# Linux: Ubuntu 23.04 이상·Debian 12 이상은 sudo apt install pipx, Fedora 는 sudo dnf install pipx

pipx ensurepath
```

```powershell
# Windows (PowerShell)
py -m pip install --user pipx
py -m pipx ensurepath
```

그다음은 모든 운영체제에서 같다.

```bash
pipx install jibsa
# 기본 Python 이 3.11 미만이면: pipx install --python python3.11 jibsa
```

**C. pip + 가상환경**

```bash
# macOS·Linux
python3 -m venv ~/.venvs/jibsa        # python3 가 3.11 미만이면 python3.11 처럼 버전을 붙인다
~/.venvs/jibsa/bin/pip install jibsa

# 매번 경로를 치지 않으려면 PATH 에 링크
mkdir -p ~/.local/bin && ln -s ~/.venvs/jibsa/bin/jibsa ~/.local/bin/jibsa
```

```powershell
# Windows (PowerShell) — bin 대신 Scripts 폴더를 쓴다
py -m venv $HOME\.venvs\jibsa
& "$HOME\.venvs\jibsa\Scripts\pip.exe" install jibsa

& "$HOME\.venvs\jibsa\Scripts\jibsa.exe" --help    # 실행할 때도 전체 경로로 부른다
```

Windows 는 링크를 만들려면 관리자 권한이 필요하다. `jibsa` 만 쳐서 쓰고 싶으면 A·B 가 간단하다.

시스템 Python 에 `pip install` 하지 않는다 (macOS·최근 Linux 는 `externally-managed-environment` 로 막는다). Debian·Ubuntu 에서 `venv` 가 없다는 오류가 나면 `sudo apt install python3-venv` 를 먼저 한다.

**저장소를 이미 받아 두었다면** URL 대신 경로를 넘긴다: `uv tool install .` / `pipx install .` / `pip install .`

**특정 버전을 설치하려면** 버전을 붙인다: `uv tool install jibsa==0.2.0` (pipx·pip 도 `jibsa==0.2.0`). 버전을 붙여 설치하면 `upgrade` 해도 그 버전에 머무니, 최신으로 돌아가려면 버전 없이 다시 설치한다 (이미 설치돼 있다고 하면 `--force` 를 붙인다).

**아직 릴리스하지 않은 최신 수정을 받으려면** PyPI 대신 GitHub 주소로 설치한다: `uv tool install git+https://github.com/Rukkakka/jibsa` (pipx·pip 도 같은 주소). 이렇게 설치하면 `upgrade` 할 때 `main` 의 최신 커밋을 받고, `jibsa --version` 이 설치한 커밋을 함께 보여 준다. 버전마다 바뀐 점은 [변경 기록](https://github.com/Rukkakka/jibsa/blob/main/CHANGELOG.md)에 있다.

### 3. 설치 확인

명령은 모든 운영체제에서 같다.

```bash
jibsa --help             # 명령 목록이 나오면 성공
jibsa --version          # 설치한 버전, GitHub 주소로 설치했으면 커밋도 (텍스트)
jibsa limits             # 요청 제한 상태 JSON. 네트워크 요청은 보내지 않는다
jibsa guide              # LLM 에이전트용 사용 가이드 (텍스트)
jibsa zigbang search listings room 역삼동 --trade 월세 --limit 3   # 실제 조회 한 번
```

`jibsa: command not found` (Windows 는 `'jibsa' 용어가 ... 인식되지 않습니다`) 가 나오면 PATH 문제다. 먼저 새 터미널을 연다. 그래도 안 되면 `jibsa` 가 설치된 `~/.local/bin` (Windows 는 `C:\Users\<이름>\.local\bin`) 이 PATH 에 있는지 본다.

| 운영체제 | PATH 확인 | 없으면 추가 |
|---|---|---|
| macOS (기본 셸 zsh) | `echo $PATH` | `~/.zshrc` 에 `export PATH="$HOME/.local/bin:$PATH"` |
| Linux (기본 셸 bash) | `echo $PATH` | `~/.bashrc` 에 `export PATH="$HOME/.local/bin:$PATH"` |
| Windows (PowerShell) | `$env:Path -split ';'` | `uv tool update-shell` 이나 `py -m pipx ensurepath` 를 다시 실행. 또는 시작 메뉴에서 "환경 변수" 를 검색해 사용자 `Path` 에 추가 |

탭 자동완성이 필요하면 `jibsa --install-completion` 을 한 번 실행한다. bash·zsh·fish·PowerShell 을 지원하고 cmd 는 지원하지 않는다.

### 4. Windows 에서 쓸 때

macOS·Linux 는 따로 할 것이 없다. Windows 는 두 가지를 챙긴다.

- **UTF-8 출력 설정 (처음 한 번)** — Windows 의 Python 은 출력 인코딩이 기본으로 UTF-8 이 아니다 (한국어 Windows 는 cp949). LLM 에이전트가 jibsa 를 부르면 출력이 파이프로 넘어가는데, 이때 한글이 깨지거나 cp949 에 없는 문자(이모지 등)에서 오류가 날 수 있다. 아래처럼 사용자 환경 변수를 설정하고 새 터미널을 연다.

  ```powershell
  setx PYTHONUTF8 1
  ```

- **한 번에 하나씩 실행** — 요청 제한 상태 파일을 잠그는 기능(`fcntl`)이 Windows 에는 없다. jibsa 를 여러 개 동시에 실행하면 요청 간격이 어긋나 사이트에서 차단될 수 있으니 (특히 네이버) 명령은 하나씩 차례로 실행한다. WSL 에서는 Linux 처럼 잠금이 동작한다.

### 5. 업데이트 · 삭제

| 설치 방법 | 업데이트 | 삭제 |
|---|---|---|
| uv | `uv tool upgrade jibsa` | `uv tool uninstall jibsa` |
| pipx | `pipx upgrade jibsa` | `pipx uninstall jibsa` |
| pip (macOS·Linux) | `~/.venvs/jibsa/bin/pip install -U jibsa` | `rm -rf ~/.venvs/jibsa ~/.local/bin/jibsa` |
| pip (Windows) | `& "$HOME\.venvs\jibsa\Scripts\pip.exe" install -U jibsa` | `Remove-Item -Recurse -Force $HOME\.venvs\jibsa` |

GitHub 주소로 설치했다면 uv·pipx 의 `upgrade` 는 그 주소에서 그대로 받고, pip 은 `pip install -U --force-reinstall git+https://github.com/Rukkakka/jibsa` 로 받는다.

요청 제한 상태 파일은 삭제해도 남으니 완전히 지우려면 그 디렉터리도 삭제한다. `JIBSA_STATE_DIR` 로 위치를 바꿨다면 그 디렉터리다.

| 운영체제 | 상태 파일 위치 | 삭제 |
|---|---|---|
| macOS·Linux | `~/.cache/jibsa` (`XDG_CACHE_HOME` 을 설정했으면 `$XDG_CACHE_HOME/jibsa`) | `rm -rf ~/.cache/jibsa` |
| Windows | `C:\Users\<이름>\.cache\jibsa` | `Remove-Item -Recurse -Force $HOME\.cache\jibsa` |

## LLM 에이전트에 연결하기

에이전트에게는 사용 문서 전체 대신 [LLM 사용 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md) 하나만 먼저 읽게 한다. 명령 고르는 법, 출력 읽는 법, 에러 대응을 짧게 모아 두었고 나머지는 필요한 절만 찾아 읽게 링크했다. 설치본에 들어 있어 `jibsa guide` 로 바로 출력된다 (설치한 버전과 내용이 맞고 네트워크도 쓰지 않는다). 에이전트 지침 파일(`CLAUDE.md`, `AGENTS.md` 등)에 이렇게 적어 두면 된다.

```text
집을 찾을 때는 jibsa CLI 를 쓴다. 처음 쓰기 전에 `jibsa guide` 를 실행해 읽고 그 규칙을 따른다.
```

[맨 위 영상](https://github.com/Rukkakka/jibsa#jibsa-집사)이 이 한 줄을 적어 둔 폴더에서 Claude Code 에 매물을 찾게 한 장면이다. 지침 파일의 두 번째 줄("이 폴더의 jibsa 는 데모용 가상 매물을 돌려준다")은 데모용이다.

## 데모 영상의 가상 데이터

두 영상의 매물은 모두 데모용 가상 데이터다. 녹화할 때 jibsa 는 직방 응답만 [가상 응답](https://github.com/Rukkakka/jibsa/blob/main/docs/demo/zigbang.json)으로 바꾸고 그 밖의 요청은 막는다. 실제 정보는 직방의 강남역 검색 결과(역 번호·노선·좌표)와 매물 위치의 시·구·동 이름뿐이고, 나머지는 지어낸 값이다.

- 매물 번호는 실제 직방에 없는 `99990001`~`99990012` 이고, 오피스텔 건물 번호도 그 매물 번호와 같다. 제목은 `[가상] 예시 원룸 1`, 지번은 `000-1` 처럼 붙였다.
- 가격·관리비(만원)·층·면적(㎡)은 매물 번호 뒤 네 자리 수와 같다 (`99990001` 은 보증금 1만원·월세 1만원·1층·1㎡, 평으로는 0.3평).
- 매물 위치는 강남역 반경 1km 안에서 고른 지점이고, 번호 순으로 역에서 0.07km 씩 멀어진다 (0.15~0.92km).
- 매물 번호와 오피스텔 건물 번호가 실제 직방에 없다는 것은 2026-10-12 에 실제 API 로 확인했다.

설치 장면은 실제 PyPI 설치 화면이다 ([녹화 대본](https://github.com/Rukkakka/jibsa/blob/main/docs/demo/demo.tape)). Claude 의 답은 실제 Claude Code 가 쓴 것이고 ([녹화 대본](https://github.com/Rukkakka/jibsa/blob/main/docs/demo/claude.tape)), 배너의 요금제 글자는 녹화한 계정 정보라 가렸다.

## 사용 문서

통합 검색(`jibsa search`)은 아직 없고 추가할 예정이다.

- [LLM 사용 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md): 에이전트용 요약. 처음 읽을 문서
- [공통 사용 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md): JSON 출력, 금액·누락값, 오류 대응, 요청 제한과 `limits`
- [당근 CLI 사용법](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md)
- [네이버 CLI 사용법](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md)
- [직방 CLI 사용법](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md)
- [변경 기록](https://github.com/Rukkakka/jibsa/blob/main/CHANGELOG.md): 버전별로 바뀐 점

## 개발 문서

- [공통 개발 규약](https://github.com/Rukkakka/jibsa/blob/main/AGENTS.md) · [개발 환경](https://github.com/Rukkakka/jibsa/blob/main/references/development.md) · [버전·릴리스](https://github.com/Rukkakka/jibsa/blob/main/references/release.md)
- [당근 개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/references/providers/daangn.md)
- [네이버 개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/references/providers/naver.md)
- [직방 개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/references/providers/zigbang.md)

## 라이선스

[MIT](https://github.com/Rukkakka/jibsa/blob/main/LICENSE)
