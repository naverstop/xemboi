/** 택일 — 생년월일 + 용도 + 기간 → 길일 추천. */
import { useEffect, useRef, useState } from "react";
import { api, useMe, PURPOSE_LABELS, type Birth, type TaekilPurpose, type ToolResponse } from "../api";
import { useEnsureEntry, EntryFeeNotice } from "../components/ChargeModal";
import { resolveBirthTime } from "../lib/birthTime";
import ExplainChat from "../components/ExplainChat";
import BirthFields, { profileToBirthValue, type BirthValue } from "../components/BirthFields";
import { useTranslation, Trans } from "react-i18next";
import { fmtNum } from "../lib/money";
import i18n from "../i18n";

const PURPOSES = Object.keys(PURPOSE_LABELS) as TaekilPurpose[];

// 상담서 PDF 본문 상단 요약 — 추천 길일 목록
function taekilPdfHeader(r: any): string {
  const best = (r?.best || []).slice(0, 8);
  if (!best.length) return "";
  const lines = best.map((d: any) => i18n.t("taekil.pdf_line", { date: d.date, ganzhi: d.ganzhi, score: fmtNum(d.score), grade: d.grade }));
  return i18n.t("taekil.pdf_header_title") + "\n" + lines.join("\n");
}

// 용도별 아이콘 (럭셔리 칩 그리드)
const PURPOSE_ICONS: Record<TaekilPurpose, string> = {
  wedding: "💍", birth: "👶", moving: "📦", opening: "🎉", contract: "🤝",
  ceremony: "🕯️", surgery: "🏥", travel: "✈️", general: "🗓️",
};

// 용도별 한 줄 설명(선택 시 안내).
// ※ 엔진은 황도흑도·사주(충형회피/출산은 궁합)·손없는날 3요소만 계산하고
//    용도별로 '가중치'만 다름 → 설명은 가중치 강조점을 그대로 반영(과장 금지).
const PURPOSE_DESC: Record<TaekilPurpose, string> = {
  wedding: "taekil.desc_wedding", birth: "taekil.desc_birth", moving: "taekil.desc_moving",
  opening: "taekil.desc_opening", contract: "taekil.desc_contract", ceremony: "taekil.desc_ceremony",
  surgery: "taekil.desc_surgery", travel: "taekil.desc_travel", general: "taekil.desc_general",
};

