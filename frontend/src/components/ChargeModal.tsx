/** 전역 포인트 충전 모달 + Context.
 *
 * 어느 화면에서든 useCharge().openCharge()로 호출 → 현재 화면 위에 모달이 떠서 충전.
 * mock 모드는 즉시 적립(redirect 없음) → 작성 중 입력값·상태 100% 보존, 잔액만 갱신.
 * 실 결제 키 전환 시에만 결제창 리디렉트(그 경우 successUrl로 복귀).
 */
import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { api, useMe, setCachedMe } from "../api";
import { entryLabel, entryCost, entryFree, type EntryMenu } from "../lib/entryFee";
import { fmtMoney, fmtNum } from "../lib/money";

declare global {
  interface Window { TossPayments?: any }
}

type Pkg = { amount: number; credits: number; label: string;
  supply_amount?: number; vat_amount?: number; total_amount?: number; vat_pct?: number };
type Ctx = { openCharge: (reason?: string) => void };

const ChargeCtx = createContext<Ctx>({ openCharge: () => {} });
export const useCharge = () => useContext(ChargeCtx);

/** 입장료 게이트(모델 C) — 제출 직전 호출. 잔액 부족 시 충전 모달(상태보존) 띄우고 false.
 *  충분하면 차감 확인 후 진행. 비로그인/무료대상은 통과. */
export function useEnsureEntry() {
  const me = useMe();
  const { t } = useTranslation();
  const { openCharge } = useCharge();
  return useCallback((menu: EntryMenu): boolean => {
    if (!me) return true;            // 비로그인 → 백엔드 미리보기
    if (entryFree(me)) return true;  // 관리자/멤버십
    const cost = entryCost(me, menu);
    if (cost <= 0) return true;
    const label = entryLabel(menu);
    const bal = me.balance ?? 0;
    if (bal < cost) {
      openCharge(t("pay.need_charge", { label, cost: fmtNum(cost) }));
      return false;
    }
    const basic = me.credit_cost_basic ?? 19000;
    const deep = me.credit_cost_deep ?? 29000;
    return window.confirm(
      t("pay.confirm_entry", { label, cost: fmtNum(cost), basic: fmtNum(basic), deep: fmtNum(deep) }),
    );
  }, [me, openCharge, t]);
}

/** 입장 안내 배너 — 프리미엄 메뉴 상단. 입장료를 입장 시점에 인지시키고, 잔액 부족이면 '입력 전' 충전 유도. */
export function EntryFeeNotice({ menu }: { menu: EntryMenu }) {
  const me = useMe();
  const { t } = useTranslation();
  const { openCharge } = useCharge();
  const cost = entryCost(me, menu);
  if (cost <= 0) return null;  // 관리자/멤버십 무료 → 숨김
  const label = entryLabel(menu);
  const bal = me?.balance ?? 0;
  const short = !!me && bal < cost;
  return (
    <div className={`entry-fee-notice${short ? " short" : ""}`}>
      <span className="efn-main">💎 {t("pay.entry_fee", { label })} <b>{fmtNum(cost)}{t("pay.pt")}</b> <em>{t("pay.entry_extra")}</em></span>
      {me && (short ? (
        <button className="efn-charge" onClick={() => openCharge(t("pay.need_charge", { label, cost: fmtNum(cost) }))}>
          {t("pay.bal_charge", { bal: fmtNum(bal) })}
        </button>
      ) : (
        <span className="efn-bal">{t("pay.bal_only", { bal: fmtNum(bal) })}</span>
      ))}
    </div>
  );
}

export function ChargeProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string | undefined>(undefined);
  const openCharge = useCallback((r?: string) => { setReason(r); setOpen(true); }, []);
  return (
    <ChargeCtx.Provider value={{ openCharge }}>
      {children}
      {open && <ChargeModal reason={reason} onClose={() => setOpen(false)} />}
    </ChargeCtx.Provider>
  );
}

