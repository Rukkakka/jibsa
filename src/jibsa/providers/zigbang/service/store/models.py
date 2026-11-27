"""상가·사무실 매물 검색·상세의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Listing,
    ListingDetail,
    Result,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.store import ZigbangStoreSalesType
from jibsa.providers.zigbang.service.common.models import (
    ZigbangRegion,
    drop_unused_scope,
)
from jibsa.providers.zigbang.service.store.constants import (
    STORE_NOT_APPLICABLE_DETAIL_FIELDS,
    STORE_NOT_APPLICABLE_FIELDS,
    STORE_OFFICE_BUSINESS,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangStoreListing(Listing):
    """직방 상가·사무실 매물."""

    business: Annotated[
        str | None,
        Field(description='업종 (현재·직전 업종, 공실이면 기타)')
    ] = None
    key_money_manwon: Annotated[
        float | None,
        Field(description='권리금 (만원). 0 이면 무권리. 업종이 사무실이고 직방이 주지 않으면 키가 없다')
    ] = None
    vacant_section: Annotated[
        bool | None,
        Field(description="직방 '이 지역 비어있는 상가' 묶음에서 온 줄이면 true (업종과 상관없는 공실), 업종(또는 일반) 묶음이면 false. 공실 묶음이 해당 없으면 키가 없다")
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = (
            super().not_applicable_fields()
            | STORE_NOT_APPLICABLE_FIELDS
            | _store_not_applicable_key_money(self.business, self.key_money_manwon)
        )
        # 업종 조건도 공실 묶음도 없으면 어느 묶음인지 가릴 일이 없어 해당 없다
        if self.vacant_section is None:
            fields |= {'vacant_section'}
        return fields


class ZigbangStoreListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 상가·사무실 매물."""

    business: Annotated[
        str | None,
        Field(description='업종 (현재·직전 업종, 공실이면 기타)')
    ] = None
    key_money_manwon: Annotated[
        float | None,
        Field(description='권리금 (만원). 0 이면 무권리. 업종이 사무실이고 직방이 주지 않으면 키가 없다')
    ] = None
    recommended_business: Annotated[
        str | None,
        Field(description='추천 업종')
    ] = None
    vacancy: Annotated[
        str | None,
        Field(description="구분 (예: '공실')")
    ] = None
    lease_unit: Annotated[
        str | None,
        Field(description='임대 구분 (예: 개별호, 통임대)')
    ] = None
    interior: Annotated[
        str | None,
        Field(description='인테리어 유무')
    ] = None
    toilet: Annotated[
        str | None,
        Field(description='화장실')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 종류')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        return (
            super().not_applicable_fields()
            | STORE_NOT_APPLICABLE_DETAIL_FIELDS
            | _store_not_applicable_key_money(self.business, self.key_money_manwon)
        )


class ZigbangStoreSearchResult(Result):
    """상가·사무실 검색 결과.

    `notes`: 일부만 보여 준다·공실 묶음을 이었다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float | None,
        Field(description='검색 반경 (km). 동 안을 찾았으면 키가 없다')
    ] = None
    boundary: Annotated[
        str | None,
        Field(description="반경 대신 법정동 코드로 그 안을 찾은 동 이름 (여럿이면 '·' 로 잇는다). 반경으로 찾았으면 키가 없다")
    ] = None
    total: Annotated[
        int | None,
        Field(description=(
            '반경(또는 동) 안 직방 목록의 매물 수 (직방이 이 지역 비어있는 상가 공실 묶음을 주면 업종 조건과 상관없이 공실 포함). 가격 필터 적용 전. '
            '직방이 위치 묶음 목록에 빈 항목을 줘 셀 수 없으면 null'
        ))
    ]
    inspected_in_radius: Annotated[
        int | None,
        Field(description='반경(또는 동) 안 직방 목록 앞에서부터 요약을 요청한 매물 수. 가격 조건이 있을 때만 출력')
    ] = None
    price_matched_in_radius: Annotated[
        int | None,
        Field(description='확인한 후보 중 거래 가능하고 가격 조건에 맞는 수. 전체 매물 수가 아니다')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위(반경·동) 안에 더 있는지: 요약을 받지 않은 매물이 남았거나 --limit 에 맞춰 잘랐다 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        list[ZigbangStoreListing],
        Field(description='직방 목록 순서 그대로의 매물 (거리순이 아니다)')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = drop_unused_scope(handler(self))
        for key in ('inspected_in_radius', 'price_matched_in_radius'):
            if data.get(key) is None:
                data.pop(key, None)
        return data


class ZigbangStoreConditions(RequestModel):
    """상가·사무실 매물 조건 (search listings store). 금액은 만원, 면적은 ㎡.

    거래 유형·1층·업종·면적은 서버에서 거르고, 가격은 요약을 받은 뒤 거른다 (`search_store_listings`).
    """

    trade: Annotated[
        ZigbangStoreSalesType,
        Field(description='거래 유형 (임대·매매·전체)')
    ] = '전체'
    first_floor: Annotated[
        bool,
        Field(description='1층만')
    ] = False
    businesses: Annotated[
        list[str],
        Field(description='업종·업종 대분류 (STORE_BUSINESS_NAMES)')
    ] = []
    area_min_m2: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='면적 상한 (㎡, 미만)')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    manage_cost_min: Annotated[
        int | None,
        Field(description='월 관리비 하한 (만원)')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(description='월 관리비 상한 (만원)')
    ] = None
    key_money_min: Annotated[
        int | None,
        Field(description='권리금 하한 (만원)')
    ] = None
    key_money_max: Annotated[
        int | None,
        Field(description='권리금 상한 (만원)')
    ] = None


def _store_not_applicable_key_money(business: str | None, key_money_manwon: float | None) -> frozenset[str]:
    """업종이 사무실이고 직방이 권리금을 주지 않았으면 키를 뺄 권리금 필드."""
    if business == STORE_OFFICE_BUSINESS and key_money_manwon is None:
        return frozenset({'key_money_manwon'})
    return frozenset()
