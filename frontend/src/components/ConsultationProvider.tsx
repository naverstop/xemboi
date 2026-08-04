import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  api,
  consultationSessionWsUrl,
  useMe,
  type ConsultationSession,
  type ConsultationChatMessage,
  type ConsultationStatus,
  type ConsultSource,
} from "../api";
import SajuChart, { type Chart } from "./SajuChart";
import { speak, primeTTS } from "../lib/tts";

/**
 * 1:1 상담 실시간 채팅 — 전역 프로바이더.
 *
 * 활성 세션의 WebSocket 연결·상태를 앱 최상단에서 보유하고, 채팅 오버레이를 Portal 로 띄운다.
 * 라우팅이 바뀌어도 유지되며(요건 9), 서버 카운트다운(요건 7)·종료 시 요약 PDF 동의 팝업(요건 8)을 포함.
 * onDuty(상담 중이거나 상담사 콘솔 접속 중)는 App 의 idle 자동로그아웃 예외에 사용.
 */

type Role = "user" | "consultant";

const MAX_REQUEST_ATTEMPTS = 3;  // 즉시 상담 미응답(no_show) 시 사용자 수동 재요청 상한(차감 보류라 돈 위험 없음)

type Ctx = {
  /** 사용자: 동의 후 상담 요청 → 대기/채팅 오버레이 오픈. source=A-1 명식/타로 자동 전달 */
  startRequest: (consultantId: number, consent: boolean, source?: ConsultSource | null) => Promise<void>;
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

/** A-1: 접수 시 전달된 소스 컨텍스트(사주 명식/타로 카드) 패널 — 상담사가 중복 질문 없이 바로 봄. */
function ConsultContextPanel({
  role,
  kind,
  ctx,
}: {
  role: Role;
  kind: "saju" | "tarot" | "birth";
  ctx: NonNullable<ConsultationSession["source_context"]>;
}) {
  const [open, setOpen] = useState(role === "consultant"); // 상담사=펼침, 사용자=접힘(전달 확인용)
  const genderKo = ctx.gender === "female" ? "여" : ctx.gender === "male" ? "남" : "미상";
  // 출산 택일(birth): 부모 라벨 — 성별로 아빠/엄마 구분(동성·미상은 부모①/② 폴백)
  const p2 = kind === "birth" ? ctx.parent2 : null;
  const roleLabel = (g?: string | null, idx?: number) =>
    g === "male" ? "아빠" : g === "female" ? "엄마" : `부모 ${idx === 2 ? "②" : "①"}`;
  return (
    <div className={`csl-ctx ${open ? "open" : ""}`}>
      <button type="button" className="csl-ctx-toggle" onClick={() => setOpen((v) => !v)}>
        <span className="csl-ctx-title">
          {kind === "tarot" ? "🃏 전달된 타로 카드"
            : kind === "birth" ? "👶 전달된 부모님 사주 명식 (출산 택일)"
            : "📜 전달된 사주 명식"}
        </span>
        {role === "user" && <span className="csl-ctx-hint">상담사에게 전달됨</span>}
        <span className="csl-ctx-arrow" aria-hidden>{open ? "▾" : "▸"}</span>
      </button>
      {open && kind === "saju" && !!ctx.chart && (
        <div className="csl-ctx-body">
          <div className="csl-ctx-meta">
            {ctx.birth_date} {ctx.birth_time || "시 모름"} · {ctx.calendar === "lunar" ? "음력" : "양력"} · {genderKo}
          </div>
          <SajuChart chart={ctx.chart as Chart} />
        </div>
      )}
      {open && kind === "birth" && !!ctx.chart && (
        <div className="csl-ctx-body">
          <div className="csl-ctx-meta">
            <b>{roleLabel(ctx.gender, 1)}</b> · {ctx.birth_date} {ctx.birth_time || "시 모름"} ·{" "}
            {ctx.calendar === "lunar" ? "음력" : "양력"} · {genderKo}
          </div>
          <SajuChart chart={ctx.chart as Chart} />
          {!!p2?.chart && (
            <>
              <div className="csl-ctx-meta" style={{ marginTop: 10 }}>
                <b>{roleLabel(p2.gender, 2)}</b> · {p2.birth_date} {p2.birth_time || "시 모름"} ·{" "}
                {p2.calendar === "lunar" ? "음력" : "양력"} · {p2.gender === "female" ? "여" : p2.gender === "male" ? "남" : "미상"}
              </div>
              <SajuChart chart={p2.chart as Chart} />
            </>
          )}
        </div>
      )}
      {open && kind === "tarot" && !!ctx.cards?.length && (
        <div className="csl-ctx-body">
          {ctx.question && <div className="csl-ctx-meta">질문: {ctx.question}</div>}
          <div className="csl-ctx-cards">
            {ctx.cards.map((c) => (
              <div key={c.position_index} className={`csl-ctx-card ${c.orientation === "reversed" ? "rev" : ""}`}>
                <span className="pos">{c.position_name}</span>
                <span className="nm">{c.name_kr}{c.orientation === "reversed" ? " · 역방향" : ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ConsultationProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<{ sessionId: string; role: Role } | null>(null);
  const [session, setSession] = useState<ConsultationSession | null>(null);
  const [messages, setMessages] = useState<ConsultationChatMessage[]>([]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [status, setStatus] = useState<ConsultationStatus | null>(null);
  const [warned, setWarned] = useState(false);
  const [ended, setEnded] = useState<{ reason?: string; noShow?: boolean; reserved?: boolean; attempt?: number; canRetry?: boolean; exhausted?: boolean } | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [consoleOnDuty, setConsoleOnDuty] = useState(false);
  const [draft, setDraft] = useState("");
  const [rated, setRated] = useState(0); // 종료 후 제출한 만족도(1~5), 0=미제출
  const socketRef = useRef<WebSocket | null>(null);
  const endedRef = useRef(false);
  const me = useMe();
  const resumeCheckedRef = useRef<string | null>(null);
  const announcedActiveRef = useRef(false);  // 입장 안내(TTS·시스템 메시지) 1회만
  const sessionRef = useRef<ConsultationSession | null>(null);  // WS 콜백 클로저 stale 방지(예약 여부 판정용)
  const lastReqRef = useRef<{ consultantId: number; source?: ConsultSource | null } | null>(null);  // 재요청용 마지막 신청 파라미터
  const attemptsRef = useRef(0);  // 현재 상담사 상대 누적 요청 횟수(no_show 재요청 카운트)

  // 상담 연결(active) 순간 입장 안내 — 음성(여성) + 시스템 메시지. 역할별 멘트. 세션당 1회.
  useEffect(() => {
    if (status !== "active" || !active || announcedActiveRef.current) return;
    announcedActiveRef.current = true;
    const line = active.role === "consultant"
      ? "상담이 연결되었습니다. 상담을 시작할게요."
      : "상담사가 입장하였습니다. 상담을 시작할게요.";
    speak(line);
    setMessages((cur) =>
      cur.some((x) => x.sender === "system" && x.content === line)
        ? cur
        : [...cur, { id: Date.now() + Math.random(), sender: "system", content: line, created_at: new Date().toISOString() }]
    );
  }, [status, active]);

  useEffect(() => { sessionRef.current = session; }, [session]);  // WS 콜백에서 최신 세션(예약 여부) 참조

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
          case "no_show": {
            endedRef.current = true; setStatus("no_show");
            const reserved = !!sessionRef.current?.reservation_id;  // 예약(선결제)=전액환불 / 즉시=무청구(차감 보류)
            const canRetry = !reserved && attemptsRef.current < MAX_REQUEST_ATTEMPTS;
            setEnded({ noShow: true, reserved, attempt: attemptsRef.current, canRetry, exhausted: !reserved && !canRetry });
            break;
          }
        }
      };
      ws.onclose = (ev) => {
        if (closedByUs || endedRef.current) return;
        // 인증/권한 거부(4401 만료·무효 토큰, 4403 비참여자·프록시 매핑)는 재연결해도 실패 —
        // 무한 재연결을 멈추고 종료 처리(1011 등 일시 중단만 재연결).
        if (ev.code === 4401 || ev.code === 4403) {
          endedRef.current = true;
          setEnded({ reason: "closed" });
          return;
        }
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

  // 진행 중 상담에서 창(탭)을 닫으려 하면 경고 — 유료 세션 유실 방지 + 개인정보 파기 정책 환기(요청).
  // (브라우저는 표준상 커스텀 문구를 표시하지 않고 기본 확인창을 띄운다.)
  useEffect(() => {
    if (!active || endedRef.current) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [active]);

  function reset() {
    endedRef.current = false;
    announcedActiveRef.current = false;
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
    primeTTS();  // 수락 클릭(제스처) 시점에 음성 프라임 → 입장 안내 자동재생 허용
    setActive({ sessionId, role });
  }

  async function _doRequest(consultantId: number, consent: boolean, source?: ConsultSource | null) {
    primeTTS();  // 신청/재요청 클릭(제스처) 시점에 음성 프라임
    const s = await api.requestConsultation(consultantId, consent, source ?? undefined);
    reset();
    setSession(s); setStatus(s.status);
    setActive({ sessionId: s.id, role: "user" });
  }

  async function startRequest(consultantId: number, consent: boolean, source?: ConsultSource | null) {
    lastReqRef.current = { consultantId, source: source ?? null };
    attemptsRef.current = 1;  // 최초 요청 = 1회차
    await _doRequest(consultantId, consent, source);
  }

  // 즉시 상담 미응답(no_show) 후 사용자 수동 재요청 — 최대 MAX_REQUEST_ATTEMPTS 회. 차감 보류라 돈 위험 없음.
  async function retryRequest() {
    const info = lastReqRef.current;
    if (!info || retrying) return;
    setRetrying(true);
    attemptsRef.current += 1;
    try {
      await _doRequest(info.consultantId, true, info.source);
    } catch {
      setEnded({ noShow: true, reserved: false, attempt: attemptsRef.current, canRetry: false, exhausted: true });
    } finally {
      setRetrying(false);
    }
  }

  function closeOverlay() {
    attemptsRef.current = 0;       // 재요청 카운터·마지막 신청 정보 초기화(다음 상담은 새 카운트)
    lastReqRef.current = null;
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
    if (!active || !session) return;
    // 금액 고지·확인 없이 즉시 차감되던 것을 방지 — 추가 차감액을 명시하고 확인받은 뒤 연장(오클릭 오차감 차단).
    const price = session.price_p;
    const bal = me?.balance;
    if (bal != null && bal < price) {
      alert(`연장하려면 ${price.toLocaleString()}P가 필요해요. (보유 ${bal.toLocaleString()}P)\n포인트를 충전한 뒤 다시 시도해 주세요.`);
      return;
    }
    const ok = window.confirm(
      `상담을 ${session.duration_min}분 연장할까요?\n\n${price.toLocaleString()}P가 추가로 차감돼요.` +
      (bal != null ? `\n(연장 후 예상 잔액 ${(bal - price).toLocaleString()}P)` : "")
    );
    if (!ok) return;
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
                  <p className="csl-wait-sub">
                    상담사가 수락하면 채팅이 시작돼요.{" "}
                    {session?.reservation_id ? "(미응답 시 자동 취소·전액 환불)" : "(미응답 시 자동 취소 · 요금은 미청구)"}
                  </p>
                  <button className="csl-wait-cancel" onClick={cancelWaiting}>요청 취소</button>
                </div>
              )}

              {/* 진행 중 채팅 */}
              {status === "active" && (
                <>
                  {/* A-1: 접수 시 전달된 사주 명식/타로 카드 — 상담사는 펼침, 사용자는 접힘 기본 */}
                  {session?.source_kind && session?.source_context && (
                    <ConsultContextPanel
                      role={active.role}
                      kind={session.source_kind}
                      ctx={session.source_context}
                    />
                  )}
                  <div className="csl-chat-body">
                    {messages.map((m) => (
                      <div key={m.id} className={`csl-bubble ${m.sender === active.role ? "mine" : "theirs"} ${m.sender === "system" ? "sys" : ""}`}>
                        {m.content}
                      </div>
                    ))}
                  </div>
                  {warned && session && (
                    <div className="csl-extend-bar">
                      <span>곧 상담 시간이 끝나요. 연장 시 <b>{session.price_p.toLocaleString()}P</b> 추가 차감 · {session.duration_min}분</span>
                      <button onClick={extend}>연장하기</button>
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

              {/* 노쇼(미응답) — 즉시상담: 무청구 + 사용자 수동 재요청(최대 3회) / 예약: 전액환불 */}
              {ended?.noShow && (
                <div className="csl-chat-wait">
                  <p>상담사가 응답하지 않았어요.</p>
                  <p className="csl-wait-sub">
                    {ended.reserved
                      ? "선결제하신 포인트는 전액 환불되었어요."
                      : "요금은 청구되지 않았어요. (상담사 수락 시에만 차감돼요)"}
                  </p>
                  {ended.canRetry ? (
                    <>
                      <p className="csl-wait-sub">다시 요청해 볼까요? (지금까지 {ended.attempt}/{MAX_REQUEST_ATTEMPTS}회 시도)</p>
                      <div className="csl-consent-actions">
                        <button className="csl-consent-ok" onClick={retryRequest} disabled={retrying}>
                          {retrying ? "다시 요청 중…" : "다시 요청"}
                        </button>
                        <button className="csl-wait-cancel" onClick={closeOverlay}>닫기</button>
                      </div>
                    </>
                  ) : (
                    <>
                      {ended.exhausted && (
                        <p className="csl-wait-sub">
                          {MAX_REQUEST_ATTEMPTS}번 시도했지만 지금은 연결이 어려워요. 예약을 하거나 다른 상담사를 선택해 주세요.
                        </p>
                      )}
                      <button className="csl-wait-cancel" onClick={closeOverlay}>닫기</button>
                    </>
                  )}
                </div>
              )}

              {/* 종료 → 만족도 평가 + 요약 PDF 동의 팝업(요건 ⑧) */}
              {ended && !ended.noShow && (
                <div className="csl-chat-end">
                  <p className="csl-end-title">상담이 종료되었어요.</p>
                  <p className="csl-end-privacy" style={{ fontSize: 12.5, lineHeight: 1.5, opacity: 0.75, margin: "2px 0 8px" }}>
                    🔒 상담 대화·사주 명식 등 개인정보는 <b>개인정보보호법</b>에 따라 안전하게 처리되며,
                    약관에 따라 <b>상담 종료 후 7일이 지나면 자동·완전 파기</b>됩니다. 회원 탈퇴 시에는 즉시 파기됩니다.
                  </p>
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
                  <p className="csl-end-sub">대화를 요약한 상담서(PDF)를 신청자·상담사가 <b>함께</b> 열람할 수 있어요.</p>
                  <div className="csl-end-actions">
                    <button className="csl-end-make" onClick={makeReport}>상담서 보기</button>
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
