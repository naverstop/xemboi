/** CalendarPage(운세 캘린더) 문자열 카탈로그 — common.fcal 로 병합.
 * 간지(d.ganzhi)·절기(d.jieqi)·경고(d.warnings)·res.note 는 백엔드 산출값 → 그대로 렌더(백엔드 i18n 영역).
 * 등급(d.grade)은 백엔드가 ko 값("대길/길/평/흉")을 내보내므로 표시용 매핑(grade_*)만 프론트에서 번역한다
 * (색상 맵 키는 백엔드 값 그대로 유지). ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 */
export const fcalKo = {
  // 등급 표시 라벨(백엔드 ko 값 → 표시명. ko 는 항등)
  grade_daegil: "대길",
  grade_gil: "길",
  grade_pyeong: "평",
  grade_hyung: "흉",

  // 복사/공유/PDF 직렬화(monthText)
  txt_title: "[운세 캘린더] {{y}}년 {{m}}월 — 일별 일진·길흉",
  txt_day: "{{d}}일 {{ganzhi}} · {{grade}} {{score}}점",
  txt_jieqi: "절기 {{j}}",
  sonless: "손없는날",

  // 히어로
  hero_badge: "曆",
  hero_title: "운세 캘린더",
  hero_desc: "한 달의 <b>일진(日辰)</b>과 내 사주 기준 <b>길흉</b>을 한눈에 봐요. 손없는날·절기·충형해 경고까지 표시해 드려요. <b>무료</b>입니다.",

  // 조회 CTA
  loading: "계산 중…",
  cta: "📅 이번 달 운세 보기 (무료)",
  cta_hint: "생년월일을 입력해 주세요",
  load_fail: "캘린더를 불러오지 못했어요.",

  // 월 내비게이션·범례·요일(weekdays 는 콤마 구분 7개, 일요일 시작)
  prev_month: "이전 달",
  next_month: "다음 달",
  ym: "{{y}}년 {{m}}월",
  son_marker: "손",
  legend_warn: "⚡ 충·형·해",
  weekdays: "일,월,화,수,목,금,토",

  // 선택일 상세
  detail_date: "{{m}}월 {{d}}일 · {{ganzhi}}",
  score_grade: "{{grade}} {{score}}점",
  jieqi_label: "🌱 절기",
  sonless_note: "🏠 손없는날 — 이사·이동에 부담 없는 날로 봐요",
  warn_note: "⚡ 내 사주와 {{list}} — 큰 결정은 신중히",
  no_conflict: "😊 내 사주와 특별한 충돌이 없어요",
  taekil_link: "🎯 결혼·이사 등 목적별 정밀 택일 보러 가기 →",

  // PDF/상담서
  pdf_doc: "{{who}} 님의 {{y}}년 {{m}}월 운세 캘린더",
  pdf_person: "{{who}} 님",
  pdf_item: "운세 캘린더(월별 일진)",
};

export const fcalVi: typeof fcalKo = {
  // 등급 표시 라벨
  grade_daegil: "Đại cát",
  grade_gil: "Cát",
  grade_pyeong: "Bình",
  grade_hyung: "Hung",

  // 복사/공유/PDF 직렬화
  txt_title: "[Lịch vận trình] Tháng {{m}}/{{y}} — nhật thần·cát hung từng ngày",
  txt_day: "Ngày {{d}} {{ganzhi}} · {{grade}} {{score}} điểm",
  txt_jieqi: "Tiết khí {{j}}",
  sonless: "Ngày không sát chủ",

  // 히어로
  hero_badge: "📆",
  hero_title: "Lịch vận trình",
  hero_desc: "Xem trong một tháng <b>nhật thần</b> từng ngày và <b>cát hung</b> theo lá số của bạn. Hiển thị cả ngày không sát chủ·tiết khí·cảnh báo xung hình hại. <b>Miễn phí</b>.",

  // 조회 CTA
  loading: "Đang tính…",
  cta: "📅 Xem vận tháng này (miễn phí)",
  cta_hint: "Vui lòng nhập ngày sinh của bạn",
  load_fail: "Không tải được lịch.",

  // 월 내비게이션·범례·요일
  prev_month: "Tháng trước",
  next_month: "Tháng sau",
  ym: "Tháng {{m}}/{{y}}",
  son_marker: "S",
  legend_warn: "⚡ Xung·hình·hại",
  weekdays: "CN,T2,T3,T4,T5,T6,T7",

  // 선택일 상세
  detail_date: "Ngày {{d}}/{{m}} · {{ganzhi}}",
  score_grade: "{{grade}} {{score}} điểm",
  jieqi_label: "🌱 Tiết khí",
  sonless_note: "🏠 Ngày không sát chủ — được xem là ngày thuận lợi cho chuyển nhà·di chuyển",
  warn_note: "⚡ {{list}} với lá số của bạn — hãy thận trọng với quyết định lớn",
  no_conflict: "😊 Không có xung khắc đặc biệt với lá số của bạn",
  taekil_link: "🎯 Xem chọn ngày chính xác theo mục đích như cưới hỏi·chuyển nhà →",

  // PDF/상담서
  pdf_doc: "Lịch vận trình tháng {{m}}/{{y}} của {{who}}",
  pdf_person: "{{who}}",
  pdf_item: "Lịch vận trình (nhật thần theo tháng)",
};
