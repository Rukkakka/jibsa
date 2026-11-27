"""매물 상세 (listing). `get_listing` 이 기본 정보·제목·입주·지번을 만들고, 단지·건물 시설(facility)·비용(cost)·주변(nearby)은 주제 모듈을 부른다."""

from httpx import HTTPStatusError

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    iso_date,
    join_address,
    m2_to_pyeong,
    move_in_label,
    normalize_address,
    note,
    read_date,
    with_negotiable,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.listing.detail import (
    NaverArticleBasicInfoV1RequestParameterModel,
    NaverArticleKeyV1RequestParameterModel,
    NaverArticleMaintenanceFeeV1RequestParameterModel,
    NaverArticleOldMaintenanceFeeV1RequestParameterModel,
    NaverLegalDivisionInfoListV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import NaverResponseModel
from jibsa.providers.naver.api.response.listing.detail import (
    NaverArticleBasicInfoModel,
    NaverArticleDetailInfoModel,
    NaverArticleKeyModel,
    NaverArticleMaintenanceFeeModel,
    NaverArticleOldMaintenanceFeeModel,
    NaverMovingInInfoModel,
    NaverPriceInfoModel,
    NaverSpaceInfoModel,
)
from jibsa.providers.naver.service.common.constants import (
    ARTICLE_URL,
    NOT_APPLICABLE_FIELDS_BY_TYPE,
    OFFICETEL_CODE,
    OPTIONAL_LOOKUP_ERRORS,
    PROPERTY_NAME_BY_CODE,
    TRADE_NAME_BY_CODE,
)
from jibsa.providers.naver.service.common.labels import (
    dong_label,
    unknown_code_label,
)
from jibsa.providers.naver.service.common.listing import (
    building_approved_at,
    known_floor,
    listing_badges,
)
from jibsa.providers.naver.service.common.response import (
    add_failure_note,
    result_or_empty,
    result_or_none,
)
from jibsa.providers.naver.service.listing.common import coded_label
from jibsa.providers.naver.service.listing.constants import (
    BUILDING_SUB_NAME_BUILDING_TYPES,
    BUILDING_SUB_NAME_REAL_ESTATE_TYPES,
    BUILDING_TYPE_LABELS,
    COMPLEX_INFO_TYPES,
    DIRECTION_BY_CODE,
    FACILITY_LABELS,
    JIBUN_EXPOSURE_BUILDING_TYPE,
    JIBUN_EXPOSURE_REAL_ESTATE_TYPES,
    KNOWN_REAL_ESTATE_TYPES,
    MOVING_IN_BOUND_LABELS,
    MOVING_IN_LABELS,
    MOVING_IN_PERIOD_LABELS,
    ONE_ROOM_TYPE_BY_SHAPE,
    YEAR_MONTH_PATTERN,
)
from jibsa.providers.naver.service.listing.cost import (
    agent_fee,
    has_fee_cell,
    sale_taxes,
)
from jibsa.providers.naver.service.listing.cost import manage_cost as _manage_cost
from jibsa.providers.naver.service.listing.facility import (
    complex_approved_at,
    complex_overview,
)
from jibsa.providers.naver.service.listing.facility import (
    facility_values as _facility_values,
)
from jibsa.providers.naver.service.listing.models import (
    NaverListingDetail,
    draws_sale_taxes,
)
from jibsa.providers.naver.service.listing.nearby import (
    nearby_development,
    surroundings,
)


def _room_type(space: NaverSpaceInfoModel | None, shape: str | None) -> str | None:
    """상세의 방 구조. 방 수로 투룸·쓰리룸·포룸이상을 가리고, 방 1개면 복층 여부와 원룸 구조(shape)로 정한다.

    shape 는 방이 여럿인 매물도 분리형('20')으로 오므로 방 수를 먼저 본다. 단지 매물(아파트·오피스텔·단지형 빌라)은
    shape 가 없어 복층이 아닌 방 1개면 구조를 몰라 None 이다 (방 수는 room_count 로 준다).
    """
    if space is None or not space.room_count:
        return None
    count = space.room_count
    if count == 2:
        return '투룸'
    if count == 3:
        return '쓰리룸'
    if count >= 4:
        return '포룸이상'
    if space.duplex:
        return '복층형원룸'
    return ONE_ROOM_TYPE_BY_SHAPE.get(shape or '')


def _loan_manwon(price: NaverPriceInfoModel | None) -> float | None:
    """융자금(만원). 금액이 있으면 그 값, 융자 없음이 명시(loanCode '0')면 0, 그 외는 모름(None).

    네이버는 융자를 입력하지 않은 매물도 `loan: 0` 으로 주고 loanCode 를 빼서 보낸다.
    """
    if price is None:
        return None
    if price.loan:
        return won_to_manwon(price.loan)
    if price.loan_code == '0':
        return 0.0
    return None


def _year_month(value: str | None) -> str | None:
    """연월만 있는 글자(`2026-11`·`202611`·`2026.11`)를 `YYYY-MM` 으로 읽는다. 월이 1~12 가 아니거나 못 읽으면 None."""
    match = YEAR_MONTH_PATTERN.match((value or '').strip())
    if match is None or not 1 <= int(match.group(2)) <= 12:
        return None
    return f'{match.group(1)}-{match.group(2)}'


def _move_in_label(moving: NaverMovingInInfoModel | None, notes: list[str]) -> str | None:
    """입주 시기 코드를 읽을 수 있는 문구로 바꾼다.

    이내입주('MV002')·이후입주('MV003')는 날짜 뒤에 '이내'·'이후' 를 붙인다 (웹과 같다). 날짜 지정('MV004')·모르는 코드는
    날짜만 쓰고, 연월만 오면 연월('2026-12')을 쓴다. 코드('MV004')를 그대로 내보내지 않는다. 초순·중순·하순과 이내·이후는 연월만
    와도 만든다 ('2026-12 초순'·'2026-12 이내'. 이내·이후는 전체 날짜면 '2026-12-01 이내'). 날짜가 없으면('-'·빈 글자)
    웹처럼 협의 가능일 때만 '협의 가능', 아니면 모름(None)이다. 날짜는 있는데 못 읽으면 같은 값을 내고 `notes` 에 `[참고]` 안내를 붙인다
    (못 읽는 글자를 입주일로 내지 않는다).
    """
    if moving is None:
        return None
    code = moving.moving_in_type or ''
    date = (moving.moving_in_date or '').strip() or None
    if date == '-':
        # 날짜 자리의 '-' 는 값이 없다는 표시라 모름이다 (층의 '-' 와 같다, `known_floor`)
        date = None
    negotiable = moving.moving_in_negotiation
    day = iso_date(date)
    # 연월은 두 갈래가 같게 읽는다 (이내·이후만 전체 날짜를 요구하면 연월만 온 이내·이후입주가 '이내'·'이후' 를 잃는다)
    month = day[:7] if day is not None else _year_month(date)
    if code in MOVING_IN_PERIOD_LABELS and month is not None:
        return with_negotiable(f'{month} {MOVING_IN_PERIOD_LABELS[code]}', negotiable)
    if code in MOVING_IN_BOUND_LABELS and month is not None:
        return with_negotiable(f'{day or month} {MOVING_IN_BOUND_LABELS[code]}', negotiable)
    if code in MOVING_IN_LABELS:
        return move_in_label(MOVING_IN_LABELS[code], negotiable=bool(negotiable))
    if date is None:
        return '협의 가능' if negotiable else None
    label = day or month
    if label is None:
        if code in MOVING_IN_BOUND_LABELS:
            kind = f'{MOVING_IN_BOUND_LABELS[code]}입주'
        elif code == 'MV004':
            kind = '날짜 지정'
        else:
            kind = f'{MOVING_IN_PERIOD_LABELS[code]}입주' if code in MOVING_IN_PERIOD_LABELS else f'입주 유형 {code}' if code else '입주 유형 모름'
        notes.append(note('참고', f"네이버가 준 입주일을 읽지 못했습니다 ({kind}, 날짜 '{date}'). url 의 매물 화면에서 확인하세요"))
        return '협의 가능' if negotiable else None
    # 연월('2026-12')은 날짜로 읽지 못하는 꼴이라 `move_in_label` 에 넘기면 못 읽은 입주일로 모아 None 이 된다. day·month 는 이미 읽은 값이라 협의만 붙인다
    return with_negotiable(label, bool(negotiable))


def get_listing(client: NaverClient, article_number: str) -> NaverListingDetail:
    """매물 상세: key → basicInfo → maintenanceFee → 법정동 코드의 지역 이름 → 단지·중개보수·세금·교통·학교·개발 예정 (최대 12회 호출, 단지부터는 필요할 때만).

    관리비는 maintenanceFee 로 '관리비' 칸을 못 만들 때(응답이 비었거나 실패, 금액·사유 없음)만 옛 형식 관리비(`oldMaintenanceFee`)를 1회 더 받아
    금액을 채운다 (상가 등, 웹도 그렇게 그린다). 포함 항목은 몰라 null 이다.

    단지는 아파트·오피스텔·재건축·분양권이면 단지 정보(`/complex`)를, 단지형 빌라면 `/complex/villa` 를 늘 받아 난방·주차를 웹처럼
    단지 값으로 채우고, 거기에 아파트·오피스텔·재건축·분양권은 매물에 현관 구조가 없을 때
    평형(`/complex/pyeong`), 단지형 빌라는 건물 날짜가 없을 때 동 목록(buildingList)을 더 받는다 (1~2회, `facility_values`).
    그 밖의 유형은 단지 번호가 있고 건물 날짜가 없을 때만 단지 정보를 받는다 (사용승인일 칸이 없는 토지·고시원은 받지 않는다).

    중개보수(agentFee)는 직거래가 아니면(직거래이거나 직거래인지 모를 때는 조회하지 않는다) 모든 거래 유형에서, 세금(tax)은 매매 매물만 더 조회한다
    (원룸·고시원 매매, 일반분양권이 아니거나 분양 상태를 모르는 분양권은 조회하지 않는다) (1회 더, 매매는 2회 더). 주변 교통(지하철·버스)은 늘,
    배정 초등학교는 단지·동 번호가 있는 매물만 더 조회한다 (1~2회 더). 주변 개발 예정(`development/article`)은 유형과 상관없이 늘
    1회 더 조회한다 (웹도 모든 매물 상세에 그린다). 최대 12회.
    건축물대장 유형(원룸·빌라 등 15개)은 매물 주차 대수가 0 이거나 없고 article/key 에 pnu 가 있을 때만 건축물대장(`/complex/buildingRegistration`)을
    1회 더 조회하고, 그 대수와 세대당 대수로 주차를 채운다 (`facility_values`). 이 유형은 단지 정보를 받아도 1회뿐이라 최대 12회를 넘지 않는다.

    중개사 정보와 본문은 내보내지 않는다 (문의·상세 설명은 원 사이트에서). 주소는 웹 위치 칸처럼 article/key 의 법정동 코드로 받은
    지역 이름(`legalDivision/infoList`)에 리와 지번을 붙여 만든다 (`_jibun_address`). 이 조회는 article/key 에 법정동 코드가 있으면 좌표와
    상관없이 1회다 (전에는 좌표가 없으면 0회). 사용승인일은 단지 유형(아파트·오피스텔·재건축·분양권)이면 단지 정보(`/complex`)의
    날짜만 쓰고(웹처럼 매물 날짜는 보지 않는다), 단지형 빌라와 그 밖의 유형은 상세의 건물 날짜(facilityInfo)를 쓰되 없으면 단지형 빌라는
    동 목록(buildingList), 그 밖의 유형은 단지 정보에서 받는다.

    key·basicInfo 밖의 부가 조회(관리비·법정동·단지·중개보수·세금·교통·학교·개발 예정)는 실패하면 그 값만 모름(None)이고, 실패한 조회마다
    결과 `notes` 에 `[실패]` 안내가 붙는다 (같은 안내는 한 번만).

    Raises:
        ListingUnavailableError: 없거나 내려간 매물이거나, 모르는 거래 유형·매물 유형 코드일 때
            (reason UNKNOWN_TRADE_TYPE·UNKNOWN_REAL_ESTATE_TYPE, listing_status 에 원래 코드).
    """
    key, trade_type = _article_key(client, article_number)
    basic = _article_basic(client, article_number, key)
    notes: list[str] = []
    # 관리비 조회 실패 안내는 옛 형식 관리비로 금액을 얻으면 사실과 달라지므로(모름이 된 칸이 다르다) 바로 붙이지 않는다.
    # maintenanceFee 의 예외는 남겨 두고 옛 형식 조회가 끝난 뒤 붙인다
    fee_errors: list[Exception] = []

    def request_fee() -> NaverResponseModel[NaverArticleMaintenanceFeeModel]:
        try:
            return client.run_request_article_maintenance_fee_v1(
                NaverArticleMaintenanceFeeV1RequestParameterModel(article_number=article_number)
            )
        except OPTIONAL_LOOKUP_ERRORS as exc:
            fee_errors.append(exc)
            raise

    unknown_both = '모름(null)으로 낸 칸: manage_cost_manwon, manage_cost_includes'
    fee = result_or_none(request_fee, notes=None, what='관리비', unknown=unknown_both)
    # 웹 ArticlePriceInfo(청크 0l4pkwg0qhg2t)와 상가 2662726134 실측 (2026-11-24): 웹은 maintenanceFee·oldMaintenanceFee 를 늘 둘 다 부르고
    # 앞의 것으로 칸을 못 만들 때 뒤의 amount 로 '관리비 <금액>' 칸을 그린다. jibsa 는 앞의 것으로 칸을 못 만들 때만 부른다 (요청을 아낀다)
    old_fee: NaverArticleOldMaintenanceFeeModel | None = None
    old_notes: list[str] = []
    if not has_fee_cell(fee):
        old_fee = result_or_none(
            lambda: client.run_request_article_old_maintenance_fee_v1(
                NaverArticleOldMaintenanceFeeV1RequestParameterModel(article_number=article_number)
            ),
            notes=old_notes,
            what='관리비',
            unknown=unknown_both,
        )
    # 리뷰 오탐 (2026-11-24): 옛 형식 금액 0 도 칸으로 낸다. 웹 isValidNumber(amount)(청크 414mp5_jlfont)는 0 도 수로 봐 '관리비 0원' 을 그린다
    # 리뷰 오탐 (2026-11-24): 두 조회가 서로 다른 이유로 실패하면 [실패] 가 두 줄이다. 두 요청의 실패를 각각 맞게 알리는 것이라 합치지 않는다
    old_amount = old_fee.amount if old_fee else None
    # maintenanceFee 가 예외로 실패했으면 안내를 먼저 붙인다. 옛 형식 금액을 받았으면 금액 칸은 채워졌고 포함 항목만 모름이다
    if fee_errors:
        add_failure_note(
            notes,
            fee_errors[0],
            '관리비',
            unknown_both if old_amount is None else '모름(null)으로 낸 칸: manage_cost_includes',
        )
    # 옛 형식 조회의 실패 안내는 금액을 못 얻었을 때만 붙인다 (금액을 얻었으면 실패가 아닌 것으로 읽힌다)
    if old_amount is None:
        for text in old_notes:
            if text not in notes:
                notes.append(text)

    price = basic.price_info
    detail = basic.detail_info
    article = detail.article_detail_info if detail else None
    space = detail.space_info if detail else None
    size = detail.size_info if detail else None
    moving = detail.moving_in_info if detail else None
    facility = detail.facility_info if detail else None
    complex_info = basic.communal_complex_info

    # 단지 이름(없으면 매물 이름)·동과 매물 특징으로 제목을 만든다
    title_parts = [
        (complex_info.complex_name if complex_info else None) or (article.article_name if article else None),
        dong_label(complex_info.dong_name) if complex_info and complex_info.dong_name else None,
    ]
    title = ' '.join(part for part in title_parts if part)
    if article and article.article_feature_description:
        title = f'{title} · {article.article_feature_description}' if title else article.article_feature_description
    move_in = _move_in_label(moving, notes)
    if old_amount is None:
        manage_cost, manage_cost_includes = _manage_cost(fee, notes)
    else:
        # 옛 형식은 금액뿐이라 포함 항목은 모른다 (웹도 항목을 보여 주지 않는다)
        manage_cost, manage_cost_includes = won_to_manwon(old_amount), None

    exclusive = size.exclusive_space if size else None
    # 상세의 supplySpace 는 오피스텔이면 계약면적이다 (평형표의 contractArea 와 같고 supplyArea 보다 크다).
    # 다른 유형은 공급면적 그대로다. 오피스텔 공급면적은 평형표를 더 조회해야 해 모름(None)으로 둔다.
    is_officetel = key.type.real_estate_type == OFFICETEL_CODE
    listed_area = size.supply_space if size else None
    coordinates = article.coordinates if article else None

    address = _jibun_address(client, key, article, notes)

    # communalComplexInfo 는 단지 매물에만 오고, 오면 complexNumber 가 article/key 의 단지 번호와 같다. 단지가 없는
    # 매물은 둘 다 비어 있다 (단독·다가구·빌라·원룸·단지형 빌라·오피스텔·아파트 10건, 2026-10-10 확인)
    complex_number = complex_info.complex_number if complex_info else (key.key.complex_number if key.key else None)

    facility_codes = (facility.life + facility.security + facility.etc + facility.aircon) if facility else []
    real_estate_type = key.type.real_estate_type
    verification = detail.verification_info if detail else None
    # 직거래 여부를 모르면(상세 정보를 못 읽었거나 값이 없으면) None 이다. 직거래에도 agentFee 가 금액을 주므로 모를 때는 요청하지 않는다
    is_direct_trade = article.is_direct_trade if article else None
    pre_sale_status_type = detail.pre_sale_status_type if detail else None
    # 단지 유형은 단지 정보를 한 번 받아 사용승인일·난방·주차가, 단지형 빌라는 난방·주차가 함께 쓴다 (단지형 빌라 사용승인일은 동 목록을 따로 받는다) (요청 순서: 법정동, 단지, 동 목록·평형, 건축물대장, agentFee ...)
    complex_ = complex_overview(client, complex_number, real_estate_type, notes)
    if complex_number is not None and real_estate_type in COMPLEX_INFO_TYPES:
        # 웹(ArticleComplexInfo)은 단지 유형의 사용승인일을 단지 정보(useApprovalDate)에서만 그리고 매물 facilityInfo 날짜는 보지 않는다.
        # 단지 조회가 실패해 complex_ 가 None 이면 모름이다 (매물 날짜로 대신하지 않는다)
        approved_at = complex_approved_at(client, complex_number, key, complex_, notes)
    elif 'approved_date' in NOT_APPLICABLE_FIELDS_BY_TYPE.get(real_estate_type or '', frozenset()):
        # 토지·고시원은 사용승인일 칸이 없어(출력에서 키를 뺀다) 받을 값이 없다. 단지 조회를 부르면 요청만 쓰고, 실패하면
        # 출력에 없는 칸을 모름이라고 안내하게 된다 (2026-11-19 사용자 결정)
        approved_at = None
    else:
        approved_at = building_approved_at(facility) or complex_approved_at(client, complex_number, key, complex_, notes)
    approved_at = read_date(approved_at, '사용승인일')
    facility_values = _facility_values(client, key, facility, complex_number, complex_, notes)

    # 웹 제목의 건물 이름. 건물 이름이 없으면 None. 건물 하위 이름은 매물 유형이 C01·D05 이거나
    # (유형, 건물 세부 유형)이 `BUILDING_SUB_NAME_BUILDING_TYPES` 의 짝일 때만 띄어 붙이고, 그 밖에는 건물 이름만 쓴다.
    building_name: str | None = None
    if article is not None:
        name = (article.non_complex_building_name or '').strip()
        if name:
            sub_name = (article.non_complex_building_sub_name or '').strip()
            joins_sub_name = real_estate_type in BUILDING_SUB_NAME_REAL_ESTATE_TYPES or (
                article.building_type in BUILDING_SUB_NAME_BUILDING_TYPES.get(real_estate_type, frozenset())
            )
            building_name = f'{name} {sub_name}' if sub_name and joins_sub_name else name

    # 방향 ('남향', 기준이 있으면 '남향 (거실 기준)'). 표에 없는 코드는 괄호를 한 번만 써서 '알 수 없는 값 (XY, 거실 기준)' 으로 낸다
    direction = coded_label(DIRECTION_BY_CODE, space.direction if space else None)
    if direction is not None and space is not None and space.direction_standard:
        direction = (
            unknown_code_label('값', f'{space.direction}, {space.direction_standard}')
            if space.direction not in DIRECTION_BY_CODE
            else f'{direction} ({space.direction_standard})'
        )

    return NaverListingDetail(
        source='naver',
        id=article_number,
        url=ARTICLE_URL.format(article_number),
        trade_type=trade_type,
        property_type=PROPERTY_NAME_BY_CODE.get(real_estate_type, real_estate_type),
        room_type=_room_type(space, detail.shape if detail else None),
        title=title or None,
        price_manwon=won_to_manwon(price.price) if price and trade_type == '매매' else None,
        deposit_manwon=(
            won_to_manwon(price.warranty_amount if price.warranty_amount is not None else price.price)
            if price and trade_type != '매매' else None
        ),
        rent_manwon=(
            won_to_manwon(price.rent_amount if price.rent_amount is not None else price.monthly_rent)
            if price and trade_type in ('월세', '단기임대') else None
        ),
        # 목록의 0 은 0원 입력과 미확인을 구분할 수 없어 모름으로 두고, 상세 관리비 API 로 구분한다 (`manage_cost`)
        manage_cost_manwon=manage_cost,
        manage_cost_includes=manage_cost_includes,
        area_m2=exclusive,
        area_pyeong=m2_to_pyeong(exclusive),
        floor=known_floor(space.floor_info.target_floor) if space and space.floor_info else None,
        building_floor=known_floor(space.floor_info.total_floor) if space and space.floor_info else None,
        address=address,
        lat=coordinates.y_coordinate if coordinates else None,
        lng=coordinates.x_coordinate if coordinates else None,
        registered_date=read_date(article.exposure_start_date, '등록일') if article else None,
        # 상세 응답의 건물 날짜를 먼저 쓰고, 없을 때만 단지 정보를 쓴다 (단지 유형은 이미 받은 단지 정보, 그 밖은 필요할 때만 조회)
        approved_date=approved_at,
        complex_id=complex_number,
        complex_name=complex_info.complex_name if complex_info else None,
        building_dong=complex_info.dong_name if complex_info else None,
        pyeong_id=key.key.pyeong_type_number if key.key else None,
        building_name=building_name,
        building_type=coded_label(BUILDING_TYPE_LABELS, article.building_type if article else None),
        has_article_detail=article is not None,
        is_direct_trade=is_direct_trade is True,
        pre_sale_status_type=pre_sale_status_type,
        real_estate_type=real_estate_type,
        supply_area_m2=None if is_officetel else listed_area,
        contract_area_m2=listed_area if is_officetel else None,
        room_count=space.room_count if space else None,
        bathroom_count=space.bath_room_count if space else None,
        direction=direction,
        move_in=move_in,
        parking=facility_values.parking,
        # 엘리베이터는 중개사가 고르는 기타시설(etc) 항목 하나라 없으면 고르지 않은 것인지 없는 것인지 모른다. 그래서 False 를
        # 내지 않는다 (2026-10-14 실측: 신림동 원룸 상세 3건 중 1건이 시설 13개를 골랐지만 ELEVATOR 는 없었고, 다른 1건은
        # 보안시설을 비워 두었다. 엘리베이터 없음을 따로 알리는 필드는 없다)
        has_elevator=True if 'ELEVATOR' in facility_codes else None,
        options=[
            FACILITY_LABELS.get(code) or unknown_code_label('시설', code)
            for code in facility_codes
            if code != 'ELEVATOR'
        ] if facility is not None else None,
        heating=facility_values.heating,
        heating_fuel=facility_values.heating_fuel,
        entrance=facility_values.entrance,
        badges=listing_badges(
            verification.verification_type if verification else None,
            real_estate_type,
            article.is_safe_lessor_of_hug if article else None,
        ),
        confirmed_date=read_date(verification.article_confirm_date, '매물 확인일') if verification else None,
        loan_manwon=_loan_manwon(price),
        # 중개보수는 직거래가 아님이 확인된 매물만 모든 거래 유형에서 조회하고(모르면 둘 다 null, 직거래면 키를 뺀다), 세금은 웹이
        # 세금 칸을 그리는 매매(원룸·고시원·일반분양권이 아닌 분양권·분양 상태를 모르는 분양권 제외)만 조회한다 (요청 순서: agentFee, tax, 교통·학교, 개발 예정)
        **(
            {'broker_fee_manwon': None, 'broker_fee_individual_check_required': None} if is_direct_trade is None
            else {} if is_direct_trade
            else agent_fee(client, article_number, notes)
        ),
        **(
            sale_taxes(client, article_number, real_estate_type, notes)
            if draws_sale_taxes(trade_type, real_estate_type, pre_sale_status_type) is True else {}
        ),
        **surroundings(client, article_number, key, notes),
        nearby_development=nearby_development(client, article_number, notes),
        notes=notes,
    )


def _article_key(client: NaverClient, article_number: str) -> tuple[NaverArticleKeyModel, str]:
    """매물 키(유형·단지·주소)와 거래 유형 이름. 모르는 거래 유형·매물 유형이면 나머지 요청을 보내지 않는다.

    Raises:
        ListingUnavailableError: 없거나 내려간 매물이거나, 모르는 거래 유형·매물 유형 코드일 때.
    """
    try:
        key_response = client.run_request_article_key_v1(
            NaverArticleKeyV1RequestParameterModel(article_number=article_number)
        )
    except HTTPStatusError as exc:
        # 매물 번호 형식이 아니면(너무 짧은 번호 등) 400 FST_ERR_VALIDATION 이다. 그런 매물은 없다.
        if exc.response.status_code in (400, 404):
            raise ListingUnavailableError('naver', article_number) from None
        raise
    if not key_response.is_success or key_response.result is None:
        raise ListingUnavailableError('naver', article_number)
    key = key_response.result
    trade_type = TRADE_NAME_BY_CODE.get(key.type.trade_type)
    if trade_type is None:
        # 모르는 거래 유형이면 가격을 어느 필드로 옮길지 몰라 틀린 값을 내게 된다. 목록에서 빼는 것과
        # 맞추고, 나머지 요청(basicInfo 등)도 보내지 않는다.
        raise ListingUnavailableError(
            'naver', article_number, status=key.type.trade_type, reason='UNKNOWN_TRADE_TYPE'
        )
    if key.type.real_estate_type not in KNOWN_REAL_ESTATE_TYPES:
        # 응답 값을 요청 모델(Literal)에 넣다 실패하면 handle_errors 가 사용자 입력 오류(INVALID_ARGUMENT)로 낸다.
        # 서버가 받는 유형 코드 밖이라 basicInfo 도 400 이므로, 모르는 거래 유형처럼 볼 수 없는 매물로 낸다
        raise ListingUnavailableError(
            'naver', article_number, status=key.type.real_estate_type, reason='UNKNOWN_REAL_ESTATE_TYPE'
        )
    return key, trade_type


def _article_basic(client: NaverClient, article_number: str, key: NaverArticleKeyModel) -> NaverArticleBasicInfoModel:
    """매물 기본 정보 (가격·면적·층·시설·단지).

    Raises:
        ListingUnavailableError: 없거나 내려간 매물일 때.
    """
    basic_response = client.run_request_article_basic_info_v1(
        NaverArticleBasicInfoV1RequestParameterModel(
            article_number=article_number,
            real_estate_type=key.type.real_estate_type,
            trade_type=key.type.trade_type,
        )
    )
    # 없거나 내려간 매물, 유형이 맞지 않는 요청 모두 404 가 아니라 200 + isSuccess=false 로 온다
    # (실제 API 로 확인). 그래서 article/key 와 달리 HTTPStatusError 를 따로 잡지 않는다.
    if not basic_response.is_success or basic_response.result is None:
        raise ListingUnavailableError('naver', article_number)
    return basic_response.result


def _jibun_address(
    client: NaverClient,
    key: NaverArticleKeyModel,
    article: NaverArticleDetailInfoModel | None,
    notes: list[str],
) -> str | None:
    """웹 위치 칸과 같게 만든 주소: article/key 의 법정동 코드로 받은 지역 이름 + 리 + 지번(보일 때만).

    웹은 좌표가 아니라 매물의 법정동 코드로 `legalDivision/infoList` 를 불러 `regionName` 을 얻고 `[regionName, address.li, 지번]` 을
    공백으로 잇는다 (지번을 붙일지는 아래 주석). 같은 방법을 쓰므로 경계 근처 매물에 옆 동 이름이 붙지 않고, 읍·면 매물의 리가 빠지지 않는다.
    article/key 에 주소나 법정동 코드가 없으면 None 이다 (요청 없음). 있으면 좌표와 상관없이 1회 요청한다. 조회가 실패하거나
    응답에 그 코드의 이름이 없으면 None 이고 `notes` 에 `[실패]` 안내가 붙는다.
    """
    address = key.address
    if address is None or not address.legal_division_number:
        return None
    unknown = '모름(null)으로 낸 칸: address'
    divisions = result_or_empty(
        lambda: client.run_request_legal_division_info_list_v1(
            NaverLegalDivisionInfoListV1RequestParameterModel(legal_division_numbers=address.legal_division_number)
        ),
        dict,
        notes=notes,
        what='지번 주소',
        unknown=unknown,
    )
    if divisions is None:
        return None
    division = divisions.get(address.legal_division_number)
    if division is None or not division.region_name:
        # 성공 응답인데 그 코드의 이름이 없다. 거절·형식 변경과 같게 알린다
        add_failure_note(notes, None, '지번 주소', unknown)
        return None
    # 주소에 지번을 붙일지. 웹 위치 칸(ArticleBuildingInfo, 번들 청크 0l4pkwg0qhg2t)과 같은 규칙이다.
    # `JIBUN_EXPOSURE_REAL_ESTATE_TYPES` 유형은 `isJibunAddressExposed` 를, 그 밖의 유형은 건물 세부 유형이 단독(C0301)일 때만 그 값을
    # 따르고 나머지는 늘 보인다. 상세(articleDetailInfo)나 `isJibunAddressExposed` 가 없으면 숨기는 쪽이고, 건물 세부 유형이 없으면 단독이 아니다.
    building_type = article.building_type if article else None
    jibun_shown = (
        (bool(article.is_jibun_address_exposed) if article else False)
        if key.type.real_estate_type in JIBUN_EXPOSURE_REAL_ESTATE_TYPES or building_type == JIBUN_EXPOSURE_BUILDING_TYPE
        else True
    )
    jibun = address.jibun if jibun_shown else None
    return normalize_address(join_address(division.region_name, address.li, jibun))
