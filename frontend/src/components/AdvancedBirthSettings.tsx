/** 사주 입력 '고급 설정' — 진태양시(출생지 시·군·구·균시차)·자시 관법. BirthFields와 /chat 공용. */
import { useEffect, useState } from "react";
import { KR_REGIONS, sidoByName, nearestRegion, DEFAULT_LON } from "../lib/regions";

export type AdvBirth = {
  apply_true_solar_time?: boolean;
  birth_longitude?: number | null;
  apply_equation_of_time?: boolean;
  night_zi_mode?: "yaja" | "jeongja";
};

export default function AdvancedBirthSettings({
  value,
  onChange,
}: {
  value: AdvBirth;
  onChange: (patch: Partial<AdvBirth>) => void;
}) {
  // 출생지 시·도/시·군·구 — 경도(birth_longitude)가 단일 진실값, 이름은 드롭다운 UI 상태
  const init = nearestRegion(value.birth_longitude);
  const [sido, setSido] = useState(init.sido);
  const [gun, setGun] = useState(init.gun);

  // 외부(프로필 자동채움 등)에서 경도가 바뀌면 드롭다운 동기화
  useEffect(() => {
    const cur = sidoByName(sido)?.guns.find((g) => g.name === gun);
    if (!cur || Math.abs(cur.lon - (value.birth_longitude ?? DEFAULT_LON)) > 0.005) {
      const n = nearestRegion(value.birth_longitude);
      setSido(n.sido); setGun(n.gun);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.birth_longitude]);

  const guns = sidoByName(sido)?.guns ?? [];
  // 접힌 헤더에 노출할 현재 출생지(시·도 약칭 + 시·군·구)
  const regionLabel = `${sidoByName(sido)?.short ?? ""} ${gun}`.trim();

  function pickSido(name: string) {
    const s = sidoByName(name);
    if (!s || !s.guns.length) return;
    setSido(name); setGun(s.guns[0].name);
    onChange({ birth_longitude: s.guns[0].lon });
  }
  function pickGun(name: string) {
    const g = guns.find((x) => x.name === name);
    if (!g) return;
    setGun(name);
    onChange({ birth_longitude: g.lon });
  }

  return (
    <details className="bf-adv">
      <summary className="bf-adv-summary">
        <span className="bf-adv-ico" aria-hidden>🧭</span>
        <span className="bf-adv-headtxt">
          <span className="bf-adv-title">
            진태양시 <b>위치</b> 보정
            <em className="bf-adv-diff">정밀·차별화</em>
            <span className="bf-adv-pulse" aria-hidden>!</span>
          </span>
          <span className="bf-adv-sub">
            {value.apply_true_solar_time ? (
              <>태어난 곳의 <b>경도(經度)</b>까지 반영 — 현재 <b>{regionLabel || "출생지 미설정"}</b> 기준 · 눌러서 지역 변경</>
            ) : (
              <>태어난 곳의 <b>경도(經度)</b>로 ‘시(時)’를 정밀 계산 — 눌러서 <b>태어난 지역</b>을 설정하세요</>
            )}
          </span>
        </span>
        <span className={`bf-adv-state ${value.apply_true_solar_time ? "on" : ""}`}>
          {value.apply_true_solar_time ? "✨ ON" : "꺼짐"}
        </span>
        <span className="bf-adv-chev" aria-hidden>▾</span>
      </summary>
      <div className="bf-adv-body">
        {value.apply_true_solar_time && (
          <div className="bf-adv-note">
            <b className="bf-adv-note-title">✨ 정밀 진태양시 보정 적용 중</b>
            출생지 경도·서머타임·당시 표준자오선까지 반영해 <b>‘시(時)’를 더 정확하게</b> 계산합니다.
            표준시만 쓰던 <b>옛 만세력(예: 원광)과 시가 달라 보일 수 있는데, 틀린 게 아니라 더 정밀하기 때문</b>이에요.
            <b>아래에서 태어난 지역(시·군·구)을 선택</b>하면 그 지역 경도로 더 정확해집니다. 옛 방식(표준시)으로 보려면 진태양시 보정을 끄면 됩니다.
          </div>
        )}
        <div className="bf-adv-row">
          <div className="bf-adv-label">
            진태양시 보정
            <span className="bf-adv-hint">시계 표준시를 출생지 경도 기준으로 보정. 서머타임(1948~88 일부)·당시 표준자오선(135°/127.5°E)은 자동 보정돼요 — 시(時)가 바뀔 수 있어요(표준시 만세력과 달라질 수 있음).</span>
          </div>
          <button type="button" className={`bf-chip ${value.apply_true_solar_time ? "on" : ""}`}
                  onClick={() => onChange({ apply_true_solar_time: !value.apply_true_solar_time })}>
            {value.apply_true_solar_time ? "적용 중" : "미적용"}
          </button>
        </div>
        {value.apply_true_solar_time && (
          <>
            <div className="bf-adv-row bf-adv-row-col">
              <div className="bf-adv-label">
                출생지 (시·도 → 시·군·구)
                <span className="bf-adv-hint">태어난 지역의 경도로 보정량이 정해져요. 정확히 모르면 가장 가까운 시·군·구를 고르세요.</span>
              </div>
              <div className="bf-adv-region">
                <select className="bf-input bf-adv-sel" aria-label="시·도"
                        value={sido} onChange={(e) => pickSido(e.target.value)}>
                  {KR_REGIONS.map((s) => <option key={s.name} value={s.name}>{s.short}</option>)}
                </select>
                <select className="bf-input bf-adv-sel" aria-label="시·군·구"
                        value={gun} onChange={(e) => pickGun(e.target.value)}>
                  {guns.map((g) => <option key={g.name} value={g.name}>{g.name}</option>)}
                </select>
              </div>
            </div>
            <div className="bf-adv-row">
              <div className="bf-adv-label">
                균시차(均時差) 반영
                <span className="bf-adv-hint">계절별 ±16분 오차까지 보정하는 정밀 옵션(시태양시).</span>
              </div>
              <button type="button" className={`bf-chip ${value.apply_equation_of_time ? "on" : ""}`}
                      onClick={() => onChange({ apply_equation_of_time: !value.apply_equation_of_time })}>
                {value.apply_equation_of_time ? "반영" : "미반영"}
              </button>
            </div>
          </>
        )}
        <div className="bf-adv-row">
          <div className="bf-adv-label">
            자시(子時) 관법
            <span className="bf-adv-hint">23~24시 출생 처리. 야자시=일주 당일·시주 익일천간 / 정자시=23시부터 모두 익일.</span>
          </div>
          <div className="bf-seg bf-seg-sm">
            <button type="button" className={(value.night_zi_mode ?? "yaja") === "yaja" ? "on" : ""}
                    onClick={() => onChange({ night_zi_mode: "yaja" })}>야자시</button>
            <button type="button" className={value.night_zi_mode === "jeongja" ? "on" : ""}
                    onClick={() => onChange({ night_zi_mode: "jeongja" })}>정자시</button>
          </div>
        </div>
      </div>
    </details>
  );
}
