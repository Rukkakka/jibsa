from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import DabangRoomListResponseModel

from typing import Annotated


class DabangRoomListCategoryV5ResponseModel(DabangRoomListResponseModel):
    """`GET /api/v5/room-list/category/{category}/{search_type}` 응답."""


class DabangNamedModel(ResponseModel):
    """옵션·보안 시설 한 칸 (`{"seq": 7, "name": "냉장고"}`)."""

    name: Annotated[
        str,
        Field(description='이름')
    ]


class DabangMaintenanceEtcDetailModel(ResponseModel):
    """관리비 세부 (`maintenance_etc_fee_charge_detail`). 정액 관리비가 10만원 미만이라 세부를 따로 적지 않은 매물 등에 온다.

    Args:
        detail_include_types: 관리비에 든 항목 코드 (`WATER_RATES` 수도, `INTERNET_RATES` 인터넷 …).
    """

    detail_include_types: Annotated[
        list[str],
        Field(description='관리비 포함 항목 코드')
    ] = []


class DabangMaintenanceFixedDetailModel(ResponseModel):
    """정액 관리비 세부 항목 하나 (`maintenance_fixed_fee_charge_detail_list`). 정액 관리비가 10만원 이상인 매물에 온다.

    Args:
        detail_code: 항목 코드 (`F01` 공용, `F11` 전기, `F12` 수도, `F13` 가스, `F14` 난방, `F15` 인터넷, `F16` TV, `F99` 기타).
        detail_cost_formulated_type: `FIXED_FEE`(관리비에 든 정액) 또는 `ACTUAL_EXPENSE`(실비로 따로 냄).
    """

    detail_code: Annotated[
        str,
        Field(description='항목 코드')
    ]
    detail_cost_formulated_type: Annotated[
        str | None,
        Field(description='정액(FIXED_FEE) 또는 실비(ACTUAL_EXPENSE)')
    ] = None


