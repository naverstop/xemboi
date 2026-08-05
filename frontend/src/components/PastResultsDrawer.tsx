/** '지난 결과' 재열람 드로어 — 프리미엄 도구/궁합 공용(운영자 지시 2026-07-19).
 *  입장료를 낸 결과가 이탈/새로고침으로 사라져 '재결제'로 오해되던 문제(패턴 A) 대응.
 *  타로 '내 기록'과 동일 UX. 클릭 시 무차감 GET(getTool/getCompatibility)으로 결과를 되살린다.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";

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
  emptyText,
  note,
  label,
}: {
  items: PastItem[] | null;
  loading?: boolean;
  onOpen: () => void;             // 드로어를 열 때 목록 새로고침
  onPick: (id: string) => void;   // 항목 선택 → 무차감 복원
  emptyText?: string;             // 기본=로케일 libx.past_empty
  note?: string;                  // 기본=로케일 libx.past_note
  label?: string;                 // 기본=로케일 libx.past_label
}) {
  const { t: tr } = useTranslation();
  const [open, setOpen] = useState(false);
  const labelTx = label ?? tr("libx.past_label");
  return (
    <div className="past-float">
      <button
        className="past-hist-btn"
        onClick={() => { onOpen(); setOpen((v) => !v); }}
        title={tr("libx.past_title")}
      >
        🗂 {labelTx}{items && items.length > 0 ? <em> {items.length}</em> : null}
      </button>
      {open && (
        <aside className="past-drawer" role="dialog" aria-label={labelTx}>
          <div className="past-drawer-head">
            <span>{labelTx}</span>
            <button className="past-drawer-x" aria-label={tr("pay.close")} onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="past-drawer-note">{note ?? tr("libx.past_note")}</div>
          {loading && <div className="past-drawer-empty">{tr("libx.loading")}</div>}
          {!loading && items && items.length === 0 && <div className="past-drawer-empty">{emptyText ?? tr("libx.past_empty")}</div>}
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

/** created_at(ISO) → 로케일 날짜·시각 표기(목록 카드용). ko='M월 D일 HH:mm' / vi='D/M HH:mm'. */
export function fmtWhen(iso: string): string {
  try {
    const loc = i18n.language?.startsWith("vi") ? "vi-VN" : "ko-KR";
    return new Date(iso).toLocaleString(loc, { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}
