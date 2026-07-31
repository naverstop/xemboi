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
import { api, setCachedMe, getCachedMe } from "../api";
import { useCharge } from "./ChargeModal";

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

const FB_REASONS = [
  "근거가 부족해요",
  "질문과 다른 답변이에요",
  "내용이 어려워요",
  "너무 짧거나 길어요",
  "표현이 어색해요",
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
      alert("복사에 실패했어요. 본문을 길게 눌러 직접 복사해 주세요.");
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
        detail: { id, message: "PDF 생성 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요." },
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
      const msg = String(e?.message || e);
      if (msg.includes("공유 횟수")) {
        alert(msg);
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
      alert("공유용 PDF 준비 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
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
    const costP = (getCachedMe()?.video_gen_cost ?? 10000).toLocaleString();
    const ok = window.confirm(
      "내 사주 이야기를 1분 영상으로 만들어 드릴까요?\n\n" +
      `· ${costP}P가 차감됩니다(생성 실패 시 자동 환불)\n` +
      "· 완성되면 하단에서 다운로드할 수 있어요\n" +
      "· 영상은 48시간 동안만 보관됩니다",
    );
    if (!ok) return;
    setVidBusy(true);
    try {
      const job = await api.createVideoJob(messageId, sessionId);
      window.dispatchEvent(new CustomEvent("saju:video-start", { detail: { token: job.job_token } }));
    } catch (e: any) {
      if (e?.status === 402) {
        openCharge(`영상 생성에는 ${costP}P가 필요해요. 충전하면 바로 만들어 드려요.`);
      } else if (e?.status === 401) {
        alert("로그인이 필요해요. 먼저 로그인해 주세요.");
      } else {
        alert(e?.message || "영상 생성을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.");
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
              {isLast && "이 풀이가 도움이 되었나요? "}
              <em className="aa-fb-reward">🎁 평점(👍/👎) 주시면 포인트 적립</em>
            </span>
          )}
          <button
            className={`aa-fb-btn${rating === 1 ? " on" : ""}`}
            onClick={() => onFeedback(1)}
            disabled={fbBusy}
            title="추천 — 도움이 됐어요"
            aria-label="추천"
          >
            👍
          </button>
          <button
            className={`aa-fb-btn${rating === -1 ? " on" : ""}`}
            onClick={() => onFeedback(-1)}
            disabled={fbBusy}
            title="반대 — 아쉬워요"
            aria-label="반대"
          >
            👎
          </button>
          {fbThanks && (
            <span className="fb-thanks">
              소중한 의견 감사합니다 🙏{fbReward > 0 && <b className="fb-reward-toast"> · 🎁 {fbReward.toLocaleString()}P 적립!</b>}
            </span>
          )}
          {fbPopup && (
            <div className="fb-popup" role="dialog" aria-label="답변 평가">
              <div className="fb-popup-title">어떤 점이 아쉬웠나요?</div>
              <div className="fb-popup-chips">
                {FB_REASONS.map((rsn) => (
                  <button
                    key={rsn}
                    className={`fb-chip${fbReasons.includes(rsn) ? " on" : ""}`}
                    onClick={() =>
                      setFbReasons((cur) =>
                        cur.includes(rsn) ? cur.filter((x) => x !== rsn) : [...cur, rsn]
                      )
                    }
                  >
                    {rsn}
                  </button>
                ))}
              </div>
              <textarea
                className="fb-popup-text"
                placeholder="자세히 알려주시면 풀이 개선에 큰 도움이 됩니다 (선택)"
                value={fbComment}
                onChange={(e) => setFbComment(e.target.value)}
                rows={2}
                maxLength={500}
              />
              <div className="fb-popup-actions">
                <button className="fb-popup-skip" onClick={() => setFbPopup(false)}>건너뛰기</button>
                <button
                  className="fb-popup-submit"
                  onClick={submitFbDetail}
                  disabled={fbReasons.length === 0 && !fbComment.trim()}
                >
                  의견 보내기
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="aa-right">
        <button className="copy-btn" onClick={onCopy} title="텍스트 복사">
          {copied ? "✓ 복사됨" : "⧉ 텍스트 복사"}
        </button>
        <span className="share-wrap">
          <button className="copy-btn" onClick={onShare} disabled={busy} title="상담서 PDF를 저장해 카카오톡·메시지 등에 첨부해 전달하세요">
            {shared ? "✓ 저장됨 — 첨부해 전달" : "↗ 공유"}
          </button>
          {shared && (
            <span className="share-hint" role="status">
              상담서 PDF가 저장되었어요. 카카오톡·메시지 등에 첨부해 전달하세요.
            </span>
          )}
        </span>
        {pdfUrl ? (
          // 생성 완료: 실제 링크로 전환 → 새 탭 열람/저장(사용자 제스처라 팝업차단 없음, API 재호출 없음)
          <a className="copy-btn" href={pdfUrl} target="_blank" rel="noopener noreferrer" title="생성된 상담서 PDF 열기·저장">
            ⤓ PDF 열기
          </a>
        ) : (
          <button className="copy-btn" onClick={onPdf} disabled={busy} title="상담서 PDF">
            {busy ? "⏳ 생성 중…" : "⤓ PDF"}
          </button>
        )}
        {source === "chat" && messageId && (
          <button className="copy-btn aa-video" onClick={onMakeVideo} disabled={vidBusy} title="내 사주를 1분 영상으로">
            {vidBusy ? "⏳ 시작 중…" : "🎬 영상으로 보기"}
          </button>
        )}
      </div>
    </div>
  );
}
