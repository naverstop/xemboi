/** 목록 다중선택(체크박스·전체선택·일괄삭제) 공용 훅.
 *  상담 기록·타로 기록 등 '히스토리 관리' 화면에서 개별삭제 대신 체크→일괄삭제를 지원한다.
 */
import { useCallback, useState } from "react";

export function useBulkSelect<T = string>() {
  const [selected, setSelected] = useState<Set<T>>(new Set());

  const toggle = useCallback((id: T) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }, []);

  // 전체선택 토글 — on=true면 ids 전부 선택, false면 해제.
  const setAll = useCallback((ids: T[], on: boolean) => {
    setSelected(on ? new Set(ids) : new Set());
  }, []);

  const clear = useCallback(() => setSelected(new Set()), []);
  const has = useCallback((id: T) => selected.has(id), [selected]);

  return { selected, toggle, setAll, clear, has, count: selected.size };
}
