// 이중 로케일(ko/vi) i18n 초기화 — react-i18next.
// ko 사이트(saju.songstock.art)=ko 기본(현행 불변) / vi 사이트(xemboi.io)=vi 기본.
//   VN 빌드는 VITE_DEFAULT_LOCALE=vi 로 오버라이드. 기본 'ko'라 한국 서비스 불변.
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

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
