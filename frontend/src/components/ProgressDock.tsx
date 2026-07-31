/** 작업 진행 dock — 화면 하단 공통(전역). 여러 작업을 카드로 쌓아 보여준다.
 *
 *  ① 영상 레인 — 'saju:video-start'(detail.token) 수신 → 폴링/localStorage 복원, 실제 % 진행바,
 *     완료 시 다운로드(전송 % 표시). 48h 보관 고지.
 *  ② 생성 레인(PDF·감정서) — 'saju:gen-start / saju:gen-done / saju:gen-error' 수신.
 *     백엔드 생성이라 실제 %가 없어 인디터미네이트 바 + 경과초로 "진행 중"을 확실히 알린다
 *     (사용자가 멈춘 줄 알고 다시 눌러 중복 생성·재다운로드 팝업이 뜨는 걸 막는 게 목적).
 *     완료 시 '열기' 버튼(탭=사용자 제스처 → 모바일 팝업 차단 없이 열람, 재생성 없음).
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, type VideoJobResp } from "../api";

const LS_KEY = "saju_video_job";  // 영상 진행/완료 토큰(복원용)

// ── 생성 작업(PDF/감정서) 카드 ──
type GenKind = "pdf" | "report";
type GenStatus = "running" | "done" | "error";
type GenTask = {
  id: string;
  kind: GenKind;
  status: GenStatus;
  startedAt: number;   // 경과초 계산 기준(ms)
  elapsed: number;     // 경과초
  url?: string;
  filename?: string;
  message?: string;
};

const GEN_LABEL: Record<GenKind, { titleKey: string; openKey: string }> = {
  pdf: { titleKey: "misc.gen_pdf_title", openKey: "misc.gen_pdf_open" },
  report: { titleKey: "misc.gen_report_title", openKey: "misc.gen_report_open" },
};

export default function ProgressDock() {
  const { t: tr } = useTranslation();
  // ── 영상 레인 ──
  const [job, setJob] = useState<VideoJobResp | null>(null);
  const [hidden, setHidden] = useState(false);
  const [crossSell, setCrossSell] = useState(false);
  const [downloading, setDownloading] = useState(false);  // 다운로드 진행 중 — 연타/중복 다운 방지
  const [dlPct, setDlPct] = useState(0);                  // 다운로드 수신 진척률(0~100)
  const timer = useRef<number | null>(null);

  // ── 생성 레인(PDF/감정서) ──
  const [tasks, setTasks] = useState<GenTask[]>([]);

  useEffect(() => {
    function clearTimer() {
      if (timer.current) {
        window.clearTimeout(timer.current);
        timer.current = null;
      }
    }
    function poll(token: string) {
      api.getVideoJob(token)
        .then((j) => {
          setJob(j);
          if (j.status === "queued" || j.status === "running") {
            timer.current = window.setTimeout(() => poll(token), 2000);
          } else if (j.status === "done") {
            localStorage.setItem(LS_KEY, token);  // 다운로드 위해 유지
          } else {
            localStorage.removeItem(LS_KEY);       // failed/expired → 정리
          }
        })
        .catch((e: any) => {
          if (e?.status === 404 || e?.status === 410 || e?.status === 401) {
            localStorage.removeItem(LS_KEY);       // 없음/만료/미인증 → 정리·중단(로그아웃 시 무한재시도 방지)
            setJob(null);
          } else {
            timer.current = window.setTimeout(() => poll(token), 4000);  // 일시 오류 → 재시도
          }
        });
    }
    function onStart(e: any) {
      const token = e?.detail?.token;
      if (!token) return;
      clearTimer();
      localStorage.setItem(LS_KEY, token);
      setHidden(false);
      setCrossSell(true);
      poll(token);
    }
    window.addEventListener("saju:video-start", onStart as EventListener);
    const saved = localStorage.getItem(LS_KEY);
    if (saved) poll(saved);  // 부트 복원
    return () => {
      window.removeEventListener("saju:video-start", onStart as EventListener);
      clearTimer();
    };
  }, []);

  // 생성 레인 이벤트 수신
  useEffect(() => {
    function onGenStart(e: any) {
      const d = e?.detail || {};
      if (!d.id || !d.kind || !(d.kind in GEN_LABEL)) return;
      setTasks((cur) => [
        ...cur.filter((t) => t.id !== d.id),
        { id: d.id, kind: d.kind, status: "running", startedAt: Date.now(), elapsed: 0 },
      ]);
    }
    function onGenDone(e: any) {
      const d = e?.detail || {};
      setTasks((cur) =>
        cur.map((t) => (t.id === d.id ? { ...t, status: "done", url: d.url, filename: d.filename } : t))
      );
    }
    function onGenError(e: any) {
      const d = e?.detail || {};
      setTasks((cur) =>
        cur.map((t) => (t.id === d.id ? { ...t, status: "error", message: d.message } : t))
      );
    }
    window.addEventListener("saju:gen-start", onGenStart as EventListener);
    window.addEventListener("saju:gen-done", onGenDone as EventListener);
    window.addEventListener("saju:gen-error", onGenError as EventListener);
    return () => {
      window.removeEventListener("saju:gen-start", onGenStart as EventListener);
      window.removeEventListener("saju:gen-done", onGenDone as EventListener);
      window.removeEventListener("saju:gen-error", onGenError as EventListener);
    };
  }, []);

  // 경과초 갱신 — 진행 중 작업이 있을 때만 1초 타이머
  useEffect(() => {
    if (!tasks.some((t) => t.status === "running")) return;
    const iv = window.setInterval(() => {
      setTasks((cur) =>
        cur.map((t) =>
          t.status === "running"
            ? { ...t, elapsed: Math.max(0, Math.floor((Date.now() - t.startedAt) / 1000)) }
            : t
        )
      );
    }, 1000);
    return () => window.clearInterval(iv);
  }, [tasks]);

  const videoVisible = !!job && !hidden;
  if (!videoVisible && tasks.length === 0) return null;

  const pct = job?.progress_pct ?? 0;
  const done = job?.status === "done";
  const failed = job?.status === "failed" || job?.status === "expired";

  function close() {
    setHidden(true);
    if (done || failed) localStorage.removeItem(LS_KEY);
  }
  function dismissTask(id: string) {
    setTasks((cur) => cur.filter((t) => t.id !== id));
  }

  return (
    <div className="progress-dock-wrap">
      {/* 영상 카드 */}
      {videoVisible && job && (
        <div className="video-dock" role="status" aria-live="polite">
          <button className="vd-close" onClick={close} aria-label={tr("pay.close")}>✕</button>
          <div className="vd-title">{tr("misc.vid_title")}</div>

          {!done && !failed && (
            <>
              <div className="vd-bar"><div className="vd-bar-fill" style={{ width: `${pct}%` }} /></div>
              <div className="vd-detail">{job.detail || tr("misc.vid_preparing")} · {pct}%</div>
              {crossSell && (
                <div className="vd-crosssell">
                  <span>{tr("misc.vid_crosssell")}</span>
                  <span className="vd-cs-links">
                    <Link to="/naming/jakmyeong" onClick={() => setCrossSell(false)}>{tr("nav.jakmyeong")}</Link>
                    <Link to="/compatibility" onClick={() => setCrossSell(false)}>{tr("nav.compat")}</Link>
                  </span>
                </div>
              )}
            </>
          )}

          {done && (
            <>
              <div className="vd-done">{tr("misc.vid_done")}</div>
              {downloading && (
                // 다운로드 진행 표시 — 14MB 전송에 수 초 걸림. 진척바를 보여줘야
                // 사용자가 "멈춘 줄 알고" 다시 눌러 브라우저 재다운로드 팝업이 뜨는 걸 막는다.
                <>
                  <div className="vd-bar"><div className="vd-bar-fill" style={{ width: `${dlPct}%` }} /></div>
                  <div className="vd-detail">{tr("misc.vid_dl_progress", { pct: dlPct })}</div>
                </>
              )}
              <button
                className="vd-download"
                disabled={downloading}
                onClick={async () => {
                  if (downloading) return;   // 연타 방지: 다운로드 중엔 재요청 차단(30개씩 받히던 문제)
                  setDownloading(true);
                  setDlPct(0);
                  try {
                    await api.downloadVideo(job.job_token, `${job.title || tr("misc.vid_filename")}.mp4`, setDlPct);
                  } catch (e: any) {
                    if (e?.status === 410 || e?.status === 404) {
                      alert(tr("misc.vid_expired"));
                      localStorage.removeItem(LS_KEY);
                      setHidden(true);
                    } else {
                      alert(e?.message || tr("misc.vid_dl_fail"));
                    }
                  } finally {
                    setDownloading(false);
                  }
                }}
              >
                {downloading ? tr("misc.vid_dl_btn_busy", { pct: dlPct }) : tr("misc.vid_dl_btn")}
              </button>
              <div className="vd-note">{tr("misc.vid_note_48h")}</div>
            </>
          )}

          {failed && (
            <div className="vd-fail">{job.detail || tr("misc.vid_gen_fail")}</div>
          )}
        </div>
      )}

      {/* 생성 작업 카드(PDF·감정서) */}
      {tasks.map((t) => (
        <div className="video-dock" role="status" aria-live="polite" key={t.id}>
          <button className="vd-close" onClick={() => dismissTask(t.id)} aria-label={tr("pay.close")}>✕</button>
          <div className="vd-title">{tr(GEN_LABEL[t.kind].titleKey)}</div>

          {t.status === "running" && (
            <>
              <div className="vd-bar vd-bar-indet"><span /></div>
              <div className="vd-detail">{tr("misc.gen_running", { sec: t.elapsed })}</div>
            </>
          )}

          {t.status === "done" && (
            <>
              <button className="vd-download" onClick={() => t.url && window.open(t.url, "_blank")}>
                {tr("misc.gen_open", { what: tr(GEN_LABEL[t.kind].openKey) })}
              </button>
              <div className="vd-note">{tr("misc.gen_done_note")}</div>
            </>
          )}

          {t.status === "error" && (
            <div className="vd-fail">{t.message || tr("misc.gen_fail")}</div>
          )}
        </div>
      ))}
    </div>
  );
}
