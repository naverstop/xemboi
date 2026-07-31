/** 궁합(宮合) 페이지 — A·B 입력 → 룰엔진 결과(펜타곤 + 3관법 게이지 + 근거 + 도화 + 해설). */
import { useEffect, useMemo, useRef, useState } from "react";
import { resolveBirthTime } from "../lib/birthTime";
import {
  api,
  useMe,
  getToken,
  notifySessionExpired,
  COMPAT_AXES,
  type CompatResponse,
  type CompatAverage,
  type CompatPersonReq,
  type SajuProfile,
  type MeResp,
} from "../api";
import SajuChart, { type Chart } from "../components/SajuChart";
import BirthFields, { profileToBirthValue } from "../components/BirthFields";
import AnswerActions, { type PdfMeta } from "../components/AnswerActions";
import { useEnsureEntry, EntryFeeNotice, useCharge } from "../components/ChargeModal";
import FollowupBilling from "../components/FollowupBilling";
import ConsultationReportButton, { type ReportReq } from "../components/ConsultationReportButton";
import { renderRich, stripMarkdown } from "../lib/format";
import { useTranslation, Trans } from "react-i18next";
import { fmtNum } from "../lib/money";
import i18n from "../i18n";

// 상담서 PDF 본문 상단 요약 — 종합 등급 + 관법별 점수
function compatPdfHeader(res: CompatResponse): string {
  const r = res.result;
  const persp = ["A", "B", "C"].map((k) => r.perspectives[k]).filter(Boolean);
  const head = persp.find((p) => p.key === "B") || persp[0];
  const lines: string[] = [];
  if (head) lines.push(i18n.t("compat.pdf_overall", { grade: head.grade, total: head.total }));
  persp.forEach((p) => lines.push(i18n.t("compat.pdf_persp", { label: p.label, grade: p.grade, total: p.total })));
  return lines.join("\n");
}

// 궁합 SSE 스트리밍 (채팅과 동일 프로토콜). 한 어시스턴트 턴을 스트리밍.
type SSEHandlers = {
  onChunk: (full: string) => void;
  onRefine?: (full: string) => void;
  onCut?: () => void;
  onStage?: (phase: string) => void;
  onDone?: (d: any) => void;
};
async function streamCompat(
  compatId: string,
  body: { message: string; depth: "basic" | "deep" },
  h: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const tok = getToken();
  const resp = await fetch(`/api/compatibility/${compatId}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
    body: JSON.stringify({ ...body, explain_level: "normal" }),
    signal,  // 이탈 시 abort → 백엔드 disconnect → LLM(GPU) 중단
  });
  if (!resp.ok || !resp.body) {
    if (resp.status === 401) { notifySessionExpired(); throw new Error("SESSION_EXPIRED"); }
    if (resp.status === 402) throw new Error("PAYWALL");
    throw new Error(`stream ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let acc = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      let event = "message";
      let data = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      if (event === "chunk" && data) {
        try { acc += JSON.parse(data).text; h.onChunk(acc); } catch {}
      } else if (event === "refine" && data) {
        try { acc = JSON.parse(data).text || acc; h.onRefine?.(acc); } catch {}
      } else if (event === "cut") {
        acc += " …"; h.onChunk(acc); h.onCut?.();
      } else if (event === "stage" && data) {
        try { h.onStage?.(JSON.parse(data).phase); } catch {}
      } else if (event === "done" && data) {
        try { h.onDone?.(JSON.parse(data)); } catch {}
      } else if (event === "error" && data) {
        try { throw new Error(JSON.parse(data).detail || i18n.t("compat.stream_err")); } catch (e) { throw e; }
      }
    }
  }
}

type PState = {
  mode: "profile" | "manual";
  profile_id?: number;
  label: string;
  birth_date: string;
  birth_time: string;
  unknown_time: boolean;
  calendar: "solar" | "lunar";
  gender: "male" | "female";
  is_leap_month: boolean;
  apply_true_solar_time?: boolean;
  birth_longitude?: number | null;
  apply_equation_of_time?: boolean;
  night_zi_mode?: "yaja" | "jeongja";
};

