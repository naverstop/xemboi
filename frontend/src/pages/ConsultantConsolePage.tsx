import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  consultantConsoleWsUrl,
  useMe,
  type ConsultationSession,
  type ConsultantAdmin,
} from "../api";
import { useConsultation } from "../components/ConsultationProvider";

/**
 * 상담사 콘솔 — 입점 상담사 전용.
 *
 * '영업 중' 토글 = 콘솔 WebSocket 연결(presence online + onDuty). 켜져 있는 동안 접수 요청을
 * 실시간 수신하고 사용자 목록에 '대기중'으로 표시된다. onDuty 인 동안 idle 자동로그아웃 예외(App).
 * 수락 시 같은 실시간 채팅 오버레이(ConsultationProvider)를 상담사 역할로 연다.
 */
export default function ConsultantConsolePage() {
  const me = useMe();
  const { openSession, setConsoleOnDuty } = useConsultation();
  const [profile, setProfile] = useState<ConsultantAdmin | null | undefined>(undefined); // undefined=로딩
  const [online, setOnline] = useState(false);
  const [requests, setRequests] = useState<ConsultationSession[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

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

  if (profile === undefined) return <div className="ccon-wrap">불러오는 중…</div>;
  if (!me || !profile)
    return (
      <div className="ccon-wrap">
        <h3>상담사 전용</h3>
        <p>입점 상담사 계정만 이용할 수 있어요. <Link to="/">홈으로</Link></p>
      </div>
    );

  const pending = requests.filter((r) => r.status === "requested");
  return (
    <div className="ccon-wrap">
      <div className="ccon-head">
        <h2>상담사 콘솔</h2>
        <label className="ccon-switch" title="영업 상태">
          <input type="checkbox" checked={online} onChange={(e) => setOnline(e.target.checked)} />
          <span className={online ? "on" : "off"}>{online ? "🟢 영업 중" : "⚪ 영업 종료"}</span>
        </label>
      </div>
      <p className="ccon-biz">
        {profile.business_name} · {profile.eff_price_p.toLocaleString()}P / {profile.eff_duration_min}분
      </p>
      {!online && (
        <p className="ccon-off">
          ‘영업 중’으로 켜면 접수 알림을 받고, 사용자 목록에 ‘대기중’으로 표시돼요. (영업 중엔 자동 로그아웃되지 않아요)
        </p>
      )}
      {online && (
        <div className="ccon-reqs">
          <h3>접수 대기 ({pending.length})</h3>
          {pending.length === 0 && <p className="ccon-empty">새 상담 요청을 기다리는 중이에요…</p>}
          {pending.map((s) => (
            <div key={s.id} className="ccon-req">
              <div>
                <b>새 상담 요청</b>
                <div className="ccon-req-sub">{s.price_p.toLocaleString()}P · {s.duration_min}분</div>
              </div>
              <div className="ccon-req-act">
                <button className="ccon-accept" onClick={() => accept(s)}>수락</button>
                <button className="ccon-decline" onClick={() => decline(s)}>거절</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
