import { NavLink, Route, Routes, Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Ic, type IcName } from "./components/icons";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import ChatPage from "./pages/ChatPage";
import LandingPage from "./pages/LandingPage";
import CompatibilityPage from "./pages/CompatibilityPage";
import TaekilPage from "./pages/TaekilPage";
import TodayPage from "./pages/TodayPage";
import ReviewsPage from "./pages/ReviewsPage";
import AmuletPage from "./pages/AmuletPage";
import CalendarPage from "./pages/CalendarPage";
import CompatInvitePage from "./pages/CompatInvitePage";
import SnackPage from "./pages/SnackPage";
import TarotPage from "./pages/TarotPage";
import UploadsPage from "./pages/UploadsPage";
import TrendPage from "./pages/TrendPage";
import LoginPage from "./pages/LoginPage";
import OAuthSuccessPage from "./pages/OAuthSuccessPage";
import AdminPage from "./pages/AdminPage";
import ConsultantConsolePage from "./pages/ConsultantConsolePage";
import PaymentsPage from "./pages/PaymentsPage";
import PaymentSuccessPage, { PaymentFailPage } from "./pages/PaymentResultPage";
import SettingsPage from "./pages/SettingsPage";
import SupportPage from "./pages/SupportPage";
import PartnerApplyPage from "./pages/PartnerApplyPage";
import LegalPage from "./pages/LegalPage";
import InstallPrompt from "./components/InstallPrompt";
import ShareFab from "./components/ShareFab";
import DisclaimerGate from "./components/DisclaimerGate";
import TermsGate from "./components/TermsGate";
import AdSlot from "./components/AdSlot";
import { useTheme } from "./hooks/useTheme";
import { useIdleTimeout } from "./hooks/useIdleTimeout";
import { api, useMe, setCachedMe, setToken, getToken, getCachedMe, notifySessionExpired, type LegalInfo, type ConsultSource } from "./api";
import { useCharge } from "./components/ChargeModal";
import ProgressDock from "./components/ProgressDock";
import ConsultationOverlay from "./components/ConsultationOverlay";
import ConsultantPushPrompt from "./components/ConsultantPushPrompt";
import { useConsultation } from "./components/ConsultationProvider";
import { startUsageTracking, track, menuKey } from "./lib/usage";
import { isStandalonePwa } from "./lib/inapp";

/** 사이드바 럭셔리 메뉴 아이콘(FLUX 베이크 메달리온) — 이미지 없으면 기존 선화 아이콘 폴백 */
function MenuIc({ k, ic }: { k: string; ic: IcName }) {
  const [err, setErr] = useState(false);
  if (err) return <Ic name={ic} />;
  return (
    <img className="nav-lux-ic" src={`/icons/menu/${k}.webp`} alt="" width={26} height={26}
         loading="lazy" onError={() => setErr(true)} />
  );
}

