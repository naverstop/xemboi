/** 오행 균형 펜타곤(작명·개명, 2026-07-27 운영자 지시).
 *  빨강 = 현재 사주 오행(팔자8), 파랑 = 이 이름을 쓰면 보완된 모습(사주 + 이름 자원오행).
 *  부족 오행을 이름이 채워 '빨강→파랑'으로 조화로워지는 걸 한눈에 보여준다.
 *  인라인 SVG(외부 의존 0). 기존 SajuChart TraitRadar 와 같은 오각 수학.
 */
const AXES = ["목", "화", "토", "금", "수"] as const;
type WX = Record<string, number>;

export default function OhaengRadar({
  saju, add, deficient, compLabel = "이름 보완 후",
}: {
  saju: WX;                 // 사주 팔자8 오행 개수 {목,화,토,금,수}
  add?: WX;                 // 이름이 더하는 자원오행 개수(보완). 없으면 빨강만
  deficient?: string[];     // 부족 오행(축 라벨 강조)
  compLabel?: string;       // 파랑 범례 라벨(작명='이름 보완 후' / 개명='현재 이름 반영')
}) {
  const cx = 100, cy = 96, R = 62, n = 5;
  const ang = (i: number) => ((-90 + (360 / n) * i) * Math.PI) / 180;
  const pt = (i: number, r: number): [number, number] => [cx + Math.cos(ang(i)) * r, cy + Math.sin(ang(i)) * r];
  const ring = (r: number) => AXES.map((_, i) => pt(i, r).join(",")).join(" ");

  const sajuV = AXES.map((k) => saju[k] || 0);
  const compV = AXES.map((k) => (saju[k] || 0) + (add?.[k] || 0));
  // 스케일: 두 폴리곤 중 최댓값 기준(최소 3칸 확보 — 납작해 보이지 않게)
  const maxV = Math.max(3, ...compV);
  const polyOf = (vals: number[]) => vals.map((v, i) => pt(i, (R * v) / maxV).join(",")).join(" ");
  const defSet = new Set(deficient || []);

  return (
    <div className="ohaeng-radar">
      <svg viewBox="0 0 200 200" role="img" aria-label="오행 균형 오각 차트">
        {[0.25, 0.5, 0.75, 1].map((f) => <polygon key={f} className="or-ring" points={ring(R * f)} />)}
        {AXES.map((_, i) => { const [x, y] = pt(i, R); return <line key={i} className="or-axis" x1={cx} y1={cy} x2={x} y2={y} />; })}
        {/* 파랑(보완 후) 먼저, 그 위에 빨강(사주) — 겹침이 보이게 */}
        {add && <polygon className="or-comp" points={polyOf(compV)} />}
        <polygon className="or-saju" points={polyOf(sajuV)} />
        {AXES.map((k, i) => {
          const [lx, ly] = pt(i, R + 16);
          const cur = saju[k] || 0, aft = cur + (add?.[k] || 0);
          return (
            <text key={k} className={`or-label${defSet.has(k) ? " def" : ""}`} x={lx} y={ly} textAnchor="middle">
              {k}
              <tspan className="or-num" x={lx} dy="13">
                {aft > cur ? `${cur}→${aft}` : `${cur}`}
              </tspan>
            </text>
          );
        })}
      </svg>
      <div className="or-legend">
        <span className="ol-item"><i className="ol-dot saju" /> 현재 사주</span>
        {add && <span className="ol-item"><i className="ol-dot comp" /> {compLabel}</span>}
      </div>
    </div>
  );
}
