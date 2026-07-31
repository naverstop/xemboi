/** 「종합 감정서」 버튼 — 상담 전체(초기 풀이 + 여러 추가질문)를 로컬 LLM이 하나의
 *  매끄러운 글로 재구성한 PDF를 생성한다. 연속 질문으로 단편화된 답변을 하나로 묶어준다.
 *  build()가 null이면 비활성(상담 내용 없음).
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";

export type ReportReq = {
  doc_title: string;
  person_line?: string;
  item?: string;
  conversation: { role: string; content: string }[];
  topic?: string;
  session_id?: string;   // 사주 세션 — 있으면 명식 패널 포함
};

export default function ConsultationReportButton({ build }: { build: () => ReportReq | null }) {
  const { t: tr } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");   // 생성 완료 시 세팅 → '열기' 링크 노출(팝업차단 대비·재생성 방지)

  async function onClick() {
    if (busy) return;                   // 연타 방지: 생성 중엔 재요청 차단(LLM 중복 생성 방지)
    const req = build();
    if (!req || req.conversation.length === 0) return;
    setBusy(true);
    setUrl("");                         // 새로 만들면 직전 링크 무효화(대화가 늘었을 수 있음)
    // 진행/열람은 하단 공통 dock에서. 감정서는 LLM 재구성이라 수십 초 걸림 → 인디터미네이트+경과초로
    // "만드는 중"을 확실히 알려 사용자가 멈춘 줄 알고 다시 누르는 걸 막는다. 완료 시 dock '열기' 버튼.
    const id = `report-${Date.now()}`;
    window.dispatchEvent(new CustomEvent("saju:gen-start", { detail: { id, kind: "report" } }));
    try {
      const r = await api.generateReport(req);
      setUrl(r.url);                    // 인라인 '감정서 열기' 링크(dock 닫아도 접근 가능한 폴백)
      window.dispatchEvent(new CustomEvent("saju:gen-done", { detail: { id, url: r.url, filename: r.filename } }));
    } catch {
      window.dispatchEvent(new CustomEvent("saju:gen-error", {
        detail: { id, message: tr("consult.rb_error") },
      }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="report-wrap">
      <button className="report-btn" onClick={onClick} disabled={busy} title={tr("consult.rb_title")}>
        {busy ? tr("consult.rb_busy") : url ? tr("consult.rb_remake") : tr("consult.rb_make")}
      </button>
      {url && !busy && (
        // 생성된 감정서 열기(실제 링크=사용자 제스처라 팝업차단 없음, API 재호출 없음)
        <a className="report-btn report-open" href={url} target="_blank" rel="noopener noreferrer"
           style={{ marginLeft: 8 }} title={tr("consult.rb_open_title")}>
          {tr("consult.rb_open")}
        </a>
      )}
    </span>
  );
}
