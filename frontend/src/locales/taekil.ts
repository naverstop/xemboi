/** TaekilPage(택일) 문자열 카탈로그 — common.taekil 로 병합.
 * 등급(d.grade)·황도흑도·건제십이신·이십팔수·생기복덕(saenggi)·간지·일지 등은
 * 백엔드 산출값이라 별도(백엔드 i18n 영역). 여기선 프론트 UI 문구만 담는다.
 */
export const taekilKo = {
  // 히어로
  hero_title: "택일",
  hero_desc: "황도흑도·건제십이신·이십팔수·생기복덕·사주 조화·손없는날을 <b>용도별 비중</b>으로 가중해 가립니다. 관법은 정답이 없어 <b>세 관점</b>의 추천 1위도 함께 보여드려요.",
  // 용도 선택
  label_purpose: "용도",
  aria_purpose: "택일 용도",
  birth_hint: "아래 입력하신 분(부모)을 기준으로, 그날 태어날 <b>아이의 사주와 부모의 궁합</b>이 좋은 날을 찾아드려요.",
  // 용도별 한 줄 설명
  desc_wedding: "혼례에 좋은 날 — 본인 사주의 충·형 회피를 가장 중시하고, 황도길일·손없는날을 함께 반영합니다.",
  desc_birth: "그날 태어날 아이의 사주와 부모(입력자)의 궁합을 가장 중시합니다.",
  desc_moving: "이사·입택에 좋은 날 — 손없는날을 가장 중시하고, 황도길일·사주를 함께 반영합니다.",
  desc_opening: "개업에 좋은 날 — 황도길일과 손없는날을 같은 비중으로 중시합니다.",
  desc_contract: "계약·서명에 좋은 날 — 본인 사주의 충·형 회피와 황도길일을 함께 중시합니다.",
  desc_ceremony: "고사·제사에 좋은 날 — 황도길일을 가장 중시하고, 사주 조화를 함께 봅니다.",
  desc_surgery: "수술·시술에 좋은 날 — 본인 사주의 충·형 회피를 가장 중시하고, 황도길일을 함께 봅니다.",
  desc_travel: "여행·출행에 좋은 날 — 황도길일을 가장 중시하고, 사주 조화를 함께 봅니다.",
  desc_general: "일반 길일 — 황도길일·사주·손없는날을 고루 반영합니다.",
  // 부모(출산)
  parent1: "부모 ①",
  parent2: "부모 ②",
  parent2_opt: "(선택 — 입력 시 두 분 모두와의 궁합으로 가립니다)",
  // 검색 기간
  label_period: "검색 기간",
  days_opt: "{{n}}일",
  // 액션
  analyzing: "분석 중…",
  cta: "📅 길일 찾기",
  cta_hint: "본인 생년월일을 입력해 주세요",
  fail: "택일에 실패했어요.",
  // 결과
  parent: "부모",
  self: "본인",
  day_branch: "{{who}} 일지 {{branch}}",
  recommended: "추천 길일",
  saenggi_title: "생기복덕(본명괘 기준)",
  sonless: "손없는날",
  score_grade: "{{score}}점 · {{grade}}",
  best_hours_title: "아이-부모 궁합이 좋은 시(時)",
  persp_title: "관법별 추천 1위",
  persp_sub: "(정답 없음 — 세 관점)",
  persp_meta: "{{ganzhi}} · {{score}}점",
  avoid_title: "피하면 좋은 날",
  // PDF/상담서
  visitor: "접속자",
  pdf_doc: "{{who}} 님이 확인한 택일",
  pdf_person: "{{who}} 님",
  pdf_item: "{{label}} 택일",
  pdf_header_title: "[추천 길일]",
  pdf_line: "- {{date}} ({{ganzhi}}) · {{score}}점 · {{grade}}",
};

