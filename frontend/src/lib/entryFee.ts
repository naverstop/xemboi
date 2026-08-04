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

export type EntryMenu = "compat" | "taekil" | "jakmyeong" | "gaemyeong" | "aho" | "tarot" | "sinnyeon";

/** 메뉴 표시명 — nav 카탈로그(로케일) 재사용. 언어 전환 시 자동 반영. */
export function entryLabel(menu: EntryMenu): string {
  return i18n.t(`nav.${menu}`);
}

export const ENTRY_MENU_LABEL: Record<EntryMenu, string> = {
  compat: "궁합",
  taekil: "택일",
  jakmyeong: "작명",
  gaemyeong: "개명",
  aho: "아호",
  tarot: "타로",
  sinnyeon: "신년운세",
};

/** 입장 시 '무엇을 전부 볼 수 있는지' — 입장 확인 모달의 오해 예방 안내 문구용. */
export const ENTRY_MENU_DESC: Record<EntryMenu, string> = {
  compat: "두 사람의 궁합 결과",
  taekil: "선택한 기간의 길일 추천",
  jakmyeong: "사주에 맞는 이름 후보",
  gaemyeong: "현재 이름 진단·개선안",
  aho: "어울리는 호(號) 후보",
  tarot: "뽑은 카드의 해석",
  sinnyeon: "올해 총운·월별 흐름",
};

/** 메뉴별 기본 입장료(서버 DEFAULTS와 동일) — 비로그인 등 me 부재 시 표시용 폴백(VND). */
const ENTRY_FALLBACK: Record<EntryMenu, number> = {
  compat: 99000,
  taekil: 99000,
  jakmyeong: 99000, // VN 제외 메뉴(안전값)
  gaemyeong: 99000,
  aho: 99000,
  tarot: 49000,
  sinnyeon: 99000, // VN 제외 메뉴(안전값)
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

// (구 confirmEntry: window.confirm 기반 — 커스텀 입장 모달로 대체되어 제거. ChargeModal.useEnsureEntry 사용)

/** 버튼 보조 라벨(예: " · 입장 10,000P"). 무료/0원이면 빈 문자열. */
export function entrySuffix(me: MeResp | null | undefined, menu: EntryMenu): string {
  const cost = entryCost(me, menu);
  if (cost <= 0) return "";
  return i18n.t("pay.entry_suffix", { cost: fmtNum(cost) });
}