export default function TaekilPage() {
  const { t: tr } = useTranslation();
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false , apply_true_solar_time: true, birth_longitude: 126.98 });
  const [b2, setB2] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "female", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  const [purpose, setPurpose] = useState<TaekilPurpose>("wedding");
  const [startDate, setStartDate] = useState("");
  const [days, setDays] = useState(60);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<ToolResponse | null>(null);

  // 로그인 사용자: 저장된 본인 사주 자동 채움(사용자별 1회)
  const me = useMe();
  const ensureEntry = useEnsureEntry();
  // 상담서 제목/대상 표기 — 로그인 시 회원명, 아니면 "접속자"
  const who = (me?.nickname?.trim() || (me?.email ? me.email.split("@")[0] : "")) || tr("taekil.visitor");
  const filledFor = useRef<number | null>(null);
  useEffect(() => {
    if (!me?.saju_profile?.birth_date || filledFor.current === me.id) return;
    filledFor.current = me.id;
    setB((prev) => ({ ...prev, ...profileToBirthValue(me.saju_profile) }));
  }, [me]);

  async function submit() {
    if (!ensureEntry("taekil")) return;
    setErr(null); setLoading(true); setRes(null);
    const birth: Birth = {
      birth_date: b.birth_date, birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
      calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
      apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
      birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
    };
    const birth2: Birth | null = (purpose === "birth" && b2.birth_date) ? {
      birth_date: b2.birth_date, birth_time: resolveBirthTime(b2.birth_time, b2.unknown_time),
      calendar: b2.calendar, gender: b2.gender, is_leap_month: b2.calendar === "lunar" ? b2.is_leap_month : false,
      apply_true_solar_time: !!b2.apply_true_solar_time, night_zi_mode: b2.night_zi_mode ?? "yaja",
      birth_longitude: b2.birth_longitude ?? null, apply_equation_of_time: !!b2.apply_equation_of_time,
    } : null;
    try {
      const out = await api.createTaekil({
        birth, birth2, purpose,
        start_date: startDate || new Date().toISOString().slice(0, 10),
        days,
      });
      setRes(out);
      setTimeout(() => document.getElementById("tool-result")?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (e: any) {
      setErr(e?.message || tr("taekil.fail"));
    } finally { setLoading(false); }
  }

  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">擇日</div>
        <h1>{tr("taekil.hero_title")}</h1>
        <p><Trans i18nKey="taekil.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      <div className="tool-form">
        <div className="bf-field">
          <label>{tr("taekil.label_purpose")}</label>
          <div className="purpose-grid" role="radiogroup" aria-label={tr("taekil.aria_purpose")}>
            {PURPOSES.map((p) => (
              <button key={p} type="button" role="radio" aria-checked={purpose === p}
                      className={`purpose-chip ${purpose === p ? "on" : ""}`}
                      onClick={() => setPurpose(p)}>
                <span className="pp-icon">{PURPOSE_ICONS[p]}</span>
                <span className="pp-label">{PURPOSE_LABELS[p]}</span>
              </button>
            ))}
          </div>
          <div className="pc-hint" style={{ marginTop: 8 }}>
            {purpose === "birth"
              ? <Trans i18nKey="taekil.birth_hint" components={{ b: <b /> }} />
              : tr(PURPOSE_DESC[purpose])}
          </div>
        </div>
        <EntryFeeNotice menu="taekil" />
        {purpose === "birth" && <div className="pc-flabel" style={{ marginTop: 4 }}>{tr("taekil.parent1")}</div>}
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} />
        {purpose === "birth" && (
          <>
            <div className="pc-flabel" style={{ marginTop: 6 }}>{tr("taekil.parent2")} <span style={{ fontWeight: 400, color: "var(--ink-400)" }}>{tr("taekil.parent2_opt")}</span></div>
            <BirthFields value={b2} onChange={(patch) => setB2((prev) => ({ ...prev, ...patch }))} />
          </>
        )}
        <div className="bf-field">
          <label>{tr("taekil.label_period")}</label>
          <div className="bf-time">
            <input className="bf-input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <select className="bf-input" style={{ flex: "0 0 110px" }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={30}>{tr("taekil.days_opt", { n: 30 })}</option><option value={60}>{tr("taekil.days_opt", { n: 60 })}</option><option value={90}>{tr("taekil.days_opt", { n: 90 })}</option>
            </select>
          </div>
        </div>
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || loading} onClick={submit}>
          {loading ? tr("taekil.analyzing") : tr("taekil.cta")}
        </button>
        {!b.birth_date && <div className="cta-hint">{tr("taekil.cta_hint")}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <div id="tool-result" className="compat-result">
          <div className="cr-headline">
            <span className="cr-names">{res.result.purpose_label}</span>
            <span className="cr-grade" style={{ background: "var(--brand-grad)" }}>{tr("taekil.day_branch", { who: purpose === "birth" ? tr("taekil.parent") : tr("taekil.self"), branch: res.result.user_day_branch })}</span>
          </div>
          <div className="cr-sub">{tr("taekil.recommended")}</div>
          <div className="taekil-grid">
            {(res.result.best || []).map((d: any, i: number) => (
              <div key={i} className={`day-card ${d.grade === "대길일" ? "best" : ""}`}>
                <div className="dc-date">{d.date}</div>
                <div className="dc-ganzhi">{d.ganzhi}</div>
                <div className="dc-tags">
                  <span className="dc-hwangdo">{d.hwangdo}</span>
                  {d.geonje && <span className="dc-geonje" title={d.geonje_note}>{d.geonje}</span>}
                  {d.su28 && <span className="dc-su28" title={d.su28_note}>{d.su28}</span>}
                  {d.saenggi && <span className={`dc-saenggi ${["생기", "천의", "복덕"].includes(d.saenggi) ? "gil" : ["절체", "화해", "절명"].includes(d.saenggi) ? "hyung" : ""}`} title={tr("taekil.saenggi_title")}>{d.saenggi}</span>}
                  {d.sonless && <span className="dc-son">{tr("taekil.sonless")}</span>}
                </div>
                <div className="dc-score">{tr("taekil.score_grade", { score: fmtNum(d.score), grade: d.grade })}</div>
                {d.best_hours && d.best_hours.length > 0 && (
                  <div className="dc-hours" title={tr("taekil.best_hours_title")}>
                    🕐 {d.best_hours.map((h: any) => `${h.sijin}(${h.ganzhi})`).join(" · ")}
                  </div>
                )}
              </div>
            ))}
          </div>

          {res.result.perspectives && (
            <div className="taekil-persp">
              <div className="cr-sub">{tr("taekil.persp_title")} <span>{tr("taekil.persp_sub")}</span></div>
              <div className="tp-chips">
                {Object.values(res.result.perspectives).map((p: any) => (
                  <div key={p.label} className="tp-chip">
                    <div className="tp-label">{p.label}</div>
                    <div className="tp-date">{p.top_date}</div>
                    <div className="tp-meta">{tr("taekil.persp_meta", { ganzhi: p.top_ganzhi, score: fmtNum(p.top_score) })}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(res.result.avoid || []).length > 0 && (
            <div className="taekil-avoid">
              <span className="cr-sub">{tr("taekil.avoid_title")}</span>
              {res.result.avoid.map((d: any, i: number) => (
                <span key={i} className="avoid-chip">{d.date} ({(d.warnings || []).join("/") || d.grade})</span>
              ))}
            </div>
          )}
          <ExplainChat
            streamPath={`/api/tools/${res.tool_id}/messages/stream`}
            isPreview={res.is_preview}
            autoStart={false}
            pdf={{
              docTitle: tr("taekil.pdf_doc", { who }),
              personLine: tr("taekil.pdf_person", { who }),
              item: tr("taekil.pdf_item", { label: res.result.purpose_label || PURPOSE_LABELS[purpose] }),
            }}
            pdfHeader={taekilPdfHeader(res.result)}
            feedbackSource="tool"
            feedbackSessionId={res.tool_id}
            suggestFetch={() => api.getToolSuggestions(res.tool_id).then((r) => r.suggestions || [])}
          />
        </div>
      )}
    </div>
  );
}
