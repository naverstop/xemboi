/** 로그인/회원가입 폼 (공용).
 * - LoginPage(풀스크린)와 ChatPage(사주입력 하단 인라인) 양쪽에서 재사용.
 * - 성공 시 setCachedMe → useMe 반응형 갱신으로 화면 전환. variant="page"는 역할별 이동.
 */
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, setToken, setCachedMe } from "../api";

type Mode = "login" | "register";

export default function LoginForm({
  variant = "page",
  onSuccess,
}: {
  variant?: "page" | "inline";
  onSuccess?: () => void;
}) {
  const nav = useNavigate();
  // 마지막 로그인 이메일만 자동 입력. 비밀번호는 절대 저장하지 않는다(XSS 유출 방지)
  // — 비밀번호 자동완성은 브라우저 비밀번호 관리자(autoComplete)에 맡긴다.
  let savedEmail = "";
  try {
    const saved = JSON.parse(localStorage.getItem("saju_saved_login") || "null");
    savedEmail = (saved && typeof saved.email === "string") ? saved.email : "";
    // 과거 버전이 평문 비밀번호를 저장했음 → 발견 즉시 이메일만 남기고 재기록(정리)
    if (saved && "pw" in saved) {
      localStorage.setItem("saju_saved_login", JSON.stringify({ email: savedEmail }));
    }
  } catch { savedEmail = ""; }
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState(savedEmail);
  const [pw, setPw] = useState("");
  const [nickname, setNickname] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [marketing, setMarketing] = useState(false);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [agreeRefund, setAgreeRefund] = useState(false);
  const [agreeDisclaimer, setAgreeDisclaimer] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false); // 개인정보 수집·이용 요약 펼치기
  const [busy, setBusy] = useState(false);

  // 전체 동의(필수+선택) — 한 번에 토글. 개별 변경 시 자동으로 상태가 동기화된다.
  const allChecked = agreeTerms && agreePrivacy && agreeRefund && agreeDisclaimer && marketing;
  const setAll = (v: boolean) => {
    setAgreeTerms(v); setAgreePrivacy(v); setAgreeRefund(v); setAgreeDisclaimer(v); setMarketing(v);
  };
  const [err, setErr] = useState<string | null>(null);
  const [minAge, setMinAge] = useState(19);

  // 세션 만료/유휴 자동 로그아웃으로 넘어온 경우 안내 배너(?expired=1 / ?idle=1).
  const logoutNotice = (() => {
    try {
      const q = new URLSearchParams(window.location.search);
      if (q.get("expired")) return "로그인 세션이 만료되어 로그아웃되었습니다. 다시 로그인해 주세요.";
      if (q.get("idle")) return "오랫동안 활동이 없어 자동 로그아웃되었습니다. 다시 로그인해 주세요.";
    } catch { /* noop */ }
    return null;
  })();

  useEffect(() => {
    api.legalVersions().then((v) => setMinAge(v.min_age_years)).catch(() => {});
  }, []);

  // 로그인 전에 하려던 일로 돌려보낸다(?next=). 예: 충전하려고 로그인 → 다시 충전 화면.
  // [운영자 지적] 종전엔 무조건 /chat 으로 보내서, 충전하러 로그인한 사용자가 엉뚱한 화면을 만났다.
  // 오픈 리다이렉트 방지: 앱 내부 경로(/로 시작, //·\ 제외)만 허용한다.
  function safeNext(): string | null {
    try {
      const raw = new URLSearchParams(window.location.search).get("next");
      if (!raw) return null;
      const p = decodeURIComponent(raw);
      if (!p.startsWith("/") || p.startsWith("//") || p.startsWith("/\\")) return null;
      if (p.startsWith("/login")) return null;   // 로그인 화면으로 되돌아가는 루프 방지
      return p;
    } catch { return null; }
  }

  function afterAuth(role: string) {
    if (onSuccess) onSuccess();
    const next = safeNext();
    // 관리자라도 돌아갈 곳이 명시돼 있으면 그쪽을 우선(관리자도 충전할 수 있다).
    if (next) { nav(next, { replace: true }); return; }
    if (variant === "page") nav(role === "admin" ? "/admin" : "/chat");
    else if (role === "admin") nav("/admin"); // 인라인이어도 관리자는 관리자 화면으로
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      if (mode === "login") {
        const r = await api.login(email, pw);
        setToken(r.access_token);
        if (r.refresh_token) localStorage.setItem("saju_refresh", r.refresh_token);
        // 마지막 사용 이메일만 저장 → 다음 로그인 화면에서 자동 입력 (비밀번호는 저장 금지)
        localStorage.setItem("saju_saved_login", JSON.stringify({ email }));
        const me = await api.me();
        setCachedMe(me);
        if (me.must_change_password) alert("관리자 초기 비밀번호입니다. 비밀번호를 변경하세요.");
        afterAuth(me.role);
      } else {
        if (!agreeTerms || !agreePrivacy || !agreeRefund || !agreeDisclaimer) {
          throw new Error("필수 약관 및 면책고지에 모두 동의해야 합니다.");
        }
        if (!birthDate) throw new Error("생년월일을 입력해 주세요.");
        const r = await api.register({
          email,
          password: pw,
          nickname: nickname || undefined,
          birth_date: birthDate,
          marketing_opt_in: marketing,
          agree_terms: agreeTerms,
          agree_privacy: agreePrivacy,
          agree_refund: agreeRefund,
          agree_disclaimer: agreeDisclaimer,
        });
        setToken(r.access_token);
        if (r.refresh_token) localStorage.setItem("saju_refresh", r.refresh_token);
        const me = await api.me();
        setCachedMe(me);
        alert("가입을 환영합니다! 1,000P 가입 보너스가 지급되었습니다.");
        afterAuth(me.role);
      }
    } catch (e: any) {
      setErr(e?.message || (mode === "login" ? "로그인 실패" : "가입 실패"));
    } finally {
      setBusy(false);
    }
  }

  async function oauth(provider: "kakao" | "google") {
    setBusy(true);
    setErr(null);
    try {
      const info = await api.oauthStart(provider);
      if (info.mock) {
        const r = await api.oauthTestLogin(provider);
        setToken(r.access_token);
        if (r.refresh_token) localStorage.setItem("saju_refresh", r.refresh_token);
        const me = await api.me();
        setCachedMe(me);
        afterAuth(me.role);
        return;
      }
      // OAuth 는 외부(카카오/구글)로 나갔다 돌아와 URL 쿼리의 next 가 유실된다.
      // 같은 탭에서 유지되는 sessionStorage 로 실어 보내고 OAuthSuccessPage 가 받아 복귀시킨다.
      const nx = safeNext();
      try { if (nx) sessionStorage.setItem("saju_login_next", nx); else sessionStorage.removeItem("saju_login_next"); } catch { /* noop */ }
      window.location.href = info.authorize_url;
    } catch (e: any) {
      setErr(e?.message || `${provider} 로그인 실패`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={variant === "inline" ? "auth-inner auth-inner-inline" : "auth-inner"}>
      <div className="auth-brand">
        <img className="logo-img" src="/pwa-icon.svg" alt="인생상담 친구" width={variant === "inline" ? 48 : 60} height={variant === "inline" ? 48 : 60} />
        <h1>인생상담 친구</h1>
        <p>{variant === "inline" ? "로그인하면 전체 답변과 무료 질문을 받을 수 있어요" : "나의 사주를 묻고, 매일의 운을 읽다"}</p>
      </div>

      <div className="auth-tabs">
        <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")} disabled={mode === "login"}>
          로그인
        </button>
        <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")} disabled={mode === "register"}>
          회원가입
        </button>
      </div>

      {logoutNotice && mode === "login" && (
        <div className="auth-notice" role="status">
          <span aria-hidden="true">🔒</span> {logoutNotice}
        </div>
      )}

      <form onSubmit={submit} className="auth-form">
        <div className="auth-field">
          <label>이메일</label>
          <input className="auth-input" type="email" autoComplete="username" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="auth-field">
          <label>비밀번호</label>
          <input className="auth-input" type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} placeholder={mode === "register" ? "8자 이상 입력" : "비밀번호"} value={pw} onChange={(e) => setPw(e.target.value)} required minLength={mode === "register" ? 8 : undefined} />
        </div>

        {mode === "register" && (
          <>
            <div className="auth-field">
              <label>닉네임 (선택)</label>
              <input className="auth-input" placeholder="표시할 이름" value={nickname} onChange={(e) => setNickname(e.target.value)} />
            </div>
            <div className="auth-field">
              <label>생년월일 (만 {minAge}세 이상)</label>
              <input className="auth-input" type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} required />
            </div>
            <div className="auth-agree">
              <label className="agree-all">
                <input type="checkbox" checked={allChecked} onChange={(e) => setAll(e.target.checked)} />
                <span><b>전체 동의</b> <em>(필수 및 선택 항목 모두 포함)</em></span>
              </label>
              <div className="agree-list">
                <label>
                  <input type="checkbox" checked={agreeTerms} onChange={(e) => setAgreeTerms(e.target.checked)} />
                  <span><i className="req">필수</i> <Link to="/legal/terms" target="_blank">이용약관</Link>에 동의합니다.</span>
                </label>
                <label>
                  <input type="checkbox" checked={agreePrivacy} onChange={(e) => setAgreePrivacy(e.target.checked)} />
                  <span>
                    <i className="req">필수</i> <Link to="/legal/privacy" target="_blank">개인정보 수집·이용</Link>에 동의합니다.
                    <button type="button" className="agree-more" onClick={() => setSummaryOpen((o) => !o)}>
                      {summaryOpen ? "요약 접기" : "요약 보기"}
                    </button>
                  </span>
                </label>
                {summaryOpen && (
                  <div className="agree-summary">
                    <div><b>수집 항목</b> 이메일·비밀번호(암호화)·생년월일(암호화), 사주 입력값·상담 내용, 결제 내역, 접속 기록</div>
                    <div><b>이용 목적</b> 회원 식별·사주 풀이 제공·결제/포인트 운영·문의 대응·법령 준수</div>
                    <div><b>보유 기간</b> 회원 탈퇴 시 지체 없이 파기(전자상거래법 등 법정 보존 항목 제외)</div>
                    <div className="agree-summary-note">동의를 거부할 수 있으나, 필수 항목 미동의 시 회원가입이 제한됩니다.</div>
                  </div>
                )}
                <label>
                  <input type="checkbox" checked={agreeRefund} onChange={(e) => setAgreeRefund(e.target.checked)} />
                  <span><i className="req">필수</i> <Link to="/legal/refund" target="_blank">환불·청약철회 정책</Link>에 동의합니다.</span>
                </label>
                <label>
                  <input type="checkbox" checked={agreeDisclaimer} onChange={(e) => setAgreeDisclaimer(e.target.checked)} />
                  <span><i className="req">필수</i> <Link to="/legal/disclaimer" target="_blank">면책고지</Link>를 확인하였으며 이에 동의합니다.</span>
                </label>
                <label>
                  <input type="checkbox" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
                  <span><i className="opt">선택</i> 이벤트·혜택 등 <b>광고성 정보 수신</b>에 동의합니다. <em>(미동의해도 가입·이용 가능)</em></span>
                </label>
              </div>
              <p className="agree-foot">만 {minAge}세 이상만 가입할 수 있으며, 가입 시 위 필수 항목에 동의한 것으로 봅니다.</p>
            </div>
          </>
        )}

        <button type="submit" className="auth-submit" disabled={busy}>
          {busy ? "처리 중..." : mode === "login" ? "로그인" : "가입하기"}
        </button>
      </form>

      <div className="auth-divider">또는 간편 로그인</div>
      <div className="auth-oauth">
        <button type="button" className="kakao" onClick={() => oauth("kakao")} disabled={busy}>
          <span>💬</span> 카카오로 시작
        </button>
        <button type="button" className="google" onClick={() => oauth("google")} disabled={busy}>
          <span>Ｇ</span> 구글로 시작
        </button>
      </div>

      {err && <div className="auth-err">{err}</div>}

      <div className="auth-foot">
        <Link to="/legal/disclaimer">면책고지</Link>
      </div>
    </div>
  );
}
