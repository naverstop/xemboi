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
import { api, refreshMe, type VideoJobResp } from "../api";
import DownloadGuard from "./DownloadGuard";

const LS_KEY = "saju_video_job";  // 영상 진행/완료 토큰(복원용)

// ── 생성 작업(PDF/감정서/부적) 카드 ──
type GenKind = "pdf" | "report" | "amulet";
type GenStatus = "running" | "done" | "error";
type GenTask = {
  id: string;
  kind: GenKind;
  status: GenStatus;
  startedAt: number;   // 경과초 계산 기준(ms)
  elapsed: number;     // 경과초
  url?: string;             // 인라인 보기용(Content-Disposition: inline)
  downloadUrl?: string;     // 파일 저장용(Content-Disposition: attachment)
  filename?: string;
  message?: string;
  closeIn?: number | null;   // 자동 닫힘 남은 초(null=대기 없음)
};

// [운영자 지시 2026-07-23] 열람·저장이 끝난 카드가 계속 떠 있어 화면을 가린다.
// → '완료 즉시'가 아니라 **사용자가 실제로 열거나 저장한 뒤**에만 카운트다운을 시작한다.
//   (완료 즉시 닫으면 아직 안 받은 사람의 파일 접근 경로가 사라진다.)
//   카운트다운 중 카드를 건드리면(hover/클릭) 즉시 취소 — 다시 받으려는 사람을 쫓아내지 않는다.
const AUTO_CLOSE_SEC = 5;

const GEN_LABEL: Record<GenKind, { titleKey: string; openKey: string }> = {
  pdf: { titleKey: "misc.gen_pdf_title", openKey: "misc.gen_pdf_open" },
  report: { titleKey: "misc.gen_report_title", openKey: "misc.gen_report_open" },
  amulet: { titleKey: "misc.gen_amulet_title", openKey: "misc.gen_amulet_open" },
};

