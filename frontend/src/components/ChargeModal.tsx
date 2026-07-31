/** 전역 포인트 충전 모달 + Context.
 *
 * 어느 화면에서든 useCharge().openCharge()로 호출 → 현재 화면 위에 모달이 떠서 충전.
 * mock 모드는 즉시 적립(redirect 없음) → 작성 중 입력값·상태 100% 보존, 잔액만 갱신.
 * 실 토스 키 전환 시에만 결제창 리디렉트(그 경우 successUrl로 복귀).
 */
import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from "react";
import { api, useMe, setCachedMe } from "../api";
import { ENTRY_MENU_LABEL, entryCost, entryFree, type EntryMenu } from "../lib/entryFee";

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
  const { openCharge } = useCharge();
  return useCallback((menu: EntryMenu): boolean => {
    if (!me) return true;            // 비로그인 → 백엔드 미리보기
    if (entryFree(me)) return true;  // 관리자/멤버십
    const cost = entryCost(me, menu);
    if (cost <= 0) return true;
    const label = ENTRY_MENU_LABEL[menu];
    const bal = me.balance ?? 0;
    if (bal < cost) {
      openCharge(`${label} 입장에는 ${cost.toLocaleString()}P가 필요해요. 충전하면 작성 내용 그대로 바로 이어집니다.`);
      return false;
    }
    const basic = me.credit_cost_basic ?? 1000;
    const deep = me.credit_cost_deep ?? 3000;
    return window.confirm(
      `${label}은(는) 입장 시 ${cost.toLocaleString()}P가 차감됩니다.\n` +
        `(추가 질문은 별도: 기본 ${basic.toLocaleString()}P · 심화 ${deep.toLocaleString()}P)\n\n계속하시겠습니까?`,
    );
  }, [me, openCharge]);
}

/** 입장 안내 배너 — 프리미엄 메뉴 상단. 입장료를 입장 시점에 인지시키고, 잔액 부족이면 '입력 전' 충전 유도. */
export function EntryFeeNotice({ menu }: { menu: EntryMenu }) {
  const me = useMe();
  const { openCharge } = useCharge();
  const cost = entryCost(me, menu);
  if (cost <= 0) return null;  // 관리자/멤버십 무료 → 숨김
  const label = ENTRY_MENU_LABEL[menu];
  const bal = me?.balance ?? 0;
  const short = !!me && bal < cost;
  return (
    <div className={`entry-fee-notice${short ? " short" : ""}`}>
      <span className="efn-main">💎 {label} 입장료 <b>{cost.toLocaleString()}P</b> <em>· 추가 질문은 별도 차감</em></span>
      {me && (short ? (
        <button className="efn-charge" onClick={() => openCharge(`${label} 입장에는 ${cost.toLocaleString()}P가 필요해요. 충전 후 그대로 이어집니다.`)}>
          잔액 {bal.toLocaleString()}P · 충전하기
        </button>
      ) : (
        <span className="efn-bal">잔액 {bal.toLocaleString()}P</span>
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
      setDone(`+${c.credits_granted.toLocaleString()}P 충전 완료 · 잔액 ${c.balance.toLocaleString()}P`);
    } catch (e: any) {
      setErr(e?.message || "충전에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally { setBusy(null); }
  }

  const bal = me?.balance ?? 0;
  return (
    <div className="charge-ov" onClick={onClose}>
      <div className="charge-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="포인트 충전">
        <div className="charge-head">
          <div>
            <div className="charge-title">⚡ 포인트 충전</div>
            <div className="charge-bal">현재 잔액 <b>{bal.toLocaleString()}P</b></div>
          </div>
          <button className="charge-x" onClick={onClose} aria-label="닫기">✕</button>
        </div>
        {reason && !done && <div className="charge-reason">{reason}</div>}
        {done ? (
          <div className="charge-done">
            <div className="charge-done-msg">✅ {done}</div>
            <button className="charge-cont" onClick={onClose}>계속하기</button>
          </div>
        ) : (
          <>
            {pkgs[0] && (
              <button className="charge-oneclick" disabled={busy !== null} onClick={() => buy(pkgs[0])}>
                {busy === pkgs[0].amount
                  ? "처리중…"
                  : `⚡ 원클릭 충전 · ${pkgs[0].credits.toLocaleString()}P (결제 ${(pkgs[0].total_amount ?? pkgs[0].amount).toLocaleString()}원)`}
              </button>
            )}
            <div className="charge-grid-label">다른 금액으로 충전</div>
            <div className="charge-grid">
              {pkgs.map((p) => (
                <button key={p.amount} className="charge-pkg" disabled={busy !== null} onClick={() => buy(p)}>
                  <span className="charge-pkg-cr">{p.credits.toLocaleString()}P</span>
                  <span className="charge-pkg-pay">결제 {(p.total_amount ?? p.amount).toLocaleString()}원</span>
                  <span className="charge-pkg-vat">부가세 {(p.vat_amount ?? 0).toLocaleString()}원 포함</span>
                  <span className="charge-pkg-btn">{busy === p.amount ? "처리중…" : "충전"}</span>
                </button>
              ))}
              {pkgs.length === 0 && <div className="charge-loading">충전 상품을 불러오는 중…</div>}
            </div>
            {err && <div className="charge-err">{err}</div>}
            <div className="charge-note">결제금액은 <b>부가세 10% 포함</b>이에요(예: 10,000P → 11,000원). 결제창 이동 없이 바로 충전되고 <b>작성 중인 내용은 그대로 유지</b>됩니다.</div>
          </>
        )}
      </div>
    </div>
  );
}
