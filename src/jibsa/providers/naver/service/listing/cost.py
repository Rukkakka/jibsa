"""매물 상세의 비용 (관리비·중개보수·세금)."""

from jibsa.core.listing import (
    null_items_note,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.listing.detail import (
    NaverArticleAgentFeeV1RequestParameterModel,
    NaverArticleTaxV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.listing.detail import (
    NaverArticleMaintenanceFeeModel,
)
from jibsa.providers.naver.service.common.labels import unknown_code_label
from jibsa.providers.naver.service.common.response import result_or_none
from jibsa.providers.naver.service.listing.constants import (
    ALL_TAX_TYPES,
    MANAGE_COST_ITEM_LABELS,
    MANAGE_COST_NONE_REASON,
    SALE_TAX_FIELDS,
)

from typing import Any


def _sum_manwon(*amounts: int | None) -> float | None:
    """원 단위 금액들의 합을 만원으로. 모두 모르면 None.

    아는 항목만 더한다. 네이버 세금 응답은 면제 항목도 null 이 아니라 0 으로 줘서 일부만 null 인 응답은 없다
    (헬리오시티 39~150㎡·일신동 빌라 6건, 2026-10-11). 일부만 null 이 오면 응답 형식이 바뀐 것이다.
    """
    known = [amount for amount in amounts if amount is not None]
    return won_to_manwon(sum(known)) if known else None


def agent_fee(client: NaverClient, article_number: str, notes: list[str]) -> dict[str, Any]:
    """중개보수 상한(`broker_fee_manwon`, 만원)과 '개별확인' 여부 (1회 호출). 직거래가 아니면 모든 거래 유형에서 조회한다 (웹도 월세 매물에 '최대 28만원' 을 보여 준다).

    네이버 웹은 `isIndividualCheckRequired` 가 참이면 금액 대신 '개별확인' 을 그리므로 금액은 None 이고 여부가 True 다.
    플래그가 없거나 거짓이면 웹도 금액을 그린다. 조회가 실패하면 둘 다 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다.
    금액(fee)이 비어 오고 플래그가 참이 아니면 broker_fee_manwon 만 None 이고 여부는 False 다. 웹(ArticleRealtorFee)도
    그때 '개별확인' 이 아니라 금액 줄을 그린다 (리뷰 오탐, 2026-11-17).
    """
    fee = result_or_none(
        lambda: client.run_request_article_agent_fee_v1(
            NaverArticleAgentFeeV1RequestParameterModel(article_number=article_number)
        ),
        notes=notes,
        what='중개보수',
        unknown='모름(null)으로 낸 칸: broker_fee_manwon, broker_fee_individual_check_required',
    )
    if fee is None:
        return {'broker_fee_manwon': None, 'broker_fee_individual_check_required': None}
    individual = fee.is_individual_check_required is True
    return {
        'broker_fee_manwon': None if individual else won_to_manwon(fee.fee),
        'broker_fee_individual_check_required': individual,
    }


def sale_taxes(
    client: NaverClient,
    article_number: str,
    real_estate_type: str,
    notes: list[str],
) -> dict[str, float | None]:
    """매매 매물의 세금 (1회 호출). 조회가 실패하면 그 값만 모름(None)으로 두고 `notes` 에 `[실패]` 안내를 붙인다.

    안내에 적는 칸은 출력에 남는 칸이다. 세 세금을 모두 그리는 유형(`ALL_TAX_TYPES`) 밖은 취득세만 남고 나머지 둘은 키를 뺀다
    (`NaverListingDetail.not_applicable_fields`).
    """
    costs: dict[str, float | None] = dict.fromkeys(SALE_TAX_FIELDS)
    unknown = (
        '모름(null)으로 낸 칸: acquisition_tax_manwon, property_tax_manwon, comprehensive_real_estate_tax_manwon'
        if real_estate_type in ALL_TAX_TYPES else '모름(null)으로 낸 칸: acquisition_tax_manwon'
    )
    tax = result_or_none(
        lambda: client.run_request_article_tax_v1(
            NaverArticleTaxV1RequestParameterModel(article_number=article_number)
        ),
        notes=notes,
        what='세금',
        unknown=unknown,
    )
    if tax is not None:
        if tax.acquisition_tax is not None:
            acquisition = tax.acquisition_tax
            costs['acquisition_tax_manwon'] = _sum_manwon(
                acquisition.acquisition_tax, acquisition.local_tax, acquisition.rural_special_tax,
            )
        if tax.property_tax is not None:
            property_ = tax.property_tax
            costs['property_tax_manwon'] = _sum_manwon(
                property_.property_tax, property_.local_education_tax, property_.urban_area_segment_tax,
            )
        if tax.total_real_estate_tax is not None:
            total = tax.total_real_estate_tax
            costs['comprehensive_real_estate_tax_manwon'] = _sum_manwon(
                total.total_real_estate_tax, total.rural_special_tax,
            )
    return costs


def _manage_cost_item_label(code: str) -> str:
    """관리비 포함 항목 코드의 글자. 표에 없으면 '알 수 없는 항목 (코드)'."""
    return MANAGE_COST_ITEM_LABELS.get(code) or unknown_code_label('항목', code)


def manage_cost(fee: NaverArticleMaintenanceFeeModel | None, notes: list[str]) -> tuple[float | None, list[str] | None]:
    """월 관리비(만원)와 관리비에 포함된 항목. 모르면 None.

    합계형(typeCode '02')은 etcDetail, 정액 합계형('04')은 같은 모양의 fixNonDetailList 의 금액과 포함 항목(categoryList)을
    쓴다. 0 은 중개사가 0원으로 입력한 것이다. '04' 는 원룸·빌라·오피스텔 16건 중 7건일 만큼 흔하다 (신림동, 2026-10-11).
    항목별형('01')은 웹처럼(번들 getMaintenanceFeeLabel: `fixDetailList.reduce((s, e) => s + (e.amount ?? 0), 0)`, 2026-11-18)
    정액·실비를 가리지 않고 모든 항목의 금액을 더해 합계로 본다. 실비 항목은 쓴 만큼 따로 내서 지금까지 본 응답에서는 모두 금액이
    null 이라 합계가 정액 항목의 합과 같다 (원룸 2653883790: 공용 10만원 정액, 전기~TV 실비 → 합계 10만원, 2026-10-10).
    포함 항목은 정액 항목(unitType '01')만 친다. 그래서 실비 금액이 모두 null 이고 항목이 모두 실비면 0만원·[] 이다.
    정액으로 내는 관리비가 0원이고 공과금은 따로 낸다는 뜻이라 모름(None)이 아니다 (docs/naver.md 의 manage_cost_includes 설명과 같은 규칙).
    미확인('03')은 etcDetail·fixNonDetailList 가 null 이고 uncheckDetail 로 사유가 와서 대개 모름이다 (빌라 2654619539·
    2653716463, 2026-10-11). 다만 사유가 '99'(없음)이면 웹이 관리비 '없음' 으로 보여 주므로 0만원·[] 이다 (직방의 '관리비
    없음' 과 같은 꼴, 웹 번들 getMaintenanceFeeLabel 대조 2026-11-16). 다른 사유('01'~'04')는 웹도 '확인 어려움' 이라 모름이다.
    사유가 없으면 웹이 옛 형식 관리비로 넘어가(`has_fee_cell` 이 False) 호출부가 옛 형식 금액을 쓰고, 거기에도 금액이 없으면
    모름이다. 그래서 금액은 typeCode 를 따로 보지 않고 값이 온 키로 정한다. 세 키(etcDetail·fixNonDetailList·fixDetailList)
    중 하나만 오고 나머지는 null 이라(신림동 월세 29건: '04' 18·'02' 10·'01' 1, 2026-10-11) 객체가 있는지만 본다.
    금액 없는 빈 etcDetail 이 다른 키와 함께 오는 응답은 없었다.
    항목별형 목록에서 빈 항목(null)을 빼고 읽었으면 합계도 포함 항목도 모자랄 수 있어 둘 다 모름(None)이고 `notes` 에 `[제외]` 안내를 붙인다.
    """
    if fee is None:
        return None, None
    summary = fee.etc_detail or fee.fix_non_detail_list
    # 합계 객체는 금액이 수일 때만 쓴다. 금액이 없으면 웹도 이 값으로 칸을 그리지 않고 옛 형식 관리비로 넘어가므로(`has_fee_cell`)
    # 포함 항목만 내지 않는다 (2026-11-24 리뷰: 금액 null·항목 목록이 온 응답에서 항목만 나가고 [실패] 안내와 어긋났다)
    if summary is not None and summary.amount is not None:
        codes = summary.category_list
        includes = None if codes is None else [_manage_cost_item_label(code) for code in codes]
        return won_to_manwon(summary.amount), includes
    dropped = fee.null_items('fix_detail_list')
    if dropped:
        notes.append(null_items_note('네이버 관리비 항목', dropped, ('manage_cost_manwon', 'manage_cost_includes')))
        return None, None
    if fee.fix_detail_list:
        fixed = [item for item in fee.fix_detail_list if item.unit_type == '01' and item.amount is not None]
        includes = [_manage_cost_item_label(item.type) for item in fixed if item.amount and item.type]
        return won_to_manwon(sum(item.amount or 0 for item in fee.fix_detail_list)), includes
    if fee.type_code == '03' and fee.uncheck_detail is not None and fee.uncheck_detail.type == MANAGE_COST_NONE_REASON:
        return 0.0, []
    return None, None


def has_fee_cell(fee: NaverArticleMaintenanceFeeModel | None) -> bool:
    """웹이 maintenanceFee 만으로 '관리비' 칸을 그리는 응답인가 (`manage_cost` 의 갈래와 같다).

    미확인('03')이면서 사유(uncheckDetail.type)가 있으면 사유 글자, 항목별형은 fixDetailList(빈 항목을 뺐으면 그 자리)가 있으면 합계,
    합계형('02')·정액 합계형('04')은 금액이 수일 때다. 못 만들면 웹은 옛 형식 관리비(`oldMaintenanceFee`)로 넘어간다.
    """
    if fee is None:
        return False
    if fee.type_code == '03' and fee.uncheck_detail is not None and fee.uncheck_detail.type:
        return True
    summary = fee.etc_detail or fee.fix_non_detail_list
    if summary is not None and summary.amount is not None:
        return True
    return bool(fee.fix_detail_list) or bool(fee.null_items('fix_detail_list'))
