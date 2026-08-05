// 언어 전환 — 한국(사주1)엔 없는 VN 전용 UI. 베트남 우선이라 '콘텐츠 영역 좌측 상단'에 표시.
//  ★ 게이팅: VN 빌드(VITE_DEFAULT_LOCALE=vi)에서만 렌더. ko 빌드는 null → 한국 UI 완전 불변.
//  ★ 위치: .app-content(position:relative) 내부 absolute 좌상단 → 사이드바 밖이라 '모바일에서도 보임'.
//  국기는 실제 SVG(이모지는 윈도우에서 코드로 표기됨). VN=기본, KR(태극기)=서브.
import { useTranslation } from "react-i18next";
import { setLocale, type Locale } from "../i18n";

const VN_BUILD =
  ((import.meta as any).env?.VITE_DEFAULT_LOCALE as string | undefined) === "vi";

// 베트남 국기 — 적색 바탕 + 황색 오각별
function FlagVI() {
  return (
    <svg viewBox="0 0 30 20" width="22" height="15" aria-hidden
         style={{ borderRadius: 2, display: "block", flex: "none", boxShadow: "0 0 0 1px rgba(0,0,0,.08)" }}>
      <rect width="30" height="20" fill="#da251d" />
      <path fill="#ff0" d="M15,5 16.2,8.4 19.8,8.5 16.9,10.6 17.9,14.1 15,12 12.1,14.1 13.1,10.6 10.2,8.5 13.8,8.4Z" />
    </svg>
  );
}

// 대한민국 국기(태극기) — 흰 바탕 + 태극(적/청) + 4괘(건곤감리)
function FlagKR() {
  return (
    <svg viewBox="0 0 36 24" width="22" height="15" aria-hidden
         style={{ borderRadius: 2, display: "block", flex: "none", boxShadow: "0 0 0 1px rgba(0,0,0,.12)" }}>
      <rect width="36" height="24" fill="#fff" />
      <circle cx="18" cy="12" r="6" fill="#cd2e3a" />
      <path d="M12,12 a3,3 0 0,1 6,0 a3,3 0 0,0 6,0 a6,6 0 0,1 -12,0" fill="#0047a0" />
      <g fill="#000">
        {/* 건(TL) 3 solid */}
        <rect x="4.5" y="4.2" width="7" height="1" /><rect x="4.5" y="6" width="7" height="1" /><rect x="4.5" y="7.8" width="7" height="1" />
        {/* 감(TR) broken·solid·broken */}
        <rect x="24.5" y="4.2" width="3" height="1" /><rect x="28.5" y="4.2" width="3" height="1" />
        <rect x="24.5" y="6" width="7" height="1" />
        <rect x="24.5" y="7.8" width="3" height="1" /><rect x="28.5" y="7.8" width="3" height="1" />
        {/* 리(BL) solid·broken·solid */}
        <rect x="4.5" y="15.2" width="7" height="1" />
        <rect x="4.5" y="17" width="3" height="1" /><rect x="8.5" y="17" width="3" height="1" />
        <rect x="4.5" y="18.8" width="7" height="1" />
        {/* 곤(BR) 3 broken */}
        <rect x="24.5" y="15.2" width="3" height="1" /><rect x="28.5" y="15.2" width="3" height="1" />
        <rect x="24.5" y="17" width="3" height="1" /><rect x="28.5" y="17" width="3" height="1" />
        <rect x="24.5" y="18.8" width="3" height="1" /><rect x="28.5" y="18.8" width="3" height="1" />
      </g>
    </svg>
  );
}

const ITEMS: { loc: Locale; Flag: () => JSX.Element; label: string }[] = [
  { loc: "vi", Flag: FlagVI, label: "Tiếng Việt" },
  { loc: "ko", Flag: FlagKR, label: "한국어" },
];

// compact: 국기만(라벨 숨김) 컴팩트 배지 — 로그인 카드 좌상단처럼 폭이 좁은 곳용.
//   기본(라벨 포함)은 사이드바 콘텐츠 상단(App.tsx .app-content)용.
export default function LanguageSwitch({ compact = false }: { compact?: boolean } = {}) {
  const { i18n } = useTranslation();
  if (!VN_BUILD) return null; // 한국 빌드에는 표시하지 않음(불변)

  const cur = ((i18n.language || "vi").slice(0, 2)) as Locale;
  const pick = (loc: Locale) => {
    if (loc === cur) return;
    setLocale(loc);
    window.location.reload();
  };

  return (
    <div
      role="group"
      aria-label="Language / Ngôn ngữ"
      style={{
        position: "absolute", // 부모(relative) 기준 좌상단. App=.app-content / Login=.auth-card
        top: 12,
        left: compact ? 12 : 16,
        zIndex: 40,
        display: "flex",
        gap: 4,
        padding: "4px 5px",
        borderRadius: 999,
        background: "var(--card, rgba(255,255,255,.92))",
        boxShadow: "0 2px 10px rgba(0,0,0,.14)",
        backdropFilter: "blur(6px)",
      }}
    >
      {ITEMS.map(({ loc, Flag, label }) => {
        const active = loc === cur;
        return (
          <button
            key={loc}
            type="button"
            aria-pressed={active}
            title={label}
            aria-label={compact ? label : undefined}
            onClick={() => pick(loc)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: compact ? 0 : 6,
              padding: compact ? "5px 7px" : "4px 10px",
              fontSize: 13,
              lineHeight: 1.2,
              borderRadius: 999,
              cursor: "pointer",
              fontWeight: active ? 700 : 400,
              border: active ? "1px solid #0d9488" : "1px solid transparent",
              background: active ? "rgba(13,148,136,.14)" : "transparent",
              color: "inherit",
            }}
          >
            <Flag />
            {!compact && <span>{label}</span>}
          </button>
        );
      })}
    </div>
  );
}
