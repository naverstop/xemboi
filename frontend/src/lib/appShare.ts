/** 앱 공유 — '설치 유도' 랜딩 링크를 OS 공유 시트/복사로 전달 (운영자 지시 2026-07-18).
 *
 *  수신자 흐름(요건 3~5)은 이미 구축된 인프라가 처리한다:
 *   - 공유 URL = `${origin}/?install=1`.
 *   - 수신자가 카카오톡·인스타 등 '인앱 브라우저'에서 열면 → InstallPrompt 가 자동 경고 후
 *     동의 1클릭으로 크롬/사파리로 탈출(escapeToExternalBrowser, ?install=1 보존).
 *   - 크롬/사파리(또는 일반 브라우저)에서 열리면 → ?install=1 로 설치 가이드가 자동으로 뜬다.
 *  즉 이 함수는 '설치까지 이어지는 올바른 링크'를 공유 시트/클립보드로 내보내는 역할만 한다.
 */

/** 수신자에게 전달할 설치유도 랜딩 URL(홈 + ?install=1). */
export function appShareUrl(): string {
  return `${window.location.origin}/?install=1`;
}

const SHARE_TITLE = "인생상담 친구";
const SHARE_TEXT =
  "사주·타로·꿈해몽·궁합까지 — 인생상담 친구예요. 이 링크를 열면 바로 앱으로 설치할 수 있어요.";

export type ShareResult = "shared" | "copied" | "failed";

/** OS 공유 시트(navigator.share) 우선, 없거나 실패하면 링크 복사 폴백. */
export async function shareApp(): Promise<ShareResult> {
  const url = appShareUrl();
  const nav = navigator as Navigator & {
    share?: (d: ShareData) => Promise<void>;
  };

  if (typeof nav.share === "function") {
    try {
      await nav.share({ title: SHARE_TITLE, text: SHARE_TEXT, url });
      return "shared";
    } catch (e) {
      // 사용자가 공유 시트를 취소한 경우(AbortError)는 오류가 아니라 정상 종료로 본다.
      if (e instanceof DOMException && e.name === "AbortError") return "shared";
      // 그 외(권한/미지원 등) → 복사 폴백으로 진행
    }
  }

  try {
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch {
    // 비보안 컨텍스트/구형 대비 execCommand 폴백
    try {
      const ta = document.createElement("textarea");
      ta.value = url;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok ? "copied" : "failed";
    } catch {
      return "failed";
    }
  }
}
