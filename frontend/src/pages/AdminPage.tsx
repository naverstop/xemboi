import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  api,
  AdminStats,
  AdminUser,
  AdminTx,
  type AdminPayment,
  Banner,
  BANNER_SLOTS,
  AnswerTemplate,
  AppSettings,
  useMe,
  type SupportTicket,
  type SupportRecipient,
  type SupportStatus,
  type SiteSettings,
  type TarotAdminCard,
  type ConsultantAdmin,
  type ConsultationSettings,
  type ConsultantSpecialty,
  type ConsultationSettlementRow,
  type SettlementTotals,
} from "../api";
import { fmtKSTDate, fmtKSTDateTime, fmtKSTShort } from "../lib/datetime";

type Tab = "stats" | "users" | "banners" | "billing" | "templates" | "support" | "site" | "tarot" | "consultants" | "settlements";

export default function AdminPage() {
  const me = useMe();
  const [tab, setTab] = useState<Tab>("stats");

  if (!me || me.role !== "admin") {
    return (
      <div style={{ padding: 20 }}>
        <h3>관리자 전용</h3>
        <p>관리자 계정으로 로그인해야 합니다. <Link to="/login">로그인</Link></p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <TabBtn tab="stats" cur={tab} setTab={setTab} label="통계" />
        <TabBtn tab="users" cur={tab} setTab={setTab} label="회원" />
        <TabBtn tab="banners" cur={tab} setTab={setTab} label="배너" />
        <TabBtn tab="billing" cur={tab} setTab={setTab} label="과금/한도" />
        <TabBtn tab="templates" cur={tab} setTab={setTab} label="답변양식" />
        <TabBtn tab="support" cur={tab} setTab={setTab} label="고객센터" />
        <TabBtn tab="site" cur={tab} setTab={setTab} label="운영설정" />
        <TabBtn tab="tarot" cur={tab} setTab={setTab} label="타로 해석" />
        <TabBtn tab="consultants" cur={tab} setTab={setTab} label="입점업체" />
        <TabBtn tab="settlements" cur={tab} setTab={setTab} label="정산" />
      </div>
      {tab === "stats" && <StatsTab />}
      {tab === "users" && <UsersTab />}
      {tab === "banners" && <BannersTab />}
      {tab === "billing" && <BillingTab />}
      {tab === "templates" && <TemplatesTab />}
      {tab === "support" && <SupportTab />}
      {tab === "site" && <SiteTab />}
      {tab === "tarot" && <TarotTab />}
      {tab === "consultants" && <ConsultantsTab />}
      {tab === "settlements" && <SettlementTab />}
    </div>
  );
}

function TabBtn({ tab, cur, setTab, label }: { tab: Tab; cur: Tab; setTab: (t: Tab) => void; label: string }) {
  return (
    <button
      onClick={() => setTab(tab)}
      style={{
        padding: "8px 16px",
        background: tab === cur ? "var(--brand-500)" : "var(--brand-50)",
        color: tab === cur ? "white" : "var(--ink-600)",
        border: tab === cur ? "none" : "1px solid var(--line)",
        borderRadius: 999,
        fontWeight: tab === cur ? 700 : 500,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

// -------- 통계 --------

function StatsTab() {
  const [s, setS] = useState<AdminStats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.adminStats().then(setS).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <div style={{ color: "crimson" }}>{err}</div>;
  if (!s) return <div>로딩...</div>;
  const cards: [string, string | number][] = [
    ["전체 회원", s.total_users],
    ["오늘 가입", `${s.today_signups} (어제 ${s.yesterday_signups})`],
    ["오늘 질문", s.today_questions],
    ["오늘 차감 P", s.today_credits_spent.toLocaleString()],
    ["누적 결제(원)", s.total_revenue_krw.toLocaleString()],
    ["미사용 잔액 P", s.total_outstanding_credits.toLocaleString()],
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
      {cards.map(([k, v]) => (
        <div key={k} style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
          <div style={{ color: "#666", fontSize: 12 }}>{k}</div>
          <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4 }}>{v}</div>
        </div>
      ))}
    </div>
  );
}

// -------- 회원 --------

const PAY_STATUS: Record<string, string> = {
  pending: "대기", approved: "결제완료", failed: "실패", cancelled: "취소", refunded: "환불됨",
};

const USERS_PAGE_SIZE = 20;  // 회원 목록 페이지당 노출 수

function UsersTab() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [sel, setSel] = useState<AdminUser | null>(null);
  const [txs, setTxs] = useState<AdminTx[]>([]);
  const [pays, setPays] = useState<AdminPayment[]>([]);
  const [delta, setDelta] = useState("1000");
  const [reason, setReason] = useState("admin_grant");
  const [busyRefund, setBusyRefund] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [page, setPage] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [consultants, setConsultants] = useState<ConsultantAdmin[]>([]);
  const [desigSpec, setDesigSpec] = useState<ConsultantSpecialty>("saju");

  async function loadConsultants() {
    try { setConsultants((await api.adminConsultants()).items); } catch { /* ignore */ }
  }
  useEffect(() => { loadConsultants(); }, []);
  function consultantOf(email?: string | null) {
    const e = (email || "").toLowerCase();
    return consultants.find((c) => c.login_email.toLowerCase() === e) || null;
  }
  async function designate(u: AdminUser, specialty: ConsultantSpecialty) {
    try { await api.adminDesignateConsultant(u.id, specialty); await loadConsultants(); alert(`${u.email} 을(를) ${CONSULT_SPECIALTY_LABEL[specialty]} 상담사로 지정했어요. 세부 설정은 '입점업체' 탭에서 편집하세요.`); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function revoke(c: ConsultantAdmin) {
    if (!window.confirm(`상담사 지정을 해제할까요? (${c.business_name})\n관련 상담 세션/정산도 함께 삭제됩니다.`)) return;
    try { await api.adminDeleteConsultant(c.id); await loadConsultants(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }

  async function load(p = page) {
    try {
      const r = await api.adminUsers(q || undefined, USERS_PAGE_SIZE, p * USERS_PAGE_SIZE);
      setItems(r.items);
      setTotal(r.total);
      setChecked(new Set());   // 페이지 이동·검색 시 선택 초기화
    } catch (e: any) {
      setErr(String(e));
    }
  }
  useEffect(() => { load(0); }, []);
  function go(p: number) { setPage(p); load(p); }
  const totalPages = Math.max(1, Math.ceil(total / USERS_PAGE_SIZE));

  async function selectUser(u: AdminUser) {
    setSel(u);
    try {
      const [tr, pr] = await Promise.all([
        api.adminUserTransactions(u.id, 30),
        api.adminUserPayments(u.id, 30),
      ]);
      setTxs(tr.items);
      setPays(pr.items);
    } catch (e: any) { setErr(String(e)); }
  }

  async function refund(p: AdminPayment) {
    if (!sel) return;
    const won = p.amount.toLocaleString();
    if (!window.confirm(`주문 ${p.order_id} (결제 ${won}원) 환불\n\n미사용 결제분만 환불됩니다 — 기본제공 포인트·사용분은 환불 대상이 아닙니다.\n토스 결제취소 + 크레딧 회수. (실키 미설정 시 mock)\n계속할까요?`)) return;
    setBusyRefund(p.order_id);
    try {
      const r = await api.adminRefundPayment(p.order_id);
      alert(`환불 완료${r.mock ? " (mock)" : ""}${r.partial ? " · 부분환불" : ""} — ${r.refunded_krw.toLocaleString()}원 환불 / ${r.recovered_credits.toLocaleString()}P 회수`);
      await selectUser(sel);  // 결제·거래내역 갱신
      await load();           // 목록 집계(결제/환불 컬럼) 갱신
    } catch (e: any) {
      alert(`환불 실패: ${e?.message || String(e)}`);
    } finally {
      setBusyRefund(null);
    }
  }

  function toggleCheck(id: number, on: boolean) {
    setChecked((prev) => { const n = new Set(prev); on ? n.add(id) : n.delete(id); return n; });
  }
  function toggleAll(on: boolean) {
    setChecked(on ? new Set(items.map((u) => u.id)) : new Set());
  }
  // 체크 → 환불 I/F: 선택 회원의 '승인' 결제를 토스 결제취소 + 크레딧 회수로 일괄 환불.
  async function refundSelected() {
    const ids = [...checked];
    if (!ids.length) return;
    const plan: { email?: string | null; order: string; amount: number }[] = [];
    for (const id of ids) {
      const u = items.find((x) => x.id === id);
      try {
        const pr = await api.adminUserPayments(id, 50);
        for (const p of pr.items) if (p.refundable) plan.push({ email: u?.email, order: p.order_id, amount: p.amount });
      } catch { /* skip */ }
    }
    if (!plan.length) { alert("선택한 회원 중 환불 가능한(승인된) 결제가 없습니다."); return; }
    const maxTotal = plan.reduce((s, x) => s + x.amount, 0);
    if (!window.confirm(`환불 실행 — 대상 ${ids.length}명 · 결제 ${plan.length}건 (최대 ${maxTotal.toLocaleString()}원)\n\n실제로는 '미사용 결제분'만 환불됩니다 — 기본제공 포인트·사용분은 환불 대상이 아닙니다.\n토스 결제취소 + 크레딧 회수. (실키 미설정 시 mock)\n계속할까요?`)) return;
    setBusyRefund("bulk");
    let ok = 0, fail = 0, refunded = 0;
    for (const x of plan) {
      try { const r = await api.adminRefundPayment(x.order); ok++; refunded += r.refunded_krw || 0; }
      catch { fail++; }
    }
    setBusyRefund(null);
    alert(`환불 완료: ${ok}건 · ${refunded.toLocaleString()}원 환불${fail ? ` · 환불 불가/실패 ${fail}건(결제분 모두 사용 등)` : ""}`);
    setChecked(new Set());
    await load();
    if (sel) await selectUser(sel);
  }

  async function grant() {
    if (!sel) return;
    try {
      const d = parseInt(delta, 10);
      if (!Number.isFinite(d) || d === 0) return alert("0이 아닌 정수 입력");
      const r = await api.adminGrantCredit(sel.id, d, reason);
      alert(`잔액: ${r.balance.toLocaleString()} P`);
      await load();
      await selectUser({ ...sel, balance: r.balance });
    } catch (e: any) {
      alert(e?.message || String(e));
    }
  }

  async function toggleAds(u: AdminUser, next: boolean) {
    try {
      const r = await api.adminSetUserAds(u.id, next);
      setItems((cur) => cur.map((x) => (x.id === u.id ? { ...x, ads_hidden: r.ads_hidden } : x)));
      if (sel?.id === u.id) setSel({ ...sel, ads_hidden: r.ads_hidden });
    } catch (e: any) {
      alert(e?.message || String(e));
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 8, alignItems: "center" }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="이메일/닉네임 검색" />
          <button onClick={() => go(0)}>검색</button>
          <span style={{ color: "#666" }}>총 {total}명</span>
          <button
            onClick={refundSelected}
            disabled={checked.size === 0 || busyRefund !== null}
            title="체크한 회원의 승인 결제를 토스 결제취소 + 크레딧 회수로 환불"
            style={{ marginLeft: "auto", background: checked.size ? "#c0392b" : "#ddd", color: "#fff", border: "none", borderRadius: 6, padding: "6px 12px", cursor: checked.size ? "pointer" : "default", fontWeight: 700 }}
          >
            {busyRefund === "bulk" ? "환불 처리중…" : `💸 선택 환불 (${checked.size})`}
          </button>
        </div>
        {err && <div style={{ color: "crimson" }}>{err}</div>}
        <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f7f7f7" }}>
              <th style={{ ...th, textAlign: "center", width: 26 }}>
                <input
                  type="checkbox"
                  checked={items.length > 0 && checked.size === items.length}
                  ref={(el) => { if (el) el.indeterminate = checked.size > 0 && checked.size < items.length; }}
                  onChange={(e) => toggleAll(e.target.checked)}
                  title="환불 대상(결제 회원) 전체선택"
                />
              </th>
              <th style={th}>ID</th>
              <th style={th}>이메일</th>
              <th style={th}>역할</th>
              <th style={{ ...th, textAlign: "right" }}>기본제공(P)</th>
              <th style={{ ...th, textAlign: "right" }}>결제(원)</th>
              <th style={{ ...th, textAlign: "right" }}>사용(P)</th>
              <th style={{ ...th, textAlign: "right" }}>잔액(P)</th>
              <th style={th}>광고숨김</th>
              <th style={th}>가입</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr
                key={u.id}
                onClick={() => selectUser(u)}
                style={{
                  cursor: "pointer",
                  background: sel?.id === u.id ? "#e8f6f2" : "transparent",
                }}
              >
                <td style={{ ...td, textAlign: "center" }} onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={checked.has(u.id)}
                    onChange={(e) => toggleCheck(u.id, e.target.checked)}
                    title="환불 대상 선택"
                  />
                </td>
                <td style={td}>{u.id}</td>
                <td style={td}>
                  <span style={{ display: "inline-block", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", verticalAlign: "bottom" }} title={u.email}>{u.email}</span>
                  {u.is_premium ? " 👑" : ""}
                </td>
                <td style={td}>
                  {u.role}
                  {consultantOf(u.email) && <span style={{ marginLeft: 4, fontSize: 10, color: "#fff", background: "#6a5cff", borderRadius: 6, padding: "1px 5px" }}>상담사</span>}
                </td>
                <td style={{ ...td, textAlign: "right" }}>{u.granted_free.toLocaleString()}</td>
                <td style={{ ...td, textAlign: "right" }}>
                  {u.paid_krw.toLocaleString()}
                  {u.refunded_krw > 0 && (
                    <span style={{ display: "block", color: "#c0392b", fontSize: 10 }} title="환불 누계">↩{u.refunded_krw.toLocaleString()}</span>
                  )}
                </td>
                <td style={{ ...td, textAlign: "right" }}>{u.spent.toLocaleString()}</td>
                <td style={{ ...td, textAlign: "right" }}>{u.balance.toLocaleString()}</td>
                <td style={td} onClick={(e) => e.stopPropagation()}>
                  <label style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={u.ads_hidden}
                      onChange={(e) => toggleAds(u, e.target.checked)}
                    />
                    <span style={{ fontSize: 11, color: u.ads_hidden ? "#0a7" : "#999" }}>
                      {u.ads_hidden ? "숨김" : "노출"}
                    </span>
                  </label>
                </td>
                <td style={td}>{fmtKSTDate(u.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {totalPages > 1 && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", justifyContent: "center", marginTop: 10 }}>
            <button onClick={() => go(0)} disabled={page <= 0}>« 처음</button>
            <button onClick={() => go(page - 1)} disabled={page <= 0}>‹ 이전</button>
            <span style={{ fontSize: 13, color: "#444", minWidth: 96, textAlign: "center" }}>{page + 1} / {totalPages} 페이지</span>
            <button onClick={() => go(page + 1)} disabled={page >= totalPages - 1}>다음 ›</button>
            <button onClick={() => go(totalPages - 1)} disabled={page >= totalPages - 1}>끝 »</button>
          </div>
        )}
      </div>
      {sel ? (
          <div>
            <h4 style={{ marginTop: 0 }}>{sel.email}</h4>
            <div style={{ color: "#666", fontSize: 13 }}>
              잔액: <strong>{sel.balance.toLocaleString()} P</strong> / 역할: {sel.role} /
              {" "}오늘무료: {sel.daily_free_used_at ? "사용" : "가능"}
            </div>

            <div style={{ marginTop: 12, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>크레딧 조정</div>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={delta}
                  onChange={(e) => setDelta(e.target.value)}
                  placeholder="+충전 / -차감"
                  style={{ width: 100 }}
                />
                <select value={reason} onChange={(e) => setReason(e.target.value)}>
                  <option value="admin_grant">admin_grant</option>
                  <option value="refund">refund</option>
                  <option value="admin_seed">admin_seed</option>
                </select>
                <button onClick={grant}>실행</button>
              </div>
            </div>

            <div style={{ marginTop: 12, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>상담사(입점업체) 지정</div>
              {(() => {
                const c = consultantOf(sel.email);
                return c ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ color: "#6a5cff", fontWeight: 700 }}>상담사 지정됨 · {c.business_name}</span>
                    <span style={{ fontSize: 12, color: "#888" }}>{CONSULT_SPECIALTY_LABEL[c.specialty] || c.specialty} · {c.eff_price_p.toLocaleString()}P/{c.eff_duration_min}분 · 상담 {c.session_count}건{c.rating_avg != null ? ` · ★${c.rating_avg}` : ""}</span>
                    <label style={{ fontSize: 12, color: "#666", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      분야
                      <select value={c.specialty} onChange={(e) => designate(sel, e.target.value as ConsultantSpecialty)}>
                        <option value="saju">사주</option>
                        <option value="tarot">타로</option>
                        <option value="both">사주+타로</option>
                      </select>
                    </label>
                    <button onClick={() => revoke(c)} style={{ color: "crimson", marginLeft: "auto" }}>지정 해제</button>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, color: "#666" }}>이 회원을 상담사로 지정하면 1:1 상담을 진행할 수 있어요.</span>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, color: "#444" }}>
                      분야
                      <select value={desigSpec} onChange={(e) => setDesigSpec(e.target.value as ConsultantSpecialty)}>
                        <option value="saju">사주</option>
                        <option value="tarot">타로</option>
                        <option value="both">사주+타로</option>
                      </select>
                    </label>
                    <button onClick={() => designate(sel, desigSpec)} style={{ marginLeft: "auto", background: "#6a5cff", color: "#fff", border: "none", borderRadius: 6, padding: "6px 14px", fontWeight: 700, cursor: "pointer" }}>상담사로 지정</button>
                  </div>
                );
              })()}
            </div>

            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>결제·환불 내역 ({pays.length})</div>
              {pays.length === 0 ? (
                <div style={{ fontSize: 12, color: "#888" }}>결제 내역이 없습니다.</div>
              ) : (
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "#f7f7f7" }}>
                      <th style={th}>주문</th>
                      <th style={{ ...th, textAlign: "right" }}>금액</th>
                      <th style={th}>상태</th>
                      <th style={th}>일시</th>
                      <th style={{ ...th, textAlign: "center" }}>환불</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pays.map((p) => (
                      <tr key={p.id}>
                        <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{p.order_id}</td>
                        <td style={{ ...td, textAlign: "right" }}>{p.amount.toLocaleString()}</td>
                        <td style={td}>{PAY_STATUS[p.status] || p.status}</td>
                        <td style={td}>{(p.approved_at || p.created_at || "").replace("T", " ").slice(0, 16)}</td>
                        <td style={{ ...td, textAlign: "center" }}>
                          {p.refundable ? (
                            <button
                              onClick={() => refund(p)}
                              disabled={busyRefund === p.order_id}
                              style={{ padding: "2px 10px", fontSize: 11, color: "#fff", background: "#c0392b", border: "none", borderRadius: 4, cursor: "pointer" }}
                            >
                              {busyRefund === p.order_id ? "처리중…" : "환불"}
                            </button>
                          ) : p.status === "refunded" ? (
                            <span style={{ fontSize: 11, color: "#c0392b" }}>
                              환불됨{p.refunded_recovered != null ? ` (${p.refunded_recovered.toLocaleString()}P)` : ""}
                            </span>
                          ) : (
                            <span style={{ fontSize: 11, color: "#bbb" }}>-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <h5 style={{ marginTop: 16 }}>거래 내역 (최근 30)</h5>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "#f7f7f7" }}>
                  <th style={th}>ID</th>
                  <th style={th}>사유</th>
                  <th style={{ ...th, textAlign: "right" }}>Δ</th>
                  <th style={{ ...th, textAlign: "right" }}>잔액</th>
                  <th style={th}>시각</th>
                </tr>
              </thead>
              <tbody>
                {txs.map((t) => (
                  <tr key={t.id}>
                    <td style={td}>{t.id}</td>
                    <td style={td}>{t.reason}</td>
                    <td style={{ ...td, textAlign: "right", color: t.delta > 0 ? "green" : "crimson" }}>
                      {t.delta > 0 ? "+" : ""}{t.delta.toLocaleString()}
                    </td>
                    <td style={{ ...td, textAlign: "right" }}>{t.balance_after.toLocaleString()}</td>
                    <td style={td}>{fmtKSTDateTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ color: "#888", fontSize: 13 }}>표에서 회원을 클릭하면 상세·환불 내역이 아래에 표시됩니다.</div>
        )}
    </div>
  );
}

// -------- 배너 --------

function BannersTab() {
  const [items, setItems] = useState<Banner[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Banner>>({
    slot: "top",
    image_url: "",
    link_url: "",
    title: "",
    weight: 10,
    active: true,
  });

  async function load() {
    try { setItems((await api.adminBanners()).items); }
    catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); }, []);

  async function create() {
    if (!form.image_url) return alert("image_url 필수");
    try {
      await api.adminCreateBanner(form as any);
      setForm({ slot: "top", image_url: "", link_url: "", title: "", weight: 10, active: true });
      await load();
    } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function toggleActive(b: Banner) {
    await api.adminUpdateBanner(b.id, { active: !b.active });
    await load();
  }
  async function del(b: Banner) {
    if (!confirm(`배너 ${b.id} 삭제?`)) return;
    await api.adminDeleteBanner(b.id);
    await load();
  }

  return (
    <div>
      {err && <div style={{ color: "crimson" }}>{err}</div>}
      <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>새 배너</div>
        <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 1fr", gap: 6 }}>
          <select value={form.slot} onChange={(e) => setForm({ ...form, slot: e.target.value })}>
            {BANNER_SLOTS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input
            placeholder="image_url"
            value={form.image_url || ""}
            onChange={(e) => setForm({ ...form, image_url: e.target.value })}
          />
          <input
            placeholder="link_url (선택)"
            value={form.link_url || ""}
            onChange={(e) => setForm({ ...form, link_url: e.target.value })}
          />
          <input
            placeholder="title (선택)"
            value={form.title || ""}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            type="number"
            placeholder="weight"
            value={form.weight ?? 10}
            onChange={(e) => setForm({ ...form, weight: parseInt(e.target.value, 10) || 0 })}
          />
          <button onClick={create}>추가</button>
        </div>
      </div>

      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>ID</th>
            <th style={th}>슬롯</th>
            <th style={th}>제목/이미지</th>
            <th style={th}>가중치</th>
            <th style={th}>활성</th>
            <th style={th}>작업</th>
          </tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id}>
              <td style={td}>{b.id}</td>
              <td style={td}>{b.slot}</td>
              <td style={td}>
                <div>{b.title || "(제목 없음)"}</div>
                <div style={{ color: "#888", fontSize: 11 }}>{b.image_url}</div>
              </td>
              <td style={td}>{b.weight}</td>
              <td style={td}>
                <button onClick={() => toggleActive(b)}>{b.active ? "ON" : "OFF"}</button>
              </td>
              <td style={td}>
                <button onClick={() => del(b)} style={{ color: "crimson" }}>삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "5px 6px", borderBottom: "1px solid #ddd", whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "5px 6px", borderBottom: "1px solid #eee", whiteSpace: "nowrap" };

// -------- 입점업체(1:1 상담사) --------

const CONSULT_SPECIALTY_LABEL: Record<string, string> = { saju: "사주", tarot: "타로", both: "사주+타로" };
const CONSULT_PRESENCE_LABEL: Record<string, string> = { online: "대기중", busy: "상담중", offline: "오프라인" };

function ConsultantsTab() {
  const [items, setItems] = useState<ConsultantAdmin[]>([]);
  const [settings, setSettings] = useState<ConsultationSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const emptyForm = {
    login_email: "", business_name: "", specialty: "saju" as ConsultantSpecialty,
    intro: "", rate_p: "", duration_min: "", commission_pct: "", sort_order: "100", is_active: true,
  };
  const [form, setForm] = useState<typeof emptyForm>(emptyForm);

  async function load() {
    try {
      const [c, s] = await Promise.all([api.adminConsultants(), api.adminGetConsultationSettings()]);
      setItems(c.items); setSettings(s.settings);
    } catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); }, []);

  function toNum(v: any): number | null {
    const s = String(v).trim();
    if (s === "") return null;
    const n = Number(s);
    return isNaN(n) ? null : n;
  }

  async function submit() {
    setErr(null); setMsg(null);
    const body = {
      business_name: form.business_name.trim(),
      specialty: form.specialty,
      intro: form.intro?.trim() || null,
      rate_p: toNum(form.rate_p),
      duration_min: toNum(form.duration_min),
      commission_pct: toNum(form.commission_pct),
      sort_order: toNum(form.sort_order) ?? 100,
      is_active: !!form.is_active,
    };
    try {
      if (editingId) {
        await api.adminUpdateConsultant(editingId, body);
        setMsg("수정되었습니다.");
      } else {
        if (!form.login_email.trim() || !body.business_name) { alert("입점 ID(이메일)와 업체명은 필수예요."); return; }
        await api.adminCreateConsultant({ login_email: form.login_email.trim(), ...body });
        setMsg("등록되었습니다.");
      }
      cancelEdit();
      await load();
    } catch (e: any) { setErr(e?.message || String(e)); }
  }

  function startEdit(c: ConsultantAdmin) {
    setEditingId(c.id);
    setForm({
      login_email: c.login_email,
      business_name: c.business_name,
      specialty: c.specialty,
      intro: c.intro || "",
      rate_p: c.rate_p == null ? "" : String(c.rate_p),
      duration_min: c.duration_min_raw == null ? "" : String(c.duration_min_raw),
      commission_pct: c.commission_pct_raw == null ? "" : String(c.commission_pct_raw),
      sort_order: String(c.sort_order),
      is_active: c.is_active,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function cancelEdit() { setEditingId(null); setForm(emptyForm); }

  async function toggleActive(c: ConsultantAdmin) {
    try { await api.adminUpdateConsultant(c.id, { is_active: !c.is_active }); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function del(c: ConsultantAdmin) {
    if (!confirm(`입점업체 "${c.business_name}" 을(를) 삭제할까요? 관련 세션/정산도 함께 삭제됩니다.`)) return;
    try { await api.adminDeleteConsultant(c.id); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function uploadSign(c: ConsultantAdmin, file: File) {
    const fd = new FormData(); fd.append("file", file);
    try { await api.adminUploadSignboard(c.id, fd); setMsg("간판 이미지를 등록했어요."); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function saveSettings() {
    if (!settings) return;
    setErr(null); setMsg(null);
    try {
      const res = await api.adminPatchConsultationSettings(settings);
      setSettings(res.settings); setMsg("전역 설정을 저장했어요.");
    } catch (e: any) { setErr(e?.message || String(e)); }
  }

  const inp: React.CSSProperties = { padding: "6px 8px", border: "1px solid var(--line)", borderRadius: 6, width: "100%", boxSizing: "border-box" };
  const box: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 14, marginBottom: 16 };
  const fld: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 3, fontSize: 12, color: "var(--ink-600)" };

  return (
    <div>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}
      {msg && <div style={{ color: "seagreen", marginBottom: 8 }}>{msg}</div>}

      {/* 전역 기본값 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>전역 기본값</div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 10 }}>
          상담사별 개별 설정이 비어 있으면 이 값이 적용돼요. 정산 = 매출 × (1−수수료%) × (1−세율%).
        </div>
        {settings && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 10 }}>
            <NumField label="기본 단가(P)" value={settings.consultation_default_price_p}
              onChange={(v) => setSettings({ ...settings, consultation_default_price_p: v })} />
            <NumField label="기본 상담시간(분)" value={settings.consultation_default_duration_min}
              onChange={(v) => setSettings({ ...settings, consultation_default_duration_min: v })} />
            <NumField label="플랫폼 수수료(%)" value={settings.consultation_commission_pct}
              onChange={(v) => setSettings({ ...settings, consultation_commission_pct: v })} />
            <NumField label="원천징수 세율(%)" step="0.1" value={settings.consultation_tax_pct}
              onChange={(v) => setSettings({ ...settings, consultation_tax_pct: v })} />
            <NumField label="노쇼 타임아웃(초)" value={settings.consultation_no_show_timeout_sec}
              onChange={(v) => setSettings({ ...settings, consultation_no_show_timeout_sec: v })} />
            <NumField label="연장 경고(초 전)" value={settings.consultation_extend_warn_sec}
              onChange={(v) => setSettings({ ...settings, consultation_extend_warn_sec: v })} />
            <NumField label="대화 보관(일)" value={settings.consultation_retention_days}
              onChange={(v) => setSettings({ ...settings, consultation_retention_days: v })} />
          </div>
        )}
        <button onClick={saveSettings} style={{ marginTop: 10 }}>전역 설정 저장</button>
      </div>

      {/* 등록/수정 폼 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>{editingId ? `입점업체 수정 #${editingId}` : "새 입점업체 등록"}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <label style={fld}>입점 ID (이메일) <span style={{ color: "#c00" }}>*필수</span>
            <input style={inp} placeholder="예: master@example.com" value={form.login_email} disabled={!!editingId}
              onChange={(e) => setForm({ ...form, login_email: e.target.value })} />
          </label>
          <label style={fld}>업체명 (간판) <span style={{ color: "#c00" }}>*필수</span>
            <input style={inp} placeholder="예: 김도사 사주원" value={form.business_name}
              onChange={(e) => setForm({ ...form, business_name: e.target.value })} />
          </label>
          <label style={fld}>분야
            <select style={inp} value={form.specialty}
              onChange={(e) => setForm({ ...form, specialty: e.target.value as ConsultantSpecialty })}>
              <option value="saju">사주</option>
              <option value="tarot">타로</option>
              <option value="both">사주+타로</option>
            </select>
          </label>
          <label style={fld}>노출 순서 (목록에서 보이는 위치)
            <select style={inp} value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })}>
              <option value="0">맨 위</option>
              <option value="50">위쪽</option>
              <option value="100">보통 (기본)</option>
              <option value="200">아래쪽</option>
              <option value="1000">맨 아래</option>
            </select>
          </label>
          <label style={fld}>개별 단가 (P)
            <input style={inp} type="number" placeholder="비우면 전역 기본값 적용" value={form.rate_p}
              onChange={(e) => setForm({ ...form, rate_p: e.target.value })} />
          </label>
          <label style={fld}>개별 상담시간 (분)
            <input style={inp} type="number" placeholder="비우면 전역 기본값 적용" value={form.duration_min}
              onChange={(e) => setForm({ ...form, duration_min: e.target.value })} />
          </label>
          <label style={fld}>개별 수수료 (%)
            <input style={inp} type="number" placeholder="비우면 전역 기본값 적용" value={form.commission_pct}
              onChange={(e) => setForm({ ...form, commission_pct: e.target.value })} />
          </label>
          <label style={{ ...fld, flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "end", paddingBottom: 8 }}>
            <input type="checkbox" checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 활성 (사용자에게 노출)
          </label>
        </div>
        <label style={{ ...fld, marginTop: 10 }}>소개 (선택 · 사용자 카드에 표시)
          <textarea style={{ ...inp, minHeight: 54 }} placeholder="예: 20년 경력 · 진로/재물/인연 전문"
            value={form.intro} onChange={(e) => setForm({ ...form, intro: e.target.value })} />
        </label>
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <button onClick={submit}>{editingId ? "수정 저장" : "등록"}</button>
          {editingId && <button onClick={cancelEdit} style={{ color: "#666" }}>취소</button>}
        </div>
      </div>

      {/* 목록 */}
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>간판</th>
            <th style={th}>업체명 / 입점ID</th>
            <th style={th}>분야</th>
            <th style={th}>단가·시간</th>
            <th style={th}>수수료</th>
            <th style={th}>상태</th>
            <th style={th}>실적(세션/매출/정산대기)</th>
            <th style={th}>활성</th>
            <th style={th}>작업</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id}>
              <td style={td}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                  {c.signboard_image_url
                    ? <img src={c.signboard_image_url} alt="" style={{ width: 44, height: 44, borderRadius: 8, objectFit: "cover" }} />
                    : <span style={{ width: 44, height: 44, borderRadius: 8, background: "#f0eef8", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>🪧</span>}
                  <label style={{ fontSize: 10, color: "var(--brand-600)", cursor: "pointer" }}>
                    업로드
                    <input type="file" accept="image/*" style={{ display: "none" }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadSign(c, f); e.currentTarget.value = ""; }} />
                  </label>
                </div>
              </td>
              <td style={td}>
                <div style={{ fontWeight: 700 }}>{c.business_name}</div>
                <div style={{ color: "#888", fontSize: 11 }}>
                  {c.login_email} {c.linked ? <span style={{ color: "seagreen" }}>· 연결됨</span> : <span style={{ color: "#c26a00" }}>· 미가입</span>}
                </div>
              </td>
              <td style={td}>{CONSULT_SPECIALTY_LABEL[c.specialty] || c.specialty}</td>
              <td style={td}>{c.eff_price_p.toLocaleString()}P · {c.eff_duration_min}분</td>
              <td style={td}>{c.eff_commission_pct}%</td>
              <td style={td}>{CONSULT_PRESENCE_LABEL[c.presence] || c.presence}</td>
              <td style={td}>
                {c.stats.sessions}건 · {c.stats.revenue_p.toLocaleString()}P · {c.stats.payout_pending_p.toLocaleString()}P
              </td>
              <td style={td}>
                <button onClick={() => toggleActive(c)}>{c.is_active ? "ON" : "OFF"}</button>
              </td>
              <td style={td}>
                <button onClick={() => startEdit(c)}>수정</button>{" "}
                <button onClick={() => del(c)} style={{ color: "crimson" }}>삭제</button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td style={td} colSpan={9}>등록된 입점업체가 없어요.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function NumField({ label, value, step, onChange }: { label: string; value: number; step?: string; onChange: (v: number) => void }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 12, color: "var(--ink-600)" }}>
      {label}
      <input type="number" step={step} value={value}
        onChange={(e) => onChange(step ? parseFloat(e.target.value) || 0 : parseInt(e.target.value, 10) || 0)}
        style={{ padding: "6px 8px", border: "1px solid var(--line)", borderRadius: 6 }} />
    </label>
  );
}

// -------- 정산 실지급 뷰 --------

function SumCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ flex: "1 1 160px", border: "1px solid #eee", borderRadius: 10, padding: "12px 14px" }}>
      <div style={{ fontSize: 12, color: "#888" }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: color || "var(--ink-900)" }}>{value}</div>
    </div>
  );
}

function SettlementTab() {
  const [rows, setRows] = useState<ConsultationSettlementRow[]>([]);
  const [totals, setTotals] = useState<SettlementTotals | null>(null);
  const [consultants, setConsultants] = useState<ConsultantAdmin[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "pending" | "settled">("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    try {
      const [s, c] = await Promise.all([
        api.adminSettlements(undefined, statusFilter || undefined),
        api.adminConsultants(),
      ]);
      setRows(s.items); setTotals(s.totals); setConsultants(c.items);
    } catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); }, [statusFilter]);

  const won = (n: number) => `${n.toLocaleString()}원`;

  async function settle(r: ConsultationSettlementRow) {
    try { await api.adminSettleSettlement(r.id); await load(); } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function unsettle(r: ConsultationSettlementRow) {
    try { await api.adminUnsettleSettlement(r.id); await load(); } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function settleAll(c: ConsultantAdmin) {
    if (!confirm(`${c.business_name} 정산대기 ${won(c.stats.payout_pending_p)}을(를) 일괄 실지급 처리할까요?`)) return;
    try {
      const r = await api.adminSettleAllConsultant(c.id);
      setMsg(`${c.business_name}: ${r.settled}건 · ${won(r.total_payout_p)} 정산 완료`);
      await load();
    } catch (e: any) { alert(e?.message || String(e)); }
  }

  const pendingConsultants = consultants.filter((c) => c.stats.payout_pending_p > 0);
  const box: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 14, marginBottom: 16 };

  return (
    <div>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}
      {msg && <div style={{ color: "seagreen", marginBottom: 8 }}>{msg}</div>}
      <div style={{ fontSize: 12, color: "#888", marginBottom: 12 }}>
        1P = 1원. 실지급 = 매출 × (1−수수료%) × (1−세율%). 프리랜서 3.3% 원천징수 반영. 실제 계좌 이체 후 ‘정산 완료’로 처리하세요.
      </div>

      {totals && (
        <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <SumCard label="총 매출" value={won(totals.revenue_p)} />
          <SumCard label="정산 대기 (실지급)" value={won(totals.payout_pending_p)} color="#c26a00" />
          <SumCard label="정산 완료 (실지급)" value={won(totals.payout_settled_p)} color="#1a8f4c" />
        </div>
      )}

      {pendingConsultants.length > 0 && (
        <div style={box}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>상담사별 정산 대기 · 일괄 처리</div>
          {pendingConsultants.map((c) => (
            <div key={c.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #f0f0f4" }}>
              <span>{c.business_name} <span style={{ color: "#888", fontSize: 12 }}>· {c.stats.sessions}건</span></span>
              <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <b style={{ color: "#c26a00" }}>{won(c.stats.payout_pending_p)}</b>
                <button onClick={() => settleAll(c)}>일괄 정산</button>
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginBottom: 10 }}>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "" | "pending" | "settled")}>
          <option value="">전체</option>
          <option value="pending">정산 대기</option>
          <option value="settled">정산 완료</option>
        </select>
      </div>

      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>상담사</th>
            <th style={th}>매출</th>
            <th style={th}>수수료</th>
            <th style={th}>과세대상</th>
            <th style={th}>원천징수</th>
            <th style={th}>실지급</th>
            <th style={th}>상태</th>
            <th style={th}>정산일</th>
            <th style={th}>처리</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={td}>{r.consultant_name || r.consultant_id}</td>
              <td style={td}>{won(r.revenue_p)}</td>
              <td style={td}>{won(r.commission_p)} <span style={{ color: "#aaa" }}>({r.commission_pct}%)</span></td>
              <td style={td}>{won(r.taxable_p)}</td>
              <td style={td}>{won(r.tax_p)} <span style={{ color: "#aaa" }}>({r.tax_pct}%)</span></td>
              <td style={{ ...td, fontWeight: 800 }}>{won(r.payout_p)}</td>
              <td style={td}>{r.status === "settled" ? <span style={{ color: "#1a8f4c" }}>완료</span> : <span style={{ color: "#c26a00" }}>대기</span>}</td>
              <td style={td}>{r.settled_at ? fmtKSTDate(r.settled_at) : "—"}</td>
              <td style={td}>
                {r.status === "pending"
                  ? <button onClick={() => settle(r)}>정산 완료</button>
                  : <button onClick={() => unsettle(r)} style={{ color: "#666" }}>취소</button>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td style={td} colSpan={9}>정산 내역이 없어요.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// -------- 과금/한도 설정 --------

function BillingTab() {
  const [s, setS] = useState<AppSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    try { setS((await api.adminGetSettings()).settings); }
    catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    if (!s) return;
    setSaving(true); setMsg(null); setErr(null);
    try {
      const res = await api.adminPatchSettings(s);
      setS(res.settings);
      setMsg("저장되었습니다.");
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  if (err && !s) return <div style={{ color: "crimson" }}>{err}</div>;
  if (!s) return <div>로딩...</div>;

  return (
    <div style={{ maxWidth: 520 }}>
      <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 16, display: "grid", gap: 12 }}>
        <Field label="무료 질문 횟수">
          <input
            type="number"
            value={s.free_quota_count}
            onChange={(e) => setS({ ...s, free_quota_count: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label="무료 횟수 리셋 주기">
          <select
            value={s.free_quota_reset}
            onChange={(e) => setS({ ...s, free_quota_reset: e.target.value as AppSettings["free_quota_reset"] })}
          >
            <option value="none">리셋 없음(누적 소진)</option>
            <option value="daily">매일</option>
            <option value="monthly">매월</option>
          </select>
        </Field>
        <Field label="기본 질문 비용 (P)">
          <input
            type="number"
            value={s.credit_cost_basic}
            onChange={(e) => setS({ ...s, credit_cost_basic: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label="심화 질문 비용 (P)">
          <input
            type="number"
            value={s.credit_cost_deep}
            onChange={(e) => setS({ ...s, credit_cost_deep: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label="미리보기 전체공개 비용 (P)">
          <input
            type="number"
            value={s.preview_reveal_cost}
            onChange={(e) => setS({ ...s, preview_reveal_cost: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label="미리보기 표시 글자수 (무료 맛보기 분량)">
          <input
            type="number"
            value={s.preview_max_chars}
            onChange={(e) => setS({ ...s, preview_max_chars: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label="피드백 리워드 비율 (%)">
          <input
            type="number"
            value={s.feedback_reward_pct}
            onChange={(e) => setS({ ...s, feedback_reward_pct: Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0)) })}
          />
        </Field>
        <Field label="피드백 리워드 일일 상한 (P)">
          <input
            type="number"
            value={s.feedback_reward_daily_cap}
            onChange={(e) => setS({ ...s, feedback_reward_daily_cap: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label="외부 AI 보강 사용">
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={s.external_llm_enabled}
              onChange={(e) => setS({ ...s, external_llm_enabled: e.target.checked })}
            />
            {s.external_llm_enabled ? "사용" : "미사용"}
          </label>
        </Field>

        <div style={{ borderTop: "1px solid #eee", marginTop: 4, paddingTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#333", marginBottom: 4 }}>
            프리미엄 메뉴 입장료 (생성 시 1회 차감 · 사주 상담 제외)
          </div>
          <div style={{ fontSize: 12, color: "#777", marginBottom: 10 }}>
            추가질문은 위 기본/심화 비용(1,000P/3,000P)으로 별도 차감됩니다.
            할인%를 적용하면 5개 메뉴 모두에 반영됩니다(행사용).
          </div>
        </div>
        <Field label="행사 할인 (%)">
          <input
            type="number"
            min={0}
            max={100}
            value={s.premium_entry_discount_pct}
            onChange={(e) =>
              setS({ ...s, premium_entry_discount_pct: Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0)) })
            }
          />
        </Field>
        {([
          ["entry_cost_compat", "궁합 입장료 (P)"],
          ["entry_cost_taekil", "택일 입장료 (P)"],
          ["entry_cost_jakmyeong", "작명 입장료 (P)"],
          ["entry_cost_gaemyeong", "개명 입장료 (P)"],
          ["entry_cost_aho", "아호 입장료 (P)"],
          ["entry_cost_tarot", "타로 입장료 (P)"],
        ] as [keyof AppSettings, string][]).map(([key, label]) => {
          const base = (s[key] as number) || 0;
          const disc = s.premium_entry_discount_pct || 0;
          const eff = Math.max(0, Math.round((base * (100 - disc)) / 100));
          return (
            <Field key={key} label={label}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="number"
                  min={0}
                  value={base}
                  onChange={(e) => setS({ ...s, [key]: parseInt(e.target.value, 10) || 0 })}
                />
                {disc > 0 && (
                  <span style={{ fontSize: 12, color: "crimson" }}>
                    → 적용가 {eff.toLocaleString()}P
                  </span>
                )}
              </div>
            </Field>
          );
        })}

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={save} disabled={saving}>{saving ? "저장중..." : "저장"}</button>
          {msg && <span style={{ color: "green", fontSize: 13 }}>{msg}</span>}
          {err && <span style={{ color: "crimson", fontSize: 13 }}>{err}</span>}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", alignItems: "center", gap: 8 }}>
      <label style={{ fontSize: 13, color: "#444" }}>{label}</label>
      <div>{children}</div>
    </div>
  );
}

// -------- 답변양식(시스템 프롬프트) 관리 --------

function TemplatesTab() {
  const [items, setItems] = useState<AnswerTemplate[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<AnswerTemplate | null>(null);
  const [form, setForm] = useState<{ name: string; body: string; active: boolean }>({
    name: "", body: "", active: false,
  });

  async function load() {
    try { setItems((await api.adminTemplates()).items); }
    catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); }, []);

  function startEdit(t: AnswerTemplate) {
    setEditing(t);
    setForm({ name: t.name, body: t.body, active: t.active });
  }
  function startNew() {
    setEditing(null);
    setForm({ name: "", body: "", active: false });
  }

  async function save() {
    if (!form.name.trim() || !form.body.trim()) return alert("이름과 내용을 입력하세요.");
    try {
      if (editing) {
        await api.adminUpdateTemplate(editing.id, form);
      } else {
        await api.adminCreateTemplate(form);
      }
      startNew();
      await load();
    } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function activate(t: AnswerTemplate) {
    await api.adminActivateTemplate(t.id);
    await load();
  }
  async function del(t: AnswerTemplate) {
    if (!confirm(`양식 "${t.name}" v${t.version} 삭제?`)) return;
    await api.adminDeleteTemplate(t.id);
    if (editing?.id === t.id) startNew();
    await load();
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      <div>
        {err && <div style={{ color: "crimson" }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <strong>답변양식 목록</strong>
          <button onClick={startNew}>+ 새 양식</button>
        </div>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f7f7f7" }}>
              <th style={th}>이름</th>
              <th style={th}>버전</th>
              <th style={th}>활성</th>
              <th style={th}>작업</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} style={editing?.id === t.id ? { background: "#eef9f6" } : undefined}>
                <td style={td}>{t.name}</td>
                <td style={td}>v{t.version}</td>
                <td style={td}>{t.active ? "✅" : ""}</td>
                <td style={td}>
                  <button onClick={() => startEdit(t)}>편집</button>{" "}
                  {!t.active && <button onClick={() => activate(t)}>활성화</button>}{" "}
                  <button onClick={() => del(t)} style={{ color: "crimson" }}>삭제</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td style={td} colSpan={4}>등록된 양식이 없습니다. 기본 양식이 사용됩니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>{editing ? `편집: ${editing.name} v${editing.version}` : "새 양식"}</div>
        <input
          style={{ width: "100%", marginBottom: 8 }}
          placeholder="양식 이름"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <textarea
          style={{ width: "100%", minHeight: 240, fontFamily: "inherit", fontSize: 13 }}
          placeholder="시스템 프롬프트 본문"
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
        />
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: "8px 0" }}>
          <input
            type="checkbox"
            checked={form.active}
            onChange={(e) => setForm({ ...form, active: e.target.checked })}
          />
          저장 시 활성화(다른 양식 비활성화)
        </label>
        <div>
          <button onClick={save}>{editing ? "수정 저장" : "추가"}</button>
        </div>
      </div>
    </div>
  );
}

// -------- 고객센터 (문의 게시판 + 메일 수신자 CRUD) --------
const SUPPORT_STATUSES: { value: SupportStatus; label: string }[] = [
  { value: "received", label: "접수" },
  { value: "in_progress", label: "처리중" },
  { value: "resolved", label: "처리완료" },
  { value: "rejected", label: "반려" },
];

function SupportTab() {
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [filter, setFilter] = useState<SupportStatus | "">("");
  const [recipients, setRecipients] = useState<SupportRecipient[]>([]);
  const [newEmail, setNewEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState<Record<number, string>>({});

  const loadTickets = () =>
    api.adminSupportTickets(filter || undefined, 100, 0).then((r) => setTickets(r.items)).catch((e) => setErr(String(e?.message || e)));
  const loadRecipients = () =>
    api.adminSupportRecipients().then((r) => setRecipients(r.items)).catch(() => {});

  useEffect(() => { loadTickets(); /* eslint-disable-next-line */ }, [filter]);
  useEffect(() => { loadRecipients(); }, []);

  async function setStatus(id: number, status: SupportStatus) {
    try { await api.adminSupportUpdateTicket(id, { status }); loadTickets(); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }
  async function saveNote(id: number) {
    try { await api.adminSupportUpdateTicket(id, { admin_note: noteDraft[id] ?? "" }); loadTickets(); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }
  // 환불 요청 승인 → 실제 환불 자동 실행(주문번호 연결분). 토스 결제취소 + 크레딧 회수 + 처리완료.
  async function refundTicket(t: SupportTicket) {
    if (!t.order_id) return;
    const won = t.amount != null ? `${t.amount.toLocaleString()}원 ` : "";
    if (!window.confirm(`#${t.id} 환불 승인 — 주문 ${t.order_id} ${won}을(를) 실제 환불할까요?\n토스 결제취소 + 크레딧 회수가 실행되고, 문의는 '처리완료'로 전환됩니다. (토스 실키 미설정 시 mock)`)) return;
    try {
      const r = await api.adminSupportRefundTicket(t.id);
      alert(`환불 완료${r.refund.mock ? " (mock)" : ""} — 회수 ${r.refund.recovered_credits.toLocaleString()}P`);
      loadTickets();
    } catch (e: any) {
      alert(`환불 실패: ${e?.message || String(e)}`);
    }
  }
  async function addRecipient() {
    const email = newEmail.trim();
    if (!email) return;
    try { await api.adminSupportAddRecipient(email); setNewEmail(""); loadRecipients(); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }
  async function toggleRecipient(r: SupportRecipient) {
    try { await api.adminSupportSetRecipient(r.id, !r.active); loadRecipients(); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }
  async function delRecipient(r: SupportRecipient) {
    if (!window.confirm(`수신자 "${r.email}" 를 삭제할까요?`)) return;
    try { await api.adminSupportDeleteRecipient(r.id); loadRecipients(); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }

  const shortDt = (iso?: string | null) => fmtKSTShort(iso);

  return (
    <div>
      {err && <div className="err" style={{ marginBottom: 12 }}>{err}</div>}

      {/* 메일 수신자 CRUD */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>문의 알림 메일 수신자</h3>
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          새 문의가 접수되면 아래 <b>활성</b> 메일로 알림이 발송됩니다. (SMTP 미설정 시 서버 로그로 대체)
        </p>
        <div style={{ display: "flex", gap: 8, margin: "10px 0" }}>
          <input
            className="bf-input" type="email" placeholder="admin@example.com" value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addRecipient(); }}
            style={{ maxWidth: 320 }}
          />
          <button onClick={addRecipient}>추가</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {recipients.length === 0 && <div style={{ fontSize: 13, color: "var(--ink-400)" }}>등록된 수신자가 없습니다.</div>}
          {recipients.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
              <span style={{ flex: 1, color: r.active ? "var(--ink-900)" : "var(--ink-400)", textDecoration: r.active ? "none" : "line-through" }}>
                {r.email}
              </span>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={r.active} onChange={() => toggleRecipient(r)} /> 활성
              </label>
              <button className="ghost" style={{ color: "#c0392b" }} onClick={() => delRecipient(r)}>삭제</button>
            </div>
          ))}
        </div>
      </div>

      {/* 문의 게시판 */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0 }}>문의 게시판 ({tickets.length})</h3>
          <select value={filter} onChange={(e) => setFilter(e.target.value as SupportStatus | "")} style={{ maxWidth: 160 }}>
            <option value="">전체 상태</option>
            {SUPPORT_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
          {tickets.length === 0 && <div style={{ fontSize: 13, color: "var(--ink-400)" }}>접수된 문의가 없습니다.</div>}
          {tickets.map((t) => (
            <div key={t.id} style={{ border: "1px solid var(--line)", borderRadius: 10, padding: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <div style={{ fontWeight: 700 }}>
                  #{t.id} [{t.category_label}] {t.title}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-400)" }}>{shortDt(t.created_at)}</div>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-600)", margin: "4px 0" }}>
                {t.contact_name ? `${t.contact_name} · ` : ""}{t.contact_email}
                {t.user_id != null ? ` · 회원ID ${t.user_id}` : " · 비로그인"}
                {t.order_id ? ` · 주문 ${t.order_id}` : ""}
                {t.amount != null ? ` · ${t.amount.toLocaleString()}원` : ""}
              </div>
              <div style={{ whiteSpace: "pre-wrap", fontSize: 13, color: "var(--ink-900)", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", margin: "6px 0" }}>
                {t.message}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: 12, color: "var(--ink-400)" }}>상태:</span>
                {SUPPORT_STATUSES.map((s) => (
                  <button
                    key={s.value}
                    onClick={() => setStatus(t.id, s.value)}
                    style={{
                      padding: "4px 10px", borderRadius: 999, fontSize: 12, cursor: "pointer",
                      border: t.status === s.value ? "none" : "1px solid var(--line)",
                      background: t.status === s.value ? "var(--brand-500)" : "var(--surface)",
                      color: t.status === s.value ? "#fff" : "var(--ink-600)",
                      fontWeight: t.status === s.value ? 700 : 500,
                    }}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              {t.order_id && t.status !== "resolved" && (
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <button
                    onClick={() => refundTicket(t)}
                    style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, color: "#fff", background: "#c0392b", border: "none", borderRadius: 6, cursor: "pointer" }}
                  >
                    💸 환불 승인·실행 (주문 {t.order_id})
                  </button>
                  <span style={{ fontSize: 11, color: "var(--ink-400)" }}>
                    토스 결제취소 + 크레딧 회수 자동 실행 → 처리완료 전환
                  </span>
                </div>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <input
                  className="bf-input"
                  placeholder="처리 메모(사용자 화면에 표시됨) — 예: 6/22 환불 완료"
                  value={noteDraft[t.id] ?? t.admin_note ?? ""}
                  onChange={(e) => setNoteDraft((d) => ({ ...d, [t.id]: e.target.value }))}
                  style={{ flex: 1 }}
                />
                <button onClick={() => saveNote(t.id)}>메모 저장</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// -------- 운영설정 (사업자 정보 · 약관 버전/본문 · 메일 SMTP) --------
type SK = keyof SiteSettings;
const BIZ_FIELDS: { key: SK; label: string; ph?: string }[] = [
  { key: "service_name", label: "서비스명", ph: "예: 인생상담 친구" },
  { key: "biz_name", label: "상호", ph: "예: ○○ 사주연구소" },
  { key: "biz_ceo", label: "대표자" },
  { key: "biz_reg_no", label: "사업자등록번호", ph: "123-45-67890" },
  { key: "biz_mailorder_no", label: "통신판매업 신고번호", ph: "2026-서울강남-01234" },
  { key: "biz_address", label: "사업장 소재지" },
  { key: "biz_tel", label: "고객센터 전화", ph: "02-000-0000" },
  { key: "biz_hours", label: "고객센터 운영시간", ph: "평일 09:00~17:00" },
  { key: "biz_email", label: "전자우편(고객문의)", ph: "help@example.com" },
  { key: "biz_privacy_officer", label: "개인정보 보호책임자" },
  { key: "biz_hosting", label: "호스팅 제공자" },
];
const VER_FIELDS: { key: SK; label: string; ph?: string }[] = [
  { key: "terms_version", label: "이용약관 버전", ph: "2026-06-01" },
  { key: "privacy_version", label: "개인정보 버전", ph: "2026-06-01" },
  { key: "refund_version", label: "환불정책 버전", ph: "2026-06-01" },
  { key: "min_age_years", label: "최소 가입연령", ph: "19" },
];
const BODY_FIELDS: { key: SK; label: string }[] = [
  { key: "legal_body_terms", label: "이용약관 본문" },
  { key: "legal_body_privacy", label: "개인정보처리방침 본문" },
  { key: "legal_body_refund", label: "환불·청약철회 정책 본문" },
  { key: "legal_body_disclaimer", label: "면책고지 본문" },
];

function SiteField({ label, value, ph, type = "text", onChange }: {
  label: string; value: string; ph?: string; type?: string; onChange: (v: string) => void;
}) {
  return (
    <div className="bf-field">
      <label style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-600)", marginBottom: 4 }}>{label}</label>
      <input className="bf-input" type={type} value={value ?? ""} placeholder={ph} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
function SiteSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {children}
    </div>
  );
}

function SiteTab() {
  const [form, setForm] = useState<SiteSettings | null>(null);
  const [orig, setOrig] = useState<SiteSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.adminGetSiteSettings()
      .then((r) => { setForm(r.settings); setOrig(r.settings); })
      .catch((e) => setErr(String(e?.message || e)));
  }, []);

  if (!form || !orig) return <div>{err ? <div className="err">{err}</div> : "불러오는 중…"}</div>;
  const f = form;
  const up = (k: SK, v: string) => setForm((cur) => (cur ? { ...cur, [k]: v } : cur));
  const checked = (k: SK) => String(f[k]).toLowerCase() === "true";

  async function save() {
    if (!form || !orig) return;
    const changed: Record<string, string | number | boolean> = {};
    (Object.keys(form) as SK[]).forEach((k) => {
      if (form[k] === orig[k]) return;
      if (k === "smtp_enabled" || k === "smtp_use_tls") changed[k] = String(form[k]).toLowerCase() === "true";
      else if (k === "smtp_port") changed[k] = form[k] ? Number(form[k]) : 587;
      else changed[k] = form[k];
    });
    if (Object.keys(changed).length === 0) { setMsg("변경사항이 없습니다."); return; }
    setBusy(true); setMsg(null); setErr(null);
    try {
      const r = await api.adminPatchSiteSettings(changed);
      setForm(r.settings); setOrig(r.settings);
      setMsg("저장되었습니다. 약관/사업자 정보 화면에 즉시 반영됩니다.");
    } catch (e: any) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <SiteSection title="사업자 정보 (전자상거래법 §13 — 약관·푸터에 노출)">
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          입력하면 이용약관 ‘제1조 사업자 정보’ 표 등에 즉시 반영됩니다. 비우면 “(운영자 설정 전)”으로 표시돼요.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {BIZ_FIELDS.map((x) => (
            <SiteField key={x.key} label={x.label} ph={x.ph} value={f[x.key]} onChange={(v) => up(x.key, v)} />
          ))}
        </div>
      </SiteSection>

      <SiteSection title="약관 버전 · 가입 연령">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
          {VER_FIELDS.map((x) => (
            <SiteField key={x.key} label={x.label} ph={x.ph} value={f[x.key]} onChange={(v) => up(x.key, v)} />
          ))}
        </div>
        <p style={{ fontSize: 11.5, color: "var(--ink-400)" }}>비우면 서버 기본값을 사용합니다.</p>
      </SiteSection>

      <SiteSection title="고객센터 알림 메일 (SMTP)">
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          문의 접수 시 수신자에게 메일을 보낼 SMTP 설정입니다. (수신자 목록은 <b>고객센터</b> 탭에서 관리)
          미설정 시 서버 로그로 대체됩니다.
        </p>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center", margin: "6px 0 10px" }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={checked("smtp_enabled")} onChange={(e) => up("smtp_enabled", e.target.checked ? "true" : "false")} />
            메일 발송 사용
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={checked("smtp_use_tls")} onChange={(e) => up("smtp_use_tls", e.target.checked ? "true" : "false")} />
            STARTTLS 사용
          </label>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10 }}>
          <SiteField label="SMTP 호스트" ph="smtp.gmail.com" value={f.smtp_host} onChange={(v) => up("smtp_host", v)} />
          <SiteField label="포트" ph="587" value={f.smtp_port} onChange={(v) => up("smtp_port", v)} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <SiteField label="계정(User)" ph="account@gmail.com" value={f.smtp_user} onChange={(v) => up("smtp_user", v)} />
          <SiteField label="비밀번호/앱비밀번호" type="password" ph="앱 비밀번호" value={f.smtp_password} onChange={(v) => up("smtp_password", v)} />
        </div>
        <SiteField label="보내는 사람(From)" ph="인생상담 친구 <no-reply@example.com>" value={f.smtp_from} onChange={(v) => up("smtp_from", v)} />
      </SiteSection>

      <SiteSection title="약관 본문 직접 편집 (선택)">
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          내용을 입력하면 해당 문서가 <b>입력한 본문(Markdown)</b>으로 대체됩니다. <b>비워두면 기본 제공 문안</b>(사업자 정보 자동 반영)이 표시됩니다.
          제목은 <code># 제목</code>, 굵게는 <code>**굵게**</code>, 목록은 <code>- 항목</code>.
        </p>
        {BODY_FIELDS.map((x) => (
          <div key={x.key} className="bf-field" style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-600)", marginBottom: 4 }}>
              {x.label} {String(f[x.key] ?? "").trim() ? "· (덮어쓰기 적용)" : "· (기본 문안 사용 중)"}
            </label>
            <textarea
              className="sf-textarea" rows={4}
              value={f[x.key] ?? ""}
              placeholder="비우면 기본 문안 사용"
              onChange={(e) => up(x.key, e.target.value)}
            />
          </div>
        ))}
      </SiteSection>

      <div style={{ display: "flex", alignItems: "center", gap: 12, position: "sticky", bottom: 0, background: "var(--bg)", padding: "10px 0" }}>
        <button onClick={save} disabled={busy} style={{ fontWeight: 700 }}>{busy ? "저장 중…" : "전체 저장"}</button>
        {msg && <span style={{ color: "var(--brand-600)", fontSize: 13 }}>{msg}</span>}
        {err && <span className="err" style={{ margin: 0 }}>{err}</span>}
      </div>
    </div>
  );
}

// -------- 타로 카드 해석/키워드 편집 --------

const SUIT_LABEL: Record<string, string> = {
  wands: "완드·불", cups: "컵·물", swords: "소드·공기", pentacles: "펜타클·흙",
};

function KeywordEditor({ label, value, onChange }: {
  label: string; value: string[]; onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("");
  function add() {
    const s = input.trim();
    if (!s) return;
    if (!value.includes(s)) onChange([...value, s]);
    setInput("");
  }
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>{label} ({value.length})</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
        {value.map((k) => (
          <span key={k} style={{ background: "var(--brand-50)", border: "1px solid var(--line)", borderRadius: 999, padding: "3px 8px", fontSize: 12, display: "inline-flex", gap: 6, alignItems: "center" }}>
            {k}
            <button type="button" onClick={() => onChange(value.filter((x) => x !== k))} style={{ border: "none", background: "none", cursor: "pointer", color: "crimson", padding: 0, fontSize: 14, lineHeight: 1 }}>×</button>
          </span>
        ))}
        {value.length === 0 && <span style={{ color: "#bbb", fontSize: 12 }}>키워드 없음</span>}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder="키워드 입력 후 Enter"
          style={{ flex: 1, fontSize: 13, padding: "5px 8px" }}
        />
        <button type="button" onClick={add}>추가</button>
      </div>
    </div>
  );
}

function CardEditor({ card, onSaved }: { card: TarotAdminCard; onSaved: (u: TarotAdminCard) => void }) {
  const [kwUp, setKwUp] = useState<string[]>(card.keywords_up);
  const [kwRev, setKwRev] = useState<string[]>(card.keywords_rev);
  const [iUp, setIUp] = useState(card.interp_up);
  const [iRev, setIRev] = useState(card.interp_rev);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const dirty =
    JSON.stringify(kwUp) !== JSON.stringify(card.keywords_up) ||
    JSON.stringify(kwRev) !== JSON.stringify(card.keywords_rev) ||
    iUp !== card.interp_up || iRev !== card.interp_rev;

  async function save() {
    if (!kwUp.length || !kwRev.length) { alert("정/역 키워드는 최소 1개 이상이어야 합니다."); return; }
    if (!iUp.trim() || !iRev.trim()) { alert("정/역 해석은 비울 수 없습니다."); return; }
    setBusy(true); setErr(null); setMsg(null);
    try {
      const u = await api.adminUpdateTarotCard(card.code, { keywords_up: kwUp, keywords_rev: kwRev, interp_up: iUp, interp_rev: iRev });
      onSaved(u); setMsg("저장됨 · 즉시 반영");
    } catch (e: any) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  }
  async function reset() {
    if (!confirm(`${card.name_kr} 카드를 초안(시드)으로 되돌릴까요? 편집분이 삭제됩니다.`)) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const u = await api.adminResetTarotCard(card.code);
      setKwUp(u.keywords_up); setKwRev(u.keywords_rev); setIUp(u.interp_up); setIRev(u.interp_rev);
      onSaved(u); setMsg("초안으로 되돌림");
    } catch (e: any) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  }

  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 14 }}>
        <img src={card.image_url} alt="" style={{ width: 52, height: 88, objectFit: "cover", borderRadius: 4 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{card.name_kr} <span style={{ color: "#999", fontWeight: 400, fontSize: 14 }}>{card.name_en}</span></div>
          <div style={{ fontSize: 12, color: "#888" }}>{card.arcana === "major" ? "메이저 아르카나" : SUIT_LABEL[card.suit || ""]} · {card.code}</div>
          <div style={{ fontSize: 11, color: card.overridden ? "var(--brand-600)" : "#aaa", marginTop: 2 }}>
            {card.overridden ? `수정됨${card.updated_at ? " · " + fmtKSTShort(card.updated_at) : ""}` : "초안(미수정)"}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--brand-600)", marginBottom: 8 }}>↑ 정방향 (Upright)</div>
          <KeywordEditor label="정방향 키워드" value={kwUp} onChange={setKwUp} />
          <div style={{ fontSize: 12, color: "#888", margin: "4px 0" }}>정방향 해석</div>
          <textarea value={iUp} onChange={(e) => setIUp(e.target.value)} rows={6} style={{ width: "100%", boxSizing: "border-box", fontSize: 13, lineHeight: 1.6, padding: 8, resize: "vertical" }} />
          <div style={{ textAlign: "right", fontSize: 11, color: iUp.length > 2000 ? "crimson" : "#bbb" }}>{iUp.length}/2000</div>
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13, color: "#6b5bb0", marginBottom: 8 }}>↻ 역방향 (Reversed)</div>
          <KeywordEditor label="역방향 키워드" value={kwRev} onChange={setKwRev} />
          <div style={{ fontSize: 12, color: "#888", margin: "4px 0" }}>역방향 해석</div>
          <textarea value={iRev} onChange={(e) => setIRev(e.target.value)} rows={6} style={{ width: "100%", boxSizing: "border-box", fontSize: 13, lineHeight: 1.6, padding: 8, resize: "vertical" }} />
          <div style={{ textAlign: "right", fontSize: 11, color: iRev.length > 2000 ? "crimson" : "#bbb" }}>{iRev.length}/2000</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
        <button onClick={save} disabled={busy || !dirty} style={{ fontWeight: 700 }}>{busy ? "저장 중…" : dirty ? "저장 · 즉시 반영" : "변경 없음"}</button>
        <button onClick={reset} disabled={busy || !card.overridden} style={{ color: "crimson" }}>초안으로 되돌리기</button>
        {msg && <span style={{ color: "var(--brand-600)", fontSize: 13 }}>{msg}</span>}
        {err && <span className="err" style={{ margin: 0 }}>{err}</span>}
      </div>
    </div>
  );
}

function TarotTab() {
  const [cards, setCards] = useState<TarotAdminCard[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try { setCards((await api.adminTarotCards()).items); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }
  useEffect(() => { load(); }, []);

  const cur = cards.find((c) => c.code === sel) || null;

  const FILTERS: [string, string, (c: TarotAdminCard) => boolean][] = [
    ["all", "전체", () => true],
    ["edited", "수정됨", (c) => c.overridden],
    ["major", "메이저", (c) => c.arcana === "major"],
    ["wands", "완드", (c) => c.suit === "wands"],
    ["cups", "컵", (c) => c.suit === "cups"],
    ["swords", "소드", (c) => c.suit === "swords"],
    ["pentacles", "펜타클", (c) => c.suit === "pentacles"],
  ];
  const filterFn = FILTERS.find((f) => f[0] === filter)?.[2] || (() => true);
  const filtered = cards
    .filter(filterFn)
    .filter((c) => !q || (c.name_kr + c.name_en).toLowerCase().includes(q.toLowerCase()));

  function onSaved(u: TarotAdminCard) {
    setCards((prev) => prev.map((c) => (c.code === u.code ? u : c)));
  }

  return (
    <div>
      <div style={{ fontSize: 13, color: "#666", marginBottom: 10 }}>
        타로 78장 정/역 키워드·해석을 수정합니다. <b>저장 즉시 새 뽑기·해석에 반영</b>됩니다(재시작 불필요).
        수정한 카드는 “초안으로 되돌리기”로 언제든 원복할 수 있어요.
      </div>
      {err && <div className="err" style={{ marginBottom: 8 }}>{err}</div>}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
        {FILTERS.map(([id, label, fn]) => (
          <button key={id} onClick={() => setFilter(id)} style={{ padding: "5px 12px", borderRadius: 999, fontSize: 13, cursor: "pointer", border: filter === id ? "none" : "1px solid var(--line)", background: filter === id ? "var(--brand-500)" : "var(--brand-50)", color: filter === id ? "#fff" : "var(--ink-600)" }}>
            {label} <span style={{ opacity: 0.6 }}>{cards.filter(fn).length}</span>
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="카드명 검색" style={{ marginLeft: "auto", fontSize: 13, padding: "5px 10px" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16, alignItems: "start" }}>
        <div style={{ maxHeight: 640, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 8 }}>
          {filtered.map((c) => (
            <button key={c.code} onClick={() => setSel(c.code)} style={{ display: "flex", width: "100%", gap: 8, alignItems: "center", padding: "8px 10px", border: "none", borderBottom: "1px solid #f0f0f0", background: sel === c.code ? "var(--brand-50)" : "transparent", cursor: "pointer", textAlign: "left" }}>
              <img src={c.image_url} alt="" style={{ width: 26, height: 44, objectFit: "cover", borderRadius: 3, flexShrink: 0 }} />
              <span style={{ flex: 1 }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{c.name_kr}</span>
                <span style={{ display: "block", color: "#999", fontSize: 11 }}>{c.name_en}</span>
              </span>
              {c.overridden && <span title="수정됨" style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--brand-500)", flexShrink: 0 }} />}
            </button>
          ))}
          {filtered.length === 0 && <div style={{ padding: 16, color: "#999", fontSize: 13 }}>결과 없음</div>}
        </div>

        {cur ? (
          <CardEditor key={cur.code} card={cur} onSaved={onSaved} />
        ) : (
          <div style={{ color: "#999", padding: 30, textAlign: "center", border: "1px dashed var(--line)", borderRadius: 8 }}>
            왼쪽 목록에서 카드를 선택하세요.
          </div>
        )}
      </div>
    </div>
  );
}
