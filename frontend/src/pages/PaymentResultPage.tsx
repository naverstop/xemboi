import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, setCachedMe } from "../api";

export default function PaymentSuccessPage() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const [msg, setMsg] = useState("결제 승인 처리 중...");
  const [ok, setOk] = useState<boolean | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    const paymentKey = sp.get("paymentKey");
    const orderId = sp.get("orderId");
    const amount = parseInt(sp.get("amount") || "0", 10);
    if (!paymentKey || !orderId || !amount) {
      setOk(false);
      setMsg("필수 파라미터 누락");
      return;
    }
    api.paymentConfirm(paymentKey, orderId, amount)
      .then(async (c) => {
        setOk(true);
        setMsg(
          `+${c.credits_granted.toLocaleString()} P 충전 완료. 잔액: ${c.balance.toLocaleString()} P`
        );
        try { setCachedMe(await api.me()); } catch { /* ignore */ }
      })
      .catch((e) => {
        setOk(false);
        setMsg(e?.message || String(e));
      });
  }, []);

  return (
    <div style={{ maxWidth: 480, margin: "60px auto", textAlign: "center" }}>
      <h2>{ok === null ? "처리 중" : ok ? "결제 완료" : "결제 실패"}</h2>
      <p>{msg}</p>
      <div style={{ marginTop: 16, display: "flex", gap: 8, justifyContent: "center" }}>
        <button onClick={() => nav("/chat")}>대화로</button>
        <button onClick={() => nav("/payments")}>결제 내역</button>
      </div>
    </div>
  );
}

export function PaymentFailPage() {
  const [sp] = useSearchParams();
  const code = sp.get("code");
  const message = sp.get("message") || "결제가 취소되었거나 실패했습니다.";
  return (
    <div style={{ maxWidth: 480, margin: "60px auto", textAlign: "center" }}>
      <h2>결제 실패</h2>
      <p>{message}</p>
      {code && <p style={{ color: "#888", fontSize: 12 }}>code: {code}</p>}
      <a href="/payments">다시 시도</a>
    </div>
  );
}
