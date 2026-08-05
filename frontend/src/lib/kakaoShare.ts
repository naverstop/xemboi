/** 카카오톡 공유(링크 카드) — 데스크톱 등 파일 첨부 불가 환경에서 PDF 링크를 카톡으로 보낸다.
 *
 *  ⚠️ 카카오 JS SDK는 링크/메시지 카드만 보낼 수 있고 '파일 첨부'는 불가하다(웹 플랫폼 제약).
 *     그래서 여기서는 상담서 PDF의 공개 토큰 URL(GET /api/pdf/{token})을 카드로 보내고,
 *     수신자가 눌러 서버에서 열람/저장한다. 실제 파일 자체 전송은 모바일 Web Share(files)에서만 됨.
 *
 *  준비물(운영자):
 *   1) Kakao Developers → 내 애플리케이션 → 앱 키 → **JavaScript 키** 를 VITE_KAKAO_JS_KEY 로 주입(빌드 env).
 *   2) 플랫폼 > Web 사이트 도메인에 https://saju.songstock.art 등록 + 카카오링크/메시지 사용 설정.
 *   키가 없으면 kakaoAvailable()=false → 공유 메뉴에서 카카오 버튼은 자동 숨김(링크복사로 대체).
 */
import i18n from "../i18n";

const KAKAO_JS_KEY = (import.meta.env.VITE_KAKAO_JS_KEY as string | undefined)?.trim();
// SDK CDN 후보(앞에서부터 시도). 둘 다 Kakao.Share.sendDefault 제공.
//  · t1.kakao.com = 공식 권장(버전 고정 v2). 일부 폐쇄망/샌드박스에선 차단될 수 있음.
//  · developers.kakao.com = 폴백(항상 로드 확인됨). 한쪽 CDN 장애/차단 시 자동 대체.
const SDK_URLS = [
  "https://t1.kakao.com/kakao_js_sdk/2.7.2/kakao.min.js",
  "https://developers.kakao.com/sdk/js/kakao.min.js",
];

let loadPromise: Promise<boolean> | null = null;

/** 키가 주입돼 있으면 true(카카오 버튼 노출 가능). */
export function kakaoAvailable(): boolean {
  return !!KAKAO_JS_KEY;
}

function loadScript(url: string): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = url;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => { s.remove(); reject(new Error("load fail: " + url)); };
    document.head.appendChild(s);
  });
}

/** 후보 URL을 순차 시도해 window.Kakao 확보. 하나라도 성공하면 true. */
async function loadSdk(): Promise<boolean> {
  if ((window as any).Kakao) return true;
  for (const url of SDK_URLS) {
    try {
      await loadScript(url);
      if ((window as any).Kakao) return true;
    } catch {
      /* 다음 후보로 */
    }
  }
  return !!(window as any).Kakao;
}

/** SDK를 필요 시 1회 동적 로드하고 init. 실패/미설정 시 null. */
async function ensureKakao(): Promise<any | null> {
  if (!KAKAO_JS_KEY) return null;
  if (!(window as any).Kakao) {
    if (!loadPromise) loadPromise = loadSdk();
    const ok = await loadPromise;
    if (!ok) { loadPromise = null; return null; }
  }
  const K = (window as any).Kakao;
  try {
    if (K && !K.isInitialized()) K.init(KAKAO_JS_KEY);
  } catch {
    return null;
  }
  return K || null;
}

/** 상담서 PDF 링크를 카카오톡 피드 카드로 공유. 성공 true / 사용불가·실패 false(호출부가 링크복사로 폴백). */
export async function shareKakaoLink(opts: {
  title: string;
  description?: string;
  url: string;       // 절대 URL(GET /api/pdf/{token})
  imageUrl: string;  // 카드 썸네일(절대 URL). 카카오가 스크랩 가능한 공개 이미지여야 함.
}): Promise<boolean> {
  const K = await ensureKakao();
  if (!K?.Share?.sendDefault) return false;
  try {
    K.Share.sendDefault({
      objectType: "feed",
      content: {
        title: opts.title,
        description: opts.description || i18n.t("answer.kakao_fallback_desc"),
        imageUrl: opts.imageUrl,
        link: { mobileWebUrl: opts.url, webUrl: opts.url },
      },
      buttons: [
        { title: i18n.t("answer.kakao_card_btn"), link: { mobileWebUrl: opts.url, webUrl: opts.url } },
      ],
    });
    return true;
  } catch {
    return false;
  }
}
