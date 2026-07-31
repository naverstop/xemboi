/** 프리미엄 사주 입력 — 빠른입력 + 날짜/시각 + 성별·양음력 세그먼트 토글. 전 메뉴 공용. */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import AdvancedBirthSettings from "./AdvancedBirthSettings";
import TimeSelect from "./TimeSelect";
import { DEFAULT_BIRTH_TIME } from "../lib/birthTime";

export type BirthValue = {
  birth_date: string;
  birth_time: string;
  unknown_time: boolean;
  gender: "male" | "female";
  calendar: "solar" | "lunar";
  is_leap_month: boolean;
  apply_true_solar_time?: boolean;
  birth_longitude?: number | null;
  apply_equation_of_time?: boolean;
  night_zi_mode?: "yaja" | "jeongja";
};

// 저장된 사주 프로필(Birth형) → BirthValue 부분값 (자동 채움용)
export function profileToBirthValue(p: any): Partial<BirthValue> {
  if (!p || !p.birth_date) return {};
  const out: Partial<BirthValue> = {
    birth_date: p.birth_date,
    calendar: p.calendar === "lunar" ? "lunar" : "solar",
    gender: p.gender === "female" ? "female" : "male",
    is_leap_month: !!p.is_leap_month,
  };
  if (p.birth_time) { out.birth_time = p.birth_time; out.unknown_time = false; }
  else { out.birth_time = ""; out.unknown_time = true; }
  if (typeof p.apply_true_solar_time === "boolean") out.apply_true_solar_time = p.apply_true_solar_time;
  if (p.birth_longitude != null) out.birth_longitude = p.birth_longitude;
  if (typeof p.apply_equation_of_time === "boolean") out.apply_equation_of_time = p.apply_equation_of_time;
  if (p.night_zi_mode) out.night_zi_mode = p.night_zi_mode;
  return out;
}

