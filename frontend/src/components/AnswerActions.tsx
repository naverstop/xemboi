/** 답변 액션 바 — 6개 메뉴(사주·궁합·택일·작명/개명/아호) 공통.
 *
 *  [좌] 👍 추천 / 👎 반대 (2단계 확대) + "이 풀이가 도움이 되었나요?"
 *  [우] 텍스트 복사 · 공유 · PDF
 *
 *  - 복사: navigator.clipboard + execCommand 폴백(비보안 컨텍스트/구형 대비)
 *  - PDF : 백엔드 상장양식(관인 날인) 생성 → 새 탭 열람·저장
 *  - 공유: ① PDF 파일 자체를 Web Share(files)로 SNS 전달 → ② URL 네이티브 공유
 *          → ③ 데스크톱 드롭다운(카카오/메일/링크) 순으로 폴백.
 *          백엔드가 만든 토큰 PDF URL 을 그대로 전달한다.
 */
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, setCachedMe, getCachedMe } from "../api";
import { useCharge } from "./ChargeModal";
import { fmtNum } from "../lib/money";

export type PdfMeta = {
  docTitle: string;     // 메뉴별 제목 (예: "홍길동 님의 사주")
  personLine?: string;  // 대상자 표기 (예: "홍 길 동 님")
  item?: string;        // 상담 항목
  when?: string;        // YYYY-MM-DD (없으면 오늘)
};

type Props = {
  text: string;              // 복사/공유/PDF 본문(plain text)
  pdf: PdfMeta;
  messageId?: number;        // 있으면 피드백(👍👎) 노출
  sessionId?: string;
  source?: "chat" | "tool" | "compat" | "tarot";  // 메시지 출처(메뉴) — id 충돌 방지 네임스페이스
  showFeedback?: boolean;    // 기본: messageId 있으면 노출
  initialFeedback?: 1 | -1;
  isLast?: boolean;          // 마지막 답변 → 평가 유도(nudge)
};

// 반대 사유 키(라벨은 answer.fb_reason_* 로 로케일 렌더; 선택 라벨이 백엔드 comment 로 전송).
const FB_REASON_KEYS = [
  "fb_reason_weak",
  "fb_reason_offtopic",
  "fb_reason_hard",
  "fb_reason_length",
  "fb_reason_awkward",
];

function fallbackCopy(s: string): boolean {
  try {
    const ta = document.createElement("textarea");
    ta.value = s;
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
async function copyText(s: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(s);
      return true;
    }
  } catch {
    /* 폴백으로 진행 */
  }
  return fallbackCopy(s);
}

