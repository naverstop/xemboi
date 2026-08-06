import { useEffect, useState, type ReactNode } from "react";
import { useTranslation, Trans } from "react-i18next";
import { Link } from "react-router-dom";
import {
  api,
  AdminStats,
  AdminUser,
  AdminTx,
  type AdminPayment,
  type AdminPaymentRow,
  Banner,
  BANNER_SLOTS,
  AnswerTemplate,
  AppSettings,
  useMe,
  type SupportTicket,
  type SupportRecipient,
  type SupportStatus,
  type Review,
  type SiteSettings,
  type TarotAdminCard,
  type TarotLearnStatus,
  type ConsultantAdmin,
  type ConsultationSettings,
  type ConsultantSpecialty,
  type ConsultantPriceUnit,
  type ConsultantStatus,
  type ConsultationSettlementRow,
  type AdminUsageSummary,
  type PartnerApplication,
  type PartnerInquiry,
  type SettlementTotals,
  type PricingOverview,
  type PricingRecommendation,
} from "../api";
import { fmtKSTDate, fmtKSTDateTime, fmtKSTShort } from "../lib/datetime";

type Tab = "stats" | "live" | "users" | "banners" | "billing" | "pricing" | "templates" | "support" | "reviews" | "site" | "tarot" | "consultants" | "settlements";

