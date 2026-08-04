import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, useMe, type ConsultantSelf, type ConsultantPriceUnit, type BusinessHours } from "../api";
import { getPushState, subscribePush, unsubscribePush } from "../hooks/usePwaInstall";

/**
 * 상담사 설정 — 입점 상담사 전용 셀프 관리(간판/사진·요금·#키워드·소개·상태).
 *
 * 관리자 통제 항목(업체명·분야·수수료·노출순서)은 읽기전용. self_managed=false 면 전체 읽기전용.
 * 요금 단위(세션/분/시간)는 하나 선택 → 백엔드가 1회(=상담시간분) 블록가로 환산 차감(표시만 분/시간).
 * 변경은 즉시 반영(진행 중 세션은 스냅샷이라 무관). 설계: [[consultation-1on1-plan]].
 */

const UNIT_LABEL: Record<ConsultantPriceUnit, string> = {
  session: "세션당(1회)",
  minute: "분당",
  hour: "시간당",
};

// 요일 인덱스는 백엔드 datetime.weekday() 기준(0=월 … 6=일).
const DAYS: { k: string; label: string }[] = [
  { k: "0", label: "월" }, { k: "1", label: "화" }, { k: "2", label: "수" },
  { k: "3", label: "목" }, { k: "4", label: "금" }, { k: "5", label: "토" }, { k: "6", label: "일" },
];
const DEFAULT_SLOT = { open: "10:00", close: "19:00" };

function bizSummary(h: BusinessHours): string {
  const on = DAYS.filter((d) => h[d.k]?.open && h[d.k]?.close);
  if (on.length === 0) return "상시(영업시간 제한 없음)";
  return on.map((d) => `${d.label} ${h[d.k].open}~${h[d.k].close}`).join(" · ");
}

function estBlockPrice(
  unit: ConsultantPriceUnit,
  rateP: number,
  perMin: number,
  perHour: number,
  dur: number,
  floor: number,
): number {
  let raw = 0;
  if (unit === "minute") raw = perMin * dur;
  else if (unit === "hour") raw = Math.round((perHour * dur) / 60);
  else raw = rateP;
  return floor > 0 ? Math.max(raw, floor) : raw;
}

