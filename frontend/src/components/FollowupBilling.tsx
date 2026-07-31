/** 추가질문 과금바 — 기본/심화 선택 + 차감 예정·잔액 명시 (사주와 동일 정책).
 *  궁합·택일·작명/개명/아호의 추가질문 입력 위에 표시해 과금을 투명하게 안내한다.
 */
import { type MeResp } from "../api";

export default function FollowupBilling({
  me,
  depth,
  onDepth,
}: {
  me: MeResp | null;
  depth: "basic" | "deep";
  onDepth: (d: "basic" | "deep") => void;
}) {
  const basic = me?.credit_cost_basic ?? 1000;
  const deep = me?.credit_cost_deep ?? 3000;
  const cost = depth === "deep" ? deep : basic;
  const free = (me?.free_remaining ?? 0) > 0;
  const note = !me
    ? "로그인 후 추가 질문 (1일 무료 또는 크레딧 차감)"
    : free
    ? `이번 질문 무료 👍 · 남은 무료 ${me!.free_remaining}회`
    : `${depth === "deep" ? "심화" : "기본"} 질문 · ${cost.toLocaleString()}P 차감 예정 · 잔액 ${me!.balance.toLocaleString()}P`;

  return (
    <div className="followup-billing">
      <div className="fb-depth" role="radiogroup" aria-label="추가질문 등급">
        <button
          type="button"
          className={`fb-pill${depth === "basic" ? " on" : ""}`}
          onClick={() => onDepth("basic")}
        >
          기본 {basic.toLocaleString()}P
        </button>
        <button
          type="button"
          className={`fb-pill${depth === "deep" ? " on" : ""}`}
          onClick={() => onDepth("deep")}
        >
          심화 {deep.toLocaleString()}P
        </button>
      </div>
      <div className={`fb-note${free ? " free" : ""}`}>{note}</div>
    </div>
  );
}