export default function BirthFields({
  value,
  onChange,
  showGender = true,
}: {
  value: BirthValue;
  onChange: (patch: Partial<BirthValue>) => void;
  showGender?: boolean;
}) {
  const { t: tr } = useTranslation();
  const [quick, setQuick] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const [dateText, setDateText] = useState(value.birth_date || "");
  const dateRef = useRef<HTMLInputElement>(null);

  // 외부에서 birth_date가 바뀌면(빠른입력·달력선택) 텍스트칸 동기화
  useEffect(() => { setDateText(value.birth_date || ""); }, [value.birth_date]);

  // 생년월일 직접 타이핑 — 숫자만 받아 YYYY-MM-DD로 자동 포맷, 8자리 완성 시 반영
  function typeDate(raw: string) {
    const dig = raw.replace(/\D/g, "").slice(0, 8);
    let f = dig;
    if (dig.length > 6) f = `${dig.slice(0, 4)}-${dig.slice(4, 6)}-${dig.slice(6)}`;
    else if (dig.length > 4) f = `${dig.slice(0, 4)}-${dig.slice(4)}`;
    setDateText(f);
    if (dig.length === 8) {
      const y = +dig.slice(0, 4), mo = +dig.slice(4, 6), da = +dig.slice(6, 8);
      if (y >= 1900 && y <= 2100 && mo >= 1 && mo <= 12 && da >= 1 && da <= 31) {
        onChange({ birth_date: `${dig.slice(0, 4)}-${dig.slice(4, 6)}-${dig.slice(6, 8)}` });
      }
    } else if (dig.length === 0) {
      onChange({ birth_date: "" });
    }
  }

  function parseQuick(raw: string) {
    setQuick(raw);
    const d = raw.replace(/\D/g, "");
    if (d.length === 0) { setInfo(null); return; }
    if (d.length !== 8 && d.length !== 10 && d.length !== 12) {
      setInfo(tr("chat.q_len")); return;
    }
    const y = d.slice(0, 4), mo = d.slice(4, 6), da = d.slice(6, 8);
    const yi = +y, moi = +mo, dai = +da;
    if (yi < 1900 || yi > 2100 || moi < 1 || moi > 12 || dai < 1 || dai > 31) {
      setInfo(tr("chat.q_date_bad")); return;
    }
    const patch: Partial<BirthValue> = { birth_date: `${y}-${mo}-${da}` };
    let timeLabel = "";
    if (d.length >= 10) {
      const hh = d.slice(8, 10);
      const mm = d.length >= 12 ? d.slice(10, 12) : "00";
      if (+hh <= 23 && +mm <= 59) { patch.birth_time = `${hh}:${mm}`; patch.unknown_time = false; timeLabel = ` ${hh}:${mm}`; }
      else { setInfo(tr("chat.q_time_bad")); return; }
    } else if (!value.unknown_time && !(value.birth_time || "").trim()) {
      // 시각 미입력 → 자동으로 00:30 채워 매끄럽게 진행('시 모름'이면 제외 유지)
      patch.birth_time = DEFAULT_BIRTH_TIME; patch.unknown_time = false; timeLabel = ` ${DEFAULT_BIRTH_TIME}`;
    }
    onChange(patch);
    setInfo(tr("chat.q_ok", { y: yi, mo: moi, da: dai, time: timeLabel }));
  }

  return (
    <div className="birth-card">
      {/* 빠른 입력 (강조) */}
      <div className="bf-quick">
        <div className="bf-quick-top">
          <span className="bf-quick-label">{tr("chat.quick_label")}</span>
          <span className="bf-quick-sub">{tr("chat.quick_sub")}</span>
        </div>
        <div className="bf-quick-row">
          <input
            className="bf-quick-input" type="text" inputMode="numeric" maxLength={14}
            placeholder={tr("chat.quick_ph")}
            value={quick} onChange={(e) => parseQuick(e.target.value)}
          />
          <button type="button" className="bf-quick-btn" onClick={() => parseQuick(quick)}>{tr("chat.apply")}</button>
        </div>
        <div className={`bf-quick-hint${info && info.startsWith("✓") ? " ok" : info ? " warn" : ""}`}>
          {info || tr("chat.quick_hint")}
        </div>
      </div>

      <div className="bf-or"><span>{tr("chat.or_manual")}</span></div>

      {/* 직접 입력 */}
      <div className="bf-grid">
        <div className="bf-field bf-field-wide">
          <label>{tr("chat.f_birth")}</label>
          <div className="bf-datebox">
            <input className="bf-input" type="text" inputMode="numeric" maxLength={10}
                   placeholder={tr("chat.birth_ph")} value={dateText}
                   onChange={(e) => typeDate(e.target.value)} />
            <button type="button" className="bf-cal-btn" title={tr("chat.cal_title")}
                    onClick={() => { const el = dateRef.current; if (!el) return; (el as any).showPicker ? (el as any).showPicker() : el.focus(); }}>📅</button>
            {/* 달력 팝업 전용(시각적 숨김) — 버튼으로 호출, 선택값은 birth_date로 반영 */}
            <input ref={dateRef} type="date" className="bf-date-native" tabIndex={-1} aria-hidden
                   value={value.birth_date} onChange={(e) => onChange({ birth_date: e.target.value })} />
          </div>
        </div>
        <div className="bf-field bf-field-wide">
          <label>{tr("chat.f_time")}</label>
          <div className="bf-time">
            <TimeSelect value={value.birth_time} disabled={value.unknown_time}
                        onChange={(v) => onChange({ birth_time: v })} />
            <button type="button" className={`bf-chip ${value.unknown_time ? "on" : ""}`}
                    onClick={() => onChange({ unknown_time: !value.unknown_time })}>{tr("chat.unknown_time")}</button>
          </div>
          <div className="bf-time-hint" style={{ fontSize: 12, color: "#8a8f98", marginTop: 4 }}>
            {value.unknown_time ? tr("chat.time_hint_unknown") : tr("chat.time_hint_default")}
          </div>
        </div>
        {showGender && (
          <div className="bf-field">
            <label>{tr("chat.f_gender")}</label>
            <div className="bf-seg">
              <button type="button" className={value.gender === "male" ? "on" : ""} onClick={() => onChange({ gender: "male" })}>{tr("chat.male")}</button>
              <button type="button" className={value.gender === "female" ? "on" : ""} onClick={() => onChange({ gender: "female" })}>{tr("chat.female")}</button>
            </div>
          </div>
        )}
        <div className="bf-field">
          <label>{tr("chat.f_calendar")}</label>
          <div className="bf-cal-row">
            <div className="bf-seg">
              <button type="button" className={value.calendar === "solar" ? "on" : ""} onClick={() => onChange({ calendar: "solar", is_leap_month: false })}>{tr("chat.solar")}</button>
              <button type="button" className={value.calendar === "lunar" ? "on" : ""} onClick={() => onChange({ calendar: "lunar" })}>{tr("chat.lunar")}</button>
            </div>
            {value.calendar === "lunar" && (
              <button type="button" className={`bf-chip ${value.is_leap_month ? "on" : ""}`}
                      onClick={() => onChange({ is_leap_month: !value.is_leap_month })}>{tr("birth.leap")}</button>
            )}
          </div>
        </div>
      </div>

      <AdvancedBirthSettings value={value} onChange={onChange} />
    </div>
  );
}
