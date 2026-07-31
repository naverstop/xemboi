import { NavLink, Route, Routes, Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import { fmtNum } from "./lib/money";
import { Ic, type IcName } from "./components/icons";
import { useEffect, useRef, useState } from "react";
import ChatPage from "./pages/ChatPage";
import LandingPage from "./pages/LandingPage";
import CompatibilityPage from "./pages/CompatibilityPage";
import NamingPage from "./pages/NamingPage";
import TaekilPage from "./pages/TaekilPage";
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
import LegalPage from "./pages/LegalPage";
import InstallPrompt from "./components/InstallPrompt";
import DisclaimerGate from "./components/DisclaimerGate";
import LanguageSwitch from "./components/LanguageSwitch";
import { IS_VN_BUILD } from "./i18n";
import TermsGate from "./components/TermsGate";
import AdSlot from "./components/AdSlot";
import { useTheme } from "./hooks/useTheme";
import { useIdleTimeout } from "./hooks/useIdleTimeout";
import { api, useMe, setCachedMe, setToken, getToken, getCachedMe, notifySessionExpired, type LegalInfo } from "./api";
import { useCharge } from "./components/ChargeModal";
import ProgressDock from "./components/ProgressDock";
import ConsultationOverlay from "./components/ConsultationOverlay";
import { useConsultation } from "./components/ConsultationProvider";

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
  const { t: tr } = useTranslation();
  // 사업자 정보(전자상거래법 footer) — 관리자 '사이트/회사정보' 입력값을 공개 API 로 읽어 반영.
  const [legal, setLegal] = useState<LegalInfo | null>(null);
  useEffect(() => { api.legalVersions().then(setLegal).catch(() => {}); }, []);
  const { openCharge } = useCharge();
  const { onDuty } = useConsultation();  // 상담 중/상담사 콘솔 접속 → idle 로그아웃 예외
  const [consultOpen, setConsultOpen] = useState(false);  // 1:1 상담 오버레이
  const [isConsultant, setIsConsultant] = useState(false);
  useEffect(() => {
    if (!me) { setIsConsultant(false); return; }
    api.myConsultantProfile().then((r) => setIsConsultant(!!r.consultant)).catch(() => setIsConsultant(false));
  }, [me?.id]);
  const { theme, toggle } = useTheme();
  const loc = useLocation();
  const navigate = useNavigate();
  const isChat = loc.pathname === "/" || loc.pathname.startsWith("/chat");
  const curS = new URLSearchParams(loc.search).get("s");
  // 타로 바로가기 — 상담·궁합·택일·작명/개명/아호(+메인)에서 우측상단에 노출(타로 페이지 자신은 제외)
  const tarotShortcutPages = ["/", "/chat", "/compatibility", "/taekil"];
  const showTarotShortcut = tarotShortcutPages.includes(loc.pathname) || loc.pathname.startsWith("/naming");
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
    if (!window.confirm(tr("shell.session_delete_confirm"))) return;
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
    const ok = window.confirm(tr("shell.logout_confirm"));
    if (!ok) return;
    const rt = localStorage.getItem("saju_refresh");
    if (rt) api.authLogout(rt);
    localStorage.removeItem("saju_refresh");
    setToken(null);
    setCachedMe(null);
    location.href = "/login";
  }
  async function withdraw() {
    const ok1 = window.confirm(tr("shell.withdraw_confirm"));
    if (!ok1) return;
    // 확인 게이트: 로케일별 확인단어(ko '탈퇴' / vi 'XÓA')를 입력. 대소문자·공백 무시로
    // vi 자판 사용자도 탈퇴 가능(기존 한국어 정확일치 요구 버그 수정).
    const word = tr("shell.withdraw_phrase");
    const phrase = window.prompt(tr("shell.withdraw_prompt", { word }));
    if ((phrase ?? "").trim().toLowerCase() !== word.toLowerCase()) {
      alert(tr("shell.withdraw_cancelled"));
      return;
    }
    try {
      await api.deleteMe();
      alert(tr("shell.withdraw_done"));
    } catch (e: any) {
      alert(tr("shell.withdraw_fail", { msg: e?.message || e }));
      return;
    }
    setToken(null);
    setCachedMe(null);
    location.href = "/login";
  }
  return (
    <div className="app-shell">
      <button className="app-hamburger" aria-label={tr("shell.menu")} onClick={() => setNavOpen((v) => !v)}>☰</button>
      <div className={`app-sidebar-overlay ${navOpen ? "open" : ""}`} onClick={() => setNavOpen(false)} />
      <aside className={`app-sidebar ${navOpen ? "open" : ""}`}>
        <Link className="app-brand" to="/" onClick={() => setNavOpen(false)} title={tr("shell.brand_home")}>
          <img className="app-brand-icon" src="/pwa-icon.svg" alt="" width={22} height={22} />
          <span>{tr("brand")}</span>
          <img className="app-brand-seal" src="/brand-seal.png" alt="" width={15} height={15} />
        </Link>
        <button
          className="app-newchat"
          onClick={() => { window.dispatchEvent(new Event("saju:new-chat")); navigate("/chat"); setNavOpen(false); }}
        >
          <Ic name="pencil" /> {tr("nav.new_consult")}
        </button>
        <nav className="app-nav">
          <NavLink to="/chat" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="chat" ic="chat" /> {tr("nav.consult")}</NavLink>
          <NavLink to="/compatibility" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gunghap" ic="heart" /> {tr("nav.compat")}</NavLink>
          <NavLink to="/taekil" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="taekil" ic="calendar" /> {tr("nav.taekil")}</NavLink>
          {/* 작명·개명·아호 — VN(xemboi)에선 제외(이름 체계가 달라 로직/검증 불가). ko 빌드만 노출 */}
          {!IS_VN_BUILD && (
            <>
              <NavLink to="/naming/jakmyeong" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="jakmyeong" ic="pen" /> {tr("nav.jakmyeong")}</NavLink>
              <NavLink to="/naming/gaemyeong" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gaemyeong" ic="renew" /> {tr("nav.gaemyeong")}</NavLink>
              <NavLink to="/naming/aho" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="aho" ic="stamp" /> {tr("nav.aho")}</NavLink>
            </>
          )}
          <NavLink to="/tarot" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="tarot" ic="tarot" /> {tr("nav.tarot")}</NavLink>
          <NavLink to="/payments" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="bolt" ic="bolt" /> {tr("nav.charge")}</NavLink>
          {me && (
            <NavLink to="/settings" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gear" ic="gear" /> {tr("nav.settings")}</NavLink>
          )}
          {isConsultant && (
            <NavLink to="/consultation/console" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><span className="nav-emoji" aria-hidden>💬</span> {tr("nav.consultant_console")}</NavLink>
          )}
          {me?.role === "admin" && (
            <>
              <NavLink to="/uploads" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="folder" ic="folder" /> {tr("nav.uploads")}</NavLink>
              <NavLink to="/trend" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="chart" ic="chart" /> {tr("nav.trend")}</NavLink>
              <NavLink to="/admin" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="wrench" ic="wrench" /> {tr("nav.admin")}</NavLink>
            </>
          )}
          <NavLink to="/support" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active support-nav" : "support-nav")}><MenuIc k="mail" ic="mail" /> {tr("nav.support")}</NavLink>
        </nav>
        {me && (
          <div className="app-sessions">
            <div className="app-sessions-label">{tr("shell.sidebar_recent")}</div>
            <div className="app-session-list">
              {navSessions.length === 0 && <div className="app-session-empty">{tr("shell.sidebar_empty")}</div>}
              {navSessions.map((s) => (
                <div
                  key={s.session_id}
                  className={`app-session-item ${curS === s.session_id ? "active" : ""}`}
                >
                  <span className="t" onClick={() => { navigate(`/chat?s=${s.session_id}`); setNavOpen(false); }}>
                    {s.title || s.birth_date}
                  </span>
                  <button className="x" title={tr("shell.session_delete")} onClick={() => delNavSession(s.session_id)}>×</button>
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
          <button onClick={toggle} className="theme-toggle" title={tr("shell.theme_toggle")} aria-label={tr("shell.theme_toggle")}>
            {theme === "dark" ? `☀️ ${tr("theme.light")}` : `🌙 ${tr("theme.dark")}`}
          </button>
          {me ? (
            <>
              <div className="app-account-name">{me.nickname || me.email}</div>
              <div className="app-account-bal">{fmtNum(me.balance)} {tr("pay.pt")}</div>
              <div className="app-account-actions">
                <button className="ghost" onClick={logout}>{tr("nav.logout")}</button>
                <button className="ghost" style={{ color: "#991b1b" }} onClick={withdraw}>{tr("nav.withdraw")}</button>
              </div>
            </>
          ) : (
            <NavLink to="/login" className="app-login-btn" onClick={() => setNavOpen(false)}>{tr("nav.login")}</NavLink>
          )}
        </div>
      </aside>
      <div className="app-content">
      <LanguageSwitch />{/* VN 빌드에서만 렌더 — 메인화면 상단 고정, VN기본/KR(태극기) 서브. ko 사이트 불변 */}
      {showTarotShortcut && (
        <Link className="tarot-shortcut" to="/tarot" title={tr("shell.tarot_shortcut_title")} aria-label={tr("shell.tarot_shortcut_aria")}>
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
            <span className="tsc-sub">{tr("nav.tarot")}</span>
          </span>
        </Link>
      )}
      <div className={isChat ? "container container-full" : "container"}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/compatibility" element={<CompatibilityPage />} />
          <Route path="/taekil" element={<TaekilPage />} />
          {!IS_VN_BUILD && <Route path="/naming/:kind" element={<NamingPage />} />}{/* 작명/개명/아호 — VN 제외 */}
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
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/consultation/console" element={<ConsultantConsolePage />} />
          <Route path="/legal/terms" element={<LegalPage kind="terms" />} />
          <Route path="/legal/privacy" element={<LegalPage kind="privacy" />} />
          <Route path="/legal/refund" element={<LegalPage kind="refund" />} />
          <Route path="/legal/disclaimer" element={<LegalPage kind="disclaimer" />} />
        </Routes>
      </div>
        <footer className="app-footer">
          <div className="app-footer-links">
            <Link to="/legal/terms">{tr("legal.title_terms")}</Link>
            <Link to="/legal/privacy" className="footer-strong">{tr("legal.title_privacy")}</Link>
            <Link to="/legal/refund">{tr("legal.title_refund")}</Link>
            <Link to="/legal/disclaimer">{tr("legal.title_disclaimer")}</Link>
          </div>
          {legal?.business && (
            <div className="app-footer-biz">
              {legal.business.name && <span><b>{legal.business.name}</b></span>}
              {legal.business.ceo && <span>{tr("shell.biz_ceo")} {legal.business.ceo}</span>}
              {legal.business.reg_no && <span>{tr("shell.biz_reg_no")} {legal.business.reg_no}</span>}
              <span>{tr("shell.biz_mailorder")} {legal.business.mailorder_no || tr("shell.biz_mailorder_pending")}</span>
              {legal.business.address && <span>{legal.business.address}</span>}
              {legal.business.tel && <span>{tr("shell.biz_tel")} {legal.business.tel}</span>}
              {legal.business.hours && <span>{tr("shell.biz_hours")} {legal.business.hours}</span>}
              {legal.business.email && (
                <span>
                  {tr("shell.biz_email")}{" "}
                  {legal.business.email.split(/[,;]/).map((e) => e.trim()).filter(Boolean).map((e, i) => (
                    <span key={e}>{i > 0 && " · "}<a href={`mailto:${e}`}>{e}</a></span>
                  ))}
                </span>
              )}
              {legal.business.privacy_officer && <span>{tr("shell.biz_privacy_officer")} {legal.business.privacy_officer}</span>}
              {legal.business.hosting && <span>{tr("shell.biz_hosting")} {legal.business.hosting}</span>}
            </div>
          )}
          <p className="app-footer-copy">© {new Date().getFullYear()} {legal?.business?.name || legal?.service_name || tr("brand")}. All rights reserved.</p>
          <p className="app-footer-note">{tr("shell.footer_note")}</p>
        </footer>
      </div>
      <InstallPrompt />
      {me && me.terms_agreed === false && <TermsGate />}
      {me && me.terms_agreed !== false && me.disclaimer_agreed === false && <DisclaimerGate />}
      {me && (
        <button className="consult-fab" onClick={() => setConsultOpen(true)} aria-label={tr("consult.entry_title")}>
          <span className="consult-fab-ic" aria-hidden>💬</span>
          <span className="consult-fab-tx">{tr("consult.chat_default_title")}</span>
        </button>
      )}
      <ConsultationOverlay open={consultOpen} onClose={() => setConsultOpen(false)} />
      {me ? (
        <button className="charge-fab" onClick={() => openCharge()} aria-label={tr("pay.bal_charge", { bal: fmtNum(me.balance ?? 0) })}>
          <span className="cfab-bal">
            <span className="cfab-ic" aria-hidden>💰</span>
            <span className="cfab-amt">{fmtNum(me.balance ?? 0)}<small>{tr("pay.pt")}</small></span>
          </span>
          <span className="cfab-go">＋ {tr("nav.charge")}</span>
        </button>
      ) : !loc.pathname.startsWith("/login") ? (
        <NavLink to="/login" className="login-fab" onClick={() => setNavOpen(false)} aria-label={tr("nav.login")}>
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
            <path fill="currentColor" d="M12 12a5 5 0 100-10 5 5 0 000 10zm0 2c-5 0-9 2.5-9 6v2h18v-2c0-3.5-4-6-9-6z" />
          </svg>
          <span>{tr("nav.login")}</span>
        </NavLink>
      ) : null}
      <ProgressDock />{/* 전역 진행 dock(영상·PDF·감정서). 작업 없을 땐 null → 비로그인도 무해 */}
      {me && idle.warning && (
        <div className="pwa-overlay" role="alertdialog" aria-label={tr("shell.idle_aria")}>
          <div className="pwa-modal">
            <h3>{tr("shell.idle_title")}</h3>
            <p>
              {tr("shell.idle_body")}
              <br />
              <Trans i18nKey="shell.idle_seconds" values={{ n: idle.remaining }} components={{ b: <strong /> }} />
            </p>
            <div className="pwa-actions">
              <button onClick={idle.stayActive}>{tr("shell.idle_stay")}</button>
              <button className="ghost" onClick={forceLogout}>{tr("nav.logout")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

