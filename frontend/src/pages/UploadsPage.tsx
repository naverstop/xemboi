import { useEffect, useState } from "react";
import { api, UploadDTO, UploadStats, LearningProgress } from "../api";
import { fmtKSTDateTime as fmtKST } from "../lib/datetime";

const PAGE_SIZE = 10;

export default function UploadsPage() {
  const [items, setItems] = useState<UploadDTO[]>([]);
  const [stats, setStats] = useState<UploadStats | null>(null);
  const [statsErr, setStatsErr] = useState(false);  // 학습 성과(관리자 전용) 조회 실패(세션 만료 등)
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [submitter, setSubmitter] = useState("admin");
  const [learning, setLearning] = useState(false);   // 수동/야간 학습 배치 실행 중
  const [learnMsg, setLearnMsg] = useState<string | null>(null);
  const [progress, setProgress] = useState<LearningProgress | null>(null);  // 실시간 진행상황

  const reload = async () => {
    try {
      const r = await api.listUploads(filter || undefined);
      setItems(r);
      setPage((p) => Math.min(p, Math.max(0, Math.ceil(r.length / PAGE_SIZE) - 1)));
      // 성과 통계는 관리자 전용 — 실패(세션 만료/비관리자)해도 목록은 표시하고, 안내만 띄운다.
      api.uploadStats().then((s) => { setStats(s); setStatsErr(false); }).catch(() => setStatsErr(true));
    } catch (e: any) {
      setErr(e.message);
    }
  };

  useEffect(() => {
    setPage(0);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  // 학습 배치 실행 상태 폴링(실행 중이면 5초마다, 끝나면 멈춤)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    const poll = async () => {
      try {
        const r = await api.learningStatus();
        if (!alive) return;
        setLearning(r.running);
        setProgress(r.progress ?? null);
        if (r.running) {
          setLearnMsg("학습 배치 실행 중…(CPU 백그라운드)");
          timer = setTimeout(poll, 3000);   // 실행 중엔 3초마다 진행상황 갱신
        } else if (learnMsg && learnMsg.startsWith("학습 배치 실행 중")) {
          setLearnMsg(null);
          reload();
        }
      } catch { /* 상태 조회 실패는 무시 */ }
    };
    poll();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runLearning = async () => {
    setLearnMsg(null);
    try {
      const r = await api.runManualLearning();
      setLearning(true);
      setLearnMsg("학습 배치 실행 중…(CPU 백그라운드)");
      alert(r.message);
      setTimeout(async function poll() {
        try {
          const s = await api.learningStatus();
          setLearning(s.running);
          if (s.running) setTimeout(poll, 5000);
          else { setLearnMsg("✓ 학습 완료 — 목록 상태를 새로고침해 확인하세요."); reload(); }
        } catch {}
      }, 5000);
    } catch (e: any) {
      const msg = String(e?.message || e);
      alert(msg);   // 409(이미 실행 중) 등
      setLearnMsg(msg);
    }
  };

  // 학습 상태 폴링 시작(zip 자동학습/수동학습 공용) — 끝나면 멈추고 목록 새로고침
  const pollLearning = () => {
    setLearning(true);
    setLearnMsg("학습 배치 실행 중…(CPU 백그라운드)");
    setTimeout(async function poll() {
      try {
        const s = await api.learningStatus();
        setLearning(s.running);
        setProgress(s.progress ?? null);
        if (s.running) setTimeout(poll, 3000);
        else { setLearnMsg("✓ 학습 완료 — 목록을 새로고침했어요."); reload(); }
      } catch { /* 무시 */ }
    }, 2000);
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      // zip: 서버가 풀어서 pdf/이미지/txt 를 학습 파이프라인에 투입 + 자동 학습 시작
      if (/\.zip$/i.test(file.name)) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("submitter", submitter);
        const r = await api.submitUploadZip(fd);
        setFile(null);
        setTitle("");
        await reload();
        setLearnMsg(r.message);
        alert(r.message);
        if (r.learning_started) pollLearning();
        return;
      }
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title || file.name);
      fd.append("category", "user_upload");
      fd.append("submitter", submitter);
      await api.submitUpload(fd);
      setFile(null);
      setTitle("");
      await reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id: number) => {
    setBusy(true);
    setErr(null);
    try {
      await api.approve(id, submitter, "approved via UI");
      await reload();
      // 즉시 색인이 아니라 야간 배치 예약임을 명확히 안내
      alert("야간 학습으로 예약되었습니다. 매일 자정 이후 일괄 학습되며, 지금 바로 반영되지는 않습니다.");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const reject = async (id: number) => {
    const c = prompt("거절 사유?") || "rejected";
    setBusy(true);
    setErr(null);
    try {
      await api.reject(id, submitter, c);
      await reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = items.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  return (
    <>
      <div className="card">
        <h3>자료 업로드</h3>
        <p style={{ marginTop: 0, fontSize: 13, color: "var(--ink-600, #666)" }}>
          업로드 후 <b>승인</b>하면 즉시 학습되지 않고, 매일 <b>자정 이후 야간 배치(CPU)</b>로 일괄
          학습됩니다. PDF·이미지는 OCR→색인, 음성/영상은 STT→색인을 거칩니다.
          <br />
          📦 <b>ZIP</b>으로 올리면 서버가 풀어 안의 <b>PDF·이미지·txt</b>를 한 번에 등록하고 <b>바로 학습을 시작</b>합니다(따로 폴더에 넣을 필요 없음).
        </p>
        <div className="row">
          <div>
            <label>파일 (txt/pdf/이미지/mp4/zip)</label>
            <input
              type="file"
              accept=".txt,.pdf,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.mp4,.m4a,.mov,.webm,.mp3,.wav,.zip"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </div>
          <div>
            <label>제목</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="(비우면 파일명)" />
          </div>
          <div>
            <label>제출자</label>
            <input value={submitter} onChange={(e) => setSubmitter(e.target.value)} />
          </div>
          <div className="upl-submit-cell">
            <label>&nbsp;</label>
            <button onClick={submit} disabled={!file || busy}>
              {file && /\.zip$/i.test(file.name) ? "📦 ZIP 등록+학습" : "업로드"}
            </button>
          </div>
        </div>
        <div className="upl-action-bar">
          <span className="upl-action-hint">
            💡 <b>학습자료_new 폴더</b>에 직접 올린 PDF·이미지나 승인된 자료를 야간 배치 대기 없이 <b>지금 즉시</b> 학습합니다(CPU).
          </span>
          <button
            className="upl-learn-btn"
            onClick={runLearning}
            disabled={learning}
            title="학습자료_new 폴더의 PDF/이미지와 승인된 자료를 야간 배치를 기다리지 않고 지금 즉시 학습합니다(CPU)."
          >
            {learning ? "⏳ 학습 실행 중…" : "🚀 관리자 수동 학습 실행"}
          </button>
        </div>
        {(learning || progress) && <LearningProgressCard p={progress} running={learning} />}
        {learnMsg && !learning && !progress && (
          <div style={{ marginTop: 8, fontSize: 13, color: "var(--ink-600, #666)" }}>{learnMsg}</div>
        )}
        {err && <div className="err">{err}</div>}
      </div>

      {stats ? (
        <StatsPanel s={stats} />
      ) : statsErr ? (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>학습 성과</h3>
          <p style={{ fontSize: 13, color: "var(--ink-600, #666)" }}>
            학습 성과 통계는 <b>관리자 로그인</b> 후 표시됩니다. 로그인 세션이 만료됐다면 다시 로그인해 주세요.
          </p>
          <button className="secondary" onClick={() => { window.location.href = "/login"; }}>관리자 로그인</button>
        </div>
      ) : null}

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>업로드 목록</h3>
          <div>
            <label style={{ display: "inline-block", marginRight: 8 }}>상태</label>
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">전체</option>
              <option value="pending">pending</option>
              <option value="approved">approved</option>
              <option value="indexed">indexed</option>
              <option value="rejected">rejected</option>
              <option value="failed">failed</option>
            </select>
            <button className="secondary" onClick={reload} style={{ marginLeft: 8 }}>
              새로고침
            </button>
          </div>
        </div>
        <div className="table-wrap" style={{ marginTop: 8 }}>
        <table className="upl-table">
          <thead>
            <tr>
              <th>#</th>
              <th>제목</th>
              <th>종류</th>
              <th>크기</th>
              <th>상태</th>
              <th>청크</th>
              <th>제출시각</th>
              <th>액션</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((u) => (
              <tr key={u.id}>
                <td data-label="#">{u.id}</td>
                <td data-label="제목">{u.title}</td>
                <td data-label="종류">{u.file_kind}</td>
                <td data-label="크기">{(u.size_bytes / 1024).toFixed(1)} KB</td>
                <td data-label="상태">
                  <span className={`tag ${u.status}`}>{u.status}</span>
                </td>
                <td data-label="청크">{u.chunks_count ?? "-"}</td>
                <td data-label="제출시각" style={{ fontSize: 11 }}>{fmtKST(u.submitted_at)}</td>
                <td data-label="액션">
                  {u.status === "pending" && (
                    <>
                      <button onClick={() => approve(u.id)} disabled={busy} title="승인하면 야간 학습 대기열에 들어갑니다(즉시 반영 아님)">승인(야간학습)</button>{" "}
                      <button className="danger" onClick={() => reject(u.id)} disabled={busy}>
                        거절
                      </button>
                    </>
                  )}
                  {u.status === "approved" && (
                    <span style={{ fontSize: 11, color: "var(--ink-400, #999)" }}>야간 학습 대기</span>
                  )}
                  {(u.status === "rejected" || u.status === "failed") && u.review_comment && (
                    <span
                      title={u.review_comment}
                      style={{ fontSize: 11, color: "var(--danger, #d23f31)", cursor: "help" }}
                    >
                      ⚠ {u.review_comment.length > 28 ? u.review_comment.slice(0, 28) + "…" : u.review_comment}
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={8} style={{ textAlign: "center", color: "#888" }}>없음</td>
              </tr>
            )}
          </tbody>
        </table>
        </div>

        {items.length > 0 && (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginTop: 12 }}>
            <button className="secondary" disabled={safePage <= 0} onClick={() => setPage(safePage - 1)}>
              ‹ 이전
            </button>
            <span style={{ fontSize: 13, color: "var(--ink-600, #666)" }}>
              {safePage + 1} / {pageCount} 페이지 · 총 {items.length}건
            </span>
            <button className="secondary" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>
              다음 ›
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// ── 학습 성과 패널(통계 카드 + 상태분포 + 14일 색인추세) ──────────────────
const STATUS_META: Record<string, { label: string; color: string }> = {
  indexed: { label: "색인완료", color: "#16a34a" },
  approved: { label: "야간대기", color: "#0277b6" },
  pending: { label: "검수대기", color: "#d97706" },
  rejected: { label: "거절", color: "#dc2626" },
  failed: { label: "실패", color: "#9333ea" },
};

function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div style={{ flex: "1 1 120px", minWidth: 120, padding: "12px 14px", border: "1px solid var(--line,#e5e7eb)", borderRadius: 10, background: "var(--card,#fff)" }}>
      <div style={{ fontSize: 12, color: "var(--ink-500,#888)" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: accent || "var(--ink-900,#111)", lineHeight: 1.2 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--ink-400,#999)" }}>{sub}</div>}
    </div>
  );
}

function StatsPanel({ s }: { s: UploadStats }) {
  // 14일 추세 지표 토글: 청크 수(자료별 학습량) / 파일 수. 청크가 핵심 지표라 기본값.
  const [trendMetric, setTrendMetric] = useState<"chunks" | "files">("chunks");
  const sizeMB = (s.total_size_bytes / 1048576).toFixed(1);
  const statuses = Object.keys(STATUS_META).filter((k) => (s.by_status[k] || 0) > 0);
  const maxStatus = Math.max(1, ...statuses.map((k) => s.by_status[k] || 0));
  const trendVal = (t: { indexed: number; chunks?: number }) =>
    trendMetric === "chunks" ? (t.chunks ?? 0) : t.indexed;
  const maxTrend = Math.max(1, ...s.trend.map(trendVal));
  const filesTotal = s.trend.reduce((a, t) => a + t.indexed, 0);
  const trendTotal = s.trend.reduce((a, t) => a + trendVal(t), 0);
  const trendUnit = trendMetric === "chunks" ? "청크" : "건";

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>학습 성과</h3>

      {/* 핵심 숫자 카드 */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        <StatCard label="코퍼스 청크 (색인량)" value={s.corpus_chunks != null ? s.corpus_chunks.toLocaleString() : "—"} sub="Qdrant saju_corpus" accent="#0277b6" />
        <StatCard label="색인 완료 파일" value={String(s.indexed_count)} sub={`총 업로드 ${s.total}건`} accent="#16a34a" />
        <StatCard label="총 업로드" value={String(s.total)} sub={`${sizeMB} MB`} />
        <StatCard label="최근 14일 색인" value={String(filesTotal)} sub="신규 색인 파일" />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 20, marginTop: 16 }}>
        {/* 상태 분포 막대 */}
        <div style={{ flex: "1 1 260px", minWidth: 240 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, color: "var(--ink-700,#444)" }}>상태 분포</div>
          {statuses.length === 0 && <div style={{ fontSize: 12, color: "#999" }}>데이터 없음</div>}
          {statuses.map((k) => {
            const v = s.by_status[k] || 0;
            const meta = STATUS_META[k];
            return (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <div style={{ width: 64, fontSize: 12, color: "var(--ink-600,#666)" }}>{meta.label}</div>
                <div style={{ flex: 1, background: "var(--line,#eef0f3)", borderRadius: 5, height: 16, overflow: "hidden" }}>
                  <div style={{ width: `${(v / maxStatus) * 100}%`, height: "100%", background: meta.color, borderRadius: 5, transition: "width .3s" }} />
                </div>
                <div style={{ width: 28, textAlign: "right", fontSize: 12, fontWeight: 700 }}>{v}</div>
              </div>
            );
          })}
          {Object.keys(s.by_kind).length > 0 && (
            <div style={{ fontSize: 11, color: "var(--ink-400,#999)", marginTop: 6 }}>
              종류: {Object.entries(s.by_kind).map(([k, v]) => `${k} ${v}`).join(" · ")}
            </div>
          )}
        </div>

        {/* 14일 추세(막대 그래프) — 청크 수 / 파일 수 토글 */}
        <div style={{ flex: "1 1 320px", minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-700,#444)", flex: "1 1 auto", minWidth: 0, wordBreak: "keep-all" }}>
              최근 14일 일별 추세 <span style={{ color: "var(--ink-400,#999)", fontWeight: 400, whiteSpace: "nowrap" }}>· 합계 {trendTotal.toLocaleString()}{trendUnit}</span>
            </span>
            <div style={{ display: "inline-flex", flexShrink: 0, border: "1px solid var(--line,#e5e7eb)", borderRadius: 8, overflow: "hidden" }}>
              {([["chunks", "청크 수"], ["files", "파일 수"]] as const).map(([m, lbl]) => (
                <button
                  key={m}
                  onClick={() => setTrendMetric(m)}
                  style={{
                    border: "none", padding: "4px 10px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
                    background: trendMetric === m ? "var(--brand-grad,#0277b6)" : "transparent",
                    color: trendMetric === m ? "#fff" : "var(--ink-500,#888)",
                  }}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>
          <svg viewBox="0 0 320 110" width="100%" height="110" style={{ overflow: "visible" }}>
            {s.trend.map((t, i) => {
              const v = trendVal(t);
              const bw = 320 / s.trend.length;
              const h = (v / maxTrend) * 78;
              const x = i * bw;
              return (
                <g key={t.date}>
                  <rect x={x + 2} y={88 - h} width={bw - 4} height={Math.max(h, v > 0 ? 2 : 0)} rx={2} fill="#0277b6" opacity={v > 0 ? 0.85 : 0.15}>
                    <title>{`${t.date}: 파일 ${t.indexed}건 · 청크 ${(t.chunks ?? 0).toLocaleString()}`}</title>
                  </rect>
                  {v > 0 && (
                    <text x={x + bw / 2} y={86 - h} textAnchor="middle" fontSize="9" fill="#0277b6" fontWeight="700">{v.toLocaleString()}</text>
                  )}
                  {(i === 0 || i === s.trend.length - 1) && (
                    <text x={x + bw / 2} y={104} textAnchor="middle" fontSize="8" fill="#999">{t.date.slice(5)}</text>
                  )}
                </g>
              );
            })}
            <line x1="0" y1="88" x2="320" y2="88" stroke="var(--line,#e5e7eb)" strokeWidth="1" />
          </svg>
        </div>
      </div>

      {/* 월별 코퍼스 청크 증가량 */}
      <div style={{ marginTop: 18 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, color: "var(--ink-700,#444)" }}>
          월별 코퍼스 청크 (증가량)
        </div>
        {!s.monthly_chunks || s.monthly_chunks.length === 0 ? (
          <div style={{ fontSize: 12, color: "var(--ink-400,#999)" }}>
            아직 기록된 월별 스냅샷이 없습니다 — 색인이 진행되면 매월 누적됩니다.
          </div>
        ) : (
          <MonthlyChunkChart data={s.monthly_chunks} />
        )}
      </div>
    </div>
  );
}

function MonthlyChunkChart({ data }: { data: UploadStats["monthly_chunks"] }) {
  const max = Math.max(1, ...data.map((d) => d.chunks));
  return (
    <div>
      {data.map((d) => (
        <div key={d.month} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <div style={{ width: 64, fontSize: 12, color: "var(--ink-600,#666)" }}>{d.month}</div>
          <div style={{ flex: 1, background: "var(--line,#eef0f3)", borderRadius: 5, height: 18, overflow: "hidden" }}>
            <div style={{ width: `${(d.chunks / max) * 100}%`, height: "100%", background: "#0277b6", borderRadius: 5, transition: "width .3s" }} />
          </div>
          <div style={{ width: 70, textAlign: "right", fontSize: 12, fontWeight: 700 }}>{d.chunks.toLocaleString()}</div>
          <div style={{ width: 70, textAlign: "right", fontSize: 11, color: d.delta && d.delta > 0 ? "#16a34a" : "var(--ink-400,#999)" }}>
            {d.delta == null ? "기준" : d.delta > 0 ? `+${d.delta.toLocaleString()}` : d.delta.toLocaleString()}
          </div>
        </div>
      ))}
      <div style={{ fontSize: 11, color: "var(--ink-400,#999)", marginTop: 4 }}>
        월말 코퍼스 청크 수와 전월 대비 증가량. 색인이 진행될수록 매월 누적됩니다.
      </div>
    </div>
  );
}

// ── 학습 배치 실시간 진행상황 카드 ──────────────────────────────
function LearningProgressCard({ p, running }: { p: LearningProgress | null; running: boolean }) {
  const isErr = p?.stage === "error";
  const isDone = !!p?.done && !running;
  // 현재 단계 내 진척(파일 N/M)
  const stagePct = p?.total ? Math.min(100, Math.round(((p.current ?? 0) / p.total) * 100)) : null;
  // 전 단계 가중 전체 진행율(단계가 바뀌어도 끊김 없이 0~100%)
  const overall = p?.overall_pct ?? (isDone ? 100 : null);
  const accent = isErr ? "#dc2626" : isDone ? "#16a34a" : "#0277b6";
  let elapsed: number | null = null;
  if (p?.started_at) {
    const t = (isDone ? new Date(p.updated_at || p.started_at) : new Date()).getTime() - new Date(p.started_at).getTime();
    elapsed = Math.max(0, Math.round(t / 1000));
  }
  const elapsedStr = elapsed == null ? "" : elapsed >= 60 ? `${Math.floor(elapsed / 60)}분 ${elapsed % 60}초` : `${elapsed}초`;
  const stageNo = p?.stage_index && p?.stage_count ? `${p.stage_index}/${p.stage_count} ` : "";
  const head = isErr ? "⚠ 학습 오류" : isDone ? "✓ 학습 완료" : `⏳ 학습 진행 중 — ${stageNo}${p?.stage_label || "준비"}`;
  return (
    <div style={{ marginTop: 12, padding: "12px 14px", border: `1px solid ${accent}33`, borderLeft: `3px solid ${accent}`, borderRadius: 8, background: "var(--surface, #f8fafc)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 700, color: accent }}>
        <span>{head}</span>
        {overall != null && !isErr && (
          <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>전체 {overall}%</span>
        )}
      </div>
      {/* 전체 진행바(전 단계 가중) — 단계가 바뀌어도 유지되어 '멈춘 듯' 착시 제거 */}
      {overall != null && !isErr && (
        <div style={{ marginTop: 8, height: 8, background: "var(--line, #e5e7eb)", borderRadius: 4, overflow: "hidden" }}>
          <div style={{ width: `${overall}%`, height: "100%", background: accent, borderRadius: 4, transition: "width .4s" }} />
        </div>
      )}
      {/* 현재 단계 내 진척(파일 N/M + 현재 처리 파일명) */}
      {stagePct != null && !isDone && !isErr && (
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-700, #444)", fontVariantNumeric: "tabular-nums" }}>
          {p?.stage_label} {p?.current}/{p?.total} ({stagePct}%)
          {p?.current_file && <span style={{ color: "var(--ink-500, #888)" }}> · {p.current_file}</span>}
        </div>
      )}
      <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-600, #666)" }}>
        {p?.message || "준비 중…"}
        {p?.chunks != null && p.chunks > 0 && ` · 누적 ${p.chunks.toLocaleString()}청크`}
        {elapsedStr && ` · 경과 ${elapsedStr}`}
      </div>
    </div>
  );
}