const blankPerson = (label: string): PState => ({
  mode: "manual",
  label,
  birth_date: "",
  birth_time: "",
  unknown_time: false,
  calendar: "solar",
  gender: "male",
  is_leap_month: false,
  apply_true_solar_time: true,
  birth_longitude: 126.98,
  apply_equation_of_time: false,
  night_zi_mode: "yaja",
});

function toReq(p: PState): CompatPersonReq {
  if (p.mode === "profile" && p.profile_id) {
    return { profile_id: p.profile_id, label: p.label || undefined };
  }
  return {
    label: p.label || undefined,
    birth: {
      birth_date: p.birth_date,
      birth_time: resolveBirthTime(p.birth_time, p.unknown_time),
      calendar: p.calendar,
      gender: p.gender,
      is_leap_month: p.calendar === "lunar" ? p.is_leap_month : false,
      apply_true_solar_time: !!p.apply_true_solar_time,
      birth_longitude: p.birth_longitude ?? null,
      apply_equation_of_time: !!p.apply_equation_of_time,
      night_zi_mode: p.night_zi_mode ?? "yaja",
    },
  };
}

const GRADE_TONE: Record<string, string> = {
  천생연분: "var(--grad-success)",
  "좋은 궁합": "var(--brand-grad)",
  "무난한 궁합": "var(--grad-info)",
  "노력 필요": "var(--grad-warning)",
  신중히: "linear-gradient(135deg,#e57373,#c62828)",
};

// ===================== 펜타곤(레이더) =====================
function polyPoints(values: number[], R: number, cx: number, cy: number): string {
  return values
    .map((v, i) => {
      const ang = (-90 + i * 72) * (Math.PI / 180);
      const rr = (Math.max(0, Math.min(100, v)) / 100) * R;
      return `${(cx + rr * Math.cos(ang)).toFixed(1)},${(cy + rr * Math.sin(ang)).toFixed(1)}`;
    })
    .join(" ");
}

function Pentagon({
  couple,
  average,
}: {
  couple: number[];
  average: number[] | null;
}) {
  const { t: tr } = useTranslation();
  const S = 320, cx = 160, cy = 160, R = 108, LR = 130;
  const rings = [0.25, 0.5, 0.75, 1];
  const axisPt = (i: number, r: number) => {
    const ang = (-90 + i * 72) * (Math.PI / 180);
    return [cx + r * Math.cos(ang), cy + r * Math.sin(ang)];
  };
  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="pentagon" role="img" aria-label={tr("compat.pentagon_aria")}>
      <defs>
        <radialGradient id="penFill" cx="50%" cy="45%" r="65%">
          <stop offset="0%" stopColor="#22b8f0" stopOpacity="0.40" />
          <stop offset="100%" stopColor="#0496d8" stopOpacity="0.16" />
        </radialGradient>
        <filter id="penGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="#0496d8" floodOpacity="0.35" />
        </filter>
      </defs>

      {/* 그리드 링 */}
      {rings.map((rp) => (
        <polygon
          key={rp}
          points={polyPoints([100, 100, 100, 100, 100], R * rp, cx, cy)}
          className="pen-ring"
        />
      ))}
      {/* 축선 */}
      {COMPAT_AXES.map((_, i) => {
        const [x, y] = axisPt(i, R);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} className="pen-axis" />;
      })}

      {/* 전체 평균(점선) */}
      {average && (
        <polygon points={polyPoints(average, R, cx, cy)} className="pen-avg" />
      )}
      {/* 이 커플(실선 + 글로우) */}
      <polygon
        points={polyPoints(couple, R, cx, cy)}
        fill="url(#penFill)"
        className="pen-couple"
        filter="url(#penGlow)"
      />
      {couple.map((v, i) => {
        const ang = (-90 + i * 72) * (Math.PI / 180);
        const rr = (v / 100) * R;
        return <circle key={i} cx={cx + rr * Math.cos(ang)} cy={cy + rr * Math.sin(ang)} r="3.5" className="pen-dot" />;
      })}

      {/* 라벨 + 점수 */}
      {COMPAT_AXES.map((ax, i) => {
        const [x, y] = axisPt(i, LR);
        const anchor = Math.abs(x - cx) < 6 ? "middle" : x > cx ? "start" : "end";
        return (
          <text key={ax.key} x={x} y={y} textAnchor={anchor as any} className="pen-label">
            <tspan>{ax.label}</tspan>
            <tspan x={x} dy="13" className="pen-label-score">{couple[i]}</tspan>
          </text>
        );
      })}
    </svg>
  );
}

