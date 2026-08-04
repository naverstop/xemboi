import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, useMe, type ConsultantPublic, type ConsultationConfig, type ConsultSource, type ConsultationSlot } from "../api";
import { useCharge } from "./ChargeModal";

/** UTC ISO → "7/9(수) 14:30" 로컬 표기 */
function fmtSlot(iso: string): string {
  const d = new Date(iso);
  const day = "일월화수목금토"[d.getDay()];
  return `${d.getMonth() + 1}/${d.getDate()}(${day}) ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
import { useConsultation } from "./ConsultationProvider";

/**
 * 1:1 상담 진입 오버레이 — 분야 탭(전체/사주/타로) + 입점 상담사 카드 리스트 → 동의 후 상담 요청.
 *
 * 한 화면 통합(홍카페형): 상단 분야 필터 탭 아래로 세로 4:5 간판 카드(코너 분야배지·상태배지·#키워드·
 * 요금·만족도·CTA)를 노출한다. '입점예정(coming_soon)' 상담사는 간판 위 오버레이 + 신청 비활성.
 * 시스템 위 별도 오버레이라 하부 라우팅에 영향 없음(요건 9). "상담 신청" → 대화 저장·7일 파기 고지
 * 동의 게이트 → startRequest → 실시간 채팅(ConsultationProvider).
 */

type Cat = "all" | "saju" | "tarot";

const CATS: { key: Cat; label: string; ic: string }[] = [
  { key: "all", label: "전체", ic: "✨" },
  { key: "saju", label: "사주", ic: "🔮" },
  { key: "tarot", label: "타로", ic: "🃏" },
];

const PRESENCE: Record<string, { txt: string; cls: string }> = {
  online: { txt: "상담가능", cls: "on" },
  busy: { txt: "상담중", cls: "busy" },
  offline: { txt: "오프라인", cls: "off" },
};

const SPEC: Record<string, { txt: string; cls: string }> = {
  saju: { txt: "사주", cls: "saju" },
  tarot: { txt: "타로", cls: "tarot" },
  both: { txt: "사주+타로", cls: "both" },
};

function priceLabel(c: ConsultantPublic): { main: string; sub: string } {
  if (c.price_unit === "minute" && c.per_min_p)
    return { main: `분당 ${c.per_min_p.toLocaleString()}P`, sub: `1회 ${c.price_p.toLocaleString()}P·${c.duration_min}분` };
  if (c.price_unit === "hour" && c.per_hour_p)
    return { main: `시간당 ${c.per_hour_p.toLocaleString()}P`, sub: `1회 ${c.price_p.toLocaleString()}P·${c.duration_min}분` };
  return { main: `${c.price_p.toLocaleString()}P`, sub: `${c.duration_min}분` };
}

// 오늘(KST) 영업시간 안내. 미설정=null(상시). 휴무=open:false.
function bizHoursToday(c: ConsultantPublic): { label: string; open: boolean } | null {
  const h = c.business_hours;
  if (!h || Object.keys(h).length === 0) return null;
  const kst = new Date(Date.now() + 9 * 3600000);   // UTC ms + 9h → KST 벽시계(UTC 필드로 읽음)
  const wd = (kst.getUTCDay() + 6) % 7;             // JS 0=일 → 파이썬 0=월 기준으로 변환
  const ent = h[String(wd)];
  if (!ent || !ent.open || !ent.close) return { label: "오늘 휴무", open: false };
  return { label: `오늘 ${ent.open}~${ent.close}`, open: true };
}

type StatusKey = "all" | "online" | "busy" | "offline";
type SortKey = "recommended" | "available" | "rating" | "sessions" | "price";

const STATUS_CHIPS: { key: StatusKey; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "online", label: "상담가능" },
  { key: "busy", label: "상담중" },
  { key: "offline", label: "오프라인" },
];
const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "recommended", label: "추천순" },
  { key: "available", label: "상담가능 먼저" },
  { key: "rating", label: "만족도순" },
  { key: "sessions", label: "상담많은순" },
  { key: "price", label: "낮은가격순" },
];
const PRESENCE_RANK: Record<string, number> = { online: 0, busy: 1, offline: 2 };

/** 검색어(이름·#키워드·소개) 필터 + 상태 필터 + 정렬. 입점예정(coming_soon)은 항상 하단. */
function filterAndSort(items: ConsultantPublic[], q: string, status: StatusKey, sort: SortKey): ConsultantPublic[] {
  const query = q.trim().toLowerCase();
  const filtered = items.filter((c) => {
    if (status !== "all" && c.presence !== status) return false;
    if (query) {
      const hay = [c.business_name, c.intro || "", ...(c.keywords || [])].join(" ").toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });
  const coming = (c: ConsultantPublic) => (c.status === "coming_soon" ? 1 : 0);
  return [...filtered].sort((a, b) => {
    const cr = coming(a) - coming(b); // 입점예정은 항상 뒤로
    if (cr) return cr;
    switch (sort) {
      case "available": return (PRESENCE_RANK[a.presence] ?? 3) - (PRESENCE_RANK[b.presence] ?? 3);
      case "rating": return (b.rating_avg ?? -1) - (a.rating_avg ?? -1);
      case "sessions": return b.session_count - a.session_count;
      case "price": return a.price_p - b.price_p;
      default: return 0; // 추천순: 서버 정렬(추천/노출순) 유지(stable sort)
    }
  });
}

export default function ConsultationOverlay({
  open,
  onClose,
  source,
}: {
  open: boolean;
  onClose: () => void;
  /** A-1: 사주 명식/타로 카드를 상담사에게 자동 전달할 소스(사주·타로 화면 CTA 진입 시) */
  source?: ConsultSource | null;
}) {
  const { startRequest } = useConsultation();
  const me = useMe();
  const { openCharge } = useCharge();
  const navigate = useNavigate();
  const [cat, setCat] = useState<Cat>("all");
  const [items, setItems] = useState<ConsultantPublic[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState<ConsultantPublic | null>(null); // 동의 게이트 대상
  const [cfg, setCfg] = useState<ConsultationConfig | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [q, setQ] = useState("");                          // 검색어(이름·#키워드·소개)
  const [statusFilter, setStatusFilter] = useState<StatusKey>("all");  // 상태 빠른필터
  const [sortBy, setSortBy] = useState<SortKey>("recommended");        // 정렬
  // A-2 예약 상담
  const [reservePending, setReservePending] = useState<ConsultantPublic | null>(null); // 슬롯 선택 대상
  const [slots, setSlots] = useState<ConsultationSlot[] | null>(null);
  const [pickedSlot, setPickedSlot] = useState<ConsultationSlot | null>(null);          // 동의 게이트
  const [reserving, setReserving] = useState(false);
  const [reserveDone, setReserveDone] = useState<ConsultationSlot | null>(null);
  const [myRes, setMyRes] = useState<ConsultationSlot[] | null>(null);
  // A-1 소스 → 상담사 분야 매핑: 출산 택일(birth)은 사주 상담사 분야로(양 부모 명식 전달).
  const srcCat = source?.kind ? (source.kind === "tarot" ? "tarot" : "saju") : undefined;

  function loadMyReservations() {
    api.myReservations().then((r) => setMyRes(r.items)).catch(() => setMyRes([]));
  }

  async function openReserve(c: ConsultantPublic) {
    setErr(null); setReservePending(c); setSlots(null); setPickedSlot(null); setReserveDone(null);
    try {
      const r = await api.consultantOpenSlots(c.id);
      setSlots(r.items);
    } catch (e: any) {
      setErr(e?.message || "예약 시간을 불러오지 못했어요.");
      setSlots([]);
    }
  }

  async function confirmReserve() {
    if (!pickedSlot) return;
    setReserving(true); setErr(null);
    try {
      const s = await api.reserveSlot(pickedSlot.id, true);
      setReserveDone(s);
      setPickedSlot(null);
      loadMyReservations();
    } catch (e: any) {
      setErr(e?.message || "예약에 실패했어요.");
    } finally {
      setReserving(false);
    }
  }

  async function cancelMyReservation(s: ConsultationSlot) {
    const full = cfg?.reserve_full_refund_hours ?? 24;
    const pct = cfg?.reserve_late_refund_pct ?? 50;
    const hoursLeft = (new Date(s.start_at).getTime() - Date.now()) / 3600000;
    const note = hoursLeft >= full ? "지금 취소하면 100% 환불돼요." : `시작 ${full}시간 이내라 ${pct}%만 환불돼요.`;
    if (!window.confirm(`${fmtSlot(s.start_at)} 예약을 취소할까요?\n${note}`)) return;
    try {
      const r = await api.cancelReservation(s.id);
      alert(`예약이 취소되었어요. (환불 ${r.refund_p.toLocaleString()}P)`);
      loadMyReservations();
    } catch (e: any) {
      alert(e?.message || "취소에 실패했어요.");
    }
  }

  useEffect(() => {
    if (!open) {
      setCat("all"); setItems(null); setErr(null); setPending(null);
      setQ(""); setStatusFilter("all"); setSortBy("recommended");
      setReservePending(null); setSlots(null); setPickedSlot(null); setReserveDone(null);
    } else {
      // A-1 소스 진입(타로 카드/사주 명식 전달): 해당 분야 상담사만 — 타로 카드를 들고 왔는데
      // 사주·전체 상담사가 섞여 나오면 안 된다(운영자 지시). 탭도 잠근다(아래 렌더 분기).
      setCat((srcCat as Cat | undefined) ?? "all");
      if (!cfg) api.consultationConfig().then(setCfg).catch(() => {});
      loadMyReservations(); // A-2 내 예약
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, source?.kind]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true); setErr(null); setItems(null);
    // 소스 진입이면 분야를 직접 고정 — 첫 커밋에서 cat 이 아직 'all'인 채 무필터 조회가
    // 한 번 새어 나가는 것(다른 분야 상담사 노출 위험) 자체를 차단한다.
    const eff = (srcCat as Cat | undefined) ?? cat;
    api.consultants(eff === "all" ? undefined : eff)
      .then((r) => { if (alive) setItems(r.items); })
      .catch((e) => { if (alive) setErr(e?.message || "상담사 목록을 불러오지 못했어요."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [cat, open, source?.kind]);

  // presence 실시간화(핵심): 오버레이가 열려 있는 동안 상담사 목록을 15초 주기로 조용히 재조회해
  // 상담사의 '영업중/부재중' 전환을 사용자 화면에 반영한다(스피너 없이 items만 교체). 백그라운드
  // 탭은 중지하고 복귀 시 즉시 1회 갱신. — '영업중인데 부재중' 지배 원인(1회 fetch) 해소.
  useEffect(() => {
    if (!open) return;
    const eff = (srcCat as Cat | undefined) ?? cat;
    const spec = eff === "all" ? undefined : eff;
    let alive = true;
    const refresh = () => {
      if (document.hidden) return;
      api.consultants(spec).then((r) => { if (alive) setItems(r.items); }).catch(() => { /* 폴링 실패 무시 */ });
    };
    const iv = window.setInterval(refresh, 15000);
    const onVis = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { alive = false; window.clearInterval(iv); document.removeEventListener("visibilitychange", onVis); };
  }, [cat, open, source?.kind]);

  async function confirmRequest() {
    if (!pending) return;
    setSubmitting(true); setErr(null);
    try {
      await startRequest(pending.id, true, source ?? undefined);
      setPending(null);
      onClose(); // 진입 오버레이 닫고 채팅 오버레이로 전환
    } catch (e: any) {
      setErr(e?.message || "상담 신청에 실패했어요.");
    } finally {
      setSubmitting(false);
    }
  }

  // 결제의지가 가장 높은 순간(신청/예약 확정)에 보유 포인트를 대조하고, 부족·미로그인 시 막다른 에러 대신
  // 즉시 충전/로그인 CTA를 노출한다. request_session/reserve 는 서버에서도 잔액을 사전거부(방어).
  const bal = me?.balance ?? 0;
  function payBlocked(price: number): boolean {
    return !me || bal < price;
  }
  function balanceGate(price: number, reason: string) {
    if (!me) {
      return (
        <div className="csl-bal-cta">
          <p className="csl-bal-need">로그인 후 이용할 수 있어요.</p>
          <button className="csl-bal-btn" onClick={() => { onClose(); navigate("/login"); }}>로그인하기</button>
        </div>
      );
    }
    const short = bal < price;
    return (
      <div className="csl-bal-cta">
        <p className={`csl-bal-line ${short ? "short" : ""}`}>
          보유 <b>{bal.toLocaleString()}P</b>
          {short && <span className="csl-bal-short"> · {(price - bal).toLocaleString()}P 부족</span>}
        </p>
        {short && <button className="csl-bal-btn" onClick={() => openCharge(reason)}>충전하기</button>}
      </div>
    );
  }

  if (!open) return null;

  return (
    <div className="pwa-overlay csl-ov" role="dialog" aria-modal="true" aria-label="1:1 상담" onClick={onClose}>
      <div className="pwa-modal csl-modal" onClick={(e) => e.stopPropagation()}>
        <button className="csl-x" onClick={onClose} aria-label="닫기">×</button>

        <div className="csl-head2">
          <h3 className="csl-title">1:1 상담</h3>
          <p className="csl-sub">마음 편히 이야기 나눌 상담사를 골라보세요.</p>
        </div>

        {/* A-2 내 예약 — 다가오는 예약 표시 + 취소 */}
        {myRes && myRes.length > 0 && (
          <div className="csl-myres">
            <div className="csl-myres-title">📅 내 예약</div>
            {myRes.map((s) => (
              <div key={s.id} className={`csl-myres-item st-${s.status}`}>
                <span className="t">{fmtSlot(s.start_at)}</span>
                <span className="n"><b className="csl-myres-who">{s.consultant_name || "상담사"}</b> 상담사에게 예약</span>
                <span className={`st st-${s.status}`}>{s.status === "booked" ? "✅ 접수됨" : "진행 중"}</span>
                {s.status === "booked" && (
                  <button className="x" onClick={() => cancelMyReservation(s)}>취소</button>
                )}
              </div>
            ))}
          </div>
        )}

        {source?.kind ? (
          /* A-1 소스 진입: 분야 잠금 — 타로 카드 진입이면 타로 상담사만, 사주 명식이면 사주 상담사만.
             탭을 숨겨 다른 분야로 새지 않게 하고, 무엇이 전달되는지 배너로 안내한다(운영자 지시). */
          <div className="csl-locked-cat" role="note">
            {source.kind === "tarot"
              ? <>🃏 방금 뽑은 <b>타로 카드가 상담사에게 그대로 전달</b>돼요 — <b>타로 상담사</b>만 보여드려요.</>
              : source.kind === "birth"
                ? <>👶 <b>부모님 두 분의 사주 명식이 상담사에게 그대로 전달</b>돼요 — <b>사주 상담사</b>만 보여드려요.</>
                : <>📜 내 <b>사주 명식이 상담사에게 그대로 전달</b>돼요 — <b>사주 상담사</b>만 보여드려요.</>}
          </div>
        ) : (
          <div className="csl-tabs" role="tablist">
            {CATS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={cat === t.key}
                className={`csl-tab ${cat === t.key ? "active" : ""}`}
                onClick={() => setCat(t.key)}
              >
                <span aria-hidden>{t.ic}</span> {t.label}
              </button>
            ))}
          </div>
        )}

        {items && items.length > 0 && (
          <div className="csl-controls">
            <div className="csl-search">
              <span className="csl-search-ic" aria-hidden>🔍</span>
              <input
                type="search"
                placeholder="상담사 이름·#키워드 검색"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="상담사 검색"
              />
            </div>
            <div className="csl-control-row">
              <div className="csl-chips" role="group" aria-label="상태 필터">
                {STATUS_CHIPS.map((s) => (
                  <button
                    key={s.key}
                    className={`csl-chip ${statusFilter === s.key ? "active" : ""}`}
                    aria-pressed={statusFilter === s.key}
                    onClick={() => setStatusFilter(s.key)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <select className="csl-sort" value={sortBy} aria-label="정렬"
                onChange={(e) => setSortBy(e.target.value as SortKey)}>
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        <div className="csl-list-wrap">
          {loading && <p className="csl-empty">불러오는 중…</p>}
          {err && <p className="csl-empty csl-err">{err}</p>}
          {items && items.length === 0 && !loading && (
            <p className="csl-empty">현재 이 분야의 상담사가 없어요.</p>
          )}
          {(() => {
            const visible = items ? filterAndSort(items, q, statusFilter, sortBy) : [];
            if (items && items.length > 0 && visible.length === 0 && !loading)
              return <p className="csl-empty">조건에 맞는 상담사가 없어요.</p>;
            return (
              <div className="csl-cards">
                {visible.map((c) => (
                  <ConsultantCard
                    key={c.id}
                    c={c}
                    onStart={() => { setErr(null); setPending(c); }}
                    onReserve={() => openReserve(c)}
                  />
                ))}
              </div>
            );
          })()}
        </div>
      </div>

      {/* 동의 게이트 — 대화 저장·7일 파기 고지 (입장 전 필수) */}
      {pending && (
        <div className="csl-consent-ov" onClick={(e) => { e.stopPropagation(); if (!submitting) setPending(null); }}>
          <div className="csl-consent" onClick={(e) => e.stopPropagation()}>
            <h4>{pending.business_name}</h4>
            <p className="csl-consent-price">
              {pending.price_p.toLocaleString()}P · {pending.duration_min}분 (신청 시 수락 후 차감)
            </p>
            {balanceGate(pending.price_p, `1:1 상담에는 ${pending.price_p.toLocaleString()}P가 필요해요. 충전하면 바로 신청할 수 있어요.`)}
            <p className="csl-consent-note">
              원활한 상담과 <b>상담서 발급</b>을 위해 대화 내용이 서버에 저장되며,
              <b> {cfg?.retention_days ?? 7}일 후 자동·완전 파기</b>됩니다. 동의하셔야 상담이 시작돼요.
            </p>
            {source && (
              <p className="csl-consent-note csl-consent-source">
                🔗 선택하신 <b>{source.kind === "saju" ? "사주 명식" : source.kind === "birth" ? "부모님 두 분의 사주 명식" : "타로 카드"}</b>
                {source.label ? ` (${source.label})` : ""} 정보가 상담사에게 함께 전달됩니다
                (같은 설명을 반복하지 않아도 돼요). 이 정보도 {cfg?.retention_days ?? 7}일 후 함께 파기됩니다.
              </p>
            )}
            {err && <p className="csl-consent-err">{err}</p>}
            <div className="csl-consent-actions">
              <button className="csl-consent-ok" onClick={confirmRequest} disabled={submitting || payBlocked(pending.price_p)}>
                {submitting ? "신청 중…" : payBlocked(pending.price_p) ? (me ? "포인트 부족" : "로그인 필요") : "동의하고 상담 신청"}
              </button>
              <button className="csl-consent-cancel" onClick={() => setPending(null)} disabled={submitting}>취소</button>
            </div>
          </div>
        </div>
      )}

      {/* A-2 예약 — 슬롯 선택 → 동의(선결제·취소정책) → 완료 */}
      {reservePending && (
        <div className="csl-consent-ov" onClick={(e) => { e.stopPropagation(); if (!reserving) { setReservePending(null); setPickedSlot(null); setReserveDone(null); } }}>
          <div className="csl-consent" onClick={(e) => e.stopPropagation()}>
            <h4>📅 {reservePending.business_name} 예약</h4>

            {reserveDone ? (
              <>
                <p className="csl-consent-note">
                  <b>{fmtSlot(reserveDone.start_at)}</b> 예약이 완료되었어요! 🎉<br />
                  시작 10분 전에 알림을 보내드리고, 시간이 되면 자동으로 상담이 접수돼요.
                  상담사가 응답하지 않으면 <b>전액 환불</b>됩니다.
                </p>
                <div className="csl-consent-actions">
                  <button className="csl-consent-ok" onClick={() => { setReservePending(null); setReserveDone(null); }}>확인</button>
                </div>
              </>
            ) : pickedSlot ? (
              <>
                <p className="csl-consent-price">
                  {fmtSlot(pickedSlot.start_at)} · {reservePending.price_p.toLocaleString()}P · {reservePending.duration_min}분
                </p>
                <p className="csl-consent-note">
                  예약 확정 시 <b>{reservePending.price_p.toLocaleString()}P가 바로 차감(홀드)</b>돼요.
                  시작 <b>{cfg?.reserve_full_refund_hours ?? 24}시간 전</b>까지 취소하면 100% 환불,
                  이후 취소는 <b>{cfg?.reserve_late_refund_pct ?? 50}%</b> 환불됩니다.
                  상담사 사정으로 취소되거나 응답하지 않으면 <b>전액 환불</b>돼요.
                </p>
                <p className="csl-consent-note">
                  대화 내용은 상담서 발급을 위해 저장되며 <b>{cfg?.retention_days ?? 7}일 후 자동·완전 파기</b>됩니다.
                </p>
                {balanceGate(reservePending.price_p, `예약(선결제)에는 ${reservePending.price_p.toLocaleString()}P가 필요해요. 충전하면 바로 예약할 수 있어요.`)}
                {err && <p className="csl-consent-err">{err}</p>}
                <div className="csl-consent-actions">
                  <button className="csl-consent-ok" onClick={confirmReserve} disabled={reserving || payBlocked(reservePending.price_p)}>
                    {reserving ? "예약 중…" : payBlocked(reservePending.price_p) ? (me ? "포인트 부족" : "로그인 필요") : "동의하고 예약 확정"}
                  </button>
                  <button className="csl-consent-cancel" onClick={() => setPickedSlot(null)} disabled={reserving}>뒤로</button>
                </div>
              </>
            ) : (
              <>
                <p className="csl-consent-note">원하는 시간을 골라주세요. (내 시간대 기준)</p>
                {slots == null && <p className="csl-consent-note">불러오는 중…</p>}
                {slots != null && slots.length === 0 && (
                  <p className="csl-consent-note">아직 열려 있는 예약 시간이 없어요. 상담사가 시간을 열면 여기에 표시돼요.</p>
                )}
                {slots != null && slots.length > 0 && (
                  <div className="csl-slots">
                    {slots.map((s) => (
                      <button key={s.id} className="csl-slot" onClick={() => { setErr(null); setPickedSlot(s); }}>
                        {fmtSlot(s.start_at)}
                      </button>
                    ))}
                  </div>
                )}
                {err && <p className="csl-consent-err">{err}</p>}
                <div className="csl-consent-actions">
                  <button className="csl-consent-cancel" onClick={() => setReservePending(null)}>닫기</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stars({ avg }: { avg: number }) {
  const r = Math.round(avg);
  return (
    <span className="csl-stars-ic" aria-hidden>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < r ? "on" : "off"}>★</span>
      ))}
    </span>
  );
}

function ConsultantCard({ c, onStart, onReserve }: { c: ConsultantPublic; onStart: () => void; onReserve: () => void }) {
  const p = PRESENCE[c.presence] || PRESENCE.offline;
  const spec = SPEC[c.specialty] || SPEC.saju;
  const isComing = c.status === "coming_soon";
  const canStart = c.presence === "online" && !isComing;
  const price = priceLabel(c);
  const biz = bizHoursToday(c);
  return (
    <div className={`csl-card ${isComing ? "coming" : ""}`}>
      <div className="csl-sign">
        {c.signboard_image_url ? (
          <img src={c.signboard_image_url} alt={c.business_name} loading="lazy" />
        ) : (
          <span className="csl-sign-ph" aria-hidden>🪧</span>
        )}
        <span className={`csl-spec-badge ${spec.cls}`}>{spec.txt}</span>
        {!isComing && <span className={`csl-badge ${p.cls}`}>{p.txt}</span>}
        {isComing && (
          <div className="csl-coming" aria-label="입점예정">
            <span className="csl-coming-ic" aria-hidden>⏳</span>
            <span className="csl-coming-tx">입점예정</span>
          </div>
        )}
      </div>
      <div className="csl-info">
        <div className="csl-card-top">
          <span className="csl-nm">{c.business_name}</span>
        </div>
        {c.intro && <p className="csl-intro">{c.intro}</p>}
        {c.keywords && c.keywords.length > 0 && (
          <div className="csl-keywords">
            {c.keywords.slice(0, 5).map((k) => (
              <span key={k} className="csl-kw">#{k}</span>
            ))}
          </div>
        )}
        <div className="csl-rating">
          {c.rating_avg != null ? (
            <span className="csl-stars" title={`만족도 ${c.rating_avg}/5 · ${c.rating_count}명 평가`}>
              <Stars avg={c.rating_avg} />
              <b>{c.rating_avg.toFixed(1)}</b>
              <span className="csl-rc">({c.rating_count})</span>
            </span>
          ) : (
            <span className="csl-norate">평가 없음</span>
          )}
          <span className="csl-dot" aria-hidden>·</span>
          <span className="csl-scount">상담 {c.session_count.toLocaleString()}건</span>
        </div>
        {biz && (
          <div className={`csl-bizhours ${biz.open ? "open" : "closed"}`}>
            <span aria-hidden>🕒</span> {biz.label}
          </div>
        )}
        <div className="csl-cta-row">
          {isComing ? (
            <span className="csl-price csl-price-soon">오픈 준비 중</span>
          ) : (
            <span className="csl-price-wrap">
              <span className="csl-price">{price.main}</span>
              <span className="csl-price-sub">{price.sub}</span>
            </span>
          )}
          <button className="csl-start" disabled={!canStart} onClick={onStart}>
            {isComing ? "입점예정" : c.presence === "busy" ? "상담중" : c.presence === "offline" ? "부재중" : "상담 신청"}
          </button>
          {/* A-2: 부재중·상담중이어도 예약은 가능 */}
          {!isComing && (
            <button className="csl-reserve" onClick={onReserve}>📅 예약</button>
          )}
        </div>
      </div>
    </div>
  );
}
