/** 슬롯 단위 배너 렌더링. me.ads_hidden 이면 비표시. */
import { useEffect, useState } from "react";
import { api, useMe } from "../api";

type B = {
  id: number;
  slot: string;
  image_url: string;
  link_url?: string | null;
  title?: string | null;
};

export default function BannerSlot({ slot, height }: { slot: string; height?: number }) {
  const me = useMe();
  const hidden = me?.ads_hidden === true;
  const [banner, setBanner] = useState<B | null>(null);

  useEffect(() => {
    if (hidden) return;
    let cancelled = false;
    api
      .publicBanners(slot, true)
      .then((r) => {
        if (cancelled) return;
        setBanner(r.items[0] || null);
      })
      .catch(() => setBanner(null));
    return () => {
      cancelled = true;
    };
  }, [slot, hidden]);

  if (hidden || !banner) return null;
  // 폭에 맞춰 SVG 전체가 보이도록 width:100%/height:auto(크롭 없음).
  // 기존 objectFit:cover+고정높이는 좁은 화면에서 좌측(아이콘+제목)을 잘라냈음.
  void height;
  const inner = (
    <img
      src={banner.image_url}
      alt={banner.title || banner.slot}
      style={{
        display: "block",
        width: "100%",
        height: "auto",
        borderRadius: 10,
      }}
    />
  );
  return (
    <div className={`banner-slot banner-${slot}`} style={{ margin: "8px 0" }}>
      {banner.link_url ? (
        <a href={banner.link_url} target="_blank" rel="noreferrer">
          {inner}
        </a>
      ) : (
        inner
      )}
    </div>
  );
}
