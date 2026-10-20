"""README 맨 위 로고(docs/logo.svg)를 만든다.

글자는 외곽선(path)으로 바꿔 넣는다. SVG 안에 글자로 두면 보는 사람 컴퓨터에 그 글꼴이 없을 때 다른 글꼴로 바뀐다.
바탕을 색으로 채워서 GitHub 밝은 화면·어두운 화면과 PyPI 에서 파일 하나로 같게 보인다 (PyPI 는 밝은·어두운 판을
고르는 `<source>` 태그를 걸러 낸다). 배치와 글꼴은 뱅기표(baenggipyo) 로고와 같게 맞췄다.

글꼴은 저장소에 두지 않는다. Google Fonts 의 IBM Plex Mono SemiBold 와 IBM Plex Sans KR SemiBold(둘 다 OFL)를 받아
경로를 넘긴다.

    uv run --no-project --with fonttools python scripts/logo/build_logo.py IBMPlexMono-SemiBold.ttf IBMPlexSansKR-SemiBold.ttf
"""

import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


OUTPUT: Path = Path(__file__).resolve().parents[2] / 'docs' / 'logo.svg'
TAG_COLOR: str = '#1D7F63'
INK: str = '#FFFFFF'
# 열쇠 이름표 윤곽 (320×120): 왼쪽 모서리를 깎은 표와 고리 구멍(evenodd). 같은 색 굵은 테두리(round)로 모서리를 둥글린다
TAG: str = 'M50 10H296A14 14 0 0 1 310 24V96A14 14 0 0 1 296 110H50L16 80V40ZM29 60A11 11 0 1 0 51 60A11 11 0 1 0 29 60Z'
# 나비넥타이 맨 집 (24×24, 중심 12,12). 문과 나비넥타이는 evenodd 로 뚫린 구멍이라 표 색이 비친다
HOUSE: str = 'M12 3L22 11.5H19V21H14V15H10V21H5V11.5H2ZM8.6 10.4L11 11.6V12.4L8.6 13.6ZM15.4 10.4L13 11.6V12.4L15.4 13.6ZM11.4 11.3H12.6V12.7H11.4Z'


def _number(value: float) -> str:
    """좌표를 소수 둘째 자리까지, 끝의 0 은 떼고 쓴다."""
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def text_path(font: TTFont, text: str, x: float, baseline: float, size: float, spacing: float = 0) -> str:
    """글자열 하나를 SVG path 의 d 값으로 바꾼다.

    Args:
        font: 글꼴.
        text: 쓸 글자열.
        x: 첫 글자의 왼쪽 x.
        baseline: 기준선 y.
        size: 글자 크기(px).
        spacing: SVG letter-spacing 처럼 글자마다 뒤에 더하는 간격(px). Defaults to 0.

    Returns:
        모든 글자의 외곽선을 이은 d 값.
    """
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font['head'].unitsPerEm
    pen = SVGPathPen(glyph_set, ntos=_number)
    for char in text:
        glyph = glyph_set[cmap[ord(char)]]
        # 글꼴 좌표는 y 가 위로 커지고 SVG 는 아래로 커진다
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += glyph.width * scale + spacing
    return pen.getCommands()


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('사용법: build_logo.py <IBMPlexMono-SemiBold.ttf> <IBMPlexSansKR-SemiBold.ttf>')
    mono, sans = (TTFont(path) for path in sys.argv[1:])
    # 배치는 로고를 고를 때 본 미리보기와 같다
    name = text_path(mono, 'jibsa', x=70, baseline=66, size=42)
    korean = text_path(sans, '집사', x=72, baseline=93, size=13, spacing=1.2)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120" role="img" aria-label="jibsa (집사)">
  <title>jibsa (집사)</title>
  <path d="{TAG}" fill="{TAG_COLOR}" fill-rule="evenodd" stroke="{TAG_COLOR}" stroke-width="8" stroke-linejoin="round"/>
  <path d="{name}" fill="{INK}"/>
  <path d="{korean}" fill="{INK}" fill-opacity=".8"/>
  <path d="{HOUSE}" fill="{INK}" fill-rule="evenodd" transform="translate(262 58) scale(2.3) translate(-12 -12)"/>
</svg>
"""
    OUTPUT.write_text(svg, encoding='utf-8')
    print(f'{OUTPUT} ({len(svg.encode())} bytes)')


if __name__ == '__main__':
    main()
