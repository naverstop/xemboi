/** LLM 답변의 마크다운 정리 — 화면 표시(renderRich) / 평문(stripMarkdown) 공통.
 *
 * 답변은 상담체 줄글이 원칙(백엔드 프롬프트로 마크다운 금지)이지만, 모델이 흘리거나
 * 과거에 저장된 답변에는 마크다운(헤더 #, 굵게 **, 목록 -·*, 번호 1.)이 섞여 있다.
 * 화면·PDF에 기호가 그대로 노출되면 'AI 비서' 느낌이 나므로 기호를 가린다.
 *
 * - 화면(JSX): renderRich() — `**x**`→굵게, 헤더 `### x`→굵은 줄, 불릿 `- `→`• `, 기호 숨김
 * - 평문(복사/공유/PDF): stripMarkdown() — 위 기호를 제거해 자연스러운 줄글로
 *
 * 줄 단위로 처리하고 개행은 보존한다(컨테이너 white-space:pre-wrap).
 */
import { createElement, type ReactNode } from "react";

const BOLD_RE = /\*\*([^\n*]+?)\*\*/g;       // **굵게**
const ITALIC_RE = /\*([^*\n]+?)\*/g;          // *강조* (** 제거 후 잔여)
// [실측 2026-07-28] '####9월'처럼 # 뒤 공백이 없으면 종전 `[ \t]+`(공백 필수)가 미매칭 →
// 마커가 그대로 노출되고 헤더 굵게도 안 먹었다. 공백을 선택(`[ \t]*`)으로 바꿔 공백 유무 무관하게
// 헤더로 인식한다(전 메뉴·과거 저장분까지 display·복사·PDF 즉시 복구).
const HEADER_RE = /^[ \t]*#{1,6}[ \t]*/;      // 줄머리 #~###### 헤더 마커(뒤 공백 유무 무관)
const BULLET_RE = /^([ \t]*)[-*+•][ \t]+/;    // 줄머리 - * + • 불릿(들여쓰기 보존)
// [2026-07-28] 순수 수평 구분선(--- *** ___) 제거. 약모델이 규칙 위반으로 흘리고, 스트리밍 라이브
// 화면엔 백엔드 _tidy_markdown 결과가 안 실려 '---'가 남던 문제(운영자 지적)를 프론트 표시단에서도
// 결정적으로 차단(화면·복사·PDF 공통). 백엔드 _HR_LINE_RE 와 동일 규칙. 표 구분선 '|---|'은 '|' 가
// 있어 미매칭(내용 보존), 문장 내 하이픈 '2020-2021'도 순수 구분선 아님 → 미매칭.
const HR_LINE_RE = /^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const BOLD_STYLE = { fontWeight: 700, fontSize: "calc(1em + 1pt)" } as const;

/** 순수 구분선(--- *** ___) 줄을 지우고 과다 빈줄을 축약(백엔드 _tidy_markdown 미러). 내용은 무손실. */
function dropHrLines(text: string): string {
  return text
    .split("\n")
    .map((l) => (HR_LINE_RE.test(l) ? "" : l))   // HR줄 → 빈 줄(내용 글자만 제거)
    .join("\n")
    .replace(/\n{3,}/g, "\n\n");                  // 3줄+ 빈줄 → 2줄
}

export type RichOpts = {
  /** 이 구절들을 <strong class="rich-em">로 자동 강조(예: 타로 카드명·방향·포지션명). */
  highlight?: string[];
};

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
/** 긴 구절 우선(부분 겹침 방지) 하나의 매칭 정규식으로 결합. 없으면 null. */
function buildHighlightRe(phrases?: string[]): RegExp | null {
  if (!phrases || phrases.length === 0) return null;
  const uniq = [...new Set(phrases.map((p) => (p || "").trim()).filter((p) => p.length >= 1))]
    .sort((a, b) => b.length - a.length);
  if (uniq.length === 0) return null;
  return new RegExp("(" + uniq.map(escapeRe).join("|") + ")", "g");
}
/** 평문 조각을 out에 push하되, hlRe 매칭 구절은 금색 강조(rich-em)로 감싼다. */
function pushPlain(out: ReactNode[], s: string, key: { n: number }, hlRe: RegExp | null): void {
  if (!s) return;
  if (!hlRe) { out.push(s); return; }
  hlRe.lastIndex = 0;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = hlRe.exec(s)) !== null) {
    if (m.index > last) out.push(s.slice(last, m.index));
    out.push(createElement("strong", { key: key.n++, className: "rich-em" }, m[0]));
    last = m.index + m[0].length;
    if (m.index === hlRe.lastIndex) hlRe.lastIndex++;  // zero-length 방어
  }
  if (last < s.length) out.push(s.slice(last));
}

/** s 안의 `**굵게**` 를 <strong>로, 나머지 평문은 pushPlain(강조 옵션 적용)으로 push. */
function pushInline(out: ReactNode[], s: string, key: { n: number }, hlRe: RegExp | null): void {
  BOLD_RE.lastIndex = 0;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = BOLD_RE.exec(s)) !== null) {
    if (m.index > last) pushPlain(out, s.slice(last, m.index), key, hlRe);
    out.push(createElement("strong", { key: key.n++, style: BOLD_STYLE }, m[1]));
    last = m.index + m[0].length;
  }
  if (last < s.length) pushPlain(out, s.slice(last), key, hlRe);
}

/** 화면 표시용: 굵게/헤더/불릿을 렌더하고 마크다운 기호는 숨긴다. pre-wrap으로 개행 보존.
 *  opts.highlight 를 주면(타로) 해당 구절을 금색 강조 — 백엔드가 평문화해도 화면 강조 유지(항목5). */
export function renderRich(text: string, opts?: RichOpts): ReactNode {
  if (!text) return text;
  const hlRe = buildHighlightRe(opts?.highlight);
  const out: ReactNode[] = [];
  const key = { n: 0 };
  const lines = dropHrLines(text).split("\n");
  lines.forEach((line, li) => {
    if (li > 0) out.push("\n");
    const hm = line.match(HEADER_RE);
    if (hm) {
      // 헤더 → 굵은 줄(마커·내부 ** 숨김)
      out.push(createElement("strong", { key: key.n++, style: BOLD_STYLE },
        line.slice(hm[0].length).replace(BOLD_RE, "$1")));
      return;
    }
    const bm = line.match(BULLET_RE);
    if (bm) {
      out.push(`${bm[1]}• `);
      pushInline(out, line.slice(bm[0].length), key, hlRe);
    } else {
      pushInline(out, line, key, hlRe);
    }
  });
  return out;
}

/** 평문(복사/공유/PDF)용: 마크다운 기호 제거 → 자연스러운 줄글. */
export function stripMarkdown(text: string): string {
  if (!text) return text;
  return dropHrLines(text)
    .split("\n")
    .map((line) => {
      const noHeader = line.replace(HEADER_RE, "");          // ### 마커 제거
      const bm = noHeader.match(BULLET_RE);
      return bm ? `${bm[1]}• ${noHeader.slice(bm[0].length)}` : noHeader;  // 불릿 → •
    })
    .join("\n")
    .replace(BOLD_RE, "$1")     // **굵게** → 굵게
    .replace(ITALIC_RE, "$1");  // *강조* → 강조
}
