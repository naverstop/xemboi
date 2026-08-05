/** 궁합(宮合) 페이지 — A·B 입력 → 룰엔진 결과(펜타곤 + 3관법 게이지 + 근거 + 도화 + 해설). */
import ReviewStrip from "../components/ReviewStrip";
import PrivacyNotice from "../components/PrivacyNotice";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { resolveBirthTime } from "../lib/birthTime";
import {
  api,
  useMe,
  refreshMe,
  ensureFreshToken,
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
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import AnswerActions, { type PdfMeta } from "../components/AnswerActions";
import { useEnsureEntry, EntryFeeNotice, useCharge } from "../components/ChargeModal";
import PastResultsDrawer, { fmtWhen, type PastItem } from "../components/PastResultsDrawer";
import { usePremiumRestore, usePastList } from "../lib/usePastResults";
import TypingDots from "../components/TypingDots";
import FollowupBilling from "../components/FollowupBilling";
import ConsultationReportButton, { type ReportReq } from "../components/ConsultationReportButton";
import { renderRich, stripMarkdown } from "../lib/format";
import { displayName } from "../lib/displayName";
import { useTranslation, Trans } from "react-i18next";
import { fmtNum } from "../lib/money";
import { DEFAULT_LON } from "../lib/regions";
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
  const tok = await ensureFreshToken();   // 만료 토큰 → 익명 미리보기 방지(무음 갱신)
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
  birth_longitude: DEFAULT_LON,
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

// 등급 색상 — 로케일 무관 stable key(grade_key)로 키잉. 백엔드가 grade_key
// (soulmate|good|fair|effort|caution)를 제공하므로 한국어 문자열 매칭에 의존하지 않는다.
const GRADE_TONE: Record<string, string> = {
  soulmate: "var(--grad-success)",
  good: "var(--brand-grad)",
  fair: "var(--grad-info)",
  effort: "var(--grad-warning)",
  caution: "linear-gradient(135deg,#e57373,#c62828)",
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
          <stop offset="0%" stopColor="#1fbfa8" stopOpacity="0.40" />
          <stop offset="100%" stopColor="#0d9488" stopOpacity="0.16" />
        </radialGradient>
        <filter id="penGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="#0d9488" floodOpacity="0.35" />
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
            <tspan>{tr(ax.tkey)}</tspan>
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
  gradeKey,
  avg,
}: {
  label: string;
  total: number;
  grade: string;
  gradeKey: string;
  avg: number | null;
}) {
  const { t: tr } = useTranslation();
  return (
    <div className="compat-gauge">
      <div className="cg-head">
        <span className="cg-label">{label}</span>
        <span className="cg-grade" style={{ background: GRADE_TONE[gradeKey] || "var(--brand-grad)" }}>
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
  const memberName = displayName(me, tr("compat.member_fallback"));  // ⚠️ 호칭=이메일 아이디 고정(운영자 결정) — lib/displayName.ts
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
  const [explainFailed, setExplainFailed] = useState(false);   // 무청크/에러/무응답 → 재시도 유도(고착 방지)
  const [explainMsgId, setExplainMsgId] = useState<number | undefined>(undefined);  // 해설 메시지 id(피드백용)
  const [compatSuggests, setCompatSuggests] = useState<string[]>([]);               // 추천질문 칩
  const [qDepth, setQDepth] = useState<"basic" | "deep">("basic");                  // 추가질문 등급(기본=1000P)
  const explainingRef = useRef(false);                                              // 항상 활성 입력
  const [explainStarted, setExplainStarted] = useState(false);                      // 해설 시작 여부(버튼 노출 제어)
  const acRef = useRef<AbortController | null>(null);                               // 현재 활성 스트림 취소(이탈 시 GPU 중단)
  const [refineStage, setRefineStage] = useState<string | null>(null);
  const [qaTurns, setQaTurns] = useState<{ role: "user" | "assistant"; content: string; refined?: boolean; is_preview?: boolean; charged?: number; message_id?: number }[]>([]);
  const [qInput, setQInput] = useState("");
  const [qStreaming, setQStreaming] = useState(false);
  // B-10 상대 초대(바이럴) — 내 생일을 담은 링크 생성
  const [inviteUrl, setInviteUrl] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);
  const depthRef = useRef(depth);
  depthRef.current = depth;
  // 이탈→복귀/새로고침 시 마지막 궁합 결과 자동 복원(무차감) + '지난 궁합' 목록
  const { restore, remember: rememberResult } = usePremiumRestore<CompatResponse>({
    storageKey: "compat_last_id",
    getOne: api.getCompatibility,
    apply: (r) => {
      setRes(r); setExplainText(""); setExplainStarted(false); setQaTurns([]);
      setTimeout(() => document.getElementById("compat-result")?.scrollIntoView({ behavior: "smooth" }), 80);
    },
  });
  const past = usePastList<PastItem>(() =>
    api.listCompat().then((r) => r.items.map((it) => ({
      id: it.compat_id,
      title: tr("compat.past_title", { a: it.a_label || tr("compat.self"), b: it.b_label || tr("compat.other") }),
      subtitle: [it.a_birth_date, it.b_birth_date].filter(Boolean).join("  ·  ") || undefined,
      when: fmtWhen(it.created_at),
    }))),
  );

  async function makeInvite() {
    if (inviteBusy) return;
    if (!a.birth_date) { setErr(tr("compat.invite_need_a")); return; }
    setInviteBusy(true); setErr(null);
    try {
      const r = await api.compatInviteCreate({
        birth_date: a.birth_date, birth_time: resolveBirthTime(a.birth_time, a.unknown_time),
        calendar: a.calendar, gender: a.gender, is_leap_month: a.calendar === "lunar" ? a.is_leap_month : false,
        apply_true_solar_time: !!a.apply_true_solar_time, night_zi_mode: a.night_zi_mode ?? "yaja",
        birth_longitude: a.birth_longitude ?? null, apply_equation_of_time: !!a.apply_equation_of_time,
      });
      setInviteUrl(r.url);
    } catch (e: any) {
      if (e?.status === 401) setErr(tr("compat.invite_login"));
      else setErr(e?.message || tr("compat.invite_fail"));
    } finally { setInviteBusy(false); }
  }

  async function copyInvite() {
    const full = window.location.origin + inviteUrl;
    try {
      await navigator.clipboard.writeText(full);
      setInviteCopied(true);
      window.setTimeout(() => setInviteCopied(false), 1600);
    } catch {
      window.prompt(tr("compat.invite_copy_prompt"), full);
    }
  }

  // 첫 번째 사람(본인): 공통 '기억하기' — 저장본 자동 채움 + 자동 저장(두 번째 사람은 미적용)
  const { remember, toggleRemember } = useBirthMemory(
    a, (patch) => setA((prev) => ({ ...prev, ...patch })),
  );

  // 궁합 초대 연계(운영자 검증에서 발견된 끊김 보완) — 수락 완료 푸시의 ?invite=토큰으로 진입하면
  // 초대에 저장된 두 생일(나+상대)을 자동으로 채운다(소유 검증은 서버 prefill이 수행).
  const loc = useLocation();
  const [inviteFilled, setInviteFilled] = useState(false);
  useEffect(() => {
    const tk = new URLSearchParams(loc.search).get("invite");
    if (!tk || !me) return;
    api.compatInvitePrefill(tk)
      .then((r) => {
        setA((prev) => ({ ...prev, ...profileToBirthValue(r.a), mode: "manual" }));
        setB((prev) => ({ ...prev, ...profileToBirthValue(r.b), mode: "manual", label: prev.label || tr("compat.other") }));
        setInviteFilled(true);
        window.history.replaceState(null, "", loc.pathname);   // 토큰 파라미터 정리
      })
      .catch(() => { /* 내 초대 아님/미수락 — 조용히 무시(일반 궁합 화면 그대로) */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id]);

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
    setExplainFailed(false);
    setExplainMsgId(undefined);
    setCompatSuggests([]);
    const ac = new AbortController(); acRef.current = ac;
    // 무응답 방지: 첫 청크 추적 + 60초 타임아웃 → 청크 0개로 끝나면 실패 전환(‘생성 중’ 고착 방지)
    let firstChunk = false;
    const to = window.setTimeout(() => { if (!firstChunk) { try { ac.abort(); } catch { /* noop */ } } }, 60000);
    try {
      await streamCompat(cid, { message: "", depth: depthRef.current }, {
        onChunk: (full) => { firstChunk = true; setExplainText(full); },
        onRefine: setExplainText,
        onStage: setRefineStage,
        onDone: (d) => { if (d?.assistant_message_id) setExplainMsgId(d.assistant_message_id); },
      }, ac.signal);
    } catch {
      /* 아래 finally에서 무청크 판정 */
    } finally {
      window.clearTimeout(to);
      setExplainStreaming(false); explainingRef.current = false;
      setRefineStage(null);
      if (!firstChunk) setExplainFailed(true);   // 청크 없이 끝남 = 실패 → 재시도 유도
      loadCompatSuggests(cid);
    }
  }
  function retryExplain() {
    if (res?.compat_id) { setExplainText(""); setExplainFailed(false); startExplain(res.compat_id); }
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
        onDone: (d) => {
          upd({ is_preview: d.is_preview, charged: d.credits_charged, message_id: d.assistant_message_id });  // 답변별 공유/피드백 연결
          if (d?.credits_charged > 0) refreshMe();   // 추가질문 차감 후 잔액 즉시 반영(패턴 B)
        },
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
    if (!(await ensureEntry("compat"))) return;
    setErr(null);
    setLoading(true);
    setRes(null);
    setExplainText("");
    setQaTurns([]);
    try {
      const out = await api.createCompatibility(toReq(a), toReq(b), depth);
      setRes(out);
      if (out.compat_id) rememberResult(out.compat_id);   // 재열람 복원용 id 기억(재차감 없이 다시 보기)
      refreshMe();   // 입장료 차감 후 사이드바·FAB 잔액 즉시 반영(패턴 B)
      // 입장료 결제(비프리뷰)면 해설을 자동 1회 생성(신년운세와 동일 UX — 운영자 지적 #12 '입장료 냈으니
      //   설명이 자동으로'). 프리뷰/비로그인은 버튼 유지.
      // ⚠️복원·지난궁합 재열람(usePremiumRestore apply:331)은 setExplainStarted(false) 유지라 자동시작 안 함 —
      //   무차감 재열람마다 GPU 추론이 도는 폭주(ef8887e4) 회귀 방지. abort 인프라(AbortController·언마운트
      //   abort·fetch signal)는 기존대로 유지되므로 이탈 시 즉시 중단됨.
      if (!out.is_preview) startExplain(out.compat_id);
      else setExplainStarted(false);
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
      <PrivacyNotice variant="tool" />
      {me && (
        <PastResultsDrawer
          items={past.items} loading={past.loading}
          onOpen={past.refresh} onPick={(id) => restore(id)}
          label={tr("compat.past_label")} emptyText={tr("compat.past_empty")}
        />
      )}
      <header className="compat-hero">
        <div className="compat-hero-badge">{tr("compat.hero_badge")}</div>
        <h1>{tr("compat.hero_title")}</h1>
        <p><Trans i18nKey="compat.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      <ReviewStrip source="compat" title={tr("landing.reviews_title")} limit={8} />
      <EntryFeeNotice menu="compat" />
      {inviteFilled && (
        <div className="cta-hint" role="status" style={{ textAlign: "center", marginBottom: 10 }}>
          <Trans i18nKey="compat.invite_filled" components={{ b: <b /> }} />
        </div>
      )}
      <div className="compat-input-grid">
        <PersonForm title={tr("compat.person1")} accent="a" p={a} setP={setA} profiles={profiles} loggedIn={!!me} />
        <div className="compat-link" aria-hidden>💞</div>
        <PersonForm title={tr("compat.person2")} accent="b" p={b} setP={setB} profiles={profiles} loggedIn={!!me} />
      </div>

      {/* B-10 상대 초대(바이럴) — 상대 생일을 모를 때 링크로 입력 부탁 */}
      {me && (
        <div className="cp-invite">
          <span><Trans i18nKey="compat.invite_hint" components={{ b: <b /> }} /></span>
          {inviteUrl ? (
            <>
              <span className="cp-invite-link">{window.location.origin}{inviteUrl}</span>
              <button onClick={copyInvite}>{inviteCopied ? tr("compat.copied") : tr("compat.copy_link")}</button>
            </>
          ) : (
            <button disabled={inviteBusy} onClick={makeInvite}>{inviteBusy ? tr("compat.invite_making") : tr("compat.invite_make")}</button>
          )}
        </div>
      )}

      <div className="compat-actions">
        <label className="compat-depth">
          <input type="checkbox" checked={depth === "deep"} onChange={(e) => setDepth(e.target.checked ? "deep" : "basic")} />
          {tr("compat.depth_deep")}
        </label>
        <button className="compat-cta" disabled={!canSubmit} onClick={submit}>
          {loading ? tr("compat.analyzing") : tr("compat.cta")}
        </button>
      {!canSubmit && !loading && reason && <div className="cta-hint">{reason}</div>}
      </div>
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
        <CompatExplainPanel
          explainText={explainText}
          explainStreaming={explainStreaming}
          explainFailed={explainFailed}
          onRetryExplain={retryExplain}
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
            // 개인정보 최소화(운영자 결정·울트라 순환검증 지적) — PDF는 무인증 공개 링크로 외부(카카오)
            //   공유되므로 이름/호칭을 넣지 않는다. 특히 상대방(제3자)의 이름은 동의 없이 외부로 나가면
            //   안 됨. 이름 대신 생년(항상 정확)으로만 두 분을 구분한다. (명식 캡션도 동일 정책)
            const yr = (s?: string) => (s || "").split("-")[0];
            const aDesc = yr(a.birth_date) ? tr("compat.born_year", { yr: yr(a.birth_date) }) : tr("compat.person_first");
            const bDesc = yr(b.birth_date) ? tr("compat.born_year", { yr: yr(b.birth_date) }) : tr("compat.person_second");
            return { docTitle: tr("compat.pdf_doc"), personLine: `${aDesc} · ${bDesc}`, item: tr("compat.pdf_item") };
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
// ⚠️ 부모(CompatibilityPage)가 스트림·QA·과금 상태를 직접 관리하는 '제어형' 패널.
//    components/ExplainChat(streamPath로 스스로 스트리밍하는 자립형)과는 아키텍처가 다르다.
//    공유/PDF/피드백 배선은 공통 AnswerActions로 이미 일원화됨(중복 아님). 이름 혼동만 제거.
function CompatExplainPanel({
  explainText, explainStreaming, explainFailed, onRetryExplain, refineStage, isPreview,
  qaTurns, qInput, setQInput, askFollowup, qStreaming, pdf, pdfHeader,
  feedbackMsgId, compatId, suggests, me, qDepth, setQDepth,
}: {
  explainText: string;
  explainStreaming: boolean;
  explainFailed: boolean;
  onRetryExplain: () => void;
  refineStage: string | null;
  isPreview: boolean;
  qaTurns: { role: "user" | "assistant"; content: string; refined?: boolean; is_preview?: boolean; charged?: number; message_id?: number }[];
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
        {explainText ? renderRich(explainText) : (
          explainFailed ? (
            <div className="explain-retry">
              <span>{tr("compat.explain_delay")}</span>
              <button type="button" className="explain-retry-btn" onClick={onRetryExplain}>{tr("compat.retry_free")}</button>
            </div>
          ) : (
            <span className="gen-live" role="status" aria-live="polite"><Trans i18nKey="compat.gen_live" components={{ b: <b /> }} /> <TypingDots /></span>
          )
        )}
      </div>
      {isPreview && (
        <div className="explain-preview-note">
          {me ? tr("compat.preview_note_charge") : tr("compat.preview_note")}
        </div>
      )}
      {pdf && explainText && !explainStreaming && (
        <AnswerActions
          text={(pdfHeader ? pdfHeader.trim() + "\n\n" : "") + stripMarkdown(explainText)}
          pdf={pdf}
          messageId={feedbackMsgId}
          source="compat"
          compatId={compatId}
          isLast
        />
      )}

      {/* 추가질문 채팅 */}
      <div className="compat-qa">
        <div className="cr-sub">{tr("compat.qa_title")}</div>
        {qaTurns.map((t, i) => (
          <div key={i} className={`qa-turn qa-${t.role}`}>
            <div className="qa-bubble">
              {t.content ? renderRich(t.content) : (
                <span className="gen-live" role="status" aria-live="polite"><Trans i18nKey="compat.answer_live" components={{ b: <b /> }} /> <TypingDots /></span>
              )}
              {t.refined && <span className="qa-refined">{tr("compat.qa_refined")}</span>}
              {t.role === "assistant" && typeof t.charged === "number" && t.charged > 0 && (
                <span className="qa-charged">{tr("compat.qa_charged", { n: fmtNum(t.charged) })}</span>
              )}
            </div>
            {/* 추가질문 답변에도 공유/복사/PDF·피드백 — 전 메뉴 표준. 미리보기·스트리밍 중 미노출 */}
            {t.role === "assistant" && t.content && !t.is_preview && pdf &&
              !(qStreaming && i === qaTurns.length - 1) && (
              <AnswerActions
                text={`${tr("compat.qa_q_prefix")}${qaTurns[i - 1]?.role === "user" ? qaTurns[i - 1].content : ""}\n\n${stripMarkdown(t.content)}`}
                pdf={{ ...pdf, item: ((qaTurns[i - 1]?.role === "user" ? qaTurns[i - 1].content : "") || pdf.item || tr("compat.qa_title")).slice(0, 40) }}
                messageId={t.message_id}
                source="compat"
                compatId={compatId}
                isLast={i === qaTurns.length - 1}
              />
            )}
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
  title, accent, p, setP, profiles, loggedIn, rememberSlot, remembered = false,
}: {
  title: string;
  accent: "a" | "b";
  p: PState;
  setP: (p: PState) => void;
  profiles: SajuProfile[];
  loggedIn: boolean;
  rememberSlot?: ReactNode;   // 첫 번째 사람(본인) 전용 '기억하기' 토글
  remembered?: boolean;       // 첫 번째 사람(본인)만 — 기억된 정보 강조 카드
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
        <>
          {rememberSlot}
          <BirthFields value={p} onChange={(patch) => setP({ ...p, ...patch })} remembered={remembered} />
        </>
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
      {res.credits_charged > 0 && (
        <div className="charge-receipt">{tr("compat.entry_charged", { n: res.credits_charged.toLocaleString() })}</div>
      )}
      <div className="cr-headline">
        <span className="cr-names">{res.person_a.label}</span>
        <span className="cr-heart">💞</span>
        <span className="cr-names">{res.person_b.label}</span>
        {headline && (
          <span className="cr-grade" style={{ background: GRADE_TONE[headline.grade_key || ""] || "var(--brand-grad)" }}>
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
              gradeKey={p.grade_key || ""}
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
