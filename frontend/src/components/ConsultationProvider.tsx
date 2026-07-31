import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  api,
  consultationSessionWsUrl,
  useMe,
  type ConsultationSession,
  type ConsultationChatMessage,
  type ConsultationStatus,
} from "../api";

/**
 * 1:1 상담 실시간 채팅 — 전역 프로바이더.
 *
 * 활성 세션의 WebSocket 연결·상태를 앱 최상단에서 보유하고, 채팅 오버레이를 Portal 로 띄운다.
 * 라우팅이 바뀌어도 유지되며(요건 9), 서버 카운트다운(요건 7)·종료 시 요약 PDF 동의 팝업(요건 8)을 포함.
 * onDuty(상담 중이거나 상담사 콘솔 접속 중)는 App 의 idle 자동로그아웃 예외에 사용.
 */

type Role = "user" | "consultant";

type Ctx = {
  /** 사용자: 동의 후 상담 요청 → 대기/채팅 오버레이 오픈 */
  startRequest: (consultantId: number, consent: boolean) => Promise<void>;
  /** 상담사: 수락 후 세션 오픈(또는 재입장) */
  openSession: (sessionId: string, role: Role) => void;
  active: boolean;
  onDuty: boolean;
  setConsoleOnDuty: (v: boolean) => void;
};

const ConsultationContext = createContext<Ctx | null>(null);
export function useConsultation(): Ctx {
  const c = useContext(ConsultationContext);
  if (!c) throw new Error("useConsultation must be used within ConsultationProvider");
  return c;
}

