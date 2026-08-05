import { fmtMoney, fmtNum } from "../lib/money";
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, useMe, setCachedMe, type PassInfo, type CreditTxn, type CreditSummary } from "../api";
import { fmtKSTDateTime, fmtKSTDate } from "../lib/datetime";
import i18n from "../i18n";

const HISTORY_PAGE = 10;   // 결제 내역 한 페이지 표시 개수

// 포인트 원장 reason → payx 카탈로그 키(ko/vi). 미등록 reason 은 delta 부호로 '적립/사용' 폴백(항상 정확).
const REASON_KEY: Record<string, string> = {
  signup_bonus: "rs_signup_bonus", purchase: "rs_topup", topup: "rs_topup",
  admin_grant: "rs_admin_grant", admin_seed: "rs_grant", family_grant: "rs_grant",
  pass_lite: "rs_pass_lite", pass_plus: "rs_pass_plus", pass_renew: "rs_pass_renew",
  refund: "rs_refund", consultation_reserve_refund: "rs_reserve_refund",
  feedback_reward: "rs_feedback_reward", review_reward: "rs_review_reward",
  question: "rs_question", tool_q: "rs_question", preview_reveal: "rs_preview_reveal",
  tarot: "rs_tarot", naming: "rs_naming", sinnyeon: "rs_sinnyeon", taekil: "rs_taekil",
  compatibility: "rs_compat", amulet: "rs_amulet", dream: "rs_dream", video_gen: "rs_video",
  consultation: "rs_consult", consultation_extend: "rs_consult_extend", consultation_reserve: "rs_consult_reserve",
};
function txnLabel(t: CreditTxn): string {
  const k = REASON_KEY[t.reason];
  return k ? i18n.t(`payx.${k}`) : i18n.t(t.delta >= 0 ? "payx.rs_earn" : "payx.rs_spend");
}
// 결제 상태 → payx 카탈로그 키(영어 원문 노출 방지)
const STATUS_KEY: Record<string, string> = {
  approved: "st_approved", refunded: "st_refunded", pending: "st_pending",
  failed: "st_failed", canceled: "st_canceled", ready: "st_pending",
};
import { Trans, useTranslation } from "react-i18next";

declare global {
  interface Window {
    TossPayments?: any;
  }
}

type Pkg = { amount: number; credits: number; label: string };

