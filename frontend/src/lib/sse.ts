// 공용 SSE 스트리밍 (채팅/궁합/도구 동일 프로토콜). 한 어시스턴트 턴 스트리밍.
import { ensureFreshToken, notifySessionExpired } from "../api";

export type SSEHandlers = {
  onChunk: (full: string) => void;
  onRefine?: (full: string) => void;
  onCut?: () => void;
  onStage?: (phase: string) => void;
  onDone?: (d: any) => void;
};

/** @returns 'done' 이벤트 수신 여부 — false면 연결이 중간에 끊긴 것(모바일 절전/네트워크 등).
 *  서버는 이어서 완성·저장했을 수 있으므로 호출부가 저장본 재동기화/재시도로 복구해야 한다(운영자 보고 실사례). */
export async function streamSSE(
  url: string,
  body: { message: string; depth: "basic" | "deep"; explain_level?: "normal" | "easy" },
  h: SSEHandlers,
  signal?: AbortSignal,
  idleMs = 60000,   // 첫 콘텐츠 청크 무도착 감시(무데이터 hang → STREAM_STALLED). 0 이면 비활성.
): Promise<boolean> {
  const tok = await ensureFreshToken();   // 만료 토큰 → 익명 미리보기 방지(무음 갱신)
  // 무데이터 hang 방어(전 소비부 공통): 외부 signal(이탈 abort)과 무청크 워치독을 내부 컨트롤러로 합침.
  // 서버가 연결만 잡고 첫 콘텐츠를 idleMs 안에 안 주면 끊어 '생성 중' 무한 고착을 STREAM_STALLED 로 전환.
  const ctrl = new AbortController();
  const relayAbort = () => { try { ctrl.abort(); } catch { /* noop */ } };
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", relayAbort, { once: true });
  }
  let gotFirst = false;
  let stalled = false;
  let watchdog: number | null = idleMs > 0
    ? window.setTimeout(() => { if (!gotFirst) { stalled = true; relayAbort(); } }, idleMs)
    : null;
  const disarm = () => { if (watchdog !== null) { window.clearTimeout(watchdog); watchdog = null; } };
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
      body: JSON.stringify({ explain_level: "normal", ...body }),
      signal: ctrl.signal,  // 페이지 이탈/워치독 abort → 연결 종료 → 백엔드 disconnect 감지 → LLM(GPU) 즉시 중단
    });
    if (!resp.ok || !resp.body) {
      if (resp.status === 401) { notifySessionExpired(); throw new Error("SESSION_EXPIRED"); }
      if (resp.status === 402) throw new Error("PAYWALL");
      throw new Error(`stream ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let acc = "";
    let gotDone = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        let event = "message";
        let data = "";
        for (const line of part.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data = line.slice(5).trim();
        }
        if (event === "chunk" && data) {
          gotFirst = true; disarm();
          try { acc += JSON.parse(data).text; h.onChunk(acc); } catch {}
        } else if (event === "refine" && data) {
          gotFirst = true; disarm();
          try { acc = JSON.parse(data).text || acc; h.onRefine?.(acc); } catch {}
        } else if (event === "cut") {
          gotFirst = true; disarm();
          acc += " …"; h.onChunk(acc); h.onCut?.();
        } else if (event === "stage" && data) {
          try { h.onStage?.(JSON.parse(data).phase); } catch {}
        } else if (event === "done" && data) {
          gotFirst = true; disarm();
          gotDone = true;
          try { h.onDone?.(JSON.parse(data)); } catch {}
        } else if (event === "error" && data) {
          try { throw new Error(JSON.parse(data).detail || "스트림 오류"); } catch (e) { throw e; }
        }
      }
    }
    return gotDone;
  } catch (e: any) {
    if (stalled) throw new Error("STREAM_STALLED");   // 워치독 abort → 소비부가 '지연' 안내/재시도로 처리
    throw e;
  } finally {
    disarm();
    if (signal) signal.removeEventListener("abort", relayAbort);
  }
}
