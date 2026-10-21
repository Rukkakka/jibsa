"""여러 소스 CLI 가 똑같이 쓰는 옵션 별칭. 도움말까지 같은 것만 둔다 (다르면 각 소스 CLI 에 둔다)."""

import typer

from jibsa.cli.output import check_fields

from typing import Annotated


PrettyOption = Annotated[
    bool | None,
    typer.Option('--pretty/--compact', help='JSON 들여쓰기. 기본값은 터미널이면 pretty, 파이프면 compact'),
]
FieldsOption = Annotated[
    list[str] | None,
    typer.Option(
        '--fields',
        callback=check_fields,
        help=(
            '매물마다 낼 필드만 고른다 (출력이 준다). 결과의 매물 키 이름을 반복하거나 쉼표로 구분 '
            '(예: id,trade_type,deposit_manwon,rent_manwon,area_m2,floor,address). id 와 당근 in_regions 는 늘 나온다. 기본 전체'
        ),
    ),
]
DepositMinOption = Annotated[int | None, typer.Option(min=0, help='보증금/전세금 하한 (만원)')]
DepositMaxOption = Annotated[int | None, typer.Option(min=0, help='보증금/전세금 상한 (만원)')]
RentMinOption = Annotated[int | None, typer.Option(min=0, help='월세 하한 (만원)')]
RentMaxOption = Annotated[int | None, typer.Option(min=0, help='월세 상한 (만원)')]
PriceMinOption = Annotated[int | None, typer.Option(min=0, help='매매가 하한 (만원)')]
PriceMaxOption = Annotated[int | None, typer.Option(min=0, help='매매가 상한 (만원)')]
