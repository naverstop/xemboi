import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, useMe, setCachedMe } from "../api";
import { fmtKSTDateTime } from "../lib/datetime";

declare global {
  interface Window {
    TossPayments?: any;
  }
}

type Pkg = { amount: number; credits: number; label: string };

export default function PaymentsPage() {
  const nav = useNavigate();
  const me = useMe();
  const [pkgs, setPkgs] = useState<Pkg[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function loadAll() {
    try {
      const r = await api.paymentPackages();
      setPkgs(r.items);
      const h = await api.paymentMyHistory();
      setHistory(h.items);
    } catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { if (me) loadAll(); }, []);

  async function buy(p: Pkg) {
    if (!me) return nav("/login");
    setBusy(p.amount);
    setErr(null);
    try {
      const order = await api.paymentCreateOrder(p.amount);
      // 토스 SDK 가 로드되어 있고 client_key 가 더미가 아니면 위젯 호출
      const isDummy = order.client_key.includes("DUMMY");
      if (!isDummy && window.TossPayments) {
        const toss = window.TossPayments(order.client_key);
        await toss.requestPayment("카드", {
          amount: order.amount,
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
      alert(
        `[테스트모드] ${p.label} 충전 완료\n+${c.credits_granted.toLocaleString()} P → 잔액 ${c.balance.toLocaleString()} P`
      );
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
      <div style={{ padding: 20 }}>
        결제는 로그인 후 이용하세요. <Link to="/login">로그인</Link>
      </div>
    );
  }

  return (
    <div>
      <h2>크레딧 충전</h2>
      <div style={{ color: "#666", marginBottom: 12 }}>
        1 P = 1원 · 질문 1건 = 1,000 P · 더보기 = 500 P · 충전 시 광고 숨김 적용
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12 }}>
        {pkgs.map((p) => (
          <div
            key={p.amount}
            style={{
              border: "1.5px solid var(--brand-200)",
              borderRadius: 12,
              padding: 18,
              textAlign: "center",
              background: "var(--brand-50)",
              boxShadow: "var(--shadow-1)",
            }}
          >
            <div style={{ fontSize: 20, fontWeight: 800, color: "var(--ink-900)" }}>{p.label}</div>
            <div style={{ color: "var(--brand-600)", margin: "8px 0 12px", fontWeight: 700 }}>
              {p.credits.toLocaleString()} P
            </div>
            <button
              onClick={() => buy(p)}
              disabled={busy !== null}
              style={{
                width: "100%",
                padding: "10px 0",
                background: "var(--brand-grad)",
                color: "white",
                border: "none",
                borderRadius: 10,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              {busy === p.amount ? "처리중..." : "충전"}
            </button>
          </div>
        ))}
      </div>
      {err && <div style={{ color: "crimson", marginTop: 12 }}>{err}</div>}

      <h3 style={{ marginTop: 24 }}>결제 내역</h3>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>주문번호</th>
            <th style={{ ...th, textAlign: "right" }}>금액</th>
            <th style={{ ...th, textAlign: "right" }}>크레딧</th>
            <th style={th}>상태</th>
            <th style={th}>시각</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => (
            <tr key={h.id}>
              <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{h.order_id}</td>
              <td style={{ ...td, textAlign: "right" }}>{h.amount.toLocaleString()}원</td>
              <td style={{ ...td, textAlign: "right" }}>+{h.credit_granted.toLocaleString()} P</td>
              <td style={td}>
                <span
                  style={{
                    padding: "2px 6px",
                    background: h.status === "approved" ? "var(--brand-500)" : "#ccc",
                    color: "white",
                    borderRadius: 3,
                    fontSize: 11,
                  }}
                >
                  {h.status}
                </span>
              </td>
              <td style={td}>
                {fmtKSTDateTime(h.approved_at || h.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "6px 8px", borderBottom: "1px solid #ddd" };
const td: React.CSSProperties = { padding: "6px 8px", borderBottom: "1px solid #eee" };
