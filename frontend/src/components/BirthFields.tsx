/** 프리미엄 사주 입력 — 빠른입력 + 날짜/시각 + 성별·양음력 세그먼트 토글. 전 메뉴 공용. */
import { useEffect, useRef, useState } from "react";
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
      setInfo("8자리(생년월일) 또는 12자리(생년월일+시분)를 입력해 주세요."); return;
    }
    const y = d.slice(0, 4), mo = d.slice(4, 6), da = d.slice(6, 8);
    const yi = +y, moi = +mo, dai = +da;
    if (yi < 1900 || yi > 2100 || moi < 1 || moi > 12 || dai < 1 || dai > 31) {
      setInfo("생년월일 숫자를 다시 확인해 주세요."); return;
    }
    const patch: Partial<BirthValue> = { birth_date: `${y}-${mo}-${da}` };
    let timeLabel = "";
    if (d.length >= 10) {
      const hh = d.slice(8, 10);
      const mm = d.length >= 12 ? d.slice(10, 12) : "00";
      if (+hh <= 23 && +mm <= 59) { patch.birth_time = `${hh}:${mm}`; patch.unknown_time = false; timeLabel = ` ${hh}:${mm}`; }
      else { setInfo("시각(시·분) 숫자를 다시 확인해 주세요."); return; }
    } else if (!value.unknown_time && !(value.birth_time || "").trim()) {
      // 시각 미입력 → 자동으로 00:30 채워 매끄럽게 진행('시 모름'이면 제외 유지)
      patch.birth_time = DEFAULT_BIRTH_TIME; patch.unknown_time = false; timeLabel = ` ${DEFAULT_BIRTH_TIME}`;
    }
    onChange(patch);
    setInfo(`✓ ${yi}년 ${moi}월 ${dai}일${timeLabel} 자동 입력됨`);
  }

  return (
    <div className="birth-card">
      {/* 빠른 입력 (강조) */}
      <div className="bf-quick">
        <div className="bf-quick-top">
          <span className="bf-quick-label">⚡ 빠른 입력</span>
          <span className="bf-quick-sub">숫자만 입력하면 자동 완성</span>
        </div>
        <div className="bf-quick-row">
          <input
            className="bf-quick-input" type="text" inputMode="numeric" maxLength={14}
            placeholder="예: 197503210430"
            value={quick} onChange={(e) => parseQuick(e.target.value)}
          />
          <button type="button" className="bf-quick-btn" onClick={() => parseQuick(quick)}>적용</button>
        </div>
        <div className={`bf-quick-hint${info && info.startsWith("✓") ? " ok" : info ? " warn" : ""}`}>
          {info || "8자리(YYYYMMDD) 또는 12자리(YYYYMMDDHHMM)"}
        </div>
      </div>

      <div className="bf-or"><span>또는 직접 입력</span></div>

      {/* 직접 입력 */}
      <div className="bf-grid">
        <div className="bf-field bf-field-wide">
          <label>📅 생년월일</label>
          <div className="bf-datebox">
            <input className="bf-input" type="text" inputMode="numeric" maxLength={10}
                   placeholder="예: 1975-03-21 (직접 입력)" value={dateText}
                   onChange={(e) => typeDate(e.target.value)} />
            <button type="button" className="bf-cal-btn" title="달력에서 선택"
                    onClick={() => { const el = dateRef.current; if (!el) return; (el as any).showPicker ? (el as any).showPicker() : el.focus(); }}>📅</button>
            {/* 달력 팝업 전용(시각적 숨김) — 버튼으로 호출, 선택값은 birth_date로 반영 */}
            <input ref={dateRef} type="date" className="bf-date-native" tabIndex={-1} aria-hidden
                   value={value.birth_date} onChange={(e) => onChange({ birth_date: e.target.value })} />
          </div>
        </div>
        <div className="bf-field bf-field-wide">
          <label>🕐 태어난 시각</label>
          <div className="bf-time">
            <TimeSelect value={value.birth_time} disabled={value.unknown_time}
                        onChange={(v) => onChange({ birth_time: v })} />
            <button type="button" className={`bf-chip ${value.unknown_time ? "on" : ""}`}
                    onClick={() => onChange({ unknown_time: !value.unknown_time })}>시 모름</button>
          </div>
          <div className="bf-time-hint" style={{ fontSize: 12, color: "#8a8f98", marginTop: 4 }}>
            {value.unknown_time ? "시주 없이 3기둥으로 분석해요." : "비워두면 자동으로 00:30로 진행돼요 · 태어난 시를 모르면 ‘시 모름’"}
          </div>
        </div>
        {showGender && (
          <div className="bf-field">
            <label>성별</label>
            <div className="bf-seg">
              <button type="button" className={value.gender === "male" ? "on" : ""} onClick={() => onChange({ gender: "male" })}>♂ 남자</button>
              <button type="button" className={value.gender === "female" ? "on" : ""} onClick={() => onChange({ gender: "female" })}>♀ 여자</button>
            </div>
          </div>
        )}
        <div className="bf-field">
          <label>달력</label>
          <div className="bf-cal-row">
            <div className="bf-seg">
              <button type="button" className={value.calendar === "solar" ? "on" : ""} onClick={() => onChange({ calendar: "solar", is_leap_month: false })}>양력</button>
              <button type="button" className={value.calendar === "lunar" ? "on" : ""} onClick={() => onChange({ calendar: "lunar" })}>음력</button>
            </div>
            {value.calendar === "lunar" && (
              <button type="button" className={`bf-chip ${value.is_leap_month ? "on" : ""}`}
                      onClick={() => onChange({ is_leap_month: !value.is_leap_month })}>윤달</button>
            )}
          </div>
        </div>
      </div>

      <AdvancedBirthSettings value={value} onChange={onChange} />
    </div>
  );
}
