import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, setCachedMe } from "../api";
import { fmtNum } from "../lib/money";

export default function PaymentSuccessPage() {
  const { t: tr } = useTranslation();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const [msg, setMsg] = useState(() => tr("misc.pay_confirming"));
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
      setMsg(tr("misc.pay_missing_params"));
      return;
    }
    api.paymentConfirm(paymentKey, orderId, amount)
      .then(async (c) => {
        setOk(true);
        setMsg(
          tr("misc.pay_success", {
            credits: fmtNum(c.credits_granted),
            balance: fmtNum(c.balance),
            pt: tr("pay.pt"),
          })
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
      <h2>{ok === null ? tr("misc.pay_processing") : ok ? tr("misc.pay_done") : tr("misc.pay_failed")}</h2>
      <p>{msg}</p>
      <div style={{ marginTop: 16, display: "flex", gap: 8, justifyContent: "center" }}>
        <button onClick={() => nav("/chat")}>{tr("misc.pay_to_chat")}</button>
        <button onClick={() => nav("/payments")}>{tr("pay.history_title")}</button>
      </div>
    </div>
  );
}

export function PaymentFailPage() {
  const { t: tr } = useTranslation();
  const [sp] = useSearchParams();
  const code = sp.get("code");
  const message = sp.get("message") || tr("misc.pay_fail_msg");
  return (
    <div style={{ maxWidth: 480, margin: "60px auto", textAlign: "center" }}>
      <h2>{tr("misc.pay_failed")}</h2>
      <p>{message}</p>
      {code && <p style={{ color: "#888", fontSize: 12 }}>code: {code}</p>}
      <a href="/payments">{tr("misc.pay_retry")}</a>
    </div>
  );
}
