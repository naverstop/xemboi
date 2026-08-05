/** 인앱 브라우저 감지 + 외부 브라우저(크롬/사파리) 탈출 (운영자 지시 2026-07-11).
 *
 *  카카오톡·네이버·인스타 등 인앱 웹뷰는 PWA 설치가 불가 → 경고 후 동의를 받아
 *  기기 기본 브라우저로 내보낸다. 탈출 URL에 ?install=1 을 붙여, 열린 크롬/사파리에서
 *  설치 가이드가 자동으로 이어지게 한다(InstallPrompt가 소비).
 *
 *  탈출 수단(플랫폼별):
 *  - 카카오톡: kakaotalk://web/openExternal?url=…  (공식 딥링크 — iOS/Android 모두)
 *  - 라인: URL 에 ?openExternalBrowser=1 부여(라인 공식 파라미터)
 *  - 그 외 Android 인앱: intent:// 스킴으로 Chrome 지정(+https 폴백)
 *  - 그 외 iOS 인앱(인스타·페북 등): 프로그램적 탈출 불가 → 'copy'(주소 복사 + 수동 안내)
 */

import i18n from "../i18n";

export function isIOS(): boolean {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

export function isAndroid(): boolean {
  return /android/i.test(window.navigator.userAgent);
}

export type InAppInfo = { inApp: boolean; kakao: boolean; name: string };

export function inAppBrowser(): InAppInfo {
  const ua = window.navigator.userAgent;
  // 표시명은 호출 시점 로케일로 해석(ko 한글 표기 / vi 로마자 표기 — misc.inapp_*). UA 정규식은 내부값.
  if (/KAKAOTALK/i.test(ua)) return { inApp: true, kakao: true, name: i18n.t("misc.inapp_kakaotalk") };
  if (/KAKAOSTORY/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_kakaostory") };
  if (/NAVER\(inapp/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_naver") };
  if (/Instagram/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_instagram") };
  if (/Threads/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_threads") };
  if (/FBAN|FBAV|FB_IAB/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_facebook") };
  if (/Line\//i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_line") };
  if (/MicroMessenger/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_wechat") };
  if (/musical_ly|Bytedance/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_tiktok") };
  if (/DaumApps|everytimeApp|band\//i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_generic") };
  // 최후 폴백: 앱 이름을 안 밝히는 Android 인앱 웹뷰(; wv). 정상 크롬·삼성인터넷 UA엔 ';wv'가 없어 오탐 낮음.
  if (/android/i.test(ua) && /;\s*wv[);]/i.test(ua)) return { inApp: true, kakao: false, name: i18n.t("misc.inapp_generic") };
  return { inApp: false, kakao: false, name: "" };
}

export function isStandalonePwa(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

/** 진짜 홈 화면 추가(standalone PWA)가 되는 순수 iOS Safari인가.
 *  iOS의 Chrome(CriOS)·Firefox(FxiOS)·Edge(EdgiOS)·오페라(OPiOS)·웨일(Whale)·네이버 등과
 *  카카오·인스타 인앱 웹뷰는 '홈 화면에 추가'가 없거나 진짜 앱으로 안 붙는다 → Safari로 유도해야 한다. */
export function isIOSSafari(): boolean {
  if (!isIOS()) return false;
  const ua = window.navigator.userAgent;
  if (/CriOS|FxiOS|EdgiOS|OPiOS|Whale|NAVER/i.test(ua)) return false;
  return !inAppBrowser().inApp;
}

/** 외부 브라우저에서 이어서 열 대상 URL(설치 가이드 자동 연결용 ?install=1 포함). iOS 복사 폴백도 이걸 쓴다. */
export function externalTargetUrl(withInstallFlag = true): string {
  const url = new URL(window.location.href);
  if (withInstallFlag) url.searchParams.set("install", "1");
  return url.toString();
}

/** 외부 브라우저로 현재 페이지 열기 시도. 'opened'=탈출 시도됨, 'copy'=수동 안내 필요(iOS 인앱). */
export function escapeToExternalBrowser(withInstallFlag = true): "opened" | "copy" {
  const target = externalTargetUrl(withInstallFlag);
  const ua = window.navigator.userAgent;

  if (/KAKAOTALK/i.test(ua)) {
    window.location.href = "kakaotalk://web/openExternal?url=" + encodeURIComponent(target);
    return "opened";
  }
  if (/Line\//i.test(ua)) {
    const lineUrl = new URL(target);
    lineUrl.searchParams.set("openExternalBrowser", "1");
    window.location.href = lineUrl.toString();
    return "opened";
  }
  if (isAndroid()) {
    // Android 인앱 공통 — Chrome intent(미설치 시 https 폴백)
    const noScheme = target.replace(/^https?:\/\//, "");
    window.location.href =
      `intent://${noScheme}#Intent;scheme=https;package=com.android.chrome;` +
      `S.browser_fallback_url=${encodeURIComponent(target)};end`;
    return "opened";
  }
  return "copy";   // iOS 비카카오 인앱 — 스킴 탈출 수단 없음
}
