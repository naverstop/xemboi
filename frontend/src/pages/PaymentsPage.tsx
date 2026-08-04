import { fmtMoney, fmtNum } from "../lib/money";
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, useMe, setCachedMe, type PassInfo, type CreditTxn, type CreditSummary } from "../api";
import { fmtKSTDateTime, fmtKSTDate } from "../lib/datetime";

const HISTORY_PAGE = 10;   // 결제 내역 한 페이지 표시 개수

// 포인트 원장 reason → 한국어 라벨. 미등록 reason 은 delta 부호로 '적립/사용' 폴백(항상 정확).
const REASON_LABEL: Record<string, string> = {
  signup_bonus: "가입 축하 포인트", purchase: "충전", topup: "충전",
  admin_grant: "관리자 지급", admin_seed: "지급", family_grant: "지급",
  pass_lite: "라이트 패스", pass_plus: "플러스 패스", pass_renew: "패스 갱신",
  refund: "환불", consultation_reserve_refund: "예약 환불",
  feedback_reward: "피드백 리워드", review_reward: "후기 리워드",
  question: "추가 질문", tool_q: "추가 질문", preview_reveal: "전체 보기",
  tarot: "타로", naming: "작명·개명·아호", sinnyeon: "신년운세", taekil: "택일",
  compatibility: "궁합", amulet: "부적", dream: "꿈해몽", video_gen: "사주 영상",
  consultation: "1:1 상담", consultation_extend: "상담 연장", consultation_reserve: "상담 예약",
};
function txnLabel(t: CreditTxn): string {
  return REASON_LABEL[t.reason] || (t.delta >= 0 ? "적립" : "사용");
}
// 결제 상태 한국어(영어 원문 노출 방지)
const STATUS_KO: Record<string, string> = {
  approved: "충전 완료", refunded: "환불됨", pending: "결제 대기", failed: "실패", canceled: "취소", ready: "결제 대기",
};
import { useTranslation } from "react-i18next";

declare global {
  interface Window {
    TossPayments?: any;
  }
}

type Pkg = { amount: number; credits: number; label: string };

