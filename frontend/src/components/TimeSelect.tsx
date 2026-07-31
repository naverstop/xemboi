/** 공용 시각 선택 — [오전 / 오후] 토글 + 시(1~12) + 분(0~59).
 *  값은 백엔드 계약 그대로 24시간 "HH:MM" 문자열(빈 문자열 = 미입력).
 *
 *  네이티브 <input type="time">는 데스크톱·모바일 모두 오전/오후와 시·분을
 *  고르기 번거로워, 전 메뉴(상담·궁합·택일·작명·설정)의 시각 입력을
 *  이 컴포넌트로 통일한다.
 */
import { useEffect, useState } from "react";

type AmPm = "AM" | "PM";

// "HH:MM"(24h) → 오전/오후·12시제. 형식이 아니면 null.
function parse12(v: string): { ampm: AmPm; h12: number; min: string } | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec((v || "").trim());
  if (!m) return null;
  const h = +m[1];
  if (h < 0 || h > 23 || +m[2] > 59) return null;
  const ampm: AmPm = h < 12 ? "AM" : "PM";
  let h12 = h % 12;
  if (h12 === 0) h12 = 12; // 0시·12시는 12로 표기(오전 12시=자정, 오후 12시=정오)
  return { ampm, h12, min: m[2] };
}

export default function TimeSelect({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  const p = parse12(value);
  const [ampm, setAmpm] = useState<AmPm>(p?.ampm ?? "AM");
  const [h12, setH12] = useState<number | "">(p?.h12 ?? "");
  const [min, setMin] = useState<string>(p?.min ?? "00");

  // 외부 값 변경(빠른입력·프로필 자동채움·초기화) 동기화.
  // 시(h12)는 비울 수 있게 하되, 오전/오후·분 선택은 사용자 선택을 보존.
  useEffect(() => {
    const q = parse12(value);
    if (q) { setAmpm(q.ampm); setH12(q.h12); setMin(q.min); }
    else setH12("");
  }, [value]);

  // 시(h12)가 비어 있으면 "미입력"으로 보고 빈 문자열을 올린다.
  function emit(a: AmPm, h: number | "", mm: string) {
    if (h === "") { onChange(""); return; }
    let h24 = h % 12;            // 12 → 0
    if (a === "PM") h24 += 12;   // 오후 12시 → 12, 오후 1시 → 13
    onChange(`${String(h24).padStart(2, "0")}:${mm}`);
  }

  return (
    <div className={`timesel${disabled ? " is-disabled" : ""}`}>
      <div className="timesel-ampm" role="group" aria-label="오전/오후 선택">
        <button
          type="button" className={ampm === "AM" ? "on" : ""} disabled={disabled}
          onClick={() => { setAmpm("AM"); emit("AM", h12, min); }}
        >오전</button>
        <button
          type="button" className={ampm === "PM" ? "on" : ""} disabled={disabled}
          onClick={() => { setAmpm("PM"); emit("PM", h12, min); }}
        >오후</button>
      </div>
      <div className="timesel-hm">
        <select
          className="timesel-sel" aria-label="시" value={h12} disabled={disabled}
          onChange={(e) => { const v = e.target.value === "" ? "" : +e.target.value; setH12(v); emit(ampm, v, min); }}
        >
          <option value="">시</option>
          {Array.from({ length: 12 }, (_, i) => i + 1).map((h) => (
            <option key={h} value={h}>{h}시</option>
          ))}
        </select>
        <select
          className="timesel-sel" aria-label="분" value={min} disabled={disabled || h12 === ""}
          onChange={(e) => { setMin(e.target.value); emit(ampm, h12, e.target.value); }}
        >
          {Array.from({ length: 60 }, (_, i) => String(i).padStart(2, "0")).map((mm) => (
            <option key={mm} value={mm}>{mm}분</option>
          ))}
        </select>
      </div>
    </div>
  );
}