// ===================== 관법 게이지 =====================
function Gauge({
  label,
  total,
  grade,
  avg,
}: {
  label: string;
  total: number;
  grade: string;
  avg: number | null;
}) {
  const { t: tr } = useTranslation();
  return (
    <div className="compat-gauge">
      <div className="cg-head">
        <span className="cg-label">{label}</span>
        <span className="cg-grade" style={{ background: GRADE_TONE[grade] || "var(--brand-grad)" }}>
          {grade}
        </span>
      </div>
      <div className="cg-bar">
        <div className="cg-fill" style={{ width: `${total}%` }} />
        {avg != null && <div className="cg-avg" style={{ left: `${avg}%` }} title={tr("compat.gauge_avg_title", { avg })} />}
      </div>
      <div className="cg-foot">
        <strong className="cg-total">{tr("compat.score", { n: total })}</strong>
        {avg != null && <span className="cg-avg-text">{tr("compat.gauge_avg_text", { avg })}</span>}
      </div>
    </div>
  );
}

// ===================== 근거 카드 =====================
function ScoreRing({ score }: { score: number }) {
  const r = 20, c = 2 * Math.PI * r;
  const off = c * (1 - score / 100);
  const hue = score >= 75 ? "#20c997" : score >= 55 ? "#0496d8" : score >= 42 ? "#ff9800" : "#e57373";
  return (
    <svg viewBox="0 0 52 52" className="score-ring">
      <circle cx="26" cy="26" r={r} className="sr-track" />
      <circle
        cx="26" cy="26" r={r} className="sr-fill"
        style={{ stroke: hue, strokeDasharray: c, strokeDashoffset: off }}
      />
      <text x="26" y="30" textAnchor="middle" className="sr-text">{score}</text>
    </svg>
  );
}

