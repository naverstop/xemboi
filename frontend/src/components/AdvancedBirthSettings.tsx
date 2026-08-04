/** 사주 입력 '고급 설정' — 진태양시(출생지 시·군·구·균시차)·자시 관법. BirthFields와 /chat 공용. */
import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { REGIONS, sidoByName, nearestRegion, DEFAULT_LON } from "../lib/regions";

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
  const { t: tr } = useTranslation();
  // 출생지 지역 — 경도(birth_longitude)가 단일 진실값, 이름은 드롭다운 UI 상태
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
            <Trans i18nKey="adv.title" components={{ b: <b /> }} />
            <em className="bf-adv-diff">{tr("adv.diff_badge")}</em>
            <span className="bf-adv-pulse" aria-hidden>!</span>
          </span>
          <span className="bf-adv-sub">
            {value.apply_true_solar_time ? (
              <Trans i18nKey="adv.sub_on" values={{ region: regionLabel || tr("adv.region_unset") }} components={{ b: <b /> }} />
            ) : (
              <Trans i18nKey="adv.sub_off" components={{ b: <b /> }} />
            )}
          </span>
        </span>
        <span className={`bf-adv-state ${value.apply_true_solar_time ? "on" : ""}`}>
          {value.apply_true_solar_time ? tr("adv.state_on") : tr("adv.state_off")}
        </span>
        <span className="bf-adv-chev" aria-hidden>▾</span>
      </summary>
      <div className="bf-adv-body">
        {value.apply_true_solar_time && (
          <div className="bf-adv-note">
            <b className="bf-adv-note-title">{tr("adv.note_title")}</b>
            {" "}<Trans i18nKey="adv.note_body" components={{ b: <b /> }} />
          </div>
        )}
        <div className="bf-adv-row">
          <div className="bf-adv-label">
            {tr("adv.row_label")}
            <span className="bf-adv-hint">{tr("adv.row_hint")}</span>
          </div>
          <button type="button" className={`bf-chip ${value.apply_true_solar_time ? "on" : ""}`}
                  onClick={() => onChange({ apply_true_solar_time: !value.apply_true_solar_time })}>
            {value.apply_true_solar_time ? tr("adv.toggle_on") : tr("adv.toggle_off")}
          </button>
        </div>
        {value.apply_true_solar_time && (
          <>
            <div className="bf-adv-row bf-adv-row-col">
              <div className="bf-adv-label">
                {tr("adv.region_label")}
                <span className="bf-adv-hint">{tr("adv.region_hint")}</span>
              </div>
              <div className="bf-adv-region">
                <select className="bf-input bf-adv-sel" aria-label={tr("adv.sido_aria")}
                        value={sido} onChange={(e) => pickSido(e.target.value)}>
                  {REGIONS.map((s) => <option key={s.name} value={s.name}>{s.short}</option>)}
                </select>
                <select className="bf-input bf-adv-sel" aria-label={tr("adv.gun_aria")}
                        value={gun} onChange={(e) => pickGun(e.target.value)}>
                  {guns.map((g) => <option key={g.name} value={g.name}>{g.name}</option>)}
                </select>
              </div>
            </div>
            <div className="bf-adv-row">
              <div className="bf-adv-label">
                {tr("adv.eot_label")}
                <span className="bf-adv-hint">{tr("adv.eot_hint")}</span>
              </div>
              <button type="button" className={`bf-chip ${value.apply_equation_of_time ? "on" : ""}`}
                      onClick={() => onChange({ apply_equation_of_time: !value.apply_equation_of_time })}>
                {value.apply_equation_of_time ? tr("adv.eot_on") : tr("adv.eot_off")}
              </button>
            </div>
          </>
        )}
        <div className="bf-adv-row">
          <div className="bf-adv-label">
            {tr("adv.zi_label")}
            <span className="bf-adv-hint">{tr("adv.zi_hint")}</span>
          </div>
          <div className="bf-seg bf-seg-sm">
            <button type="button" className={(value.night_zi_mode ?? "yaja") === "yaja" ? "on" : ""}
                    onClick={() => onChange({ night_zi_mode: "yaja" })}>{tr("adv.zi_yaja")}</button>
            <button type="button" className={value.night_zi_mode === "jeongja" ? "on" : ""}
                    onClick={() => onChange({ night_zi_mode: "jeongja" })}>{tr("adv.zi_jeongja")}</button>
          </div>
        </div>
      </div>
    </details>
  );
}
