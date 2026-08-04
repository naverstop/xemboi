/** B-3 이용 후기 페이지 — 승인된 후기 전체 목록(메뉴 필터). 작성은 각 답변의 👍 직후 팝업에서. */
import { useEffect, useState } from "react";
import { api, type Review, type ReviewSource } from "../api";

const FILTERS: { key: ReviewSource | ""; label: string }[] = [
  { key: "", label: "전체" },
  { key: "chat", label: "사주 상담" },
  { key: "compat", label: "궁합" },
  { key: "tarot", label: "타로" },
  { key: "tool", label: "택일·작명" },
  { key: "sinnyeon", label: "신년운세" },
  { key: "consultation", label: "1:1 상담" },
];

export default function ReviewsPage() {
  const [src, setSrc] = useState<ReviewSource | "">("");
  const [items, setItems] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .publicReviews(src || undefined, 50)
      .then((r) => alive && setItems(r.items))
      .catch(() => alive && setItems([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [src]);

  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">後記</div>
        <h1>이용 후기</h1>
        <p>실제 이용자들이 남긴 <b>진짜 후기</b>예요. 상담 답변 아래 👍를 누르면 후기를 남길 수 있고, 게시가 확정되면 <b>포인트를 적립</b>해 드려요.</p>
      </header>

      <div className="rv-filter" role="tablist" aria-label="메뉴 필터">
        {FILTERS.map((f) => (
          <button
            key={f.key || "all"}
            role="tab"
            aria-selected={src === f.key}
            className={`fb-chip${src === f.key ? " on" : ""}`}
            onClick={() => setSrc(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: "var(--ink-400, #888)" }}>후기를 불러오는 중…</p>
      ) : items.length === 0 ? (
        <p style={{ color: "var(--ink-400, #888)" }}>
          아직 게시된 후기가 없어요. 첫 후기의 주인공이 되어 주세요 — 상담 답변 아래 👍를 누르면 남길 수 있어요.
        </p>
      ) : (
        <div className="rv-page-grid">
          {items.map((r) => (
            <figure className="rv-card" key={r.id}>
              <div className="rv-stars" aria-label={`별점 ${r.rating}점`}>
                {"★".repeat(r.rating)}
                <span className="rv-stars-dim">{"★".repeat(5 - r.rating)}</span>
              </div>
              <blockquote className="rv-quote" style={{ WebkitLineClamp: "unset" as any }}>{r.content}</blockquote>
              <figcaption className="rv-meta">
                <span className="rv-name">{r.display_name}</span>
                <span className="rv-src">{r.source_label}</span>
                {r.created_at && <span>{r.created_at.slice(0, 10)}</span>}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  );
}