function fmt(sec: number | null): string {
  if (sec == null || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function ConsultationProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<{ sessionId: string; role: Role } | null>(null);
  const [session, setSession] = useState<ConsultationSession | null>(null);
  const [messages, setMessages] = useState<ConsultationChatMessage[]>([]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [status, setStatus] = useState<ConsultationStatus | null>(null);
  const [warned, setWarned] = useState(false);
  const [ended, setEnded] = useState<{ reason?: string; noShow?: boolean } | null>(null);
  const [consoleOnDuty, setConsoleOnDuty] = useState(false);
  const [draft, setDraft] = useState("");
  const [rated, setRated] = useState(0); // 종료 후 제출한 만족도(1~5), 0=미제출
  const socketRef = useRef<WebSocket | null>(null);
  const endedRef = useRef(false);
  const me = useMe();
  const resumeCheckedRef = useRef<string | null>(null);

  // 새로고침/재접속 시 진행 중인 내 상담을 자동 복원(유료 세션 유실 방지). 로그인당 1회 확인.
  useEffect(() => {
    if (!me) { resumeCheckedRef.current = null; return; }
    if (active) return;
    if (resumeCheckedRef.current === String(me.id)) return;
    resumeCheckedRef.current = String(me.id);
    api.myConsultations()
      .then((r) => {
        const live = r.items.find(
          (s) => (s.status === "active" || s.status === "requested") && s.user_id === me.id
        );
        if (live) openSession(live.id, "user");
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id, active]);

  // 활성 세션 WebSocket 연결(+ 예기치 못한 끊김 시 재연결·DB 복원)
  useEffect(() => {
    if (!active) return;
    let closedByUs = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      const ws = new WebSocket(consultationSessionWsUrl(active!.sessionId));
      socketRef.current = ws;
      ws.onmessage = (ev) => {
        let m: any;
        try { m = JSON.parse(ev.data); } catch { return; }
        switch (m.type) {
          case "state":
            if (m.session) { setSession(m.session); setStatus(m.session.status); if (m.session.remaining_sec != null) setRemaining(m.session.remaining_sec); }
            setMessages(m.history || []);
            break;
          case "message":
            setMessages((cur) => [...cur, { id: Date.now() + Math.random(), sender: m.sender, content: m.content, created_at: new Date().toISOString() }]);
            if (status !== "active") setStatus("active");
            break;
          case "tick":
            setRemaining(m.remaining_sec);
            setStatus((s) => (s === "requested" || s == null ? "active" : s));
            break;
          case "warn_extend":
            setWarned(true); setRemaining(m.remaining_sec);
            break;
          case "ended":
            endedRef.current = true; setStatus("completed"); setEnded({ reason: m.reason });
            break;
          case "no_show":
            endedRef.current = true; setStatus("no_show"); setEnded({ noShow: true });
            break;
        }
      };
      ws.onclose = () => {
        if (closedByUs || endedRef.current) return;
        retry = setTimeout(connect, 1500); // 재연결 → 서버가 state(이력 포함) 재전송
      };
    }
    connect();
    return () => {
      closedByUs = true;
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
      socketRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.sessionId]);

  function reset() {
    endedRef.current = false;
    setSession(null); setMessages([]); setRemaining(null); setStatus(null);
    setWarned(false); setEnded(null); setDraft(""); setRated(0);
  }

  async function submitRating(n: number) {
    if (!active || rated) return;
    setRated(n);
    try { await api.rateConsultation(active.sessionId, n); } catch { /* 평가 실패는 조용히 무시 */ }
  }

  function openSession(sessionId: string, role: Role) {
    reset();
    setActive({ sessionId, role });
  }

  async function startRequest(consultantId: number, consent: boolean) {
    const s = await api.requestConsultation(consultantId, consent);
    reset();
    setSession(s); setStatus(s.status);
    setActive({ sessionId: s.id, role: "user" });
  }

  function closeOverlay() {
    setActive(null);
    reset();
  }

  function send() {
    const text = draft.trim();
    if (!text || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(JSON.stringify({ type: "message", content: text }));
    setDraft("");
  }

  function endChat() {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "end" }));
    } else {
      if (active) api.endConsultation(active.sessionId).catch(() => {});
    }
  }

  async function cancelWaiting() {
    if (active) { try { await api.cancelConsultation(active.sessionId); } catch { /* ignore */ } }
    closeOverlay();
  }

  async function extend() {
    if (!active) return;
    try { await api.extendConsultation(active.sessionId); setWarned(false); }
    catch (e: any) { alert(e?.message || "연장에 실패했어요."); }
  }

  async function makeReport() {
    if (!active) return;
    const id = `pdf-${Date.now()}`;
    window.dispatchEvent(new CustomEvent("saju:gen-start", { detail: { id, kind: "report" } }));
    try {
      const r = await api.consultationReport(active.sessionId);
      window.dispatchEvent(new CustomEvent("saju:gen-done", { detail: { id, url: r.url, filename: r.filename } }));
    } catch {
      window.dispatchEvent(new CustomEvent("saju:gen-error", { detail: { id, message: "상담서 생성에 실패했어요." } }));
    }
    closeOverlay();
  }

  const ctx: Ctx = {
    startRequest,
    openSession,
    active: active != null,
    onDuty: consoleOnDuty || active != null,
    setConsoleOnDuty,
  };

  return (
    <ConsultationContext.Provider value={ctx}>
      {children}
      {active &&
        createPortal(
          <div className="csl-chat-wrap" role="dialog" aria-label="1:1 상담 채팅">
            <div className="csl-chat">
              <div className="csl-chat-head">
                <div className="csl-chat-title">
                  {session?.consultant_name || "1:1 상담"}
                  <span className="csl-chat-role">{active.role === "consultant" ? "상담사" : "상담"}</span>
                </div>
                {status === "active" && (
                  <div className={`csl-timer ${warned ? "warn" : ""}`}>⏱ {fmt(remaining)}</div>
                )}
                <button className="csl-chat-x" onClick={() => (status === "active" ? endChat() : closeOverlay())} aria-label="닫기">×</button>
              </div>

              {/* 대기 중(수락 전) */}
              {(status === "requested" || status == null) && !ended && (
                <div className="csl-chat-wait">
                  <div className="csl-spin" aria-hidden />
                  <p>상담사 연결을 기다리는 중이에요…</p>
                  <p className="csl-wait-sub">상담사가 수락하면 채팅이 시작돼요. (미응답 시 자동 취소·환불)</p>
                  <button className="csl-wait-cancel" onClick={cancelWaiting}>요청 취소</button>
                </div>
              )}

              {/* 진행 중 채팅 */}
              {status === "active" && (
                <>
                  <div className="csl-chat-body">
                    {messages.map((m) => (
                      <div key={m.id} className={`csl-bubble ${m.sender === active.role ? "mine" : "theirs"} ${m.sender === "system" ? "sys" : ""}`}>
                        {m.content}
                      </div>
                    ))}
                  </div>
                  {warned && (
                    <div className="csl-extend-bar">
                      곧 상담 시간이 끝나요. <button onClick={extend}>연장하기</button>
                    </div>
                  )}
                  <div className="csl-chat-input">
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                      placeholder="메시지를 입력하세요"
                      rows={1}
                    />
                    <button onClick={send} disabled={!draft.trim()}>전송</button>
                  </div>
                  <button className="csl-end" onClick={endChat}>상담 종료</button>
                </>
              )}

              {/* 노쇼(미응답) */}
              {ended?.noShow && (
                <div className="csl-chat-wait">
                  <p>상담사가 응답하지 않았어요.</p>
                  <p className="csl-wait-sub">결제하신 포인트는 전액 환불되었어요.</p>
                  <button className="csl-wait-cancel" onClick={closeOverlay}>닫기</button>
                </div>
              )}

              {/* 종료 → 만족도 평가 + 요약 PDF 동의 팝업(요건 ⑧) */}
              {ended && !ended.noShow && (
                <div className="csl-chat-end">
                  <p className="csl-end-title">상담이 종료되었어요.</p>
                  {active.role === "user" && (
                    <div className="csl-rate-box">
                      <p className="csl-rate-q">
                        {rated ? "평가해 주셔서 감사합니다!" : "상담은 어떠셨나요? 만족도를 평가해 주세요."}
                      </p>
                      <div className="csl-rate-stars" role="radiogroup" aria-label="만족도">
                        {[1, 2, 3, 4, 5].map((n) => (
                          <button
                            key={n}
                            className={`csl-rate-star ${n <= rated ? "on" : ""}`}
                            onClick={() => submitRating(n)}
                            disabled={!!rated}
                            aria-label={`${n}점`}
                          >
                            ★
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="csl-end-sub">대화 내용을 요약해 상담서(PDF)로 만들어 드릴까요?</p>
                  <div className="csl-end-actions">
                    <button className="csl-end-make" onClick={makeReport}>상담서 만들기</button>
                    <button className="csl-end-skip" onClick={closeOverlay}>
                      {rated || active.role !== "user" ? "닫기" : "안 할래요"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>,
          document.body
        )}
    </ConsultationContext.Provider>
  );
}