export default function AdminPage() {
  const { t: tr } = useTranslation();
  const me = useMe();
  const [tab, setTab] = useState<Tab>("stats");

  if (!me || me.role !== "admin") {
    return (
      <div style={{ padding: 20 }}>
        <h3>{tr("admin.gate.title")}</h3>
        <p>{tr("admin.gate.need")} <Link to="/login">{tr("admin.gate.login")}</Link></p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <TabBtn tab="stats" cur={tab} setTab={setTab} label={tr("admin.tabs.stats")} />
        <TabBtn tab="live" cur={tab} setTab={setTab} label={tr("admin.tabs.live")} />
        <TabBtn tab="users" cur={tab} setTab={setTab} label={tr("admin.tabs.users")} />
        <TabBtn tab="banners" cur={tab} setTab={setTab} label={tr("admin.tabs.banners")} />
        <TabBtn tab="billing" cur={tab} setTab={setTab} label={tr("admin.tabs.billing")} />
        <TabBtn tab="pricing" cur={tab} setTab={setTab} label={tr("admin.tabs.pricing")} />
        <TabBtn tab="templates" cur={tab} setTab={setTab} label={tr("admin.tabs.templates")} />
        <TabBtn tab="support" cur={tab} setTab={setTab} label={tr("admin.tabs.support")} />
        <TabBtn tab="reviews" cur={tab} setTab={setTab} label={tr("admin.tabs.reviews")} />
        <TabBtn tab="site" cur={tab} setTab={setTab} label={tr("admin.tabs.site")} />
        <TabBtn tab="tarot" cur={tab} setTab={setTab} label={tr("admin.tabs.tarot")} />
        <TabBtn tab="consultants" cur={tab} setTab={setTab} label={tr("admin.tabs.consultants")} />
        <TabBtn tab="settlements" cur={tab} setTab={setTab} label={tr("admin.tabs.settlements")} />
      </div>
      {tab === "stats" && <StatsTab />}
      {tab === "live" && <LiveStatsTab />}
      {tab === "users" && <UsersTab />}
      {tab === "banners" && <BannersTab />}
      {tab === "billing" && <BillingTab />}
      {tab === "pricing" && <PricingAgentTab />}
      {tab === "templates" && <TemplatesTab />}
      {tab === "support" && <SupportTab />}
      {tab === "reviews" && <ReviewsTab />}
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

const ADMIN_PAY_PAGE = 20;  // 관리자 결제 리스트 페이지당

/** 현재 통계(운영자 지시 2026-07-11) — 접속·방문·PWA 설치·메뉴 사용도·버튼 클릭. 30초 자동 갱신. */
function LiveStatsTab() {
  const { t: tr, i18n } = useTranslation();
  const [s, setS] = useState<AdminUsageSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.adminUsageSummary()
      .then((r) => { if (alive) { setS(r); setErr(null); } })
      .catch((e) => { if (alive) setErr(String(e?.message || e)); });
    load();
    const iv = window.setInterval(load, 30_000);
    return () => { alive = false; window.clearInterval(iv); };
  }, []);
  if (err) return <div style={{ color: "crimson" }}>{err}</div>;
  if (!s) return <div>{tr("admin.loading")}</div>;

  // 사이드 메뉴 전체 고정 목록(사이드바 순서) — 방문 0이어도 표시(운영자 지시: 전체 다 반영)
  const MENU_KEYS = [
    "landing", "chat", "compatibility", "today", "calendar", "sinnyeon", "taekil",
    "naming-jakmyeong", "naming-gaemyeong", "naming-aho", "tarot", "amulet", "dream", "snack",
    "payments", "settings", "consultation", "uploads", "trend", "admin", "reviews", "support", "login",
  ];
  const MENU_KO: Record<string, string> = Object.fromEntries(MENU_KEYS.map((k) => [k, tr(`admin.live.menu.${k}`)]));
  const CLICK_KO: Record<string, string> = {
    cta: tr("admin.live.click.cta"), explain: tr("admin.live.click.explain"), question: tr("admin.live.click.question"),
    reveal: tr("admin.live.click.reveal"), "answer-action": tr("admin.live.click.answer_action"),
    "quick-input": tr("admin.live.click.quick_input"), "share-card": tr("admin.live.click.share_card"), download: tr("admin.live.click.download"),
    video: tr("admin.live.click.video"), report: tr("admin.live.click.report"), "install-guide": tr("admin.live.click.install_guide"),
    "install-fab": tr("admin.live.click.install_fab"), "inapp-escape": tr("admin.live.click.inapp_escape"),
    "consult-fab": tr("admin.live.click.consult_fab"), charge: tr("admin.live.click.charge"),
    "pwa:install-accept": tr("admin.live.click.pwa_install_accept"), "pwa:installed": tr("admin.live.click.pwa_installed"),
    "pwa:mark-installed": tr("admin.live.click.pwa_mark_installed"),
  };
  const menuName = (k: string) => MENU_KO[k] || k;
  // 서버 집계 + 전체 메뉴 병합(없으면 0) — 사이드바 순서 유지, 목록 밖 키는 뒤에
  const menuMap = new Map(s.menus.map((m) => [m.key, m]));
  const allMenus = [
    ...MENU_KEYS.map((k) => menuMap.get(k) || { key: k, today: 0, week: 0 }),
    ...s.menus.filter((m) => !(m.key in MENU_KO)),
  ];
  const maxWeek = Math.max(1, ...allMenus.map((m) => m.week));
  // 클릭 현황 — 메뉴별 그룹(한눈에: 메뉴 | 기능 | 오늘 | 7일). 'pwa:*'는 전역 그룹.
  const clickGroups = new Map<string, { fn: string; today: number; week: number }[]>();
  for (const c of s.clicks) {
    const i = c.key.lastIndexOf(":");
    const menu = c.key.startsWith("pwa:") ? tr("admin.live.grp_pwa") : i > 0 ? menuName(c.key.slice(0, i)) : tr("admin.live.grp_etc");
    const fnKey = c.key.startsWith("pwa:") ? c.key : i > 0 ? c.key.slice(i + 1) : c.key;
    const fn = CLICK_KO[fnKey] || fnKey;
    if (!clickGroups.has(menu)) clickGroups.set(menu, []);
    clickGroups.get(menu)!.push({ fn, today: c.today, week: c.week });
  }

  // 상단 타일 — 접속/방문(파랑 강조), PWA 설치(플랫폼별)
  const hot: [string, number][] = [[tr("admin.live.tile_online"), s.online_now], [tr("admin.live.tile_visitors"), s.today_visitors]];
  const pwa: [string, number][] = [
    [tr("admin.live.tile_pwa_total"), s.pwa.total], [tr("admin.live.tile_ios"), s.pwa.ios || 0],
    [tr("admin.live.tile_android"), s.pwa.android || 0], [tr("admin.live.tile_desktop"), s.pwa.desktop || 0],
    [tr("admin.live.tile_other"), s.pwa.other || 0],   // 합계 정합(플랫폼 미상='other')
  ];

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 12 }}>
        {hot.map(([k, v]) => (
          <div key={k} style={{ border: "1px solid var(--brand-100)", background: "var(--brand-50)", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "var(--brand-700)", fontSize: 12, fontWeight: 700 }}>{k}</div>
            <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4, color: "var(--brand-700)" }}>{v.toLocaleString()}</div>
          </div>
        ))}
        <div style={{ border: "1px solid var(--brand-100)", background: "var(--brand-50)", borderRadius: 8, padding: 12 }}>
          <div style={{ color: "var(--brand-700)", fontSize: 12, fontWeight: 700 }}>📲 설치율</div>
          <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4, color: "var(--brand-700)" }}>{s.install_rate}%</div>
          <div style={{ fontSize: 11, color: "var(--ink-400)", marginTop: 2 }}>
            {s.pwa.total.toLocaleString()} / {s.total_devices.toLocaleString()} 기기
          </div>
        </div>
        {pwa.map(([k, v]) => (
          <div key={k} style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "var(--ink-400)", fontSize: 12 }}>{k}</div>
            <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4 }}>{v.toLocaleString()}</div>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 12, color: "var(--ink-400)", margin: "0 0 6px" }}>
        {tr("admin.live.as_of", { time: new Date(s.as_of).toLocaleTimeString(i18n.language === "vi" ? "vi-VN" : "ko-KR") })}
      </p>

      <h3 style={{ margin: "18px 0 8px" }}>{tr("admin.live.h_menu_usage")} <span style={{ fontSize: 12, color: "var(--ink-400)", fontWeight: 400 }}>{tr("admin.live.h_menu_usage_sub")}</span></h3>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--bg)" }}>
            <th style={aTh}>{tr("admin.live.th_menu")}</th>
            <th style={{ ...aTh, textAlign: "right", width: 70 }}>{tr("admin.live.th_today")}</th>
            <th style={{ ...aTh, textAlign: "right", width: 90 }}>{tr("admin.live.th_week")}</th>
            <th style={{ ...aTh, width: "36%" }}>{tr("admin.live.th_week_share")}</th>
          </tr>
        </thead>
        <tbody>
          {allMenus.map((m) => (
            <tr key={m.key} style={m.week === 0 ? { opacity: .55 } : undefined}>
              <td style={aTd}>{menuName(m.key)}</td>
              <td style={{ ...aTd, textAlign: "right" }}>{m.today.toLocaleString()}</td>
              <td style={{ ...aTd, textAlign: "right" }}>{m.week.toLocaleString()}</td>
              <td style={aTd}>
                <span style={{ display: "block", height: 10, background: "var(--brand-50)", borderRadius: 999 }}>
                  <i style={{ display: "block", height: "100%", borderRadius: 999, background: "var(--brand-grad)",
                              width: `${m.week === 0 ? 0 : Math.max(3, (m.week / maxWeek) * 100)}%` }} />
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ margin: "18px 0 8px" }}>{tr("admin.live.h_feature")} <span style={{ fontSize: 12, color: "var(--ink-400)", fontWeight: 400 }}>{tr("admin.live.h_feature_sub")}</span></h3>
      <table style={{ width: "100%", maxWidth: 760, fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--bg)" }}>
            <th style={{ ...aTh, width: 110 }}>{tr("admin.live.th_menu")}</th>
            <th style={aTh}>{tr("admin.live.th_feature")}</th>
            <th style={{ ...aTh, textAlign: "right", width: 64 }}>{tr("admin.live.th_today")}</th>
            <th style={{ ...aTh, textAlign: "right", width: 80 }}>{tr("admin.live.th_week")}</th>
            <th style={{ ...aTh, textAlign: "right", width: 80 }}>{tr("admin.live.th_total")}</th>
          </tr>
        </thead>
        <tbody>
          {(() => {
            const groups = new Map<string, typeof s.features>();
            for (const f of s.features) {
              if (!groups.has(f.menu)) groups.set(f.menu, []);
              groups.get(f.menu)!.push(f);
            }
            return [...groups.entries()].map(([menu, rows]) =>
              rows.map((f, i) => (
                <tr key={`${menu}-${f.feature}`} style={f.week === 0 && f.today === 0 ? { opacity: .6 } : undefined}>
                  {i === 0 && (
                    <td style={{ ...aTd, fontWeight: 700, verticalAlign: "top" }} rowSpan={rows.length}>{menu}</td>
                  )}
                  <td style={aTd}>{f.feature}</td>
                  <td style={{ ...aTd, textAlign: "right", fontWeight: f.today > 0 ? 700 : 400 }}>{f.today.toLocaleString()}</td>
                  <td style={{ ...aTd, textAlign: "right" }}>{f.week.toLocaleString()}</td>
                  <td style={{ ...aTd, textAlign: "right", color: "var(--ink-400)" }}>{f.total.toLocaleString()}</td>
                </tr>
              )),
            );
          })()}
        </tbody>
      </table>

      <h3 style={{ margin: "18px 0 8px" }}>{tr("admin.live.h_click")} <span style={{ fontSize: 12, color: "var(--ink-400)", fontWeight: 400 }}>{tr("admin.live.h_click_sub")}</span></h3>
      {s.clicks.length === 0 ? (
        <p style={{ color: "var(--ink-400)", fontSize: 13 }}>{tr("admin.live.click_empty")}</p>
      ) : (
        <table style={{ width: "100%", maxWidth: 640, fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg)" }}>
              <th style={{ ...aTh, width: 130 }}>{tr("admin.live.th_menu")}</th>
              <th style={aTh}>{tr("admin.live.th_feature_btn")}</th>
              <th style={{ ...aTh, textAlign: "right", width: 70 }}>{tr("admin.live.th_today")}</th>
              <th style={{ ...aTh, textAlign: "right", width: 90 }}>{tr("admin.live.th_week")}</th>
            </tr>
          </thead>
          <tbody>
            {[...clickGroups.entries()].map(([menu, rows]) =>
              rows.map((r, i) => (
                <tr key={`${menu}-${r.fn}`}>
                  {i === 0 && (
                    <td style={{ ...aTd, fontWeight: 700, verticalAlign: "top" }} rowSpan={rows.length}>{menu}</td>
                  )}
                  <td style={aTd}>{r.fn}</td>
                  <td style={{ ...aTd, textAlign: "right" }}>{r.today.toLocaleString()}</td>
                  <td style={{ ...aTd, textAlign: "right" }}>{r.week.toLocaleString()}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StatsTab() {
  const { t: tr } = useTranslation();
  const [s, setS] = useState<AdminStats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pays, setPays] = useState<AdminPaymentRow[]>([]);
  const [payTotal, setPayTotal] = useState(0);
  const [payPage, setPayPage] = useState(0);  // 0-base
  useEffect(() => {
    api.adminStats().then(setS).catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => {
    api.adminAllPayments(ADMIN_PAY_PAGE, payPage * ADMIN_PAY_PAGE)
      .then((r) => { setPays(r.items); setPayTotal(r.total); })
      .catch(() => {});
  }, [payPage]);
  if (err) return <div style={{ color: "crimson" }}>{err}</div>;
  if (!s) return <div>{tr("admin.loading")}</div>;
  const cards: [string, string | number][] = [
    [tr("admin.stats.c_total_users"), s.total_users],
    [tr("admin.stats.c_today_signups"), tr("admin.stats.signups_val", { today: s.today_signups, yesterday: s.yesterday_signups })],
    [tr("admin.stats.c_today_questions"), s.today_questions],
    [tr("admin.stats.c_today_spent"), s.today_credits_spent.toLocaleString()],
    [tr("admin.stats.c_total_revenue"), s.total_revenue_krw.toLocaleString()],
    [tr("admin.stats.c_outstanding"), s.total_outstanding_credits.toLocaleString()],
  ];
  // 기간별 매출(실제 번 돈) — 강조 카드
  const rev: [string, number][] = [
    [tr("admin.stats.r_today"), s.revenue_today_krw],
    [tr("admin.stats.r_week"), s.revenue_week_krw],
    [tr("admin.stats.r_month"), s.revenue_month_krw],
    [tr("admin.stats.r_year"), s.revenue_year_krw],
  ];
  const payPages = Math.max(1, Math.ceil(payTotal / ADMIN_PAY_PAGE));

  return (
    <div>
      {/* 기간별 매출 — 실제 관리자 수익 (반응형: 좁으면 자동 줄바꿈) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12, marginBottom: 14 }}>
        {rev.map(([k, v]) => (
          <div key={k} style={{ border: "1px solid var(--brand-100)", background: "var(--brand-50)", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "var(--brand-700)", fontSize: 12, fontWeight: 700 }}>💰 {k}</div>
            <div style={{ fontSize: 22, fontWeight: 800, marginTop: 4, color: "var(--brand-700)" }}>{v.toLocaleString()}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {cards.map(([k, v]) => (
          <div key={k} style={{ border: "1px solid var(--line)", borderRadius: 6, padding: 12 }}>
            <div style={{ color: "var(--ink-400)", fontSize: 12 }}>{k}</div>
            <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4 }}>{v}</div>
          </div>
        ))}
      </div>

      {/* 전 회원 결제 히스토리 — 20개씩 페이지 */}
      <h3 style={{ marginTop: 22, marginBottom: 8 }}>{tr("admin.stats.pay_history")} <span style={{ fontSize: 13, color: "var(--ink-400)", fontWeight: 400 }}>{tr("admin.stats.pay_total", { count: payTotal.toLocaleString() })}</span></h3>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--bg)" }}>
            <th style={aTh}>{tr("admin.stats.th_member")}</th>
            <th style={{ ...aTh, textAlign: "right" }}>{tr("admin.stats.th_amount")}</th>
            <th style={{ ...aTh, textAlign: "right" }}>{tr("admin.stats.th_credit")}</th>
            <th style={aTh}>{tr("admin.stats.th_status")}</th>
            <th style={aTh}>{tr("admin.stats.th_time")}</th>
          </tr>
        </thead>
        <tbody>
          {pays.map((p) => (
            <tr key={p.order_id}>
              <td style={aTd}>{p.email}</td>
              <td style={{ ...aTd, textAlign: "right" }}>{p.amount.toLocaleString()}</td>
              <td style={{ ...aTd, textAlign: "right" }}>+{p.credit_granted.toLocaleString()} P</td>
              <td style={aTd}>
                <span style={{
                  padding: "2px 7px", borderRadius: 999, fontSize: 11, fontWeight: 700, color: "#fff",
                  background: p.status === "approved" ? "var(--brand-500)" : p.status === "refunded" ? "#ef4444" : "#9ca3af",
                }}>{tr(`admin.payStatus.${p.status}`, p.status)}</span>
              </td>
              <td style={aTd}>{fmtKSTDateTime(p.approved_at || p.created_at)}</td>
            </tr>
          ))}
          {pays.length === 0 && (
            <tr><td style={{ ...aTd, textAlign: "center", color: "var(--ink-400)" }} colSpan={5}>{tr("admin.stats.pay_empty")}</td></tr>
          )}
        </tbody>
      </table>
      {payPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 6, marginTop: 12 }}>
          <button type="button" disabled={payPage <= 0} onClick={() => setPayPage(payPage - 1)} style={aPageBtn(payPage <= 0)}>‹</button>
          <span style={{ fontSize: 13, color: "var(--ink-600)", padding: "0 6px" }}>{payPage + 1} / {payPages}</span>
          <button type="button" disabled={payPage >= payPages - 1} onClick={() => setPayPage(payPage + 1)} style={aPageBtn(payPage >= payPages - 1)}>›</button>
        </div>
      )}
    </div>
  );
}

const aTh: React.CSSProperties = { textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--line)", color: "var(--ink-600)" };
const aTd: React.CSSProperties = { padding: "6px 8px", borderBottom: "1px solid var(--line)" };
function aPageBtn(disabled: boolean): React.CSSProperties {
  return {
    minWidth: 32, height: 32, borderRadius: 8, border: "1px solid var(--line)",
    background: "var(--surface)", color: "var(--ink-600)", fontWeight: 700,
    cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1,
  };
}

// -------- 회원 --------

const USERS_PAGE_SIZE = 20;  // 회원 목록 페이지당 노출 수

function UsersTab() {
  const { t: tr } = useTranslation();
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
    try { await api.adminDesignateConsultant(u.id, specialty); await loadConsultants(); alert(tr("admin.users.designate_ok", { email: u.email, label: tr(`admin.spec.${specialty}`, specialty) })); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function revoke(c: ConsultantAdmin) {
    if (!window.confirm(tr("admin.users.revoke_confirm", { name: c.business_name }))) return;
    try { await api.adminDeleteConsultant(c.id); await loadConsultants(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function uploadSignboard(c: ConsultantAdmin, file: File) {
    const fd = new FormData(); fd.append("file", file);
    try { await api.adminUploadSignboard(c.id, fd); await loadConsultants(); }
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
    if (!window.confirm(tr("admin.users.refund_confirm1", { order: p.order_id, won }))) return;
    setBusyRefund(p.order_id);
    try {
      const r = await api.adminRefundPayment(p.order_id);
      alert(tr("admin.users.refund_done", {
        mock: r.mock ? tr("admin.users.refund_mock") : "",
        partial: r.partial ? tr("admin.users.refund_partial") : "",
        refunded: r.refunded_krw.toLocaleString(),
        recovered: r.recovered_credits.toLocaleString(),
      }));
      await selectUser(sel);  // 결제·거래내역 갱신
      await load();           // 목록 집계(결제/환불 컬럼) 갱신
    } catch (e: any) {
      alert(tr("admin.users.refund_fail", { err: e?.message || String(e) }));
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
    if (!plan.length) { alert(tr("admin.users.bulk_none")); return; }
    const maxTotal = plan.reduce((s, x) => s + x.amount, 0);
    if (!window.confirm(tr("admin.users.bulk_confirm", { n: ids.length, m: plan.length, max: maxTotal.toLocaleString() }))) return;
    setBusyRefund("bulk");
    let ok = 0, fail = 0, refunded = 0;
    for (const x of plan) {
      try { const r = await api.adminRefundPayment(x.order); ok++; refunded += r.refunded_krw || 0; }
      catch { fail++; }
    }
    setBusyRefund(null);
    alert(tr("admin.users.bulk_done", { ok, refunded: refunded.toLocaleString(), fail: fail ? tr("admin.users.bulk_fail_suffix", { fail }) : "" }));
    setChecked(new Set());
    await load();
    if (sel) await selectUser(sel);
  }

  async function grant() {
    if (!sel) return;
    try {
      const d = parseInt(delta, 10);
      if (!Number.isFinite(d) || d === 0) return alert(tr("admin.users.grant_bad"));
      const r = await api.adminGrantCredit(sel.id, d, reason);
      alert(tr("admin.users.grant_balance", { bal: r.balance.toLocaleString() }));
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
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("admin.users.search_ph")} />
          <button onClick={() => go(0)}>{tr("admin.users.search_btn")}</button>
          <span style={{ color: "#666" }}>{tr("admin.users.total", { count: total })}</span>
          <button
            onClick={refundSelected}
            disabled={checked.size === 0 || busyRefund !== null}
            title={tr("admin.users.bulk_title")}
            style={{ marginLeft: "auto", background: checked.size ? "#c0392b" : "#ddd", color: "#fff", border: "none", borderRadius: 6, padding: "6px 12px", cursor: checked.size ? "pointer" : "default", fontWeight: 700 }}
          >
            {busyRefund === "bulk" ? tr("admin.users.bulk_busy") : tr("admin.users.bulk_btn", { count: checked.size })}
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
                  title={tr("admin.users.all_title")}
                />
              </th>
              <th style={th}>{tr("admin.users.th_id")}</th>
              <th style={th}>{tr("admin.users.th_email")}</th>
              <th style={th}>{tr("admin.users.th_role")}</th>
              <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.th_granted")}</th>
              <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.th_paid")}</th>
              <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.th_spent")}</th>
              <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.th_balance")}</th>
              <th style={th}>{tr("admin.users.th_ads")}</th>
              <th style={th}>{tr("admin.users.th_join")}</th>
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
                    title={tr("admin.users.row_check_title")}
                  />
                </td>
                <td style={td}>{u.id}</td>
                <td style={td}>
                  <span style={{ display: "inline-block", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", verticalAlign: "bottom" }} title={u.email}>{u.email}</span>
                  {u.is_premium ? " 👑" : ""}
                </td>
                <td style={td}>
                  {u.role}
                  {consultantOf(u.email) && <span style={{ marginLeft: 4, fontSize: 10, color: "#fff", background: "#6a5cff", borderRadius: 6, padding: "1px 5px" }}>{tr("admin.users.badge_consultant")}</span>}
                </td>
                <td style={{ ...td, textAlign: "right" }}>{u.granted_free.toLocaleString()}</td>
                <td style={{ ...td, textAlign: "right" }}>
                  {u.paid_krw.toLocaleString()}
                  {u.refunded_krw > 0 && (
                    <span style={{ display: "block", color: "#c0392b", fontSize: 10 }} title={tr("admin.users.refunded_title")}>↩{u.refunded_krw.toLocaleString()}</span>
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
                      {u.ads_hidden ? tr("admin.users.ads_hidden") : tr("admin.users.ads_shown")}
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
            <button onClick={() => go(0)} disabled={page <= 0}>{tr("admin.users.pg_first")}</button>
            <button onClick={() => go(page - 1)} disabled={page <= 0}>{tr("admin.users.pg_prev")}</button>
            <span style={{ fontSize: 13, color: "#444", minWidth: 96, textAlign: "center" }}>{tr("admin.users.pg_page", { page: page + 1, total: totalPages })}</span>
            <button onClick={() => go(page + 1)} disabled={page >= totalPages - 1}>{tr("admin.users.pg_next")}</button>
            <button onClick={() => go(totalPages - 1)} disabled={page >= totalPages - 1}>{tr("admin.users.pg_last")}</button>
          </div>
        )}
      </div>
      {sel ? (
          <div>
            <h4 style={{ marginTop: 0 }}>{sel.email}</h4>
            <div style={{ color: "#666", fontSize: 13 }}>
              {tr("admin.users.d_balance")} <strong>{sel.balance.toLocaleString()} P</strong> / {tr("admin.users.d_role")} {sel.role} /
              {" "}{tr("admin.users.d_todayfree")} {sel.daily_free_used_at ? tr("admin.users.used") : tr("admin.users.available")}
            </div>

            <div style={{ marginTop: 12, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{tr("admin.users.credit_adj")}</div>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={delta}
                  onChange={(e) => setDelta(e.target.value)}
                  placeholder={tr("admin.users.delta_ph")}
                  style={{ width: 100 }}
                />
                <select value={reason} onChange={(e) => setReason(e.target.value)}>
                  <option value="admin_grant">admin_grant</option>
                  <option value="refund">refund</option>
                  <option value="admin_seed">admin_seed</option>
                </select>
                <button onClick={grant}>{tr("admin.users.run")}</button>
              </div>
            </div>

            <div style={{ marginTop: 12, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{tr("admin.users.desig_title")}</div>
              {(() => {
                const c = consultantOf(sel.email);
                return c ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    {/* 간판 이미지 — 회원관리에서 직접 관리 */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                      {c.signboard_image_url
                        ? <img src={c.signboard_image_url} alt={tr("admin.users.signboard_alt")} style={{ width: 48, height: 60, borderRadius: 8, objectFit: "cover", border: "1px solid #eee" }} />
                        : <span style={{ width: 48, height: 60, borderRadius: 8, background: "#f0eef8", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>🪧</span>}
                      <label style={{ fontSize: 10, color: "var(--brand-600)", cursor: "pointer", fontWeight: 700 }}>
                        {tr("admin.users.signboard_change")}
                        <input type="file" accept="image/*" style={{ display: "none" }}
                          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadSignboard(c, f); e.currentTarget.value = ""; }} />
                      </label>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <span style={{ color: "#6a5cff", fontWeight: 700 }}>{tr("admin.users.designated", { name: c.business_name })}</span>
                      <span style={{ fontSize: 12, color: "#888" }}>{tr(`admin.spec.${c.specialty}`, c.specialty)} · {c.eff_price_p.toLocaleString()}P/{c.eff_duration_min}{tr("admin.min")} · {tr("admin.users.meta_sessions", { n: c.session_count })}{c.rating_avg != null ? ` · ★${c.rating_avg}` : ""}{c.status === "coming_soon" ? tr("admin.users.meta_coming") : c.status === "hidden" ? tr("admin.users.meta_hidden") : ""}</span>
                    </div>
                    <label style={{ fontSize: 12, color: "#666", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      {tr("admin.users.field_spec")}
                      <select value={c.specialty} onChange={(e) => designate(sel, e.target.value as ConsultantSpecialty)}>
                        <option value="saju">{tr("admin.spec.saju")}</option>
                        <option value="tarot">{tr("admin.spec.tarot")}</option>
                        <option value="both">{tr("admin.spec.both")}</option>
                      </select>
                    </label>
                    <button onClick={() => revoke(c)} style={{ color: "crimson", marginLeft: "auto" }}>{tr("admin.users.unassign")}</button>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, color: "#666" }}>{tr("admin.users.not_designated")}</span>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, color: "#444" }}>
                      {tr("admin.users.field_spec")}
                      <select value={desigSpec} onChange={(e) => setDesigSpec(e.target.value as ConsultantSpecialty)}>
                        <option value="saju">{tr("admin.spec.saju")}</option>
                        <option value="tarot">{tr("admin.spec.tarot")}</option>
                        <option value="both">{tr("admin.spec.both")}</option>
                      </select>
                    </label>
                    <button onClick={() => designate(sel, desigSpec)} style={{ marginLeft: "auto", background: "#6a5cff", color: "#fff", border: "none", borderRadius: 6, padding: "6px 14px", fontWeight: 700, cursor: "pointer" }}>{tr("admin.users.designate_btn")}</button>
                  </div>
                );
              })()}
            </div>

            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{tr("admin.users.pay_history", { count: pays.length })}</div>
              {pays.length === 0 ? (
                <div style={{ fontSize: 12, color: "#888" }}>{tr("admin.users.pay_empty")}</div>
              ) : (
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "#f7f7f7" }}>
                      <th style={th}>{tr("admin.users.pth_order")}</th>
                      <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.pth_amount")}</th>
                      <th style={th}>{tr("admin.users.pth_status")}</th>
                      <th style={th}>{tr("admin.users.pth_time")}</th>
                      <th style={{ ...th, textAlign: "center" }}>{tr("admin.users.pth_refund")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pays.map((p) => (
                      <tr key={p.id}>
                        <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{p.order_id}</td>
                        <td style={{ ...td, textAlign: "right" }}>{p.amount.toLocaleString()}</td>
                        <td style={td}>{tr(`admin.payStatus.${p.status}`, p.status)}</td>
                        <td style={td}>{(p.approved_at || p.created_at || "").replace("T", " ").slice(0, 16)}</td>
                        <td style={{ ...td, textAlign: "center" }}>
                          {p.refundable ? (
                            <button
                              onClick={() => refund(p)}
                              disabled={busyRefund === p.order_id}
                              style={{ padding: "2px 10px", fontSize: 11, color: "#fff", background: "#c0392b", border: "none", borderRadius: 4, cursor: "pointer" }}
                            >
                              {busyRefund === p.order_id ? tr("admin.users.r_processing") : tr("admin.users.r_refund")}
                            </button>
                          ) : p.status === "refunded" ? (
                            <span style={{ fontSize: 11, color: "#c0392b" }}>
                              {tr("admin.users.r_refunded")}{p.refunded_recovered != null ? ` (${p.refunded_recovered.toLocaleString()}P)` : ""}
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

            <h5 style={{ marginTop: 16 }}>{tr("admin.users.tx_title")}</h5>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "#f7f7f7" }}>
                  <th style={th}>{tr("admin.users.txth_id")}</th>
                  <th style={th}>{tr("admin.users.txth_reason")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.txth_delta")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{tr("admin.users.txth_balance")}</th>
                  <th style={th}>{tr("admin.users.txth_time")}</th>
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
          <div style={{ color: "#888", fontSize: 13 }}>{tr("admin.users.detail_hint")}</div>
        )}
    </div>
  );
}

// -------- 배너 --------

function BannersTab() {
  const { t: tr } = useTranslation();
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
    if (!form.image_url) return alert(tr("admin.banners.img_required"));
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
    if (!confirm(tr("admin.banners.del_confirm", { id: b.id }))) return;
    await api.adminDeleteBanner(b.id);
    await load();
  }

  return (
    <div>
      {err && <div style={{ color: "crimson" }}>{err}</div>}
      <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>{tr("admin.banners.new_title")}</div>
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
            placeholder={tr("admin.banners.ph_link")}
            value={form.link_url || ""}
            onChange={(e) => setForm({ ...form, link_url: e.target.value })}
          />
          <input
            placeholder={tr("admin.banners.ph_title")}
            value={form.title || ""}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            type="number"
            placeholder="weight"
            value={form.weight ?? 10}
            onChange={(e) => setForm({ ...form, weight: parseInt(e.target.value, 10) || 0 })}
          />
          <button onClick={create}>{tr("admin.banners.add")}</button>
        </div>
      </div>

      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>{tr("admin.banners.th_id")}</th>
            <th style={th}>{tr("admin.banners.th_slot")}</th>
            <th style={th}>{tr("admin.banners.th_title_img")}</th>
            <th style={th}>{tr("admin.banners.th_weight")}</th>
            <th style={th}>{tr("admin.banners.th_active")}</th>
            <th style={th}>{tr("admin.banners.th_action")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id}>
              <td style={td}>{b.id}</td>
              <td style={td}>{b.slot}</td>
              <td style={td}>
                <div>{b.title || tr("admin.banners.no_title")}</div>
                <div style={{ color: "#888", fontSize: 11 }}>{b.image_url}</div>
              </td>
              <td style={td}>{b.weight}</td>
              <td style={td}>
                <button onClick={() => toggleActive(b)}>{b.active ? "ON" : "OFF"}</button>
              </td>
              <td style={td}>
                <button onClick={() => del(b)} style={{ color: "crimson" }}>{tr("admin.banners.del")}</button>
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

function ConsultantsTab() {
  const { t: tr } = useTranslation();
  const [items, setItems] = useState<ConsultantAdmin[]>([]);
  const [apps, setApps] = useState<PartnerApplication[]>([]);   // 입점 신청 대기(운영자 지시 2026-07-11)
  const [inqs, setInqs] = useState<PartnerInquiry[]>([]);       // 입점 문의 대기(신청 전 게이트, 2026-07-12)
  const [settings, setSettings] = useState<ConsultationSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const emptyForm = {
    login_email: "", business_name: "", specialty: "saju" as ConsultantSpecialty,
    intro: "", keywords: "", rate_p: "", duration_min: "", commission_pct: "",
    price_unit: "session" as ConsultantPriceUnit, per_min_p: "", per_hour_p: "",
    sort_order: "100", is_active: true, status: "active" as ConsultantStatus, self_managed: true,
  };
  const [form, setForm] = useState<typeof emptyForm>(emptyForm);

  async function load() {
    try {
      const [c, s, a, q] = await Promise.all([
        api.adminConsultants(), api.adminGetConsultationSettings(),
        api.adminPartnerApplications("pending"), api.adminPartnerInquiries("pending"),
      ]);
      setItems(c.items); setSettings(s.settings); setApps(a.items); setInqs(q.items);
    } catch (e: any) { setErr(String(e)); }
  }

  async function approveApp(a: PartnerApplication) {
    if (!confirm(tr("admin.consult.app_approve_confirm", { name: a.business_name, email: a.email }))) return;
    try { await api.adminPartnerApprove(a.id); setMsg(tr("admin.consult.app_approve_ok", { name: a.business_name })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function rejectApp(a: PartnerApplication) {
    const reason = prompt(tr("admin.consult.app_reject_prompt", { name: a.business_name }), "");
    if (reason === null) return;
    try { await api.adminPartnerReject(a.id, reason); setMsg(tr("admin.consult.app_reject_ok", { name: a.business_name })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function allowInq(q: PartnerInquiry) {
    if (!confirm(tr("admin.consult.inq_allow_confirm", { email: q.email }))) return;
    try { await api.adminPartnerInquiryAllow(q.id); setMsg(tr("admin.consult.inq_allow_ok", { email: q.email })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function dismissInq(q: PartnerInquiry) {
    const reason = prompt(tr("admin.consult.inq_dismiss_prompt", { email: q.email }), "");
    if (reason === null) return;
    try { await api.adminPartnerInquiryDismiss(q.id, reason); setMsg(tr("admin.consult.inq_dismiss_ok", { email: q.email })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
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
      keywords: form.keywords.split(",").map((s) => s.trim().replace(/^#+/, "")).filter(Boolean),
      rate_p: toNum(form.rate_p),
      duration_min: toNum(form.duration_min),
      commission_pct: toNum(form.commission_pct),
      price_unit: form.price_unit,
      per_min_p: toNum(form.per_min_p),
      per_hour_p: toNum(form.per_hour_p),
      sort_order: toNum(form.sort_order) ?? 100,
      is_active: !!form.is_active,
      status: form.status,
      self_managed: !!form.self_managed,
    };
    try {
      if (editingId) {
        await api.adminUpdateConsultant(editingId, body);
        setMsg(tr("admin.consult.saved"));
      } else {
        if (!form.login_email.trim() || !body.business_name) { alert(tr("admin.consult.id_name_required")); return; }
        await api.adminCreateConsultant({ login_email: form.login_email.trim(), ...body });
        setMsg(tr("admin.consult.created"));
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
      keywords: (c.keywords || []).join(", "),
      rate_p: c.rate_p == null ? "" : String(c.rate_p),
      duration_min: c.duration_min_raw == null ? "" : String(c.duration_min_raw),
      commission_pct: c.commission_pct_raw == null ? "" : String(c.commission_pct_raw),
      price_unit: c.price_unit || "session",
      per_min_p: c.per_min_p == null ? "" : String(c.per_min_p),
      per_hour_p: c.per_hour_p == null ? "" : String(c.per_hour_p),
      sort_order: String(c.sort_order),
      is_active: c.is_active,
      status: c.status || "active",
      self_managed: c.self_managed !== false,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function cancelEdit() { setEditingId(null); setForm(emptyForm); }

  async function toggleActive(c: ConsultantAdmin) {
    try { await api.adminUpdateConsultant(c.id, { is_active: !c.is_active }); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function del(c: ConsultantAdmin) {
    if (!confirm(tr("admin.consult.del_confirm", { name: c.business_name }))) return;
    try { await api.adminDeleteConsultant(c.id); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function uploadSign(c: ConsultantAdmin, file: File) {
    const fd = new FormData(); fd.append("file", file);
    try { await api.adminUploadSignboard(c.id, fd); setMsg(tr("admin.consult.sign_ok")); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function saveSettings() {
    if (!settings) return;
    setErr(null); setMsg(null);
    try {
      const res = await api.adminPatchConsultationSettings(settings);
      setSettings(res.settings); setMsg(tr("admin.consult.settings_saved"));
    } catch (e: any) { setErr(e?.message || String(e)); }
  }

  const inp: React.CSSProperties = { padding: "6px 8px", border: "1px solid var(--line)", borderRadius: 6, width: "100%", boxSizing: "border-box" };
  const box: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 14, marginBottom: 16 };
  const fld: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 3, fontSize: 12, color: "var(--ink-600)" };

  return (
    <div>
      {/* ── 입점 문의 대기(신청 전 게이트) — [신청 허용] 시 해당 메일 ID에 신청서 작성이 열림 ── */}
      {inqs.length > 0 && (
        <div style={{ border: "1.5px solid var(--brand-500, #7a5cff)", background: "var(--brand-50, #f4f1ff)", borderRadius: 10, padding: 14, marginBottom: 16 }}>
          <h3 style={{ margin: "0 0 10px" }}>{tr("admin.consult.inq_title", { count: inqs.length })}</h3>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg)" }}>
                <th style={aTh}>{tr("admin.consult.inq_th_date")}</th><th style={aTh}>{tr("admin.consult.inq_th_email")}</th><th style={aTh}>{tr("admin.consult.inq_th_note")}</th><th style={aTh}>{tr("admin.consult.inq_th_action")}</th>
              </tr>
            </thead>
            <tbody>
              {inqs.map((q) => (
                <tr key={q.id}>
                  <td style={aTd}>{fmtKSTDate(q.created_at)}</td>
                  <td style={aTd}><b>{q.email}</b></td>
                  <td style={{ ...aTd, maxWidth: 340 }} title={q.note || ""}>{(q.note || "—").slice(0, 60)}{(q.note || "").length > 60 ? "…" : ""}</td>
                  <td style={aTd}>
                    <button onClick={() => allowInq(q)} style={{ marginRight: 6, background: "var(--brand-500)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 10px", cursor: "pointer" }}>{tr("admin.consult.inq_allow")}</button>
                    <button onClick={() => dismissInq(q)} style={{ background: "none", border: "1px solid var(--line)", borderRadius: 6, padding: "4px 10px", cursor: "pointer" }}>{tr("admin.consult.inq_dismiss")}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 입점 신청 대기(운영자 지시) — 승인=권한 부여, 반려=사유 알림 ── */}
      {apps.length > 0 && (
        <div style={{ border: "1.5px solid var(--gold, #b9862f)", background: "var(--gold-tint, #f6efdd)", borderRadius: 10, padding: 14, marginBottom: 16 }}>
          <h3 style={{ margin: "0 0 10px" }}>{tr("admin.consult.app_title", { count: apps.length })}</h3>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg)" }}>
                <th style={aTh}>{tr("admin.consult.app_th_date")}</th><th style={aTh}>{tr("admin.consult.app_th_email")}</th><th style={aTh}>{tr("admin.consult.app_th_name")}</th>
                <th style={aTh}>{tr("admin.consult.app_th_spec")}</th><th style={aTh}>{tr("admin.consult.app_th_contact")}</th><th style={aTh}>{tr("admin.consult.app_th_intro")}</th>
                <th style={aTh}>{tr("admin.consult.app_th_docs")}</th><th style={aTh}>{tr("admin.consult.app_th_terms")}</th><th style={aTh}>{tr("admin.consult.app_th_action")}</th>
              </tr>
            </thead>
            <tbody>
              {apps.map((a) => (
                <tr key={a.id}>
                  <td style={aTd}>{fmtKSTDate(a.created_at)}</td>
                  <td style={aTd}>{a.email}</td>
                  <td style={aTd}><b>{a.business_name}</b></td>
                  <td style={aTd}>{tr(`admin.spec.${a.specialty}`, a.specialty)}</td>
                  <td style={aTd}>{a.contact || "—"}</td>
                  <td style={{ ...aTd, maxWidth: 220 }} title={a.intro || ""}>{(a.intro || "—").slice(0, 40)}{(a.intro || "").length > 40 ? "…" : ""}</td>
                  <td style={aTd}>
                    {(a.docs || []).length === 0 ? <span style={{ color: "var(--ink-400)" }}>{tr("admin.consult.doc_none")}</span> : (a.docs || []).map((d) => (
                      <button key={d.id} title={d.name}
                              onClick={() => api.adminPartnerDocOpen(a.id, d.id).catch((e: any) => setErr(e?.message || tr("admin.consult.doc_open_fail")))}
                              style={{ display: "block", background: "none", border: "1px solid var(--line)", borderRadius: 6, padding: "2px 8px", marginBottom: 3, cursor: "pointer", fontSize: 12, whiteSpace: "nowrap" }}>
                        {d.kind === "biz_license" ? tr("admin.consult.doc_biz") : d.kind === "bank_book" ? tr("admin.consult.doc_bank") : tr("admin.consult.doc_etc")} {tr("admin.consult.doc_view")}
                      </button>
                    ))}
                  </td>
                  <td style={aTd}>v{a.terms_version}</td>
                  <td style={aTd}>
                    <button onClick={() => approveApp(a)} style={{ marginRight: 6, background: "var(--brand-500)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 10px", cursor: "pointer" }}>{tr("admin.consult.app_approve")}</button>
                    <button onClick={() => rejectApp(a)} style={{ background: "none", border: "1px solid var(--line)", borderRadius: 6, padding: "4px 10px", cursor: "pointer" }}>{tr("admin.consult.app_reject")}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}
      {msg && <div style={{ color: "seagreen", marginBottom: 8 }}>{msg}</div>}

      {/* 전역 기본값 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{tr("admin.consult.gd_title")}</div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 10 }}>
          {tr("admin.consult.gd_desc")}
        </div>
        {settings && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 10 }}>
            <NumField label={tr("admin.consult.gd_price")} value={settings.consultation_default_price_p}
              onChange={(v) => setSettings({ ...settings, consultation_default_price_p: v })} />
            <NumField label={tr("admin.consult.gd_duration")} value={settings.consultation_default_duration_min}
              onChange={(v) => setSettings({ ...settings, consultation_default_duration_min: v })} />
            <NumField label={tr("admin.consult.gd_min_price")} value={settings.consultation_min_price_p}
              onChange={(v) => setSettings({ ...settings, consultation_min_price_p: v })} />
            <NumField label={tr("admin.consult.gd_commission")} value={settings.consultation_commission_pct}
              onChange={(v) => setSettings({ ...settings, consultation_commission_pct: v })} />
            <NumField label={tr("admin.consult.gd_tax")} step="0.1" value={settings.consultation_tax_pct}
              onChange={(v) => setSettings({ ...settings, consultation_tax_pct: v })} />
            <NumField label={tr("admin.consult.gd_noshow")} value={settings.consultation_no_show_timeout_sec}
              onChange={(v) => setSettings({ ...settings, consultation_no_show_timeout_sec: v })} />
            <NumField label={tr("admin.consult.gd_extend_warn")} value={settings.consultation_extend_warn_sec}
              onChange={(v) => setSettings({ ...settings, consultation_extend_warn_sec: v })} />
            <NumField label={tr("admin.consult.gd_retention")} value={settings.consultation_retention_days}
              onChange={(v) => setSettings({ ...settings, consultation_retention_days: v })} />
            <NumField label={tr("admin.consult.gd_reserve_full")} value={settings.consultation_reserve_full_refund_hours ?? 24}
              onChange={(v) => setSettings({ ...settings, consultation_reserve_full_refund_hours: v })} />
            <NumField label={tr("admin.consult.gd_reserve_late")} value={settings.consultation_reserve_late_refund_pct ?? 50}
              onChange={(v) => setSettings({ ...settings, consultation_reserve_late_refund_pct: v })} />
            <NumField label={tr("admin.consult.gd_reserve_grace")} value={settings.consultation_reserve_grace_min ?? 10}
              onChange={(v) => setSettings({ ...settings, consultation_reserve_grace_min: v })} />
          </div>
        )}
        <button onClick={saveSettings} style={{ marginTop: 10 }}>{tr("admin.consult.gd_save")}</button>
      </div>

      {/* 등록/수정 폼 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>{editingId ? tr("admin.consult.form_edit_title", { id: editingId }) : tr("admin.consult.form_new_title")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <label style={fld}>{tr("admin.consult.f_login_email")} <span style={{ color: "#c00" }}>{tr("admin.consult.f_required")}</span>
            <input style={inp} placeholder={tr("admin.consult.f_login_ph")} value={form.login_email} disabled={!!editingId}
              onChange={(e) => setForm({ ...form, login_email: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_biz_name")} <span style={{ color: "#c00" }}>{tr("admin.consult.f_required")}</span>
            <input style={inp} placeholder={tr("admin.consult.f_biz_name_ph")} value={form.business_name}
              onChange={(e) => setForm({ ...form, business_name: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_spec")}
            <select style={inp} value={form.specialty}
              onChange={(e) => setForm({ ...form, specialty: e.target.value as ConsultantSpecialty })}>
              <option value="saju">{tr("admin.spec.saju")}</option>
              <option value="tarot">{tr("admin.spec.tarot")}</option>
              <option value="both">{tr("admin.spec.both")}</option>
            </select>
          </label>
          <label style={fld}>{tr("admin.consult.f_sort")}
            <select style={inp} value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })}>
              <option value="0">{tr("admin.consult.sort_top")}</option>
              <option value="50">{tr("admin.consult.sort_up")}</option>
              <option value="100">{tr("admin.consult.sort_normal")}</option>
              <option value="200">{tr("admin.consult.sort_down")}</option>
              <option value="1000">{tr("admin.consult.sort_bottom")}</option>
            </select>
          </label>
          <label style={fld}>{tr("admin.consult.f_price_unit")}
            <select style={inp} value={form.price_unit}
              onChange={(e) => setForm({ ...form, price_unit: e.target.value as ConsultantPriceUnit })}>
              <option value="session">{tr("admin.consult.unit_session")}</option>
              <option value="minute">{tr("admin.consult.unit_minute")}</option>
              <option value="hour">{tr("admin.consult.unit_hour")}</option>
            </select>
          </label>
          <label style={fld}>{tr("admin.consult.f_duration")}
            <input style={inp} type="number" placeholder={tr("admin.consult.f_default_ph")} value={form.duration_min}
              onChange={(e) => setForm({ ...form, duration_min: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_session_price")} {form.price_unit !== "session" && <span style={{ color: "#aaa" }}>{tr("admin.consult.when_session")}</span>}
            <input style={inp} type="number" placeholder={tr("admin.consult.f_default_ph")} value={form.rate_p}
              onChange={(e) => setForm({ ...form, rate_p: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_commission")}
            <input style={inp} type="number" placeholder={tr("admin.consult.f_default_ph")} value={form.commission_pct}
              onChange={(e) => setForm({ ...form, commission_pct: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_per_min")} {form.price_unit !== "minute" && <span style={{ color: "#aaa" }}>{tr("admin.consult.when_minute")}</span>}
            <input style={inp} type="number" placeholder={tr("admin.consult.per_min_ph")} value={form.per_min_p}
              onChange={(e) => setForm({ ...form, per_min_p: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_per_hour")} {form.price_unit !== "hour" && <span style={{ color: "#aaa" }}>{tr("admin.consult.when_hour")}</span>}
            <input style={inp} type="number" placeholder={tr("admin.consult.per_hour_ph")} value={form.per_hour_p}
              onChange={(e) => setForm({ ...form, per_hour_p: e.target.value })} />
          </label>
          <label style={fld}>{tr("admin.consult.f_status")}
            <select style={inp} value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as ConsultantStatus })}>
              <option value="active">{tr("admin.consult.status_active")}</option>
              <option value="coming_soon">{tr("admin.consult.status_coming")}</option>
              <option value="hidden">{tr("admin.consult.status_hidden")}</option>
            </select>
          </label>
          <label style={{ ...fld, flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "end", paddingBottom: 8 }}>
            <input type="checkbox" checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> {tr("admin.consult.f_active")}
          </label>
          <label style={{ ...fld, flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "end", paddingBottom: 8 }}>
            <input type="checkbox" checked={form.self_managed}
              onChange={(e) => setForm({ ...form, self_managed: e.target.checked })} /> {tr("admin.consult.f_self")}
          </label>
        </div>
        <label style={{ ...fld, marginTop: 10 }}>{tr("admin.consult.f_keywords")}
          <input style={inp} placeholder={tr("admin.consult.keywords_ph")} value={form.keywords}
            onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
        </label>
        <label style={{ ...fld, marginTop: 10 }}>{tr("admin.consult.f_intro")}
          <textarea style={{ ...inp, minHeight: 54 }} placeholder={tr("admin.consult.intro_ph")}
            value={form.intro} onChange={(e) => setForm({ ...form, intro: e.target.value })} />
        </label>
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <button onClick={submit}>{editingId ? tr("admin.consult.f_save") : tr("admin.consult.f_create")}</button>
          {editingId && <button onClick={cancelEdit} style={{ color: "#666" }}>{tr("admin.consult.f_cancel")}</button>}
        </div>
      </div>

      {/* 목록 */}
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>{tr("admin.consult.lt_sign")}</th>
            <th style={th}>{tr("admin.consult.lt_name_id")}</th>
            <th style={th}>{tr("admin.consult.lt_spec")}</th>
            <th style={th}>{tr("admin.consult.lt_price")}</th>
            <th style={th}>{tr("admin.consult.lt_commission")}</th>
            <th style={th}>{tr("admin.consult.lt_status")}</th>
            <th style={th}>{tr("admin.consult.lt_perf")}</th>
            <th style={th}>{tr("admin.consult.lt_active")}</th>
            <th style={th}>{tr("admin.consult.lt_action")}</th>
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
                    {tr("admin.consult.upload")}
                    <input type="file" accept="image/*" style={{ display: "none" }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadSign(c, f); e.currentTarget.value = ""; }} />
                  </label>
                </div>
              </td>
              <td style={td}>
                <div style={{ fontWeight: 700 }}>{c.business_name}</div>
                <div style={{ color: "#888", fontSize: 11 }}>
                  {c.login_email} {c.linked ? <span style={{ color: "seagreen" }}>{tr("admin.consult.linked")}</span> : <span style={{ color: "#c26a00" }}>{tr("admin.consult.not_joined")}</span>}
                </div>
              </td>
              <td style={td}>{tr(`admin.spec.${c.specialty}`, c.specialty)}</td>
              <td style={td}>{c.eff_price_p.toLocaleString()}P · {c.eff_duration_min}{tr("admin.min")}</td>
              <td style={td}>{c.eff_commission_pct}%</td>
              <td style={td}>
                {tr(`admin.presence.${c.presence}`, c.presence)}
                {c.status === "coming_soon" && <div style={{ fontSize: 10, color: "#c26a00" }}>{tr("admin.consult.coming")}</div>}
                {c.status === "hidden" && <div style={{ fontSize: 10, color: "#999" }}>{tr("admin.consult.hidden")}</div>}
                {c.self_managed === false && <div style={{ fontSize: 10, color: "#c2334f" }}>{tr("admin.consult.self_lock")}</div>}
              </td>
              <td style={td}>
                {c.stats.sessions}{tr("admin.cnt")} · {c.stats.revenue_p.toLocaleString()}P · {c.stats.payout_pending_p.toLocaleString()}P
              </td>
              <td style={td}>
                <button onClick={() => toggleActive(c)}>{c.is_active ? "ON" : "OFF"}</button>
              </td>
              <td style={td}>
                <button onClick={() => startEdit(c)}>{tr("admin.consult.list_edit")}</button>{" "}
                <button onClick={() => del(c)} style={{ color: "crimson" }}>{tr("admin.consult.list_del")}</button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td style={td} colSpan={9}>{tr("admin.consult.list_empty")}</td></tr>
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
  const { t: tr } = useTranslation();
  const [rows, setRows] = useState<ConsultationSettlementRow[]>([]);
  const [totals, setTotals] = useState<SettlementTotals | null>(null);
  const [consultants, setConsultants] = useState<ConsultantAdmin[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "pending" | "settled">("");
  const [cycle, setCycle] = useState<string>("");            // 정산월(YYYY-MM) — ''=전체
  const [currentCycle, setCurrentCycle] = useState<string>("");
  const [payoutDate, setPayoutDate] = useState<string>("");  // 선택 정산월의 지급예정일(마지막 영업일)
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    try {
      const [s, c] = await Promise.all([
        api.adminSettlements(undefined, statusFilter || undefined, cycle || undefined),
        api.adminConsultants(),
      ]);
      setRows(s.items); setTotals(s.totals); setConsultants(c.items);
      setCurrentCycle(s.current_cycle || "");
      setPayoutDate(s.payout_date || "");
    } catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); }, [statusFilter, cycle]);

  // 정산월 선택지 — 현재 정산월 기준 최근 6개월
  const cycleOptions = (() => {
    if (!currentCycle) return [] as string[];
    const [y0, m0] = [Number(currentCycle.slice(0, 4)), Number(currentCycle.slice(5, 7))];
    return Array.from({ length: 6 }, (_, i) => {
      let y = y0, m = m0 - i;
      while (m < 1) { m += 12; y -= 1; }
      return `${y}-${String(m).padStart(2, "0")}`;
    });
  })();

  const won = (n: number) => tr("admin.settle.won", { n: n.toLocaleString() });

  async function settle(r: ConsultationSettlementRow) {
    try { await api.adminSettleSettlement(r.id); await load(); } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function unsettle(r: ConsultationSettlementRow) {
    try { await api.adminUnsettleSettlement(r.id); await load(); } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function settleAll(c: ConsultantAdmin) {
    if (!confirm(tr("admin.settle.settle_all_confirm", { name: c.business_name, amount: won(c.stats.payout_pending_p) }))) return;
    try {
      const r = await api.adminSettleAllConsultant(c.id);
      setMsg(tr("admin.settle.settle_all_ok", { name: c.business_name, count: r.settled, amount: won(r.total_payout_p) }));
      await load();
    } catch (e: any) { alert(e?.message || String(e)); }
  }

  const pendingConsultants = consultants.filter((c) => c.stats.payout_pending_p > 0);
  const box: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 14, marginBottom: 16 };

  return (
    <div>
      {/* 정산 규칙(운영자 확정): 매월 25일 24시 마감(전월 26일~당월 25일 실적) → 당월 마지막 영업일 지급(수동 송금) */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <label style={{ fontSize: 13 }}>{tr("admin.settle.cycle_label")}{" "}
          <select value={cycle} onChange={(e) => setCycle(e.target.value)} style={{ padding: "4px 8px" }}>
            <option value="">{tr("admin.settle.cycle_all")}</option>
            {cycleOptions.map((c) => (
              <option key={c} value={c}>{c} {c === currentCycle ? tr("admin.settle.cycle_current") : ""}</option>
            ))}
          </select>
        </label>
        {cycle && payoutDate && (
          <span style={{ fontSize: 13, background: "var(--gold-tint, #f6efdd)", border: "1px solid var(--gold, #b9862f)", borderRadius: 999, padding: "4px 12px", fontWeight: 700 }}>
            {tr("admin.settle.payout_badge", { date: payoutDate })}
          </span>
        )}
        <span style={{ fontSize: 12, color: "var(--ink-400)" }}>{tr("admin.settle.period_basis")}</span>
        {totals?.commission_p !== undefined && (
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--brand-700)" }}>
            {tr("admin.settle.commission_total", { amount: (totals.commission_p || 0).toLocaleString() })}
          </span>
        )}
      </div>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}
      {msg && <div style={{ color: "seagreen", marginBottom: 8 }}>{msg}</div>}
      <div style={{ fontSize: 12, color: "#888", marginBottom: 12 }}>
        {tr("admin.settle.rule_desc")}
      </div>

      {totals && (
        <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <SumCard label={tr("admin.settle.sc_revenue")} value={won(totals.revenue_p)} />
          <SumCard label={tr("admin.settle.sc_pending")} value={won(totals.payout_pending_p)} color="#c26a00" />
          <SumCard label={tr("admin.settle.sc_settled")} value={won(totals.payout_settled_p)} color="#1a8f4c" />
        </div>
      )}

      {pendingConsultants.length > 0 && (
        <div style={box}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>{tr("admin.settle.pending_title")}</div>
          {pendingConsultants.map((c) => (
            <div key={c.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #f0f0f4" }}>
              <span>{c.business_name} <span style={{ color: "#888", fontSize: 12 }}>· {c.stats.sessions}{tr("admin.cnt")}</span></span>
              <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <b style={{ color: "#c26a00" }}>{won(c.stats.payout_pending_p)}</b>
                <button onClick={() => settleAll(c)}>{tr("admin.settle.settle_all_btn")}</button>
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginBottom: 10 }}>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "" | "pending" | "settled")}>
          <option value="">{tr("admin.settle.filter_all")}</option>
          <option value="pending">{tr("admin.settle.filter_pending")}</option>
          <option value="settled">{tr("admin.settle.filter_settled")}</option>
        </select>
      </div>

      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f7f7f7" }}>
            <th style={th}>{tr("admin.settle.th_consultant")}</th>
            <th style={th}>{tr("admin.settle.th_revenue")}</th>
            <th style={th}>{tr("admin.settle.th_commission")}</th>
            <th style={th}>{tr("admin.settle.th_taxable")}</th>
            <th style={th}>{tr("admin.settle.th_tax")}</th>
            <th style={th}>{tr("admin.settle.th_payout")}</th>
            <th style={th}>{tr("admin.settle.th_status")}</th>
            <th style={th}>{tr("admin.settle.th_settled_date")}</th>
            <th style={th}>{tr("admin.settle.th_action")}</th>
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
              <td style={td}>{r.status === "settled" ? <span style={{ color: "#1a8f4c" }}>{tr("admin.settle.st_settled")}</span> : <span style={{ color: "#c26a00" }}>{tr("admin.settle.st_pending")}</span>}</td>
              <td style={td}>{r.settled_at ? fmtKSTDate(r.settled_at) : "—"}</td>
              <td style={td}>
                {r.status === "pending"
                  ? <button onClick={() => settle(r)}>{tr("admin.settle.act_settle")}</button>
                  : <button onClick={() => unsettle(r)} style={{ color: "#666" }}>{tr("admin.settle.act_unsettle")}</button>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td style={td} colSpan={9}>{tr("admin.settle.empty")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// -------- 과금/한도 설정 --------

function BillingTab() {
  const { t: tr } = useTranslation();
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
      setMsg(tr("admin.billing.saved"));
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  if (err && !s) return <div style={{ color: "crimson" }}>{err}</div>;
  if (!s) return <div>{tr("admin.loading")}</div>;

  return (
    <div style={{ maxWidth: 520 }}>
      <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 16, display: "grid", gap: 12 }}>
        <Field label={tr("admin.billing.f_free_quota")}>
          <input
            type="number"
            value={s.free_quota_count}
            onChange={(e) => setS({ ...s, free_quota_count: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_reset")}>
          <select
            value={s.free_quota_reset}
            onChange={(e) => setS({ ...s, free_quota_reset: e.target.value as AppSettings["free_quota_reset"] })}
          >
            <option value="none">{tr("admin.billing.reset_none")}</option>
            <option value="daily">{tr("admin.billing.reset_daily")}</option>
            <option value="monthly">{tr("admin.billing.reset_monthly")}</option>
          </select>
        </Field>
        <Field label={tr("admin.billing.f_cost_basic")}>
          <input
            type="number"
            value={s.credit_cost_basic}
            onChange={(e) => setS({ ...s, credit_cost_basic: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_cost_deep")}>
          <input
            type="number"
            value={s.credit_cost_deep}
            onChange={(e) => setS({ ...s, credit_cost_deep: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_reveal")}>
          <input
            type="number"
            value={s.preview_reveal_cost}
            onChange={(e) => setS({ ...s, preview_reveal_cost: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_preview_chars")}>
          <input
            type="number"
            value={s.preview_max_chars}
            onChange={(e) => setS({ ...s, preview_max_chars: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_fb_pct")}>
          <input
            type="number"
            value={s.feedback_reward_pct}
            onChange={(e) => setS({ ...s, feedback_reward_pct: Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0)) })}
          />
        </Field>
        <Field label={tr("admin.billing.f_fb_cap")}>
          <input
            type="number"
            value={s.feedback_reward_daily_cap}
            onChange={(e) => setS({ ...s, feedback_reward_daily_cap: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_amulet")}>
          <input
            type="number"
            min={0}
            value={s.amulet_cost_p}
            onChange={(e) => setS({ ...s, amulet_cost_p: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_video")}>
          <input
            type="number"
            min={0}
            value={s.video_gen_cost}
            onChange={(e) => setS({ ...s, video_gen_cost: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_review_reward")}>
          <input
            type="number"
            min={0}
            value={s.review_reward_p}
            onChange={(e) => setS({ ...s, review_reward_p: parseInt(e.target.value, 10) || 0 })}
          />
        </Field>
        <Field label={tr("admin.billing.f_ext_llm")}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={s.external_llm_enabled}
              onChange={(e) => setS({ ...s, external_llm_enabled: e.target.checked })}
            />
            {s.external_llm_enabled ? tr("admin.billing.use") : tr("admin.billing.no_use")}
          </label>
        </Field>

        <div style={{ borderTop: "1px solid #eee", marginTop: 4, paddingTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#333", marginBottom: 4 }}>
            {tr("admin.billing.premium_title")}
          </div>
          <div style={{ fontSize: 12, color: "#777", marginBottom: 10 }}>
            {tr("admin.billing.premium_desc", { basic: (s.credit_cost_basic ?? 0).toLocaleString(), deep: (s.credit_cost_deep ?? 0).toLocaleString() })}
          </div>
        </div>
        <Field label={tr("admin.billing.f_discount")}>
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
          ["entry_cost_compat", "e_compat"],
          ["entry_cost_taekil", "e_taekil"],
          ["entry_cost_jakmyeong", "e_jakmyeong"],
          ["entry_cost_gaemyeong", "e_gaemyeong"],
          ["entry_cost_aho", "e_aho"],
          ["entry_cost_tarot", "e_tarot"],
          ["entry_cost_sinnyeon", "e_sinnyeon"],
        ] as [keyof AppSettings, string][]).map(([key, labelKey]) => {
          const base = (s[key] as number) || 0;
          const disc = s.premium_entry_discount_pct || 0;
          const eff = Math.max(0, Math.round((base * (100 - disc)) / 100));
          return (
            <Field key={key} label={tr(`admin.billing.${labelKey}`)}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="number"
                  min={0}
                  value={base}
                  onChange={(e) => setS({ ...s, [key]: parseInt(e.target.value, 10) || 0 })}
                />
                {disc > 0 && (
                  <span style={{ fontSize: 12, color: "crimson" }}>
                    {tr("admin.billing.eff_price", { eff: eff.toLocaleString() })}
                  </span>
                )}
              </div>
            </Field>
          );
        })}

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={save} disabled={saving}>{saving ? tr("admin.billing.saving") : tr("admin.billing.save")}</button>
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
  const { t: tr } = useTranslation();
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
    if (!form.name.trim() || !form.body.trim()) return alert(tr("admin.tpl.name_body_required"));
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
    if (!confirm(tr("admin.tpl.del_confirm", { name: t.name, ver: t.version }))) return;
    await api.adminDeleteTemplate(t.id);
    if (editing?.id === t.id) startNew();
    await load();
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      <div>
        {err && <div style={{ color: "crimson" }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <strong>{tr("admin.tpl.list_title")}</strong>
          <button onClick={startNew}>{tr("admin.tpl.new_btn")}</button>
        </div>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f7f7f7" }}>
              <th style={th}>{tr("admin.tpl.th_name")}</th>
              <th style={th}>{tr("admin.tpl.th_version")}</th>
              <th style={th}>{tr("admin.tpl.th_active")}</th>
              <th style={th}>{tr("admin.tpl.th_action")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} style={editing?.id === t.id ? { background: "#eef9f6" } : undefined}>
                <td style={td}>{t.name}</td>
                <td style={td}>v{t.version}</td>
                <td style={td}>{t.active ? "✅" : ""}</td>
                <td style={td}>
                  <button onClick={() => startEdit(t)}>{tr("admin.tpl.edit")}</button>{" "}
                  {!t.active && <button onClick={() => activate(t)}>{tr("admin.tpl.activate")}</button>}{" "}
                  <button onClick={() => del(t)} style={{ color: "crimson" }}>{tr("admin.tpl.del")}</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td style={td} colSpan={4}>{tr("admin.tpl.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>{editing ? tr("admin.tpl.edit_title", { name: editing.name, ver: editing.version }) : tr("admin.tpl.new_title")}</div>
        <input
          style={{ width: "100%", marginBottom: 8 }}
          placeholder={tr("admin.tpl.name_ph")}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <textarea
          style={{ width: "100%", minHeight: 240, fontFamily: "inherit", fontSize: 13 }}
          placeholder={tr("admin.tpl.body_ph")}
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
        />
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: "8px 0" }}>
          <input
            type="checkbox"
            checked={form.active}
            onChange={(e) => setForm({ ...form, active: e.target.checked })}
          />
          {tr("admin.tpl.active_label")}
        </label>
        <div>
          <button onClick={save}>{editing ? tr("admin.tpl.save") : tr("admin.tpl.add")}</button>
        </div>
      </div>
    </div>
  );
}

// -------- 고객센터 (문의 게시판 + 메일 수신자 CRUD) --------
function SupportTab() {
  const { t: tr } = useTranslation();
  const SUPPORT_STATUSES: { value: SupportStatus; label: string }[] = [
    { value: "received", label: tr("admin.support.st_received") },
    { value: "in_progress", label: tr("admin.support.st_in_progress") },
    { value: "resolved", label: tr("admin.support.st_resolved") },
    { value: "rejected", label: tr("admin.support.st_rejected") },
  ];
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
    const won = t.amount != null ? tr("admin.support.won_amt", { amount: t.amount.toLocaleString() }) : "";
    if (!window.confirm(tr("admin.support.refund_confirm", { id: t.id, order: t.order_id, won }))) return;
    try {
      const r = await api.adminSupportRefundTicket(t.id);
      alert(tr("admin.support.refund_done", { mock: r.refund.mock ? tr("admin.support.refund_mock") : "", recovered: r.refund.recovered_credits.toLocaleString() }));
      loadTickets();
    } catch (e: any) {
      alert(tr("admin.support.refund_fail", { err: e?.message || String(e) }));
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
    if (!window.confirm(tr("admin.support.del_recipient_confirm", { email: r.email }))) return;
    try { await api.adminSupportDeleteRecipient(r.id); loadRecipients(); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }

  const shortDt = (iso?: string | null) => fmtKSTShort(iso);

  return (
    <div>
      {err && <div className="err" style={{ marginBottom: 12 }}>{err}</div>}

      {/* 메일 수신자 CRUD */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("admin.support.recipients_title")}</h3>
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          <Trans i18nKey="admin.support.recipients_note" components={{ b: <b /> }} />
        </p>
        <div style={{ display: "flex", gap: 8, margin: "10px 0" }}>
          <input
            className="bf-input" type="email" placeholder="admin@example.com" value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addRecipient(); }}
            style={{ maxWidth: 320 }}
          />
          <button onClick={addRecipient}>{tr("admin.support.add")}</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {recipients.length === 0 && <div style={{ fontSize: 13, color: "var(--ink-400)" }}>{tr("admin.support.no_recipients")}</div>}
          {recipients.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
              <span style={{ flex: 1, color: r.active ? "var(--ink-900)" : "var(--ink-400)", textDecoration: r.active ? "none" : "line-through" }}>
                {r.email}
              </span>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={r.active} onChange={() => toggleRecipient(r)} /> {tr("admin.support.active")}
              </label>
              <button className="ghost" style={{ color: "#c0392b" }} onClick={() => delRecipient(r)}>{tr("admin.support.del")}</button>
            </div>
          ))}
        </div>
      </div>

      {/* 문의 게시판 */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0 }}>{tr("admin.support.board_title", { count: tickets.length })}</h3>
          <select value={filter} onChange={(e) => setFilter(e.target.value as SupportStatus | "")} style={{ maxWidth: 160 }}>
            <option value="">{tr("admin.support.filter_all")}</option>
            {SUPPORT_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
          {tickets.length === 0 && <div style={{ fontSize: 13, color: "var(--ink-400)" }}>{tr("admin.support.no_tickets")}</div>}
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
                {t.user_id != null ? tr("admin.support.meta_member", { id: t.user_id }) : tr("admin.support.meta_guest")}
                {t.order_id ? tr("admin.support.meta_order", { order: t.order_id }) : ""}
                {t.amount != null ? tr("admin.support.meta_amount", { amount: t.amount.toLocaleString() }) : ""}
              </div>
              <div style={{ whiteSpace: "pre-wrap", fontSize: 13, color: "var(--ink-900)", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", margin: "6px 0" }}>
                {t.message}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: 12, color: "var(--ink-400)" }}>{tr("admin.support.status_label")}</span>
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
                    {tr("admin.support.refund_btn", { order: t.order_id })}
                  </button>
                  <span style={{ fontSize: 11, color: "var(--ink-400)" }}>
                    {tr("admin.support.refund_note")}
                  </span>
                </div>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <input
                  className="bf-input"
                  placeholder={tr("admin.support.note_ph")}
                  value={noteDraft[t.id] ?? t.admin_note ?? ""}
                  onChange={(e) => setNoteDraft((d) => ({ ...d, [t.id]: e.target.value }))}
                  style={{ flex: 1 }}
                />
                <button onClick={() => saveNote(t.id)}>{tr("admin.support.save_note")}</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// -------- B-3 이용 후기 승인 (수집 → 승인 시 공개 노출 + 리워드 지급) --------
function ReviewsTab() {
  const { t: tr } = useTranslation();
  const REVIEW_STATUSES: { key: string; label: string }[] = [
    { key: "pending", label: tr("admin.reviews.st_pending") },
    { key: "approved", label: tr("admin.reviews.st_approved") },
    { key: "rejected", label: tr("admin.reviews.st_rejected") },
  ];
  const [items, setItems] = useState<Review[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("pending");
  const [busy, setBusy] = useState<number | null>(null);

  const load = () =>
    api.adminReviews(filter || undefined, 100, 0)
      .then((r) => { setItems(r.items); setTotal(r.total); })
      .catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filter]);

  async function setStatus(id: number, status: "pending" | "approved" | "rejected") {
    setBusy(id);
    try {
      await api.adminUpdateReview(id, status);
      await load();
    } catch (e: any) {
      alert(e?.message || tr("admin.reviews.status_fail"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>{tr("admin.reviews.title", { count: total })}</h3>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">{tr("admin.reviews.filter_all")}</option>
          {REVIEW_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <span style={{ fontSize: 12, color: "var(--ink-400)" }}>
          {tr("admin.reviews.note")}
        </span>
      </div>
      {items.length === 0 && <p style={{ color: "var(--ink-400)" }}>{tr("admin.reviews.empty")}</p>}
      <div style={{ display: "grid", gap: 10 }}>
        {items.map((r) => (
          <div key={r.id} className="card" style={{ border: "1px solid var(--line)", borderRadius: 10, padding: 12 }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--ink-500)" }}>
              <b style={{ color: "var(--ink-800)" }}>#{r.id}</b>
              <span style={{ color: "#f6b73c" }}>{"★".repeat(r.rating)}<span style={{ color: "var(--line)" }}>{"★".repeat(5 - r.rating)}</span></span>
              <span>{r.display_name}</span>
              <span style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "1px 7px", fontSize: 11 }}>{r.source_label}</span>
              <span>{r.created_at ? fmtKSTDateTime(r.created_at) : ""}</span>
              <b style={{
                color: r.status === "approved" ? "var(--brand-600)" : r.status === "rejected" ? "#c62828" : "var(--ink-500)",
              }}>{REVIEW_STATUSES.find((s) => s.key === r.status)?.label}</b>
            </div>
            <p style={{ margin: "8px 0", fontSize: 14, lineHeight: 1.6 }}>{r.content}</p>
            <div style={{ display: "flex", gap: 6 }}>
              {REVIEW_STATUSES.map((s) => (
                <button
                  key={s.key}
                  disabled={busy === r.id || r.status === s.key}
                  onClick={() => setStatus(r.id, s.key as "pending" | "approved" | "rejected")}
                  style={{
                    padding: "4px 12px", borderRadius: 999, cursor: "pointer",
                    background: r.status === s.key ? "var(--brand-500)" : "transparent",
                    color: r.status === s.key ? "#fff" : "var(--ink-600)",
                    border: r.status === s.key ? "none" : "1px solid var(--line)",
                  }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// -------- 운영설정 (사업자 정보 · 약관 버전/본문 · 메일 SMTP) --------
type SK = keyof SiteSettings;

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
  const { t: tr } = useTranslation();
  const BIZ_FIELDS: { key: SK; label: string; ph?: string }[] = [
    { key: "service_name", label: tr("admin.site.f_service_name"), ph: tr("admin.site.ph_service_name") },
    { key: "biz_name", label: tr("admin.site.f_biz_name"), ph: tr("admin.site.ph_biz_name") },
    { key: "biz_ceo", label: tr("admin.site.f_biz_ceo") },
    { key: "biz_reg_no", label: tr("admin.site.f_biz_reg_no"), ph: tr("admin.site.ph_biz_reg_no") },
    { key: "biz_mailorder_no", label: tr("admin.site.f_biz_mailorder"), ph: tr("admin.site.ph_biz_mailorder") },
    { key: "biz_address", label: tr("admin.site.f_biz_address") },
    { key: "biz_tel", label: tr("admin.site.f_biz_tel"), ph: tr("admin.site.ph_biz_tel") },
    { key: "biz_hours", label: tr("admin.site.f_biz_hours"), ph: tr("admin.site.ph_biz_hours") },
    { key: "biz_email", label: tr("admin.site.f_biz_email"), ph: tr("admin.site.ph_biz_email") },
    { key: "biz_privacy_officer", label: tr("admin.site.f_biz_privacy") },
    { key: "biz_hosting", label: tr("admin.site.f_biz_hosting") },
  ];
  const VER_FIELDS: { key: SK; label: string; ph?: string }[] = [
    { key: "terms_version", label: tr("admin.site.f_terms_ver"), ph: tr("admin.site.ph_ver") },
    { key: "privacy_version", label: tr("admin.site.f_privacy_ver"), ph: tr("admin.site.ph_ver") },
    { key: "refund_version", label: tr("admin.site.f_refund_ver"), ph: tr("admin.site.ph_ver") },
    { key: "min_age_years", label: tr("admin.site.f_min_age"), ph: tr("admin.site.ph_min_age") },
  ];
  const BODY_FIELDS: { key: SK; label: string }[] = [
    { key: "legal_body_terms", label: tr("admin.site.b_terms") },
    { key: "legal_body_privacy", label: tr("admin.site.b_privacy") },
    { key: "legal_body_refund", label: tr("admin.site.b_refund") },
    { key: "legal_body_disclaimer", label: tr("admin.site.b_disclaimer") },
  ];
  const [form, setForm] = useState<SiteSettings | null>(null);
  const [orig, setOrig] = useState<SiteSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testBusy, setTestBusy] = useState(false);
  const [testRes, setTestRes] = useState<{ ok: boolean; detail: string } | null>(null);

  async function sendTestEmail() {
    setTestBusy(true); setTestRes(null);
    try {
      const r = await api.adminTestEmail(testTo.trim() || undefined);
      setTestRes({ ok: r.ok, detail: r.detail });
    } catch (e: any) {
      setTestRes({ ok: false, detail: String(e?.message || e) });
    } finally { setTestBusy(false); }
  }

  useEffect(() => {
    api.adminGetSiteSettings()
      .then((r) => { setForm(r.settings); setOrig(r.settings); })
      .catch((e) => setErr(String(e?.message || e)));
  }, []);

  if (!form || !orig) return <div>{err ? <div className="err">{err}</div> : tr("admin.loading")}</div>;
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
    if (Object.keys(changed).length === 0) { setMsg(tr("admin.site.no_change")); return; }
    setBusy(true); setMsg(null); setErr(null);
    try {
      const r = await api.adminPatchSiteSettings(changed);
      setForm(r.settings); setOrig(r.settings);
      setMsg(tr("admin.site.saved"));
    } catch (e: any) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <SiteSection title={tr("admin.site.biz_title")}>
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          {tr("admin.site.biz_note")}
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {BIZ_FIELDS.map((x) => (
            <SiteField key={x.key} label={x.label} ph={x.ph} value={f[x.key]} onChange={(v) => up(x.key, v)} />
          ))}
        </div>
      </SiteSection>

      <SiteSection title={tr("admin.site.ver_title")}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
          {VER_FIELDS.map((x) => (
            <SiteField key={x.key} label={x.label} ph={x.ph} value={f[x.key]} onChange={(v) => up(x.key, v)} />
          ))}
        </div>
        <p style={{ fontSize: 11.5, color: "var(--ink-400)" }}>{tr("admin.site.ver_note")}</p>
      </SiteSection>

      <SiteSection title={tr("admin.site.smtp_title")}>
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          <Trans i18nKey="admin.site.smtp_note" components={{ b: <b /> }} />
        </p>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center", margin: "6px 0 10px" }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={checked("smtp_enabled")} onChange={(e) => up("smtp_enabled", e.target.checked ? "true" : "false")} />
            {tr("admin.site.smtp_use")}
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={checked("smtp_use_tls")} onChange={(e) => up("smtp_use_tls", e.target.checked ? "true" : "false")} />
            {tr("admin.site.smtp_tls")}
          </label>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10 }}>
          <SiteField label={tr("admin.site.smtp_host")} ph="smtp.gmail.com" value={f.smtp_host} onChange={(v) => up("smtp_host", v)} />
          <SiteField label={tr("admin.site.smtp_port")} ph="587" value={f.smtp_port} onChange={(v) => up("smtp_port", v)} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <SiteField label={tr("admin.site.smtp_user")} ph="account@gmail.com" value={f.smtp_user} onChange={(v) => up("smtp_user", v)} />
          <SiteField label={tr("admin.site.smtp_pw")} type="password" ph={tr("admin.site.smtp_pw_ph")} value={f.smtp_password} onChange={(v) => up("smtp_password", v)} />
        </div>
        <SiteField label={tr("admin.site.smtp_from")} ph={tr("admin.site.smtp_from_ph")} value={f.smtp_from} onChange={(v) => up("smtp_from", v)} />

        <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-600)", marginBottom: 4 }}>{tr("admin.site.test_title")}</div>
          <p style={{ fontSize: 11.5, color: "var(--ink-400)", margin: "0 0 8px" }}>
            <Trans i18nKey="admin.site.test_note" components={{ b: <b /> }} />
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              className="bf-input" type="email" style={{ flex: "1 1 240px", minWidth: 0 }}
              placeholder={tr("admin.site.test_to_ph")} value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
            />
            <button
              onClick={sendTestEmail} disabled={testBusy}
              style={{
                padding: "9px 16px", borderRadius: 10, border: "none", fontWeight: 700, fontSize: 13,
                background: "var(--brand-grad)", color: "#fff", cursor: testBusy ? "default" : "pointer", opacity: testBusy ? 0.6 : 1,
              }}
            >
              {testBusy ? tr("admin.site.test_busy") : tr("admin.site.test_btn")}
            </button>
          </div>
          {testRes && (
            <div style={{ marginTop: 8, fontSize: 12.5, fontWeight: 600, color: testRes.ok ? "#15803d" : "#b91c1c" }}>
              {testRes.ok ? "✅ " : "⚠️ "}{testRes.detail}
            </div>
          )}
        </div>
      </SiteSection>

      <SiteSection title={tr("admin.site.body_title")}>
        <p style={{ fontSize: 12, color: "var(--ink-400)", marginTop: -4 }}>
          <Trans i18nKey="admin.site.body_note" components={{ b: <b />, c: <code /> }} />
        </p>
        {BODY_FIELDS.map((x) => (
          <div key={x.key} className="bf-field" style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-600)", marginBottom: 4 }}>
              {x.label} {String(f[x.key] ?? "").trim() ? tr("admin.site.body_overwrite") : tr("admin.site.body_default")}
            </label>
            <textarea
              className="sf-textarea" rows={4}
              value={f[x.key] ?? ""}
              placeholder={tr("admin.site.body_ph")}
              onChange={(e) => up(x.key, e.target.value)}
            />
          </div>
        ))}
      </SiteSection>

      <div style={{ display: "flex", alignItems: "center", gap: 12, position: "sticky", bottom: 0, background: "var(--bg)", padding: "10px 0" }}>
        <button onClick={save} disabled={busy} style={{ fontWeight: 700 }}>{busy ? tr("admin.site.save_busy") : tr("admin.site.save_all")}</button>
        {msg && <span style={{ color: "var(--brand-600)", fontSize: 13 }}>{msg}</span>}
        {err && <span className="err" style={{ margin: 0 }}>{err}</span>}
      </div>
    </div>
  );
}

// -------- 타로 카드 해석/키워드 편집 --------

function KeywordEditor({ label, value, onChange }: {
  label: string; value: string[]; onChange: (v: string[]) => void;
}) {
  const { t: tr } = useTranslation();
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
            <button type="button" aria-label={tr("admin.tarot.kw_del_aria", { k })} onClick={() => onChange(value.filter((x) => x !== k))} style={{ border: "none", background: "none", cursor: "pointer", color: "crimson", padding: 0, fontSize: 14, lineHeight: 1 }}>×</button>
          </span>
        ))}
        {value.length === 0 && <span style={{ color: "#bbb", fontSize: 12 }}>{tr("admin.tarot.kw_empty")}</span>}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={tr("admin.tarot.kw_ph")}
          style={{ flex: 1, fontSize: 13, padding: "5px 8px" }}
        />
        <button type="button" onClick={add}>{tr("admin.tarot.kw_add")}</button>
      </div>
    </div>
  );
}

function CardEditor({ card, onSaved }: { card: TarotAdminCard; onSaved: (u: TarotAdminCard) => void }) {
  const { t: tr } = useTranslation();
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
    if (!kwUp.length || !kwRev.length) { alert(tr("admin.tarot.kw_min")); return; }
    if (!iUp.trim() || !iRev.trim()) { alert(tr("admin.tarot.interp_min")); return; }
    setBusy(true); setErr(null); setMsg(null);
    try {
      const u = await api.adminUpdateTarotCard(card.code, { keywords_up: kwUp, keywords_rev: kwRev, interp_up: iUp, interp_rev: iRev });
      onSaved(u); setMsg(tr("admin.tarot.saved"));
    } catch (e: any) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  }
  async function reset() {
    if (!confirm(tr("admin.tarot.reset_confirm", { name: card.name_kr }))) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const u = await api.adminResetTarotCard(card.code);
      setKwUp(u.keywords_up); setKwRev(u.keywords_rev); setIUp(u.interp_up); setIRev(u.interp_rev);
      onSaved(u); setMsg(tr("admin.tarot.reset_done"));
    } catch (e: any) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  }

  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 14 }}>
        <img src={card.image_url} alt="" style={{ width: 52, height: 88, objectFit: "cover", borderRadius: 4 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{card.name_kr} <span style={{ color: "#999", fontWeight: 400, fontSize: 14 }}>{card.name_en}</span></div>
          <div style={{ fontSize: 12, color: "#888" }}>{card.arcana === "major" ? tr("admin.tarot.major") : tr(`admin.tarot.suit.${card.suit || ""}`, card.suit || "")} · {card.code}</div>
          <div style={{ fontSize: 11, color: card.overridden ? "var(--brand-600)" : "#aaa", marginTop: 2 }}>
            {card.overridden ? `${tr("admin.tarot.edited")}${card.updated_at ? " · " + fmtKSTShort(card.updated_at) : ""}` : tr("admin.tarot.draft")}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--brand-600)", marginBottom: 8 }}>{tr("admin.tarot.up_title")}</div>
          <KeywordEditor label={tr("admin.tarot.up_kw")} value={kwUp} onChange={setKwUp} />
          <div style={{ fontSize: 12, color: "#888", margin: "4px 0" }}>{tr("admin.tarot.up_interp")}</div>
          <textarea value={iUp} onChange={(e) => setIUp(e.target.value)} rows={6} style={{ width: "100%", boxSizing: "border-box", fontSize: 13, lineHeight: 1.6, padding: 8, resize: "vertical" }} />
          <div style={{ textAlign: "right", fontSize: 11, color: iUp.length > 2000 ? "crimson" : "#bbb" }}>{iUp.length}/2000</div>
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13, color: "#6b5bb0", marginBottom: 8 }}>{tr("admin.tarot.rev_title")}</div>
          <KeywordEditor label={tr("admin.tarot.rev_kw")} value={kwRev} onChange={setKwRev} />
          <div style={{ fontSize: 12, color: "#888", margin: "4px 0" }}>{tr("admin.tarot.rev_interp")}</div>
          <textarea value={iRev} onChange={(e) => setIRev(e.target.value)} rows={6} style={{ width: "100%", boxSizing: "border-box", fontSize: 13, lineHeight: 1.6, padding: 8, resize: "vertical" }} />
          <div style={{ textAlign: "right", fontSize: 11, color: iRev.length > 2000 ? "crimson" : "#bbb" }}>{iRev.length}/2000</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
        <button onClick={save} disabled={busy || !dirty} style={{ fontWeight: 700 }}>{busy ? tr("admin.tarot.save_busy") : dirty ? tr("admin.tarot.save_dirty") : tr("admin.tarot.save_clean")}</button>
        <button onClick={reset} disabled={busy || !card.overridden} style={{ color: "crimson" }}>{tr("admin.tarot.reset_btn")}</button>
        {msg && <span style={{ color: "var(--brand-600)", fontSize: 13 }}>{msg}</span>}
        {err && <span className="err" style={{ margin: 0 }}>{err}</span>}
      </div>
    </div>
  );
}

function TarotTab() {
  const { t: tr } = useTranslation();
  const [cards, setCards] = useState<TarotAdminCard[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  // 재학습(확정 스냅샷 버전화) — 수동 1일 1회 + 야간(04:15) 패리티 자동
  const [learn, setLearn] = useState<TarotLearnStatus | null>(null);
  const [learning, setLearning] = useState(false);

  async function load() {
    try { setCards((await api.adminTarotCards()).items); }
    catch (e: any) { setErr(String(e?.message || e)); }
  }
  async function loadLearn() {
    try { setLearn(await api.adminTarotLearnStatus()); } catch { /* 표시용 — 실패 무시 */ }
  }
  useEffect(() => { load(); loadLearn(); }, []);

  async function relearnNow() {
    if (learning) return;
    if (!window.confirm(tr("admin.tarot.relearn_confirm"))) return;
    setLearning(true);
    try {
      const r = await api.adminTarotRelearn();
      setLearn(r);
      alert(tr("admin.tarot.relearn_done", { version: r.version, date: r.learned_at ? new Date(r.learned_at).toLocaleString() : "" }));
    } catch (e: any) {
      alert(e?.message || tr("admin.tarot.relearn_fail"));
      loadLearn();
    } finally {
      setLearning(false);
    }
  }

  const cur = cards.find((c) => c.code === sel) || null;

  const FILTERS: [string, string, (c: TarotAdminCard) => boolean][] = [
    ["all", tr("admin.tarot.filter_all"), () => true],
    ["edited", tr("admin.tarot.filter_edited"), (c) => c.overridden],
    ["major", tr("admin.tarot.filter_major"), (c) => c.arcana === "major"],
    ["wands", tr("admin.tarot.filter_wands"), (c) => c.suit === "wands"],
    ["cups", tr("admin.tarot.filter_cups"), (c) => c.suit === "cups"],
    ["swords", tr("admin.tarot.filter_swords"), (c) => c.suit === "swords"],
    ["pentacles", tr("admin.tarot.filter_pentacles"), (c) => c.suit === "pentacles"],
  ];
  const filterFn = FILTERS.find((f) => f[0] === filter)?.[2] || (() => true);
  const filtered = cards
    .filter(filterFn)
    .filter((c) => !q || (c.name_kr + c.name_en).toLowerCase().includes(q.toLowerCase()));

  function onSaved(u: TarotAdminCard) {
    setCards((prev) => prev.map((c) => (c.code === u.code ? u : c)));
    loadLearn();  // 수정·저장/초안복원 → 패리티 재조회 → 변경분 생기면 재학습 버튼 즉시 재활성
  }

  return (
    <div>
      {/* 재학습 바(운영자 요구) — 입력 창 상단: 수동 버튼(1일 1회) + 최종 학습일자·버전 + 패리티 상태 */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 10,
                    padding: "10px 14px", border: "1px solid var(--line)", borderRadius: 10, background: "var(--brand-50)" }}>
        {/* 활성 조건 = 변경분 존재. 수정·저장이 발생하면(onSaved→loadLearn) 같은 날에도 즉시 재활성.
            변경분이 없으면 눌러도 서버가 중복학습을 거부(409)하므로 버튼도 잠근다. */}
        <button
          onClick={relearnNow}
          disabled={learning || (!!learn && !learn.changed)}
          title={learn && !learn.changed
            ? tr("admin.tarot.relearn_title_none")
            : tr("admin.tarot.relearn_title_do")}
          style={{ padding: "7px 16px", borderRadius: 8, fontWeight: 700, fontSize: 13, cursor: learning || (learn && !learn.changed) ? "not-allowed" : "pointer",
                   border: "none", background: learning || (learn && !learn.changed) ? "var(--line)" : "var(--brand-500)", color: learning || (learn && !learn.changed) ? "var(--ink-500)" : "#fff" }}
        >
          {learning ? tr("admin.tarot.relearn_busy") : tr("admin.tarot.relearn_btn")}
        </button>
        <span style={{ fontSize: 13, color: "var(--ink-700)" }}>
          {tr("admin.tarot.last_learned")} <b>{learn?.learned_at ? new Date(learn.learned_at).toLocaleString() : tr("admin.tarot.not_yet")}</b>
          {" · "}{tr("admin.tarot.version_label")} <b>v{learn?.version ?? 0}</b>
        </span>
        {learn?.changed && (
          <span style={{ fontSize: 12, fontWeight: 700, color: "#C2554D" }}>
            {tr("admin.tarot.changed_note")}
          </span>
        )}
        {learn && !learn.changed && (
          <span style={{ fontSize: 12, color: "var(--ink-500)" }}>
            {tr("admin.tarot.unchanged_note")}
          </span>
        )}
      </div>
      <div style={{ fontSize: 13, color: "#666", marginBottom: 10 }}>
        <Trans i18nKey="admin.tarot.desc" components={{ b: <b /> }} />
      </div>
      {err && <div className="err" style={{ marginBottom: 8 }}>{err}</div>}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
        {FILTERS.map(([id, label, fn]) => (
          <button key={id} onClick={() => setFilter(id)} style={{ padding: "5px 12px", borderRadius: 999, fontSize: 13, cursor: "pointer", border: filter === id ? "none" : "1px solid var(--line)", background: filter === id ? "var(--brand-500)" : "var(--brand-50)", color: filter === id ? "#fff" : "var(--ink-600)" }}>
            {label} <span style={{ opacity: 0.6 }}>{cards.filter(fn).length}</span>
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("admin.tarot.q_ph")} style={{ marginLeft: "auto", fontSize: 13, padding: "5px 10px" }} />
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
              {c.overridden && <span title={tr("admin.tarot.edited")} style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--brand-500)", flexShrink: 0 }} />}
            </button>
          ))}
          {filtered.length === 0 && <div style={{ padding: 16, color: "#999", fontSize: 13 }}>{tr("admin.tarot.no_result")}</div>}
        </div>

        {cur ? (
          <CardEditor key={cur.code} card={cur} onSaved={onSaved} />
        ) : (
          <div style={{ color: "#999", padding: 30, textAlign: "center", border: "1px dashed var(--line)", borderRadius: 8 }}>
            {tr("admin.tarot.select_prompt")}
          </div>
        )}
      </div>
    </div>
  );
}

// -------- AI가격: 마케팅 가격 에이전트(2026-07-13) --------
// 시장조사(관리자 수동 시트) → 결정적 권장가 → 관리자 [적용] 클릭으로만 가격변경. 자동적용 없음.
function PricingAgentTab() {
  const { t: tr } = useTranslation();
  const [ov, setOv] = useState<PricingOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ competitor_name: "", menu_key: "entry_cost_compat", price_krw: "", note: "" });

  async function load() {
    try { setOv(await api.adminPricingOverview()); } catch (e: any) { setErr(String(e?.message || e)); }
  }
  useEffect(() => { load(); }, []);

  async function toggleSurvey(on: boolean) {
    try { await api.adminPatchSettings({ pricing_survey_enabled: on } as any); setMsg(tr("admin.pricing.survey_toggled", { state: on ? "ON" : "OFF" })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function runSurvey() {
    setBusy(true); setErr(null); setMsg(null);
    try { const r = await api.adminPricingSurvey(); setMsg(tr("admin.pricing.survey_done", { pending: r.pending, skipped: r.skipped })); await load(); }
    catch (e: any) { setErr(e?.message || String(e)); } finally { setBusy(false); }
  }
  async function addCompetitor() {
    const price = parseInt(form.price_krw, 10);
    if (!form.competitor_name.trim() || !(price >= 0)) { alert(tr("admin.pricing.competitor_required")); return; }
    try {
      await api.adminPricingUpsertCompetitor({ competitor_name: form.competitor_name.trim(), menu_key: form.menu_key, price_krw: price, note: form.note.trim() || undefined });
      setForm({ ...form, competitor_name: "", price_krw: "", note: "" }); await load();
    } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function apply(r: PricingRecommendation) {
    if (!confirm(tr("admin.pricing.apply_confirm", { label: r.label, cur: r.current_price.toLocaleString(), rec: r.recommended_price.toLocaleString() }))) return;
    try { await api.adminPricingApply(r.id); setMsg(tr("admin.pricing.apply_done", { label: r.label, rec: r.recommended_price.toLocaleString() })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function dismiss(r: PricingRecommendation) {
    try { await api.adminPricingDismiss(r.id); await load(); } catch (e: any) { alert(e?.message || String(e)); }
  }
  async function rollback(r: PricingRecommendation) {
    if (!confirm(tr("admin.pricing.rollback_confirm", { label: r.label, from: (r.applied_from ?? 0).toLocaleString() }))) return;
    try { await api.adminPricingRollback(r.id); setMsg(tr("admin.pricing.rollback_done", { label: r.label })); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }
  async function saveGuardrail(menu_key: string, patch: Record<string, number | boolean>) {
    try { await api.adminPricingUpdateGuardrail({ menu_key, ...patch } as any); await load(); }
    catch (e: any) { alert(e?.message || String(e)); }
  }

  if (!ov) return <div style={{ padding: 16 }}>{err ? <span style={{ color: "crimson" }}>{err}</span> : tr("admin.loading")}</div>;
  const box: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 14, marginBottom: 16 };
  const staleCount = ov.competitors.filter((c) => c.stale).length;

  return (
    <div>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}
      {msg && <div style={{ color: "seagreen", marginBottom: 8 }}>{msg}</div>}

      {/* 안전 고지 + 조사 실행 */}
      <div style={{ ...box, borderColor: "var(--gold, #b9862f)", background: "var(--gold-tint, #f6efdd)" }}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>{tr("admin.pricing.title")}</div>
        <div style={{ fontSize: 12.5, color: "#555", lineHeight: 1.7, marginBottom: 10 }}>
          <Trans i18nKey="admin.pricing.desc" components={{ b: <b /> }} />
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={ov.survey_enabled} onChange={(e) => toggleSurvey(e.target.checked)} />
            {tr("admin.pricing.auto_survey")}
          </label>
          <button onClick={runSurvey} disabled={busy} style={{ background: "var(--brand-500)", color: "#fff", border: "none", borderRadius: 6, padding: "6px 14px", cursor: "pointer" }}>
            {busy ? tr("admin.pricing.survey_busy") : tr("admin.pricing.survey_btn")}
          </button>
          {staleCount > 0 && <span style={{ color: "#c0392b", fontSize: 12 }}>{tr("admin.pricing.stale_warn", { count: staleCount })}</span>}
        </div>
      </div>

      {/* 권장 대기(승인) */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>{tr("admin.pricing.rec_title", { count: ov.pending.length })}</div>
        {ov.pending.length === 0 ? <div style={{ fontSize: 13, color: "#888" }}>{tr("admin.pricing.rec_empty")}</div> : (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "var(--bg)" }}>
              <th style={aTh}>{tr("admin.pricing.rth_item")}</th><th style={aTh}>{tr("admin.pricing.rth_current")}</th><th style={aTh}>{tr("admin.pricing.rth_comp_min")}</th><th style={aTh}>{tr("admin.pricing.rth_recommended")}</th><th style={aTh}>{tr("admin.pricing.rth_rationale")}</th><th style={aTh}>{tr("admin.pricing.rth_action")}</th>
            </tr></thead>
            <tbody>
              {ov.pending.map((r) => (
                <tr key={r.id}>
                  <td style={aTd}><b>{r.label}</b></td>
                  <td style={aTd}>{r.current_price.toLocaleString()}P</td>
                  <td style={aTd}>{r.competitor_min ? r.competitor_min.toLocaleString() + tr("admin.won") : "—"}</td>
                  <td style={aTd}><b style={{ color: "var(--brand-600)" }}>{r.recommended_price.toLocaleString()}P</b></td>
                  <td style={{ ...aTd, maxWidth: 320, fontSize: 11.5, color: "#666", whiteSpace: "normal" }}>{r.rationale}</td>
                  <td style={aTd}>
                    <button onClick={() => apply(r)} style={{ marginRight: 6, background: "var(--brand-500)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 10px", cursor: "pointer" }}>{tr("admin.pricing.apply_btn")}</button>
                    <button onClick={() => dismiss(r)} style={{ background: "none", border: "1px solid var(--line)", borderRadius: 6, padding: "4px 10px", cursor: "pointer" }}>{tr("admin.pricing.dismiss_btn")}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 경쟁사 시트 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{tr("admin.pricing.sheet_title")}</div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 10 }}>{tr("admin.pricing.sheet_desc")}</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
          <input placeholder={tr("admin.pricing.comp_ph")} value={form.competitor_name} onChange={(e) => setForm({ ...form, competitor_name: e.target.value })} style={{ width: 110 }} />
          <select value={form.menu_key} onChange={(e) => setForm({ ...form, menu_key: e.target.value })}>
            {ov.guardrails.map((g) => <option key={g.menu_key} value={g.menu_key}>{g.label}</option>)}
          </select>
          <input placeholder={tr("admin.pricing.price_ph")} type="number" value={form.price_krw} onChange={(e) => setForm({ ...form, price_krw: e.target.value })} style={{ width: 90 }} />
          <input placeholder={tr("admin.pricing.note_ph")} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} style={{ width: 130 }} />
          <button onClick={addCompetitor} style={{ background: "var(--brand-500)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 12px", cursor: "pointer" }}>{tr("admin.pricing.add")}</button>
        </div>
        {ov.competitors.length > 0 && (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "var(--bg)" }}><th style={aTh}>{tr("admin.pricing.cth_competitor")}</th><th style={aTh}>{tr("admin.pricing.cth_item")}</th><th style={aTh}>{tr("admin.pricing.cth_price")}</th><th style={aTh}>{tr("admin.pricing.cth_verified")}</th><th style={aTh}>{tr("admin.pricing.cth_note")}</th><th style={aTh}></th></tr></thead>
            <tbody>
              {ov.competitors.map((c) => (
                <tr key={c.id}>
                  <td style={aTd}>{c.competitor_name}</td>
                  <td style={aTd}>{c.label}</td>
                  <td style={aTd}>{c.price_krw.toLocaleString()}{tr("admin.won")}</td>
                  <td style={{ ...aTd, color: c.stale ? "#c0392b" : undefined }}>{c.verified_at ? fmtKSTDate(c.verified_at) : "—"}{c.stale ? " ⚠️" : ""}</td>
                  <td style={aTd}>{c.note || "—"}</td>
                  <td style={aTd}><button onClick={() => api.adminPricingDeleteCompetitor(c.id).then(load)} style={{ background: "none", border: "none", cursor: "pointer", color: "#c0392b" }}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 가드레일 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{tr("admin.pricing.guardrail_title")}</div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 10 }}>{tr("admin.pricing.guardrail_desc")}</div>
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
          <thead><tr style={{ background: "var(--bg)" }}><th style={aTh}>{tr("admin.pricing.gth_item")}</th><th style={aTh}>{tr("admin.pricing.gth_undercut")}</th><th style={aTh}>{tr("admin.pricing.gth_maxchange")}</th><th style={aTh}>{tr("admin.pricing.gth_floor")}</th><th style={aTh}>{tr("admin.pricing.gth_ceiling")}</th><th style={aTh}>{tr("admin.pricing.gth_enabled")}</th></tr></thead>
          <tbody>
            {ov.guardrails.map((g) => (
              <tr key={g.menu_key}>
                <td style={aTd}>{g.label}</td>
                <td style={aTd}><input type="number" defaultValue={g.undercut_pct} style={{ width: 52 }} onBlur={(e) => { const v = parseInt(e.target.value, 10); if (v !== g.undercut_pct) saveGuardrail(g.menu_key, { undercut_pct: v }); }} /></td>
                <td style={aTd}><input type="number" defaultValue={g.max_change_pct} style={{ width: 52 }} onBlur={(e) => { const v = parseInt(e.target.value, 10); if (v !== g.max_change_pct) saveGuardrail(g.menu_key, { max_change_pct: v }); }} /></td>
                <td style={aTd}><input type="number" defaultValue={g.floor_p} style={{ width: 74 }} onBlur={(e) => { const v = parseInt(e.target.value, 10); if (v !== g.floor_p) saveGuardrail(g.menu_key, { floor_p: v }); }} /></td>
                <td style={aTd}><input type="number" defaultValue={g.ceiling_p} style={{ width: 84 }} onBlur={(e) => { const v = parseInt(e.target.value, 10); if (v !== g.ceiling_p) saveGuardrail(g.menu_key, { ceiling_p: v }); }} /></td>
                <td style={aTd}><input type="checkbox" checked={g.enabled} onChange={(e) => saveGuardrail(g.menu_key, { enabled: e.target.checked })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 3소스 diff 안내 */}
      {ov.sync_diff.length > 0 && (
        <div style={{ ...box, borderColor: "#e0b000", background: "#fffbe6" }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{tr("admin.pricing.sync_title", { count: ov.sync_diff.length })}</div>
          <div style={{ fontSize: 12, color: "#775500", marginBottom: 8 }}>
            <Trans i18nKey="admin.pricing.sync_desc" components={{ b: <b /> }} />
          </div>
          <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "var(--bg)" }}><th style={aTh}>{tr("admin.pricing.sth_item")}</th><th style={aTh}>{tr("admin.pricing.sth_live")}</th><th style={aTh}>{tr("admin.pricing.sth_code")}</th></tr></thead>
            <tbody>{ov.sync_diff.map((d) => (
              <tr key={d.menu_key}><td style={aTd}>{d.label}</td><td style={aTd}><b>{d.live.toLocaleString()}</b></td><td style={aTd}>{d.code_default.toLocaleString()}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {/* 변경 이력 */}
      <div style={box}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>{tr("admin.pricing.history_title")}</div>
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
          <thead><tr style={{ background: "var(--bg)" }}><th style={aTh}>{tr("admin.pricing.hth_time")}</th><th style={aTh}>{tr("admin.pricing.hth_item")}</th><th style={aTh}>{tr("admin.pricing.hth_change")}</th><th style={aTh}>{tr("admin.pricing.hth_status")}</th><th style={aTh}>{tr("admin.pricing.hth_by")}</th><th style={aTh}></th></tr></thead>
          <tbody>
            {ov.history.filter((r) => r.status !== "pending").slice(0, 30).map((r) => (
              <tr key={r.id}>
                <td style={aTd}>{r.decided_at ? fmtKSTShort(r.decided_at) : (r.created_at ? fmtKSTShort(r.created_at) : "—")}</td>
                <td style={aTd}>{r.label}</td>
                <td style={aTd}>{r.current_price.toLocaleString()} → {r.recommended_price.toLocaleString()}</td>
                <td style={aTd}>{r.status === "applied" ? tr("admin.pricing.st_applied") : r.status === "dismissed" ? tr("admin.pricing.st_dismissed") : tr("admin.pricing.st_nochange")}</td>
                <td style={aTd}>{r.decided_by || "—"}</td>
                <td style={aTd}>{r.status === "applied" && r.applied_from != null && <button onClick={() => rollback(r)} style={{ background: "none", border: "1px solid var(--line)", borderRadius: 6, padding: "2px 8px", cursor: "pointer", fontSize: 11 }}>{tr("admin.pricing.rollback_btn")}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
