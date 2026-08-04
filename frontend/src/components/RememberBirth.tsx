/** '내 사주정보 기억하기' — 전 메뉴 공통 훅+필 토글(운영자 결정 2026-07).
 *
 *  정책:
 *  - 한 번이라도 저장돼 있으면(회원=saju_profile, 비회원=localStorage) 화면 진입 시 자동 채움 + 토글 ON.
 *  - 한 번이라도 생년월일을 '입력'하면 기본 활성화(자동 ON·자동 저장) — 사용자가 명시적으로 끈 경우만 예외.
 *  - ON 상태에서 입력이 바뀌면 저장(회원=서버 saju_profile 디바운스, 비회원=localStorage) → 전 메뉴 공유.
 *  - OFF 토글 시 저장본 삭제(회원=서버 프로필 null, 비회원=LS 제거) + '명시적 끔' 마킹(재자동화 방지).
 *
 *  localStorage 키는 사주상담(ChatPage)과 동일("saju_birth_remember"/"saju_birth_saved") —
 *  어느 메뉴에서 기억하든 모든 메뉴에 반영된다. "0"은 '명시적으로 껐음' 마커.
 */
import { useEffect, useRef, useState } from "react";
import { api, setCachedMe, useMe, type Birth } from "../api";
import { resolveBirthTime } from "../lib/birthTime";
import { profileToBirthValue, type BirthValue } from "./BirthFields";

const REMEMBER_KEY = "saju_birth_remember";
const SAVED_KEY = "saju_birth_saved";

function toBirth(b: BirthValue): Birth {
  return {
    birth_date: b.birth_date,
    birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
    calendar: b.calendar,
    gender: b.gender,
    is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
    apply_true_solar_time: !!b.apply_true_solar_time,
    birth_longitude: b.birth_longitude ?? null,
    apply_equation_of_time: !!b.apply_equation_of_time,
    night_zi_mode: b.night_zi_mode ?? "yaja",
  };
}

