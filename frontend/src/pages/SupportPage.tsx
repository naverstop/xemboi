/** 고객센터(CONTACT US) — 결제·환불 등 문의 접수 + 내 문의 내역 게시판.
 *
 *  - 접수 즉시 게시판(DB)에 저장되고, 관리자 메일로 알림이 발송된다.
 *  - 환불 분류 선택 시, 로그인 회원은 본인 결제내역에서 주문을 골라 금액을 자동 채운다.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, useMe, type SupportCategory, type SupportTicket } from "../api";
import { COMPANY } from "../lib/company";
import { fmtKSTDate } from "../lib/datetime";

const CATEGORIES: { value: SupportCategory; label: string; hint: string }[] = [
  { value: "refund", label: "환불 요청", hint: "결제한 포인트/상품의 환불을 요청합니다." },
  { value: "payment", label: "결제 오류", hint: "결제는 됐는데 포인트 미지급 등 결제 문제." },
  { value: "account", label: "계정 문의", hint: "로그인·탈퇴·정보수정 등 계정 관련." },
  { value: "etc", label: "기타 문의", hint: "그 밖의 문의·건의 사항." },
];

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
      setErr(e?.message || "문의 접수에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  const shortDate = (iso?: string | null) => fmtKSTDate(iso);

  return (
    <div className="support-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">📨</div>
        <h1>고객센터</h1>
        <p>결제·환불 등 문의를 남겨 주세요. 접수 즉시 담당자에게 전달되며, <b>기재하신 메일</b>로 답변드립니다.</p>
      </header>

      {done ? (
        <div className="card support-done">
          <div className="sd-ico" aria-hidden="true">✅</div>
          <h3>문의가 접수되었어요 (#{done.id})</h3>
          <p>
            <b>{done.category_label}</b> · “{done.title}”<br />
            담당자가 확인 후 <b>{done.contact_email}</b> 로 답변드릴게요.
          </p>
          <div className="support-done-actions">
            <button className="chat-cta" onClick={() => setDone(null)}>새 문의 작성</button>
          </div>
        </div>
      ) : (
        <div className="card support-form">
          <h3 style={{ marginTop: 0 }}>문의 작성</h3>

          <label className="sf-label">문의 유형</label>
          <div className="sf-cats">
            {CATEGORIES.map((c) => (
              <button
                key={c.value}
                type="button"
                className={`sf-cat${category === c.value ? " on" : ""}`}
                onClick={() => setCategory(c.value)}
              >
                {c.label}
              </button>
            ))}
          </div>
          <p className="sf-hint">{CATEGORIES.find((c) => c.value === category)?.hint}</p>

          <div className="sf-grid">
            <div className="sf-field">
              <label className="sf-label">이름/호칭</label>
              <input className="bf-input" placeholder="홍길동" value={contactName} onChange={(e) => setContactName(e.target.value)} />
            </div>
            <div className="sf-field">
              <label className="sf-label">답변 받을 이메일 <i className="req-star">*</i></label>
              <input className="bf-input" type="email" placeholder="you@example.com" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
            </div>
          </div>

          {(category === "refund" || category === "payment") && (
            <div className="sf-grid">
              <div className="sf-field">
                <label className="sf-label">결제 주문 {me && refundablePayments.length > 0 ? "(선택)" : "(주문번호)"}</label>
                {me && refundablePayments.length > 0 ? (
                  <select className="bf-input" value={orderId} onChange={(e) => onPickOrder(e.target.value)}>
                    <option value="">결제 내역에서 선택…</option>
                    {refundablePayments.map((p) => (
                      <option key={p.order_id} value={p.order_id}>
                        {shortDate(p.created_at)} · {p.amount.toLocaleString()}원 · {p.order_id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input className="bf-input" placeholder="주문번호(영수증 참고)" value={orderId} onChange={(e) => setOrderId(e.target.value)} />
                )}
              </div>
              <div className="sf-field">
                <label className="sf-label">결제 금액(원)</label>
                <input className="bf-input" type="number" inputMode="numeric" placeholder="예: 10000" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </div>
            </div>
          )}

          <label className="sf-label">제목 <i className="req-star">*</i></label>
          <input className="bf-input" placeholder="예: 10,000원 충전 환불 요청합니다" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />

          <label className="sf-label" style={{ marginTop: 12 }}>문의 내용 <i className="req-star">*</i></label>
          <textarea className="sf-textarea" rows={6} placeholder="환불/문의 사유를 자세히 적어 주세요. (예: 결제 후 미사용, 중복 결제 등)" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={4000} />

          {!me && (
            <p className="sf-guest">
              비로그인 상태예요. 결제·환불은 <Link to="/login">로그인</Link> 후 결제 내역과 함께 문의하시면 더 빠르게 처리됩니다.
            </p>
          )}
          {err && <div className="err">{err}</div>}

          <div className="chat-start-actions">
            <button className="chat-cta" onClick={submit} disabled={busy || !valid}>
              {busy ? "접수 중…" : "📨 문의 접수"}
            </button>
          </div>
          <p className="sf-foot">
            접수 내용은 답변 목적에 한해 처리됩니다(자세히는 <Link to="/legal/privacy">개인정보처리방침</Link>).
            환불 기준은 <Link to="/legal/refund">환불·청약철회 정책</Link>을 참고해 주세요. 고객센터: {COMPANY.email}
          </p>
        </div>
      )}

      {me && tickets.length > 0 && (
        <div className="card support-board">
          <h3 style={{ marginTop: 0 }}>내 문의 내역</h3>
          <div className="sb-list">
            {tickets.map((t) => (
              <div key={t.id} className="sb-row">
                <div className="sb-main">
                  <span className="sb-cat">{t.category_label}</span>
                  <span className="sb-title">{t.title}</span>
                  <span className="sb-meta">
                    #{t.id} · {shortDate(t.created_at)}
                    {t.amount != null && ` · ${t.amount.toLocaleString()}원`}
                  </span>
                  {t.admin_note && <div className="sb-note">💬 {t.admin_note}</div>}
                </div>
                <span className="sb-status" style={{ background: STATUS_TONE[t.status] || "var(--brand-grad)" }}>
                  {t.status_label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
