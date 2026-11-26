"""매물 상세의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import Field

from jibsa.core.listing import (
    ListingDetail,
)

from typing import Annotated


class DaangnListingDetail(ListingDetail):
    """상세 페이지로 보강한 당근 매물.

    `key_money_manwon`·`key_money_negotiable` 은 상가에만, `broker_fee_manwon` 은 중개사 매물에만 있다
    (그 밖에는 키를 뺀다). 권리금 설명 글(`premiumMoneyDescription`)은 작성자가 쓴 자유 글이라 옮기지 않는다.

    `notes`: --trade 조건이 없어 대표 조건을 보여 준다는 안내. CLI 가 결과 위에 붙인다
    """

    other_trades: Annotated[
        list[str],
        Field(description='보여 주는 조건 외에 함께 올라온 거래 조건 (만원, 예: 전세 20000, 월세 1000/50, 연세는 보증금/1년치 1000/1400)')
    ] = []
    manage_cost_excludes: Annotated[
        list[str] | None,
        Field(description='관리비와 따로 내는 항목 (쓴 만큼 내는 전기·수도 등). 소스가 알려 주지 않으면 null. 당근이 빈 항목을 줘 셀 수 없어도 null')
    ] = None
    key_money_manwon: Annotated[
        float | None,
        Field(description='권리금 (만원, 상가만)')
    ] = None
    key_money_negotiable: Annotated[
        bool | None,
        Field(description='권리금 협의 가능 여부 (상가만). true 면 권리금 금액은 참고용이다')
    ] = None
    broker_fee_manwon: Annotated[
        float | None,
        Field(description='보여 주는 거래 조건의 중개보수 (만원, 부가세 포함). 당근이 법정 상한 요율로 계산한 값이다')
    ] = None
    favorite_count: Annotated[
        int | None,
        Field(description='당근에서 이 매물을 관심 목록에 넣은 사람 수')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (daangn complex 에 넘긴다). 아파트·오피스텔 등 단지 매물만')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='단지 종류 (아파트, 오피스텔, 주상복합 ...). property_type 은 작성자가 고른 매물 종류라 다를 수 있다')
    ] = None
    direct_deal: Annotated[
        bool,
        Field(exclude=True, description='직거래 매물인지. 중개보수가 해당 없는지 가리는 데만 쓴다')
    ] = False

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.property_type is not None and self.property_type != '상가' and self.key_money_manwon is None:
            fields = fields | {'key_money_manwon', 'key_money_negotiable'}
        if self.direct_deal:
            fields = fields | {'broker_fee_manwon'}
        if self.complex_id is None:
            fields = fields | {'complex_id', 'complex_name', 'complex_type'}
        return fields