function ChargeModal({ reason, onClose }: { reason?: string; onClose: () => void }) {
  const me = useMe();
  const { t } = useTranslation();
  const [pkgs, setPkgs] = useState<Pkg[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.paymentPackages().then((r) => setPkgs(r.items)).catch(() => {}); }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  async function buy(p: Pkg) {
    if (!me) return;
    setBusy(p.amount); setErr(null); setDone(null);
    try {
      const order = await api.paymentCreateOrder(p.amount);
      const isDummy = String(order.client_key || "").includes("DUMMY");
      if (!isDummy && window.TossPayments) {
        const toss = window.TossPayments(order.client_key);
        await toss.requestPayment("카드", {
          amount: order.amount, orderId: order.order_id, orderName: order.order_name,
          customerEmail: order.customer_email, customerName: order.customer_name,
          successUrl: order.success_url, failUrl: order.fail_url,
        });
        return; // 실 결제는 리디렉트 → 아래로 안 옴
      }
      const fakeKey = `mock_pk_${order.order_id}`;
      const c = await api.paymentConfirm(fakeKey, order.order_id, order.amount);
      const newMe = await api.me(); setCachedMe(newMe);
      setDone(`+${fmtNum(c.credits_granted)}${t("pay.pt")} · ${t("pay.bal_only", { bal: fmtNum(c.balance) })}`);
    } catch (e: any) {
      setErr(e?.message || t("pay.fail"));
    } finally { setBusy(null); }
  }

  const bal = me?.balance ?? 0;
  const hasVat = pkgs.some((p) => (p.vat_amount ?? 0) > 0);
  return (
    <div className="charge-ov" onClick={onClose}>
      <div className="charge-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={t("pay.aria_charge")}>
        <div className="charge-head">
          <div>
            <div className="charge-title">{t("pay.modal_title")}</div>
            <div className="charge-bal">{t("pay.cur_balance")} <b>{fmtNum(bal)}{t("pay.pt")}</b></div>
          </div>
          <button className="charge-x" onClick={onClose} aria-label={t("pay.close")}>✕</button>
        </div>
        {reason && !done && <div className="charge-reason">{reason}</div>}
        {done ? (
          <div className="charge-done">
            <div className="charge-done-msg">✅ {done}</div>
            <button className="charge-cont" onClick={onClose}>{t("pay.done_continue")}</button>
          </div>
        ) : (
          <>
            {pkgs[0] && (
              <button className="charge-oneclick" disabled={busy !== null} onClick={() => buy(pkgs[0])}>
                {busy === pkgs[0].amount
                  ? t("pay.processing")
                  : t("pay.oneclick", { credits: fmtNum(pkgs[0].credits), pay: fmtMoney(pkgs[0].total_amount ?? pkgs[0].amount) })}
              </button>
            )}
            <div className="charge-grid-label">{t("pay.other_amount")}</div>
            <div className="charge-grid">
              {pkgs.map((p) => (
                <button key={p.amount} className="charge-pkg" disabled={busy !== null} onClick={() => buy(p)}>
                  <span className="charge-pkg-cr">{fmtNum(p.credits)}{t("pay.pt")}</span>
                  <span className="charge-pkg-pay">{t("pay.pay_label", { pay: fmtMoney(p.total_amount ?? p.amount) })}</span>
                  {(p.vat_amount ?? 0) > 0 && (
                    <span className="charge-pkg-vat">{t("pay.vat_incl", { vat: fmtMoney(p.vat_amount ?? 0) })}</span>
                  )}
                  <span className="charge-pkg-btn">{busy === p.amount ? t("pay.processing") : t("pay.charge_btn")}</span>
                </button>
              ))}
              {pkgs.length === 0 && <div className="charge-loading">{t("pay.loading_pkgs")}</div>}
            </div>
            {err && <div className="charge-err">{err}</div>}
            <div className="charge-note">{hasVat ? t("pay.note_vat") : t("pay.note_novat")}</div>
          </>
        )}
      </div>
    </div>
  );
}
