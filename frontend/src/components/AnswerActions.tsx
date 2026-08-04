/** 답변 액션 바 — 6개 메뉴(사주·궁합·택일·작명/개명/아호) 공통.
 *
 *  [좌] 👍 추천 / 👎 반대 (2단계 확대) + "이 풀이가 도움이 되었나요?"
 *  [우] 텍스트 복사 · 공유 · PDF
 *
 *  - 복사: navigator.clipboard + execCommand 폴백(비보안 컨텍스트/구형 대비)
 *  - PDF : 백엔드 상장양식(관인 날인) 생성 → 새 탭 열람·저장
 *  - 공유: ① (모바일) Web Share(files)로 PDF 파일 자체를 카톡·메일 앱에 첨부 전송
 *          ② (데스크톱 등 파일공유 미지원) 공유 메뉴 — 카카오톡(링크카드)·메일(mailto)·링크복사·PDF저장.
 *          ⚠️ 웹 플랫폼 제약상 PC 브라우저는 카톡/메일에 '파일 첨부'가 불가 → 링크(토큰 URL)로만 전달된다.
 *          백엔드가 만든 공개 토큰 PDF URL(GET /api/pdf/{token})을 전달하고 수신자가 서버에서 열람한다.
 */
import { useRef, useState, type ReactNode } from "react";
import { api, setCachedMe, getCachedMe } from "../api";
import { useCharge } from "./ChargeModal";
import { kakaoAvailable, shareKakaoLink } from "../lib/kakaoShare";
import { canNativeFileShare } from "../lib/webShare";
import { inAppBrowser } from "../lib/inapp";
import DownloadGuard from "../components/DownloadGuard";
import ShareQuotaNote from "./ShareQuotaNote";

/** 라벨 폭 고정 스택 — 버튼의 모든 상태 라벨을 투명 고스트로 겹쳐 그려 폭을 최대 라벨에 예약.
 *  클릭 시 라벨이 바뀌어도('⤓ PDF'→'⏳ 생성 중…') 버튼 가로 사이즈가 출렁이지 않는다(운영자 보고).
 *  inline-grid 겹침이라 폰트/메뉴별 크기 차이에도 정확한 실측 폭으로 동작한다. */
function Stable({ widest, children }: { widest: ReactNode[]; children: ReactNode }) {
  return (
    <span className="aa-stable">
      {widest.map((w, i) => (
        <span key={i} className="aa-stable-ghost" aria-hidden>{w}</span>
      ))}
      <span className="aa-stable-cur">{children}</span>
    </span>
  );
}

// 슬롯별 상태 라벨 전집 — 고스트 예약 폭 산정용(여기 없는 라벨이 생기면 다시 출렁인다)
const COPY_LABELS = ["⧉ 텍스트 복사", "✓ 복사됨"];
const SHARE_LABELS = ["↗ 공유", "⏳ 준비 중…", "✓ 링크 복사됨"];
const PDF_LABELS = ["⤓ PDF", "⏳ 생성 중…", "📄 PDF 열기", "⏳ 여는 중…", "✅ 다시 열기"];
const VIDEO_LABELS = ["🎬 영상으로 보기", "⏳ 시작 중…"];
import { useTranslation } from "react-i18next";
import { fmtNum } from "../lib/money";

export type PdfMeta = {
  docTitle: string;     // 메뉴별 제목 (예: "홍길동 님의 사주")
  personLine?: string;  // 대상자 표기 (예: "홍 길 동 님")
  item?: string;        // 상담 항목
  when?: string;        // YYYY-MM-DD (없으면 오늘)
};

export type TarotPdfCard = { position_name: string; name_kr: string; name_en: string; orientation: string; image_url: string };

