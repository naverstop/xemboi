import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, EvalRun, EvalStatus } from "../api";
import { fmtKSTDate } from "../lib/datetime";

/**
 * RAG 검색 품질 평가 대시보드(관리자).
 *
 * 무엇을 보는 화면인가:
 *  - 고정된 49개 사주 질문(평가셋)에 대해, 우리 지식DB에서 "정답에 필요한 핵심어"가
 *    검색 상위에 잘 올라오는지를 측정한 "검색 품질 회귀 테스트" 결과 추이.
 *  - 자료(책/유튜브/업로드)를 추가할 때마다 평가를 돌려, 그 추가가 검색 품질을
 *    실제로 올렸는지(효과)를 숫자로 확인한다.
 *  - 주의: 이 점수는 "검색이 정답 재료를 잘 가져오는가"를 보는 선행지표이며,
 *    최종 답변 문장 품질 그 자체는 아니다(답변은 LLM 단계에서 별도).
 */

// ---- 표시 헬퍼 ----
const PCT = (v: number) => `${(v * 100).toFixed(1)}%`;
const SCORE = (v: number) => v.toFixed(3);
const MS = (v: number) => `${v.toFixed(0)}ms`;

type MetricDef = {
  key: keyof EvalRun;
  label: string;
  short: string;
  color: string;
  fmt: (v: number) => string;
  higherBetter: boolean;
  hint: string;
};

const METRICS: MetricDef[] = [
  {
    key: "keyword_hit_rate_mean",
    label: "핵심 적중률",
    short: "hit",
    color: "#2563eb",
    fmt: PCT,
    higherBetter: true,
    hint: "한 질문의 정답 핵심어 중, 검색된 상위 청크에서 발견된 평균 비율. 높을수록 정답 재료를 잘 가져옴.",
  },
  {
    key: "pass_at_60",
    label: "합격률",
    short: "pass@60",
    color: "#16a34a",
    fmt: PCT,
    higherBetter: true,
    hint: "핵심어를 60% 이상 찾은 '합격' 질문의 비율. 목표 100%. 합격한 질문은 답변 근거가 충분하다고 본다.",
  },
  {
    key: "top1_score_mean",
    label: "최상위 유사도",
    short: "top1",
    color: "#9333ea",
    fmt: SCORE,
    higherBetter: true,
    hint: "1순위 검색 청크의 의미 유사도(코사인, 0~1). 질문과 가장 가까운 자료가 얼마나 가까운지.",
  },
  {
    key: "latency_ms_mean",
    label: "검색 속도",
    short: "lat",
    color: "#f59e0b",
    fmt: MS,
    higherBetter: false,
    hint: "질문 1건당 평균 검색 시간(ms). 낮을수록 빠름. 사용자 응답 체감과 직결.",
  },
];

/** 측정 조건 지문 — 이게 다르면 점수를 비교하면 안 된다.
 *
 * [P3-D2 2026-07-22] 예전 평가는 리랭커·게이트 없이 top_k 8로 돌아 운영(리랭커 on·게이트
 * 3종·top_k 4)과 완전히 다른 파이프라인을 쟀다. 운영과 정렬하면서 점수가 크게 떨어지는데,
 * 과거 52개 런과 한 선에 그리면 "품질 급락"으로 오독해 잘못된 롤백이 난다. */
function evalMode(r: EvalRun): string {
  return `${r.eval_mode || "legacy"}/k${r.top_k}/N${r.n_questions}`;
}

/** i번째 run과 **같은 측정 조건**을 가진 가장 최근의 이전 run 인덱스(=공정 비교 대상). 없으면 -1. */
function comparableIdx(runs: EvalRun[], i: number): number {
  for (let j = i - 1; j >= 0; j--) {
    if (evalMode(runs[j]) === evalMode(runs[i])) return j;
  }
  return -1;
}

