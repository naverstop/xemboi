import { useEffect, useState } from "react";
import { api, Review, ReviewSource } from "../api";

/** B-3 공개 후기 스트립 — 승인된 후기만 가로 스크롤 카드로 노출.
 *  랜딩 섹션·메뉴 히어로 밑·/reviews 페이지에서 공용. 후기가 없으면 아무것도 렌더하지 않는다(콜드스타트). */
export default function ReviewStrip({
  source,
  limit = 12,
  title,
}: {
  source?: ReviewSource;
  limit?: number;
  title?: string;
}) {
  const [items, setItems] = useState<Review[]>([]);

  useEffect(() => {
    let alive = true;
    api
      .publicReviews(source, limit)
      .then((r) => alive && setItems(r.items))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [source, limit]);

  if (!items.length) return null;

  return (
    <div className="rv-strip-wrap">
      {title && <div className="rv-strip-title">{title}</div>}
      <div className="rv-strip" role="list">
        {items.map((r) => (
          <figure className="rv-card" role="listitem" key={r.id}>
            <div className="rv-stars" aria-label={`별점 ${r.rating}점`}>
              {"★".repeat(r.rating)}
              <span className="rv-stars-dim">{"★".repeat(5 - r.rating)}</span>
            </div>
            <blockquote className="rv-quote">{r.content}</blockquote>
            <figcaption className="rv-meta">
              <span className="rv-name">{r.display_name}</span>
              <span className="rv-src">{r.source_label}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}
