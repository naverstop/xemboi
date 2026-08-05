/** B-3 이용 후기 페이지 — 승인된 후기 전체 목록(메뉴 필터). 작성은 각 답변의 👍 직후 팝업에서. */
import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api, type Review, type ReviewSource } from "../api";

// label 은 i18n 키(common.reviews.*) — 렌더 시 tr() 로 해석해 언어 전환에 즉시 반응.
const FILTERS: { key: ReviewSource | ""; label: string }[] = [
  { key: "", label: "reviews.f_all" },
  { key: "chat", label: "reviews.f_chat" },
  { key: "compat", label: "reviews.f_compat" },
  { key: "tarot", label: "reviews.f_tarot" },
  { key: "tool", label: "reviews.f_tool" },
  { key: "sinnyeon", label: "reviews.f_sinnyeon" },
  { key: "consultation", label: "reviews.f_consult" },
];

export default function ReviewsPage() {
  const { t: tr } = useTranslation();
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
        <div className="compat-hero-badge">{tr("reviews.hero_badge")}</div>
        <h1>{tr("reviews.hero_title")}</h1>
        <p><Trans i18nKey="reviews.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      <div className="rv-filter" role="tablist" aria-label={tr("reviews.filter_aria")}>
        {FILTERS.map((f) => (
          <button
            key={f.key || "all"}
            role="tab"
            aria-selected={src === f.key}
            className={`fb-chip${src === f.key ? " on" : ""}`}
            onClick={() => setSrc(f.key)}
          >
            {tr(f.label)}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: "var(--ink-400, #888)" }}>{tr("reviews.loading")}</p>
      ) : items.length === 0 ? (
        <p style={{ color: "var(--ink-400, #888)" }}>
          {tr("reviews.empty")}
        </p>
      ) : (
        <div className="rv-page-grid">
          {items.map((r) => (
            <figure className="rv-card" key={r.id}>
              <div className="rv-stars" aria-label={tr("reviews.stars_aria", { n: r.rating })}>
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