export default function CompatibilityPage() {
  const me = useMe();
  const { t: tr } = useTranslation();
  const ensureEntry = useEnsureEntry();
  const { openCharge } = useCharge();
  const memberName = me?.nickname?.trim() || (me?.email ? me.email.split("@")[0] : "") || tr("compat.member_fallback");
  const [a, setA] = useState<PState>(() => blankPerson(tr("compat.self")));
  const [b, setB] = useState<PState>(() => blankPerson(tr("compat.other")));
  const [profiles, setProfiles] = useState<SajuProfile[]>([]);
  const [depth, setDepth] = useState<"basic" | "deep">("deep");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<CompatResponse | null>(null);
  const [avg, setAvg] = useState<CompatAverage | null>(null);
  // 스트리밍 해설 + 추가질문
  const [explainText, setExplainText] = useState("");
  const [explainStreaming, setExplainStreaming] = useState(false);
  const [explainMsgId, setExplainMsgId] = useState<number | undefined>(undefined);  // 해설 메시지 id(피드백용)
  const [compatSuggests, setCompatSuggests] = useState<string[]>([]);               // 추천질문 칩
  const [qDepth, setQDepth] = useState<"basic" | "deep">("basic");                  // 추가질문 등급(기본=1000P)
  const explainingRef = useRef(false);                                              // 항상 활성 입력
  const [explainStarted, setExplainStarted] = useState(false);                      // 해설 시작 여부(버튼 노출 제어)
  const acRef = useRef<AbortController | null>(null);                               // 현재 활성 스트림 취소(이탈 시 GPU 중단)
  const [refineStage, setRefineStage] = useState<string | null>(null);
  const [qaTurns, setQaTurns] = useState<{ role: "user" | "assistant"; content: string; refined?: boolean; is_preview?: boolean; charged?: number }[]>([]);
  const [qInput, setQInput] = useState("");
  const [qStreaming, setQStreaming] = useState(false);
  const depthRef = useRef(depth);
  depthRef.current = depth;

  // 첫 번째 사람(본인): 저장된 사주 자동 채움(사용자별 1회)
  const aFilledFor = useRef<number | null>(null);
  useEffect(() => {
    if (!me?.saju_profile?.birth_date || aFilledFor.current === me.id) return;
    aFilledFor.current = me.id;
    setA((prev) => ({ ...prev, ...profileToBirthValue(me.saju_profile) }));
  }, [me]);

  useEffect(() => {
    if (me) api.listSajuProfiles().then((r) => setProfiles(r.items)).catch(() => {});
    api.compatibilityAverage().then(setAvg).catch(() => {});
  }, [me]);

  async function loadCompatSuggests(cid: string) {
    try { setCompatSuggests((await api.getCompatSuggestions(cid)).suggestions || []); } catch { /* 무시 */ }
  }

  // 페이지 이탈 시 진행 중 스트림 즉시 취소 → 백엔드 disconnect → LLM(GPU) 중단
  useEffect(() => () => { try { acRef.current?.abort(); } catch { /* noop */ } }, []);

  async function startExplain(cid: string) {
    setExplainStarted(true);
    setExplainStreaming(true); explainingRef.current = true;
    setExplainText("");
    setExplainMsgId(undefined);
    setCompatSuggests([]);
    const ac = new AbortController(); acRef.current = ac;
    try {
      await streamCompat(cid, { message: "", depth: depthRef.current }, {
        onChunk: setExplainText,
        onRefine: setExplainText,
        onStage: setRefineStage,
        onDone: (d) => { if (d?.assistant_message_id) setExplainMsgId(d.assistant_message_id); },
      }, ac.signal);
    } catch {
      /* 부분 스트리밍/이탈 취소 — 조용히 유지 */
    } finally {
      setExplainStreaming(false); explainingRef.current = false;
      setRefineStage(null);
      loadCompatSuggests(cid);
    }
  }

  async function askFollowup(preset?: string) {
    const q = (preset ?? qInput).trim();
    if (!q || qStreaming || !res) return;
    setQInput("");
    setQStreaming(true);
    setCompatSuggests([]);
    // 항상 활성 입력 — 해설 진행 중이면 끝날 때까지 대기(동일 세션 동시 스트림 방지)
    while (explainingRef.current) await new Promise((r) => setTimeout(r, 250));
    setQaTurns((t) => [...t, { role: "user", content: q }, { role: "assistant", content: "" }]);
    const upd = (patch: any) =>
      setQaTurns((t) => { const c = [...t]; c[c.length - 1] = { ...c[c.length - 1], ...patch }; return c; });
    const ac = new AbortController(); acRef.current = ac;
    try {
      await streamCompat(res.compat_id, { message: q, depth: qDepth }, {
        onChunk: (full) => upd({ content: full }),
        onRefine: (full) => upd({ content: full, refined: true }),
        onStage: setRefineStage,
        onDone: (d) => upd({ is_preview: d.is_preview, charged: d.credits_charged }),
      }, ac.signal);
    } catch (e: any) {
      if (e?.name === "AbortError") { /* 이탈 취소 — 조용히 무시 */ }
      else if (e?.message === "PAYWALL") { upd({ content: "" }); openCharge(tr("compat.need_points")); }
      else upd({ content: tr("compat.answer_fail") });
    } finally {
      setQStreaming(false);
      setRefineStage(null);
      loadCompatSuggests(res.compat_id);
    }
  }

  const okPerson = (p: PState) => (p.mode === "profile" ? !!p.profile_id : !!p.birth_date);
  const canSubmit = useMemo(() => okPerson(a) && okPerson(b) && !loading, [a, b, loading]);
  const reason = !okPerson(a) ? tr("compat.reason_a")
    : !okPerson(b) ? tr("compat.reason_b")
    : null;

  async function submit() {
    if (!ensureEntry("compat")) return;
    setErr(null);
    setLoading(true);
    setRes(null);
    setExplainText("");
    setQaTurns([]);
    try {
      const out = await api.createCompatibility(toReq(a), toReq(b), depth);
      setRes(out);
      setExplainStarted(false);  // 해설은 '자세히 설명' 버튼 클릭 시에만 생성(불필요 GPU 방지)
      api.compatibilityAverage().then(setAvg).catch(() => {});
      setTimeout(() => document.getElementById("compat-result")?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (e: any) {
      setErr(e?.message || tr("compat.fail"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">宮合</div>
        <h1>{tr("compat.hero_title")}</h1>
        <p><Trans i18nKey="compat.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      <EntryFeeNotice menu="compat" />
      <div className="compat-input-grid">
        <PersonForm title={tr("compat.person1")} accent="a" p={a} setP={setA} profiles={profiles} loggedIn={!!me} />
        <div className="compat-link" aria-hidden>💞</div>
        <PersonForm title={tr("compat.person2")} accent="b" p={b} setP={setB} profiles={profiles} loggedIn={!!me} />
      </div>

      <div className="compat-actions">
        <label className="compat-depth">
          <input type="checkbox" checked={depth === "deep"} onChange={(e) => setDepth(e.target.checked ? "deep" : "basic")} />
          {tr("compat.depth_deep")}
        </label>
        <button className="compat-cta" disabled={!canSubmit} onClick={submit}>
          {loading ? tr("compat.analyzing") : tr("compat.cta")}
        </button>
      </div>
      {!canSubmit && !loading && reason && <div className="cta-hint">{reason}</div>}
      {err && <div className="compat-err">{err}</div>}

      {res && <Result res={res} avg={avg} />}
      {res && !explainStarted && (
        <div className="cr-explain">
          <div className="explain-body">
            <button className="explain-cta" onClick={() => startExplain(res.compat_id)}>
              {tr("compat.explain_cta")}
            </button>
          </div>
        </div>
      )}
      {res && explainStarted && (
        <ExplainChat
          explainText={explainText}
          explainStreaming={explainStreaming}
          refineStage={refineStage}
          isPreview={res.is_preview}
          qaTurns={qaTurns}
          qInput={qInput}
          setQInput={setQInput}
          askFollowup={askFollowup}
          qStreaming={qStreaming}
          suggests={compatSuggests}
          me={me}
          qDepth={qDepth}
          setQDepth={setQDepth}
          pdf={(() => {
            const aName = res.person_a.label && res.person_a.label !== tr("compat.self") ? res.person_a.label : memberName;
            const bLabel = res.person_b.label;
            const [by, bm] = (b.birth_date || "").split("-");
            const bDesc =
              bLabel && bLabel !== tr("compat.other")
                ? tr("compat.pdf_other_named", { label: bLabel })
                : by && bm
                ? tr("compat.pdf_other_ym", { y: by, m: Number(bm) })
                : tr("compat.pdf_other");
            return { docTitle: tr("compat.pdf_couple", { a: aName, b: bDesc }), personLine: tr("compat.pdf_person", { a: aName, b: bDesc }), item: tr("compat.pdf_item") };
          })()}
          pdfHeader={compatPdfHeader(res)}
          feedbackMsgId={explainMsgId}
          compatId={res.compat_id}
        />
      )}
    </div>
  );
}

// ===================== 해설(스트리밍) + 추가질문 =====================
function ExplainChat({
  explainText, explainStreaming, refineStage, isPreview,
  qaTurns, qInput, setQInput, askFollowup, qStreaming, pdf, pdfHeader,
  feedbackMsgId, compatId, suggests, me, qDepth, setQDepth,
}: {
  explainText: string;
  explainStreaming: boolean;
  refineStage: string | null;
  isPreview: boolean;
  qaTurns: { role: "user" | "assistant"; content: string; refined?: boolean; is_preview?: boolean; charged?: number }[];
  qInput: string;
  setQInput: (v: string) => void;
  askFollowup: (preset?: string) => void;
  qStreaming: boolean;
  pdf?: PdfMeta;
  pdfHeader?: string;
  feedbackMsgId?: number;   // 해설 메시지 id(궁합 피드백용)
  compatId?: string;        // 익명 피드백 upsert 키
  suggests?: string[];      // 추천질문 칩
  me: MeResp | null;
  qDepth: "basic" | "deep";
  setQDepth: (d: "basic" | "deep") => void;
}) {
  const { t: tr } = useTranslation();
  const stageText = refineStage === "refining" ? tr("compat.refining") : null;
  return (
    <div className="cr-explain">
      <div className="cr-sub">{tr("compat.explain_label")} {refineStage && <span className="cr-refine-tag">{stageText}</span>}</div>
      <div className="explain-body">
        {explainText ? renderRich(explainText) : (explainStreaming ? "" : tr("compat.explain_loading"))}
        {explainStreaming && !explainText && <span className="thinking-dots" />}
      </div>
      {isPreview && (
        <div className="explain-preview-note">{tr("compat.preview_note")}</div>
      )}
      {pdf && explainText && !explainStreaming && (
        <AnswerActions
          text={(pdfHeader ? pdfHeader.trim() + "\n\n" : "") + stripMarkdown(explainText)}
          pdf={pdf}
          messageId={feedbackMsgId}
          source="compat"
          sessionId={compatId}
          isLast
        />
      )}

      {/* 추가질문 채팅 */}
      <div className="compat-qa">
        <div className="cr-sub">{tr("compat.qa_title")}</div>
        {qaTurns.map((t, i) => (
          <div key={i} className={`qa-turn qa-${t.role}`}>
            <div className="qa-bubble">
              {t.content ? renderRich(t.content) : <span className="thinking-dots" />}
              {t.refined && <span className="qa-refined">{tr("compat.qa_refined")}</span>}
              {t.role === "assistant" && typeof t.charged === "number" && t.charged > 0 && (
                <span className="qa-charged">{tr("compat.qa_charged", { n: fmtNum(t.charged) })}</span>
              )}
            </div>
          </div>
        ))}
        {suggests && suggests.length > 0 && !qStreaming && (
          <div className="suggest-chips followup">
            <div className="suggest-label">{tr("compat.followup_label")}</div>
            {suggests.map((sg) => (
              <button key={sg} className="chip" disabled={qStreaming} onClick={() => askFollowup(sg)}>
                {sg}
              </button>
            ))}
          </div>
        )}
        <FollowupBilling me={me} depth={qDepth} onDepth={setQDepth} />
        <div className="qa-input-row">
          <input
            className="qa-input"
            placeholder={tr("compat.qa_ph")}
            value={qInput}
            disabled={qStreaming}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") askFollowup(); }}
          />
          <button className="qa-send" disabled={qStreaming || !qInput.trim()} onClick={() => askFollowup()}>
            {qStreaming ? "…" : explainStreaming ? tr("compat.qa_wait") : tr("compat.qa_ask")}
          </button>
        </div>
        {pdf && explainText && qaTurns.some((t) => t.role === "assistant" && t.content) && !qStreaming && (
          <div className="report-row">
            <ConsultationReportButton
              build={(): ReportReq | null => {
                const conversation = [
                  { role: "assistant", content: (pdfHeader ? pdfHeader.trim() + "\n\n" : "") + stripMarkdown(explainText) },
                  ...qaTurns.filter((t) => t.content).map((t) => ({ role: t.role, content: stripMarkdown(t.content) })),
                ];
                return {
                  doc_title: tr("compat.report_doc_suffix", { title: pdf.docTitle }),
                  person_line: pdf.personLine,
                  item: pdf.item || tr("compat.report_item"),
                  conversation,
                  topic: tr("compat.report_topic"),
                };
              }}
            />
            <span className="report-hint">{tr("compat.report_hint")}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ===================== 입력 폼 =====================
function PersonForm({
  title, accent, p, setP, profiles, loggedIn,
}: {
  title: string;
  accent: "a" | "b";
  p: PState;
  setP: (p: PState) => void;
  profiles: SajuProfile[];
  loggedIn: boolean;
}) {
  const { t: tr } = useTranslation();
  const up = (patch: Partial<PState>) => setP({ ...p, ...patch });
  return (
    <div className={`person-card pc-${accent}`}>
      <div className="pc-title">{title}</div>
      <input
        className="pc-name"
        placeholder={tr("compat.name_ph")}
        value={p.label}
        onChange={(e) => up({ label: e.target.value })}
      />
      {loggedIn && profiles.length > 0 && (
        <div className="pc-mode">
          <button className={p.mode === "manual" ? "on" : ""} onClick={() => up({ mode: "manual" })}>{tr("compat.mode_manual")}</button>
          <button className={p.mode === "profile" ? "on" : ""} onClick={() => up({ mode: "profile" })}>{tr("compat.mode_profile")}</button>
        </div>
      )}
      {p.mode === "profile" ? (
        <select
          className="pc-field"
          value={p.profile_id || ""}
          onChange={(e) => up({ profile_id: Number(e.target.value) || undefined })}
        >
          <option value="">{tr("compat.profile_select")}</option>
          {profiles.map((pr) => (
            <option key={pr.id} value={pr.id}>
              {pr.label} · {pr.birth_date}
            </option>
          ))}
        </select>
      ) : (
        <BirthFields value={p} onChange={(patch) => setP({ ...p, ...patch })} />
      )}
    </div>
  );
}

// ===================== 결과 =====================
function Result({ res, avg }: { res: CompatResponse; avg: CompatAverage | null }) {
  const { t: tr } = useTranslation();
  const r = res.result;
  const coupleVals = COMPAT_AXES.map((ax) => r.factors[ax.key]?.score ?? 0);
  const avgFactors = avg?.average?.factors || null;
  const avgVals = avgFactors ? COMPAT_AXES.map((ax) => avgFactors[ax.key] ?? 0) : null;
  const persp = ["A", "B", "C"].map((k) => r.perspectives[k]).filter(Boolean);
  const headline = persp.find((p) => p.key === "B") || persp[0];

  return (
    <div id="compat-result" className="compat-result">
      <div className="cr-headline">
        <span className="cr-names">{res.person_a.label}</span>
        <span className="cr-heart">💞</span>
        <span className="cr-names">{res.person_b.label}</span>
        {headline && (
          <span className="cr-grade" style={{ background: GRADE_TONE[headline.grade] || "var(--brand-grad)" }}>
            {headline.grade} · {tr("compat.score", { n: headline.total })}
          </span>
        )}
      </div>

      <div className="cr-top">
        <section className="cr-pentagon-card">
          <Pentagon couple={coupleVals} average={avgVals} />
          <div className="pen-legend">
            <span className="pl-couple">{tr("compat.legend_couple")}</span>
            {avgVals ? (
              <span className="pl-avg">{tr("compat.legend_avg", { n: fmtNum(avg?.count ?? 0) })}</span>
            ) : (
              <span className="pl-none">{tr("compat.legend_none", { n: avg?.min_samples ?? 5 })}</span>
            )}
          </div>
        </section>

        <section className="cr-gauges">
          <div className="cr-sub">{tr("compat.gauges_title")} <span>{tr("compat.gauges_sub")}</span></div>
          {persp.map((p) => (
            <Gauge
              key={p.key}
              label={p.label}
              total={p.total}
              grade={p.grade}
              avg={avg?.average?.totals?.[p.key] ?? null}
            />
          ))}
        </section>
      </div>

      {r.penalties.length > 0 && (
        <div className="cr-penalties">
          {r.penalties.map((pen, i) => (
            <span key={i} className="penalty-badge" title={pen.detail}>⚠ {pen.type}</span>
          ))}
        </div>
      )}

      <div className="cr-factors">
        {COMPAT_AXES.map((ax) => {
          const f = r.factors[ax.key];
          if (!f) return null;
          return (
            <div key={ax.key} className="factor-card">
              <ScoreRing score={f.score} />
              <div className="fc-body">
                <div className="fc-label">{f.label}</div>
                {f.items.map((it, i) => (
                  <div key={i} className={`fc-item sign-${it.sign}`}>
                    <b>{it.type}</b> {it.detail}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {r.dohwa_readings.length > 0 && (
        <div className="cr-dohwa">
          <div className="cr-sub">{tr("compat.dohwa_title")}</div>
          <div className="dohwa-grid">
            {r.dohwa_readings.map((d, i) => (
              <div key={i} className="dohwa-card">{d}</div>
            ))}
          </div>
        </div>
      )}

      <div className="cr-charts">
        <div className="cr-chart-col">
          <div className="cr-chart-name">{res.person_a.label}</div>
          <SajuChart chart={res.person_a.chart as Chart} />
        </div>
        <div className="cr-chart-col">
          <div className="cr-chart-name">{res.person_b.label}</div>
          <SajuChart chart={res.person_b.chart as Chart} />
        </div>
      </div>
    </div>
  );
}
