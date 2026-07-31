import { NavLink, Route, Routes, Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
          <span>{t("brand")}</span>
          <img className="app-brand-seal" src="/brand-seal.png" alt="" width={15} height={15} />
        </Link>
        <button
          className="app-newchat"
          onClick={() => { window.dispatchEvent(new Event("saju:new-chat")); navigate("/chat"); setNavOpen(false); }}
        >
          <Ic name="pencil" /> {t("nav.new_consult")}
        </button>
        <nav className="app-nav">
          <NavLink to="/chat" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="chat" ic="chat" /> {t("nav.consult")}</NavLink>
          <NavLink to="/compatibility" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gunghap" ic="heart" /> {t("nav.compat")}</NavLink>
          <NavLink to="/taekil" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="taekil" ic="calendar" /> {t("nav.taekil")}</NavLink>
          {/* 작명·개명·아호 — VN(xemboi)에선 제외(이름 체계가 달라 로직/검증 불가). ko 빌드만 노출 */}
          {!IS_VN_BUILD && (
            <>
              <NavLink to="/naming/jakmyeong" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="jakmyeong" ic="pen" /> {t("nav.jakmyeong")}</NavLink>
              <NavLink to="/naming/gaemyeong" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gaemyeong" ic="renew" /> {t("nav.gaemyeong")}</NavLink>
              <NavLink to="/naming/aho" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="aho" ic="stamp" /> {t("nav.aho")}</NavLink>
            </>
          )}
          <NavLink to="/tarot" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="tarot" ic="tarot" /> {t("nav.tarot")}</NavLink>
          <NavLink to="/payments" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="bolt" ic="bolt" /> {t("nav.charge")}</NavLink>
          {me && (
            <NavLink to="/settings" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="gear" ic="gear" /> {t("nav.settings")}</NavLink>
          )}
          {isConsultant && (
            <NavLink to="/consultation/console" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><span className="nav-emoji" aria-hidden>💬</span> {t("nav.consultant_console")}</NavLink>
          )}
          {me?.role === "admin" && (
            <>
              <NavLink to="/uploads" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="folder" ic="folder" /> {t("nav.uploads")}</NavLink>
              <NavLink to="/trend" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="chart" ic="chart" /> {t("nav.trend")}</NavLink>
              <NavLink to="/admin" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}><MenuIc k="wrench" ic="wrench" /> {t("nav.admin")}</NavLink>
            </>
          )}
          <NavLink to="/support" onClick={() => setNavOpen(false)} className={({ isActive }) => (isActive ? "active support-nav" : "support-nav")}><MenuIc k="mail" ic="mail" /> {t("nav.support")}</NavLink>
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
            {theme === "dark" ? `☀️ ${t("theme.light")}` : `🌙 ${t("theme.dark")}`}
          </button>
          {me ? (
            <>
              <div className="app-account-name">{me.nickname || me.email}</div>
              <div className="app-account-bal">{me.balance.toLocaleString()} P</div>
              <div className="app-account-actions">
                <button className="ghost" onClick={logout}>{t("nav.logout")}</button>
                <button className="ghost" style={{ color: "#991b1b" }} onClick={withdraw}>{t("nav.withdraw")}</button>
              </div>
            </>
          ) : (
            <NavLink to="/login" className="app-login-btn" onClick={() => setNavOpen(false)}>{t("nav.login")}</NavLink>
          )}
        </div>
      </aside>
      <div className="app-content">
      <LanguageSwitch />{/* VN 빌드에서만 렌더 — 메인화면 상단 고정, VN기본/KR(태극기) 서브. ko 사이트 불변 */}
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
            <Link to="/legal/terms">이용약관</Link>
            <Link to="/legal/privacy" className="footer-strong">개인정보처리방침</Link>
            <Link to="/legal/refund">환불정책</Link>
            <Link to="/legal/disclaimer">면책고지</Link>
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
          <p className="app-footer-copy">© {new Date().getFullYear()} {legal?.business?.name || legal?.service_name || t("brand")}. All rights reserved.</p>
          <p className="app-footer-note">본 서비스 응답은 학습 자료 기반 참고용입니다. 의료·법률·투자 자문이 아닙니다.</p>
        </footer>
      </div>
      <InstallPrompt />
      {me && me.terms_agreed === false && <TermsGate />}
      {me && me.terms_agreed !== false && me.disclaimer_agreed === false && <DisclaimerGate />}
      {me && (
        <button className="consult-fab" onClick={() => setConsultOpen(true)} aria-label="1:1 상담하기">
          <span className="consult-fab-ic" aria-hidden>💬</span>
          <span className="consult-fab-tx">1:1 상담</span>
        </button>
      )}
      <ConsultationOverlay open={consultOpen} onClose={() => setConsultOpen(false)} />
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

