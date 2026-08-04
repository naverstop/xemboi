/** 상담 입장/상태 안내용 음성(Web SpeechSynthesis) — 무료·서버 불필요.
 *
 * ko-KR 여성 보이스 우선 선택('아름다운 여자 목소리' 요구). 브라우저 자동재생 정책상 사용자 제스처
 * (상담 신청/수락 클릭) 시점에 primeTTS()로 보이스 목록을 프라임해야 이후 자동 발화가 된다.
 * iOS 등 ko 여성 보이스 미탑재 기기는 기본 보이스로 폴백(무음이 아니라 가용 보이스 사용).
 */
function supported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
}

export function primeTTS(): void {
  if (!supported()) return;
  try {
    window.speechSynthesis.getVoices();       // 보이스 목록 프라임(첫 발화 지연/무음 방지)
    // onvoiceschanged 로 늦게 로드되는 브라우저 대비 — 접근만 해두면 이후 speak 시 채워짐
    window.speechSynthesis.onvoiceschanged = () => { /* noop: 목록 갱신 트리거 */ };
  } catch { /* 미지원 */ }
}

function pickKoFemaleVoice(): SpeechSynthesisVoice | null {
  try {
    const vs = window.speechSynthesis.getVoices() || [];
    const ko = vs.filter((v) => /^ko(-|_|$)/i.test(v.lang) || /korean|한국/i.test(v.name));
    if (!ko.length) return null;
    // 알려진 한국어 여성 보이스 우선(Microsoft SunHi/Heami, Google 한국의, Apple Yuna 등)
    const female = ko.find((v) => /sunhi|heami|yuna|female|여성|여자|google 한국의/i.test(v.name));
    return female || ko[0];
  } catch {
    return null;
  }
}

export function speak(text: string): void {
  if (!supported() || !text) return;
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    u.rate = 1.0;
    u.pitch = 1.12;   // 살짝 높여 부드러운 여성 톤
    u.volume = 1;
    const v = pickKoFemaleVoice();
    if (v) u.voice = v;
    window.speechSynthesis.cancel();  // 이전 발화 중단(중첩 방지)
    window.speechSynthesis.speak(u);
  } catch { /* 미지원 — 무음 폴백 */ }
}
