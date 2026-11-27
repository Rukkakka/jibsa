"""`detail.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    Field,
)

from jibsa.core.listing import (
    ListingDetail,
)
from jibsa.providers.dabang.service.common.constants import OFFICETEL_TYPE
from jibsa.providers.dabang.service.common.models import (
    DabangListing,
    is_complex_type,
)

from typing import (
    Annotated,
)


class DabangDetailedListing(DabangListing):
    """`--details` 로 매물 상세를 1회 더 받아 사용승인일(`approved_date`)을 채우고 건물 용도를 붙인 목록 매물."""

    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (단독주택, 공동주택, 근린생활시설 ...). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다. 모르면 null')
    ] = None


class DabangListingDetail(ListingDetail):
    """다방 매물 상세. 단기임대는 월세 매물에 붙는 표시라 `short_term_period` 로 받는 기간을 알린다.

    `notes`: 빈 항목 안내
    """

    listing_number: Annotated[
        int | None,
        Field(description='다방 화면의 매물번호')
    ] = None
    manage_cost_charge_type: Annotated[
        str | None,
        Field(description="관리비 부과 방식 (다방 표시 '정액관리비'·'기타부과'·'확인불가'). 모르면 null")
    ] = None
    manage_cost_excludes: Annotated[
        list[str] | None,
        Field(description="관리비에 들지 않고 실비로 따로 내는 항목 (다방 상세보기의 '실비', 예 ['전기', '수도']). 정액관리비를 항목마다 적은 매물만 알고 그 밖은 null")
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡, 공급 + 주차장 등 기타 공용. 다방이 오피스텔에 주는 값). 오피스텔에만 키가 있고 모르면 null')
    ] = None
    with_tenant: Annotated[
        bool,
        Field(description='세입자를 끼고 파는 매매 (다방 기 보증금/월세 표시). 매매만')
    ] = False
    tenant_deposit_manwon: Annotated[
        float | None,
        Field(description='세입자 낀 매매의 기존 보증금·전세금 (만원). with_tenant 가 true 일 때만 키가 있고 읽지 못하면 null')
    ] = None
    tenant_rent_manwon: Annotated[
        float | None,
        Field(description='세입자 낀 매매의 기존 월세 (만원). 기존 세입자가 월세일 때만 키가 있다')
    ] = None
    lh_jeonse: Annotated[
        bool,
        Field(description='LH 전세임대 가능 (다방 표시). 매매는 키가 없다')
    ] = False
    leasehold_registration: Annotated[
        bool,
        Field(description='임차권 등기명령 매물 (다방 경고: 기존 임차인의 권리가 우선 적용되니 확인 후 거래)')
    ] = False
    unregistered_building: Annotated[
        bool,
        Field(description="미등기 건물 (다방 '미등기건물' 표시)")
    ] = False
    non_compliant_building: Annotated[
        bool | None,
        Field(description="위반건축물 여부 (다방 '해당'·'해당없음'). 다방이 알려 주지 않으면 null")
    ] = None
    short_term_period: Annotated[
        str | None,
        Field(description="단기임대를 받는 기간 (예 '1개월(이상 협의가능)'). 단기임대를 받지 않는 매물은 키가 없다")
    ] = None
    direction_criterion: Annotated[
        str | None,
        Field(description='방향 기준 (안방·거실)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 (개별난방 등)')
    ] = None
    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (단독주택, 공동주택, 근린생활시설 ...). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다')
    ] = None
    loan: Annotated[
        str | None,
        Field(description="융자 (예 '시세대비 30%미만'). 모르면 null")
    ] = None
    safety: Annotated[
        list[str] | None,
        Field(description='보안 시설 (CCTV, 현관보안 ...)')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (오피스텔·아파트). dabang complex·search listings --complex 에 넘긴다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.trade_type != '월세' or self.short_term_period is None:
            fields = fields | {'short_term_period'}
        # 상세 유형은 '오피스텔(분리형)'·'원룸(분리형,복층)' 처럼 구조를 붙여 온다 (2026-10-25 실측). 다방이 단지 ID 를 주면
        # 유형과 상관없이 두고, 없을 때만 유형으로 해당 없음(키 삭제)과 모름(null)을 가른다
        if self.complex_id is None and not is_complex_type(self.property_type):
            fields = fields | {'complex_id'}
        # 다방은 계약면적을 오피스텔에만 주고 다른 유형은 0 으로 준다 (2026-11-13 실측: 상세 46건 중 오피스텔 5건만 값이 있다).
        # 오피스텔인데 값이 없으면 해당 없음이 아니라 모름(null)이라 키를 둔다 (공급면적과 같다)
        if self.contract_area_m2 is None and (self.property_type is None or not self.property_type.startswith(OFFICETEL_TYPE)):
            fields = fields | {'contract_area_m2'}
        # 세입자 낀 매물·LH 전세임대는 웹이 거래 유형과 상관없이 표시만 보고 보여 준다. 해당 없는 거래는 키를 빼되 다방이
        # 표시를 붙였으면 웹처럼 둔다
        if self.trade_type != '매매' and not self.with_tenant:
            fields = fields | {'with_tenant'}
        if not self.with_tenant:
            fields = fields | {'tenant_deposit_manwon', 'tenant_rent_manwon'}
        elif self.tenant_deposit_manwon is not None and self.tenant_rent_manwon is None:
            # 기존 세입자가 전세라 월세가 없다 ('20억')
            fields = fields | {'tenant_rent_manwon'}
        if self.trade_type == '매매' and not self.lh_jeonse:
            fields = fields | {'lh_jeonse'}
        return fields
