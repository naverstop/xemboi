/**
 * 프리미엄 메뉴(궁합/택일/타로 등) 입장료 공통 유틸.
 *
 * - 입장료/할인/무료여부는 모두 서버(`/api/auth/me`)가 내려준 값을 사용한다(하드코딩 없음).
 *   · me.premium_entry_costs[menu] : 할인 반영된 메뉴별 입장료
 *   · me.premium_entry_free        : 이 사용자(관리자/멤버십) 입장 무료 여부
 * - 사주 상담(chat)은 이 정책 대상이 아니다.
 * - 문구/메뉴명은 i18n(pay.* / nav.*) 카탈로그 사용 → ko/vi 자동 전환.
 */
import type { MeResp } from "../api";
import i18n from "../i18n";
import { fmtNum } from "./money";

export type EntryMenu = "compat" | "taekil" | "jakmyeong" | "gaemyeong" | "aho" | "tarot";

/** 메뉴 표시명 — nav 카탈로그(로케일) 재사용. 언어 전환 시 자동 반영. */
export function entryLabel(menu: EntryMenu): string {
  return i18n.t(`nav.${menu}`);
}

/** 메뉴별 기본 입장료(서버 DEFAULTS와 동일) — 비로그인 등 me 부재 시 표시용 폴백(VND). */
const ENTRY_FALLBACK: Record<EntryMenu, number> = {
  compat: 99000,
  taekil: 99000,
  jakmyeong: 99000, // VN 제외 메뉴(안전값)
  gaemyeong: 99000,
  aho: 99000,
  tarot: 49000,
};

/** 이 사용자가 실제로 낼 입장료(P). 무료 대상이면 0. 서버값 우선, 폴백은 메뉴별 기본값. */
export function entryCost(me: MeResp | null | undefined, menu: EntryMenu): number {
  if (me && me.premium_entry_free) return 0;
  return me?.premium_entry_costs?.[menu] ?? ENTRY_FALLBACK[menu];
}

/** 관리자/멤버십 무료 여부. */
export function entryFree(me: MeResp | null | undefined): boolean {
  return !!(me && me.premium_entry_free);
}

/**
 * 생성(입장) 직전 확인. 진행하면 true.
 * - 비로그인: 백엔드가 미리보기로 처리 → 확인 생략(true).
 * - 무료(관리자/멤버십): 즉시 true.
 * - 잔액 부족: 안내 후 false(결제 유도).
 * - 그 외: 차감 확인 다이얼로그.
 */
export function confirmEntry(me: MeResp | null | undefined, menu: EntryMenu): boolean {
  if (!me) return true; // 비로그인 — 미리보기
  if (entryFree(me)) return true; // 관리자/멤버십 무료
  const cost = entryCost(me, menu);
  if (cost <= 0) return true;
  const label = entryLabel(menu);
  const bal = me.balance ?? 0;
  if (bal < cost) {
    alert(i18n.t("pay.need_charge_alert", { label, cost: fmtNum(cost), bal: fmtNum(bal) }));
    return false;
  }
  // 추가 질문 단가는 관리자 설정값(me.credit_cost_*)을 그대로 안내 — 하드코딩 금지.
  const basic = me.credit_cost_basic ?? 19000;
  const deep = me.credit_cost_deep ?? 29000;
  return window.confirm(
    i18n.t("pay.confirm_entry", { label, cost: fmtNum(cost), basic: fmtNum(basic), deep: fmtNum(deep) }),
  );
}

/** 버튼 보조 라벨(예: " · 입장 10,000P"). 무료/0원이면 빈 문자열. */
export function entrySuffix(me: MeResp | null | undefined, menu: EntryMenu): string {
  const cost = entryCost(me, menu);
  if (cost <= 0) return "";
  return i18n.t("pay.entry_suffix", { cost: fmtNum(cost) });
}