/** B-7 월 패스 — 포인트 자동차감형(30일). 카드 자동결제가 아니라 기존 포인트에서 차감. */
function PassSection() {
  const { t: tr } = useTranslation();
  const [info, setInfo] = useState<PassInfo | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => api.passInfo().then(setInfo).catch(() => {});
  useEffect(() => { load(); }, []);

  if (!info) return null;
  const mine = info.mine;

  async function subscribe(tier: "lite" | "plus") {
    const p = info!.products[tier];
    if (!window.confirm(
      tr("payx.pass_confirm", { label: p.label, price: fmtNum(p.price_p), days: p.period_days }),
    )) return;
    setBusy(tier); setMsg(null);
    try {
      await api.passSubscribe(tier);
      await load();
      api.me().then(setCachedMe).catch(() => {});
      setMsg(tr("payx.pass_started"));
    } catch (e: any) {
      setMsg(e?.message || tr("payx.pass_sub_fail"));
    } finally { setBusy(null); }
  }

  async function cancelPass() {
    if (!window.confirm(tr("payx.pass_cancel_confirm"))) return;
    setBusy("cancel");
    try {
      await api.passCancel();
      await load();
      setMsg(tr("payx.pass_canceled"));
    } catch (e: any) {
      setMsg(e?.message || tr("payx.pass_cancel_fail"));
    } finally { setBusy(null); }
  }

  return (
    <div style={{ marginTop: 28 }}>
      <h3 style={{ marginBottom: 4 }}>{tr("payx.pass_title")} <span style={{ fontSize: 12, fontWeight: 500, color: "var(--ink-400)" }}>{tr("payx.pass_title_note")}</span></h3>
      {mine && (
        <div className="pass-mine">
          <Trans i18nKey="payx.pass_mine" values={{ label: mine.label, date: mine.next_renewal_at.slice(0, 10) }} components={{ b: <b /> }} />
          {mine.tier === "plus" && <>{tr("payx.pass_plus_remain", { q: mine.free_basic_remaining, a: mine.amulet_free_remaining })}</>}
          {mine.auto_renew
            ? <button className="pass-cancel" disabled={busy !== null} onClick={cancelPass}>{tr("payx.pass_cancel_btn")}</button>
            : <span className="pass-ending">{tr("payx.pass_ending")}</span>}
        </div>
      )}
      {!mine && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12, marginTop: 10 }}>
          {(["lite", "plus"] as const).map((tier) => {
            const p = info.products[tier];
            return (
              <div key={tier} className={`pass-card${tier === "plus" ? " plus" : ""}`}>
                {tier === "plus" && <span className="pass-best">{tr("payx.pass_best")}</span>}
                <div className="pass-name">{p.label}</div>
                <div className="pass-price">{tr("payx.pass_price_p", { price: fmtNum(p.price_p) })} <small>{tr("payx.pass_per_days", { days: p.period_days })}</small></div>
                <ul className="pass-benefits">
                  {p.benefits.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
                {/* 가치 한 줄 — 플러스는 절약액(초록), 라이트는 하루 환산가/추가 횟수(정보톤).
                    라이트엔 개별 판매가가 없어 P 상당액을 매기지 않는다(근거 없는 숫자 금지). */}
                {p.worth_note && (
                  <div className={`pass-worth${tier === "plus" ? "" : " info"}`}>
                    {tier === "plus" ? "💰" : "✨"} {p.worth_note}
                  </div>
                )}
                <button className="pass-cta" disabled={busy !== null} onClick={() => subscribe(tier)}>
                  {busy === tier ? tr("payx.pass_processing") : tr("payx.pass_start_btn")}
                </button>
              </div>
            );
          })}
        </div>
      )}
      {msg && <div style={{ marginTop: 10, fontSize: 13, color: "var(--ink-600)" }}>{msg}</div>}
    </div>
  );
}

