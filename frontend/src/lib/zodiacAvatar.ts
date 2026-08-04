/** 12띠 3D 캐릭터 아바타(public/zodiac/{띠}_{단계}.jpg) 매핑.
 * 띠는 연도 나눗셈이 아니라 백엔드가 계산한 명식의 년지(年支)로 정확히 결정한다. */

export const BRANCH_ZODIAC: Record<string, string> = {
  子: "쥐", 丑: "소", 寅: "호랑이", 卯: "토끼", 辰: "용", 巳: "뱀",
  午: "말", 未: "양", 申: "원숭이", 酉: "닭", 戌: "개", 亥: "돼지",
};

export const ZODIACS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"];

/** 생년월일 → 생애 단계(영상 파이프라인과 동일한 5단계). 장식용 근사치. */
export function lifeStage(birthDate?: string | null): string {
  const y = birthDate ? parseInt(birthDate.slice(0, 4), 10) : NaN;
  if (!Number.isFinite(y)) return "청년";
  const age = new Date().getFullYear() - y;
  if (age < 8) return "초년";
  if (age < 20) return "유년";
  if (age < 40) return "청년";
  if (age < 60) return "장년";
  return "노년";
}

/** 년지 + 생년월일 → 아바타 정보. 년지가 없으면 null(표시 안 함). */
export function zodiacAvatar(yearBranch?: string | null, birthDate?: string | null): { zodiac: string; src: string } | null {
  const zodiac = yearBranch ? BRANCH_ZODIAC[yearBranch] : undefined;
  if (!zodiac) return null;
  return { zodiac, src: `/zodiac/${zodiac}_${lifeStage(birthDate)}.jpg` };
}
