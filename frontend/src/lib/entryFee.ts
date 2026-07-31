/**
 * 프리미엄 5개 메뉴(궁합/택일/작명/개명/아호) 입장료 공통 유틸.
 *
 * - 입장료/할인/무료여부는 모두 서버(`/api/auth/me`)가 내려준 값을 사용한다(하드코딩 없음).
 *   · me.premium_entry_costs[menu] : 할인 반영된 메뉴별 입장료
 *   · me.premium_entry_free        : 이 사용자(관리자/멤버십) 입장 무료 여부
 * - 사주 상담(chat)은 이 정책 대상이 아니다.
 */
import type { MeResp } from "../api";

export type EntryMenu = "compat" | "taekil" | "jakmyeong" | "gaemyeong" | "aho" | "tarot";

export const ENTRY_MENU_LABEL: Record<EntryMenu, string> = {
  compat: "궁합",
  taekil: "택일",
  jakmyeong: "작명",
  gaemyeong: "개명",
  aho: "아호",
  tarot: "타로",
};

/** 메뉴별 기본 입장료(서버 DEFAULTS와 동일) — 비로그인 등 me 부재 시 표시용 폴백. */
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
  const label = ENTRY_MENU_LABEL[menu];
  const bal = me.balance ?? 0;
  if (bal < cost) {
    alert(
      `${label} 입장에는 ${cost.toLocaleString()}P가 필요합니다.\n` +
        `현재 잔액 ${bal.toLocaleString()}P — 포인트를 충전한 뒤 다시 시도해 주세요.`,
    );
    return false;
  }
  // 추가 질문 단가는 관리자 설정값(me.credit_cost_*)을 그대로 안내 — 하드코딩 금지.
  const basic = me.credit_cost_basic ?? 19000;
  const deep = me.credit_cost_deep ?? 29000;
  return window.confirm(
    `${label}은(는) 입장 시 ${cost.toLocaleString()}P가 차감됩니다.\n` +
      `(추가 질문은 별도: 기본 ${basic.toLocaleString()}P · 심화 ${deep.toLocaleString()}P)\n\n계속하시겠습니까?`,
  );
}

/** 버튼 보조 라벨(예: " · 입장 10,000P"). 무료/0원이면 빈 문자열. */
export function entrySuffix(me: MeResp | null | undefined, menu: EntryMenu): string {
  const cost = entryCost(me, menu);
  if (cost <= 0) return "";
  return ` · 입장 ${cost.toLocaleString()}P`;
}