export default function PaymentsPage() {
  const nav = useNavigate();
  const me = useMe();
  const { t: tr } = useTranslation();
  const [pkgs, setPkgs] = useState<Pkg[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [txns, setTxns] = useState<CreditTxn[]>([]);   // 포인트 원장(충전·차감·환불 전부)
  const [txnSummary, setTxnSummary] = useState<CreditSummary | null>(null);   // 정합성 요약(충전+적립-사용=잔액)
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [selMonth, setSelMonth] = useState<string | null>(null);  // null=전체, "2026-07" 등
  const [page, setPage] = useState(0);                            // 0-base

  // 결제 시각(승인 우선)의 KST 월("YYYY-MM")
  const monthOf = (h: any) => fmtKSTDate(h.approved_at || h.created_at).slice(0, 7);
  // 상단 월 필터 버튼용 — 내역에 존재하는 월 목록(최신순)
  const months = Array.from(new Set(history.map(monthOf).filter((m) => m.length === 7))).sort().reverse();
  const filtered = selMonth ? history.filter((h) => monthOf(h) === selMonth) : history;
  const totalPages = Math.max(1, Math.ceil(filtered.length / HISTORY_PAGE));
  const pageSafe = Math.min(page, totalPages - 1);
  const paged = filtered.slice(pageSafe * HISTORY_PAGE, pageSafe * HISTORY_PAGE + HISTORY_PAGE);
  const pickMonth = (m: string | null) => { setSelMonth(m); setPage(0); };  // 월 클릭 → 그 달로 + 첫 페이지

  async function loadAll() {
    try {
      const r = await api.paymentPackages();
      setPkgs(r.items);
      const h = await api.paymentMyHistory();
      setHistory(h.items);
      try { const th = await api.creditHistory(); setTxns(th.items); setTxnSummary(th.summary); } catch { /* 원장 조회 실패는 결제 화면 전체를 막지 않음 */ }
    } catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { if (me) loadAll(); }, []);

  async function buy(p: Pkg) {
    if (!me) return nav("/login?next=%2Fpayments");   // 로그인 후 충전 화면으로 복귀
    setBusy(p.amount);
    setErr(null);
    try {
      const order = await api.paymentCreateOrder(p.amount);
      // 토스 v2 결제창(SDK v2/standard) 호출 — client_key(gck) 가 더미가 아니면.
      //   v1 대비: method "카드"→"CARD", amount 숫자→{value,currency}, payment({customerKey}) 경유.
      //   성공 리디렉트 파라미터(paymentKey·orderId·amount)·백엔드 confirm 은 v1·v2 공통이라 무변경.
      const isDummy = order.client_key.includes("DUMMY");
      if (!isDummy && window.TossPayments) {
        const toss = window.TossPayments(order.client_key);
        const payment = toss.payment({ customerKey: "ANONYMOUS" });
        await payment.requestPayment({
          method: "CARD",
          amount: { value: order.amount, currency: "KRW" },
          orderId: order.order_id,
          orderName: order.order_name,
          customerEmail: order.customer_email,
          customerName: order.customer_name,
          successUrl: order.success_url,
          failUrl: order.fail_url,
        });
        // 위 호출은 페이지 리디렉트하므로 아래로 안 옴
        return;
      }
      // 더미 키 → 즉시 mock 승인 (개발용)
      const fakeKey = `mock_pk_${Date.now()}`;
      const c = await api.paymentConfirm(fakeKey, order.order_id, order.amount);
      alert(tr("pay.test_done", {
        label: p.label,
        credits: fmtNum(c.credits_granted),
        balance: fmtNum(c.balance),
      }));
      // me 캐시 갱신
      const newMe = await api.me();
      setCachedMe(newMe);
      await loadAll();
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!me) {
    return (
      <div className="compat-page">
        <header className="compat-hero">
          <div className="compat-hero-badge">{tr("payx.hero_badge")}</div>
          <h1>{tr("pay.charge_title")}</h1>
          <p><Trans i18nKey="payx.login_body" components={{ b: <b /> }} /></p>
        </header>
        <div className="compat-actions">
          {/* 로그인 후 다시 충전 화면으로 — '충전하려고 로그인했는데 딴 데로 감' 방지(운영자 지적) */}
          <Link className="compat-cta" to="/login?next=%2Fpayments" style={{ textDecoration: "none" }}>{tr("payx.login_cta")}</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">{tr("payx.hero_badge")}</div>
        <h1>{tr("pay.charge_title")}</h1>
        <p><Trans i18nKey="payx.rate_line" values={{ basic: fmtNum(me.credit_cost_basic ?? 1900), reveal: fmtNum(me.preview_reveal_cost ?? 900) }} components={{ b: <b /> }} /></p>
      </header>
      {/* 인라인 스타일 → 클래스. 라벨이 2줄인 카드(연간회원 등) 때문에 '충전' 버튼 높이가 제각각이던 문제를
          .pkg-card 의 flex column + .pkg-buy 의 margin-top:auto 로 하단 정렬한다(운영자 지적). */}
      <div className="pkg-grid">
        {pkgs.map((p) => (
          <div key={p.amount} className="pkg-card">
            <div className="pkg-label">{p.label}</div>
            <div className="pkg-credits">{p.credits.toLocaleString()} P</div>
            <button className="pkg-buy" onClick={() => buy(p)} disabled={busy !== null}>
              {busy === p.amount ? tr("pay.processing") : tr("pay.charge_btn")}
            </button>
          </div>
        ))}
      </div>
      {err && <div className="compat-err">{err}</div>}

      <PassSection />

      {/* 포인트 원장 — '잔액 줄었는데 쓴 기록이 없다' 오해 차단(패턴 D). 충전·차감·환불 전부 시간순. */}
      <h3 style={{ marginTop: 24, marginBottom: 4 }}>{tr("payx.ledger_title")}</h3>
      <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--ink-500)" }}>
        {tr("payx.ledger_sub")}
      </p>
      {/* 정합성 대조 — 사용자가 직접 '충전+적립−사용=잔액'을 확인(돈에 관한 화면) */}
      {txnSummary && (
        <div className="ledger-summary">
          <div className="ls-cards">
            <div className="ls-card"><span className="ls-lb">{tr("payx.ls_purchased")}</span><span className="ls-v">+{tr("payx.pt_amount", { n: fmtNum(txnSummary.purchased) })}</span></div>
            <div className="ls-card"><span className="ls-lb">{tr("payx.ls_rewarded")}</span><span className="ls-v">+{tr("payx.pt_amount", { n: fmtNum(txnSummary.rewarded) })}</span></div>
            <div className="ls-card"><span className="ls-lb">{tr("payx.ls_used")}</span><span className="ls-v ls-minus">−{tr("payx.pt_amount", { n: fmtNum(txnSummary.used) })}</span></div>
            <div className="ls-card ls-bal"><span className="ls-lb">{tr("pay.cur_balance")}</span><span className="ls-v">{tr("payx.pt_amount", { n: fmtNum(txnSummary.balance) })}</span></div>
          </div>
          <div className={`ls-reconcile ${txnSummary.consistent ? "ok" : "bad"}`}>
            {txnSummary.consistent
              ? <Trans i18nKey="payx.ls_ok" values={{ purchased: fmtNum(txnSummary.purchased), rewarded: fmtNum(txnSummary.rewarded), used: fmtNum(txnSummary.used), balance: fmtNum(txnSummary.balance) }} components={{ b: <b /> }} />
              : <>{tr("payx.ls_bad", { computed: fmtNum(txnSummary.computed_balance), balance: fmtNum(txnSummary.balance) })}</>}
          </div>
        </div>
      )}
      <div style={{ maxHeight: 360, overflowY: "auto", border: "1px solid var(--border, #eee)", borderRadius: 8 }}>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f7f7f7" }}>
              <th style={th}>{tr("payx.th_desc")}</th>
              <th style={{ ...th, textAlign: "right" }}>{tr("payx.th_delta")}</th>
              <th style={{ ...th, textAlign: "right" }}>{tr("payx.th_balance")}</th>
              <th style={th}>{tr("pay.th_time")}</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((t) => (
              <tr key={t.id}>
                <td style={td}>{txnLabel(t)}</td>
                <td style={{ ...td, textAlign: "right", fontWeight: 700, color: t.delta >= 0 ? "var(--brand-600)" : "#c0392b" }}>
                  {t.delta >= 0 ? "+" : "−"}{tr("payx.pt_amount", { n: fmtNum(Math.abs(t.delta)) })}
                </td>
                <td style={{ ...td, textAlign: "right", color: "var(--ink-500)" }}>{tr("payx.pt_amount", { n: fmtNum(t.balance_after) })}</td>
                <td style={td}>{fmtKSTDateTime(t.created_at)}</td>
              </tr>
            ))}
            {txns.length === 0 && (
              <tr><td style={{ ...td, textAlign: "center", color: "var(--ink-400)" }} colSpan={4}>{tr("payx.ledger_empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 24, marginBottom: 8 }}>{tr("payx.history_title2")}</h3>
      {/* 상단 월별 필터 — 누르면 그 달 내역만 바로 표시 */}
      {months.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          <button type="button" onClick={() => pickMonth(null)}
                  style={monthChip(selMonth === null)}>{tr("payx.month_all")}</button>
          {months.map((m) => {
            const [yy, mm] = m.split("-");
            return (
              <button key={m} type="button" onClick={() => pickMonth(m)} style={monthChip(selMonth === m)}>
                {tr("payx.month_chip", { yy, m: Number(mm) })}
              </button>
            );
          })}
        </div>
      )}
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>{tr("pay.th_order")}</th>
            <th style={{ ...th, textAlign: "right" }}>{tr("pay.th_amount")}</th>
            <th style={{ ...th, textAlign: "right" }}>{tr("pay.th_credit")}</th>
            <th style={th}>{tr("pay.th_status")}</th>
            <th style={th}>{tr("pay.th_time")}</th>
          </tr>
        </thead>
        <tbody>
          {paged.map((h) => (
            <tr key={h.id}>
              <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{h.order_id}</td>
              <td style={{ ...td, textAlign: "right" }}>{fmtMoney(h.amount)}</td>
              <td style={{ ...td, textAlign: "right", color: h.status === "refunded" ? "var(--ink-400)" : undefined }}>
                {h.status === "refunded"
                  ? <s>+{tr("payx.pt_amount", { n: fmtNum(h.credit_granted) })}</s>   /* 환불됨 = 적립분 회수됨을 취소선으로 명시 */
                  : <>+{tr("payx.pt_amount", { n: fmtNum(h.credit_granted) })}</>}
              </td>
              <td style={td}>
                <span
                  style={{
                    padding: "2px 6px",
                    background: h.status === "approved" ? "var(--brand-500)" : h.status === "refunded" ? "#e67e22" : "#ccc",
                    color: "white",
                    borderRadius: 3,
                    fontSize: 11,
                  }}
                >
                  {STATUS_KEY[h.status] ? tr(`payx.${STATUS_KEY[h.status]}`) : h.status}
                </span>
              </td>
              <td style={td}>
                {fmtKSTDateTime(h.approved_at || h.created_at)}
              </td>
            </tr>
          ))}
          {paged.length === 0 && (
            <tr><td style={{ ...td, textAlign: "center", color: "var(--ink-400)" }} colSpan={5}>
              {selMonth ? tr("payx.empty_month") : tr("payx.empty_hist")}
            </td></tr>
          )}
        </tbody>
      </table>

      {/* 페이지 이동 (10개씩) */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 6, marginTop: 12 }}>
          <button type="button" disabled={pageSafe <= 0} onClick={() => setPage(pageSafe - 1)} style={pageBtn(pageSafe <= 0)}>‹</button>
          {Array.from({ length: totalPages }, (_, i) => (
            <button key={i} type="button" onClick={() => setPage(i)} style={pageNum(i === pageSafe)}>{i + 1}</button>
          ))}
          <button type="button" disabled={pageSafe >= totalPages - 1} onClick={() => setPage(pageSafe + 1)} style={pageBtn(pageSafe >= totalPages - 1)}>›</button>
        </div>
      )}
      <div style={{ textAlign: "center", fontSize: 12, color: "var(--ink-400)", marginTop: 6 }}>
        {tr("payx.total_count", { n: filtered.length })}{selMonth ? tr("payx.total_count_month", { yy: selMonth.split("-")[0], m: Number(selMonth.split("-")[1]) }) : ""}
      </div>
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "6px 8px", borderBottom: "1px solid #ddd" };
const td: React.CSSProperties = { padding: "6px 8px", borderBottom: "1px solid #eee" };
// 상단 월 필터 칩
function monthChip(on: boolean): React.CSSProperties {
  return {
    padding: "5px 12px", borderRadius: 999, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
    border: on ? "1px solid transparent" : "1px solid var(--brand-100)",
    background: on ? "var(--brand-grad)" : "transparent",
    color: on ? "#fff" : "var(--ink-600)",
  };
}
// 페이지 이전/다음
function pageBtn(disabled: boolean): React.CSSProperties {
  return {
    minWidth: 30, height: 30, borderRadius: 8, border: "1px solid var(--line)",
    background: "var(--surface)", color: "var(--ink-600)", fontWeight: 700,
    cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1,
  };
}
// 페이지 번호
function pageNum(on: boolean): React.CSSProperties {
  return {
    minWidth: 30, height: 30, borderRadius: 8, fontWeight: 700, cursor: "pointer",
    border: on ? "1px solid transparent" : "1px solid var(--line)",
    background: on ? "var(--brand-500)" : "var(--surface)",
    color: on ? "#fff" : "var(--ink-600)",
  };
}
