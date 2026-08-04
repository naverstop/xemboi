/** 공통 다운로드/열람 가드 링크 (운영자 지시 2026-07-11).
 *
 *  전 메뉴 다운로드 버튼 규약:
 *  ① 클릭 → 즉시 실행 + 잠깐 잠금(연타해도 1회만)
 *  ② 완료 → 라벨이 "✅ 다운로드 완료"로 바뀜
 *  ③ 완료 후 재클릭 → "다시 다운로드 하시겠습니까?" 확인 팝업(확인/취소)
 *
 *  mode="download"=파일 저장(임시 anchor click), mode="open"=새 탭 열람(PDF 등).
 *  href는 접근성·호버 URL 표시용으로 유지하되 실제 동작은 onClick이 제어한다.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

export default function DownloadGuard({
  href, filename, className, children, doneLabel, busyLabel, mode = "download", onFire,
}: {
  href: string;
  filename?: string;
  className?: string;
  children: ReactNode;              // 대기 라벨
  doneLabel?: ReactNode;            // 완료 라벨(기본: ✅ 다운로드 완료 / ✅ 열람 완료 · 다시 열기)
  busyLabel?: ReactNode;            // 진행 라벨(기본: ⏳ 여는 중…/다운로드 중…) — 폭 고정 스택 주입용
  mode?: "download" | "open";
  onFire?: () => void;              // 실제 실행된 순간 콜백(메뉴 닫기 등)
}) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const lock = useRef(false);   // 동기 잠금 — React state는 같은 틱 연타를 못 막는다(3연타=3다운로드 실측)
  const timer = useRef<number | null>(null);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  function fire() {
    if (mode === "open") {
      window.open(href, "_blank", "noopener");
      return;
    }
    const a = document.createElement("a");
    a.href = href;
    if (filename) a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function onClick(e: React.MouseEvent) {
    e.preventDefault();                         // 기본 내비게이션 차단 — 상태 머신이 실행을 제어
    if (lock.current) return;                   // 연타 방지: 동기 잠금(더블클릭·같은 틱 다연타 포함)
    if (state === "done" &&
        !window.confirm(mode === "open" ? "다시 여시겠습니까?" : "다시 다운로드 하시겠습니까?")) return;
    lock.current = true;
    setState("busy");
    onFire?.();
    fire();
    timer.current = window.setTimeout(() => { lock.current = false; setState("done"); }, 1400);
  }

  return (
    <a className={className} href={href} onClick={onClick} aria-disabled={state === "busy"}
       target={mode === "open" ? "_blank" : undefined} rel="noopener noreferrer">
      {state === "busy"
        ? (busyLabel ?? (mode === "open" ? "⏳ 여는 중…" : "⏳ 다운로드 중…"))
        : state === "done"
          ? (doneLabel ?? (mode === "open" ? "✅ 열람 완료 · 다시 열기" : "✅ 다운로드 완료"))
          : children}
    </a>
  );
}
