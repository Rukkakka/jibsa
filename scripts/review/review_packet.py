"""`/review-diff` 리뷰어에게 넘길 리뷰 묶음 파일 하나를 만든다.

리뷰어가 "바뀐 줄을 감싼 함수 열기", "그 함수를 부르는 곳 찾기" 를 도구 호출로 하나씩 하지 않도록, 스크립트가 미리 해서 파일 하나로 모은다.
묶음은 세 섹션이다.

- ① 바뀐 내용: `.py` 는 감싼 함수를 붙인 `git diff -W`, 나머지는 그냥 diff. 150,000자를 넘으면 `.py` 도 `-W` 없이 다시 만든다
- ② 추적 안 된 파일 (작업 트리를 볼 때만): 경로와 내용 (파일마다 20,000자까지, 넘으면 앞부분만 넣고 나머지는 리뷰어가 파일에서 연다)
- ③ 바뀌거나 지운 이름(함수·클래스·최상위 상수)을 부르는 곳

    python scripts/review/review_packet.py --out packet.md                      # 이 브랜치 커밋 + 커밋 전 변경
    python scripts/review/review_packet.py --out packet.md --head my-branch     # 로컬 브랜치
    python scripts/review/review_packet.py --out packet.md --base abc~1 --head abc  # 지난 커밋 하나
"""

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_BRANCH = 'main'
# ① 의 글자 수가 이 값을 넘으면 감싼 함수 없이 그냥 diff 로 다시 만든다
DIFF_CHAR_LIMIT = 150_000
# 추적 안 된 파일 하나에 넣는 글자 수. 넘으면 앞부분만 넣고 나머지는 리뷰어가 파일에서 연다
UNTRACKED_FILE_CHAR_LIMIT = 20_000
# 이름마다 보여 주는 부르는 곳 수
MAX_CALLERS = 15
HUNK_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


class GitError(Exception):
    pass


