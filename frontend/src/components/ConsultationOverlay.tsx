import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, useMe, type ConsultantPublic, type ConsultationConfig, type ConsultSource, type ConsultationSlot } from "../api";
import { useCharge } from "./ChargeModal";
import i18n from "../i18n";

/** UTC ISO → 로케일 슬롯 표기(ko "7/9(수) 14:30" / vi "9/7 (T4) 14:30") */
function fmtSlot(iso: string): string {
  const d = new Date(iso);
  const day = i18n.t("consult.weekdays").split(",")[d.getDay()];
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return i18n.t("consult.slot_fmt", { m: d.getMonth() + 1, d: d.getDate(), w: day, time });
}
import { useTranslation, Trans } from "react-i18next";
import { fmtNum } from "../lib/money";
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

const CATS: { key: Cat; tk: string; ic: string }[] = [
  { key: "all", tk: "consult.cat_all", ic: "✨" },
  { key: "saju", tk: "consult.cat_saju", ic: "🔮" },
  { key: "tarot", tk: "consult.cat_tarot", ic: "🃏" },
];

// 접속 상태 → 배지 라벨 키(consult.*)·CSS 클래스. 라벨은 컴포넌트에서 tr 로 해석.
const PRESENCE: Record<string, { key: string; cls: string }> = {
  online: { key: "presence_online", cls: "on" },
  busy: { key: "presence_busy", cls: "busy" },
  offline: { key: "presence_offline", cls: "off" },
};

const SPEC: Record<string, { tk: string; cls: string }> = {
  saju: { tk: "consult.cat_saju", cls: "saju" },
  tarot: { tk: "consult.cat_tarot", cls: "tarot" },
  both: { tk: "consult.spec_both", cls: "both" },
};

function priceLabel(c: ConsultantPublic): { main: string; sub: string } {
  if (c.price_unit === "minute" && c.per_min_p)
    return {
      main: i18n.t("consult.price_per_min", { p: fmtNum(c.per_min_p) }),
      sub: i18n.t("consult.price_once_dur", { p: fmtNum(c.price_p), min: fmtNum(c.duration_min) }),
    };
  if (c.price_unit === "hour" && c.per_hour_p)
    return {
      main: i18n.t("consult.price_per_hour", { p: fmtNum(c.per_hour_p) }),
      sub: i18n.t("consult.price_once_dur", { p: fmtNum(c.price_p), min: fmtNum(c.duration_min) }),
    };
  return { main: i18n.t("consult.pts", { p: fmtNum(c.price_p) }), sub: i18n.t("consult.dur_min", { n: fmtNum(c.duration_min) }) };
}

// 오늘(KST) 영업시간 안내. 미설정=null(상시). 휴무=open:false.
function bizHoursToday(c: ConsultantPublic): { label: string; open: boolean } | null {
  const h = c.business_hours;
  if (!h || Object.keys(h).length === 0) return null;
  const kst = new Date(Date.now() + 9 * 3600000);   // UTC ms + 9h → KST 벽시계(UTC 필드로 읽음)
  const wd = (kst.getUTCDay() + 6) % 7;             // JS 0=일 → 파이썬 0=월 기준으로 변환
  const ent = h[String(wd)];
  if (!ent || !ent.open || !ent.close) return { label: i18n.t("consult.biz_closed_today"), open: false };
  return { label: i18n.t("consult.biz_today", { open: ent.open, close: ent.close }), open: true };
}

type StatusKey = "all" | "online" | "busy" | "offline";
type SortKey = "recommended" | "available" | "rating" | "sessions" | "price";