export default function AnswerActions({
  text, pdf, messageId, sessionId, source = "chat", showFeedback, initialFeedback, isLast,
}: Props) {
  const { t: tr } = useTranslation();
  const [rating, setRating] = useState<1 | -1 | undefined>(initialFeedback);
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);  // 공유(다운로드) 완료 안내 토스트
  const [busy, setBusy] = useState(false);
  const [fbPopup, setFbPopup] = useState(false);
  const [fbReasons, setFbReasons] = useState<string[]>([]);
  const [fbComment, setFbComment] = useState("");
  const [fbThanks, setFbThanks] = useState(false);
  const [fbReward, setFbReward] = useState(0);  // 피드백 리워드 적립액(>0이면 토스트)
  const [fbBusy, setFbBusy] = useState(false);  // 피드백 제출 중 — 더블클릭/중복요청 방지
  const [vidBusy, setVidBusy] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");   // 생성 완료 시 세팅 → '⤓ PDF 열기' 링크 노출(재생성/팝업차단 없이 열람)
  const { openCharge } = useCharge();
  // 생성된 PDF 결과 캐시 — 공유/PDF 반복 클릭 시 재생성 방지
  const pdfCache = useRef<{ token: string; url: string; download_url: string; filename: string } | null>(null);

  const fbVisible = (showFeedback ?? !!messageId) && !!messageId;

  async function ensurePdf() {
    if (pdfCache.current) return pdfCache.current;
    const r = await api.generatePdf({
      doc_title: pdf.docTitle,
      person_line: pdf.personLine,
      item: pdf.item,
      content: text,
      when: pdf.when,
      // 사주 상담 세션이면 명식 패널(한지 위 본인 사주) 포함 — 소유권 검증은 백엔드
      session_id: source === "chat" ? sessionId : undefined,
    });
    pdfCache.current = r;
    setPdfUrl(r.url);   // 버튼 → 실제 링크(⤓ PDF 열기)로 전환: 팝업차단 없이 열람, 재클릭해도 재생성 안 함
    return r;
  }

  async function onCopy() {
    const ok = await copyText(text);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } else {
      alert(tr("answer.copy_fail"));
    }
  }

  async function onPdf() {
    if (busy) return;
    setBusy(true);
    // 진행/열람은 하단 공통 dock에서 처리 — 생성이 걸리는 동안 진행중 표시(연타·이탈 방지),
    // 완료 시 dock의 '열기' 버튼(탭=제스처라 모바일 팝업차단 없음). 여기선 트리거만.
    const id = `pdf-${Date.now()}`;
    window.dispatchEvent(new CustomEvent("saju:gen-start", { detail: { id, kind: "pdf" } }));
    try {
      const r = await ensurePdf();
      window.dispatchEvent(new CustomEvent("saju:gen-done", { detail: { id, url: r.url, filename: r.filename } }));
    } catch {
      window.dispatchEvent(new CustomEvent("saju:gen-error", {
        detail: { id, message: tr("answer.pdf_gen_error") },
      }));
    } finally {
      setBusy(false);
    }
  }

  // 공유 횟수 차감(백엔드). 한도 초과면 false → 공유 중단. 로그인 필요 등은 무시(익명 허용).
  async function recordShare(channel: "kakao" | "email" | "link"): Promise<boolean> {
    try {
      await api.submitShare({ channel, message_id: messageId, session_id: sessionId });
    } catch (e: any) {
      // 공유 한도 초과(403 share_quota_exceeded) → 로케일 메시지 안내 후 공유 중단.
      // 한국어 문자열 매칭 대신 서버 코드로 판별(vi 로케일에서도 정확히 동작).
      if (e?.code === "share_quota_exceeded") {
        alert(e?.message || String(e));
        return false;
      }
      /* 로그인 필요 등 → 무시하고 공유 진행 */
    }
    return true;
  }

  // 공유 = PDF 파일을 사용자 기기에 다운로드 → 사용자가 직접 카카오톡·메시지 등에 첨부해 전달.
  //  (링크 공유는 서버 열람 트래픽 부담이 커 채택하지 않음 — 운영 결정 2026-07-04)
  //  · 모바일 등 파일 공유 지원 기기: 네이티브 공유 시트(파일 저장/메신저 선택)로 매끄럽게 전달
  //  · 그 외(데스크톱 다수): 파일을 다운로드하고 "첨부해 전달하세요" 안내
  async function onShare() {
    if (busy) return;
    setBusy(true);
    try {
      const r = await ensurePdf();
      const navAny = navigator as any;
      // ① 파일 공유 지원 기기: 네이티브 시트(파일 저장/전달) — 수신자는 서버를 거치지 않음
      try {
        const resp = await fetch(r.url);
        const blob = await resp.blob();
        const file = new File([blob], r.filename, { type: "application/pdf" });
        if (navAny.canShare && navAny.canShare({ files: [file] }) && navAny.share) {
          await recordShare("link");
          await navAny.share({ title: pdf.docTitle, text: pdf.docTitle, files: [file] });
          return;
        }
      } catch {
        /* 파일 공유 미지원/취소 → 다운로드로 폴백 */
      }
      // ② 다운로드(첨부 강제) → 안내 토스트
      await recordShare("link");
      const a = document.createElement("a");
      a.href = window.location.origin + r.download_url;  // ?download=1 → Content-Disposition: attachment
      a.download = r.filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setShared(true);
      window.setTimeout(() => setShared(false), 4000);
    } catch {
      alert(tr("answer.share_fail"));
    } finally {
      setBusy(false);
    }
  }

  async function onFeedback(r: 1 | -1) {
    if (fbBusy) return;  // 제출 중 더블클릭 방지(👍👎 연타)
    setRating(r);
    if (messageId) {
      setFbBusy(true);
      try {
        const res = await api.submitFeedback({ message_id: messageId, session_id: sessionId, rating: r, source });
        if (res?.reward_granted && res.reward_granted > 0) {
          setFbReward(res.reward_granted);
          api.me().then(setCachedMe).catch(() => {});  // 플로팅 버튼 등 잔액 즉시 갱신
        }
      } catch {
        /* UI 유지 */
      } finally {
        setFbBusy(false);
      }
    }
    if (r === -1) {
      setFbReasons([]);
      setFbComment("");
      setFbPopup(true);
    } else {
      setFbThanks(true);
      window.setTimeout(() => setFbThanks(false), 2500);
    }
  }

  async function submitFbDetail() {
    setFbPopup(false);
    const comment = [...fbReasons, fbComment.trim()].filter(Boolean).join(" / ");
    if (!comment || !messageId) return;
    try {
      await api.submitFeedback({ message_id: messageId, session_id: sessionId, rating: -1, comment, source });
    } catch {
      /* 무시 */
    }
    setFbThanks(true);
    window.setTimeout(() => setFbThanks(false), 2500);
  }

  // 사주 답변 → 1분 쇼츠 영상(10,000P). 클릭 확인 → 즉시 차감·생성 시작 → 하단 진행팝업.
  async function onMakeVideo() {
    if (vidBusy || !messageId) return;
    // 차감 P는 관리자 설정값(me.video_gen_cost)을 따른다 — 하드코딩 금지(관리자 변경 즉시 반영).
    const costP = fmtNum(getCachedMe()?.video_gen_cost ?? 10000);
    const ok = window.confirm(tr("answer.video_confirm", { cost: costP }));
    if (!ok) return;
    setVidBusy(true);
    try {
      const job = await api.createVideoJob(messageId, sessionId);
      window.dispatchEvent(new CustomEvent("saju:video-start", { detail: { token: job.job_token } }));
    } catch (e: any) {
      if (e?.status === 402) {
        openCharge(tr("answer.video_need_charge", { cost: costP }));
      } else if (e?.status === 401) {
        alert(tr("err.login_required"));
      } else {
        alert(e?.message || tr("answer.video_fail"));
      }
    } finally {
      setVidBusy(false);
    }
  }

  return (
    <div className="answer-actions">
      {fbVisible && (
        <div className={`aa-fb${rating === undefined && isLast ? " nudge" : ""}`}>
          {rating === undefined && (
            <span className="aa-fb-label">
              {isLast && tr("answer.nudge_q")}
              <em className="aa-fb-reward">{tr("answer.nudge_reward")}</em>
            </span>
          )}
          <button
            className={`aa-fb-btn${rating === 1 ? " on" : ""}`}
            onClick={() => onFeedback(1)}
            disabled={fbBusy}
            title={tr("answer.fb_up_title")}
            aria-label={tr("answer.fb_up_aria")}
          >
            👍
          </button>
          <button
            className={`aa-fb-btn${rating === -1 ? " on" : ""}`}
            onClick={() => onFeedback(-1)}
            disabled={fbBusy}
            title={tr("answer.fb_down_title")}
            aria-label={tr("answer.fb_down_aria")}
          >
            👎
          </button>
          {fbThanks && (
            <span className="fb-thanks">
              {tr("answer.fb_thanks")}{fbReward > 0 && <b className="fb-reward-toast">{tr("answer.fb_reward_toast", { amount: fmtNum(fbReward) })}</b>}
            </span>
          )}
          {fbPopup && (
            <div className="fb-popup" role="dialog" aria-label={tr("answer.fb_dialog_aria")}>
              <div className="fb-popup-title">{tr("answer.fb_popup_title")}</div>
              <div className="fb-popup-chips">
                {FB_REASON_KEYS.map((k) => {
                  const rsn = tr(`answer.${k}`);
                  return (
                    <button
                      key={k}
                      className={`fb-chip${fbReasons.includes(rsn) ? " on" : ""}`}
                      onClick={() =>
                        setFbReasons((cur) =>
                          cur.includes(rsn) ? cur.filter((x) => x !== rsn) : [...cur, rsn]
                        )
                      }
                    >
                      {rsn}
                    </button>
                  );
                })}
              </div>
              <textarea
                className="fb-popup-text"
                placeholder={tr("answer.fb_popup_ph")}
                value={fbComment}
                onChange={(e) => setFbComment(e.target.value)}
                rows={2}
                maxLength={500}
              />
              <div className="fb-popup-actions">
                <button className="fb-popup-skip" onClick={() => setFbPopup(false)}>{tr("answer.fb_skip")}</button>
                <button
                  className="fb-popup-submit"
                  onClick={submitFbDetail}
                  disabled={fbReasons.length === 0 && !fbComment.trim()}
                >
                  {tr("answer.fb_submit")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="aa-right">
        <button className="copy-btn" onClick={onCopy} title={tr("answer.copy_title")}>
          {copied ? tr("answer.copy_done") : tr("answer.copy_btn")}
        </button>
        <span className="share-wrap">
          <button className="copy-btn" onClick={onShare} disabled={busy} title={tr("answer.share_title")}>
            {shared ? tr("answer.share_done") : tr("answer.share_btn")}
          </button>
          {shared && (
            <span className="share-hint" role="status">
              {tr("answer.share_hint")}
            </span>
          )}
        </span>
        {pdfUrl ? (
          // 생성 완료: 실제 링크로 전환 → 새 탭 열람/저장(사용자 제스처라 팝업차단 없음, API 재호출 없음)
          <a className="copy-btn" href={pdfUrl} target="_blank" rel="noopener noreferrer" title={tr("answer.pdf_open_title")}>
            {tr("answer.pdf_open")}
          </a>
        ) : (
          <button className="copy-btn" onClick={onPdf} disabled={busy} title={tr("answer.pdf_title")}>
            {busy ? tr("answer.pdf_busy") : tr("answer.pdf_btn")}
          </button>
        )}
        {source === "chat" && messageId && (
          <button className="copy-btn aa-video" onClick={onMakeVideo} disabled={vidBusy} title={tr("answer.video_title")}>
            {vidBusy ? tr("answer.video_busy") : tr("answer.video_btn")}
          </button>
        )}
      </div>
    </div>
  );
}
