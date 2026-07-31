// 이중 로케일(ko/vi) i18n 초기화 — react-i18next.
// ko 사이트(saju.songstock.art)=ko 기본(현행 불변) / vi 사이트(xemboi.io)=vi 기본.
//   VN 빌드는 VITE_DEFAULT_LOCALE=vi 로 오버라이드. 기본 'ko'라 한국 서비스 불변.
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { chatKo, chatVi } from "./locales/chat";

export const SUPPORTED = ["ko", "vi"] as const;
export type Locale = (typeof SUPPORTED)[number];

const DEFAULT_LOCALE =
  ((import.meta as any).env?.VITE_DEFAULT_LOCALE as string | undefined) || "ko";

// VN 배포(xemboi) 빌드 여부(빌드타임 상수). 작명/개명/아호 등 'VN 미지원 기능' 게이팅 +
// 언어 스위치 노출에 사용. 한국(ko) 빌드에선 false → 사주1 UI/기능 완전 불변.
export const IS_VN_BUILD = DEFAULT_LOCALE === "vi";

// 문자열 카탈로그(common 네임스페이스). 점진 확장 — 지금은 브랜드/셸 핵심부터.
// vi 번역은 1차안 — 도메인/자연스러움은 베트남 원어민 검수 권장(특히 사주 용어).
const resources = {
  ko: {
    common: {
      brand: "인생상담 친구",
      nav: {
        new_consult: "새 상담", consult: "상담", compat: "궁합", taekil: "택일",
        jakmyeong: "작명", gaemyeong: "개명", aho: "아호", tarot: "타로", charge: "충전",
        settings: "설정", consultant_console: "상담사 콘솔", uploads: "업로드",
        trend: "평가 추세", admin: "관리자", support: "고객센터",
        login: "로그인", logout: "로그아웃", withdraw: "탈퇴",
      },
      theme: { dark: "다크", light: "라이트" },
      landing: {
        eyebrow: "사주·명리 AI",
        hero_title: "사주로 풀어보는 나의 길",
        hero_sub: "상담·궁합·택일·작명까지. 명리 규칙과 AI가 근거와 함께 풀어드려요. 아래에서 원하는 기능을 골라보세요.",
        hero_cta: "무료로 시작하기",
        bottom_cta: "지금 무료로 시작해 보세요",
        band_sub: "비로그인 미리보기로 먼저 확인하고, 로그인하면 무료 질문을 받을 수 있어요.",
        band_btn: "사주 상담 시작",
        fee_enter: "💎 입장", fee_extra: "· 추가 질문 별도", fee_free: "🆓 무료로 시작",
        note_in: "✨ 로그인 완료 — 진태양시 정밀 보정·전체 해설·이어지는 질문까지 <b>모든 기능을 100% 이용</b> 중이에요.",
        note_guest: "비로그인은 <b>50% 미리보기</b>만 제공해요. <b>로그인</b>하시면 진태양시 정밀 보정·전체 해설·무료 질문 등 <b>본 사이트만의 차별화 기능을 100%</b> 이용할 수 있어요.",
        faq_title: "자주 묻는 질문",
        faq: [
          { q: "정확한가요?", a: "합·충·오행·십성·신살을 규칙으로 계산한 근거에 AI 해설을 더합니다. 관법은 정답이 없어 여러 관점을 함께 보여드립니다." },
          { q: "무료인가요?", a: "비로그인은 답변의 50% 미리보기를 제공하고, 로그인하면 무료 질문과 전체 보기를 이용할 수 있어요." },
          { q: "태어난 시를 몰라요.", a: "‘시 모름’으로도 분석할 수 있어요(시주 제외)." },
        ],
        card: {
          sang: { badge: "사주 상담", title: "내 사주, AI에게 묻다",
            desc: "생년월일만 넣으면 성격·운세·올해의 흐름까지 1:1로 풀어드려요.",
            bullets: ["명식·오행 근거 기반 풀이", "이어지는 추가 질문", "초보도 쉬운 풀이 모드"], cta: "무료 사주상담 시작" },
          gunghap: { badge: "궁합", title: "두 사람의 인연을 사주로",
            desc: "두 사주를 합·충·오행·신살로 비교해 궁합 점수와 해설을 보여드려요.",
            bullets: ["펜타곤 시각화", "정답 없는 다관법 제시", "전체 평균과 비교"], cta: "궁합 보기" },
          taekil: { badge: "택일", title: "좋은 날을 가리다",
            desc: "혼인·이사·개업·계약… 목적에 맞는 길일을 기간에서 골라드려요.",
            bullets: ["황도흑도·건제십이신", "내 사주와 충·형 회피", "관법별 추천 1위 비교"], cta: "택일 하기" },
          tarot: { badge: "타로", title: "카드가 전하는 오늘의 답",
            desc: "78장 가운데 직접 뽑은 카드로 연애·재물·선택의 갈림길을 읽어드려요.",
            bullets: ["말굽 7장 · 켈틱 크로스 11장", "직접 뽑는 카드, 정·역방향", "포지션별 해석과 구체적 조언"], cta: "타로 보기" },
        },
      },
      auth: {
        sub_inline: "로그인하면 전체 답변과 무료 질문을 받을 수 있어요",
        sub_page: "나의 사주를 묻고, 매일의 운을 읽다",
        tab_login: "로그인", tab_register: "회원가입",
        notice_expired: "로그인 세션이 만료되어 로그아웃되었습니다. 다시 로그인해 주세요.",
        notice_idle: "오랫동안 활동이 없어 자동 로그아웃되었습니다. 다시 로그인해 주세요.",
        must_change_pw: "관리자 초기 비밀번호입니다. 비밀번호를 변경하세요.",
        err_agree: "필수 약관 및 면책고지에 모두 동의해야 합니다.",
        err_birth: "생년월일을 입력해 주세요.",
        welcome: "가입을 환영합니다! 가입 보너스가 지급되었습니다.",
        fail_login: "로그인 실패", fail_register: "가입 실패", fail_oauth: "{{provider}} 로그인 실패",
        email: "이메일", password: "비밀번호",
        nickname: "닉네임 (선택)", nickname_ph: "표시할 이름",
        pw_ph_register: "8자 이상 입력", pw_ph_login: "비밀번호",
        birth: "생년월일 (만 {{age}}세 이상)",
        agree_all: "전체 동의", agree_all_sub: "(필수 및 선택 항목 모두 포함)",
        req: "필수", opt: "선택",
        agree_terms: "<a>이용약관</a>에 동의합니다.",
        agree_privacy: "<a>개인정보 수집·이용</a>에 동의합니다.",
        summary_open: "요약 보기", summary_close: "요약 접기",
        sum_items_label: "수집 항목",
        sum_items: "이메일·비밀번호(암호화)·생년월일(암호화), 사주 입력값·상담 내용, 결제 내역, 접속 기록",
        sum_purpose_label: "이용 목적",
        sum_purpose: "회원 식별·사주 풀이 제공·결제/포인트 운영·문의 대응·법령 준수",
        sum_retention_label: "보유 기간",
        sum_retention: "회원 탈퇴 시 지체 없이 파기(전자상거래법 등 법정 보존 항목 제외)",
        sum_note: "동의를 거부할 수 있으나, 필수 항목 미동의 시 회원가입이 제한됩니다.",
        agree_refund: "<a>환불·청약철회 정책</a>에 동의합니다.",
        agree_disclaimer: "<a>면책고지</a>를 확인하였으며 이에 동의합니다.",
        agree_marketing: "이벤트·혜택 등 <b>광고성 정보 수신</b>에 동의합니다.",
        agree_marketing_sub: "(미동의해도 가입·이용 가능)",
        agree_foot: "만 {{age}}세 이상만 가입할 수 있으며, 가입 시 위 필수 항목에 동의한 것으로 봅니다.",
        submit_busy: "처리 중...", submit_login: "로그인", submit_register: "가입하기",
        oauth_divider: "또는 간편 로그인",
        oauth_kakao: "카카오로 시작", oauth_google: "구글로 시작", oauth_facebook: "페이스북으로 시작",
        foot_disclaimer: "면책고지",
      },
      pay: {
        pt: "P",
        charge_title: "크레딧 충전",
        rate_note: "1 P = 1원 · 충전하면 광고가 숨겨집니다",
        processing: "처리중...", charge_btn: "충전",
        login_required: "결제는 로그인 후 이용하세요.", login_link: "로그인",
        test_done: "[테스트모드] {{label}} 충전 완료\n+{{credits}} P → 잔액 {{balance}} P",
        history_title: "결제 내역",
        th_order: "주문번호", th_amount: "금액", th_credit: "크레딧", th_status: "상태", th_time: "시각",
        modal_title: "⚡ 포인트 충전", aria_charge: "포인트 충전", cur_balance: "현재 잔액", close: "닫기",
        fail: "충전에 실패했어요. 잠시 후 다시 시도해 주세요.",
        oneclick: "⚡ 원클릭 충전 · {{credits}}P (결제 {{pay}})",
        other_amount: "다른 금액으로 충전", pay_label: "결제 {{pay}}", vat_incl: "부가세 {{vat}} 포함",
        loading_pkgs: "충전 상품을 불러오는 중…", done_continue: "계속하기",
        note_vat: "결제금액은 <b>부가세 10% 포함</b>이에요. 결제창 이동 없이 바로 충전되고 <b>작성 중인 내용은 그대로 유지</b>됩니다.",
        note_novat: "결제창 이동 없이 바로 충전되고, <b>작성 중인 내용은 그대로 유지</b>됩니다.",
        entry_fee: "{{label}} 입장료", entry_extra: "· 추가 질문은 별도 차감",
        bal_charge: "잔액 {{bal}}P · 충전하기", bal_only: "잔액 {{bal}}P",
        need_charge: "{{label}} 입장에는 {{cost}}P가 필요해요. 충전하면 작성 내용 그대로 바로 이어집니다.",
        confirm_entry: "{{label}}은(는) 입장 시 {{cost}}P가 차감됩니다.\n(추가 질문은 별도: 기본 {{basic}}P · 심화 {{deep}}P)\n\n계속하시겠습니까?",
        entry_suffix: " · 입장 {{cost}}P",
        need_charge_alert: "{{label}} 입장에는 {{cost}}P가 필요합니다.\n현재 잔액 {{bal}}P — 포인트를 충전한 뒤 다시 시도해 주세요.",
      },
      chat: chatKo,
    },
  },
  vi: {
    common: {
      brand: "Xem Bói",
      nav: {
        new_consult: "Tư vấn mới", consult: "Xem Tứ Trụ", compat: "Xem tuổi", taekil: "Xem ngày",
        jakmyeong: "Đặt tên", gaemyeong: "Đổi tên", aho: "Biệt hiệu", tarot: "Tarot", charge: "Nạp điểm",
        settings: "Cài đặt", consultant_console: "Bảng tư vấn", uploads: "Tải lên",
        trend: "Xu hướng đánh giá", admin: "Quản trị", support: "Hỗ trợ",
        login: "Đăng nhập", logout: "Đăng xuất", withdraw: "Hủy tài khoản",
      },
      theme: { dark: "Tối", light: "Sáng" },
      landing: {
        eyebrow: "Tứ Trụ · AI mệnh lý",
        hero_title: "Vận mệnh của bạn qua lá số Tứ Trụ",
        hero_sub: "Từ tư vấn, xem tuổi, chọn ngày đến đặt tên — quy tắc mệnh lý và AI cùng luận giải có căn cứ. Hãy chọn tính năng bạn muốn bên dưới.",
        hero_cta: "Bắt đầu miễn phí",
        bottom_cta: "Hãy bắt đầu miễn phí ngay",
        band_sub: "Xem trước không cần đăng nhập; đăng nhập để nhận câu hỏi miễn phí.",
        band_btn: "Bắt đầu xem Tứ Trụ",
        fee_enter: "💎 Vào cửa", fee_extra: "· Hỏi thêm tính riêng", fee_free: "🆓 Bắt đầu miễn phí",
        note_in: "✨ Đã đăng nhập — bạn đang <b>dùng 100% mọi tính năng</b>: hiệu chỉnh giờ mặt trời thật, luận giải đầy đủ và hỏi nối tiếp.",
        note_guest: "Chưa đăng nhập chỉ có <b>bản xem trước 50%</b>. <b>Đăng nhập</b> để dùng <b>100% tính năng riêng</b>: hiệu chỉnh giờ mặt trời thật, luận giải đầy đủ, câu hỏi miễn phí.",
        faq_title: "Câu hỏi thường gặp",
        faq: [
          { q: "Có chính xác không?", a: "Chúng tôi tính hợp·xung·ngũ hành·thập thần·thần sát theo quy tắc rồi thêm luận giải của AI. Mệnh lý không có đáp án tuyệt đối nên trình bày nhiều góc nhìn." },
          { q: "Có miễn phí không?", a: "Chưa đăng nhập được xem trước 50% câu trả lời; đăng nhập để dùng câu hỏi miễn phí và xem đầy đủ." },
          { q: "Tôi không biết giờ sinh.", a: "Vẫn phân tích được với ‘không rõ giờ’ (bỏ trụ giờ)." },
        ],
        card: {
          sang: { badge: "Xem Tứ Trụ", title: "Hỏi AI về lá số của bạn",
            desc: "Chỉ cần ngày sinh, AI luận giải tính cách, vận trình và dòng chảy năm nay theo kiểu 1:1.",
            bullets: ["Luận giải dựa trên lá số & Ngũ hành", "Hỏi thêm nối tiếp", "Chế độ dễ hiểu cho người mới"], cta: "Bắt đầu xem miễn phí" },
          gunghap: { badge: "Xem tuổi", title: "Duyên hai người qua lá số",
            desc: "So sánh hai lá số qua hợp·xung·ngũ hành·thần sát, cho điểm hợp tuổi và luận giải.",
            bullets: ["Biểu đồ ngũ giác", "Nhiều trường phái, không tuyệt đối", "So với mức trung bình"], cta: "Xem hợp tuổi" },
          taekil: { badge: "Xem ngày", title: "Chọn ngày tốt",
            desc: "Cưới hỏi·chuyển nhà·khai trương·ký kết… chọn ngày tốt theo mục đích trong khoảng thời gian.",
            bullets: ["Hoàng đạo/Hắc đạo · Kiến trừ 12 thần", "Tránh xung·hình với lá số của bạn", "So sánh đề xuất số 1 theo trường phái"], cta: "Chọn ngày" },
          tarot: { badge: "Tarot", title: "Lá bài trả lời cho hôm nay",
            desc: "Tự rút lá trong 78 lá để đọc chuyện tình duyên·tài lộc·ngã rẽ lựa chọn.",
            bullets: ["Móng ngựa 7 lá · Celtic Cross 11 lá", "Tự rút lá, xuôi·ngược", "Luận giải theo vị trí & lời khuyên cụ thể"], cta: "Xem Tarot" },
        },
      },
      auth: {
        sub_inline: "Đăng nhập để nhận câu trả lời đầy đủ và câu hỏi miễn phí",
        sub_page: "Hỏi lá số của bạn, đọc vận mỗi ngày",
        tab_login: "Đăng nhập", tab_register: "Đăng ký",
        notice_expired: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
        notice_idle: "Bạn không hoạt động lâu nên đã bị tự động đăng xuất. Vui lòng đăng nhập lại.",
        must_change_pw: "Đây là mật khẩu khởi tạo của quản trị. Vui lòng đổi mật khẩu.",
        err_agree: "Bạn phải đồng ý tất cả điều khoản bắt buộc và tuyên bố miễn trừ.",
        err_birth: "Vui lòng nhập ngày sinh.",
        welcome: "Chào mừng bạn! Điểm thưởng đăng ký đã được cộng.",
        fail_login: "Đăng nhập thất bại", fail_register: "Đăng ký thất bại", fail_oauth: "Đăng nhập {{provider}} thất bại",
        email: "Email", password: "Mật khẩu",
        nickname: "Biệt danh (tùy chọn)", nickname_ph: "Tên hiển thị",
        pw_ph_register: "Nhập từ 8 ký tự", pw_ph_login: "Mật khẩu",
        birth: "Ngày sinh (từ {{age}} tuổi trở lên)",
        agree_all: "Đồng ý tất cả", agree_all_sub: "(gồm cả mục bắt buộc và tùy chọn)",
        req: "Bắt buộc", opt: "Tùy chọn",
        agree_terms: "Đồng ý với <a>Điều khoản sử dụng</a>.",
        agree_privacy: "Đồng ý <a>Thu thập·sử dụng thông tin cá nhân</a>.",
        summary_open: "Xem tóm tắt", summary_close: "Thu gọn",
        sum_items_label: "Mục thu thập",
        sum_items: "Email·mật khẩu (mã hóa)·ngày sinh (mã hóa), dữ liệu lá số·nội dung tư vấn, lịch sử thanh toán, nhật ký truy cập",
        sum_purpose_label: "Mục đích",
        sum_purpose: "Xác định thành viên·cung cấp luận giải·vận hành thanh toán/điểm·xử lý yêu cầu·tuân thủ pháp luật",
        sum_retention_label: "Thời gian lưu",
        sum_retention: "Hủy ngay khi hủy tài khoản (trừ mục luật định phải lưu)",
        sum_note: "Bạn có thể từ chối, nhưng không đồng ý mục bắt buộc thì không thể đăng ký.",
        agree_refund: "Đồng ý <a>Chính sách hoàn tiền·hủy giao dịch</a>.",
        agree_disclaimer: "Đã đọc và đồng ý <a>Tuyên bố miễn trừ</a>.",
        agree_marketing: "Đồng ý nhận <b>thông tin quảng cáo</b> (sự kiện·ưu đãi).",
        agree_marketing_sub: "(không đồng ý vẫn dùng được)",
        agree_foot: "Chỉ người từ {{age}} tuổi mới đăng ký được; khi đăng ký xem như đã đồng ý các mục bắt buộc trên.",
        submit_busy: "Đang xử lý...", submit_login: "Đăng nhập", submit_register: "Đăng ký",
        oauth_divider: "Hoặc đăng nhập nhanh",
        oauth_kakao: "Bắt đầu với Kakao", oauth_google: "Bắt đầu với Google", oauth_facebook: "Bắt đầu với Facebook",
        foot_disclaimer: "Tuyên bố miễn trừ",
      },
      pay: {
        pt: "điểm",
        charge_title: "Nạp điểm",
        rate_note: "1 điểm = 1 VND · Nạp điểm để ẩn quảng cáo",
        processing: "Đang xử lý...", charge_btn: "Nạp",
        login_required: "Vui lòng đăng nhập để thanh toán.", login_link: "Đăng nhập",
        test_done: "[Chế độ thử] Đã nạp {{label}}\n+{{credits}} điểm → Số dư {{balance}} điểm",
        history_title: "Lịch sử thanh toán",
        th_order: "Mã đơn", th_amount: "Số tiền", th_credit: "Điểm", th_status: "Trạng thái", th_time: "Thời gian",
        modal_title: "⚡ Nạp điểm", aria_charge: "Nạp điểm", cur_balance: "Số dư hiện tại", close: "Đóng",
        fail: "Nạp điểm thất bại. Vui lòng thử lại sau.",
        oneclick: "⚡ Nạp nhanh · {{credits}} điểm (thanh toán {{pay}})",
        other_amount: "Nạp số tiền khác", pay_label: "Thanh toán {{pay}}", vat_incl: "Gồm VAT {{vat}}",
        loading_pkgs: "Đang tải gói nạp…", done_continue: "Tiếp tục",
        note_vat: "Số tiền đã <b>gồm VAT 10%</b>. Nạp ngay không cần chuyển trang, <b>nội dung đang soạn được giữ nguyên</b>.",
        note_novat: "Nạp ngay không cần chuyển trang, <b>nội dung đang soạn được giữ nguyên</b>.",
        entry_fee: "Phí vào {{label}}", entry_extra: "· Hỏi thêm tính riêng",
        bal_charge: "Số dư {{bal}} điểm · Nạp thêm", bal_only: "Số dư {{bal}} điểm",
        need_charge: "Vào {{label}} cần {{cost}} điểm. Nạp xong bạn tiếp tục ngay với nội dung đang soạn.",
        confirm_entry: "Vào {{label}} sẽ trừ {{cost}} điểm.\n(Hỏi thêm tính riêng: cơ bản {{basic}} điểm · chuyên sâu {{deep}} điểm)\n\nTiếp tục?",
        entry_suffix: " · Vào cửa {{cost}} điểm",
        need_charge_alert: "Vào {{label}} cần {{cost}} điểm.\nSố dư hiện tại {{bal}} điểm — vui lòng nạp thêm rồi thử lại.",
      },
      chat: chatVi,
    },
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: [...SUPPORTED],
    nonExplicitSupportedLngs: true, // vi-VN → vi
    load: "languageOnly",
    defaultNS: "common",
    ns: ["common"],
    returnNull: false,
    interpolation: { escapeValue: false }, // React가 XSS 이스케이프 담당
    detection: {
      // 디바이스(브라우저) 언어 기준 로딩. 우선순위:
      //   ① saju_lang(사용자가 스위치로 명시 전환) → ② navigator(기기 언어) → ③ fallbackLng(배포 기본).
      //   기기 언어가 ko → 한국어, vi → 베트남어, 그 외(en 등) → 배포 기본(VN 빌드=vi).
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "saju_lang",
      caches: ["localStorage"],
    },
  });

/** 로케일 전환 + localStorage 영속 + <html lang> 갱신. 언어 스위처에서 호출. */
export function setLocale(loc: Locale): void {
  i18n.changeLanguage(loc);
  try {
    localStorage.setItem("saju_lang", loc);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = loc;
}

export default i18n;
