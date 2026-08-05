/** 상담사 입점 신청(운영자 지시 2026-07-11) — 분야 선택 → 신청서 → 기능 튜토리얼 → 클릭랩 약관 동의.
 *
 *  법적 설계: 약관 전문은 서버 단일 소스(/api/partner/terms)를 그대로 표시하고,
 *  핵심조항(수수료·정산·해지) 3종을 개별 확인 체크(약관규제법 §3 명시·설명의무).
 *  [입점 신청하기] 클릭 = 동의 — 서버가 전문 스냅샷·버전·해시·시각·IP를 영구 보존.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import { api, useMe, type PartnerTerms, type PartnerApplication, type PartnerInquiry } from "../api";
import PrivacyNotice from "../components/PrivacyNotice";
import { fmtKSTDate } from "../lib/datetime";

// 운영자 확정 프로세스(2026-07-12): 회원가입 → 입점 문의(메일 ID) → 관리자 확인·허용 → 신청서 작성 → 심사·승인
// title/desc 는 i18n 키(common.partner.*) — 렌더 시 tr() 로 해석해 언어 전환에 즉시 반응.
const PROCESS_STEPS: { ic: string; title: string; desc: string }[] = [
  { ic: "1️⃣", title: "partner.step1_t", desc: "partner.step1_d" },
  { ic: "2️⃣", title: "partner.step2_t", desc: "partner.step2_d" },
  { ic: "3️⃣", title: "partner.step3_t", desc: "partner.step3_d" },
  { ic: "4️⃣", title: "partner.step4_t", desc: "partner.step4_d" },
];

function ProcessSteps() {
  const { t: tr } = useTranslation();
  return (
    <>
      <h3 className="am-step">{tr("partner.steps_title")}</h3>
      <div className="ptn-features">
        {PROCESS_STEPS.map((s) => (
          <div key={s.title} className="ptn-feature">
            <span className="ptn-ic" aria-hidden>{s.ic}</span>
            <div><b>{tr(s.title)}</b><p>{tr(s.desc)}</p></div>
          </div>
        ))}
      </div>
    </>
  );
}

const SPECIALTIES: { key: "saju" | "tarot" | "both"; emoji: string; label: string; desc: string }[] = [
  { key: "saju", emoji: "📜", label: "partner.sp_saju", desc: "partner.sp_saju_d" },
  { key: "tarot", emoji: "🃏", label: "partner.sp_tarot", desc: "partner.sp_tarot_d" },
  { key: "both", emoji: "✨", label: "partner.sp_both", desc: "partner.sp_both_d" },
];

// 입점 후 관리하게 될 기능 안내(튜토리얼 수준 — 운영자 지시: 신청자에게 충분히 설명)
const FEATURES: { ic: string; title: string; desc: string }[] = [
  { ic: "🖼️", title: "partner.ft1_t", desc: "partner.ft1_d" },
  { ic: "💰", title: "partner.ft2_t", desc: "partner.ft2_d" },
  { ic: "📅", title: "partner.ft3_t", desc: "partner.ft3_d" },
  { ic: "🟢", title: "partner.ft4_t", desc: "partner.ft4_d" },
  { ic: "📊", title: "partner.ft5_t", desc: "partner.ft5_d" },
];

export default function PartnerApplyPage() {
  const { t: tr } = useTranslation();
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
    if (f.size > DOC_MAX) { setErr(tr("partner.err_file_big")); return null; }
    if (!/\.(jpe?g|png|webp|pdf)$/i.test(f.name)) { setErr(tr("partner.err_file_type")); return null; }
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
      setErr(e?.message || tr("partner.err_inquiry"));
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
      setErr(e?.message || tr("partner.err_apply"));
    } finally { setBusy(false); }
  }

  // ① 비로그인 — 회원가입 유도(운영자 확정 프로세스 1단계)
  if (!me) {
    return (
      <div className="compat-page">
        <PrivacyNotice variant="tool" />
        <header className="compat-hero">
          <div className="compat-hero-badge">{tr("partner.hero_badge")}</div>
          <h1>{tr("partner.hero_title_inquiry")}</h1>
          <p><Trans i18nKey="partner.hero_desc" components={{ b: <b /> }} /></p>
        </header>
        <div className="compat-result" style={{ textAlign: "center" }}>
          <h3>{tr("partner.login_title")}</h3>
          <p style={{ color: "var(--ink-500)" }}>
            <Trans i18nKey="partner.login_desc" components={{ b: <b />, br: <br /> }} />
          </p>
          <div className="compat-actions">
            <Link className="compat-cta" to="/login" style={{ textDecoration: "none" }}>{tr("partner.login_cta")}</Link>
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
          <div className="compat-hero-badge">{tr("partner.hero_badge")}</div>
          <h1>{tr("partner.hero_title_apply")}</h1>
        </header>
        <div className="compat-result" style={{ textAlign: "center" }}>
          {mine.status === "pending" && (
            <>
              <h3>{tr("partner.pending_title")}</h3>
              <p style={{ color: "var(--ink-500)" }}>
                {tr("partner.pending_meta", {
                  date: fmtKSTDate(mine.created_at), name: mine.business_name,
                  sp: mine.specialty === "saju" ? tr("partner.sp_short_saju") : mine.specialty === "tarot" ? tr("partner.sp_short_tarot") : tr("partner.sp_short_both"),
                })}<br />
                {tr("partner.pending_note")}
              </p>
            </>
          )}
          {mine.status === "approved" && (
            <>
              <h3>{tr("partner.approved_title")}</h3>
              <p style={{ color: "var(--ink-500)" }}>{tr("partner.approved_desc")}</p>
              <div className="compat-actions">
                <Link className="compat-cta" to="/consultation/console" style={{ textDecoration: "none" }}>{tr("partner.console_cta")}</Link>
              </div>
            </>
          )}
          {mine.status === "rejected" && (
            <>
              <h3>{tr("partner.rejected_title")}</h3>
              {mine.reject_reason && <p style={{ color: "var(--ink-500)" }}>{tr("partner.reason", { reason: mine.reject_reason })}</p>}
              <p style={{ color: "var(--ink-400)", fontSize: 13 }}>{tr("partner.rejected_note")}</p>
              <div className="compat-actions">
                <button className="compat-cta" onClick={() => setMine(null)}>{tr("partner.reapply")}</button>
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
          <div className="compat-hero-badge">{tr("partner.hero_badge")}</div>
          <h1>{tr("partner.hero_title_inquiry")}</h1>
          <p><Trans i18nKey="partner.hero_desc" components={{ b: <b /> }} /></p>
        </header>

        {inquiry?.status === "pending" ? (
          <div className="compat-result" style={{ textAlign: "center" }}>
            <h3>{inqDone ? tr("partner.inq_done_title") : tr("partner.inq_pending_title")}</h3>
            <p style={{ color: "var(--ink-500)" }}>
              <Trans i18nKey="partner.inq_meta" values={{ date: fmtKSTDate(inquiry.created_at), email: inquiry.email }} components={{ b: <b /> }} /><br />
              {tr("partner.inq_note")}
            </p>
          </div>
        ) : inquiry?.status === "dismissed" ? (
          <div className="compat-result" style={{ textAlign: "center" }}>
            <h3>{tr("partner.dismissed_title")}</h3>
            {inquiry.decide_note && <p style={{ color: "var(--ink-500)" }}>{tr("partner.reason", { reason: inquiry.decide_note })}</p>}
            <p style={{ color: "var(--ink-400)", fontSize: 13 }}>{tr("partner.dismissed_note")}</p>
            <div className="compat-actions">
              <button className="compat-cta" onClick={() => { setInquiry(null); setInqDone(false); }}>{tr("partner.reinquiry")}</button>
            </div>
          </div>
        ) : (
          <>
            <h3 className="am-step">{tr("partner.inq_step_title")}</h3>
            <div className="tool-form">
              <p className="pc-hint" style={{ marginTop: 0 }}>
                <Trans i18nKey="partner.inq_account" values={{ email: me.email }} components={{ b: <b /> }} />
              </p>
              <div className="bf-field">
                <label>{tr("partner.inq_note_label")}</label>
                <textarea className="bf-input" rows={4} maxLength={2000}
                          placeholder={tr("partner.inq_ph")}
                          value={inqNote} onChange={(e) => setInqNote(e.target.value)} />
              </div>
            </div>
            <div className="compat-actions">
              <button className="compat-cta" disabled={inqBusy} onClick={submitInquiry}>
                {inqBusy ? tr("partner.submitting") : tr("partner.inq_cta")}
              </button>
              <div className="cta-hint">{tr("partner.inq_hint")}</div>
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
        <div className="compat-hero-badge">{tr("partner.hero_badge")}</div>
        <h1>{tr("partner.hero_title_apply")}</h1>
        <p><Trans i18nKey="partner.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      {!done && (
        <div className="compat-result" style={{ textAlign: "center", marginBottom: 18 }}>
          <h3>{tr("partner.ok_title")}</h3>
          <p style={{ color: "var(--ink-500)" }}>{tr("partner.ok_desc")}</p>
        </div>
      )}

      {done && (
        <div className="compat-result" style={{ textAlign: "center", marginBottom: 18 }}>
          <h3>{tr("partner.done_title")}</h3>
          <p style={{ color: "var(--ink-500)" }}>{tr("partner.done_desc")}</p>
        </div>
      )}

      {!done && (
        <>
          <h3 className="am-step">{tr("partner.s1_title")}</h3>
          <div className="am-purposes" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            {SPECIALTIES.map((s) => (
              <button key={s.key} className={`am-purpose${specialty === s.key ? " on" : ""}`} onClick={() => setSpecialty(s.key)}>
                <span className="am-emoji" aria-hidden>{s.emoji}</span>
                <b>{tr(s.label)}</b>
                <span className="am-desc">{tr(s.desc)}</span>
              </button>
            ))}
          </div>

          <h3 className="am-step">{tr("partner.s2_title")}</h3>
          <div className="tool-form">
            <div className="bf-field">
              <label>{tr("partner.biz_label")}</label>
              <input className="bf-input" maxLength={120} placeholder={tr("partner.biz_ph")} value={bizName} onChange={(e) => setBizName(e.target.value)} />
            </div>
            <div className="bf-field">
              <label>{tr("partner.contact_label")}</label>
              <input className="bf-input" maxLength={64} placeholder={tr("partner.contact_ph")} value={contact} onChange={(e) => setContact(e.target.value)} />
            </div>
            <div className="bf-field">
              <label>{tr("partner.intro_label")}</label>
              <textarea className="bf-input" rows={4} maxLength={2000}
                        placeholder={tr("partner.intro_ph")}
                        value={intro} onChange={(e) => setIntro(e.target.value)} />
            </div>
            {me && <p className="pc-hint"><Trans i18nKey="partner.apply_account" values={{ email: me.email }} components={{ b: <b /> }} /></p>}
          </div>

          <h3 className="am-step">{tr("partner.s3_title")}</h3>
          <div className="tool-form">
            <div className="bf-field">
              <label>{tr("partner.doc_biz_label")} <span className="ptn-doc-hint">{tr("partner.doc_hint_type")}</span></label>
              {bizFile ? (
                <div className="ptn-doc-row">
                  <span className="ptn-doc-ic" aria-hidden>📄</span>
                  <span className="ptn-doc-name">{bizFile.name}</span>
                  <span className="ptn-doc-size">{fmtSize(bizFile.size)}</span>
                  <button type="button" className="ptn-doc-x" aria-label={tr("partner.doc_remove")} onClick={() => setBizFile(null)}>✕</button>
                </div>
              ) : (
                <label className="ptn-doc-add">
                  <input type="file" accept={DOC_ACCEPT} style={{ display: "none" }}
                         onChange={(e) => { setBizFile(pickDoc(e.target.files?.[0])); e.target.value = ""; }} />
                  {tr("partner.doc_biz_add")}
                </label>
              )}
            </div>
            <div className="bf-field">
              <label>{tr("partner.doc_bank_label")} <span className="ptn-doc-hint">{tr("partner.doc_bank_hint")}</span></label>
              {bankFile ? (
                <div className="ptn-doc-row">
                  <span className="ptn-doc-ic" aria-hidden>🏦</span>
                  <span className="ptn-doc-name">{bankFile.name}</span>
                  <span className="ptn-doc-size">{fmtSize(bankFile.size)}</span>
                  <button type="button" className="ptn-doc-x" aria-label={tr("partner.doc_remove")} onClick={() => setBankFile(null)}>✕</button>
                </div>
              ) : (
                <label className="ptn-doc-add">
                  <input type="file" accept={DOC_ACCEPT} style={{ display: "none" }}
                         onChange={(e) => { setBankFile(pickDoc(e.target.files?.[0])); e.target.value = ""; }} />
                  {tr("partner.doc_bank_add")}
                </label>
              )}
            </div>
            <div className="bf-field">
              <label>{tr("partner.doc_extra_label")} <span className="ptn-doc-hint">{tr("partner.doc_extra_hint")}</span></label>
              {extraFiles.map((f, i) => (
                <div key={i} className="ptn-doc-row">
                  <span className="ptn-doc-ic" aria-hidden>📄</span>
                  <span className="ptn-doc-name">{f.name}</span>
                  <span className="ptn-doc-size">{fmtSize(f.size)}</span>
                  <button type="button" className="ptn-doc-x" aria-label={tr("partner.doc_remove")}
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
                  {tr("partner.doc_extra_add")}
                </label>
              )}
              <p className="pc-hint">{tr("partner.doc_privacy")}</p>
            </div>
          </div>

          <h3 className="am-step">{tr("partner.s4_title")}</h3>
          <div className="ptn-features">
            {FEATURES.map((f) => (
              <div key={f.title} className="ptn-feature">
                <span className="ptn-ic" aria-hidden>{f.ic}</span>
                <div><b>{tr(f.title)}</b><p>{tr(f.desc)}</p></div>
              </div>
            ))}
          </div>

          <h3 className="am-step">{tr("partner.s5_title")}</h3>
          {terms ? (
            <>
              <div className="ptn-terms" role="document" aria-label={tr("partner.terms_aria")}>
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
                <Trans i18nKey="partner.terms_note" values={{ version: terms.version }} components={{ b: <b /> }} />
              </p>
            </>
          ) : (
            <p style={{ color: "var(--ink-400)" }}>{tr("partner.terms_loading")}</p>
          )}

          <div className="compat-actions">
            <button className="compat-cta" disabled={!canSubmit} onClick={submit}>
              {busy ? tr("partner.submitting") : tr("partner.apply_cta")}
            </button>
            {!specialty ? <div className="cta-hint">{tr("partner.hint_specialty")}</div>
              : bizName.trim().length < 2 ? <div className="cta-hint">{tr("partner.hint_bizname")}</div>
              : !bizFile ? <div className="cta-hint">{tr("partner.hint_bizfile")}</div>
              : !bankFile ? <div className="cta-hint">{tr("partner.hint_bankfile")}</div>
              : !allChecked ? <div className="cta-hint">{tr("partner.hint_checks")}</div> : null}
          </div>
          {err && <div className="compat-err">{err}</div>}
        </>
      )}
    </div>
  );
}
