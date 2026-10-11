"""여러 소스 CLI 가 똑같이 쓰는 옵션 별칭. 도움말까지 같은 것만 둔다 (다르면 각 소스 CLI 에 둔다)."""

import typer

from typing import Annotated


PrettyOption = Annotated[
    bool | None,
    typer.Option('--pretty/--compact', help='JSON 들여쓰기. 기본값은 터미널이면 pretty, 파이프면 compact'),
]
DepositMinOption = Annotated[int | None, typer.Option(min=0, help='보증금/전세금 하한 (만원)')]
DepositMaxOption = Annotated[int | None, typer.Option(min=0, help='보증금/전세금 상한 (만원)')]
RentMinOption = Annotated[int | None, typer.Option(min=0, help='월세 하한 (만원)')]
RentMaxOption = Annotated[int | None, typer.Option(min=0, help='월세 상한 (만원)')]
PriceMinOption = Annotated[int | None, typer.Option(min=0, help='매매가 하한 (만원)')]
PriceMaxOption = Annotated[int | None, typer.Option(min=0, help='매매가 상한 (만원)')]