export function useBirthMemory(
  b: BirthValue,
  setB: (patch: Partial<BirthValue>) => void,
  opts?: {
    onPrefill?: (patch: Partial<BirthValue>) => void;  // 자동 조회(푸시 랜딩 UX) 등
    /** false면 완전 비활성(불러오기·자동ON·저장 모두 중단). 작명 '아기 이름 짓기'처럼
     *  입력 생일이 '본인'이 아닌 모드에서 내 저장 정보가 오염되는 것을 차단.
     *  다시 true가 되면 저장본을 새로 불러온다(작명 '내 이름 짓기' 전환). */
    enabled?: boolean;
  },
) {
  const me = useMe();
  const enabled = opts?.enabled !== false;
  const [remember, setRemember] = useState(false);
  const loadedFor = useRef<string | null>(null);
  const explicitOff = useRef(localStorage.getItem(REMEMBER_KEY) === "0");

  // 초기 로드 — 저장본 있으면 자동 채움 + ON.
  // ⚠️ 회원인데 me 캐시에 아직 프로필이 없으면(로그인 직후·부트 갱신 전 stale 캐시) '로드 완료'
  // 도장을 찍지 않는다 — 프로필이 늦게 도착하는 순간 다시 채운다(운영자 지적: ON인데 빈칸 재발 원인).
  // 또한 회원도 LS 사본(SAVED_KEY)을 폴백으로 사용 — 서버 캐시가 늦어도 즉시 채워진다.
  useEffect(() => {
    if (!enabled) { loadedFor.current = null; setRemember(false); return; }  // 재활성화 시 재로드되게 가드 리셋
    // 도장은 '프로필 내용 서명' 기준 — 내 저장 완료/타 기기 갱신으로 서버본이 바뀌면 자동 재반영
    const key = me
      ? `u${me.id}|${me.saju_profile?.birth_date || ""}|${me.saju_profile?.birth_time || ""}`
      : "guest";
    if (loadedFor.current === key) return;
    const explicitlyOff = localStorage.getItem(REMEMBER_KEY) === "0";
    const lsSaved = (() => {
      try { return JSON.parse(localStorage.getItem(SAVED_KEY) || "null"); } catch { return null; }
    })();
    const fill = (src: any) => {
      const patch = profileToBirthValue(src);
      setB(patch);
      setRemember(true);
      opts?.onPrefill?.(patch);
    };
    if (me) {
      if (me.saju_profile?.birth_date) {
        loadedFor.current = key;               // 실제로 채웠을 때만 완료 처리
        fill(me.saju_profile);
      } else if (!explicitlyOff && lsSaved?.birth_date) {
        fill(lsSaved);                          // 서버 프로필 도착 전 — LS 사본으로 즉시 채움(도장은 보류)
      }
      // 프로필이 없으면 도장 없이 대기 → me 갱신(setCachedMe)마다 재시도
    } else {
      loadedFor.current = key;
      if (localStorage.getItem(REMEMBER_KEY) === "1" && lsSaved?.birth_date) fill(lsSaved);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, me?.saju_profile?.birth_date, enabled]);

  // '한 번이라도 입력하면 기본 활성화' — 명시적으로 끈 적 없으면 생년월일 입력 즉시 자동 ON
  useEffect(() => {
    if (enabled && !remember && !explicitOff.current && b.birth_date) setRemember(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b.birth_date, enabled]);

  // ON 상태에서 변경 저장 — 회원=서버(디바운스+이탈 시 즉시 발사)·전원=LS 사본(이중 안전망).
  // ⚠️ 이전엔 900ms 안에 페이지를 떠나면 clearTimeout으로 서버 저장이 통째로 유실됐다(운영자 지적 원인 ②).
  const pendingSave = useRef<Birth | null>(null);
  useEffect(() => {
    if (!enabled || !remember || !b.birth_date) return;
    const toSave = toBirth(b);
    localStorage.setItem(REMEMBER_KEY, "1");
    localStorage.setItem(SAVED_KEY, JSON.stringify(toSave));   // 회원 포함 — 캐시/네트워크와 무관한 즉시 사본
    if (me) {
      // 에코 저장 차단 — 서버 프로필과 동일한 값(방금 fill된 값)은 재저장하지 않는다.
      // 없으면 '옛값 fill → 디바운스 재저장'이 다른 페이지에서 발사한 새값 저장을 롤백시킬 수 있다.
      const p0 = me.saju_profile;
      if (p0 && p0.birth_date === toSave.birth_date && (p0.birth_time || "") === (toSave.birth_time || "")
          && p0.calendar === toSave.calendar && p0.gender === toSave.gender) return;
      pendingSave.current = toSave;
      const t = setTimeout(() => {
        pendingSave.current = null;
        api.saveSajuProfile(toSave).then(setCachedMe).catch(() => {});
      }, 900);
      return () => {
        clearTimeout(t);
        if (pendingSave.current) {               // 디바운스 중 이탈/변경 — 유실 대신 즉시 발사
          const p = pendingSave.current;
          pendingSave.current = null;
          api.saveSajuProfile(p).then(setCachedMe).catch(() => {});
        }
      };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b, remember, enabled]);

  const toggleRemember = (on: boolean) => {
    setRemember(on);
    explicitOff.current = !on;
    if (me) {
      api.saveSajuProfile(on ? toBirth(b) : null).then(setCachedMe).catch(() => {});
    }
    if (on) {
      localStorage.setItem(REMEMBER_KEY, "1");
      if (b.birth_date) localStorage.setItem(SAVED_KEY, JSON.stringify(toBirth(b)));  // 회원 포함 사본
    } else {
      localStorage.setItem(REMEMBER_KEY, "0");   // 명시적 끔 — 재자동화 방지 마커
      localStorage.removeItem(SAVED_KEY);
    }
  };

  return { remember, toggleRemember };
}

/** 필 토글 UI — ChatPage와 동일한 .remember-check 디자인(스위치+상태 힌트). */
export default function RememberBirthToggle({
  remember, onToggle,
}: { remember: boolean; onToggle: (on: boolean) => void }) {
  return (
    <div className="bf-remember-row">
      <label className={`remember-check${remember ? " on" : ""}`}
             title="켜 두면 입력한 사주정보를 저장해, 어느 메뉴에서든 자동으로 불러옵니다.">
        <input type="checkbox" checked={remember} onChange={(e) => onToggle(e.target.checked)} />
        <span className="rc-switch" aria-hidden><i /></span>
        <span className="rc-txt">
          💾 내 사주정보 기억하기
          <em>{remember ? "모든 메뉴에서 자동 입력돼요" : "켜면 매번 입력 안 해도 돼요"}</em>
        </span>
      </label>
    </div>
  );
}
