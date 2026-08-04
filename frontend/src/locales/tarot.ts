/** TarotPage(타로) 문자열 카탈로그 — common.tarot 로 병합.
 * 카드명(name_kr/name_en)·포지션명(position_name)·방향(orientation)은 백엔드 산출값 → 그대로 렌더(별도 i18n 영역).
 * 표시 방향 라벨(정/역방향)만 upright/reversed 로 번역한다.
 */
export const tarotKo = {
  member_fallback: "회원",

  /* 섹션(백엔드 key)별 표시명 + 예시질문 5개(exs[0]은 placeholder 대표). */
  sec: {
    love: {
      nm: "연애 · 재회",
      exs: [
        "이번에 새로 만난 사람, 저와 잘 이어질까요?",
        "헤어진 그 사람과 다시 만날 가능성이 있을까요?",
        "지금 사귀는 사람과 결혼까지 갈 수 있을까요?",
        "그 사람은 지금 저를 어떻게 생각하고 있을까요?",
        "마음에 둔 상대에게 먼저 다가가도 될까요?",
      ],
    },
    money: {
      nm: "금전 · 재물",
      exs: [
        "지금 고민 중인 투자, 진행해도 괜찮을까요?",
        "올해 안에 목돈이 들어올 운이 있을까요?",
        "빌려준 돈을 돌려받을 수 있을까요?",
        "지금 시작하려는 부업, 수익이 날까요?",
        "집·차 같은 큰 지출, 지금 해도 될까요?",
      ],
    },
    career: {
      nm: "직업 · 사업",
      exs: [
        "준비 중인 이직, 올해 안에 결실이 있을까요?",
        "지금 회사에 남을까요, 옮기는 게 나을까요?",
        "새로 시작한 사업, 자리를 잡을 수 있을까요?",
        "곧 있을 승진·평가 결과가 좋을까요?",
        "지금 하는 일이 저와 잘 맞는 길일까요?",
      ],
    },
    study: {
      nm: "학업 · 시험",
      exs: [
        "이번 시험, 지금 방식대로 준비하면 합격할까요?",
        "어느 전공·진로가 저에게 맞을까요?",
        "자격증 공부, 올해 안에 마칠 수 있을까요?",
        "지금의 슬럼프를 어떻게 넘기면 좋을까요?",
        "유학·편입을 지금 준비해도 될까요?",
      ],
    },
    choice: {
      nm: "선택의 기로",
      exs: [
        "지금 사는 집을 팔까요, 계속 둘까요?",
        "A와 B 두 제안 중 어느 쪽을 택해야 할까요?",
        "이 관계를 정리할까요, 이어갈까요?",
        "낯선 곳으로 이사·이직을 결정해도 될까요?",
        "지금은 결정을 미룰까요, 밀어붙일까요?",
      ],
    },
    life: {
      nm: "인생 종합 · 심층",
      exs: [
        "지금 제 인생의 큰 흐름이 어디로 가고 있나요?",
        "올 한 해 제가 집중해야 할 것은 무엇일까요?",
        "요즘 반복되는 고민, 그 뿌리는 무엇일까요?",
        "제가 지금 놓치고 있는 기회가 있을까요?",
        "앞으로 1년, 제 삶의 가장 큰 변화는 무엇일까요?",
      ],
    },
  },

  sub_celtic: "켈틱 크로스 확장 · 11장",
  sub_horse: "말굽 스프레드 · 7장",
  spread_celtic: "켈틱 크로스 11장",
  spread_horse: "말굽 7장",

  /* 방향 표시 라벨 */
  upright: "정방향",
  reversed: "역방향",

  /* 에러·안내(alert/confirm/openCharge/setErr) */
  del_confirm: "이 타로 상담 기록을 삭제할까요?",
  del_fail: "삭제에 실패했어요. 잠시 후 다시 시도해 주세요.",
  charge_entry: "타로 입장 포인트가 부족해요. 충전하면 작성 내용 그대로 이어집니다.",
  charge_followup: "추가 질문 포인트가 부족해요. 충전하면 작성 내용 그대로 이어집니다.",
  sessions_full: "저장된 타로 기록이 최대 {{max}}개에 도달했어요.\n왼쪽 ‘내 기록’에서 오래된 기록을 삭제한 뒤 다시 시도해 주세요.\n(기록은 최대 1주간 보관됩니다.)",
  create_fail: "타로 세션을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.",
  picks_fail: "카드 확정에 실패했어요.",
  answer_fail: "답변 생성에 실패했어요. 잠시 후 다시 시도해 주세요.",

  /* PDF 헤더 */
  pdf_q: "[질문] {{q}}",
  pdf_spread: "[스프레드] {{spread}} ({{sec}})",
  pdf_card: "{{n}}. {{pos}}: {{kr}} ({{en}}) · {{ori}}",

  /* 추가 질문 요금 안내(feeNote) */
  fee_guest: "※ 로그인 후 추가 질문을 이용할 수 있어요 (1일 무료 또는 포인트 차감)",
  fee_free: "※ 이번 추가 질문 무료 · 남은 무료 {{n}}회",
  fee_paid: "※ 추가 질문은 기본 {{basic}}{{pt}} · 심화 {{deep}}{{pt}} 차감 · 잔액 {{bal}}{{pt}}",

  /* 좌측 플로팅 + 기록 서랍 */
  float_new: "✦ 새롭게 타로보기",
  float_new_title: "새 타로 리딩 시작(입장료는 카드 섞기 때 차감)",
  float_hist: "🕮 내 기록",
  float_hist_title: "내 타로 상담 기록",
  drawer_title: "내 타로 기록",
  drawer_close: "닫기",
  drawer_note: "🕰 타로 상담 기록은 <b>최대 1주간</b> 보관됩니다.",
  drawer_empty: "아직 저장된 타로 기록이 없어요.",
  sess_pending: "· 해석 전",
  sess_del: "삭제",

  /* 헤더 */
  brand_sub: "미드나잇 골드 아틀리에 · 타로",
  steps: ["질문", "셔플", "뽑기", "리딩"],
  steps_aria: "진행 단계",

  /* 보관 안내 */
  storenote_in: "🕰 타로 상담 기록은 최대 1주간 보관되며, 최대 20개까지 저장됩니다. 왼쪽 위 ‘내 기록’에서 다시 볼 수 있어요.",
  storenote_guest: "🔒 로그인하지 않으면 이 기기에서만 임시 보관되어, 기기를 바꾸거나 브라우저를 정리하면 기록이 사라집니다. 로그인하면 최대 1주간 안전하게 보관됩니다.",

  /* 1. 질문 */
  q_h2: "어떤 이야기가 궁금하신가요?",
  q_sub: "신중히 고민하고 질문을 입력하세요. 질문에 따라 상담 내용이 달라집니다.",
  examples_label: "💡 {{sec}} — 이런 질문이 잘 통해요",
  q_ph_nudge: "질문을 먼저 입력해 주세요",
  q_ph_sec: "예) {{ex}}",
  q_ph_default: "예) 지금 준비 중인 이직, 올해 안에 결실이 있을까요?",
  q_aria: "질문 입력",
  cta_prep: "준비 중…",
  cta_shuffle: "카드 섞기 →",

  /* 2. 셔플 */
  shuf_h2: "카드를 섞고 있습니다",
  shuf_sub: "마음속으로 질문을 한 번 더 떠올려 주세요.",
  shuf_q: "질문",

  /* 3·4. 테이블 */
  table_pick: "왼손으로, 끌리는 카드를 뽑아주세요",
  table_flip: "이제, 한 장씩 직접 뒤집어 주세요",
  table_done: "카드가 전하는 이야기입니다",
  pickbar: "일흔여덟 장 가운데 <b>{{n}}</b>장 — 카드에 손을 얹으면 살짝 떠오르고, 누르면 아래 자리로 내려앉습니다.",
  pick_count: "뽑은 카드",
  retry: "다시 시도",
  spreadhint_flip: "카드를 누르면 뒤집힙니다 · <b>{{n}}</b>장 남음",
  spreadhint_confirm: "카드를 확정하는 중…",
  flip_aria: "{{n}}번 카드 뒤집기",

  /* 5. 해석(리딩) */
  reading_sub: "카드가 전하는 이야기",
  reading_qecho: "질문 — {{q}}  ({{sec}} · {{spread}})",
  reading_loading: "해석을 불러오는 중…",
  refining_tag: "✨ 보강 중…",
  reading_fail: "해석 생성에 실패했어요. 네트워크나 서버 사정일 수 있어요.",
  retry_free: "다시 시도 (무과금)",
  pdf_doc: "{{name}} 님의 타로 리딩",
  pdf_item_q: "타로 추가 질문",
  pdf_person: "{{name}} 님",
  pdf_item: "타로 리딩 ({{sec}})",
  qa_refined: "✨ 보강됨",
  qa_charged: "✓ {{n}}{{pt}} 차감됨",
  suggest_more: "💡 이어서 물어보세요",
  followup_ph: "이어서 궁금한 점을 물어보세요…",
  followup_aria: "추가 질문",
  q_basic_title: "기본 질문 · {{n}}{{pt}}",
  q_basic: "기본 질문 {{n}}{{pt}}",
  q_deep_title: "심화 질문 · {{n}}{{pt}}",
  q_deep: "심화 질문 {{n}}{{pt}}",
  restart: "↺ 새 리딩 시작",

  /* 저작권 고지 */
  legal: `<b>저작권 고지</b> — 본 서비스의 타로 카드 이미지는 라이더-웨이트-스미스(Rider-Waite-Smith) 타로 원판(1909년, 아서 E. 웨이트 기획 · 파멜라 콜먼 스미스 작화, 윌리엄 라이더 앤 선 출판)을 기반으로 자체 보정·가공한 것입니다. 해당 원판은 전 세계 대부분 지역에서 퍼블릭 도메인(공유 저작물)입니다. "Rider-Waite", "Universal Waite" 등의 명칭은 U.S. Games Systems, Inc.의 상표일 수 있으며, 본 서비스는 U.S. Games Systems, Inc.와 무관하고 제휴·후원·승인 관계가 없습니다. 타로 콘텐츠는 참고 및 오락 목적으로 제공됩니다.`,
};

