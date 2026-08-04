/** '이 [명식/결과]로 1:1 상담' 강조 CTA 배너 — FLUX 엠블럼 + 제목 + 설명 + 화살표 + 글로우.
 *  타로의 '이 카드로 1:1 상담' 럭셔리 CTA와 동일 UX를 밝은 브랜드 톤으로 공용화(운영자 지시 2026-07-21).
 *  배지 이미지가 없으면(onError) 아이콘만 숨기고 텍스트 CTA는 그대로 동작. */
export default function ConsultBanner({
  badge = "/saju/consult-badge.webp",
  title,
  desc,
  onClick,
}: {
  badge?: string;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <div className="consult-banner-wrap">
      <button type="button" className="consult-banner" title={desc} onClick={onClick}>
        <img
          className="cbn-emblem" src={badge} alt="" width={52} height={52}
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
        />
        <span className="cbn-text">
          <b className="cbn-title">{title}</b>
          <small className="cbn-desc">{desc}</small>
        </span>
        <span className="cbn-arrow" aria-hidden>➤</span>
      </button>
    </div>
  );
}
