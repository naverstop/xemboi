/** 시각 미입력 정책 — 전 메뉴(상담·궁합·택일·작명) 공통.
 *
 *  운영자 결정(2026-06-22):
 *   - 시각을 비워두면 자동으로 00:30(자시)로 진행 → 입력 흐름이 매끄럽게 넘어간다.
 *   - 단, 사용자가 '시 모름'을 명시하면 시주를 제외(null)하고 3기둥으로 분석한다.
 *  (백엔드는 birth_time=null 을 "시주 미상(時不明)"으로 정상 처리한다 — pillars.py 참조.)
 */
export const DEFAULT_BIRTH_TIME = "00:30";

/** UI의 (birth_time, unknown_time) → 백엔드로 보낼 birth_time 값.
 *  - unknown_time=true  → null(시주 제외)
 *  - 그 외 빈 값         → DEFAULT_BIRTH_TIME(00:30)
 *  - 값이 있으면         → 그대로
 */
export function resolveBirthTime(
  birthTime: string | null | undefined,
  unknownTime?: boolean,
): string | null {
  if (unknownTime) return null;
  const t = (birthTime ?? "").trim();
  return t || DEFAULT_BIRTH_TIME;
}
