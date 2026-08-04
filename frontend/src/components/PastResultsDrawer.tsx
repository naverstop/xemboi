/** '지난 결과' 재열람 드로어 — 프리미엄 도구/궁합 공용(운영자 지시 2026-07-19).
 *  입장료를 낸 결과가 이탈/새로고침으로 사라져 '재결제'로 오해되던 문제(패턴 A) 대응.
 *  타로 '내 기록'과 동일 UX. 클릭 시 무차감 GET(getTool/getCompatibility)으로 결과를 되살린다.
 */
import { useState } from "react";

export type PastItem = {
  id: string;
  title: string;
  subtitle?: string;
  when: string;   // 표시용 날짜문자열
};

export default function PastResultsDrawer({
  items,
  loading,
  onOpen,
  onPick,
  emptyText = "아직 저장된 결과가 없어요.",
  note = "🕰 지난 결과는 언제든 다시 볼 수 있어요 — 재열람은 포인트가 차감되지 않아요.",
  label = "지난 결과",
}: {
  items: PastItem[] | null;
  loading?: boolean;
  onOpen: () => void;             // 드로어를 열 때 목록 새로고침
  onPick: (id: string) => void;   // 항목 선택 → 무차감 복원
  emptyText?: string;
  note?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="past-float">
      <button
        className="past-hist-btn"
        onClick={() => { onOpen(); setOpen((v) => !v); }}
        title="입장료 없이 지난 결과를 다시 봅니다"
      >
        🗂 {label}{items && items.length > 0 ? <em> {items.length}</em> : null}
      </button>
      {open && (
        <aside className="past-drawer" role="dialog" aria-label={label}>
          <div className="past-drawer-head">
            <span>{label}</span>
            <button className="past-drawer-x" aria-label="닫기" onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="past-drawer-note">{note}</div>
          {loading && <div className="past-drawer-empty">불러오는 중…</div>}
          {!loading && items && items.length === 0 && <div className="past-drawer-empty">{emptyText}</div>}
          {!loading && items && items.map((it) => (
            <button key={it.id} className="past-item" onClick={() => { onPick(it.id); setOpen(false); }}>
              <div className="past-item-title">{it.title}</div>
              {it.subtitle && <div className="past-item-sub">{it.subtitle}</div>}
              <div className="past-item-when">{it.when}</div>
            </button>
          ))}
        </aside>
      )}
    </div>
  );
}

/** created_at(ISO) → 'M월 D일 HH:mm' 한국시간 표기(목록 카드용). */
export function fmtWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}
