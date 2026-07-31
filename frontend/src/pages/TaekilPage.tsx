/** 택일 — 생년월일 + 용도 + 기간 → 길일 추천. */
import { useEffect, useRef, useState } from "react";
import { api, useMe, PURPOSE_LABELS, type Birth, type TaekilPurpose, type ToolResponse } from "../api";
import { useEnsureEntry, EntryFeeNotice } from "../components/ChargeModal";
import { resolveBirthTime } from "../lib/birthTime";
import ExplainChat from "../components/ExplainChat";
import BirthFields, { profileToBirthValue, type BirthValue } from "../components/BirthFields";

const PURPOSES = Object.keys(PURPOSE_LABELS) as TaekilPurpose[];

// 상담서 PDF 본문 상단 요약 — 추천 길일 목록
function taekilPdfHeader(r: any): string {
  const best = (r?.best || []).slice(0, 8);
  if (!best.length) return "";
  const lines = best.map((d: any) => `- ${d.date} (${d.ganzhi}) · ${d.score}점 · ${d.grade}`);
  return "[추천 길일]\n" + lines.join("\n");
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
  wedding: "혼례에 좋은 날 — 본인 사주의 충·형 회피를 가장 중시하고, 황도길일·손없는날을 함께 반영합니다.",
  birth: "그날 태어날 아이의 사주와 부모(입력자)의 궁합을 가장 중시합니다.",
  moving: "이사·입택에 좋은 날 — 손없는날을 가장 중시하고, 황도길일·사주를 함께 반영합니다.",
  opening: "개업에 좋은 날 — 황도길일과 손없는날을 같은 비중으로 중시합니다.",
  contract: "계약·서명에 좋은 날 — 본인 사주의 충·형 회피와 황도길일을 함께 중시합니다.",
  ceremony: "고사·제사에 좋은 날 — 황도길일을 가장 중시하고, 사주 조화를 함께 봅니다.",
  surgery: "수술·시술에 좋은 날 — 본인 사주의 충·형 회피를 가장 중시하고, 황도길일을 함께 봅니다.",
  travel: "여행·출행에 좋은 날 — 황도길일을 가장 중시하고, 사주 조화를 함께 봅니다.",
  general: "일반 길일 — 황도길일·사주·손없는날을 고루 반영합니다.",
};

export default function TaekilPage() {
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
  const who = (me?.nickname?.trim() || (me?.email ? me.email.split("@")[0] : "")) || "접속자";
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
      setErr(e?.message || "택일에 실패했어요.");
    } finally { setLoading(false); }
  }

  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">擇日</div>
        <h1>택일</h1>
        <p>황도흑도·건제십이신·이십팔수·생기복덕·사주 조화·손없는날을 <b>용도별 비중</b>으로 가중해 가립니다. 관법은 정답이 없어 <b>세 관점</b>의 추천 1위도 함께 보여드려요.</p>
      </header>

      <div className="tool-form">
        <div className="bf-field">
          <label>용도</label>
          <div className="purpose-grid" role="radiogroup" aria-label="택일 용도">
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
              ? <>아래 입력하신 분(부모)을 기준으로, 그날 태어날 <b>아이의 사주와 부모의 궁합</b>이 좋은 날을 찾아드려요.</>
              : PURPOSE_DESC[purpose]}
          </div>
        </div>
        <EntryFeeNotice menu="taekil" />
        {purpose === "birth" && <div className="pc-flabel" style={{ marginTop: 4 }}>부모 ①</div>}
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} />
        {purpose === "birth" && (
          <>
            <div className="pc-flabel" style={{ marginTop: 6 }}>부모 ② <span style={{ fontWeight: 400, color: "var(--ink-400)" }}>(선택 — 입력 시 두 분 모두와의 궁합으로 가립니다)</span></div>
            <BirthFields value={b2} onChange={(patch) => setB2((prev) => ({ ...prev, ...patch }))} />
          </>
        )}
        <div className="bf-field">
          <label>검색 기간</label>
          <div className="bf-time">
            <input className="bf-input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <select className="bf-input" style={{ flex: "0 0 110px" }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={30}>30일</option><option value={60}>60일</option><option value={90}>90일</option>
            </select>
          </div>
        </div>
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || loading} onClick={submit}>
          {loading ? "분석 중…" : "📅 길일 찾기"}
        </button>
        {!b.birth_date && <div className="cta-hint">본인 생년월일을 입력해 주세요</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <div id="tool-result" className="compat-result">
          <div className="cr-headline">
            <span className="cr-names">{res.result.purpose_label}</span>
            <span className="cr-grade" style={{ background: "var(--brand-grad)" }}>{purpose === "birth" ? "부모" : "본인"} 일지 {res.result.user_day_branch}</span>
          </div>
          <div className="cr-sub">추천 길일</div>
          <div className="taekil-grid">
            {(res.result.best || []).map((d: any, i: number) => (
              <div key={i} className={`day-card ${d.grade === "대길일" ? "best" : ""}`}>
                <div className="dc-date">{d.date}</div>
                <div className="dc-ganzhi">{d.ganzhi}</div>
                <div className="dc-tags">
                  <span className="dc-hwangdo">{d.hwangdo}</span>
                  {d.geonje && <span className="dc-geonje" title={d.geonje_note}>{d.geonje}</span>}
                  {d.su28 && <span className="dc-su28" title={d.su28_note}>{d.su28}</span>}
                  {d.saenggi && <span className={`dc-saenggi ${["생기", "천의", "복덕"].includes(d.saenggi) ? "gil" : ["절체", "화해", "절명"].includes(d.saenggi) ? "hyung" : ""}`} title="생기복덕(본명괘 기준)">{d.saenggi}</span>}
                  {d.sonless && <span className="dc-son">손없는날</span>}
                </div>
                <div className="dc-score">{d.score}점 · {d.grade}</div>
                {d.best_hours && d.best_hours.length > 0 && (
                  <div className="dc-hours" title="아이-부모 궁합이 좋은 시(時)">
                    🕐 {d.best_hours.map((h: any) => `${h.sijin}(${h.ganzhi})`).join(" · ")}
                  </div>
                )}
              </div>
            ))}
          </div>

          {res.result.perspectives && (
            <div className="taekil-persp">
              <div className="cr-sub">관법별 추천 1위 <span>(정답 없음 — 세 관점)</span></div>
              <div className="tp-chips">
                {Object.values(res.result.perspectives).map((p: any) => (
                  <div key={p.label} className="tp-chip">
                    <div className="tp-label">{p.label}</div>
                    <div className="tp-date">{p.top_date}</div>
                    <div className="tp-meta">{p.top_ganzhi} · {p.top_score}점</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(res.result.avoid || []).length > 0 && (
            <div className="taekil-avoid">
              <span className="cr-sub">피하면 좋은 날</span>
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
              docTitle: `${who} 님이 확인한 택일`,
              personLine: `${who} 님`,
              item: `${res.result.purpose_label || PURPOSE_LABELS[purpose]} 택일`,
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
