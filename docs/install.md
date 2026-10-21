# 설치

[README](../README.md) · [공통 사용 규칙](common.md) · [LLM 가이드](llm.md)

> 한 줄 설치와 첫 조회는 [README 의 빠른 시작](../README.md#빠른-시작)에 있다. 이 문서는 준비물, 설치 방법 세 가지,
> PATH 문제, 업데이트·삭제까지 자세히 적는다.

macOS·Linux·Windows 에서 쓸 수 있다. 운영체제마다 명령이 다른 곳은 나눠 적었다. Windows 명령은 PowerShell 기준이고 (명령 프롬프트 cmd 는 아님), WSL 안에서 쓴다면 Linux 를 따른다.

## 1. 준비물

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

## 2. `jibsa` 명령 설치

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

**아직 릴리스하지 않은 최신 수정을 받으려면** PyPI 대신 GitHub 주소로 설치한다: `uv tool install git+https://github.com/Rukkakka/jibsa` (pipx·pip 도 같은 주소). 이렇게 설치하면 `upgrade` 할 때 `main` 의 최신 커밋을 받고, `jibsa --version` 이 설치한 커밋을 함께 보여 준다. 버전마다 바뀐 점은 [변경 기록](../CHANGELOG.md)에 있다.

## 3. 설치 확인

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

Windows 는 UTF-8 출력 설정(`setx PYTHONUTF8 1`)을 처음 한 번 챙긴다 ([README 의 Windows 에서 쓸 때](../README.md#windows-에서-쓸-때)). macOS·Linux 는 따로 할 것이 없다.

## 4. 업데이트 · 삭제

| 설치 방법 | 업데이트 | 삭제 |
|---|---|---|
| uv | `uv tool upgrade jibsa` | `uv tool uninstall jibsa` |
| pipx | `pipx upgrade jibsa` | `pipx uninstall jibsa` |
| pip (macOS·Linux) | `~/.venvs/jibsa/bin/pip install -U jibsa` | `rm -rf ~/.venvs/jibsa ~/.local/bin/jibsa` |
| pip (Windows) | `& "$HOME\.venvs\jibsa\Scripts\pip.exe" install -U jibsa` | `Remove-Item -Recurse -Force $HOME\.venvs\jibsa` |

GitHub 주소로 설치했다면 uv·pipx 의 `upgrade` 는 그 주소에서 그대로 받고, pip 은 `pip install -U --force-reinstall git+https://github.com/Rukkakka/jibsa` 로 받는다.

요청 제한 상태 파일과 매물 검색 이어 받기 표(`next`)는 삭제해도 남으니 완전히 지우려면 그 디렉터리도 삭제한다. `JIBSA_STATE_DIR` 로 위치를 바꿨다면 그 디렉터리다 ([설정](../README.md#설정)).

| 운영체제 | 상태 파일 위치 | 삭제 |
|---|---|---|
| macOS·Linux | `~/.cache/jibsa` (`XDG_CACHE_HOME` 을 설정했으면 `$XDG_CACHE_HOME/jibsa`) | `rm -rf ~/.cache/jibsa` |
| Windows | `C:\Users\<이름>\.cache\jibsa` | `Remove-Item -Recurse -Force $HOME\.cache\jibsa` |
