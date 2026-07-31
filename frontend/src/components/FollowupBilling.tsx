/** 추가질문 과금바 — 기본/심화 선택 + 차감 예정·잔액 명시 (사주와 동일 정책).
 *  궁합·택일·작명/개명/아호의 추가질문 입력 위에 표시해 과금을 투명하게 안내한다.
 */
import { useTranslation } from "react-i18next";
import { type MeResp } from "../api";
import { fmtNum } from "../lib/money";

export default function FollowupBilling({
  me,
  depth,
  onDepth,
}: {
  me: MeResp | null;
  depth: "basic" | "deep";
  onDepth: (d: "basic" | "deep") => void;
}) {
  const { t: tr } = useTranslation();
  const basic = me?.credit_cost_basic ?? 19000;
  const deep = me?.credit_cost_deep ?? 29000;
  const cost = depth === "deep" ? deep : basic;
  const free = (me?.free_remaining ?? 0) > 0;
  const note = !me
    ? tr("explain.fb_guest")
    : free
    ? tr("explain.fb_free", { rem: fmtNum(me!.free_remaining ?? 0) })
    : tr("explain.fb_paid", {
        level: depth === "deep" ? tr("chat.lvl_deep") : tr("chat.lvl_basic"),
        cost: fmtNum(cost),
        bal: fmtNum(me!.balance),
      });

  return (
    <div className="followup-billing">
      <div className="fb-depth" role="radiogroup" aria-label={tr("explain.fb_depth_aria")}>
        <button
          type="button"
          className={`fb-pill${depth === "basic" ? " on" : ""}`}
          onClick={() => onDepth("basic")}
        >
          {tr("chat.depth_basic")} {fmtNum(basic)}{tr("pay.pt")}
        </button>
        <button
          type="button"
          className={`fb-pill${depth === "deep" ? " on" : ""}`}
          onClick={() => onDepth("deep")}
        >
          {tr("chat.depth_deep")} {fmtNum(deep)}{tr("pay.pt")}
        </button>
      </div>
      <div className={`fb-note${free ? " free" : ""}`}>{note}</div>
    </div>
  );
}