export default function ProgressDock() {
  const { t: tr } = useTranslation();
  // ── 영상 레인 ──
  const [job, setJob] = useState<VideoJobResp | null>(null);
  const [hidden, setHidden] = useState(false);
  const [crossSell, setCrossSell] = useState(false);
  // 저장 로직 재설계(운영자 보고: "완료라는데 다운로드 안 됨, 두 번째에야 됨"):
  //   완성 시 blob 을 '미리' 받아 두고(preparing/dlPct), 클릭 핸들러는 동기 a.click 만 수행.
  //   기존엔 클릭 안에서 await fetch(14MB) 후 click → 모바일 사용자 제스처 만료로 저장이
  //   조용히 무시되는데 성공(✅완료)으로 표시됐다. 동기 저장이면 활성화 창을 벗어날 수 없다.
  const [blobUrl, setBlobUrl] = useState<string | null>(null); // 준비된 저장용 object URL
  const [preparing, setPreparing] = useState(false);
  const [prepErr, setPrepErr] = useState<string | null>(null);
  const [downloaded, setDownloaded] = useState(false);    // 저장 실행됨 표시(재클릭 즉시 재저장 허용)
  const [dlPct, setDlPct] = useState(0);                  // 수신 진척률(0~100)
  const saveLock = useRef(0);                             // 동기 연타 방지(더블클릭 이중 저장)
  const timer = useRef<number | null>(null);
  const [videoCloseIn, setVideoCloseIn] = useState<number | null>(null);  // 저장 후 자동 닫힘 카운트다운

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
            if (j.status === "failed") refreshMe();   // 실패 → 서버 자동환불 → 잔액 즉시 반영(패턴 B)
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
      setDownloaded(false);   // 새 영상 작업 — 이전 완료 상태 초기화
      setBlobUrl((old) => { if (old) URL.revokeObjectURL(old); return null; });
      setPrepErr(null);
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
        cur.map((t) => (t.id === d.id
          ? { ...t, status: "done", url: d.url, downloadUrl: d.download_url, filename: d.filename }
          : t))
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

  // 1초 타이머 — ①진행중 경과초 갱신 ②열람 후 자동 닫힘 카운트다운. 둘 중 하나라도 있으면 가동.
  useEffect(() => {
    if (!tasks.some((t) => t.status === "running" || typeof t.closeIn === "number")) return;
    const iv = window.setInterval(() => {
      setTasks((cur) =>
        cur.flatMap((t) => {
          if (typeof t.closeIn === "number") {
            const n = t.closeIn - 1;
            return n <= 0 ? [] : [{ ...t, closeIn: n }];   // 0 도달 = 카드 제거(자동 닫힘)
          }
          return t.status === "running"
            ? [{ ...t, elapsed: Math.max(0, Math.floor((Date.now() - t.startedAt) / 1000)) }]
            : [t];
        })
      );
    }, 1000);
    return () => window.clearInterval(iv);
  }, [tasks]);

  // 영상 카드 자동 닫힘 — 저장을 마친 뒤에만 진입(아래 저장 버튼에서 setVideoCloseIn).
  useEffect(() => {
    if (videoCloseIn === null) return;
    if (videoCloseIn <= 0) {
      setVideoCloseIn(null);
      setHidden(true);
      setBlobUrl((u) => { if (u) URL.revokeObjectURL(u); return null; });
      localStorage.removeItem(LS_KEY);   // 수동 ✕ 와 동일 처리(저장을 끝낸 카드만 여기 도달)
      return;
    }
    const t = window.setTimeout(() => setVideoCloseIn((n) => (n === null ? null : n - 1)), 1000);
    return () => window.clearTimeout(t);
  }, [videoCloseIn]);

  // 완성 즉시 blob 사전 준비 — 클릭 시점엔 동기 저장만 남긴다(모바일 제스처 만료 방지)
  const jobToken = job?.status === "done" ? job.job_token : null;
  useEffect(() => {
    // hidden 체크 필수 — 카드를 닫으면 blobUrl 을 revoke(=null) 하는데, 그때 이 effect 가 다시 돌면
    // 보이지도 않는 영상 14MB 를 배경에서 재수신한다(닫기·자동닫힘 공통). 닫힌 뒤엔 준비하지 않는다.
    if (hidden || !jobToken || blobUrl || preparing || prepErr) return;  // prepErr=수동 재시도 대기(자동 루프 금지)
    let alive = true;
    setPreparing(true); setPrepErr(null); setDlPct(0);
    api.prepareVideoBlob(jobToken, setDlPct)
      .then((u) => { if (alive) setBlobUrl(u); else URL.revokeObjectURL(u); })
      .catch((e: any) => {
        if (!alive) return;
        if (e?.status === 410 || e?.status === 404) {
          alert("보관 기간이 지나 영상이 삭제되었어요.");
          localStorage.removeItem(LS_KEY);
          setHidden(true);
        } else {
          setPrepErr(e?.message || "영상 파일을 불러오지 못했어요.");
        }
      })
      .finally(() => { if (alive) setPreparing(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobToken, blobUrl, prepErr, hidden]);

  const videoVisible = !!job && !hidden;
  if (!videoVisible && tasks.length === 0) return null;

  const pct = job?.progress_pct ?? 0;
  const done = job?.status === "done";
  const failed = job?.status === "failed" || job?.status === "expired";

  function close() {
    setHidden(true);
    if (blobUrl) { URL.revokeObjectURL(blobUrl); setBlobUrl(null); }
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
              {preparing && (
                // 파일 사전 수신 진행 표시 — 14MB 전송에 수 초. 준비가 끝나야 저장 버튼이 열린다.
                <>
                  <div className="vd-bar"><div className="vd-bar-fill" style={{ width: `${dlPct}%` }} /></div>
                  <div className="vd-detail">{tr("misc.vid_prep_progress", { pct: dlPct })}</div>
                </>
              )}
              {prepErr && (
                <div className="vd-fail">
                  {prepErr}{" "}
                  <button className="vd-download" onClick={() => setPrepErr(null)}>{tr("misc.vid_retry")}</button>
                </div>
              )}
              {!prepErr && (
                // 재생(새 탭 열람)과 다운로드(저장)를 나란히 — 사용자가 선택(운영자 지시)
                <div className="vd-actions">
                  <button
                    className="vd-download vd-download-alt"
                    disabled={!blobUrl}
                    onClick={() => {
                      // blob 은 이미 준비됨 → 동기 window.open(팝업 차단 없음). 새 탭에서 재생.
                      if (!blobUrl) return;
                      window.open(blobUrl, "_blank", "noopener");
                    }}
                  >
                    {tr("misc.vid_play")}
                  </button>
                  <button
                    className="vd-download"
                    disabled={!blobUrl}
                    onClick={() => {
                      // ⚠️ 이 핸들러는 반드시 '동기'로 유지 — await 가 끼면 모바일 사용자 제스처가
                      // 만료돼 저장이 조용히 무시된다(운영자 보고 버그의 원인).
                      if (!blobUrl) return;
                      const now = Date.now();
                      if (now - saveLock.current < 800) return;  // 더블클릭 이중 저장 방지
                      saveLock.current = now;
                      api.saveBlobUrl(blobUrl, `${job.title || tr("misc.vid_filename")}.mp4`);
                      setDownloaded(true);
                      setVideoCloseIn(AUTO_CLOSE_SEC);   // 저장했으니 카운트다운 시작(재클릭 시 재장전)
                    }}
                  >
                    {!blobUrl ? tr("misc.vid_btn_prep", { pct: dlPct }) : downloaded ? tr("misc.vid_saved_again") : tr("misc.vid_save")}
                  </button>
                </div>
              )}
              {videoCloseIn !== null && (
                <button className="vd-autoclose" onClick={() => setVideoCloseIn(null)}>
                  {tr("misc.autoclose", { sec: videoCloseIn })}
                </button>
              )}
              <div className="vd-note">
                {tr("misc.vid_note_retention")}
                {downloaded && ` · ${tr("misc.vid_note_resave")}`}
              </div>
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
              {t.url && (
                // 열기(새 탭 보기)와 저장(파일 다운로드)을 나란히 — 사용자가 선택(운영자 지시)
                <div className="vd-actions">
                  <DownloadGuard
                    key={`${t.id}-open`} className="vd-download" href={t.url} mode="open"
                    onFire={() => setTasks((cur) => cur.map((x) =>
                      x.id === t.id ? { ...x, closeIn: AUTO_CLOSE_SEC } : x))}
                  >
                    📄 {tr("misc.gen_open", { what: tr(GEN_LABEL[t.kind].openKey) })}
                  </DownloadGuard>
                  <DownloadGuard
                    key={`${t.id}-save`} className="vd-download vd-download-alt"
                    href={t.downloadUrl || `${t.url}${t.url.includes("?") ? "&" : "?"}download=1`}
                    filename={t.filename} mode="download"
                    onFire={() => setTasks((cur) => cur.map((x) =>
                      x.id === t.id ? { ...x, closeIn: AUTO_CLOSE_SEC } : x))}
                  >
                    ⤓ {tr("misc.save_short")}
                  </DownloadGuard>
                </div>
              )}
              {typeof t.closeIn === "number" ? (
                <button className="vd-autoclose"
                        onClick={() => setTasks((cur) => cur.map((x) =>
                          x.id === t.id ? { ...x, closeIn: null } : x))}>
                  {tr("misc.autoclose", { sec: t.closeIn })}
                </button>
              ) : (
                <div className="vd-note">{tr("misc.gen_done_note")}</div>
              )}
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
