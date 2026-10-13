"""Claude 데모 GIF 에서 Claude Code 배너의 요금제 글자(`· Claude Pro`)를 배경색으로 덮는다.

Claude Code 배너는 모델 옆에 요금제를 늘 보여 주고 끄는 설정이 없다. `claude.tape` 로 녹화한 뒤
`python3 docs/demo/hide_plan.py docs/demo/claude.gif` 로 덮는다. ffmpeg 가 필요하다.

배너는 답이 화면을 채우는 순간 한 번에 사라지므로 로고(분홍)가 제자리에 보이는 장면만 덮는다.
글자 자리는 1200x880·D2Coding 17 에서 'Opus 5.5 with medium effort · Claude Pro' 를 잰 값이다. 모델·생각 깊이
글자가 바뀌면 PLAN_BOX 의 x 를 다시 잰다.
"""

import json
import subprocess
import sys
from pathlib import Path


# 덮을 칸 (x, y, 너비, 높이): '· Claude Pro' 는 x 387~492, y 62~74
PLAN_BOX: tuple[int, int, int, int] = (380, 58, 125, 22)
# 로고를 찾을 칸 (x, y, 너비, 높이)과 배경색 (Catppuccin Mocha)
LOGO_BOX: tuple[int, int, int, int] = (28, 42, 80, 46)
BACKGROUND: str = '0x1d1d2d'


def frame_times(gif: Path) -> list[float]:
    """GIF 장면마다의 시작 시각(초)."""
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'frame=best_effort_timestamp_time',
         '-of', 'json', str(gif)],
        check=True, capture_output=True, text=True,
    ).stdout
    return [float(frame['best_effort_timestamp_time']) for frame in json.loads(out)['frames']]


def logo_frames(gif: Path) -> list[bool]:
    """장면마다 로고가 제자리에 보이는지 (분홍 픽셀이 있는지)."""
    x, y, width, height = LOGO_BOX
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', str(gif), '-fps_mode', 'passthrough', '-vf', f'crop={width}:{height}:{x}:{y}',
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        check=True, capture_output=True,
    ).stdout
    size = width * height * 3
    shown = []
    for start in range(0, len(raw), size):
        frame = raw[start:start + size]
        shown.append(any(
            frame[i] > 180 and frame[i + 1] < 150 and frame[i + 2] < 150 for i in range(0, len(frame), 3)
        ))
    return shown


def intervals(times: list[float], shown: list[bool]) -> list[tuple[float, float]]:
    """로고가 보이는 장면들을 (시작, 다음 장면 시작) 구간으로 묶는다."""
    spans: list[tuple[float, float]] = []
    start: float | None = None
    for index, visible in enumerate(shown):
        if visible and start is None:
            start = times[index]
        if not visible and start is not None:
            spans.append((start, times[index]))
            start = None
    if start is not None:
        spans.append((start, times[-1] + 1))
    return spans


def main() -> None:
    gif = Path(sys.argv[1])
    times, shown = frame_times(gif), logo_frames(gif)
    if len(times) != len(shown):
        sys.exit(f'장면 수가 맞지 않습니다: 시각 {len(times)}개, 장면 {len(shown)}개')
    spans = intervals(times, shown)
    if not spans:
        sys.exit('배너 로고가 보이는 장면이 없습니다')
    # 경계 장면을 확실히 덮도록 끝을 아주 조금 앞당긴다 (다음 장면 시작 직전까지)
    enable = '+'.join(f'between(t,{start:.3f},{end - 0.001:.3f})' for start, end in spans)
    x, y, width, height = PLAN_BOX
    covered = f"drawbox=x={x}:y={y}:w={width}:h={height}:color={BACKGROUND}:t=fill:enable='{enable}'"
    output = gif.with_suffix('.tmp.gif')
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-i', str(gif), '-fps_mode', 'passthrough', '-filter_complex',
         f'[0]{covered},split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none',
         str(output)],
        check=True,
    )
    output.replace(gif)
    print(f'{gif}: {len(spans)}개 구간에서 요금제 글자를 덮었습니다 ' + ', '.join(f'{s:.1f}~{e:.1f}s' for s, e in spans))


if __name__ == '__main__':
    main()
