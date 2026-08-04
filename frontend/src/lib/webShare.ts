/** OS 네이티브 파일 공유(Web Share files)를 쓸지 판별 — **모바일(Android/iOS)에서만** true.
 *
 *  ⚠️ 기능 감지(navigator.canShare)만으로 분기하면 안 됨: Windows/macOS 크롬·엣지도
 *  파일 공유를 '지원한다'고 답하지만, 열리는 건 OS 공유창(Windows 공유 시트)이고
 *  대상 로딩에서 멈추거나 카카오톡 등 유용한 대상이 없어 "공유가 안 된다"로 보임(운영자 리포트 2026-07).
 *  데스크톱은 항상 자체 공유 메뉴(카카오톡 링크카드·메일·링크복사·저장)를 쓸 것.
 */
export function canNativeFileShare(files: File[]): boolean {
  const ua = navigator.userAgent;
  const isMobile =
    /Android|iPhone|iPad|iPod/i.test(ua) ||
    // iPadOS 13+는 데스크톱 UA(Macintosh)로 위장 — 터치 지점으로 구분
    (ua.includes("Macintosh") && (navigator.maxTouchPoints || 0) > 1);
  if (!isMobile) return false;
  const nav: any = navigator;
  return !!nav.canShare?.({ files }) && !!nav.share;
}