export const tarotVi: typeof tarotKo = {
  member_fallback: "Quý khách",

  sec: {
    love: {
      nm: "Tình duyên · Nối lại",
      exs: [
        "Người tôi mới quen liệu có tiến xa được với tôi không?",
        "Tôi có khả năng gặp lại và nối lại với người cũ không?",
        "Tôi và người đang yêu có thể đi đến hôn nhân không?",
        "Bây giờ người ấy đang nghĩ về tôi như thế nào?",
        "Tôi có nên chủ động đến với người mình thầm thương không?",
      ],
    },
    money: {
      nm: "Tiền bạc · Tài lộc",
      exs: [
        "Khoản đầu tư tôi đang cân nhắc, có nên tiến hành không?",
        "Trong năm nay tôi có vận đón được khoản tiền lớn không?",
        "Tôi có đòi lại được khoản tiền đã cho vay không?",
        "Nghề tay trái tôi định bắt đầu có sinh lời không?",
        "Khoản chi lớn như mua nhà·xe, lúc này tôi có nên chi không?",
      ],
    },
    career: {
      nm: "Nghề nghiệp · Kinh doanh",
      exs: [
        "Việc chuyển việc tôi đang chuẩn bị có kết quả trong năm nay không?",
        "Tôi nên ở lại công ty hiện tại hay chuyển đi thì hơn?",
        "Việc kinh doanh mới bắt đầu có trụ vững được không?",
        "Kết quả thăng chức·đánh giá sắp tới của tôi có tốt không?",
        "Công việc hiện tại có hợp với con đường của tôi không?",
      ],
    },
    study: {
      nm: "Học hành · Thi cử",
      exs: [
        "Kỳ thi này, cứ ôn theo cách hiện tại thì tôi có đỗ không?",
        "Ngành học·hướng đi nào hợp với tôi?",
        "Việc học chứng chỉ tôi có hoàn thành trong năm nay không?",
        "Tôi nên vượt qua giai đoạn sa sút này bằng cách nào?",
        "Lúc này tôi có nên chuẩn bị du học·chuyển trường không?",
      ],
    },
    choice: {
      nm: "Ngã rẽ lựa chọn",
      exs: [
        "Tôi nên bán căn nhà đang ở hay cứ giữ tiếp?",
        "Giữa hai đề nghị A và B, tôi nên chọn bên nào?",
        "Mối quan hệ này tôi nên chấm dứt hay tiếp tục?",
        "Tôi có nên quyết định chuyển nhà·đổi việc đến nơi xa lạ không?",
        "Lúc này nên hoãn quyết định lại hay dứt khoát tiến tới?",
      ],
    },
    life: {
      nm: "Tổng quan cuộc đời · Chuyên sâu",
      exs: [
        "Dòng chảy lớn của đời tôi lúc này đang đi về đâu?",
        "Năm nay điều tôi cần tập trung nhất là gì?",
        "Nỗi lo cứ lặp lại gần đây, gốc rễ của nó là gì?",
        "Có cơ hội nào tôi đang bỏ lỡ mà không hay không?",
        "Một năm tới, thay đổi lớn nhất trong đời tôi là gì?",
      ],
    },
  },

  sub_celtic: "Celtic Cross mở rộng · 11 lá",
  sub_horse: "Trải Móng ngựa · 7 lá",
  spread_celtic: "Celtic Cross 11 lá",
  spread_horse: "Móng ngựa 7 lá",

  upright: "Xuôi",
  reversed: "Ngược",

  del_confirm: "Bạn có muốn xóa bản ghi tư vấn Tarot này không?",
  del_fail: "Xóa thất bại. Vui lòng thử lại sau.",
  charge_entry: "Bạn không đủ điểm để vào Tarot. Nạp điểm để tiếp tục ngay với nội dung đang soạn.",
  charge_followup: "Bạn không đủ điểm để hỏi thêm. Nạp điểm để tiếp tục ngay với nội dung đang soạn.",
  sessions_full: "Bản ghi Tarot đã lưu đã đạt mức tối đa {{max}}.\nHãy xóa bớt bản ghi cũ trong ‘Bản ghi của tôi’ (góc trên bên trái) rồi thử lại.\n(Bản ghi được lưu tối đa 1 tuần.)",
  create_fail: "Không thể bắt đầu phiên Tarot. Vui lòng thử lại sau.",
  picks_fail: "Xác nhận lá bài thất bại.",
  answer_fail: "Tạo câu trả lời thất bại. Vui lòng thử lại sau.",

  pdf_q: "[Câu hỏi] {{q}}",
  pdf_spread: "[Trải bài] {{spread}} ({{sec}})",
  pdf_card: "{{n}}. {{pos}}: {{kr}} ({{en}}) · {{ori}}",

  fee_guest: "※ Đăng nhập để có thể hỏi thêm (miễn phí 1 lần/ngày hoặc trừ điểm)",
  fee_free: "※ Câu hỏi thêm lần này miễn phí · Còn {{n}} lần miễn phí",
  fee_paid: "※ Hỏi thêm sẽ trừ: cơ bản {{basic}} {{pt}} · chuyên sâu {{deep}} {{pt}} · Số dư {{bal}} {{pt}}",

  float_new: "✦ Xem Tarot mới",
  float_new_title: "Bắt đầu lượt Tarot mới (phí vào cửa trừ khi xáo bài)",
  float_hist: "🕮 Bản ghi của tôi",
  float_hist_title: "Bản ghi tư vấn Tarot của tôi",
  drawer_title: "Bản ghi Tarot của tôi",
  drawer_close: "Đóng",
  drawer_note: "🕰 Bản ghi tư vấn Tarot được lưu <b>tối đa 1 tuần</b>.",
  drawer_empty: "Chưa có bản ghi Tarot nào được lưu.",
  sess_pending: "· Chưa luận giải",
  sess_del: "Xóa",

  brand_sub: "Midnight Gold Atelier · Tarot",
  steps: ["Câu hỏi", "Xáo bài", "Rút bài", "Luận giải"],
  steps_aria: "Các bước tiến hành",

  storenote_in: "🕰 Bản ghi tư vấn Tarot được lưu tối đa 1 tuần và tối đa 20 bản. Bạn có thể xem lại ở ‘Bản ghi của tôi’ góc trên bên trái.",
  storenote_guest: "🔒 Nếu không đăng nhập, bản ghi chỉ lưu tạm trên thiết bị này; đổi máy hoặc dọn trình duyệt sẽ mất. Đăng nhập để lưu an toàn tối đa 1 tuần.",

  q_h2: "Bạn đang băn khoăn điều gì?",
  q_sub: "Hãy suy nghĩ thật kỹ rồi nhập câu hỏi. Nội dung luận giải sẽ thay đổi theo câu hỏi của bạn.",
  examples_label: "💡 {{sec}} — những câu hỏi kiểu này rất hợp",
  q_ph_nudge: "Vui lòng nhập câu hỏi trước",
  q_ph_sec: "VD) {{ex}}",
  q_ph_default: "VD) Việc chuyển việc đang chuẩn bị có kết quả trong năm nay không?",
  q_aria: "Nhập câu hỏi",
  cta_prep: "Đang chuẩn bị…",
  cta_shuffle: "Xáo bài →",

  shuf_h2: "Đang xáo bài",
  shuf_sub: "Hãy thầm nhắc lại câu hỏi trong lòng một lần nữa.",
  shuf_q: "Câu hỏi",

  table_pick: "Hãy dùng tay trái rút lá bài mà bạn thấy cuốn hút",
  table_flip: "Giờ hãy tự lật từng lá một",
  table_done: "Đây là câu chuyện lá bài muốn kể",
  pickbar: "Trong 78 lá, hãy chọn <b>{{n}}</b> lá — đặt tay lên lá bài nó sẽ khẽ nổi lên, nhấn vào thì lá hạ xuống vị trí bên dưới.",
  pick_count: "Lá đã rút",
  retry: "Thử lại",
  spreadhint_flip: "Nhấn vào lá bài để lật · còn <b>{{n}}</b> lá",
  spreadhint_confirm: "Đang xác nhận lá bài…",
  flip_aria: "Lật lá bài số {{n}}",

  reading_sub: "Câu chuyện mà lá bài muốn kể",
  reading_qecho: "Câu hỏi — {{q}}  ({{sec}} · {{spread}})",
  reading_loading: "Đang tải luận giải…",
  refining_tag: "✨ Đang bổ trợ…",
  reading_fail: "Tạo luận giải thất bại. Có thể do mạng hoặc máy chủ.",
  retry_free: "Thử lại (miễn phí)",
  pdf_doc: "Bản luận Tarot của {{name}}",
  pdf_item_q: "Câu hỏi thêm Tarot",
  pdf_person: "{{name}}",
  pdf_item: "Luận giải Tarot ({{sec}})",
  qa_refined: "✨ Đã bổ trợ",
  qa_charged: "✓ Đã trừ {{n}} {{pt}}",
  suggest_more: "💡 Hỏi tiếp",
  followup_ph: "Hỏi tiếp điều bạn còn thắc mắc…",
  followup_aria: "Câu hỏi thêm",
  q_basic_title: "Câu hỏi cơ bản · {{n}} {{pt}}",
  q_basic: "Câu hỏi cơ bản {{n}} {{pt}}",
  q_deep_title: "Câu hỏi chuyên sâu · {{n}} {{pt}}",
  q_deep: "Câu hỏi chuyên sâu {{n}} {{pt}}",
  restart: "↺ Bắt đầu lượt xem mới",

  legal: `<b>Thông báo bản quyền</b> — Hình ảnh lá bài Tarot của dịch vụ này được chỉnh sửa·gia công lại từ bộ bài gốc Rider-Waite-Smith (năm 1909, do Arthur E. Waite biên soạn · Pamela Colman Smith minh họa, William Rider & Son xuất bản). Bộ bài gốc thuộc phạm vi công cộng (public domain) ở hầu hết các khu vực trên thế giới. Các tên gọi như "Rider-Waite", "Universal Waite" có thể là thương hiệu của U.S. Games Systems, Inc.; dịch vụ này không liên quan và không có quan hệ hợp tác·tài trợ·chứng thực với U.S. Games Systems, Inc. Nội dung Tarot được cung cấp nhằm mục đích tham khảo và giải trí.`,
};
