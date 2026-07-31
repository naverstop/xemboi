/** 한글 한 글자 → 한자 후보 칩 → 선택. 성·이름 공용. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { glossKo } from "../lib/naming-data";

type Cand = { char: string; strokes: number; defn: string; is_surname: boolean };

export default function HanjaSyllablePicker({
  syllable,
  selected,
  onPick,
  surnameMode = false,
}: {
  syllable: string;
  selected: string;
  onPick: (han: string) => void;
  surnameMode?: boolean;
}) {
  const [cands, setCands] = useState<Cand[]>([]);
  const valid = /^[가-힣]$/.test(syllable);

  useEffect(() => {
    if (!valid) { setCands([]); return; }
    let alive = true;
    api.lookupHanja(syllable).then((r) => { if (alive) setCands(r.items); }).catch(() => { if (alive) setCands([]); });
    return () => { alive = false; };
  }, [syllable, valid]);

  if (!valid) return null;
  return (
    <div className="syl-pick">
      <div className="syl-head">‘{syllable}’ 한자 선택</div>
      <div className="hanja-pick">
        {cands.map((h) => (
          <button key={h.char} type="button"
                  className={`hanja-chip ${selected === h.char ? "on" : ""}`}
                  title={glossKo(h.defn) || h.defn}
                  onClick={() => onPick(h.char)}>
            <span className="hc-char">{h.char}</span>
            <span className="hc-sub">{h.strokes}획{surnameMode && h.is_surname ? "·성" : ""}</span>
          </button>
        ))}
        {cands.length === 0 && <span className="pc-hint">후보를 찾지 못했어요.</span>}
      </div>
    </div>
  );
}
