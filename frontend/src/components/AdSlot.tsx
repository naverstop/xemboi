/** 답변 하단 광고 슬롯 (항목 N).
 * - 자체 배너(House Ads, slot=answer_bottom) 우선 → 없으면 외부 광고(Google AdSense) 폴백.
 * - me.ads_hidden 이면 비표시 (등급 연동은 P4에서 level 기반으로 확장).
 * - AdSense 식별자는 프론트 환경변수로 관리: VITE_ADSENSE_CLIENT, VITE_ADSENSE_SLOT_ANSWER.
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, useMe } from "../api";

type B = {
  id: number;
  slot: string;
  image_url: string;
  link_url?: string | null;
  title?: string | null;
};

const ADSENSE_CLIENT = import.meta.env.VITE_ADSENSE_CLIENT as string | undefined;
const ADSENSE_SLOT = import.meta.env.VITE_ADSENSE_SLOT_ANSWER as string | undefined;

export default function AdSlot({
  slot = "answer_bottom",
  height,
  adsenseSlot,
}: {
  slot?: string;
  height?: number;
  adsenseSlot?: string; // 이 배치 전용 AdSense 광고단위 ID(없으면 기본 ANSWER 슬롯)
}) {
  const me = useMe();
  const { t: tr } = useTranslation();
  const hidden = me?.ads_hidden === true;
  const slotId = adsenseSlot || ADSENSE_SLOT;
  const [banner, setBanner] = useState<B | null>(null);
  const [loaded, setLoaded] = useState(false);
  const insRef = useRef<HTMLModElement | null>(null);
  const pushed = useRef(false);

  useEffect(() => {
    if (hidden) return;
    let cancelled = false;
    api
      .publicBanners(slot, true)
      .then((r) => {
        if (cancelled) return;
        setBanner(r.items[0] || null);
        setLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setBanner(null);
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [slot, hidden]);

  // 자체 배너가 없을 때만 AdSense 렌더 시도
  const useAdsense = loaded && !banner && !!ADSENSE_CLIENT && !!slotId;

  // AdSense 스크립트 1회 동적 로드 (환경변수 있을 때만)
  const ensureAdsenseScript = () => {
    if (!ADSENSE_CLIENT) return;
    const id = "adsbygoogle-js";
    if (document.getElementById(id)) return;
    const sc = document.createElement("script");
    sc.id = id;
    sc.async = true;
    sc.crossOrigin = "anonymous";
    sc.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}`;
    document.head.appendChild(sc);
  };

  useEffect(() => {
    if (!useAdsense || pushed.current) return;
    ensureAdsenseScript();
    try {
      // @ts-expect-error adsbygoogle 전역
      (window.adsbygoogle = window.adsbygoogle || []).push({});
      pushed.current = true;
    } catch {
      /* AdSense 미로딩/차단 시 무시 */
    }
  }, [useAdsense]);

  if (hidden) return null;

  if (banner) {
    const img = (
      <img
        src={banner.image_url}
        alt={banner.title || banner.slot}
        className="adslot-img"
        style={{ height: height || "auto" }}
      />
    );
    return (
      <div className="ad-slot house" aria-label={tr("misc.ad_label")}>
        <span className="ad-label">{tr("misc.ad_label")}</span>
        {banner.link_url ? (
          <a href={banner.link_url} target="_blank" rel="noreferrer">
            {img}
          </a>
        ) : (
          img
        )}
      </div>
    );
  }

  if (useAdsense) {
    return (
      <div className="ad-slot adsense" aria-label={tr("misc.ad_label")}>
        <span className="ad-label">Sponsored</span>
        <ins
          ref={insRef}
          className="adsbygoogle"
          style={{ display: "block" }}
          data-ad-client={ADSENSE_CLIENT}
          data-ad-slot={slotId}
          data-ad-format="auto"
          data-full-width-responsive="true"
        />
      </div>
    );
  }

  // 광고 없음 → 빈 슬롯 렌더 안 함(collapse)
  return null;
}