export default function ConsultantSettingsPage({ embedded = false }: { embedded?: boolean }) {
  const me = useMe();
  const [profile, setProfile] = useState<ConsultantSelf | null | undefined>(undefined);
  const [bizName, setBizName] = useState("");   // 상호(카드 표시명) — 상담사 본인 입력
  const [intro, setIntro] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [kwInput, setKwInput] = useState("");
  const [unit, setUnit] = useState<ConsultantPriceUnit>("session");
  const [rateP, setRateP] = useState("");
  const [perMin, setPerMin] = useState("");
  const [perHour, setPerHour] = useState("");
  const [status, setStatus] = useState<"active" | "coming_soon">("active");
  const [hours, setHours] = useState<BusinessHours>({});   // 요일별 영업시간(0=월~6=일)
  const [saving, setSaving] = useState(false);
  const [signUploading, setSignUploading] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; tx: string } | null>(null);
  const [pushSt, setPushSt] = useState<{ supported: boolean; permission: NotificationPermission; subscribed: boolean } | null>(null);
  const [pushBusy, setPushBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  function hydrate(c: ConsultantSelf) {
    setProfile(c);
    setBizName(c.business_name || "");
    setIntro(c.intro || "");
    setKeywords(c.keywords || []);
    setUnit(c.price_unit || "session");
    setRateP(c.rate_p != null ? String(c.rate_p) : "");
    setPerMin(c.per_min_p != null ? String(c.per_min_p) : "");
    setPerHour(c.per_hour_p != null ? String(c.per_hour_p) : "");
    setStatus(c.status === "coming_soon" ? "coming_soon" : "active");
    setHours(c.business_hours ? { ...c.business_hours } : {});
  }

  function setDayOn(k: string, on: boolean) {
    setHours((h) => {
      const next = { ...h };
      if (on) next[k] = next[k] || { ...DEFAULT_SLOT };
      else delete next[k];
      return next;
    });
  }
  function setDayTime(k: string, field: "open" | "close", v: string) {
    setHours((h) => ({ ...h, [k]: { ...(h[k] || { ...DEFAULT_SLOT }), [field]: v } }));
  }
  function applyPreset(days: string[], slot: { open: string; close: string }) {
    setHours((h) => {
      const next = { ...h };
      for (const k of days) next[k] = { ...slot };
      return next;
    });
  }

  useEffect(() => {
    api.myConsultantProfile()
      .then((r) => (r.consultant ? hydrate(r.consultant) : setProfile(null)))
      .catch(() => setProfile(null));
    getPushState().then(setPushSt).catch(() => {});
  }, []);

  async function togglePush() {
    if (!pushSt || pushBusy) return;
    setPushBusy(true);
    if (pushSt.subscribed) await unsubscribePush();
    else await subscribePush();
    setPushSt(await getPushState());
    setPushBusy(false);
  }

  if (profile === undefined) return <div className="cset-wrap">불러오는 중…</div>;
  if (!me || !profile)
    return (
      <div className="cset-wrap">
        <h3>상담사 전용</h3>
        <p>입점 상담사 계정만 이용할 수 있어요. <Link to="/">홈으로</Link></p>
      </div>
    );

  const locked = !profile.self_managed;
  const dur = profile.duration_min || profile.eff_duration_min || 30;
  const floor = profile.min_price_p || 0;
  const est = estBlockPrice(unit, Number(rateP) || 0, Number(perMin) || 0, Number(perHour) || 0, dur, floor);
  // 선택 단위의 요금이 비어 있으면 실차감이 '0P'가 아니라 폴백(세션=기본값)이거나 입력 필요 — 오해 방지 표기
  const estDisplay =
    unit === "minute" && perMin === "" ? "분당 요금 입력 필요"
    : unit === "hour" && perHour === "" ? "시간당 요금 입력 필요"
    : unit === "session" && rateP === "" ? `${profile.eff_price_p.toLocaleString()}P (기본값 적용)`
    : `${est.toLocaleString()}P`;

  function addKeyword() {
    const t = kwInput.trim().replace(/^#+/, "").trim().slice(0, 12);
    if (!t) return;
    if (keywords.some((k) => k.toLowerCase() === t.toLowerCase())) { setKwInput(""); return; }
    if (keywords.length >= 8) { setMsg({ ok: false, tx: "키워드는 최대 8개까지 등록할 수 있어요." }); return; }
    setKeywords([...keywords, t]);
    setKwInput("");
  }

  async function save() {
    if (!bizName.trim()) { setMsg({ ok: false, tx: "상호(상담사명)를 입력해 주세요." }); return; }
    // 영업시간 정리·검증: 켠 요일만, open<close 확인. 하나라도 역전이면 저장 중단.
    const cleanHours: BusinessHours = {};
    for (const d of DAYS) {
      const ent = hours[d.k];
      if (!ent || !ent.open || !ent.close) continue;
      if (ent.open >= ent.close) {
        setMsg({ ok: false, tx: `${d.label}요일 영업 종료 시각이 시작 시각보다 빨라요. 시간을 확인해 주세요.` });
        return;
      }
      cleanHours[d.k] = { open: ent.open, close: ent.close };
    }
    // 상담사 확인 절차 — 영업시간이 바뀌었으면 요약을 보여주고 최종 확정받는다.
    const prevHours = JSON.stringify(profile?.business_hours || {});
    if (JSON.stringify(cleanHours) !== prevHours) {
      const ok = window.confirm(`아래 영업시간으로 저장할까요?\n\n${bizSummary(cleanHours)}\n\n(영업시간 외에는 예약 시간을 열 수 없어요)`);
      if (!ok) return;
    }
    setSaving(true); setMsg(null);
    try {
      const body: any = { business_name: bizName.trim(), intro, keywords, price_unit: unit, status, business_hours: cleanHours };
      if (unit === "session") body.rate_p = rateP === "" ? null : Number(rateP);
      if (unit === "minute") body.per_min_p = perMin === "" ? null : Number(perMin);
      if (unit === "hour") body.per_hour_p = perHour === "" ? null : Number(perHour);
      const r = await api.updateMyConsultant(body);
      hydrate(r.consultant);
      setMsg({ ok: true, tx: "저장했어요. 상담사 목록에 바로 반영돼요." });
    } catch (e: any) {
      setMsg({ ok: false, tx: e?.message || "저장에 실패했어요." });
    } finally {
      setSaving(false);
    }
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setSignUploading(true); setMsg(null);
    try {
      const form = new FormData();
      form.append("file", f);
      const r = await api.uploadMyConsultantSignboard(form);
      hydrate(r.consultant);
      setMsg({ ok: true, tx: "간판 이미지를 등록했어요." });
    } catch (e: any) {
      setMsg({ ok: false, tx: e?.message || "이미지 등록에 실패했어요." });
    } finally {
      setSignUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className={embedded ? "cset-wrap embedded" : "cset-wrap"}>
      {!embedded && (
        <div className="cset-head">
          <h2>상담사 설정</h2>
          <Link to="/consultation/console" className="cset-console-link">← 콘솔로</Link>
        </div>
      )}
      <p className="cset-biz">
        <b>{profile.business_name}</b>
        <span className="cset-spec">{profile.specialty === "both" ? "사주+타로" : profile.specialty === "tarot" ? "타로" : "사주"}</span>
        <span className="cset-ro">분야·수수료는 관리자가 설정해요</span>
      </p>

      {/* 상호 — 상담사 본인 입력(카드에 표시). 비우면 저장 불가 */}
      <section className="cset-sec">
        <h3>상호 <small>(상담사명 · 사용자 카드에 표시)</small></h3>
        <input className="cset-biz-input" type="text" value={bizName} maxLength={120} disabled={locked}
          placeholder="예: 달빛 사주상담소" onChange={(e) => setBizName(e.target.value)} />
        <p className="cset-hint">사용자에게 보이는 이름이에요. 이메일·아이디 말고 상호(간판 이름)를 적어 주세요.</p>
      </section>

      {locked && (
        <p className="cset-locked">관리자가 셀프 편집을 잠갔어요. 변경이 필요하면 고객센터로 문의해 주세요.</p>
      )}
      {msg && <p className={`cset-msg ${msg.ok ? "ok" : "err"}`}>{msg.tx}</p>}

      {/* 간판/사진 */}
      <section className="cset-sec">
        <h3>간판 · 사진</h3>
        <div className="cset-sign-row">
          <div className="cset-sign-preview">
            {profile.signboard_image_url
              ? <img src={profile.signboard_image_url} alt="간판" />
              : <span className="cset-sign-ph" aria-hidden>🪧</span>}
          </div>
          <div className="cset-sign-side">
            <button className="cset-upload" disabled={locked || signUploading} onClick={() => fileRef.current?.click()}>
              {signUploading ? "업로드 중…" : "이미지 변경"}
            </button>
            <p className="cset-hint">권장 세로 4:5 비율 · 8MB 이하 (png/jpg/webp)</p>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickFile} />
          </div>
        </div>
      </section>

      {/* 요금 */}
      <section className="cset-sec">
        <h3>요금</h3>
        <div className="cset-field">
          <label>요금 방식</label>
          <select value={unit} disabled={locked} onChange={(e) => setUnit(e.target.value as ConsultantPriceUnit)}>
            <option value="session">세션당(1회 고정)</option>
            <option value="minute">분당</option>
            <option value="hour">시간당</option>
          </select>
        </div>
        {unit === "session" && (
          <div className="cset-field">
            <label>1회 요금 (P)</label>
            <input type="number" min={0} inputMode="numeric" value={rateP} disabled={locked}
              placeholder="비우면 기본값(관리자 설정)" onChange={(e) => setRateP(e.target.value)} />
          </div>
        )}
        {unit === "minute" && (
          <div className="cset-field">
            <label>분당 요금 (P)</label>
            <input type="number" min={0} inputMode="numeric" value={perMin} disabled={locked}
              placeholder="예: 300" onChange={(e) => setPerMin(e.target.value)} />
          </div>
        )}
        {unit === "hour" && (
          <div className="cset-field">
            <label>시간당 요금 (P)</label>
            <input type="number" min={0} inputMode="numeric" value={perHour} disabled={locked}
              placeholder="예: 18000" onChange={(e) => setPerHour(e.target.value)} />
          </div>
        )}
        <p className="cset-est">
          카드 표시: <b>{UNIT_LABEL[unit]}</b>
          {" · "}상담 1회 = <b>{dur}분</b> 블록, 실제 차감 <b>{estDisplay}</b>
          {floor > 0 && <span className="cset-floor"> (최소 {floor.toLocaleString()}P)</span>}
        </p>
        <p className="cset-hint">수락 시 1회(={dur}분) 요금이 차감되고, 연장 시 1블록씩 추가돼요. 상담시간(분)은 관리자가 설정해요.</p>
      </section>

      {/* #키워드 */}
      <section className="cset-sec">
        <h3>#전문영역 키워드 <small>(최대 8개)</small></h3>
        <div className="cset-kw-list">
          {keywords.map((k) => (
            <span key={k} className="cset-kw">
              #{k}
              {!locked && <button aria-label={`${k} 삭제`} onClick={() => setKeywords(keywords.filter((x) => x !== k))}>×</button>}
            </span>
          ))}
          {keywords.length === 0 && <span className="cset-kw-empty">예: 연애 · 취업 · 재물</span>}
        </div>
        {!locked && (
          <div className="cset-kw-add">
            <input
              type="text" value={kwInput} maxLength={12} placeholder="키워드 입력 후 Enter"
              onChange={(e) => setKwInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addKeyword(); } }}
            />
            <button onClick={addKeyword}>추가</button>
          </div>
        )}
      </section>

      {/* 소개 */}
      <section className="cset-sec">
        <h3>소개</h3>
        <textarea className="cset-intro" value={intro} disabled={locked} maxLength={2000} rows={3}
          placeholder="상담 스타일·경력을 한두 줄로 소개해 주세요." onChange={(e) => setIntro(e.target.value)} />
      </section>

      {/* 노출 상태 */}
      <section className="cset-sec">
        <h3>노출 상태</h3>
        <div className="cset-status">
          <label className={status === "active" ? "on" : ""}>
            <input type="radio" name="cstatus" checked={status === "active"} disabled={locked} onChange={() => setStatus("active")} />
            영업 (목록에 정상 노출)
          </label>
          <label className={status === "coming_soon" ? "on" : ""}>
            <input type="radio" name="cstatus" checked={status === "coming_soon"} disabled={locked} onChange={() => setStatus("coming_soon")} />
            입점예정 (‘입점예정’으로 노출·신청 잠금)
          </label>
        </div>
      </section>

      {/* 영업시간(요일별) — 상시 예약 가능 범위. 미설정=상시(제한 없음) */}
      <section className="cset-sec">
        <h3>영업시간 <small>(요일별 · 예약 가능 범위)</small></h3>
        <p className="cset-hint">
          영업시간을 정하면 <b>그 시간 안에서만 예약 시간을 열 수 있어요.</b> 비워 두면 상시(제한 없음)로 운영돼요.
          입력창을 직접 숫자로 쳐도 되고, 시계 아이콘으로 골라도 돼요.
        </p>
        <div className="cset-biz-presets">
          <button type="button" disabled={locked} onClick={() => applyPreset(["0", "1", "2", "3", "4"], DEFAULT_SLOT)}>평일 10:00~19:00</button>
          <button type="button" disabled={locked} onClick={() => applyPreset(DAYS.map((d) => d.k), DEFAULT_SLOT)}>매일 10:00~19:00</button>
          <button type="button" disabled={locked} onClick={() => setHours({})}>전체 지우기(상시)</button>
        </div>
        <div className="cset-biz-grid">
          {DAYS.map((d) => {
            const ent = hours[d.k];
            const on = !!ent;
            return (
              <div key={d.k} className={`cset-biz-row ${on ? "on" : "off"}`}>
                <label className="cset-biz-day">
                  <input type="checkbox" checked={on} disabled={locked} onChange={(e) => setDayOn(d.k, e.target.checked)} />
                  <span>{d.label}</span>
                </label>
                {on ? (
                  <div className="cset-biz-times">
                    <input type="time" value={ent.open} disabled={locked} step={600}
                      onChange={(e) => setDayTime(d.k, "open", e.target.value)} />
                    <span className="cset-biz-tilde">~</span>
                    <input type="time" value={ent.close} disabled={locked} step={600}
                      onChange={(e) => setDayTime(d.k, "close", e.target.value)} />
                  </div>
                ) : (
                  <span className="cset-biz-rest">휴무</span>
                )}
              </div>
            );
          })}
        </div>
        <p className="cset-est">현재 설정: <b>{bizSummary(hours)}</b></p>
      </section>

      {/* 상담 요청 알림(Web Push) — 오프라인에도 접수 알림 받기 */}
      <section className="cset-sec">
        <h3>상담 요청 알림</h3>
        {pushSt && !pushSt.supported && (
          <p className="cset-hint">이 브라우저는 푸시 알림을 지원하지 않아요. (iPhone은 <b>홈 화면에 추가</b> 후 이용해 주세요)</p>
        )}
        {pushSt && pushSt.supported && pushSt.permission === "denied" && (
          <p className="cset-hint">브라우저에서 알림이 차단돼 있어요. <b>브라우저 설정 &gt; 알림</b>에서 이 사이트를 허용해 주세요.</p>
        )}
        {pushSt && pushSt.supported && pushSt.permission !== "denied" && (
          <div className="cset-push-row">
            <span className={`cset-push-state ${pushSt.subscribed ? "on" : "off"}`}>
              {pushSt.subscribed ? "🔔 켜짐 — 영업 중이 아니어도 접수 알림을 받아요" : "🔕 꺼짐 — 오프라인 시 알림을 못 받아요"}
            </span>
            <button className="cset-push-btn" onClick={togglePush} disabled={pushBusy}>
              {pushBusy ? "설정 중…" : pushSt.subscribed ? "끄기" : "알림 받기"}
            </button>
          </div>
        )}
        <p className="cset-hint">알림을 켜두면 앱을 닫아도 새 상담 요청이 오면 푸시로 알려드려요.</p>
      </section>

      <button className="cset-save" disabled={locked || saving} onClick={save}>
        {saving ? "저장 중…" : "변경사항 저장"}
      </button>
    </div>
  );
}
