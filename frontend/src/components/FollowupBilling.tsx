/** 추가질문 과금바 — 기본/심화 선택 + '차감' 강조 배지. 전 메뉴 공통(운영자 지적: 매출 직결이라
 *  차감이 눈에 분명히 보여야 하고, 기본/심화 버튼 UI가 전 메뉴 동일해야 한다).
 *  사용처: 사주상담(ChatPage)·궁합·택일·작명/개명/아호·오늘의운세·해몽·부적·달력·신년운세·타로.
 *
 *  ⚠️ [버그 2026-07-23] free_remaining>0 이면 "무료"라고 띄웠다가, 입장료를 낸 tool 메뉴는 추가질문이
 *     항상 차감돼(allow_free_quota=False) 1,900P 를 차감당했다. 그래서 이 컴포넌트는 free_remaining 을
 *     **스스로 참조하지 않는다.** 무료 상태는 호출부가 판단해 freeNote 로 넘긴다(사주상담만 일일무료 있음).
 *
 *  ⚠️ 플러스 패스 %할인은 반영(서버와 동일 반올림): cost = round(정가 × (100-할인)/100).
 */
import { useTranslation, Trans } from "react-i18next";
import { type MeResp } from "../api";
import { fmtNum } from "../lib/money";

export default function FollowupBilling({
  me,
  depth,
  onDepth,
  freeNote,
}: {
  me: MeResp | null;
  depth: "basic" | "deep";
  onDepth: (d: "basic" | "deep") => void;
  /** 무료/무과금 안내(사주상담 일일무료·관리자·연간회원 등). 주어지면 초록 '무료' 배지, null/undefined 면
   *  '차감' 배지. 유료 차감 상태에서는 넘기지 않는다(호출부가 판단). */
  freeNote?: string | null;
}) {
  const { t: tr } = useTranslation();
  const disc = me?.active_pass?.tier === "plus" ? (me?.pass_followup_discount_pct ?? 0) : 0;
  const applyDisc = (p: number) => (disc > 0 ? Math.max(0, Math.round((p * (100 - disc)) / 100)) : p);
  const basic = applyDisc(me?.credit_cost_basic ?? 19000);
  const deep = applyDisc(me?.credit_cost_deep ?? 29000);
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
          role="radio"
          aria-checked={depth === "basic"}
          className={`fb-pill${depth === "basic" ? " on" : ""}`}
          onClick={() => onDepth("basic")}
        >
          {tr("chat.depth_basic")} {fmtNum(basic)}{tr("pay.pt")}
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={depth === "deep"}
          className={`fb-pill${depth === "deep" ? " on" : ""}`}
          onClick={() => onDepth("deep")}
        >
          {tr("chat.depth_deep")} {fmtNum(deep)}{tr("pay.pt")}
        </button>
      </div>

      {/* 차감 배지 — 매출 직결. 회색 작은 글씨가 아니라 눈에 분명히 보이는 색상 배지로. */}
      {!me ? (
        <div className="fb-charge guest">🔒 {tr("explain.fb_locked")}</div>
      ) : freeNote ? (
        <div className="fb-charge free">🆓 {freeNote}</div>
      ) : (
        <div className="fb-charge" aria-live="polite">
          <span className="fb-charge-ic" aria-hidden>💳</span>
          <span className="fb-charge-main">
            <Trans
              i18nKey="explain.fb_charge"
              values={{ level: depth === "deep" ? tr("chat.lvl_deep") : tr("chat.lvl_basic"), cost: fmtNum(cost) }}
              components={{ b: <b /> }}
            />
          </span>
          {disc > 0 && <span className="fb-charge-tag">{tr("explain.fb_disc", { pct: disc })}</span>}
          <span className="fb-charge-bal">{tr("pay.bal_only", { bal: fmtNum(me.balance) })}</span>
        </div>
      )}
    </div>
  );
}