export const taekilVi: typeof taekilKo = {
  // 히어로
  hero_title: "Chọn ngày tốt",
  hero_desc: "Chúng tôi cân nhắc hoàng đạo/hắc đạo · Kiến trừ thập nhị thần · Nhị thập bát tú · Sinh khí phúc đức · sự hòa hợp Tứ Trụ · ngày không sát chủ theo <b>trọng số từng mục đích</b> để chọn ngày. Mệnh lý không có đáp án tuyệt đối nên chúng tôi cũng cho bạn xem đề xuất số 1 theo <b>ba góc nhìn</b>.",
  // 용도 선택
  label_purpose: "Mục đích",
  aria_purpose: "Mục đích chọn ngày",
  birth_hint: "Dựa trên người (cha/mẹ) bạn nhập bên dưới, chúng tôi tìm ngày tốt về <b>sự hợp tuổi giữa lá số của con sinh ngày đó và cha mẹ</b>.",
  // 용도별 한 줄 설명
  desc_wedding: "Ngày tốt để cưới hỏi — ưu tiên nhất việc tránh xung·hình trong lá số của bạn, đồng thời cân nhắc ngày hoàng đạo·ngày không sát chủ.",
  desc_birth: "Ưu tiên nhất sự hợp tuổi giữa lá số của con sinh ngày đó và cha mẹ (người nhập).",
  desc_moving: "Ngày tốt để chuyển nhà·nhập trạch — ưu tiên nhất ngày không sát chủ, đồng thời cân nhắc ngày hoàng đạo·Tứ Trụ.",
  desc_opening: "Ngày tốt để khai trương — coi trọng ngang nhau ngày hoàng đạo và ngày không sát chủ.",
  desc_contract: "Ngày tốt để ký kết·ký tên — coi trọng cả việc tránh xung·hình trong lá số của bạn và ngày hoàng đạo.",
  desc_ceremony: "Ngày tốt để cúng tế — ưu tiên nhất ngày hoàng đạo, đồng thời xét sự hòa hợp Tứ Trụ.",
  desc_surgery: "Ngày tốt để phẫu thuật·tiểu phẫu — ưu tiên nhất việc tránh xung·hình trong lá số của bạn, đồng thời xét ngày hoàng đạo.",
  desc_travel: "Ngày tốt để du lịch·xuất hành — ưu tiên nhất ngày hoàng đạo, đồng thời xét sự hòa hợp Tứ Trụ.",
  desc_general: "Ngày tốt chung — cân nhắc đều ngày hoàng đạo·Tứ Trụ·ngày không sát chủ.",
  // 부모(출산)
  parent1: "Cha mẹ ①",
  parent2: "Cha mẹ ②",
  parent2_opt: "(tùy chọn — nếu nhập, chọn ngày theo sự hợp tuổi với cả hai người)",
  // 검색 기간
  label_period: "Khoảng thời gian tìm",
  days_opt: "{{n}} ngày",
  // 액션
  analyzing: "Đang phân tích…",
  cta: "📅 Tìm ngày tốt",
  cta_hint: "Vui lòng nhập ngày sinh của bạn",
  fail: "Chọn ngày thất bại.",
  // 결과
  parent: "Cha mẹ",
  self: "Bản thân",
  day_branch: "Địa chi ngày {{branch}} ({{who}})",
  recommended: "Ngày tốt đề xuất",
  saenggi_title: "Sinh khí phúc đức (theo bản mệnh quái)",
  sonless: "Ngày không sát chủ",
  score_grade: "{{score}} điểm · {{grade}}",
  best_hours_title: "Giờ (時) hợp giữa con và cha mẹ",
  persp_title: "Đề xuất số 1 theo trường phái",
  persp_sub: "(không tuyệt đối — ba góc nhìn)",
  persp_meta: "{{ganzhi}} · {{score}} điểm",
  avoid_title: "Ngày nên tránh",
  // PDF/상담서
  visitor: "khách",
  pdf_doc: "Chọn ngày của {{who}}",
  pdf_person: "{{who}}",
  pdf_item: "Chọn ngày {{label}}",
  pdf_header_title: "[Ngày tốt đề xuất]",
  pdf_line: "- {{date}} ({{ganzhi}}) · {{score}} điểm · {{grade}}",
};
