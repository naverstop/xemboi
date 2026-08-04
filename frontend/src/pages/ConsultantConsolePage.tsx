import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  consultantConsoleWsUrl,
  useMe,
  type ConsultationSession,
  type ConsultationSlot,
  type ConsultantSelf,
  type ConsultantEarnings,
} from "../api";
import { useConsultation } from "../components/ConsultationProvider";
import ConsultantSettingsPage from "./ConsultantSettingsPage";

/**
 * 상담사 — 입점 상담사 전용 통합 화면(메뉴 1개). 상단 [접수]/[설정] 탭.
 *
 * 접수: '영업 중' 토글 = 콘솔 WebSocket 연결(presence online + onDuty). 켜져 있는 동안 접수 요청을
 * 실시간 수신하고 사용자 목록에 '대기중'으로 표시된다. onDuty 인 동안 idle 자동로그아웃 예외(App).
 * 수락 시 같은 실시간 채팅 오버레이(ConsultationProvider)를 상담사 역할로 연다.
 * 설정: 간판·요금·#키워드(ConsultantSettingsPage 임베드). 영업 상태는 탭과 무관하게 유지된다.
 */
export default function ConsultantConsolePage() {
  const me = useMe();
  const { openSession, setConsoleOnDuty } = useConsultation();
  const [profile, setProfile] = useState<ConsultantSelf | null | undefined>(undefined); // undefined=로딩
  const [online, setOnline] = useState(false);
  // 접수 반복 알림음(운영자 지시: 응답할 때까지) — 기본 ON, 상담사가 끌 수 있음
  const [soundOn, setSoundOn] = useState(() => localStorage.getItem("ccon_sound") !== "0");
  const audioCtxRef = useRef<AudioContext | null>(null);
  const [requests, setRequests] = useState<ConsultationSession[]>([]);
  const [tab, setTab] = useState<"console" | "reserve" | "earnings" | "settings">("console");
  const wsRef = useRef<WebSocket | null>(null);
  // 내 수익(정산 집계)
  const [earnings, setEarnings] = useState<ConsultantEarnings | null | undefined>(undefined);
  // A-2 예약 슬롯 관리
  const [slots, setSlots] = useState<ConsultationSlot[] | null>(null);
  const [slotAt, setSlotAt] = useState("");   // datetime-local
  const [slotErr, setSlotErr] = useState<string | null>(null);

  function loadSlots() {
    api.consultantSlots().then((r) => setSlots(r.items)).catch(() => setSlots([]));
  }
  useEffect(() => { if (tab === "reserve") loadSlots(); }, [tab]);

  useEffect(() => {
    if (tab !== "earnings") return;
    setEarnings(undefined);
    api.consultantEarnings().then(setEarnings).catch(() => setEarnings(null));
  }, [tab]);

  async function addSlot() {
    if (!slotAt) return;
    setSlotErr(null);
    try {
      await api.addConsultantSlot(new Date(slotAt).toISOString()); // 로컬 → UTC ISO
      setSlotAt("");
      loadSlots();
    } catch (e: any) {
      setSlotErr(e?.message || "예약 시간 등록에 실패했어요.");
    }
  }

  async function removeSlot(s: ConsultationSlot) {
    const msg = s.status === "booked"
      ? "이미 예약된 시간이에요. 취소하면 사용자에게 100% 환불되고 알림이 가요. 취소할까요?"
      : "이 예약 시간을 삭제할까요?";
    if (!window.confirm(msg)) return;
    try {
      await api.removeConsultantSlot(s.id);
      loadSlots();
    } catch (e: any) {
      alert(e?.message || "처리에 실패했어요.");
    }
  }

  useEffect(() => {
    api
      .myConsultantProfile()
      .then((r) => {
        setProfile(r.consultant);
        if (r.consultant) setOnline(r.consultant.presence !== "offline");
      })
      .catch(() => setProfile(null));
  }, []);

  // '영업 중' → 콘솔 WS 연결(presence online·onDuty). 끄면 해제(→offline).
  useEffect(() => {
    if (!online || !profile) return;
    let hb: ReturnType<typeof setInterval> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closedByUs = false;
    function connect() {
      const ws = new WebSocket(consultantConsoleWsUrl());
      wsRef.current = ws;
      ws.onopen = () => {
        setConsoleOnDuty(true);
        hb = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
        }, 25000);
      };
      ws.onmessage = (ev) => {
        let m: any;
        try { m = JSON.parse(ev.data); } catch { return; }
        if (m.type === "requests") setRequests(m.items || []);
        else if (m.type === "new_request" && m.session)
          setRequests((cur) => [m.session, ...cur.filter((x) => x.id !== m.session.id)]);
        else if (m.type === "session_ended" && m.session_id)  // 리퍼/종료 통지 → 접수함·재입장 카드에서 제거
          setRequests((cur) => cur.filter((x) => x.id !== m.session_id));
      };
      ws.onclose = () => {
        if (hb) clearInterval(hb);
        if (closedByUs) return;
        retry = setTimeout(connect, 2000); // 재연결
      };
    }
    connect();
    return () => {
      closedByUs = true;
      if (hb) clearInterval(hb);
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
      wsRef.current = null;
      setConsoleOnDuty(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, profile]);

  async function accept(s: ConsultationSession) {
    try {
      await api.acceptConsultation(s.id);
      openSession(s.id, "consultant");
      setRequests((cur) => cur.filter((x) => x.id !== s.id));
    } catch (e: any) {
      alert(e?.message || "수락에 실패했어요.");
    }
  }
  async function decline(s: ConsultationSession) {
    try {
      await api.declineConsultation(s.id);
      setRequests((cur) => cur.filter((x) => x.id !== s.id));
    } catch { /* ignore */ }
  }

  // 승인 후 첫 진입 온보딩(운영자 지시: 튜토리얼 수준 안내) — 1회만, 다시 보지 않음
  const [onboard, setOnboard] = useState(false);
  useEffect(() => {
    if (profile && localStorage.getItem("ccon_onboarded") !== "1") setOnboard(true);
  }, [profile?.id]);
  function closeOnboard() { localStorage.setItem("ccon_onboarded", "1"); setOnboard(false); }

  const pending = requests.filter((r) => r.status === "requested");
  // 진행 중(active) 세션 — 새로고침/크래시 후 재접속 시 콘솔이 pending(requested+active)을 다시 받으므로
  //   여기서 '재입장' 카드로 노출해 상담사가 진행 중 상담으로 즉시 복귀할 수 있게 한다(고객 방치 방지).
  const activeSessions = requests.filter((r) => r.status === "active");

  // 접수 대기 반복 알림 — pending이 있는 동안 15초마다 차임+음성+탭 제목 깜빡임.
  // 수락/거절/취소로 pending이 0이 되면 즉시 중지(운영자 요구: 응답할 때까지).
  // ⚠️ Rules of Hooks: 이 useEffect는 반드시 아래 조기 return(로딩/비상담사)보다 위에 있어야 한다.
  //   조기 return 아래에 두면 profile 로딩(undefined) 렌더에선 호출 안 되고 로드 후 렌더에선 호출되어
  //   hook 개수가 달라짐 → React #310(Rendered more hooks) → 트리 크래시(백지). chime/speakAlert는 함수선언(호이스팅)이라 참조 가능.
  useEffect(() => {
    const baseTitle = document.title.replace(/^🔔[^|]*\| /, "");
    if (!online || pending.length === 0) { document.title = baseTitle; return; }
    let flip = false;
    const ring = () => {
      if (soundOn) { chime(); speakAlert(); }
      flip = !flip;
      document.title = flip ? `🔔 새 상담 요청 (${pending.length}) | ${baseTitle}` : baseTitle;
    };
    ring();
    const iv = window.setInterval(ring, 15000);
    return () => {
      window.clearInterval(iv);
      document.title = baseTitle;
      try { window.speechSynthesis?.cancel(); } catch { /* noop */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, soundOn, pending.length]);

  if (profile === undefined) return <div className="ccon-wrap">불러오는 중…</div>;
  if (!me || !profile)
    return (
      <div className="ccon-wrap">
        <h3>상담사 전용</h3>
        <p>입점 상담사 계정만 이용할 수 있어요. <Link to="/">홈으로</Link></p>
      </div>
    );

  // 오디오 unlock — 브라우저 자동재생 정책상 사용자 제스처(영업 토글) 시점에 준비해야 이후 자동 재생 가능
  function unlockAudio() {
    try {
      if (!audioCtxRef.current) {
        const AC = window.AudioContext || (window as any).webkitAudioContext;
        audioCtxRef.current = new AC();
      }
      void audioCtxRef.current.resume();
      window.speechSynthesis?.getVoices();          // 보이스 목록 프라임(첫 발화 지연 방지)
    } catch { /* 미지원 브라우저 — 푸시/화면 알림으로 폴백 */ }
  }
  function chime() {                                 // 2음 차임(파일 불필요 — WebAudio 합성)
    const ctx = audioCtxRef.current;
    if (!ctx || ctx.state !== "running") return;
    const t = ctx.currentTime;
    [[880, 0], [1318.5, 0.18]].forEach(([f, dt]) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t + dt);
      g.gain.exponentialRampToValueAtTime(0.35, t + dt + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dt + 0.7);
      o.connect(g); g.connect(ctx.destination);
      o.start(t + dt); o.stop(t + dt + 0.8);
    });
  }
  function speakAlert() {                            // 음성 "상담이 들어왔어요"
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance("상담이 들어왔어요");
      u.lang = "ko-KR"; u.rate = 1.05; u.volume = 1;
      window.speechSynthesis.speak(u);
    } catch { /* 미지원 — 차임만 */ }
  }
  function toggleSound(on: boolean) {
    setSoundOn(on);
    localStorage.setItem("ccon_sound", on ? "1" : "0");
    if (on) { unlockAudio(); chime(); }              // 켜는 제스처로 즉시 unlock+확인음
  }
  // 영업 on/off — 즉시 DB persist(WS 연결과 독립). '토글=권위, 하트비트=liveness'.
  // WS는 online effect가 접수알림·하트비트용으로 별도 연결/해제. busy(상담중)면 서버가 세션 우선.
  function setBiz(next: boolean) {
    if (next) unlockAudio();
    setOnline(next);
    api.setConsultantAvailability(next).catch(() => { /* WS 연결로도 반영되므로 실패 무시 */ });
  }

  return (
    <div className="ccon-wrap">
      {onboard && (
        <div className="pwa-overlay" onClick={closeOnboard}>
          <div className="pwa-modal pwa-guide" onClick={(e) => e.stopPropagation()}>
            <h3>🎉 입점을 환영해요! 시작 가이드</h3>
            <ol className="pwa-steps">
              <li><span className="pwa-step-ic" aria-hidden>🖼️</span><span className="pwa-step-no" aria-hidden>1</span>
                <span className="pwa-step-tx"><b>간판·요금·설정</b> 탭에서 상담소 사진·소개·#키워드·요금(회당/분당/시간당)을 등록하세요. 사용자 목록 카드에 그대로 노출돼요.</span></li>
              <li><span className="pwa-step-ic" aria-hidden>📅</span><span className="pwa-step-no" aria-hidden>2</span>
                <span className="pwa-step-tx"><b>예약</b> 탭에서 상담 가능한 시간대를 등록하면 사용자가 예약할 수 있어요.</span></li>
              <li><span className="pwa-step-ic" aria-hidden>🟢</span><span className="pwa-step-no" aria-hidden>3</span>
                <span className="pwa-step-tx">우측 상단 <b>영업 중</b> 토글을 켜면 실시간 접수가 시작돼요. 새 요청은 수락/거절할 때까지 <b>소리·알림</b>으로 계속 알려드립니다.</span></li>
              <li><span className="pwa-step-ic" aria-hidden>📊</span><span className="pwa-step-no" aria-hidden>4</span>
                <span className="pwa-step-tx"><b>내 수익</b> 탭에서 건수·매출·실지급액을 확인하세요. 매월 <b>25일 마감 → 당월 마지막 영업일</b>에 등록 계좌로 지급됩니다(원천징수 3.3% 공제).</span></li>
            </ol>
            <div className="pwa-actions"><button onClick={closeOnboard}>시작하기</button></div>
          </div>
        </div>
      )}
      <div className="ccon-head">
        {/* 영업 상태 — 크고 색상 있는 토글(녹=영업중·적=영업종료), 좌측. 클릭 즉시 DB 저장 */}
        <button
          type="button"
          role="switch"
          aria-checked={online}
          className={`ccon-biz-switch ${online ? "on" : "off"}`}
          onClick={() => setBiz(!online)}
          title="영업 상태 — 켜면 실시간 접수 시작(즉시 저장)"
        >
          <span className="ccon-biz-track" aria-hidden><span className="ccon-biz-knob" /></span>
          <span className="ccon-biz-txt">{online ? "영업 중" : "영업 종료"}</span>
        </button>
        <label className="ccon-switch ccon-sound" title="접수 알림음 — 켜 두면 새 요청이 응답될 때까지 15초마다 소리·음성으로 알려드려요">
          <input type="checkbox" checked={soundOn} onChange={(e) => toggleSound(e.target.checked)} />
          <span className={soundOn ? "on" : "off"}>{soundOn ? "🔔 알림음" : "🔕 무음"}</span>
        </label>
      </div>

      <div className="ccon-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "console"}
          className={`ccon-tab ${tab === "console" ? "active" : ""}`} onClick={() => setTab("console")}>
          접수{online && pending.length > 0 ? ` (${pending.length})` : ""}
        </button>
        <button role="tab" aria-selected={tab === "reserve"}
          className={`ccon-tab ${tab === "reserve" ? "active" : ""}`} onClick={() => setTab("reserve")}>
          예약
        </button>
        <button role="tab" aria-selected={tab === "earnings"}
          className={`ccon-tab ${tab === "earnings" ? "active" : ""}`} onClick={() => setTab("earnings")}>
          내 수익
        </button>
        <button role="tab" aria-selected={tab === "settings"}
          className={`ccon-tab ${tab === "settings" ? "active" : ""}`} onClick={() => setTab("settings")}>
          간판·요금·설정
        </button>
      </div>

      {tab === "console" ? (
        <>
          <p className="ccon-biz">
            {profile.business_name} · {profile.eff_price_p.toLocaleString()}P / {profile.eff_duration_min}분
          </p>
          {!online && (
            <p className="ccon-off">
              ‘영업 중’으로 켜면 접수 알림을 받고, 사용자 목록에 ‘대기중’으로 표시돼요. (영업 중엔 자동 로그아웃되지 않아요)
            </p>
          )}
          {activeSessions.length > 0 && (
            <div className="ccon-reqs ccon-active-reqs">
              <h3>진행 중 상담 ({activeSessions.length})</h3>
              {activeSessions.map((s) => (
                <div key={s.id} className="ccon-req ccon-req-active">
                  <div>
                    <b>진행 중인 상담</b>
                    <div className="ccon-req-sub">
                      {s.price_p.toLocaleString()}P · {s.duration_min}분
                      {(s.extended_min ?? 0) > 0 ? ` (+${s.extended_min}분 연장)` : ""}
                    </div>
                    <div className="ccon-req-sub">고객이 대기 중일 수 있어요. 바로 이어서 응대하세요.</div>
                  </div>
                  <div className="ccon-req-act">
                    <button className="ccon-accept" onClick={() => openSession(s.id, "consultant")}>재입장</button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {online && (
            <div className="ccon-reqs">
              <h3>접수 대기 ({pending.length})</h3>
              {pending.length === 0 && <p className="ccon-empty">새 상담 요청을 기다리는 중이에요…</p>}
              {pending.map((s) => (
                <div key={s.id} className="ccon-req">
                  <div>
                    <b>새 상담 요청</b>
                    {/* A-1: 명식/카드 첨부 표시 — 수락 시 채팅방 상단에서 바로 볼 수 있음 */}
                    {s.source_kind && (
                      <span className="ccon-req-ctx">
                        {s.source_kind === "saju" ? "📜 사주 명식 첨부" : "🃏 타로 카드 첨부"}
                      </span>
                    )}
                    <div className="ccon-req-sub">{s.price_p.toLocaleString()}P · {s.duration_min}분</div>
                    {/* 수락 전에도 첨부 내용을 미리 확인(운영자 요청) — 타로: 질문+카드 목록, 사주: 생년 요약 */}
                    {s.source_kind === "tarot" && (s.source_context?.cards?.length ?? 0) > 0 && (
                      <div className="ccon-req-cards">
                        {s.source_context?.question && (
                          <div className="ccon-req-q">“{s.source_context.question}”</div>
                        )}
                        <ul>
                          {(s.source_context?.cards ?? []).map((c) => (
                            <li key={c.position_index}>
                              <em>{c.position_index + 1}. {c.position_name}</em> {c.name_kr}
                              {c.orientation === "reversed" && <i className="ccon-rev"> 역방향</i>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {s.source_kind === "saju" && s.source_context?.birth_date && (
                      <div className="ccon-req-cards">
                        <div className="ccon-req-q">
                          {s.source_context.birth_date}
                          {s.source_context.birth_time ? ` ${s.source_context.birth_time}` : ""}
                          {s.source_context.calendar === "lunar" ? " · 음력" : " · 양력"}
                          {s.source_context.gender === "male" ? " · 남" : s.source_context.gender === "female" ? " · 여" : ""}
                          {" — 명식은 수락 후 채팅방 상단에서 확인"}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="ccon-req-act">
                    <button className="ccon-accept" onClick={() => accept(s)}>수락</button>
                    <button className="ccon-decline" onClick={() => decline(s)}>거절</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : tab === "reserve" ? (
        <div className="ccon-reserve">
          <p className="ccon-biz">예약 가능한 시간을 열어두면, 부재중에도 사용자가 예약(선결제)할 수 있어요.
            시간이 되면 자동으로 접수가 생성되고 알림이 와요.</p>
          <div className="ccon-slot-add">
            <input
              type="datetime-local"
              value={slotAt}
              onChange={(e) => setSlotAt(e.target.value)}
              min={new Date(Date.now() + 3600000).toISOString().slice(0, 16)}
            />
            <button className="ccon-accept" onClick={addSlot} disabled={!slotAt}>시간 열기</button>
          </div>
          {slotErr && <p className="csl-consent-err">{slotErr}</p>}
          {slots == null && <p className="ccon-empty">불러오는 중…</p>}
          {slots != null && slots.length === 0 && <p className="ccon-empty">등록된 예약 시간이 없어요.</p>}
          {slots != null && slots.length > 0 && (
            <div className="ccon-slots">
              {slots.map((s) => (
                <div key={s.id} className={`ccon-slot st-${s.status}`}>
                  <span className="t">{new Date(s.start_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" })}</span>
                  <span className="st">
                    {s.status === "open" ? "열림" : s.status === "booked" ? `예약됨 (${s.charged_p.toLocaleString()}P 홀드)` :
                     s.status === "converted" ? "진행됨" : "취소됨"}
                  </span>
                  {(s.status === "open" || s.status === "booked") && (
                    <button className="ccon-decline" onClick={() => removeSlot(s)}>
                      {s.status === "booked" ? "예약 취소" : "삭제"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : tab === "earnings" ? (
        <div className="ccon-earn">
          {earnings === undefined && <p className="ccon-empty">불러오는 중…</p>}
          {earnings === null && <p className="ccon-empty">수익 정보를 불러오지 못했어요.</p>}
          {earnings && (
            <>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "8px 0 16px" }}>
                <div style={{ flex: "1 1 160px", padding: "14px 16px", borderRadius: 12, background: "var(--surface-2, #f5f3ee)" }}>
                  <div style={{ fontSize: 13, opacity: 0.7 }}>지급 예정(현재)</div>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>{earnings.payout_pending_p.toLocaleString()}P</div>
                </div>
                <div style={{ flex: "1 1 160px", padding: "14px 16px", borderRadius: 12, background: "var(--surface-2, #f5f3ee)" }}>
                  <div style={{ fontSize: 13, opacity: 0.7 }}>지급 완료 누계</div>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>{earnings.payout_settled_p.toLocaleString()}P</div>
                </div>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", padding: "8px 6px", opacity: 0.7 }}>기간</th>
                    <th style={{ textAlign: "right", padding: "8px 6px", opacity: 0.7 }}>상담 건수</th>
                    <th style={{ textAlign: "right", padding: "8px 6px", opacity: 0.7 }}>매출</th>
                    <th style={{ textAlign: "right", padding: "8px 6px", opacity: 0.7 }}>수익(실지급)</th>
                  </tr>
                </thead>
                <tbody>
                  {([["오늘", earnings.today], ["이번 달", earnings.month], ["올해", earnings.year], ["전체", earnings.total]] as const).map(
                    ([label, p]) => (
                      <tr key={label} style={{ borderTop: "1px solid var(--border, #e5e1d8)" }}>
                        <td style={{ padding: "10px 6px", fontWeight: label === "전체" ? 700 : 400 }}>{label}</td>
                        <td style={{ padding: "10px 6px", textAlign: "right" }}>{p.count.toLocaleString()}건</td>
                        <td style={{ padding: "10px 6px", textAlign: "right" }}>{p.revenue_p.toLocaleString()}P</td>
                        <td style={{ padding: "10px 6px", textAlign: "right", fontWeight: 600 }}>{p.payout_p.toLocaleString()}P</td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
              <p className="ccon-off" style={{ marginTop: 14 }}>
                ‘수익(실지급)’은 매출에서 플랫폼 수수료와 원천징수(3.3%)를 뺀 실수령 예정액이에요.
                실제 지급은 정산 주기에 따라 별도로 이뤄집니다. (기준: 한국시간)
              </p>
            </>
          )}
        </div>
      ) : (
        <ConsultantSettingsPage embedded />
      )}
    </div>
  );
}
