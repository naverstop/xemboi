/** 남은 무료 공유 횟수 표시 (운영자 지시 2026-07-23).
 *
 *  배경: 공유 한도가 실제로 걸리도록 고친 뒤(사전 확인 → 공유 → 성공 시 집계) 사용자가 소진을
 *  '막히고 나서야' 알게 되는 문제가 남았다. 예전엔 한도가 사실상 무력해서 드러나지 않던 문제다.
 *  공유가 일어나는 지점마다 잔여와 **다음 초기화 날짜**를 함께 보여준다
 *  (주기가 달력 월이 아니라 사용자별 30일 롤링이라, 날짜를 안 보여주면 언제 돌아오는지 알 수 없다).
 *
 *  · 비로그인·조회 실패 → 아무것도 그리지 않는다(공유 흐름을 방해하지 않는다)
 *  · 관리자(unlimited)   → '무제한'
 *  집계 직후 갱신은 window 이벤트 'saju:share-counted' 로 받는다(ProgressDock 의 이벤트 방식과 동일).
 */
import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api } from "../api";

type Q = {
  used: number; limit: number; remaining: number; unlimited: boolean;
  period_days?: number; period_start?: string | null;
};

/** 다음 초기화 날짜(M/D). 서버 period_start 는 naive UTC 라 'Z' 를 붙여 해석한다. */
function nextResetLabel(q: Q): string | null {
  if (!q.period_start || !q.period_days) return null;
  const t = Date.parse(q.period_start.endsWith("Z") ? q.period_start : q.period_start + "Z");
  if (Number.isNaN(t)) return null;
  const d = new Date(t + q.period_days * 86400_000);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function ShareQuotaNote({ className }: { className?: string }) {
  const { t: tr } = useTranslation();
  const [q, setQ] = useState<Q | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => {
      api.shareQuota()
        .then((r) => { if (alive) setQ(r); })
        .catch(() => { if (alive) setQ(null); });   // 비로그인·장애 → 표시 생략
    };
    load();
    window.addEventListener("saju:share-counted", load);
    return () => { alive = false; window.removeEventListener("saju:share-counted", load); };
  }, []);

  if (!q) return null;
  const cls = className ?? "share-quota-note";
  if (q.unlimited) return <div className={cls}>{tr("answer.quota_unlimited")}</div>;

  const reset = nextResetLabel(q);
  const out = q.remaining <= 0;
  return (
    <div className={`${cls}${out ? " is-out" : ""}`}>
      {out
        ? <>{tr("answer.quota_out")}</>
        : <Trans i18nKey="answer.quota_left" values={{ n: q.remaining, limit: q.limit }} components={{ b: <b />, of: <span className="sqn-of" /> }} />}
      {reset && <span className="sqn-reset">{tr("answer.quota_reset", { date: reset })}</span>}
    </div>
  );
}