const STATUS_CHIPS: { key: StatusKey; tk: string }[] = [
  { key: "all", tk: "consult.cat_all" },
  { key: "online", tk: "consult.st_online" },
  { key: "busy", tk: "consult.presence_busy" },
  { key: "offline", tk: "consult.presence_offline" },
];
const SORT_OPTIONS: { key: SortKey; tk: string }[] = [
  { key: "recommended", tk: "consult.sort_recommended" },
  { key: "available", tk: "consult.sort_available" },
  { key: "rating", tk: "consult.sort_rating" },
  { key: "sessions", tk: "consult.sort_sessions" },
  { key: "price", tk: "consult.sort_price" },
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
  const { t: tr } = useTranslation();
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
      setErr(e?.message || tr("consult.err_slots"));
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
      setErr(e?.message || tr("consult.err_reserve"));
    } finally {
      setReserving(false);
    }
  }

  async function cancelMyReservation(s: ConsultationSlot) {
    const full = cfg?.reserve_full_refund_hours ?? 24;
    const pct = cfg?.reserve_late_refund_pct ?? 50;
    const hoursLeft = (new Date(s.start_at).getTime() - Date.now()) / 3600000;
    const note = hoursLeft >= full ? tr("consult.cancel_full_note") : tr("consult.cancel_late_note", { h: full, pct });
    if (!window.confirm(tr("consult.cancel_confirm", { slot: fmtSlot(s.start_at), note }))) return;
    try {
      const r = await api.cancelReservation(s.id);
      alert(tr("consult.cancel_done", { p: fmtNum(r.refund_p) }));
      loadMyReservations();
    } catch (e: any) {
      alert(e?.message || tr("consult.err_cancel"));
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
      .catch((e) => { if (alive) setErr(e?.message || tr("consult.err_list")); })
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
      setErr(e?.message || tr("consult.err_request"));
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
          <p className="csl-bal-need">{tr("consult.bal_login_need")}</p>
          <button className="csl-bal-btn" onClick={() => { onClose(); navigate("/login"); }}>{tr("consult.bal_login_btn")}</button>
        </div>
      );
    }
    const short = bal < price;
    return (
      <div className="csl-bal-cta">
        <p className={`csl-bal-line ${short ? "short" : ""}`}>
          <Trans i18nKey="consult.bal_have" values={{ bal: fmtNum(bal) }} components={{ b: <b /> }} />
          {short && <span className="csl-bal-short">{tr("consult.bal_short", { n: fmtNum(price - bal) })}</span>}
        </p>
        {short && <button className="csl-bal-btn" onClick={() => openCharge(reason)}>{tr("consult.bal_charge_btn")}</button>}
      </div>
    );
  }

  if (!open) return null;

  return (
    <div className="pwa-overlay csl-ov" role="dialog" aria-modal="true" aria-label={tr("consult.dialog_aria")} onClick={onClose}>
      <div className="pwa-modal csl-modal" onClick={(e) => e.stopPropagation()}>
        <button className="csl-x" onClick={onClose} aria-label={tr("consult.close")}>×</button>

        <div className="csl-head2">
          <h3 className="csl-title">{tr("consult.dialog_aria")}</h3>
          <p className="csl-sub">{tr("consult.overlay_sub")}</p>
        </div>

        {/* A-2 내 예약 — 다가오는 예약 표시 + 취소 */}
        {myRes && myRes.length > 0 && (
          <div className="csl-myres">
            <div className="csl-myres-title">{tr("consult.myres_title")}</div>
            {myRes.map((s) => (
              <div key={s.id} className={`csl-myres-item st-${s.status}`}>
                <span className="t">{fmtSlot(s.start_at)}</span>
                <span className="n">
                  <Trans
                    i18nKey="consult.myres_with"
                    values={{ name: s.consultant_name || tr("consult.role_consultant") }}
                    components={{ b: <b className="csl-myres-who" /> }}
                  />
                </span>
                <span className={`st st-${s.status}`}>{s.status === "booked" ? tr("consult.myres_booked") : tr("consult.myres_ongoing")}</span>
                {s.status === "booked" && (
                  <button className="x" onClick={() => cancelMyReservation(s)}>{tr("consult.consent_cancel")}</button>
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
              ? <Trans i18nKey="consult.locked_tarot" components={{ b: <b /> }} />
              : source.kind === "birth"
                ? <Trans i18nKey="consult.locked_birth" components={{ b: <b /> }} />
                : <Trans i18nKey="consult.locked_saju" components={{ b: <b /> }} />}
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
                <span aria-hidden>{t.ic}</span> {tr(t.tk)}
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
                placeholder={tr("consult.search_ph")}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label={tr("consult.search_aria")}
              />
            </div>
            <div className="csl-control-row">
              <div className="csl-chips" role="group" aria-label={tr("consult.filter_aria")}>
                {STATUS_CHIPS.map((s) => (
                  <button
                    key={s.key}
                    className={`csl-chip ${statusFilter === s.key ? "active" : ""}`}
                    aria-pressed={statusFilter === s.key}
                    onClick={() => setStatusFilter(s.key)}
                  >
                    {tr(s.tk)}
                  </button>
                ))}
              </div>
              <select className="csl-sort" value={sortBy} aria-label={tr("consult.sort_aria")}
                onChange={(e) => setSortBy(e.target.value as SortKey)}>
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>{tr(o.tk)}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        <div className="csl-list-wrap">
          {loading && <p className="csl-empty">{tr("consult.loading")}</p>}
          {err && <p className="csl-empty csl-err">{err}</p>}
          {items && items.length === 0 && !loading && (
            <p className="csl-empty">{tr("consult.empty_cat")}</p>
          )}
          {(() => {
            const visible = items ? filterAndSort(items, q, statusFilter, sortBy) : [];
            if (items && items.length > 0 && visible.length === 0 && !loading)
              return <p className="csl-empty">{tr("consult.empty_filtered")}</p>;
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
              {tr("consult.consent_price", {
                price: `${fmtNum(pending.price_p)}${tr("pay.pt")}`,
                min: fmtNum(pending.duration_min),
              })}
            </p>
            {balanceGate(pending.price_p, tr("consult.charge_reason_start", { p: fmtNum(pending.price_p) }))}
            <p className="csl-consent-note">
              <Trans
                i18nKey="consult.consent_note"
                values={{ days: cfg?.retention_days ?? 7 }}
                components={{ b: <b /> }}
              />
            </p>
            {source && (
              <p className="csl-consent-note csl-consent-source">
                <Trans
                  i18nKey="consult.consent_source"
                  values={{
                    what: source.kind === "saju" ? tr("consult.src_saju") : source.kind === "birth" ? tr("consult.src_birth") : tr("consult.src_tarot"),
                    label: source.label ? ` (${source.label})` : "",
                    days: cfg?.retention_days ?? 7,
                  }}
                  components={{ b: <b /> }}
                />
              </p>
            )}
            {err && <p className="csl-consent-err">{err}</p>}
            <div className="csl-consent-actions">
              <button className="csl-consent-ok" onClick={confirmRequest} disabled={submitting}>
                {submitting ? tr("consult.consent_submitting") : tr("consult.consent_submit")}
              </button>
              <button className="csl-consent-cancel" onClick={() => setPending(null)} disabled={submitting}>{tr("consult.consent_cancel")}</button>
            </div>
          </div>
        </div>
      )}

      {/* A-2 예약 — 슬롯 선택 → 동의(선결제·취소정책) → 완료 */}
      {reservePending && (
        <div className="csl-consent-ov" onClick={(e) => { e.stopPropagation(); if (!reserving) { setReservePending(null); setPickedSlot(null); setReserveDone(null); } }}>
          <div className="csl-consent" onClick={(e) => e.stopPropagation()}>
            <h4>{tr("consult.reserve_title", { name: reservePending.business_name })}</h4>

            {reserveDone ? (
              <>
                <p className="csl-consent-note">
                  <Trans
                    i18nKey="consult.reserve_done"
                    values={{ slot: fmtSlot(reserveDone.start_at) }}
                    components={{ b: <b />, br: <br /> }}
                  />
                </p>
                <div className="csl-consent-actions">
                  <button className="csl-consent-ok" onClick={() => { setReservePending(null); setReserveDone(null); }}>{tr("consult.ok")}</button>
                </div>
              </>
            ) : pickedSlot ? (
              <>
                <p className="csl-consent-price">
                  {tr("consult.reserve_price_line", {
                    slot: fmtSlot(pickedSlot.start_at),
                    p: fmtNum(reservePending.price_p),
                    min: fmtNum(reservePending.duration_min),
                  })}
                </p>
                <p className="csl-consent-note">
                  <Trans
                    i18nKey="consult.reserve_terms"
                    values={{
                      p: fmtNum(reservePending.price_p),
                      h: cfg?.reserve_full_refund_hours ?? 24,
                      pct: cfg?.reserve_late_refund_pct ?? 50,
                    }}
                    components={{ b: <b /> }}
                  />
                </p>
                <p className="csl-consent-note">
                  <Trans i18nKey="consult.reserve_retention" values={{ days: cfg?.retention_days ?? 7 }} components={{ b: <b /> }} />
                </p>
                {balanceGate(reservePending.price_p, tr("consult.charge_reason_reserve", { p: fmtNum(reservePending.price_p) }))}
                {err && <p className="csl-consent-err">{err}</p>}
                <div className="csl-consent-actions">
                  <button className="csl-consent-ok" onClick={confirmReserve} disabled={reserving || payBlocked(reservePending.price_p)}>
                    {reserving ? tr("consult.reserving") : payBlocked(reservePending.price_p) ? (me ? tr("consult.need_points_btn") : tr("consult.need_login_btn")) : tr("consult.reserve_submit")}
                  </button>
                  <button className="csl-consent-cancel" onClick={() => setPickedSlot(null)} disabled={reserving}>{tr("consult.back_plain")}</button>
                </div>
              </>
            ) : (
              <>
                <p className="csl-consent-note">{tr("consult.pick_slot")}</p>
                {slots == null && <p className="csl-consent-note">{tr("consult.loading")}</p>}
                {slots != null && slots.length === 0 && (
                  <p className="csl-consent-note">{tr("consult.no_slots")}</p>
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
                  <button className="csl-consent-cancel" onClick={() => setReservePending(null)}>{tr("consult.close")}</button>
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
  const { t: tr } = useTranslation();
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
        <span className={`csl-spec-badge ${spec.cls}`}>{tr(spec.tk)}</span>
        {!isComing && <span className={`csl-badge ${p.cls}`}>{tr(`consult.${p.key}`)}</span>}
        {isComing && (
          <div className="csl-coming" aria-label={tr("consult.coming_soon")}>
            <span className="csl-coming-ic" aria-hidden>⏳</span>
            <span className="csl-coming-tx">{tr("consult.coming_soon")}</span>
          </div>
        )}
      </div>
      <div className="csl-info">
        <div className="csl-card-top">
          <span className="csl-nm">{c.business_name}</span>
          <span className={`csl-badge ${p.cls}`}>{tr(`consult.${p.key}`)}</span>
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
            <span className="csl-stars" title={tr("consult.rating_title", { avg: c.rating_avg, count: fmtNum(c.rating_count) })}>
              <Stars avg={c.rating_avg} />
              <b>{c.rating_avg.toFixed(1)}</b>
              <span className="csl-rc">({c.rating_count})</span>
            </span>
          ) : (
            <span className="csl-norate">{tr("consult.no_rating")}</span>
          )}
          <span className="csl-dot" aria-hidden>·</span>
          <span className="csl-scount">{tr("consult.session_count", { count: fmtNum(c.session_count) })}</span>
        </div>
        {biz && (
          <div className={`csl-bizhours ${biz.open ? "open" : "closed"}`}>
            <span aria-hidden>🕒</span> {biz.label}
          </div>
        )}
        <div className="csl-cta-row">
          {isComing ? (
            <span className="csl-price csl-price-soon">{tr("consult.opening_soon")}</span>
          ) : (
            <span className="csl-price-wrap">
              <span className="csl-price">{price.main}</span>
              <span className="csl-price-sub">{price.sub}</span>
            </span>
          )}
          <button className="csl-start" disabled={!canStart} onClick={onStart}>
            {isComing ? tr("consult.coming_soon") : c.presence === "busy" ? tr("consult.card_busy") : c.presence === "offline" ? tr("consult.card_offline") : tr("consult.card_start")}
          </button>
          {/* A-2: 부재중·상담중이어도 예약은 가능 */}
          {!isComing && (
            <button className="csl-reserve" onClick={onReserve}>{tr("consult.reserve_btn")}</button>
          )}
        </div>
      </div>
    </div>
  );
}