/** B-7 월 패스 — 포인트 자동차감형(30일). 카드 자동결제가 아니라 기존 포인트에서 차감. */
function PassSection() {
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
      `${p.label}를 시작할까요?\n\n· 지금 ${p.price_p.toLocaleString()}P가 차감되고, ${p.period_days}일마다 자동으로 갱신돼요\n` +
      "· 갱신 시 포인트가 부족하면 자동으로 중지돼요(추가 결제 없음)\n· 언제든 해지할 수 있어요(남은 기간은 그대로 이용)",
    )) return;
    setBusy(tier); setMsg(null);
    try {
      await api.passSubscribe(tier);
      await load();
      api.me().then(setCachedMe).catch(() => {});
      setMsg("패스가 시작됐어요! 🎉");
    } catch (e: any) {
      setMsg(e?.message || "구독에 실패했어요.");
    } finally { setBusy(null); }
  }

  async function cancelPass() {
    if (!window.confirm("자동갱신을 해지할까요? 남은 기간은 그대로 이용할 수 있어요.")) return;
    setBusy("cancel");
    try {
      await api.passCancel();
      await load();
      setMsg("자동갱신이 해지됐어요. 남은 기간까지 혜택이 유지돼요.");
    } catch (e: any) {
      setMsg(e?.message || "해지에 실패했어요.");
    } finally { setBusy(null); }
  }

  return (
    <div style={{ marginTop: 28 }}>
      <h3 style={{ marginBottom: 4 }}>월 패스 <span style={{ fontSize: 12, fontWeight: 500, color: "var(--ink-400)" }}>— 포인트 자동차감(30일) · 카드 자동결제 아님</span></h3>
      {mine && (
        <div className="pass-mine">
          <b>{mine.label}</b> 이용 중 · 다음 갱신 {mine.next_renewal_at.slice(0, 10)}
          {mine.tier === "plus" && <> · 이번 주기 무료 질문 {mine.free_basic_remaining}회 / 부적 {mine.amulet_free_remaining}회 남음</>}
          {mine.auto_renew
            ? <button className="pass-cancel" disabled={busy !== null} onClick={cancelPass}>자동갱신 해지</button>
            : <span className="pass-ending"> · 해지 예약됨(기간 만료 시 종료)</span>}
        </div>
      )}
      {!mine && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12, marginTop: 10 }}>
          {(["lite", "plus"] as const).map((tier) => {
            const p = info.products[tier];
            return (
              <div key={tier} className={`pass-card${tier === "plus" ? " plus" : ""}`}>
                {tier === "plus" && <span className="pass-best">추천</span>}
                <div className="pass-name">{p.label}</div>
                <div className="pass-price">{p.price_p.toLocaleString()}P <small>/ {p.period_days}일</small></div>
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
                  {busy === tier ? "처리중…" : "시작하기"}
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
  const { t } = useTranslation();
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
      alert(t("pay.test_done", {
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
          <div className="compat-hero-badge">充電</div>
          <h1>크레딧 충전</h1>
          <p>결제는 <b>로그인 후</b> 이용할 수 있어요.</p>
        </header>
        <div className="compat-actions">
          {/* 로그인 후 다시 충전 화면으로 — '충전하려고 로그인했는데 딴 데로 감' 방지(운영자 지적) */}
          <Link className="compat-cta" to="/login?next=%2Fpayments" style={{ textDecoration: "none" }}>🔐 로그인하고 충전하기</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">充電</div>
        <h1>크레딧 충전</h1>
        <p>1 P = 1원 · 기본 질문 = {(me.credit_cost_basic ?? 1900).toLocaleString()} P · 전체보기 = {(me.preview_reveal_cost ?? 900).toLocaleString()} P · 충전 시 <b>광고 숨김</b>이 적용됩니다.</p>
      </header>
      {/* 인라인 스타일 → 클래스. 라벨이 2줄인 카드(연간회원 등) 때문에 '충전' 버튼 높이가 제각각이던 문제를
          .pkg-card 의 flex column + .pkg-buy 의 margin-top:auto 로 하단 정렬한다(운영자 지적). */}
      <div className="pkg-grid">
        {pkgs.map((p) => (
          <div key={p.amount} className="pkg-card">
            <div className="pkg-label">{p.label}</div>
            <div className="pkg-credits">{p.credits.toLocaleString()} P</div>
            <button className="pkg-buy" onClick={() => buy(p)} disabled={busy !== null}>
              {busy === p.amount ? "처리중..." : "충전"}
            </button>
          </div>
        ))}
      </div>
      {err && <div className="compat-err">{err}</div>}

      <PassSection />

      {/* 포인트 원장 — '잔액 줄었는데 쓴 기록이 없다' 오해 차단(패턴 D). 충전·차감·환불 전부 시간순. */}
      <h3 style={{ marginTop: 24, marginBottom: 4 }}>포인트 사용·적립 내역</h3>
      <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--ink-500)" }}>
        충전·차감·환불이 모두 시간순으로 기록돼요. 잔액이 어디에 쓰였는지 여기서 확인할 수 있어요. (기준: 한국시간)
      </p>
      {/* 정합성 대조 — 사용자가 직접 '충전+적립−사용=잔액'을 확인(돈에 관한 화면) */}
      {txnSummary && (
        <div className="ledger-summary">
          <div className="ls-cards">
            <div className="ls-card"><span className="ls-lb">충전(구입)</span><span className="ls-v">+{txnSummary.purchased.toLocaleString()} P</span></div>
            <div className="ls-card"><span className="ls-lb">적립·환불</span><span className="ls-v">+{txnSummary.rewarded.toLocaleString()} P</span></div>
            <div className="ls-card"><span className="ls-lb">사용</span><span className="ls-v ls-minus">−{txnSummary.used.toLocaleString()} P</span></div>
            <div className="ls-card ls-bal"><span className="ls-lb">현재 잔액</span><span className="ls-v">{txnSummary.balance.toLocaleString()} P</span></div>
          </div>
          <div className={`ls-reconcile ${txnSummary.consistent ? "ok" : "bad"}`}>
            {txnSummary.consistent
              ? <>✓ 충전 {txnSummary.purchased.toLocaleString()} + 적립·환불 {txnSummary.rewarded.toLocaleString()} − 사용 {txnSummary.used.toLocaleString()} = <b>{txnSummary.balance.toLocaleString()} P</b> — 내역과 잔액이 정확히 일치합니다.</>
              : <>⚠️ 내역 합({txnSummary.computed_balance.toLocaleString()} P)과 현재 잔액({txnSummary.balance.toLocaleString()} P)이 달라요. 고객센터로 문의해 주세요.</>}
          </div>
        </div>
      )}
      <div style={{ maxHeight: 360, overflowY: "auto", border: "1px solid var(--border, #eee)", borderRadius: 8 }}>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f7f7f7" }}>
              <th style={th}>내용</th>
              <th style={{ ...th, textAlign: "right" }}>변동</th>
              <th style={{ ...th, textAlign: "right" }}>잔액</th>
              <th style={th}>시각</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((t) => (
              <tr key={t.id}>
                <td style={td}>{txnLabel(t)}</td>
                <td style={{ ...td, textAlign: "right", fontWeight: 700, color: t.delta >= 0 ? "var(--brand-600)" : "#c0392b" }}>
                  {t.delta >= 0 ? "+" : "−"}{Math.abs(t.delta).toLocaleString()} P
                </td>
                <td style={{ ...td, textAlign: "right", color: "var(--ink-500)" }}>{t.balance_after.toLocaleString()} P</td>
                <td style={td}>{fmtKSTDateTime(t.created_at)}</td>
              </tr>
            ))}
            {txns.length === 0 && (
              <tr><td style={{ ...td, textAlign: "center", color: "var(--ink-400)" }} colSpan={4}>아직 포인트 내역이 없어요.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 24, marginBottom: 8 }}>충전·결제 내역</h3>
      {/* 상단 월별 필터 — 누르면 그 달 내역만 바로 표시 */}
      {months.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          <button type="button" onClick={() => pickMonth(null)}
                  style={monthChip(selMonth === null)}>전체</button>
          {months.map((m) => {
            const [yy, mm] = m.split("-");
            return (
              <button key={m} type="button" onClick={() => pickMonth(m)} style={monthChip(selMonth === m)}>
                {yy}년 {Number(mm)}월
              </button>
            );
          })}
        </div>
      )}
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>{t("pay.th_order")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("pay.th_amount")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("pay.th_credit")}</th>
            <th style={th}>{t("pay.th_status")}</th>
            <th style={th}>{t("pay.th_time")}</th>
          </tr>
        </thead>
        <tbody>
          {paged.map((h) => (
            <tr key={h.id}>
              <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{h.order_id}</td>
              <td style={{ ...td, textAlign: "right" }}>{h.amount.toLocaleString()}원</td>
              <td style={{ ...td, textAlign: "right", color: h.status === "refunded" ? "var(--ink-400)" : undefined }}>
                {h.status === "refunded"
                  ? <s>+{h.credit_granted.toLocaleString()} P</s>   /* 환불됨 = 적립분 회수됨을 취소선으로 명시 */
                  : `+${h.credit_granted.toLocaleString()} P`}
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
                  {STATUS_KO[h.status] || h.status}
                </span>
              </td>
              <td style={td}>
                {fmtKSTDateTime(h.approved_at || h.created_at)}
              </td>
            </tr>
          ))}
          {paged.length === 0 && (
            <tr><td style={{ ...td, textAlign: "center", color: "var(--ink-400)" }} colSpan={5}>
              {selMonth ? "이 달 결제 내역이 없어요." : "결제 내역이 없어요."}
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
        총 {filtered.length}건{selMonth ? ` (${selMonth.split("-")[0]}년 ${Number(selMonth.split("-")[1])}월)` : ""}
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