export default function App() {
  const me = useMe();
  // 사업자 정보(전자상거래법 footer) — 관리자 '사이트/회사정보' 입력값을 공개 API 로 읽어 반영.
  const [legal, setLegal] = useState<LegalInfo | null>(null);
  useEffect(() => { api.legalVersions().then(setLegal).catch(() => {}); }, []);
  const { openCharge } = useCharge();
  const { onDuty } = useConsultation();  // 상담 중/상담사 콘솔 접속 → idle 로그아웃 예외
  const [consultOpen, setConsultOpen] = useState(false);  // 1:1 상담 오버레이
  // A-1: 사주/타로 화면 CTA 진입 시 명식·카드 자동 전달 소스 (FAB 진입은 null)
  const [consultSource, setConsultSource] = useState<ConsultSource | null>(null);
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent).detail as ConsultSource | undefined;
      setConsultSource(d && d.kind && d.refId ? d : null);
      setConsultOpen(true);
    };
    window.addEventListener("saju:consult-open", h);
    return () => window.removeEventListener("saju:consult-open", h);
  }, []);
  const [isConsultant, setIsConsultant] = useState(false);
  useEffect(() => {
    if (!me) { setIsConsultant(false); return; }
    api.myConsultantProfile().then((r) => setIsConsultant(!!r.consultant)).catch(() => setIsConsultant(false));
  }, [me?.id]);
  // '입점 신청' 메뉴 노출(운영자 지시 2026-07-11): 일반 사용자에겐 숨김 —
  // 신청 이력자(심사현황 확인)·승인된 상담사·관리자만. 최초 신청은 /partner-apply 직접 링크로 안내.
  const [partnerApplied, setPartnerApplied] = useState(false);
  useEffect(() => {
    if (!me) { setPartnerApplied(false); return; }
    const check = () => api.partnerApplyMine().then((r) => setPartnerApplied(!!(r.application || r.inquiry))).catch(() => setPartnerApplied(false));
    check();
    window.addEventListener("saju:partner-apply-changed", check);   // 신청 직후 메뉴 즉시 반영
    return () => window.removeEventListener("saju:partner-apply-changed", check);
  }, [me?.id]);
  const showPartnerMenu = !!me && (partnerApplied || isConsultant || me.role === "admin");
  const { theme, toggle } = useTheme();
  const loc = useLocation();
  const navigate = useNavigate();
  const isChat = loc.pathname === "/" || loc.pathname.startsWith("/chat");
  const curS = new URLSearchParams(loc.search).get("s");
  // 타로 바로가기 — 상담·궁합·택일·작명/개명/아호(+메인)에서 우측상단에 노출(타로 페이지 자신은 제외)
  // 타로 바로가기 — 전 사용자 메뉴 표준 노출(운영자 지시 2026-07-11: 오늘운세·신년운세에도).
  // 제외: 타로 자신·관리/운영 화면(관리자·업로드·평가추세·상담사 콘솔)·결제 진행/법적 고지 화면.
  const tarotShortcutExclude = ["/tarot", "/admin", "/uploads", "/trend", "/consultation", "/legal", "/payments"];
  const showTarotShortcut = !tarotShortcutExclude.some((p) => loc.pathname === p || loc.pathname.startsWith(p + "/")) && loc.pathname !== "/login";
  const [navSessions, setNavSessions] = useState<{ session_id: string; title: string; birth_date: string }[]>([]);
  const [navOpen, setNavOpen] = useState(false);
  async function refreshNav() {
    if (!me) { setNavSessions([]); return; }
    try {
      const r = await api.myChatSessions(50);
      setNavSessions(r.items as any);
    } catch { /* ignore */ }
  }
  useEffect(() => {
    if (me) refreshNav();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isChat]);
  useEffect(() => {
    const h = () => refreshNav();
    window.addEventListener("saju:sessions-changed", h);
    return () => window.removeEventListener("saju:sessions-changed", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // 입력창(.chat-input)에 포커스가 있는 동안 body.composing 토글 → 모바일에서 플로팅 버튼
  // (1:1 상담·충전)을 숨겨 전송 버튼 오탭을 막는다(입력 끝나면 다시 나타남). 전 메뉴 공통 클래스.
  useEffect(() => {
    const isInput = (t: EventTarget | null) =>
      t instanceof Element && t.classList.contains("chat-input");
    const on = (e: FocusEvent) => { if (isInput(e.target)) document.body.classList.add("composing"); };
    const off = (e: FocusEvent) => { if (isInput(e.target)) document.body.classList.remove("composing"); };
    document.addEventListener("focusin", on);
    document.addEventListener("focusout", off);
    return () => {
      document.removeEventListener("focusin", on);
      document.removeEventListener("focusout", off);
      document.body.classList.remove("composing");
    };
  }, []);
  // 첫 진입 1회: /chat 으로 '직접' 들어오면 대문(랜딩)에서 시작 — 대문이 곧 입구.
  // (앱 내 이동(상담/새 상담 클릭)·진행 중 세션 ?s= 은 그대로 유지)
  const bootRef = useRef(false);
  useEffect(() => {
    if (bootRef.current) return;
    bootRef.current = true;
    // 앱 로드 시 서버 최신 me 로 캐시 갱신 → saju_profile(본인 사주 자동 채움) 등 신선도 보장.
    // 토큰이 있으면 검증(만료면 jfetch 가 notifySessionExpired→로그인 화면). 토큰은 없는데 로그인했던
    // 흔적(캐시 me)만 남았으면 = 세션이 조용히 끊긴 것 → 바로 로그인 화면으로(먹통 방지).
    if (getToken()) {
      api.me().then(setCachedMe).catch(() => {});
    } else if (getCachedMe()) {
      notifySessionExpired();
    }
    if (loc.pathname.startsWith("/chat") && !curS) {
      navigate("/", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function delNavSession(id: string) {
    if (!window.confirm("이 상담을 삭제할까요?")) return;
    try { await api.deleteChatSession(id); } catch { /* ignore */ }
    if (curS === id) navigate("/chat");
    refreshNav();
  }
  function forceLogout() {
    const rt = localStorage.getItem("saju_refresh");
    if (rt) api.authLogout(rt);
    localStorage.removeItem("saju_refresh");
    setToken(null);
    setCachedMe(null);
    location.href = "/login?idle=1";
  }
  // 영업 중 상담사(onDuty)는 idle 자동로그아웃 제외 — 대기 중 presence 유지 + 접수 대응(요건: 상담사 on/off)
  const idle = useIdleTimeout({ enabled: !!me && !onDuty, onTimeout: forceLogout });

  /* 라우트 전환 시 항상 화면 최상단에서 시작(운영자 지적: '사이드 메뉴를 누르면 일부 화면이 중간부터
     로딩된다'). SPA는 페이지가 바뀌어도 window 스크롤이 그대로 남아, 스크롤된 상태에서 메뉴를 누르면
     새 화면의 헤더가 뷰포트 위로 밀려 보인다. 페인트 전(useLayoutEffect)에 리셋해 깜빡임 방지.
     ⚠️ 조기반환(isAuthPage)보다 위에 둬야 훅이 항상 같은 순서로 실행된다. */
  useLayoutEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [loc.pathname]);

  // 사용 현황 수집(관리자 '현재 통계') — 부트 1회 + 라우트 전환마다 메뉴 페이지뷰
  useEffect(() => { startUsageTracking(); }, []);
  useEffect(() => { track("page", menuKey(loc.pathname)); }, [loc.pathname]);

  // 앱 설치 플로팅(운영자 지시: 눈에 보여야 설치 유도) — 설치되면(standalone 실행/appinstalled) 숨김
  const [showInstallFab, setShowInstallFab] = useState(
    () => !isStandalonePwa() && localStorage.getItem("saju_pwa_installed") !== "1",
  );
  useEffect(() => {
    const hide = () => setShowInstallFab(false);
    window.addEventListener("saju:pwa-installed", hide);
    return () => window.removeEventListener("saju:pwa-installed", hide);
  }, []);

  const isAuthPage = loc.pathname === "/login" || loc.pathname.startsWith("/login/");
  if (isAuthPage) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/login/oauth-success" element={<OAuthSuccessPage />} />
      </Routes>
    );
  }
  function logout() {
    const ok = window.confirm(
      "로그아웃을 하면 개인정보, 일주정보와 채팅 히스토리는 이 기기에서 삭제됩니다.\n\n※ 동일 계정으로 재로그인하면 서버에 보관된 정보는 그대로 복원됩니다.\n\n진행할까요?"
    );
    if (!ok) return;
    const rt = localStorage.getItem("saju_refresh");
    if (rt) api.authLogout(rt);
    localStorage.removeItem("saju_refresh");
    setToken(null);
    setCachedMe(null);
    location.href = "/login";
  }
  async function withdraw() {
    const ok1 = window.confirm(
      "⚠️ 정말 탈퇴하시겠습니까?\n\n탈퇴 시 계정, 개인정보, 사주/일주 정보, 모든 채팅 기록, 보유 포인트 및 결제 이력이 영구적으로 삭제되며 복원할 수 없습니다."
    );
    if (!ok1) return;
    const phrase = window.prompt("확인을 위해 「탈퇴」 단어를 입력해 주세요.");
    if (phrase !== "탈퇴") {
      alert("탈퇴가 취소되었습니다.");
      return;
    }
    try {
      await api.deleteMe();
      alert("탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다.");
    } catch (e: any) {
      alert(`탈퇴 실패: ${e?.message || e}`);
      return;
    }
    setToken(null);
    setCachedMe(null);
    location.href = "/login";
  }
  return (
    <div className="app-shell">
      <button className="app-hamburger" aria-label="메뉴" onClick={() => setNavOpen((v) => !v)}>☰</button>
      <div className={`app-sidebar-overlay ${navOpen ? "open" : ""}`} onClick={() => setNavOpen(false)} />
      <aside className={`app-sidebar ${navOpen ? "open" : ""}`}>
        <Link className="app-brand" to="/" onClick={() => setNavOpen(false)} title="메인으로">
          <img className="app-brand-icon" src="/pwa-icon.svg" alt="" width={22} height={22} />
          <span>인생상담 친구</span>
          <img className="app-brand-seal" src="/brand-seal.png" alt="" width={15} height={15} />
        </Link>
        <button
          className="app-newchat"
          onClick={() => { window.dispatchEvent(new Event("saju:new-chat")); navigate("/chat"); setNavOpen(false); }}
        >
          <Ic name="pencil" /> 새 상담
        </button>
        <nav className="app-nav">
          <NavLink to="/chat" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="chat" ic="chat" /> 상담</NavLink>
          <NavLink to="/today" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="today" ic="calendar" /> 오늘의 운세</NavLink>
          <NavLink to="/calendar" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="fcalendar" ic="calendar" /> 운세 캘린더</NavLink>
          <NavLink to="/compatibility" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gunghap" ic="heart" /> 궁합</NavLink>
          <NavLink to="/taekil" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="taekil" ic="calendar" /> 택일</NavLink>
          <NavLink to="/amulet" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="amulet" ic="amulet" /> 부적</NavLink>
          <NavLink to="/tarot" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="tarot" ic="tarot" /> 타로</NavLink>
          <NavLink to="/snack" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="snack" ic="star" /> 무료 테스트</NavLink>
          <NavLink to="/reviews" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="reviews" ic="star" /> 이용 후기</NavLink>
          <NavLink to="/payments" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="bolt" ic="bolt" /> 충전</NavLink>
          <NavLink to="/support" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active support-nav" : "support-nav")}><MenuIc k="mail" ic="mail" /> 고객센터</NavLink>
          {/* 앱 설치 — 다른 메뉴와 동일 UI(FLUX 메달리온 아이콘) · 스누즈 무관 상시 진입점 */}
          <button type="button" className="app-install-btn"
                  onClick={() => { setNavOpen(false); window.dispatchEvent(new CustomEvent("saju:open-install-guide")); }}>
            <MenuIc k="install" ic="bolt" /> 앱 설치
          </button>
          {/* 입점 신청 — 일반 사용자에겐 비노출(운영자 지시): 신청 이력자·상담사·관리자만 */}
          {showPartnerMenu && (
            <NavLink to="/partner-apply" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="partner" ic="heart" /> 입점 신청</NavLink>
          )}
          {/* ── 이후 관리자/운영 메뉴(운영자 지시) ── */}
          {me && (
            <NavLink to="/settings" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gear" ic="gear" /> 설정</NavLink>
          )}
          {isConsultant && (
            <NavLink to="/consultation/console" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><span className="nav-emoji" aria-hidden>💬</span> 상담사</NavLink>
          )}
          {me?.role === "admin" && (
            <>
              <NavLink to="/uploads" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="folder" ic="folder" /> 업로드</NavLink>
              <NavLink to="/trend" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="chart" ic="chart" /> 평가 추세</NavLink>
              <NavLink to="/admin" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="wrench" ic="wrench" /> 관리자</NavLink>
            </>
          )}
        </nav>
        {me && (
          <div className="app-sessions">
            <div className="app-sessions-label">최근 상담</div>
            <div className="app-session-list">
              {navSessions.length === 0 && <div className="app-session-empty">아직 상담이 없어요</div>}
              {navSessions.map((s) => (
                <div
                  key={s.session_id}
                  className={`app-session-item ${curS === s.session_id ? "active" : ""}`}
                >
                  <span className="t" onClick={() => { navigate(`/chat?s=${s.session_id}`); setNavOpen(false); }}>
                    {s.title || s.birth_date}
                  </span>
                  <button className="x" title="삭제" onClick={() => delNavSession(s.session_id)}>×</button>
                </div>
              ))}
            </div>
          </div>
        )}
        {/* 사이드바 광고 2칸 (로그인/다크 토글 위). 자체배너 우선 → 없으면 AdSense. ads_hidden이면 자동 비표시 */}
        <div className="sidebar-ads-bottom">
          <AdSlot slot="side_1" height={120} adsenseSlot={import.meta.env.VITE_ADSENSE_SLOT_SIDE1 as string | undefined} />
          <AdSlot slot="side_2" height={120} adsenseSlot={import.meta.env.VITE_ADSENSE_SLOT_SIDE2 as string | undefined} />
        </div>
        <div className="app-sidebar-foot">
          <button onClick={toggle} className="theme-toggle" title="테마 전환" aria-label="테마 전환">
            {theme === "dark" ? "☀️ 라이트" : "🌙 다크"}
          </button>
          {me ? (
            <>
              <div className="app-account-name">{me.nickname || me.email}</div>
              <div className="app-account-bal">{me.balance.toLocaleString()} P</div>
              <div className="app-account-actions">
                <button className="ghost" onClick={logout}>로그아웃</button>
                <button className="ghost" style={{ color: "#991b1b" }} onClick={withdraw}>탈퇴</button>
              </div>
            </>
          ) : (
            <NavLink to="/login" className="app-login-btn" onClick={() => setNavOpen(false)}>로그인</NavLink>
          )}
        </div>
      </aside>
      <div className="app-content">
      {showTarotShortcut && (
        <Link className="tarot-shortcut" to="/tarot" title="타로 리딩 — 카드가 전하는 이야기" aria-label="타로 리딩 보러가기">
          <span className="tsc-emblem" aria-hidden>
            <img className="tsc-img" src="/tarot/tarot-badge.webp" alt="" width={40} height={40}
                 onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
            <svg className="tsc-svg" viewBox="0 0 40 40" aria-hidden>
              <defs>
                <linearGradient id="tscG" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#F6E9BE" /><stop offset=".5" stopColor="#C9A455" /><stop offset="1" stopColor="#9C7C38" />
                </linearGradient>
              </defs>
              <rect x="9" y="4" width="22" height="32" rx="4" fill="#10142F" stroke="url(#tscG)" strokeWidth="1.6" />
              <circle cx="20" cy="16" r="5.2" fill="none" stroke="url(#tscG)" strokeWidth="1.2" />
              <path d="M20 8.5 L20.9 14 M20 23.5 L20.9 18 M12.8 16 L18 15.1 M27.2 16 L22 15.1" stroke="url(#tscG)" strokeWidth="1" strokeLinecap="round" />
              <path d="M23.5 26 A4 4 0 1 1 23.5 32 A3 3 0 1 0 23.5 26 Z" fill="url(#tscG)" />
              <circle cx="15" cy="29" r=".9" fill="#F0DCA0" /><circle cx="20" cy="31" r=".7" fill="#F0DCA0" />
            </svg>
          </span>
          <span className="tsc-labels">
            <span className="tsc-text">TAROT</span>
            <span className="tsc-sub">타로</span>
          </span>
        </Link>
      )}
      <div className={isChat ? "container container-full" : "container"}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/compatibility" element={<CompatibilityPage />} />
          <Route path="/taekil" element={<TaekilPage />} />
          <Route path="/today" element={<TodayPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/amulet" element={<AmuletPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/compat-invite/:token" element={<CompatInvitePage />} />
          <Route path="/snack" element={<SnackPage />} />
          <Route path="/snack/:testId" element={<SnackPage />} />
          <Route path="/tarot" element={<TarotPage />} />
          <Route path="/uploads" element={<UploadsPage />} />
          <Route path="/trend" element={<TrendPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/login/oauth-success" element={<OAuthSuccessPage />} />
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/payments/success" element={<PaymentSuccessPage />} />
          <Route path="/payments/fail" element={<PaymentFailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/support" element={<SupportPage />} />
          <Route path="/partner-apply" element={<PartnerApplyPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/consultation/console" element={<ConsultantConsolePage />} />
          {/* 상담사 설정은 콘솔의 '설정' 탭으로 통합 — 구 경로는 콘솔로 리다이렉트 */}
          <Route path="/consultation/settings" element={<Navigate to="/consultation/console" replace />} />
          {/* /legal 단독 진입은 개인정보처리방침으로 — 하위 경로 없는 링크/북마크가 빈 화면이 되는 사고 방지 */}
          <Route path="/legal" element={<Navigate to="/legal/privacy" replace />} />
          <Route path="/legal/terms" element={<LegalPage kind="terms" />} />
          <Route path="/legal/privacy" element={<LegalPage kind="privacy" />} />
          <Route path="/legal/refund" element={<LegalPage kind="refund" />} />
          <Route path="/legal/disclaimer" element={<LegalPage kind="disclaimer" />} />
        </Routes>
      </div>
        <footer className="app-footer">
          <div className="app-footer-links">
            <Link to="/legal/terms">이용약관</Link>
            <Link to="/legal/privacy" className="footer-strong">개인정보처리방침</Link>
            <Link to="/legal/refund">환불정책</Link>
            <Link to="/legal/disclaimer">면책고지</Link>
            {/* 입점 문의 — 상담사 모집 진입점(운영자 확정: 사이드바 대신 푸터). 메달리온 아이콘 pill로 강조 */}
            <Link to="/partner-apply" className="partner-inquiry-link"><MenuIc k="partner" ic="heart" /> 상담사 입점 문의</Link>
          </div>
          {legal?.business && (
            <div className="app-footer-biz">
              {legal.business.name && <span><b>{legal.business.name}</b></span>}
              {legal.business.ceo && <span>대표 {legal.business.ceo}</span>}
              {legal.business.reg_no && <span>사업자등록번호 {legal.business.reg_no}</span>}
              <span>통신판매업 신고 {legal.business.mailorder_no || "준비 중"}</span>
              {legal.business.address && <span>{legal.business.address}</span>}
              {legal.business.tel && <span>고객센터 {legal.business.tel}</span>}
              {legal.business.hours && <span>운영시간 {legal.business.hours}</span>}
              {legal.business.email && (
                <span>
                  이메일{" "}
                  {legal.business.email.split(/[,;]/).map((e) => e.trim()).filter(Boolean).map((e, i) => (
                    <span key={e}>{i > 0 && " · "}<a href={`mailto:${e}`}>{e}</a></span>
                  ))}
                </span>
              )}
              {legal.business.privacy_officer && <span>개인정보보호책임자 {legal.business.privacy_officer}</span>}
              {legal.business.hosting && <span>호스팅 {legal.business.hosting}</span>}
            </div>
          )}
          <p className="app-footer-copy">© {new Date().getFullYear()} {legal?.business?.name || legal?.service_name || "인생상담 친구"}. All rights reserved.</p>
          <p className="app-footer-note">본 서비스 응답은 학습 자료 기반 참고용입니다. 의료·법률·투자 자문이 아닙니다.</p>
        </footer>
      </div>
      <InstallPrompt />
      {me && me.terms_agreed === false && <TermsGate />}
      {me && me.terms_agreed !== false && me.disclaimer_agreed === false && <DisclaimerGate />}
      {/* 1:1 상담 플로팅 — 비로그인 포함 항상 노출(운영자 결정 2026-07). 상담사 목록 API는 공개라
          비로그인도 열람 가능, 예약·시작 액션만 로그인 안내(401 친화 문구)로 유도된다. */}
      {/* 앱 설치 플로팅 — 좌하단(1:1 상담과 대칭). 설치 완료 시 자동 숨김.
          드로어(사이드바) 열림 중에는 숨김 — 사이드바 하단 로그인 버튼과 겹침 방지(드로어에 '앱 설치' 메뉴 있음). */}
      {showInstallFab && !navOpen && (
        <button className="install-fab" aria-label="앱으로 설치하기"
                onClick={() => window.dispatchEvent(new CustomEvent("saju:open-install-guide"))}>
          <span className="install-fab-ic" aria-hidden>📲</span>
          <span className="install-fab-tx">앱 설치</span>
        </button>
      )}
      {/* 설치 완료(또는 이미 앱)면 '앱 설치'가 사라진 자리에 '공유' FAB — 친구에게 설치유도 링크 전달(운영자 지시) */}
      {!showInstallFab && !navOpen && <ShareFab />}
      <button className="consult-fab" onClick={() => { setConsultSource(null); setConsultOpen(true); }} aria-label="1:1 상담하기">
        <span className="consult-fab-ic" aria-hidden>💬</span>
        <span className="consult-fab-tx">1:1 상담</span>
      </button>
      <ConsultationOverlay
        open={consultOpen}
        onClose={() => { setConsultOpen(false); setConsultSource(null); }}
        source={consultSource}
      />
      {/* 상담사 알림 자동 구독 — 로그인 상담사면 오프라인에도 접수 알림 받도록(허용 1클릭 배너/무음 재등록) */}
      <ConsultantPushPrompt active={isConsultant} />
      {me ? (
        <button className="charge-fab" onClick={() => openCharge()} aria-label={`내 포인트 ${(me.balance ?? 0).toLocaleString()}P · 충전하기`}>
          <span className="cfab-bal">
            <span className="cfab-ic" aria-hidden>💰</span>
            <span className="cfab-amt">{(me.balance ?? 0).toLocaleString()}<small>P</small></span>
          </span>
          <span className="cfab-go">＋ 충전</span>
        </button>
      ) : !loc.pathname.startsWith("/login") ? (
        <NavLink to="/login" className="login-fab" onClick={() => setNavOpen(false)} aria-label="로그인">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
            <path fill="currentColor" d="M12 12a5 5 0 100-10 5 5 0 000 10zm0 2c-5 0-9 2.5-9 6v2h18v-2c0-3.5-4-6-9-6z" />
          </svg>
          <span>로그인</span>
        </NavLink>
      ) : null}
      <ProgressDock />{/* 전역 진행 dock(영상·PDF·감정서). 작업 없을 땐 null → 비로그인도 무해 */}
      {me && idle.warning && (
        <div className="pwa-overlay" role="alertdialog" aria-label="유휴 자동 로그아웃 경고">
          <div className="pwa-modal">
            <h3>자동 로그아웃 안내</h3>
            <p>
              일정 시간 활동이 없어 곧 자동으로 로그아웃됩니다.
              <br />
              <strong>{idle.remaining}</strong>초 후 로그아웃됩니다.
            </p>
            <div className="pwa-actions">
              <button onClick={idle.stayActive}>계속 이용하기</button>
              <button className="ghost" onClick={forceLogout}>로그아웃</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

