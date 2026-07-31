/** 공유 해설(스트리밍) + 추가질문 채팅 + 추천질문 칩. streamPath만 주면 동작(궁합/도구 공용). */
import { useEffect, useRef, useState } from "react";
import { streamSSE } from "../lib/sse";
import { renderRich, stripMarkdown } from "../lib/format";
import { useMe } from "../api";
import { useCharge } from "./ChargeModal";
import AnswerActions, { type PdfMeta } from "./AnswerActions";
import FollowupBilling from "./FollowupBilling";
import ConsultationReportButton, { type ReportReq } from "./ConsultationReportButton";

type Turn = { role: "user" | "assistant"; content: string; refined?: boolean; charged?: number };

export default function ExplainChat({
  streamPath,
  isPreview,
  autoStart = true,
  pdf,
  pdfHeader,
  feedbackSource,
  feedbackSessionId,
  suggestFetch,
}: {
  streamPath: string;
  isPreview: boolean;
  autoStart?: boolean;
  pdf?: PdfMeta;          // 주면 해설 아래에 복사·공유·PDF 액션바 노출(택일/작명 등)
  pdfHeader?: string;     // PDF 본문 상단에 붙일 결과 요약(추천 길일/이름 등)
  feedbackSource?: "tool" | "compat";  // 주면 해설에 👍👎 노출(메시지 출처 네임스페이스)
  feedbackSessionId?: string;          // 익명 피드백 upsert 키(tool_id 등)
  suggestFetch?: () => Promise<string[]>;  // 주면 해설/답변 후 '이어서 물어보세요' 칩 노출
}) {
  const [explain, setExplain] = useState("");
  const [explaining, setExplaining] = useState(false);
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

  async function loadSuggests() {
    if (!suggestFetch) return;
    try { setSuggests(await suggestFetch()); } catch { /* 무시 */ }
  }

  function startExplain() {
    if (startedRef.current) return;
    startedRef.current = true;
    setExplainOn(true);
    setExplaining(true); explainingRef.current = true;
    const ac = new AbortController(); acRef.current = ac;
    streamSSE(streamPath, { message: "", depth: "deep" }, {
      onChunk: setExplain, onRefine: setExplain, onStage: setStage,
      onDone: (d) => { if (d?.assistant_message_id) setMsgId(d.assistant_message_id); },
    }, ac.signal).catch(() => {}).finally(() => {
      setExplaining(false); explainingRef.current = false; setStage(null);
      loadSuggests();
    });
  }

  useEffect(() => {
    // 새 결과(streamPath 변경) 시 초기화 — 인스턴스 재사용돼도 '설명' 버튼이 새로 노출
    startedRef.current = false;
    setExplainOn(autoStart);
    setExplain("");
    if (autoStart) startExplain();
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
        onDone: (d) => { if (typeof d?.credits_charged === "number") upd({ charged: d.credits_charged }); },
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
      <div className="cr-sub">
        해설 {stage === "refining" && <span className="cr-refine-tag">보강 중…</span>}
      </div>
      <div className="explain-body">
        {!explainOn ? (
          <button className="explain-cta" onClick={startExplain}>
            🔮 자세히 설명해 드릴까요?
          </button>
        ) : (
          <>
            {explain ? renderRich(explain) : (explaining ? "" : "해설을 불러오는 중…")}
            {explaining && !explain && <span className="thinking-dots" />}
          </>
        )}
      </div>
      {isPreview && (
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
              {t.content ? renderRich(t.content) : <span className="thinking-dots" />}
              {t.refined && <span className="qa-refined">✨ 보강됨</span>}
              {t.role === "assistant" && typeof t.charged === "number" && t.charged > 0 && (
                <span className="qa-charged">✓ {t.charged.toLocaleString()}P 차감됨</span>
              )}
            </div>
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
