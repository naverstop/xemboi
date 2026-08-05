/** 회원 호칭(○○님 표기) 공용 헬퍼.
 *
 *  ⚠️ 운영자 결정(2026-07) — 호칭은 반드시 **이메일 아이디**(@ 앞, 예: orion0321)를 우선한다.
 *     닉네임을 우선하면 원치 않는 값('연수' 등)이 상담·PDF에 노출되는 사고가 있었음.
 *     다른 에이전트/작업자는 이 순서를 닉네임 우선으로 되돌리지 말 것.
 *     (사이드바 계정 라벨 등 '호칭'이 아닌 표시는 이 헬퍼 대상 아님)
 */
import i18n from "../i18n";

export function displayName(
  me: { email?: string | null; nickname?: string | null } | null | undefined,
  fallback?: string,   // 미지정 시 로케일 폴백(libx.dn_customer — ko '고객')
): string {
  const emailId = me?.email ? me.email.split("@")[0] : "";
  return emailId || me?.nickname?.trim() || fallback || i18n.t("libx.dn_customer");
}