def git(*args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    """git 을 저장소 루트에서 부른다. 실패하면 GitError."""
    proc = subprocess.run(
        ['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    if proc.returncode not in ok_codes:
        raise GitError(proc.stderr.strip() or f'git {" ".join(args)} 실패 (exit {proc.returncode})')
    return proc.stdout


def diff_args(base: str, head: str | None) -> list[str]:
    """비교 대상 리비전 인자. head 가 없으면 base 와 작업 트리를 비교한다."""
    return [base, head] if head else [base]


def read_side(rev: str | None, path: str) -> str | None:
    """그 쪽 파일 내용. rev 가 None 이면 디스크(작업 트리). 파일이 없으면 None."""
    if rev is None:
        file = ROOT / path
        return file.read_text(encoding='utf-8', errors='replace') if file.is_file() else None
    try:
        return git('show', f'{rev}:{path}')
    except GitError:
        return None


def parse_hunks(diff_text: str) -> dict[str, tuple[list[int], list[int]]]:
    """`git diff -U0` 출력에서 파일마다 (base 쪽 바뀐 줄, head 쪽 바뀐 줄) 을 구한다."""
    result: dict[str, tuple[list[int], list[int]]] = {}
    current: tuple[list[int], list[int]] | None = None
    for line in diff_text.splitlines():
        if line.startswith('diff --git '):
            path = line.rsplit(' b/', 1)[-1]
            current = result.setdefault(path, ([], []))
            continue
        match = HUNK_RE.match(line)
        if match and current is not None:
            old_start, old_len, new_start, new_len = match.groups()
            old_count = 1 if old_len is None else int(old_len)
            new_count = 1 if new_len is None else int(new_len)
            current[0].extend(range(int(old_start), int(old_start) + old_count))
            current[1].extend(range(int(new_start), int(new_start) + new_count))
    return result


def definitions(tree: ast.Module) -> dict[str, int]:
    """파일 안 함수·클래스·최상위 상수의 이름 → 정의 줄."""
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.setdefault(node.name, node.lineno)
    for stmt in tree.body:
        for name in assigned_names(stmt):
            found.setdefault(name, stmt.lineno)
    return found


def assigned_names(stmt: ast.stmt) -> list[str]:
    if isinstance(stmt, ast.Assign):
        return [t.id for t in stmt.targets if isinstance(t, ast.Name)]
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return [stmt.target.id]
    return []


def covers(node: ast.AST, line: int) -> bool:
    start = getattr(node, 'lineno', None)
    end = getattr(node, 'end_lineno', None)
    return start is not None and end is not None and start <= line <= end


def name_at(tree: ast.Module, line: int) -> str | None:
    """줄을 감싼 가장 안쪽 함수 → 클래스 → 최상위 대입 대상 이름. 없으면 None."""
    for kinds in ((ast.FunctionDef, ast.AsyncFunctionDef), (ast.ClassDef,)):
        best: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and isinstance(node, kinds) and covers(node, line):
                # 안쪽일수록 시작 줄이 크다
                if best is None or node.lineno >= best.lineno:
                    best = node
        if best is not None:
            return best.name
    for stmt in tree.body:
        if covers(stmt, line):
            names = assigned_names(stmt)
            if names:
                return names[0]
    return None


def is_dunder(name: str) -> bool:
    return name.startswith('__') and name.endswith('__')


def collect_names(
    base: str, head: str | None
) -> tuple[dict[str, dict[str, tuple[str, str]]], list[str]]:
    """바뀐·지운 이름 → {정의 파일: (상태, 정의 위치)}. 파싱 실패한 파일 경로 목록도 돌려준다.

    같은 이름이 여러 파일에서 바뀌거나 지워지면 파일마다 따로 둔다 (한 파일의 지움이 다른 파일의 바뀜에 가려지지 않게).
    """
    hunks = parse_hunks(git('diff', '-U0', '--no-renames', *diff_args(base, head), '--', '*.py'))
    names: dict[str, dict[str, tuple[str, str]]] = {}
    failed: list[str] = []
    for path, (old_lines, new_lines) in hunks.items():
        base_src = read_side(base, path)
        head_src = read_side(head, path)
        try:
            base_tree = ast.parse(base_src) if base_src is not None else None
            head_tree = ast.parse(head_src) if head_src is not None else None
        except (SyntaxError, ValueError):
            failed.append(path)
            continue
        head_defs = definitions(head_tree) if head_tree else {}
        base_defs = definitions(base_tree) if base_tree else {}
        picks: list[str] = []
        if head_tree:
            picks += [n for line in new_lines if (n := name_at(head_tree, line))]
        if base_tree:
            picks += [n for line in old_lines if (n := name_at(base_tree, line))]
        for name in picks:
            if is_dunder(name):
                continue
            if name in head_defs:
                state, where = '바뀜', f'{path}:{head_defs[name]}'
            else:
                state, where = '지움', f'{path}:{base_defs.get(name, 0)}'
            places = names.setdefault(name, {})
            if path not in places or (places[path][0] == '지움' and state == '바뀜'):
                places[path] = (state, where)
    return names, failed


_bound_names: dict[str, set[str] | None] = {}


def bound_names(path: str, head: str | None) -> set[str] | None:
    """`.py` 파일이 스스로 정의하거나 묶는 이름 (어디서든 함수·클래스, 최상위 대입, 함수 인자). 파싱 못 하면 None."""
    if path not in _bound_names:
        source = read_side(head, path)
        found: set[str] | None = None
        if source is not None:
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                tree = None
            if tree is not None:
                found = set(definitions(tree)) | {node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)}
        _bound_names[path] = found
    return _bound_names[path]


_code_names: dict[str, dict[str, set[int]] | None] = {}


def code_name_lines(path: str, head: str | None) -> dict[str, set[int]] | None:
    """`.py` 파일에서 이름 → 그 이름이 코드(주석·문자열 밖)로 나오는 줄. 토큰으로 못 나누면 None."""
    if path not in _code_names:
        source = read_side(head, path)
        lines: dict[str, set[int]] | None = None
        if source is not None:
            try:
                lines = {}
                for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                    if tok.type == tokenize.NAME:
                        lines.setdefault(tok.string, set()).add(tok.start[0])
            except (tokenize.TokenError, SyntaxError):
                lines = None
        _code_names[path] = lines
    return _code_names[path]


def callers(name: str, head: str | None, def_paths: set[str]) -> list[str]:
    """이름을 부르는 곳 (`경로:줄: 그 줄`). 이름의 정의 줄과, 주석·docstring 에서 이름만 말한 줄은 뺀다.

    바뀐 정의가 없는 파일이 같은 이름을 스스로 정의하거나 인자로 받으면 그 파일의 줄은 그 이름을 쓰는 것이라 뺀다
    (테스트 도우미 `_trade`, 인자 `keep` 같은 이름만 같은 것).
    """
    if head is None:
        out = git('grep', '-n', '-I', '-w', '--untracked', name, '--', 'src', 'tests', 'scripts', ok_codes=(0, 1))
    else:
        out = git('grep', '-n', '-I', '-w', name, head, '--', 'src', 'tests', 'scripts', ok_codes=(0, 1))
    starts = re.compile(
        rf'^\s*(?:(?:async\s+)?def\s+{re.escape(name)}\b|class\s+{re.escape(name)}\b|{re.escape(name)}\s*(?::|=(?!=)))'
    )
    found: list[str] = []
    for raw in out.splitlines():
        if head is not None and raw.startswith(f'{head}:'):
            raw = raw[len(head) + 1 :]
        parts = raw.split(':', 2)
        if len(parts) < 3 or starts.match(parts[2]):
            continue
        if parts[0].endswith('.py'):
            if parts[0] not in def_paths and name in (bound_names(parts[0], head) or set()):
                continue
            code_lines = code_name_lines(parts[0], head)
            if code_lines is not None and int(parts[1]) not in code_lines.get(name, set()):
                continue
        found.append(f'{parts[0]}:{parts[1]}: {parts[2]}')
    return found


def untracked_section(out_path: Path) -> str:
    """추적 안 된 파일의 경로와 내용 (파일마다 `UNTRACKED_FILE_CHAR_LIMIT` 자까지)."""
    lines: list[str] = []
    for path in git('ls-files', '--others', '--exclude-standard').splitlines():
        file = ROOT / path
        if file.resolve() == out_path:
            continue
        lines.append(f'#### {path}')
        try:
            data = file.read_bytes()
            if b'\0' in data:
                raise UnicodeDecodeError('utf-8', b'', 0, 1, 'NUL')
            content = data.decode('utf-8').rstrip('\n')
            lines += ['```', content[:UNTRACKED_FILE_CHAR_LIMIT], '```']
            if len(content) > UNTRACKED_FILE_CHAR_LIMIT:
                lines.append(f'(이하 {len(content) - UNTRACKED_FILE_CHAR_LIMIT:,}자 생략. 파일에서 연다)')
        except (UnicodeDecodeError, OSError):
            lines.append('(바이너리, 내용 생략)')
    return '\n'.join(lines) if lines else '(없음)'


def build_diff(base: str, head: str | None, wrap: bool) -> str:
    revs = diff_args(base, head)
    py = git('diff', *(['-W'] if wrap else []), *revs, '--', '*.py')
    other = git('diff', *revs, '--', '.', ':(exclude)*.py')
    return f'#### .py\n{py or "(변경 없음)"}\n\n#### 그 밖의 파일\n{other or "(변경 없음)"}'


def callers_section(base: str, head: str | None) -> tuple[str, int]:
    names, failed = collect_names(base, head)
    blocks: list[str] = []
    for name, places in sorted(names.items()):
        found = callers(name, head, set(places))
        blocks.append(f'### {name} — ' + ', '.join(f'{state} {where}' for state, where in places.values()))
        if len(places) > 1:
            blocks.append('(같은 이름이 여러 파일에서 바뀌었다. 아래 부르는 곳은 이름으로 찾아 섞여 있으니 그 파일의 import 로 어느 정의인지 가른다)')
        blocks += found[:MAX_CALLERS]
        if len(found) > MAX_CALLERS:
            blocks.append(f'… {len(found) - MAX_CALLERS}곳 더')
        if not found:
            blocks.append('(부르는 곳 없음)')
    blocks += [f'### {path} — 파싱 실패' for path in failed]
    return ('\n'.join(blocks) if blocks else '(없음)'), len(names)


def main() -> int:
    parser = argparse.ArgumentParser(description='리뷰어에게 넘길 리뷰 묶음 파일을 만든다.')
    parser.add_argument('--out', required=True, help='묶음 파일을 쓸 경로')
    parser.add_argument('--head', help='리뷰할 끝 리비전 (없으면 작업 트리)')
    parser.add_argument('--base', help=f'시작 리비전 (없으면 {MAIN_BRANCH} 와의 merge-base)')
    args = parser.parse_args()
    out_path = Path(args.out).resolve()
    head: str | None = args.head
    try:
        base = args.base or git('merge-base', MAIN_BRANCH, head or 'HEAD').strip()
        diff = build_diff(base, head, wrap=True)
        wrapped = True
        if len(diff) > DIFF_CHAR_LIMIT:
            diff = build_diff(base, head, wrap=False)
            wrapped = False
        untracked = untracked_section(out_path) if head is None else None
        call_text, name_count = callers_section(base, head)
    except GitError as error:
        print(error, file=sys.stderr)
        return 1

    target = f'{head} (커밋)' if head else '작업 트리 (커밋 전 변경과 추적 안 된 파일 포함)'
    note = (
        '감싼 함수를 함께 붙인 diff, `git diff -W`'
        if wrapped
        else f'한도({DIFF_CHAR_LIMIT:,}자)를 넘어 감싼 함수 없이 그냥 diff'
    )
    parts = [
        f'# 리뷰 묶음\n\n비교: `{base}` → {target}\n\n'
        '리뷰어가 도구로 하나씩 열 일을 미리 모았다. 아래 세 섹션을 먼저 읽고, 모자란 곳만 직접 연다.',
        f'## ① 바뀐 내용\n\n({note})\n\n{diff}',
    ]
    if untracked is not None:
        parts.append(f'## ② 추적 안 된 파일\n\n{untracked}')
    else:
        parts.append('## ② 추적 안 된 파일\n\n(리비전을 보므로 해당 없음)')
    parts.append(f'## ③ 바뀌거나 지운 이름을 부르는 곳\n\n{call_text}')
    text = '\n\n'.join(parts) + '\n'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding='utf-8')
    print(f'{out_path} 글자 {len(text)} 이름 {name_count} ①{"함수 포함" if wrapped else "한도 넘어 그냥 diff"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
