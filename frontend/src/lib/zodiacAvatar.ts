/** 12띠 3D 캐릭터 아바타(public/zodiac/{띠}_{단계}.jpg) 매핑.
 * 띠는 연도 나눗셈이 아니라 백엔드가 계산한 명식의 년지(年支)로 정확히 결정한다.
 * VN 12지는 丑=물소(水牛)·卯=고양이(貓)로 한국(소·토끼)과 갈리며, 전용 FLUX 아트를 사용한다. */
import i18n from "../i18n";

const isVi = () => (i18n.language || "ko").startsWith("vi");

// 지지 → 이미지 파일명 키. 한국=소·토끼, VN=물소·고양이(나머지 동일).
const BRANCH_ZODIAC_KO: Record<string, string> = {
  子: "쥐", 丑: "소", 寅: "호랑이", 卯: "토끼", 辰: "용", 巳: "뱀",
  午: "말", 未: "양", 申: "원숭이", 酉: "닭", 戌: "개", 亥: "돼지",
};
const BRANCH_ZODIAC_VI: Record<string, string> = { ...BRANCH_ZODIAC_KO, 丑: "물소", 卯: "고양이" };

/** 지지 → 현재 로케일 이미지 키(VN이면 물소·고양이). */
export function branchZodiacKey(yearBranch?: string | null): string | undefined {
  if (!yearBranch) return undefined;
  return (isVi() ? BRANCH_ZODIAC_VI : BRANCH_ZODIAC_KO)[yearBranch];
}
// 하위호환 export(한국 기준 맵) — 기존 참조 유지.
export const BRANCH_ZODIAC = BRANCH_ZODIAC_KO;

const ZODIACS_KO = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"];
const ZODIACS_VI = ["쥐", "물소", "호랑이", "고양이", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"];
/** 랜딩 띠 스트립용 12 이미지 키(로케일 인지). */
export function zodiacStripKeys(): string[] {
  return isVi() ? ZODIACS_VI : ZODIACS_KO;
}
// 하위호환 export.
export const ZODIACS = ZODIACS_KO;

// 표시 라벨(이미지 키 → 로케일 표시명). VN 키(물소·고양이)·KO 키(소·토끼) 모두 포함.
const ZODIAC_LABEL: Record<string, { ko: string; vi: string }> = {
  쥐: { ko: "쥐", vi: "Chuột" },
  소: { ko: "소", vi: "Trâu" }, 물소: { ko: "물소", vi: "Trâu" },   // 丑
  호랑이: { ko: "호랑이", vi: "Hổ" },
  토끼: { ko: "토끼", vi: "Mèo" }, 고양이: { ko: "고양이", vi: "Mèo" }, // 卯
  용: { ko: "용", vi: "Rồng" },
  뱀: { ko: "뱀", vi: "Rắn" },
  말: { ko: "말", vi: "Ngựa" },
  양: { ko: "양", vi: "Dê" },
  원숭이: { ko: "원숭이", vi: "Khỉ" },
  닭: { ko: "닭", vi: "Gà" },
  개: { ko: "개", vi: "Chó" },
  돼지: { ko: "돼지", vi: "Lợn" },
};

/** 이미지 키 → 현재 로케일 표시명(VN이면 Trâu/Mèo 등). */
export function zodiacLabel(imageKey?: string | null): string {
  if (!imageKey) return "";
  return ZODIAC_LABEL[imageKey]?.[isVi() ? "vi" : "ko"] ?? imageKey;
}

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

/** 년지 + 생년월일 → 아바타 정보(로케일 인지 이미지). 년지가 없으면 null. */
export function zodiacAvatar(yearBranch?: string | null, birthDate?: string | null): { zodiac: string; src: string } | null {
  const zodiac = branchZodiacKey(yearBranch);
  if (!zodiac) return null;
  return { zodiac, src: `/zodiac/${zodiac}_${lifeStage(birthDate)}.jpg` };
}
