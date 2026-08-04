/** 공유 해설(스트리밍) + 추가질문 채팅 + 추천질문 칩. streamPath만 주면 동작(궁합/도구 공용). */
import { useEffect, useRef, useState } from "react";
import { streamSSE } from "../lib/sse";
import { renderRich, stripMarkdown } from "../lib/format";
import { useMe, refreshMe } from "../api";
import { useCharge } from "./ChargeModal";
import AnswerActions, { type PdfMeta } from "./AnswerActions";
import FollowupBilling from "./FollowupBilling";
import TypingDots from "./TypingDots";
import ConsultationReportButton, { type ReportReq } from "./ConsultationReportButton";

type Turn = {
  role: "user" | "assistant"; content: string; refined?: boolean; charged?: number;
  message_id?: number;   // 피드백(👍👎)·공유 연결용 — done 이벤트의 assistant_message_id
  is_preview?: boolean;  // 미리보기 컷 답변엔 공유/PDF 미노출(결제 전 반쪽 유출 방지)
};

export default function ExplainChat({
  streamPath,
  isPreview,
  autoStart = true,
  qaOnly = false,
  pdf,
  pdfHeader,
  feedbackSource,
  feedbackSessionId,
  suggestFetch,
  onBeforeExplain,
  entryPaid = false,
  initialExplain,
}: {
  streamPath: string;
  isPreview: boolean;
  autoStart?: boolean;
  /** 저장된 해설(재열람 복원·24h 재사용) — 있으면 버튼 대신 즉시 표시(재생성·재스트림 없음).
   *  종전엔 복원 세션이 버튼을 띄우고, 클릭 시 빈 메시지 스트림이 '추가질문' 경로로 빠져
   *  "질문을 입력해 주세요" 에러 → "해설 생성이 지연" 오표시(운영자 실측·재현 확정). */
  initialExplain?: string;
  /** 입장료를 낸 프리미엄 메뉴(작명·궁합·택일 등)면 true — 해설은 입장료에 '포함'이라
   *  '무료'라고 하면 돈 낸 사용자에게 오해를 준다(운영자 지적). free-tag → '포함'으로 바뀜. */
  entryPaid?: boolean;
  qaOnly?: boolean;       // 해설 블록 없이 '추가 질문'만(첫 답변을 페이지가 자체 렌더하는 꿈해몽 등)
  pdf?: PdfMeta;          // 주면 해설 아래에 복사·공유·PDF 액션바 노출(택일/작명 등)
  pdfHeader?: string;     // PDF 본문 상단에 붙일 결과 요약(추천 길일/이름 등)
  feedbackSource?: "tool" | "compat";  // 주면 해설에 👍👎 노출(메시지 출처 네임스페이스)
  feedbackSessionId?: string;          // 익명 피드백 upsert 키(tool_id 등)
  suggestFetch?: () => Promise<string[]>;  // 주면 해설/답변 후 '이어서 물어보세요' 칩 노출
  /** 해설 시작 직전 게이트(운영자 지시: 미결제 상태의 '설명' 클릭은 차감 동의 팝업 후 진행).
   *  false 반환 시 해설을 시작하지 않는다(페이지가 입장 팝업→재생성 등 자체 처리). */
  onBeforeExplain?: () => Promise<boolean>;
}) {
  const [explain, setExplain] = useState("");
  const [explaining, setExplaining] = useState(false);
  const [explainFailed, setExplainFailed] = useState(false);   // 무청크/에러/무응답으로 끝남 → 재시도 유도
  const [stage, setStage] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [qStreaming, setQStreaming] = useState(false);
  const [msgId, setMsgId] = useState<number | undefined>(undefined);  // 해설 메시지 id(피드백용)
  const [suggests, setSuggests] = useState<string[]>([]);            // 추천질문 칩
  const me = useMe();
  const { openCharge } = useCharge();
  const [qDepth, setQDepth] = useState<"basic" | "deep">("basic");   // 추가질문 등급(기본=1000P)
  const startedRef = useRef(false);                       // 중복 시작 방지 가드
  const [explainOn, setExplainOn] = useState(autoStart);  // 버튼 노출 제어(autoStart면 즉시 시작)
  const explainingRef = useRef(false);  // 항상 활성 입력 — ask가 해설 완료를 대기
  const acRef = useRef<AbortController | null>(null);     // 현재 활성 스트림 취소(이탈 시 GPU 중단)
  const explainTopRef = useRef<HTMLDivElement | null>(null);  // 해설 시작점 — 완료 시 여기로 스크롤(운영자 지시)

  async function loadSuggests() {
    if (!suggestFetch) return;
    try { setSuggests(await suggestFetch()); } catch { /* 무시 */ }
  }

  async function startExplain() {
    if (startedRef.current) return;
    startedRef.current = true;
    // 시작 게이트(운영자 지시): 미결제 상태의 '설명' 클릭은 차감 동의 팝업을 먼저 — 거부/미충족이면
    // 시작하지 않고 재클릭 가능 상태로 되돌린다(종전엔 무과금 프리뷰 스트림으로 흘러 '작동 안 됨').
    if (onBeforeExplain) {
      let ok = false;
      try { ok = await onBeforeExplain(); } catch { ok = false; }
      if (!ok) { startedRef.current = false; return; }
    }
    setExplainOn(true);
    setExplaining(true); explainingRef.current = true;
    setExplainFailed(false);
    const ac = new AbortController(); acRef.current = ac;
    // 무응답 방지: 첫 청크가 오는지 추적 + 60초 타임아웃. 청크 0개로 끝나면(에러·무응답·빈 결과)
    // '생성 중'으로 고착시키지 않고 실패로 전환해 '다시 시도'를 노출한다(운영자 보고: 신년 해설 멈춤).
    let firstChunk = false;
    const to = window.setTimeout(() => {
      if (!firstChunk) { try { ac.abort(); } catch { /* noop */ } }
    }, 60000);
    streamSSE(streamPath, { message: "", depth: "deep" }, {
      onChunk: (full) => { firstChunk = true; setExplain(full); },
      onRefine: setExplain, onStage: setStage,
      onDone: (d) => { if (d?.assistant_message_id) setMsgId(d.assistant_message_id); },
    }, ac.signal).catch(() => { /* 아래 finally에서 무청크 판정 */ }).finally(() => {
      window.clearTimeout(to);
      setExplaining(false); explainingRef.current = false; setStage(null);
      if (!firstChunk) setExplainFailed(true);   // 청크 없이 끝남 = 실패 → 재시도 유도
      loadSuggests();
      // [운영자 지시 — 전 메뉴 공통] 해설이 검증·보강까지 끝나 최종본이 확정되면, 스트리밍으로
      // 밑까지 내려간 화면을 해설 '시작점'으로 되돌린다 — 사용자가 처음부터 읽도록.
      if (firstChunk) {
        const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        window.setTimeout(() => explainTopRef.current?.scrollIntoView(
          { block: "start", behavior: reduced ? "auto" : "smooth" }), 120);
      }
    });
  }

  function retryExplain() {
    startedRef.current = false;
    setExplain(""); setExplainFailed(false);
    startExplain();
  }

  useEffect(() => {
    // 새 결과(streamPath 변경) 시 초기화 — 인스턴스 재사용돼도 '설명' 버튼이 새로 노출
    startedRef.current = false;
    setExplainOn(autoStart);
    setExplain(""); setExplainFailed(false);
    setTurns([]);
    if (qaOnly) loadSuggests();       // 해설 없이 QA만 — 추천칩은 즉시 로드
    else if (initialExplain && initialExplain.trim()) {
      // 저장 해설 즉시 표시(복원·24h 재사용) — 재스트림·재생성 없이 본문+추가질문 활성
      startedRef.current = true;
      setExplainOn(true);
      setExplain(initialExplain);
      loadSuggests();
    }
    else if (autoStart) startExplain();
    // 페이지 이탈(언마운트)·결과 교체 시 진행 중 스트림 즉시 취소 → 백엔드 disconnect → LLM(GPU) 중단
    return () => { try { acRef.current?.abort(); } catch { /* noop */ } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamPath]);

  async function ask(preset?: string) {
    const text = (preset ?? q).trim();
    if (!text || qStreaming) return;
    setQ("");
    setQStreaming(true);
    setSuggests([]);
    // 항상 활성 입력 — 해설 진행 중이면 끝날 때까지 대기(동일 세션 동시 스트림 방지)
    while (explainingRef.current) await new Promise((r) => setTimeout(r, 250));
    setTurns((t) => [...t, { role: "user", content: text }, { role: "assistant", content: "" }]);
    const upd = (p: Partial<Turn>) =>
      setTurns((t) => { const c = [...t]; c[c.length - 1] = { ...c[c.length - 1], ...p }; return c; });
    const ac = new AbortController(); acRef.current = ac;
    try {
      await streamSSE(streamPath, { message: text, depth: qDepth }, {
        onChunk: (f) => upd({ content: f }), onRefine: (f) => upd({ content: f, refined: true }),
        onStage: setStage,
        onDone: (d) => {
          upd({
            charged: typeof d?.credits_charged === "number" ? d.credits_charged : undefined,
            message_id: d?.assistant_message_id,   // 답변별 공유/피드백 연결
            is_preview: !!d?.is_preview,
          });
          if (typeof d?.credits_charged === "number" && d.credits_charged > 0) refreshMe();   // 추가질문 차감 후 잔액 즉시 반영(패턴 B)
        },
      }, ac.signal);
    } catch (e: any) {
      if (e?.name === "AbortError") { /* 이탈 취소 — 조용히 무시 */ }
      else if (e?.message === "PAYWALL") { upd({ content: "" }); openCharge("추가 질문 포인트가 부족해요. 충전하면 작성 내용 그대로 이어집니다."); }
      else upd({ content: "답변 생성에 실패했어요." });
    } finally {
      setQStreaming(false); setStage(null);
      loadSuggests();
    }
  }

  return (
    <div className="cr-explain">
      {!qaOnly && (
        <>
          <div className="cr-sub" ref={explainTopRef} style={{ scrollMarginTop: 72 }}>
            해설 {stage === "refining" && <span className="cr-refine-tag">보강 중…</span>}
          </div>
          <div className="explain-body">
            {!explainOn ? (
              <button className="explain-cta" onClick={startExplain}>
                🔮 자세히 설명해 드릴까요?{" "}
                {entryPaid
                  ? <span className="free-tag included">입장료 포함</span>
                  : <span className="free-tag">무료</span>}
              </button>
            ) : (
              <>
                {explain ? renderRich(explain) : (
                  explainFailed ? (
                    <div className="explain-retry">
                      <span>해설 생성이 지연되고 있어요. 네트워크나 서버 사정일 수 있어요.</span>
                      <button type="button" className="explain-retry-btn" onClick={retryExplain}>🔄 다시 시도 (무과금)</button>
                    </div>
                  ) : (
                    <span className="gen-live" role="status" aria-live="polite">
                      🔮 <b>설명을 생성하고 있어요</b> <TypingDots />
                    </span>
                  )
                )}
              </>
            )}
          </div>
        </>
      )}
      {!qaOnly && isPreview && (
        <div className="reveal-cta reveal-cta-note">
          🔒 여기까지는 <b>미리보기</b>예요 —{" "}
          {me ? "전체 해설은 충전 후 이용할 수 있어요." : "로그인하면 전체 해설과 추가 질문을 볼 수 있어요."}
        </div>
      )}
      {pdf && explain && !explaining && (
        <AnswerActions
          text={(pdfHeader ? pdfHeader.trim() + "\n\n" : "") + stripMarkdown(explain)}
          pdf={pdf}
          messageId={feedbackSource ? msgId : undefined}
          source={feedbackSource}
          sessionId={feedbackSessionId}
          isLast
        />
      )}
      <div className="compat-qa">
        <div className="cr-sub">추가 질문</div>
        {turns.map((t, i) => (
          <div key={i} className={`qa-turn qa-${t.role}`}>
            <div className="qa-bubble">
              {t.content ? renderRich(t.content) : (
                <span className="gen-live" role="status" aria-live="polite"><b>답변을 생성하고 있어요</b> <TypingDots /></span>
              )}
              {t.refined && <span className="qa-refined">✨ 보강됨</span>}
              {t.role === "assistant" && typeof t.charged === "number" && t.charged > 0 && (
                <span className="qa-charged">✓ {t.charged.toLocaleString()}P 차감됨</span>
              )}
            </div>
            {/* 추가질문 답변에도 공유/복사/PDF·피드백 — 사주(ChatPage)와 동일 표준(운영자 지적: 답변 후 공유 부재).
                미리보기 컷 답변은 미노출(결제 전 반쪽 유출 방지), 스트리밍 중인 마지막 턴도 미노출. */}
            {t.role === "assistant" && t.content && !t.is_preview && pdf &&
              !(qStreaming && i === turns.length - 1) && (
              <AnswerActions
                text={`[질문] ${turns[i - 1]?.role === "user" ? turns[i - 1].content : ""}\n\n${stripMarkdown(t.content)}`}
                pdf={{ ...pdf, item: ((turns[i - 1]?.role === "user" ? turns[i - 1].content : "") || pdf.item || "추가 질문").slice(0, 40) }}
                messageId={feedbackSource ? t.message_id : undefined}
                source={feedbackSource}
                sessionId={feedbackSessionId}
                isLast={i === turns.length - 1}
              />
            )}
          </div>
        ))}
        {suggests.length > 0 && !qStreaming && (
          <div className="suggest-chips followup">
            <div className="suggest-label">💡 이어서 물어보세요</div>
            {suggests.map((sg) => (
              <button key={sg} className="chip" disabled={qStreaming} onClick={() => ask(sg)}>
                {sg}
              </button>
            ))}
          </div>
        )}
        <FollowupBilling me={me} depth={qDepth} onDepth={setQDepth} />
        <div className="qa-input-row">
          <input
            className="qa-input"
            placeholder="결과에 대해 더 물어보세요"
            value={q}
            disabled={qStreaming}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
          />
          <button className="qa-send" disabled={qStreaming || !q.trim()} onClick={() => ask()}>
            {qStreaming ? "…" : explaining ? "대기" : "질문"}
          </button>
        </div>
        {pdf && explain && turns.some((t) => t.role === "assistant" && t.content) && !qStreaming && (
          <div className="report-row">
            <ConsultationReportButton
              build={(): ReportReq | null => {
                const conversation = [
                  { role: "assistant", content: (pdfHeader ? pdfHeader.trim() + "\n\n" : "") + stripMarkdown(explain) },
                  ...turns.filter((t) => t.content).map((t) => ({ role: t.role, content: stripMarkdown(t.content) })),
                ];
                return {
                  doc_title: `${pdf.docTitle} 종합 감정서`,
                  person_line: pdf.personLine,
                  item: pdf.item || "종합 감정",
                  conversation,
                  topic: pdf.item ? `${pdf.item} 상담` : "상담",
                };
              }}
            />
            <span className="report-hint">여러 질문·답변을 하나의 감정서로 정리해 PDF로 만듭니다.</span>
          </div>
        )}
      </div>
    </div>
  );
}