function deltaLabel(m: MetricDef, cur: number, prev: number) {
  const d = cur - prev;
  const improved = m.higherBetter ? d > 1e-9 : d < -1e-9;
  const worse = m.higherBetter ? d < -1e-9 : d > 1e-9;
  // 색=좋고 나쁨(국내 관례: 개선=빨강, 하락=파랑), 화살표=수치 방향(증가 ▲ / 감소 ▼).
  // 속도처럼 낮을수록 좋은 지표는 값이 내려가면 ▼ 이지만 색은 빨강(개선)으로 표시돼 혼동이 없다.
  const color = improved ? "#dc2626" : worse ? "#2563eb" : "var(--ink-400)";
  const arrow = d > 1e-9 ? "▲" : d < -1e-9 ? "▼" : "—";
  let txt: string;
  if (m.fmt === PCT) txt = `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)}%p`;
  else if (m.fmt === MS) txt = `${d >= 0 ? "+" : ""}${d.toFixed(0)}ms`;
  else txt = `${d >= 0 ? "+" : ""}${d.toFixed(3)}`;
  const word = improved ? "개선" : worse ? "하락" : "유지";
  return { color, arrow, txt, word };
}

// ===================== KPI 효과 타일 =====================
function KpiTiles({ runs }: { runs: EvalRun[] }) {
  const last = runs.length - 1;
  const compIdx = comparableIdx(runs, last);
  const cur = runs[last];
  const prev = compIdx >= 0 ? runs[compIdx] : null;

  return (
    <div className="card">
      <div className="card-head-row" style={{ marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>최신 평가 효과</h3>
        <span style={{ fontSize: 12, color: "var(--ink-400)" }}>
          {prev
            ? `직전 동일조건(${evalMode(cur)}) 대비 변화 · 라벨 ${cur.tag || "-"}`
            : `같은 조건(${evalMode(cur)})의 이전 실행 없음 — 비교 생략 · 라벨 ${cur.tag || "-"}`}
        </span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 12,
        }}
      >
        {METRICS.map((m) => {
          const v = Number(cur[m.key]) || 0;
          const d = prev ? deltaLabel(m, v, Number(prev[m.key]) || 0) : null;
          return (
            <div
              key={m.key}
              title={m.hint}
              style={{
                border: "1px solid var(--line)",
                borderRadius: 12,
                padding: "12px 14px",
                background: "var(--bg)",
              }}
            >
              <div style={{ fontSize: 12, color: "var(--ink-600)", display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 9, height: 9, borderRadius: 9, background: m.color, display: "inline-block" }} />
                {m.label}
              </div>
              <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4, color: "var(--ink-900)" }}>
                {m.fmt(v)}
              </div>
              {d ? (
                <div style={{ fontSize: 12.5, marginTop: 2, color: d.color, fontWeight: 600 }}>
                  {d.arrow} {d.txt} <span style={{ opacity: 0.8 }}>({d.word})</span>
                </div>
              ) : (
                <div style={{ fontSize: 12, marginTop: 2, color: "var(--ink-400)" }}>비교 기준 없음</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ===================== 다중 라인 차트(공용) =====================
type Series = { key: keyof EvalRun; label: string; color: string; fmt: (v: number) => string };

function LineChart({
  runs,
  series,
  title,
  yKind = "ratio",
  targetLine,
}: {
  runs: EvalRun[];
  series: Series[];
  title: string;
  // pct: 0~1 값을 %축으로 / ratio: 0~1 값을 소수축으로 / count: ms 등 절대값(0부터 정수축)
  yKind?: "pct" | "ratio" | "count";
  targetLine?: { value: number; label: string };
}) {
  const W = 720;
  const H = 260;
  const padL = 46;
  const padR = 18;
  const padT = 22;
  const padB = 46;

  const vals = runs.flatMap((r) => series.map((s) => Number(r[s.key]) || 0));
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  // 목표선이 있으면 양방향으로 범위에 포함시켜 "항상" 보이게 한다(데이터가 목표 위/아래로
  // 쏠려도 사라지지 않음).
  if (targetLine) {
    lo = Math.min(lo, targetLine.value);
    hi = Math.max(hi, targetLine.value);
  }
  if (yKind === "count") {
    // ms 등 절대값: 0부터 시작하는 정수축. 데이터 범위로 윗단만 확대.
    const span = hi - lo || Math.max(1, hi * 0.2);
    hi = hi + span * 0.2;
    const step = Math.max(1, Math.round(hi / 4));
    lo = 0;
    hi = Math.ceil(hi / step) * step;
  } else {
    // 0~1 비율(%/소수): 데이터 범위로 확대하되 [0,1] 안에 가두고 0.05 단위 스냅.
    // hi 를 1.0 로 캡해 정수축으로 뒤집히는 일이 없게 한다.
    const span = hi - lo || 0.1;
    lo = Math.max(0, lo - span * 0.25);
    hi = Math.min(1, hi + span * 0.25);
    lo = Math.floor(lo * 20) / 20;
    hi = Math.ceil(hi * 20) / 20;
    if (hi - lo < 0.1) {
      hi = Math.min(1, lo + 0.1);
      lo = Math.max(0, hi - 0.1);
    }
  }

  const n = runs.length;
  const x = (i: number) =>
    n <= 1 ? (padL + (W - padR)) / 2 : padL + (i * (W - padL - padR)) / (n - 1);
  const y = (v: number) => H - padB - ((v - lo) / (hi - lo)) * (H - padT - padB);

  const ticks = 4;
  const gridVals = Array.from({ length: ticks + 1 }, (_, k) => lo + ((hi - lo) * k) / ticks);
  const axisTextStyle = { fill: "var(--ink-400)" } as const;

  // 데이터가 매일 쌓이면 점이 많아지므로, 값 라벨/축 라벨을 솎아 가독성을 유지한다.
  const dense = n > 12;
  const labelEvery = Math.max(1, Math.ceil(n / 10));
  const showXLabel = (i: number) => i === 0 || i === n - 1 || i % labelEvery === 0;

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
        {/* 가로 그리드 + Y 라벨 */}
        {gridVals.map((gv, k) => (
          <g key={k}>
            <line x1={padL} x2={W - padR} y1={y(gv)} y2={y(gv)} stroke="var(--line)" strokeWidth={1} />
            <text x={padL - 6} y={y(gv) + 3} fontSize={10} textAnchor="end" style={axisTextStyle}>
              {yKind === "pct" ? `${Math.round(gv * 100)}%` : yKind === "count" ? Math.round(gv) : gv.toFixed(2)}
            </text>
          </g>
        ))}

        {/* 목표선 */}
        {targetLine && targetLine.value >= lo && targetLine.value <= hi && (
          <g>
            <line
              x1={padL}
              x2={W - padR}
              y1={y(targetLine.value)}
              y2={y(targetLine.value)}
              stroke="#dc2626"
              strokeWidth={1.2}
              strokeDasharray="5 4"
            />
            <text x={W - padR} y={y(targetLine.value) - 4} fontSize={10} textAnchor="end" fill="#dc2626">
              {targetLine.label}
            </text>
          </g>
        )}

        {/* 시리즈 */}
        {series.map((s) => {
          const pts = runs.map((r, i) => `${x(i)},${y(Number(r[s.key]) || 0)}`).join(" ");
          return (
            <g key={String(s.key)}>
              <polyline fill="none" stroke={s.color} strokeWidth={2.5} points={pts} />
              {runs.map((r, i) => {
                const v = Number(r[s.key]) || 0;
                return (
                  <g key={i}>
                    <circle cx={x(i)} cy={y(v)} r={dense ? 2.5 : 4} fill={s.color}>
                      <title>{`${s.label} · ${r.tag || fmtKSTDate(r.ts)}: ${s.fmt(v)}`}</title>
                    </circle>
                    {!dense && (
                      <text
                        x={x(i)}
                        y={y(v) - 9}
                        fontSize={10}
                        textAnchor="middle"
                        fill={s.color}
                        fontWeight={700}
                      >
                        {s.fmt(v)}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}

        {/* X 라벨(라벨/날짜 + N) — 점이 많으면 솎아서 표시 */}
        {runs.map((r, i) =>
          showXLabel(i) ? (
            <text key={i} x={x(i)} y={H - 24} fontSize={10} textAnchor="middle" style={axisTextStyle}>
              {(r.tag || r.ts.slice(5, 10)).slice(0, 16)}
            </text>
          ) : null
        )}
        {runs.map((r, i) =>
          showXLabel(i) ? (
            <text key={`n${i}`} x={x(i)} y={H - 11} fontSize={9} textAnchor="middle" style={{ fill: "var(--ink-400)" }}>
              N={r.n_questions}
            </text>
          ) : null
        )}
      </svg>

      {/* 범례 */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, marginTop: 4 }}>
        {series.map((s) => (
          <span key={String(s.key)} style={{ color: s.color, fontWeight: 600 }}>
            ● {s.label}
          </span>
        ))}
        <span style={{ color: "var(--ink-400)" }}>※ Y축은 변화를 보기 쉽게 확대 표시</span>
      </div>
    </div>
  );
}

// ===================== 실행 컨트롤 + 신선도 =====================
function RunControls({
  runs,
  onDone,
}: {
  runs: EvalRun[];
  onDone: () => void;
}) {
  const [status, setStatus] = useState<EvalStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [tag, setTag] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.evalStatus();
      setStatus(s);
      return s;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  const startPolling = useCallback(() => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      const s = await fetchStatus();
      if (s && !s.running) {
        if (pollRef.current) window.clearInterval(pollRef.current);
        pollRef.current = null;
        setBusy(false);
        setMsg(s.last_error ? `실행 실패: ${s.last_error}` : "평가 완료 — 결과를 갱신했습니다.");
        onDone();
      }
    }, 2500);
  }, [fetchStatus, onDone]);

  const run = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.evalRun(tag.trim() || undefined);
      setMsg(r.message);
      await fetchStatus();
      startPolling();
    } catch (e: any) {
      setBusy(false);
      setMsg(e?.message || "실행 요청 실패");
    }
  };

  // 신선도: 마지막 run 이 며칠 전인지
  const last = runs[runs.length - 1];
  const ageDays = last ? Math.floor((Date.now() - new Date(last.ts).getTime()) / 86400000) : null;
  const stale = ageDays != null && ageDays >= 7;

  const running = busy || status?.running;

  return (
    <div className="card">
      <div className="card-head-row">
        <div>
          <h3 style={{ margin: 0 }}>평가 실행</h3>
          <div style={{ fontSize: 12.5, color: "var(--ink-600)", marginTop: 4 }}>
            매일 <strong>03:30</strong> 야간 학습(코퍼스 색인) 직후 자동으로 평가가 1회 실행돼 추세가 쌓입니다.
            아래 버튼은 지금 즉시 1회 더 돌리고 싶을 때(예: 방금 자료 추가) 사용하세요.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            placeholder="라벨(예: after_youtube)"
            style={{ width: 180, fontSize: 13 }}
            disabled={!!running}
          />
          <button onClick={run} disabled={!!running}>
            {running ? "평가 중…" : "지금 평가 실행"}
          </button>
        </div>
      </div>

      {last && (
        <div
          style={{
            fontSize: 12.5,
            marginTop: 4,
            padding: stale ? "8px 10px" : 0,
            borderRadius: 8,
            background: stale ? "#fef3c7" : "transparent",
            color: stale ? "#92400e" : "var(--ink-600)",
          }}
        >
          {stale ? "⚠ " : ""}
          마지막 평가: {last.ts.replace("T", " ").slice(0, 16)} ({ageDays}일 전) · 라벨 {last.tag || "-"}
          {stale && " — 그동안 자료를 추가했다면 다시 평가하는 것을 권장합니다."}
        </div>
      )}

      {msg && (
        <div
          style={{
            fontSize: 13,
            marginTop: 8,
            color: msg.includes("실패") ? "#b91c1c" : "var(--brand-700)",
          }}
        >
          {running ? "⏳ " : ""}
          {msg}
        </div>
      )}
    </div>
  );
}

// ===================== 상세 비교 표 =====================
function CompareTable({ runs, allRuns }: { runs: EvalRun[]; allRuns: EvalRun[] }) {
  // 표는 최근 구간(runs)만 보여주되, 비교 대상(동일 N 직전)은 전체 이력(allRuns)에서 찾는다.
  const offset = allRuns.length - runs.length;
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>실행별 상세 (직전 동일조건 대비 변화)</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>시각</th>
              <th>라벨</th>
              <th>N</th>
              <th>핵심 적중률</th>
              <th>합격률</th>
              <th>최상위 유사도</th>
              <th>평균 유사도</th>
              <th>속도</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r, i) => {
              const gi = offset + i; // 전체 이력 기준 인덱스
              const ci = comparableIdx(allRuns, gi);
              const prev = ci >= 0 ? allRuns[ci] : null;
              // 측정 조건(정렬여부·top_k·N)이 직전과 다르면 추세 단절 — 점수를 이어 읽으면 안 된다.
              const modeChanged = gi > 0 && evalMode(allRuns[gi - 1]) !== evalMode(r);
              const aligned = (r.eval_mode || "legacy") === "aligned";
              const cell = (m: MetricDef) => {
                const v = Number(r[m.key]) || 0;
                const d = prev ? deltaLabel(m, v, Number(prev[m.key]) || 0) : null;
                return (
                  <td>
                    <div style={{ fontWeight: 600 }}>{m.fmt(v)}</div>
                    {d && (
                      <div style={{ fontSize: 11, color: d.color }}>
                        {d.arrow} {d.txt}
                      </div>
                    )}
                  </td>
                );
              };
              return (
                <tr key={gi}>
                  <td>{gi + 1}</td>
                  <td style={{ fontSize: 11 }}>{r.ts.replace("T", " ").slice(0, 16)}</td>
                  <td>
                    {r.tag || "-"}
                    <span
                      className="tag"
                      style={{ marginLeft: 6, opacity: 0.85 }}
                      title={
                        aligned
                          ? "운영과 동일한 검색 조건(리랭커·임계·게이트·top_k)으로 측정 — 실제 서비스 품질"
                          : "옛 방식: 리랭커 없음·게이트 없음·top_k 8. 후보 풀이 운영의 1.88배라 점수가 높게 나온다(운영 품질 아님)"
                      }
                    >
                      {aligned ? "운영정렬" : "옛측정"}
                    </span>
                    {modeChanged && (
                      <span
                        className="tag pending"
                        style={{ marginLeft: 6 }}
                        title="측정 조건이 직전 실행과 다르다 — 위아래 점수를 이어서 비교하지 말 것"
                      >
                        조건변경
                      </span>
                    )}
                  </td>
                  <td>{r.n_questions}</td>
                  {cell(METRICS[0])}
                  {cell(METRICS[1])}
                  {cell(METRICS[2])}
                  <td style={{ fontWeight: 600 }}>{SCORE(Number(r.topk_mean_score_mean) || 0)}</td>
                  {cell(METRICS[3])}
                </tr>
              );
            }).reverse()}{/* 최신 실행이 맨 위로(역순 표시) — 비교/번호는 시간순 기준 유지 */}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--ink-400)", marginTop: 8 }}>
        ※ 변화(Δ)는 <strong>같은 N(표본 크기)</strong>을 가진 가장 최근 이전 실행과 비교합니다. N이 다르면
        평가셋이 바뀐 것이라 점수 차이를 효과로 해석하면 안 됩니다.
      </div>
    </div>
  );
}

// ===================== 해석 가이드 =====================
function Guide() {
  return (
    <details className="card">
      <summary style={{ cursor: "pointer", fontWeight: 700 }}>이 화면 읽는 법 · 지표 설명</summary>
      <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--ink-600)", marginTop: 10 }}>
        <p style={{ marginTop: 0 }}>
          <strong>무엇을 보나요?</strong> 고정된 49개 사주 질문에 대해, 우리 지식DB(RAG)가{" "}
          <em>정답에 필요한 핵심어가 담긴 자료</em>를 검색 상위에 잘 올려주는지를 측정한 결과입니다. 자료를 추가할
          때마다 평가를 돌리면, 그 추가가 검색 품질을 실제로 올렸는지(효과)를 숫자로 확인할 수 있습니다.
        </p>
        <ul style={{ margin: "0 0 10px", paddingLeft: 18 }}>
          <li>
            <strong style={{ color: "#2563eb" }}>핵심 적중률(hit)</strong> — 질문의 핵심어 중 검색결과에서 발견된
            평균 비율. <b>높을수록 좋음.</b>
          </li>
          <li>
            <strong style={{ color: "#16a34a" }}>합격률(pass@60)</strong> — 핵심어를 60% 이상 찾은 질문의 비율.{" "}
            <b>목표 100%</b>, 높을수록 좋음.
          </li>
          <li>
            <strong style={{ color: "#9333ea" }}>최상위 유사도(top1)</strong> — 1순위 자료의 의미 유사도(0~1).
            높을수록 질문에 딱 맞는 자료가 있다는 뜻.
          </li>
          <li>
            <strong style={{ color: "#f59e0b" }}>검색 속도(lat)</strong> — 질문당 평균 검색 시간(ms).{" "}
            <b>낮을수록 좋음.</b>
          </li>
        </ul>
        <p style={{ margin: 0 }}>
          <strong>꼭 기억할 점</strong> ① 이 점수는 “검색이 정답 재료를 잘 가져오는가”를 보는 <u>선행지표</u>이며,
          최종 답변 문장의 품질 자체는 아닙니다(답변은 LLM 단계에서 별도로 생성). ② 표본 크기(N)가 다른 실행끼리는
          점수를 직접 비교하지 마세요 — 평가셋이 바뀐 것입니다. ③ 효과를 정확히 보려면 자료 추가 <u>전·후</u>를{" "}
          <u>같은 N</u>으로 한 번씩 돌려 비교하세요.
        </p>
      </div>
    </details>
  );
}

// ===================== 메인 =====================
export default function TrendPage() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    api
      .runs()
      .then((r) => {
        setRuns(r.runs);
        setErr(null);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (err) return <div className="card err">{err}</div>;
  if (!loaded) return <div className="card">불러오는 중…</div>;

  // 데이터가 없어도 실행 컨트롤/가이드는 보여준다.
  const headerNote =
    runs.length === 0
      ? "아직 평가 기록이 없습니다. 아래 ‘지금 평가 실행’으로 첫 평가를 돌려보세요."
      : `총 ${runs.length}회 평가 · 최근 라벨 ${runs[runs.length - 1].tag || "-"}`;

  // 매일 자동 평가로 점이 계속 쌓이므로, 차트/표는 최근 구간만 보여 가독성을 유지한다.
  const MAX_VIEW = 30;
  const view = runs.slice(-MAX_VIEW);
  const truncated = runs.length > MAX_VIEW;

  return (
    <>
      <div className="card">
        <h2 style={{ margin: "0 0 4px" }}>RAG 검색 품질 평가</h2>
        <div style={{ fontSize: 13, color: "var(--ink-600)" }}>
          지식DB가 “정답에 필요한 자료”를 검색 상위에 잘 올려주는지 측정하는 회귀 테스트입니다. {headerNote}
        </div>
      </div>

      <RunControls runs={runs} onDone={load} />

      {runs.length > 0 && <KpiTiles runs={runs} />}

      {truncated && (
        <div style={{ fontSize: 12, color: "var(--ink-400)", margin: "-8px 2px 8px" }}>
          ※ 아래 차트·표는 가독성을 위해 최근 {MAX_VIEW}회만 표시합니다 (전체 {runs.length}회 기록 보관).
        </div>
      )}

      {view.length > 0 && (
        <LineChart
          runs={view}
          title="검색 정확도 추세 (핵심 적중률 · 합격률)"
          yKind="pct"
          targetLine={{ value: 0.6, label: "합격 기준 60%" }}
          series={[
            { key: "keyword_hit_rate_mean", label: "핵심 적중률", color: "#2563eb", fmt: PCT },
            { key: "pass_at_60", label: "합격률(≥60%)", color: "#16a34a", fmt: PCT },
          ]}
        />
      )}

      {view.length > 0 && (
        <LineChart
          runs={view}
          title="검색 유사도 추세 (의미적 일치도)"
          yKind="ratio"
          series={[
            { key: "top1_score_mean", label: "최상위 유사도", color: "#9333ea", fmt: SCORE },
            { key: "topk_mean_score_mean", label: "평균 유사도", color: "#0ea5e9", fmt: SCORE },
          ]}
        />
      )}

      {view.length > 0 && (
        <LineChart
          runs={view}
          title="검색 속도 추세 (낮을수록 빠름)"
          yKind="count"
          series={[{ key: "latency_ms_mean", label: "평균 검색시간(ms)", color: "#f59e0b", fmt: MS }]}
        />
      )}

      {view.length > 0 && <CompareTable runs={view} allRuns={runs} />}

      <Guide />
    </>
  );
}
