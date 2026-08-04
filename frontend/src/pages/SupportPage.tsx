/** 고객센터(CONTACT US) — 결제·환불 등 문의 접수 + 내 문의 내역 게시판.
 *
 *  - 접수 즉시 게시판(DB)에 저장되고, 관리자 메일로 알림이 발송된다.
 *  - 환불 분류 선택 시, 로그인 회원은 본인 결제내역에서 주문을 골라 금액을 자동 채운다.
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { Link } from "react-router-dom";
import { api, useMe, type SupportCategory, type SupportTicket } from "../api";
import { COMPANY } from "../lib/company";
import { fmtKSTDate } from "../lib/datetime";
import PrivacyNotice from "../components/PrivacyNotice";
import { fmtMoney } from "../lib/money";

// 라벨/힌트는 support.cat_<value>[_hint] 로케일 키에서 렌더 시 조회
const CATEGORY_VALUES: SupportCategory[] = ["refund", "payment", "account", "etc"];

const STATUS_TONE: Record<string, string> = {
  received: "var(--grad-info, linear-gradient(135deg,#22b8f0,#0496d8))",
  in_progress: "var(--grad-warning, linear-gradient(135deg,#ffb74d,#fb8c00))",
  resolved: "var(--grad-success, linear-gradient(135deg,#34d399,#10b981))",
  rejected: "linear-gradient(135deg,#e57373,#c62828)",
};

type Pay = {
  id: number; order_id: string; amount: number; credit_granted: number;
  status: string; created_at: string;
};

export default function SupportPage() {
  const me = useMe();
  const { t: tr } = useTranslation();
  const [category, setCategory] = useState<SupportCategory>("refund");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [orderId, setOrderId] = useState("");
  const [amount, setAmount] = useState<string>("");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<SupportTicket | null>(null);

  const [payments, setPayments] = useState<Pay[]>([]);
  const [tickets, setTickets] = useState<SupportTicket[]>([]);

  // 로그인 회원: 이메일/닉네임 자동 채움 + 결제내역·내 문의 불러오기
  useEffect(() => {
    if (!me) return;
    if (me.email && !contactEmail) setContactEmail(me.email);
    if (me.nickname && !contactName) setContactName(me.nickname);
    api.paymentMyHistory().then((r) => setPayments(r.items as Pay[])).catch(() => {});
    refreshTickets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);

  const refreshTickets = () => {
    if (!me) return;
    api.supportMyTickets().then((r) => setTickets(r.items)).catch(() => {});
  };

  // 환불 가능한(승인된) 결제만 드롭다운에 노출
  const refundablePayments = useMemo(
    () => payments.filter((p) => p.status === "approved"),
    [payments]
  );

  const onPickOrder = (oid: string) => {
    setOrderId(oid);
    const p = payments.find((x) => x.order_id === oid);
    if (p) setAmount(String(p.amount));
  };

  const valid = contactEmail.trim() && title.trim() && message.trim();

  async function submit() {
    if (!valid) return;
    setBusy(true);
    setErr(null);
    try {
      const t = await api.supportCreateTicket({
        category,
        contact_email: contactEmail.trim(),
        contact_name: contactName.trim() || undefined,
        order_id: orderId.trim() || undefined,
        amount: amount ? Number(amount) : undefined,
        title: title.trim(),
        message: message.trim(),
      });
      setDone(t);
      setTitle("");
      setMessage("");
      setOrderId("");
      setAmount("");
      refreshTickets();
    } catch (e: any) {
      setErr(e?.message || tr("support.submit_fail"));
    } finally {
      setBusy(false);
    }
  }

  const shortDate = (iso?: string | null) => fmtKSTDate(iso);

  return (
    <div className="support-page">
      <PrivacyNotice variant="tool" />
      <header className="compat-hero">
        <div className="compat-hero-badge">📨</div>
        <h1>{tr("support.hero_title")}</h1>
        <p><Trans i18nKey="support.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      {done ? (
        <div className="card support-done">
          <div className="sd-ico" aria-hidden="true">✅</div>
          <h3>{tr("support.done_title", { id: done.id })}</h3>
          <p>
            <b>{tr(`support.cat_${category}`)}</b> · “{done.title}”<br />
            <Trans i18nKey="support.done_reply" values={{ email: done.contact_email }} components={{ b: <b /> }} />
          </p>
          <div className="support-done-actions">
            <button className="chat-cta" onClick={() => setDone(null)}>{tr("support.new_ticket")}</button>
          </div>
        </div>
      ) : (
        <div className="card support-form">
          <h3 style={{ marginTop: 0 }}>{tr("support.form_title")}</h3>

          <label className="sf-label">{tr("support.field_type")}</label>
          <div className="sf-cats">
            {CATEGORY_VALUES.map((c) => (
              <button
                key={c}
                type="button"
                className={`sf-cat${category === c ? " on" : ""}`}
                onClick={() => setCategory(c)}
              >
                {tr(`support.cat_${c}`)}
              </button>
            ))}
          </div>
          <p className="sf-hint">{tr(`support.cat_${category}_hint`)}</p>

          <div className="sf-grid">
            <div className="sf-field">
              <label className="sf-label">{tr("support.field_name")}</label>
              <input className="bf-input" placeholder={tr("support.name_ph")} value={contactName} onChange={(e) => setContactName(e.target.value)} />
            </div>
            <div className="sf-field">
              <label className="sf-label">{tr("support.field_email")} <i className="req-star">*</i></label>
              <input className="bf-input" type="email" placeholder="you@example.com" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
            </div>
          </div>

          {(category === "refund" || category === "payment") && (
            <div className="sf-grid">
              <div className="sf-field">
                <label className="sf-label">{tr("support.field_order")} {me && refundablePayments.length > 0 ? tr("support.field_order_optional") : tr("support.field_order_manual")}</label>
                {me && refundablePayments.length > 0 ? (
                  <select className="bf-input" value={orderId} onChange={(e) => onPickOrder(e.target.value)}>
                    <option value="">{tr("support.order_select")}</option>
                    {refundablePayments.map((p) => (
                      <option key={p.order_id} value={p.order_id}>
                        {shortDate(p.created_at)} · {fmtMoney(p.amount)} · {p.order_id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input className="bf-input" placeholder={tr("support.order_ph")} value={orderId} onChange={(e) => setOrderId(e.target.value)} />
                )}
              </div>
              <div className="sf-field">
                <label className="sf-label">{tr("support.field_amount")}</label>
                <input className="bf-input" type="number" inputMode="numeric" placeholder={tr("support.amount_ph")} value={amount} onChange={(e) => setAmount(e.target.value)} />
              </div>
            </div>
          )}

          <label className="sf-label">{tr("support.field_subject")} <i className="req-star">*</i></label>
          <input className="bf-input" placeholder={tr("support.title_ph")} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />

          <label className="sf-label" style={{ marginTop: 12 }}>{tr("support.field_message")} <i className="req-star">*</i></label>
          <textarea className="sf-textarea" rows={6} placeholder={tr("support.message_ph")} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={4000} />

          {!me && (
            <p className="sf-guest">
              <Trans i18nKey="support.guest_note" components={{ a: <Link to="/login" /> }} />
            </p>
          )}
          {err && <div className="err">{err}</div>}

          <div className="chat-start-actions">
            <button className="chat-cta" onClick={submit} disabled={busy || !valid}>
              {busy ? tr("support.submitting") : tr("support.submit")}
            </button>
          </div>
          <p className="sf-foot">
            <Trans
              i18nKey="support.foot"
              values={{ email: COMPANY.email }}
              components={{ a: <Link to="/legal/privacy" />, b: <Link to="/legal/refund" /> }}
            />
          </p>
        </div>
      )}

      {me && tickets.length > 0 && (
        <div className="card support-board">
          <h3 style={{ marginTop: 0 }}>{tr("support.board_title")}</h3>
          <div className="sb-list">
            {tickets.map((t) => (
              <div key={t.id} className="sb-row">
                <div className="sb-main">
                  <span className="sb-cat">{tr(`support.cat_${t.category}`)}</span>
                  <span className="sb-title">{t.title}</span>
                  <span className="sb-meta">
                    #{t.id} · {shortDate(t.created_at)}
                    {t.amount != null && ` · ${fmtMoney(t.amount)}`}
                  </span>
                  {t.admin_note && <div className="sb-note">💬 {t.admin_note}</div>}
                </div>
                <span className="sb-status" style={{ background: STATUS_TONE[t.status] || "var(--brand-grad)" }}>
                  {tr(`support.st_${t.status}`)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
