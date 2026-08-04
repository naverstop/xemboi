/** 상담사 입점 신청(운영자 지시 2026-07-11) — 분야 선택 → 신청서 → 기능 튜토리얼 → 클릭랩 약관 동의.
 *
 *  법적 설계: 약관 전문은 서버 단일 소스(/api/partner/terms)를 그대로 표시하고,
 *  핵심조항(수수료·정산·해지) 3종을 개별 확인 체크(약관규제법 §3 명시·설명의무).
 *  [입점 신청하기] 클릭 = 동의 — 서버가 전문 스냅샷·버전·해시·시각·IP를 영구 보존.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, useMe, type PartnerTerms, type PartnerApplication, type PartnerInquiry } from "../api";
import PrivacyNotice from "../components/PrivacyNotice";
import { fmtKSTDate } from "../lib/datetime";

// 운영자 확정 프로세스(2026-07-12): 회원가입 → 입점 문의(메일 ID) → 관리자 확인·허용 → 신청서 작성 → 심사·승인
const PROCESS_STEPS: { ic: string; title: string; desc: string }[] = [
  { ic: "1️⃣", title: "회원가입", desc: "입점은 회원 계정(메일 ID) 기준으로 진행돼요." },
  { ic: "2️⃣", title: "입점 문의", desc: "이 페이지에서 문의를 남기면 메일 ID가 관리자에게 전달돼요." },
  { ic: "3️⃣", title: "관리자 확인", desc: "관리자가 확인 후 신청을 허용하면 알림으로 알려드려요." },
  { ic: "4️⃣", title: "신청서 작성 → 승인", desc: "서류(사업자등록증·통장사본) 첨부와 약관 동의 후 심사를 거쳐 입점이 완료돼요." },
];

function ProcessSteps() {
  return (
    <>
      <h3 className="am-step">입점은 이렇게 진행돼요</h3>
      <div className="ptn-features">
        {PROCESS_STEPS.map((s) => (
          <div key={s.title} className="ptn-feature">
            <span className="ptn-ic" aria-hidden>{s.ic}</span>
            <div><b>{s.title}</b><p>{s.desc}</p></div>
          </div>
        ))}
      </div>
    </>
  );
}

const SPECIALTIES: { key: "saju" | "tarot" | "both"; emoji: string; label: string; desc: string }[] = [
  { key: "saju", emoji: "📜", label: "사주 상담사", desc: "명리·사주 기반 1:1 상담" },
  { key: "tarot", emoji: "🃏", label: "타로 상담사", desc: "타로 리딩 기반 1:1 상담" },
  { key: "both", emoji: "✨", label: "사주 + 타로", desc: "두 분야 모두 상담" },
];

// 입점 후 관리하게 될 기능 안내(튜토리얼 수준 — 운영자 지시: 신청자에게 충분히 설명)
const FEATURES: { ic: string; title: string; desc: string }[] = [
  { ic: "🖼️", title: "간판·사진·소개", desc: "승인 후 콘솔에서 상담소 간판 사진, 소개글, #전문 키워드를 직접 등록해요. 사용자 목록 카드에 그대로 노출됩니다." },
  { ic: "💰", title: "요금 설정", desc: "회당·분당·시간당 중 원하는 단위로 요금을 정해요. 결제는 포인트(1P=1원)로 자동 차감되고, 상담이 끝나면 정산 원장에 바로 기록됩니다." },
  { ic: "📅", title: "예약 시간 관리", desc: "상담 가능한 시간대를 슬롯으로 등록하면 사용자가 예약할 수 있어요. 예약은 48시간 전까지 취소·환불됩니다." },
  { ic: "🟢", title: "영업 ON / OFF", desc: "콘솔의 '영업 중' 토글을 켜면 사용자에게 '상담가능'으로 표시되고 실시간 접수를 받아요. 새 요청은 수락/거절할 때까지 소리·알림으로 계속 알려드려요. 끄면 '부재중'으로 표시됩니다." },
  { ic: "📊", title: "내 수익·정산", desc: "콘솔 '내 수익'에서 상담 건수·매출·실지급액을 일/월/년 단위로 확인해요. 매월 25일 마감 → 당월 마지막 영업일에 등록 계좌로 지급됩니다(원천징수 3.3% 공제)." },
];

export default function PartnerApplyPage() {
  const me = useMe();
  const [terms, setTerms] = useState<PartnerTerms | null>(null);
  const [mine, setMine] = useState<PartnerApplication | null>(null);
  const [inquiry, setInquiry] = useState<PartnerInquiry | null>(null);   // 신청 전 게이트(문의) 상태
  const [canApply, setCanApply] = useState(false);                       // 관리자 허용 여부(신청서 작성 자격)
  const [loaded, setLoaded] = useState(false);                           // mine 조회 완료 전 화면 깜빡임 방지
  const [inqNote, setInqNote] = useState("");
  const [inqBusy, setInqBusy] = useState(false);
  const [inqDone, setInqDone] = useState(false);
  const [specialty, setSpecialty] = useState<"saju" | "tarot" | "both" | null>(null);
  const [bizName, setBizName] = useState("");
  const [contact, setContact] = useState("");
  const [intro, setIntro] = useState("");
  const [checks, setChecks] = useState<boolean[]>([]);
  const [bizFile, setBizFile] = useState<File | null>(null);        // 사업자등록증(필수)
  const [bankFile, setBankFile] = useState<File | null>(null);      // 통장사본(필수 — 정산 계좌 확인)
  const [extraFiles, setExtraFiles] = useState<File[]>([]);         // 온라인 입점 증빙(선택, 최대 5)
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const DOC_ACCEPT = ".jpg,.jpeg,.png,.webp,.pdf";
  const DOC_MAX = 10 * 1024 * 1024;
  function pickDoc(f: File | null | undefined): File | null {
    if (!f) return null;
    if (f.size > DOC_MAX) { setErr("파일이 너무 커요 — 파일당 10MB 이하로 첨부해 주세요."); return null; }
    if (!/\.(jpe?g|png|webp|pdf)$/i.test(f.name)) { setErr("이미지(jpg/png/webp) 또는 PDF만 첨부할 수 있어요."); return null; }
    setErr(null);
    return f;
  }
  const fmtSize = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`);

  useEffect(() => {
    api.partnerTerms().then((t) => { setTerms(t); setChecks(t.key_points.map(() => false)); }).catch(() => {});
    if (me) {
      api.partnerApplyMine()
        .then((r) => { setMine(r.application); setInquiry(r.inquiry); setCanApply(r.can_apply); })
        .catch(() => {})
        .finally(() => setLoaded(true));
    } else { setLoaded(true); }
  }, [me?.id]);

  async function submitInquiry() {
    if (!me || inqBusy) return;
    setInqBusy(true); setErr(null);
    try {
      const q = await api.partnerInquiry(inqNote.trim());
      setInquiry(q); setInqDone(true);
      window.dispatchEvent(new CustomEvent("saju:partner-apply-changed"));   // 사이드바 메뉴 즉시 노출
      window.scrollTo(0, 0);
    } catch (e: any) {
      setErr(e?.message || "문의 접수에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally { setInqBusy(false); }
  }

  const allChecked = checks.length > 0 && checks.every(Boolean);
  const canSubmit = !!me && !!specialty && bizName.trim().length >= 2 && !!bizFile && !!bankFile && allChecked && !busy;

  async function submit() {
    if (!canSubmit || !terms || !bizFile || !bankFile) return;
    setBusy(true); setErr(null);
    try {
      const a = await api.partnerApply({
        specialty: specialty!, business_name: bizName.trim(),
        contact: contact.trim() || undefined, intro: intro.trim() || undefined,
        terms_version: terms.version, agree_key_points: true,
        biz_license: bizFile, bank_book: bankFile, extra_docs: extraFiles,
      });
      setMine(a); setDone(true);
      window.dispatchEvent(new CustomEvent("saju:partner-apply-changed"));   // 사이드바 '입점 신청' 메뉴 즉시 노출
      window.scrollTo(0, 0);
    } catch (e: any) {
      setErr(e?.message || "신청에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally { setBusy(false); }
  }

  // ① 비로그인 — 회원가입 유도(운영자 확정 프로세스 1단계)
  if (!me) {
    return (
      <div className="compat-page">
        <PrivacyNotice variant="tool" />
        <header className="compat-hero">
          <div className="compat-hero-badge">入店</div>
          <h1>상담사 입점 문의</h1>
          <p>사주·타로 상담사로 입점해 <b>1:1 유료 상담</b>을 운영해 보세요. 요금은 직접 정하고,
            매월 <b>25일 마감 → 당월 마지막 영업일</b>에 정산됩니다.</p>
        </header>
        <div className="compat-result" style={{ textAlign: "center" }}>
          <h3>먼저 회원가입이 필요해요</h3>
          <p style={{ color: "var(--ink-500)" }}>
            입점은 <b>회원 계정(메일 ID)</b> 기준으로 승인·권한·정산이 관리돼요.<br />
            가입 후 이 페이지에서 입점 문의를 남겨 주세요.
          </p>
          <div className="compat-actions">
            <Link className="compat-cta" to="/login" style={{ textDecoration: "none" }}>회원가입 / 로그인 하기</Link>
          </div>
        </div>
        <ProcessSteps />
      </div>
    );
  }

  if (!loaded) return <div className="compat-page" />;   // 상태 조회 중 — 잘못된 화면 깜빡임 방지

  // 이미 신청/승인된 상태 — 현황 안내
  if (mine && !done) {
    return (
      <div className="compat-page">
        <PrivacyNotice variant="tool" />
        <header className="compat-hero">
          <div className="compat-hero-badge">入店</div>
          <h1>상담사 입점 신청</h1>
        </header>
        <div className="compat-result" style={{ textAlign: "center" }}>
          {mine.status === "pending" && (
            <>
              <h3>⏳ 심사 대기 중이에요</h3>
              <p style={{ color: "var(--ink-500)" }}>
                {fmtKSTDate(mine.created_at)} 접수 · {mine.business_name} ({mine.specialty === "saju" ? "사주" : mine.specialty === "tarot" ? "타로" : "사주+타로"})<br />
                승인되면 알림으로 바로 알려드릴게요.
              </p>
            </>
          )}
          {mine.status === "approved" && (
            <>
              <h3>🎉 입점이 승인됐어요!</h3>
              <p style={{ color: "var(--ink-500)" }}>콘솔에서 간판·요금·예약시간을 설정하고 영업을 시작해 보세요.</p>
              <div className="compat-actions">
                <Link className="compat-cta" to="/consultation/console" style={{ textDecoration: "none" }}>🛠️ 상담사 콘솔 열기</Link>
              </div>
            </>
          )}
          {mine.status === "rejected" && (
            <>
              <h3>이번 신청은 승인되지 않았어요</h3>
              {mine.reject_reason && <p style={{ color: "var(--ink-500)" }}>사유: {mine.reject_reason}</p>}
              <p style={{ color: "var(--ink-400)", fontSize: 13 }}>보완 후 다시 신청하실 수 있어요.</p>
              <div className="compat-actions">
                <button className="compat-cta" onClick={() => setMine(null)}>다시 신청하기</button>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // ② 신청 자격 없음 — 입점 문의 게이트(운영자 확정: 관리자 허용 후에만 신청서 작성)
  if (!done && !canApply) {
    return (
      <div className="compat-page">
        <PrivacyNotice variant="tool" />
        <header className="compat-hero">
          <div className="compat-hero-badge">入店</div>
          <h1>상담사 입점 문의</h1>
          <p>사주·타로 상담사로 입점해 <b>1:1 유료 상담</b>을 운영해 보세요. 요금은 직접 정하고,
            매월 <b>25일 마감 → 당월 마지막 영업일</b>에 정산됩니다.</p>
        </header>

        {inquiry?.status === "pending" ? (
          <div className="compat-result" style={{ textAlign: "center" }}>
            <h3>{inqDone ? "📨 입점 문의가 접수됐어요!" : "⏳ 관리자 확인 중이에요"}</h3>
            <p style={{ color: "var(--ink-500)" }}>
              {fmtKSTDate(inquiry.created_at)} 접수 · <b>{inquiry.email}</b><br />
              관리자가 확인 후 신청을 허용하면 알림으로 알려드릴게요. 허용되면 이 페이지에서 바로 신청서를 작성할 수 있어요.
            </p>
          </div>
        ) : inquiry?.status === "dismissed" ? (
          <div className="compat-result" style={{ textAlign: "center" }}>
            <h3>이번에는 입점 진행이 어려워요</h3>
            {inquiry.decide_note && <p style={{ color: "var(--ink-500)" }}>사유: {inquiry.decide_note}</p>}
            <p style={{ color: "var(--ink-400)", fontSize: 13 }}>보완 후 다시 문의하실 수 있어요.</p>
            <div className="compat-actions">
              <button className="compat-cta" onClick={() => { setInquiry(null); setInqDone(false); }}>다시 문의하기</button>
            </div>
          </div>
        ) : (
          <>
            <h3 className="am-step">1. 입점 문의를 남겨 주세요</h3>
            <div className="tool-form">
              <p className="pc-hint" style={{ marginTop: 0 }}>
                문의 계정: <b>{me.email}</b> — 이 메일 ID가 관리자에게 전달되고, 승인·권한·정산의 기준이 됩니다.
              </p>
              <div className="bf-field">
                <label>남기실 말 (선택 — 경력·활동 플랫폼·연락처 등)</label>
                <textarea className="bf-input" rows={4} maxLength={2000}
                          placeholder="예: 사주 상담 경력 10년, OO플랫폼에서 활동 중입니다. 연락처는 010-…"
                          value={inqNote} onChange={(e) => setInqNote(e.target.value)} />
              </div>
            </div>
            <div className="compat-actions">
              <button className="compat-cta" disabled={inqBusy} onClick={submitInquiry}>
                {inqBusy ? "접수 중…" : "📨 입점 문의 남기기"}
              </button>
              <div className="cta-hint">관리자 확인 후 신청서 작성이 열려요</div>
            </div>
            {err && <div className="compat-err">{err}</div>}
            <ProcessSteps />
          </>
        )}
      </div>
    );
  }

  // ③ 신청 자격 있음(관리자 허용/재신청) — 신청서 작성
  return (
    <div className="compat-page">
      <PrivacyNotice variant="tool" />
      <header className="compat-hero">
        <div className="compat-hero-badge">入店</div>
        <h1>상담사 입점 신청</h1>
        <p>사주·타로 상담사로 입점해 <b>1:1 유료 상담</b>을 운영해 보세요. 요금은 직접 정하고,
          매월 <b>25일 마감 → 당월 마지막 영업일</b>에 정산됩니다.</p>
      </header>

      {!done && (
        <div className="compat-result" style={{ textAlign: "center", marginBottom: 18 }}>
          <h3>✅ 관리자 확인이 완료됐어요</h3>
          <p style={{ color: "var(--ink-500)" }}>아래 신청서를 작성해 주세요 — 서류 첨부와 약관 동의 후 심사가 시작됩니다.</p>
        </div>
      )}

      {done && (
        <div className="compat-result" style={{ textAlign: "center", marginBottom: 18 }}>
          <h3>✅ 신청이 접수됐어요!</h3>
          <p style={{ color: "var(--ink-500)" }}>관리자 승인 후 알림으로 알려드릴게요. 승인되면 바로 콘솔에서 영업을 시작할 수 있어요.</p>
        </div>
      )}

      {!done && (
        <>
          <h3 className="am-step">1. 분야를 선택해 주세요</h3>
          <div className="am-purposes" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            {SPECIALTIES.map((s) => (
              <button key={s.key} className={`am-purpose${specialty === s.key ? " on" : ""}`} onClick={() => setSpecialty(s.key)}>
                <span className="am-emoji" aria-hidden>{s.emoji}</span>
                <b>{s.label}</b>
                <span className="am-desc">{s.desc}</span>
              </button>
            ))}
          </div>

          <h3 className="am-step">2. 신청 정보를 입력해 주세요</h3>
          <div className="tool-form">
            <div className="bf-field">
              <label>상담소(간판) 이름 *</label>
              <input className="bf-input" maxLength={120} placeholder="예: 달빛 사주상담소" value={bizName} onChange={(e) => setBizName(e.target.value)} />
            </div>
            <div className="bf-field">
              <label>연락처 (선택 — 심사·정산 안내용)</label>
              <input className="bf-input" maxLength={64} placeholder="예: 010-1234-5678" value={contact} onChange={(e) => setContact(e.target.value)} />
            </div>
            <div className="bf-field">
              <label>소개·경력 (선택)</label>
              <textarea className="bf-input" rows={4} maxLength={2000}
                        placeholder="상담 경력, 전문 분야, 자격 등을 자유롭게 적어 주세요. 심사에 참고됩니다."
                        value={intro} onChange={(e) => setIntro(e.target.value)} />
            </div>
            {me && <p className="pc-hint">신청 계정: <b>{me.email}</b> — 이 메일 ID 기준으로 승인·권한 부여·해지가 관리됩니다.</p>}
          </div>

          <h3 className="am-step">3. 심사 서류를 첨부해 주세요</h3>
          <div className="tool-form">
            <div className="bf-field">
              <label>사업자등록증 * <span className="ptn-doc-hint">이미지(jpg/png/webp) 또는 PDF · 10MB 이하</span></label>
              {bizFile ? (
                <div className="ptn-doc-row">
                  <span className="ptn-doc-ic" aria-hidden>📄</span>
                  <span className="ptn-doc-name">{bizFile.name}</span>
                  <span className="ptn-doc-size">{fmtSize(bizFile.size)}</span>
                  <button type="button" className="ptn-doc-x" aria-label="첨부 삭제" onClick={() => setBizFile(null)}>✕</button>
                </div>
              ) : (
                <label className="ptn-doc-add">
                  <input type="file" accept={DOC_ACCEPT} style={{ display: "none" }}
                         onChange={(e) => { setBizFile(pickDoc(e.target.files?.[0])); e.target.value = ""; }} />
                  📎 사업자등록증 첨부하기
                </label>
              )}
            </div>
            <div className="bf-field">
              <label>통장사본 * <span className="ptn-doc-hint">정산 대금 지급 계좌 확인용 · 이미지 또는 PDF · 10MB 이하</span></label>
              {bankFile ? (
                <div className="ptn-doc-row">
                  <span className="ptn-doc-ic" aria-hidden>🏦</span>
                  <span className="ptn-doc-name">{bankFile.name}</span>
                  <span className="ptn-doc-size">{fmtSize(bankFile.size)}</span>
                  <button type="button" className="ptn-doc-x" aria-label="첨부 삭제" onClick={() => setBankFile(null)}>✕</button>
                </div>
              ) : (
                <label className="ptn-doc-add">
                  <input type="file" accept={DOC_ACCEPT} style={{ display: "none" }}
                         onChange={(e) => { setBankFile(pickDoc(e.target.files?.[0])); e.target.value = ""; }} />
                  📎 통장사본 첨부하기
                </label>
              )}
            </div>
            <div className="bf-field">
              <label>온라인 입점 증빙 (선택 · 최대 5개) <span className="ptn-doc-hint">타 플랫폼 입점 화면·자격증·경력 증빙 등</span></label>
              {extraFiles.map((f, i) => (
                <div key={i} className="ptn-doc-row">
                  <span className="ptn-doc-ic" aria-hidden>📄</span>
                  <span className="ptn-doc-name">{f.name}</span>
                  <span className="ptn-doc-size">{fmtSize(f.size)}</span>
                  <button type="button" className="ptn-doc-x" aria-label="첨부 삭제"
                          onClick={() => setExtraFiles((cur) => cur.filter((_, j) => j !== i))}>✕</button>
                </div>
              ))}
              {extraFiles.length < 5 && (
                <label className="ptn-doc-add">
                  <input type="file" accept={DOC_ACCEPT} multiple style={{ display: "none" }}
                         onChange={(e) => {
                           const picked = Array.from(e.target.files || []).map((f) => pickDoc(f)).filter((f): f is File => !!f);
                           if (picked.length) setExtraFiles((cur) => [...cur, ...picked].slice(0, 5));
                           e.target.value = "";
                         }} />
                  📎 증빙 서류 추가하기
                </label>
              )}
              <p className="pc-hint">첨부 서류는 입점 심사에만 사용되며, 관리자만 열람할 수 있어요.</p>
            </div>
          </div>

          <h3 className="am-step">4. 입점하면 이런 걸 관리하게 돼요</h3>
          <div className="ptn-features">
            {FEATURES.map((f) => (
              <div key={f.title} className="ptn-feature">
                <span className="ptn-ic" aria-hidden>{f.ic}</span>
                <div><b>{f.title}</b><p>{f.desc}</p></div>
              </div>
            ))}
          </div>

          <h3 className="am-step">5. 입점 약관 (정산·수수료·지급 방식)</h3>
          {terms ? (
            <>
              <div className="ptn-terms" role="document" aria-label="입점 이용약관 전문">
                <pre>{terms.text}</pre>
              </div>
              <div className="ptn-checks">
                {terms.key_points.map((kp, i) => (
                  <label key={i} className="ptn-check">
                    <input type="checkbox" checked={checks[i] || false}
                           onChange={(e) => setChecks((cur) => cur.map((v, j) => (j === i ? e.target.checked : v)))} />
                    <span>{kp}</span>
                  </label>
                ))}
              </div>
              <p className="ptn-note">
                아래 <b>[입점 신청하기]</b>를 누르는 순간 위 약관 전문(버전 {terms.version})에 동의한 것으로 보며,
                동의 일시·계정·약관 버전이 전자적으로 보존됩니다. 동의한 전문은 이 페이지에서 언제든 다시 확인할 수 있어요.
              </p>
            </>
          ) : (
            <p style={{ color: "var(--ink-400)" }}>약관을 불러오는 중…</p>
          )}

          <div className="compat-actions">
            <button className="compat-cta" disabled={!canSubmit} onClick={submit}>
              {busy ? "접수 중…" : "🤝 입점 신청하기 (약관 동의)"}
            </button>
            {!specialty ? <div className="cta-hint">분야를 선택해 주세요</div>
              : bizName.trim().length < 2 ? <div className="cta-hint">상담소 이름을 입력해 주세요</div>
              : !bizFile ? <div className="cta-hint">사업자등록증을 첨부해 주세요</div>
              : !bankFile ? <div className="cta-hint">통장사본을 첨부해 주세요</div>
              : !allChecked ? <div className="cta-hint">핵심 조항 3가지를 모두 확인해 주세요</div> : null}
          </div>
          {err && <div className="compat-err">{err}</div>}
        </>
      )}
    </div>
  );
}