class DabangNewRoomDetailRoomModel(ResponseModel):
    """상세의 매물 (`room`). 응답 키는 snake_case 다 (웹이 받은 뒤 camelCase 로 바꾼다).

    가격은 `price_info` 에 `[보증금 또는 매매가, 월세, 거래 유형]` 숫자(만원)로 온다 (월세 `[[1000, 63, 0]]`, 매매
    `[[39000, 0, 2]]`, 2026-10-25 실측). 거래 유형은 `selling_type` 과 같은 코드다 (0 월세, 1 전세, 2 매매). 관리비
    `maintenance_cost` 는 **원** 단위다 (70000 = 7만원). 단기임대는 별도 거래가 아니라 월세 매물에 붙는 표시라
    `short_lease_str` 에 받는 기간이 온다 ('1개월(이상 협의가능)'). 화면은 `status` 가 0·3·4 이면 '비공개 처리된 매물' 로
    닫는다 (room 청크, 2026-10-25).

    본문(`memo`)·좌표(`location`, `random_location`)·사진은 모델에 두지 않는다 (출력하지 않는 정보).
    """

    id: Annotated[
        str,
        Field(description='매물 ID')
    ]
    seq: Annotated[
        int | None,
        Field(description='매물번호')
    ] = None
    status: Annotated[
        int | None,
        Field(description='공개 상태 (1 공개, 0·3·4 비공개)')
    ] = None
    title: Annotated[
        str | None,
        Field(description='한 줄 제목')
    ] = None
    room_type_str: Annotated[
        str | None,
        Field(description="매물 종류 ('원룸', '오피스텔' ...)")
    ] = None
    selling_type: Annotated[
        int | None,
        Field(description='거래 유형 코드 (0 월세, 1 전세, 2 매매)')
    ] = None
    price_info: Annotated[
        list[list[float]],
        Field(description='[[보증금 또는 매매가, 월세, 거래 유형 코드]] (만원)')
    ] = []
    room_size: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    provision_size: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    maintenance_cost: Annotated[
        float | None,
        Field(description='월 관리비 (원). 관리비가 없으면 null 이고 maintenance_cost_str 이 "없음"')
    ] = None
    maintenance_cost_str: Annotated[
        str | None,
        Field(description="관리비 글 ('7만원', '없음')")
    ] = None
    maintenance_items_str: Annotated[
        list[str],
        Field(description='관리비 포함 항목 이름')
    ] = []
    maintenance_etc_fee_charge_detail: Annotated[
        DabangMaintenanceEtcDetailModel | None,
        Field(description='관리비 세부')
    ] = None
    maintenance_fixed_fee_charge_detail_list: Annotated[
        list[DabangMaintenanceFixedDetailModel] | None,
        Field(description='정액 관리비 세부 항목 (10만원 이상)')
    ] = None
    parking: Annotated[
        bool | None,
        Field(description='주차 가능')
    ] = None
    parking_num: Annotated[
        float | None,
        Field(description='총 주차 대수')
    ] = None
    moving_date: Annotated[
        str | None,
        Field(description="입주 가능일 ('즉시 입주', '즉시 입주 (협의 가능)', 날짜)")
    ] = None
    full_jibun_address_str: Annotated[
        str | None,
        Field(description='지번 주소 (번지는 대개 가려져 동까지)')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (오피스텔·아파트)')
    ] = None
    room_floor_str: Annotated[
        str | None,
        Field(description="해당 층 ('5층', '고층')")
    ] = None
    building_floor_str: Annotated[
        str | None,
        Field(description="건물 층수 ('6층')")
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방')
    ] = None
    elevator_str: Annotated[
        str | None,
        Field(description="엘리베이터 ('있음', '없음', '-')")
    ] = None
    loan_str: Annotated[
        str | None,
        Field(description="융자 ('시세대비 30%미만' 등)")
    ] = None
    short_lease_str: Annotated[
        str | None,
        Field(description='단기임대를 받는 기간. 받지 않으면 null')
    ] = None
    beds_num: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bath_num: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    direction_str: Annotated[
        str | None,
        Field(description='방향')
    ] = None
    direction_measurement_base_type_str: Annotated[
        str | None,
        Field(description='방향 기준 (안방·거실)')
    ] = None
    building_use_types_str: Annotated[
        list[str],
        Field(description="건축물 용도 ('단독주택', '공동주택' ...)")
    ] = []
    building_approval_type_str: Annotated[
        str | None,
        Field(description="날짜 종류 ('사용승인일' 등)")
    ] = None
    building_approval_date_str: Annotated[
        str | None,
        Field(description="사용승인일 ('2010.11.17')")
    ] = None
    saved_time_str: Annotated[
        str | None,
        Field(description="등록일 ('2026.09.29')")
    ] = None
    room_options: Annotated[
        list[DabangNamedModel] | None,
        Field(description='옵션')
    ] = None
    safeties: Annotated[
        list[DabangNamedModel] | None,
        Field(description='보안 시설')
    ] = None
    is_contract: Annotated[
        bool | None,
        Field(description='계약 완료 표시')
    ] = None


class DabangNewRoomDetailV3ResponseModel(ResponseModel):
    """`GET /api/3/new-room/detail` 응답. 봉투 없이 바로 온다. 중개사(`agent`·`contact`)·사진(`image_list`)·같은 중개사의
    다른 매물(`other_rooms`)도 오지만 모델에 두지 않는다. 없는 매물은 400 `{"msg": "존재하지 않는 매물입니다."}` 다.
    """

    room: Annotated[
        DabangNewRoomDetailRoomModel,
        Field(description='매물')
    ]


class DabangRoomGetRoomIdV3ResponseModel(ResponseModel):
    """`GET /api/3/room/get-room-id` 응답 (매물번호 → 매물 ID)."""

    room_id: Annotated[
        str | None,
        Field(description='매물 ID')
    ] = None
