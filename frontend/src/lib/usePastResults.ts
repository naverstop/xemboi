/** 프리미엄 결과 재열람 공용 훅 (패턴 A — 결과유실+재차감 대응, 2026-07-19).
 *  - usePremiumRestore: 생성한 결과의 id를 sessionStorage에 기억하고, 페이지 재진입/새로고침 시
 *    무차감 GET으로 자동 복원한다. 드로어에서 지난 항목을 고를 때도 이 restore를 쓴다.
 *  - usePastList: '지난 결과' 드로어용 목록 상태(열 때 새로고침).
 *  sessionStorage는 F5/SPA 재마운트에도 유지되므로(탭 닫힘에만 소멸) 이탈→복귀 시나리오를 덮는다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export function usePremiumRestore<T>(opts: {
  storageKey: string;
  getOne: (id: string) => Promise<T>;
  apply: (res: T) => void;   // 복원된 결과를 페이지 상태에 반영(setRes + restored 플래그 등)
  /** 복원 대상 필터 — false면 폐기(키 제거·미반영). 예: 미리보기(익명) 세션은 재열람 대상이 아니다.
   *  [운영자 실측·확정 2026-08-05] 로그아웃 상태에서 만든 익명 미리보기 세션(is_preview=True·user_id=None)이
   *  sessionStorage에 남아, 로그인 후 재진입 시 그대로 복원됐다. 그 세션은 preview 플래그가 DB에 영구
   *  고정이라 해설을 다시 눌러도 계속 컷+보강 스킵 → '로그인했는데 또 미리보기로 멈춤'. accept로 원천 차단. */
  accept?: (res: T) => boolean;
}) {
  const { storageKey, getOne, apply, accept } = opts;
  const applyRef = useRef(apply);
  applyRef.current = apply;
  const getRef = useRef(getOne);
  getRef.current = getOne;
  const acceptRef = useRef(accept);
  acceptRef.current = accept;
  const once = useRef(false);

  const restore = useCallback((id: string): Promise<void> => {
    return getRef.current(id)
      .then((r) => {
        if (acceptRef.current && !acceptRef.current(r)) { sessionStorage.removeItem(storageKey); return; }
        applyRef.current(r); sessionStorage.setItem(storageKey, id);
      })
      .catch(() => { sessionStorage.removeItem(storageKey); });   // 만료·삭제·비소유 → 조용히 무시
  }, [storageKey]);

  // 마운트 1회 — 기억된 마지막 결과가 있으면 자동 복원(무차감)
  useEffect(() => {
    if (once.current) return;
    once.current = true;
    const id = sessionStorage.getItem(storageKey);
    if (id) void restore(id);
  }, [storageKey, restore]);

  const remember = useCallback((id: string) => {
    try { sessionStorage.setItem(storageKey, id); } catch { /* noop */ }
  }, [storageKey]);

  return { restore, remember };
}

export function usePastList<I>(fetchList: () => Promise<I[]>) {
  const fetchRef = useRef(fetchList);
  fetchRef.current = fetchList;
  const [items, setItems] = useState<I[] | null>(null);
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(() => {
    setLoading(true);
    fetchRef.current()
      .then((its) => setItems(its))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);
  return { items, loading, refresh };
}
