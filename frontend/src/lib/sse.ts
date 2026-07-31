// 공용 SSE 스트리밍 (채팅/궁합/도구 동일 프로토콜). 한 어시스턴트 턴 스트리밍.
import { getToken, notifySessionExpired } from "../api";

export type SSEHandlers = {
  onChunk: (full: string) => void;
  onRefine?: (full: string) => void;
  onCut?: () => void;
  onStage?: (phase: string) => void;
  onDone?: (d: any) => void;
};

export async function streamSSE(
  url: string,
  body: { message: string; depth: "basic" | "deep"; explain_level?: "normal" | "easy" },
  h: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const tok = getToken();
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
    body: JSON.stringify({ explain_level: "normal", ...body }),
    signal,  // 페이지 이탈 시 abort → 연결 종료 → 백엔드 disconnect 감지 → LLM(GPU) 즉시 중단
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
        try { acc += JSON.parse(data).text; h.onChunk(acc); } catch {}
      } else if (event === "refine" && data) {
        try { acc = JSON.parse(data).text || acc; h.onRefine?.(acc); } catch {}
      } else if (event === "cut") {
        acc += " …"; h.onChunk(acc); h.onCut?.();
      } else if (event === "stage" && data) {
        try { h.onStage?.(JSON.parse(data).phase); } catch {}
      } else if (event === "done" && data) {
        try { h.onDone?.(JSON.parse(data)); } catch {}
      } else if (event === "error" && data) {
        try { throw new Error(JSON.parse(data).detail || "스트림 오류"); } catch (e) { throw e; }
      }
    }
  }
}