type Props = {
  text: string;              // 복사/공유 본문(plain text). PDF는 pdfContent 있으면 그걸 사용.
  pdfContent?: string;       // PDF 본문(타로: 카드 목록 텍스트 제외한 질문+해석). 없으면 text.
  tarotCards?: TarotPdfCard[]; // 타로 — 뽑은 카드(PDF에 이미지 그리드로 포함)
  pdf: PdfMeta;
  messageId?: number;        // 있으면 피드백(👍👎) 노출
  sessionId?: string;
  compatId?: string;         // 궁합 세션 id — PDF에 2인 명식+펜타곤 포함(source==='compat')
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
  text, pdfContent, tarotCards, pdf, messageId, sessionId, compatId, source = "chat", showFeedback, initialFeedback, isLast,
}: Props) {
  const { t: tr } = useTranslation();
  const [rating, setRating] = useState<1 | -1 | undefined>(initialFeedback);
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);  // 링크복사 등 완료 안내 토스트
  const [menuOpen, setMenuOpen] = useState(false);   // 데스크톱 공유 메뉴(카카오/메일/링크) 열림
  const [pdfShareUrl, setPdfShareUrl] = useState(""); // 공유용 절대 URL(origin+/api/pdf/{token})
  const [emailMode, setEmailMode] = useState(false); // 메일 보내기: 받는사람 입력 폼 표시
  const [emailTo, setEmailTo] = useState("");
  const [emailBusy, setEmailBusy] = useState(false);
  // busy 분리 — PDF 클릭이 공유 버튼 라벨까지 바꿔 우측 바 전체가 출렁이던 문제 방지(운영자 보고)
  const [pdfBusy, setPdfBusy] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  const shareLock = useRef(false);   // 공유 메뉴 항목 동기 연타 잠금(state 로는 같은 틱 연타를 못 막음)
  const [fbPopup, setFbPopup] = useState(false);
  const [fbReasons, setFbReasons] = useState<string[]>([]);
  const [fbComment, setFbComment] = useState("");
  const [fbThanks, setFbThanks] = useState(false);
  const [fbReward, setFbReward] = useState(0);  // 피드백 리워드 적립액(>0이면 토스트)
  const [fbBusy, setFbBusy] = useState(false);  // 피드백 제출 중 — 더블클릭/중복요청 방지
  // B-3 한 줄 후기(👍 직후 유도, 회원만)
  const [rvPopup, setRvPopup] = useState(false);
  const [rvText, setRvText] = useState("");
  const [rvStars, setRvStars] = useState(5);
  const [rvBusy, setRvBusy] = useState(false);
  const [rvDone, setRvDone] = useState("");
  const [vidBusy, setVidBusy] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");   // 생성 완료 시 세팅 → '⤓ PDF 열기' 링크 노출(재생성/팝업차단 없이 열람)
  const { openCharge } = useCharge();
  const inApp = inAppBrowser();   // 카톡/네이버/인스타 인앱 웹뷰 — Web Share(files) 막힘 → 저장 후 첨부 안내
  // 생성된 PDF 결과 캐시 — 공유/PDF 반복 클릭 시 재생성 방지
  const pdfCache = useRef<{ token: string; url: string; download_url: string; filename: string } | null>(null);
  // 진행 중 요청 공유 — busy 분리 후 공유·PDF 동시 클릭 시 같은 생성 요청을 재사용(이중 POST 방지)
  const pdfInflight = useRef<Promise<{ token: string; url: string; download_url: string; filename: string }> | null>(null);

  const fbVisible = (showFeedback ?? !!messageId) && !!messageId;

  async function ensurePdf() {
    if (pdfCache.current) return pdfCache.current;
    if (!pdfInflight.current) {
      pdfInflight.current = api.generatePdf({
        doc_title: pdf.docTitle,
        person_line: pdf.personLine,
        item: pdf.item,
        content: pdfContent ?? text,   // 타로: 카드 목록 텍스트 없이 질문+해석(카드는 이미지 그리드로)
        when: pdf.when,
        // 사주 상담(chat)·도구(tool: 신년운세·택일·작명 등) 세션이면 명식 패널(한지 위 본인 사주) 포함
        //   — 소유권 검증은 백엔드. tool은 tool_sessions에서 chart_json을 조회한다.
        session_id: (source === "chat" || source === "tool") ? sessionId : undefined,
        // 궁합이면 2인 명식+펜타곤 포함 — 소유권(IDOR)·비프리뷰 검증은 백엔드
        compat_id: source === "compat" ? compatId : undefined,
        // 타로: 뽑은 카드를 PDF에 이미지 그리드로 포함(역방향 180° 회전)
        tarot_cards: tarotCards && tarotCards.length ? tarotCards : undefined,
      }).then((r) => {
        pdfCache.current = r;
        setPdfUrl(r.url); // 버튼 → 실제 링크(⤓ PDF 열기)로 전환: 팝업차단 없이 열람, 재클릭해도 재생성 안 함
        return r;
      }).finally(() => { pdfInflight.current = null; });  // 실패 시 재시도 허용
    }
    return pdfInflight.current;
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
    if (pdfBusy) return;
    setPdfBusy(true);
    // 진행/열람은 하단 공통 dock에서 처리 — 생성이 걸리는 동안 진행중 표시(연타·이탈 방지),
    // 완료 시 dock의 '열기' 버튼(탭=제스처라 모바일 팝업차단 없음). 여기선 트리거만.
    const id = `pdf-${Date.now()}`;
    window.dispatchEvent(new CustomEvent("saju:gen-start", { detail: { id, kind: "pdf" } }));
    try {
      const r = await ensurePdf();
      window.dispatchEvent(new CustomEvent("saju:gen-done", {
        detail: { id, url: r.url, download_url: r.download_url, filename: r.filename },  // 열기·저장 둘 다 dock에서 선택
      }));
    } catch {
      window.dispatchEvent(new CustomEvent("saju:gen-error", {
        detail: { id, message: tr("answer.pdf_gen_error") },
      }));
    } finally {
      setPdfBusy(false);
    }
  }

  // ── 공유 한도 규약(2026-07-23 전면 재설계) ────────────────────────────────
  // 예전 구조: '차감 → 공유'(데스크톱) / '공유 → 차감'(모바일). 둘 다 문제가 있었다.
  //   · 차감 먼저 → 클립보드 실패·카카오 취소로 공유가 무산돼도 횟수만 날아감(환원 수단 없음)
  //   · 공유 먼저 → 한도 초과여도 이미 전송된 뒤라 **강제력이 0**(모바일이 사실상 무제한이었다)
  // 새 구조: **사전 확인 → 공유 → 성공 시에만 집계**. 둘 다 해결되고 환원 API 도 필요 없다.
  //   ⚠️ 환원 엔드포인트를 만들면 안 된다 — refund 는 1회씩 감소라 반복 호출로 카운터를 0으로
  //      되돌릴 수 있다(=무제한 공유). 그래서 '소비 후 보상'이 아니라 '사전 확인'을 택했다.
  //   실제 공유 동작(OS 공유시트·클립보드·카카오 SDK)은 전부 클라이언트에서 일어나므로
  //   서버가 막을 수 없다. 여기서 막지 않으면 한도는 존재하지 않는 것과 같다.

  // 한도/로그인 판정은 ApiError.code 로 한다. 예전엔 한국어 문구 부분일치(msg.includes("공유 횟수"))
  // 라서 ERR_MAP 카피를 한 줄만 다듬어도 전 채널 제한이 조용히 사라졌다(무증상 fail-open).
  function gateOf(e: any): "quota" | "login" | "other" {
    const code = String(e?.code || "");
    if (code === "share_quota_exceeded") return "quota";
    if (code === "login required to share" || e?.status === 401) return "login";
    return "other";
  }

  // 공유 '전' 한도 확인. 소진이면 공유 자체를 시작하지 않는다.
  async function canShareNow(): Promise<boolean> {
    try {
      const q = await api.shareQuota();
      if (!q.unlimited && q.remaining <= 0) {
        alert("무료 공유 횟수를 모두 사용했어요. 월 패스를 이용하면 더 많이 공유할 수 있어요.");
        return false;
      }
      return true;
    } catch (e: any) {
      if (gateOf(e) === "login") { alert("공유하려면 먼저 로그인해 주세요."); return false; }
      return true;   // 그 외 장애(5xx·네트워크)는 공유를 막지 않는다 — 무료 기능이라 가용성 우선
    }
  }

  // 공유가 확정된 뒤 집계. 이 시점엔 이미 나간 공유라 실패해도 되돌릴 수 없으므로 흐름을 막지 않는다
  // (한도는 canShareNow 가 앞에서 이미 막았다).
  async function countShare(channel: "kakao" | "email" | "link"): Promise<void> {
    try {
      await api.submitShare({ channel, message_id: messageId, session_id: sessionId });
      window.dispatchEvent(new Event("saju:share-counted"));   // 잔여 배지 즉시 갱신
    } catch { /* 집계 실패가 사용자 공유를 되돌리지는 못한다 */ }
  }

  // 공유:
  //  ① (모바일 Android/iOS 한정) PDF 파일 자체를 Web Share(files)로 카톡·메일 앱에 첨부 전송 —
  //     성공 시에만 1회 집계. 취소(AbortError)면 아무 것도 하지 않는다(이중집계·원치 않는 다운로드 제거).
  //  ② (데스크톱은 무조건) 카카오/메일/링크 메뉴. ⚠️ canShare 기능감지만으로 분기 금지 —
  //     Windows 크롬도 파일공유를 '지원'하지만 OS 공유창이 멈춰 보임(lib/webShare.ts 참조).
  async function onShare() {
    if (shareBusy) return;
    setShareBusy(true);
    try {
      const r = await ensurePdf();
      const absUrl = window.location.origin + r.url;
      setPdfShareUrl(absUrl);
      const navAny = navigator as any;
      // ① 모바일: 네이티브 시트로 PDF 파일 자체 전달
      let file: File | null = null;
      try {
        const resp = await fetch(r.url);
        const blob = await resp.blob();
        file = new File([blob], r.filename, { type: "application/pdf" });
      } catch {
        file = null;
      }
      if (file && canNativeFileShare([file])) {
        // ⚠️ 한도 확인은 반드시 share() '앞'에서 — 뒤에서 하면 이미 카톡으로 전송된 뒤라 못 막는다.
        if (!(await canShareNow())) return;
        try {
          // ⚠️ files 만 보낸다 — title/text 를 함께 주면 카카오톡 등 일부 대상이 'PDF 문서 첨부'가
          //   아니라 '텍스트/링크 메시지'로 강등해 안내 이미지만 가고 파일이 안 붙는다(운영자 지적 #9,
          //   '휴대폰에서도 파일 안 붙음' 2026-07-30). title 도 같은 강등을 유발하므로 넣지 않는다.
          await navAny.share({ files: [file] });
          await countShare("link");   // 성공 확정 후 1회만 집계(취소 시 미집계)
        } catch (e: any) {
          if (e?.name === "AbortError") return;   // 사용자 취소 → 미집계·미다운로드
          setMenuOpen(true);                        // 그 외 실패 → 데스크톱 메뉴로
        }
        return;
      }
      // ② 파일공유 미지원: 데스크톱은 카카오/메일/링크 메뉴. 인앱 웹뷰(카톡/네이버/인스타)는
      //    Web Share(files)가 막혀 링크카드=이미지로만 가므로, 메뉴 상단에 '저장 후 채팅 첨부' 안내를
      //    띄운다(inApp 분기 렌더). ensurePdf 는 위에서 이미 돌아 PDF 저장 버튼이 즉시 뜬다.
      setMenuOpen(true);
    } catch {
      alert(tr("answer.share_fail"));
    } finally {
      setShareBusy(false);
    }
  }

  // 데스크톱 공유 메뉴 선택 — 채널별로 PDF '링크'를 전달(파일 첨부는 웹 제약상 불가).
  //  ① 사전 한도 확인 → ② 공유 실행 → ③ **성공한 경우에만** 집계.
  //  예전엔 ②보다 집계가 먼저라, 클립보드 실패·카카오 미전송이어도 횟수만 사라졌다(환원 불가).
  async function shareVia(channel: "kakao" | "email" | "link") {
    // 동기 잠금 — React state 는 같은 틱 연타를 못 막는다(DownloadGuard 와 동일 규약).
    // 없을 땐 더블클릭 한 번에 1회 공유로 2회가 차감됐다(무료 5회 중 40%).
    if (shareLock.current) return;
    shareLock.current = true;
    try {
      if (!(await canShareNow())) { setMenuOpen(false); return; }
      const url = pdfShareUrl || (pdfCache.current ? window.location.origin + pdfCache.current.url : "");
      if (!url) { setMenuOpen(false); return; }
      if (channel === "kakao") {
        // 카드 대표이미지 = PDF 첫 장 썸네일(앱 아이콘 아님). 카카오 스크래퍼가 공개 URL을 가져가
        //   '실제 상담서'처럼 보이게 한다(운영자 지적 #9 '안내 이미지만 온다'). 렌더 실패해도 링크는 동작.
        //   ⚠️ 데스크톱 카카오 웹은 파일 첨부가 원천 불가 → 링크 카드가 상한(PDF 파일 자체는 휴대폰 공유).
        const sent = await shareKakaoLink({
          title: pdf.docTitle,
          description: "상담 내용 전문이 담긴 PDF예요. 카드를 눌러 전체 내용을 확인하세요.",
          url,
          imageUrl: url + "/thumb.png",
        });
        if (sent) {
          await countShare("kakao");
        } else if (await copyText(url)) {
          await countShare("link");
          alert("카카오 공유를 사용할 수 없어 링크를 복사했어요. 붙여넣어 전달해 주세요.");
        } else {
          // 공유도 복사도 실패 — 아무것도 나가지 않았으므로 차감하지 않는다.
          alert("카카오 공유와 링크 복사에 모두 실패했어요. 주소창의 링크를 직접 전달해 주세요.");
        }
      } else if (channel === "email") {
        // (사용되지 않음 — 메일은 onEmailSend로 처리) 안전 폴백만 유지
        mailtoFallback(url, "");
        await countShare("email");
      } else {
        const done = await copyText(url);
        if (done) {
          await countShare("link");
          setShared(true);
          window.setTimeout(() => setShared(false), 4000);
        } else {
          // 복사 실패인데 차감되던 자리 — 이제 차감하지 않고 사용자에게 알린다(예전엔 무증상).
          alert("링크 복사에 실패했어요. 브라우저 주소를 길게 눌러 복사해 주세요.");
        }
      }
      setMenuOpen(false);
    } finally {
      shareLock.current = false;
    }
  }

  // 메일 클라이언트로 폴백(서버 SMTP 미설정/실패 시): 링크를 본문에 담아 사용자 메일앱 실행.
  function mailtoFallback(url: string, to: string) {
    const subject = encodeURIComponent(pdf.docTitle);
    const body = encodeURIComponent(`${pdf.docTitle}\n\n상담서 PDF 보기: ${url}\n\n— 인생상담 친구`);
    window.location.href = `mailto:${to}?subject=${subject}&body=${body}`;
  }

  // 메일 보내기 = 서버가 PDF를 첨부해 발송(로그인+한도). SMTP 미설정(503)이면 mailto(링크)로 폴백.
  async function onEmailSend() {
    if (emailBusy) return;
    const to = emailTo.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) {
      alert("받는 사람 이메일 주소를 정확히 입력해 주세요.");
      return;
    }
    const url = pdfShareUrl || (pdfCache.current ? window.location.origin + pdfCache.current.url : "");
    const token = pdfCache.current?.token;
    if (!token) { alert("공유용 PDF를 먼저 준비해 주세요."); return; }
    setEmailBusy(true);
    try {
      await api.emailPdf({ token, to, doc_title: pdf.docTitle });
      setEmailMode(false);
      setMenuOpen(false);
      setEmailTo("");
      setShared(true);  // "메일 전송됨" 토스트
      window.setTimeout(() => setShared(false), 4000);
    } catch (e: any) {
      const status = e?.status;
      if (status === 503) {
        // 서버 메일 미설정 → 사용자 메일앱(mailto·링크)로 폴백.
        // ⚠️ 503 은 서버가 한도를 소비하기 '전'에 나온다(pdf.py: SMTP 확인 → consume 순서).
        //    예전엔 여기서 집계도 확인도 없어, SMTP 가 꺼진 환경은 메일 채널 전체가 무제한이었다.
        if (await canShareNow()) {
          mailtoFallback(url, to);
          await countShare("email");
          setEmailMode(false);
          setMenuOpen(false);
        }
      } else if (gateOf(e) === "quota") {
        alert("무료 공유 횟수를 모두 사용했어요. 월 패스를 이용하면 더 많이 공유할 수 있어요.");
      } else if (status === 401 || status === 403) {
        alert("메일 발송은 로그인 후 이용할 수 있어요.");
      } else {
        alert("메일 발송에 실패했어요. 잠시 후 다시 시도하거나 링크 복사로 전달해 주세요.");
      }
    } finally {
      setEmailBusy(false);
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
    } else if (getCachedMe()) {
      // B-3: 👍 직후 한 줄 후기 유도(회원만 — 작성 API가 로그인 필요). 건너뛰어도 👍는 이미 반영됨.
      setRvText("");
      setRvStars(5);
      setRvPopup(true);
    } else {
      setFbThanks(true);
      window.setTimeout(() => setFbThanks(false), 2500);
    }
  }

  // B-3 한 줄 후기 제출 — 관리자 승인 후 게시, 승인 시 리워드 지급(백엔드 정책)
  async function submitReview() {
    const content = rvText.trim();
    if (content.length < 5 || rvBusy) return;
    setRvBusy(true);
    try {
      await api.submitReview({ source, content, rating: rvStars });
      setRvPopup(false);
      setRvDone("후기가 접수됐어요! 확인 후 게시되며, 게시되면 포인트가 적립됩니다 🎁");
      window.setTimeout(() => setRvDone(""), 4000);
    } catch (e: any) {
      setRvPopup(false);
      setRvDone(e?.message || "후기 접수에 실패했어요. 잠시 후 다시 시도해 주세요.");
      window.setTimeout(() => setRvDone(""), 4000);
    } finally {
      setRvBusy(false);
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

  // 사주 답변 → 1분 쇼츠 영상. 클릭 확인 → 즉시 차감·생성 시작 → 하단 진행팝업.
  async function onMakeVideo() {
    if (vidBusy || !messageId) return;
    // 차감 P는 관리자 설정값(me.video_gen_cost)을 따른다 — 하드코딩 금지(관리자 변경 즉시 반영).
    const costP = fmtNum(getCachedMe()?.video_gen_cost ?? 39000);
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
      api.me().then(setCachedMe).catch(() => {});   // 영상 생성 즉시 차감 → 사이드바·FAB 잔액 즉시 반영(패턴 B)
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
          {rvPopup && (
            <div className="fb-popup" role="dialog" aria-label="한 줄 후기">
              <div className="fb-popup-title">도움이 되셨다니 기뻐요! 한 줄 후기를 남겨 주시겠어요?</div>
              <div className="rv-star-input" aria-label="별점 선택">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={n <= rvStars ? "on" : ""}
                    onClick={() => setRvStars(n)}
                    aria-label={`${n}점`}
                  >
                    ★
                  </button>
                ))}
              </div>
              <textarea
                className="fb-popup-text"
                placeholder="예) 올해 이직 고민이 있었는데 방향을 잡는 데 도움이 됐어요 (5자 이상)"
                value={rvText}
                onChange={(e) => setRvText(e.target.value)}
                rows={2}
                maxLength={200}
              />
              <div className="fb-popup-actions">
                <button className="fb-popup-skip" onClick={() => setRvPopup(false)}>다음에요</button>
                <button
                  className="fb-popup-submit"
                  onClick={submitReview}
                  disabled={rvText.trim().length < 5 || rvBusy}
                >
                  후기 남기기 🎁
                </button>
              </div>
            </div>
          )}
          {rvDone && <span className="fb-thanks">{rvDone}</span>}
        </div>
      )}

      <div className="aa-right">
        <button className="copy-btn" onClick={onCopy} title={tr("answer.copy_title")}>
          {copied ? tr("answer.copy_done") : tr("answer.copy_btn")}
        </button>
        <span className="share-wrap">
          <button className="copy-btn" onClick={onShare} disabled={shareBusy} title={tr("answer.share_title")}>
            {shareBusy ? tr("answer.share_busy") : shared ? tr("answer.share_done") : tr("answer.share_btn")}
          </button>
          {menuOpen && (
            <>
              <div className="share-menu-backdrop" onClick={() => setMenuOpen(false)} />
              <div className="share-menu" role="menu" aria-label="상담서 PDF 공유">
                <div className="share-menu-title">상담서 PDF 공유</div>
                <ShareQuotaNote />

                {inApp.inApp && (
                  <div className="share-inapp-guide" role="note">
                    <b>📄 상담서 파일 그대로 보내기</b>
                    지금은 <b>{inApp.name}</b> 안이라 카톡엔 <b>링크 카드(이미지)</b>만 전달돼요.
                    파일 그대로 보내려면 아래 <b>⤓ PDF 저장</b> 후, 카톡 채팅방 <b>[＋] → 파일</b>에서
                    방금 저장한 PDF를 첨부해 보내세요.
                  </div>
                )}

                {kakaoAvailable() && (
                  <button className="share-menu-item" role="menuitem" onClick={() => shareVia("kakao")}>
                    <span className="smi-ic smi-kakao" aria-hidden>💬</span> 카카오톡으로 보내기
                  </button>
                )}
                <button className="share-menu-item" role="menuitem" onClick={() => setEmailMode((v) => !v)}>
                  <span className="smi-ic" aria-hidden>✉️</span> 메일로 보내기
                  <span className="smi-caret" aria-hidden>{emailMode ? "▾" : "▸"}</span>
                </button>
                {emailMode && (
                  <div className="share-email-form">
                    <input
                      type="email"
                      className="share-email-input"
                      placeholder="받는 사람 이메일"
                      value={emailTo}
                      onChange={(e) => setEmailTo(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") onEmailSend(); }}
                      autoFocus
                    />
                    <button className="share-email-send" onClick={onEmailSend} disabled={emailBusy}>
                      {emailBusy ? "보내는 중…" : "PDF 첨부 발송"}
                    </button>
                    <div className="share-email-note">서버가 PDF를 첨부해 보냅니다. 미설정 시 내 메일앱(링크)으로 열려요.</div>
                  </div>
                )}
                <button className="share-menu-item" role="menuitem" onClick={() => shareVia("link")}>
                  <span className="smi-ic" aria-hidden>🔗</span> 링크 복사
                </button>
                {pdfCache.current && (
                  <DownloadGuard
                    className="share-menu-item"
                    href={window.location.origin + pdfCache.current.download_url}
                    filename={pdfCache.current.filename}
                    doneLabel={<><span className="smi-ic" aria-hidden>✅</span> 저장 완료</>}
                    onFire={() => setMenuOpen(false)}
                  >
                    <span className="smi-ic" aria-hidden>⤓</span> PDF 저장
                  </DownloadGuard>
                )}
                {!inApp.inApp && (
                  <div className="share-menu-note">
                    PC에선 카카오/메일에 파일을 직접 첨부할 수 없어 <b>링크</b>로 전달돼요.
                    파일 그대로 보내려면 휴대폰에서 공유하세요.
                  </div>
                )}
              </div>
            </>
          )}
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
          <button className="copy-btn" onClick={onPdf} disabled={pdfBusy} title={tr("answer.pdf_title")}>
            {pdfBusy ? tr("answer.pdf_busy") : tr("answer.pdf_btn")}
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
