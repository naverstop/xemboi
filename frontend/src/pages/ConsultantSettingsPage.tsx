import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, useMe, type ConsultantSelf, type ConsultantPriceUnit, type BusinessHours } from "../api";
import { getPushState, subscribePush, unsubscribePush } from "../hooks/usePwaInstall";
import { useTranslation, Trans } from "react-i18next";

/**
 * 상담사 설정 — 입점 상담사 전용 셀프 관리(간판/사진·요금·#키워드·소개·상태).
 *
 * 관리자 통제 항목(업체명·분야·수수료·노출순서)은 읽기전용. self_managed=false 면 전체 읽기전용.
 * 요금 단위(세션/분/시간)는 하나 선택 → 백엔드가 1회(=상담시간분) 블록가로 환산 차감(표시만 분/시간).
 * 변경은 즉시 반영(진행 중 세션은 스냅샷이라 무관). 설계: [[consultation-1on1-plan]].
 */

// 요일 인덱스는 백엔드 datetime.weekday() 기준(0=월 … 6=일).
const DAYS: { k: string }[] = [
  { k: "0" }, { k: "1" }, { k: "2" },
  { k: "3" }, { k: "4" }, { k: "5" }, { k: "6" },
];
const DEFAULT_SLOT = { open: "10:00", close: "19:00" };

function bizSummary(h: BusinessHours, days: string[], always: string): string {
  const on = DAYS.filter((d) => h[d.k]?.open && h[d.k]?.close);
  if (on.length === 0) return always;
  return on.map((d) => `${days[Number(d.k)]} ${h[d.k].open}~${h[d.k].close}`).join(" · ");
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
  const { t: tr } = useTranslation();
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

  const UNIT_LABEL: Record<ConsultantPriceUnit, string> = {
    session: tr("consult.cset_unit_session"),
    minute: tr("consult.cset_unit_minute"),
    hour: tr("consult.cset_unit_hour"),
  };
  const dayLabels = tr("consult.cset_days").split(",");

  if (profile === undefined) return <div className="cset-wrap">{tr("consult.loading")}</div>;
  if (!me || !profile)
    return (
      <div className="cset-wrap">
        <h3>{tr("consult.con_only_title")}</h3>
        <p>{tr("consult.con_only_desc")} <Link to="/">{tr("consult.con_go_home")}</Link></p>
      </div>
    );

  const locked = !profile.self_managed;
  const dur = profile.duration_min || profile.eff_duration_min || 30;
  const floor = profile.min_price_p || 0;
  const est = estBlockPrice(unit, Number(rateP) || 0, Number(perMin) || 0, Number(perHour) || 0, dur, floor);
  // 선택 단위의 요금이 비어 있으면 실차감이 '0P'가 아니라 폴백(세션=기본값)이거나 입력 필요 — 오해 방지 표기
  const estDisplay =
    unit === "minute" && perMin === "" ? tr("consult.cset_est_need_min")
    : unit === "hour" && perHour === "" ? tr("consult.cset_est_need_hour")
    : unit === "session" && rateP === "" ? tr("consult.cset_est_default", { p: profile.eff_price_p.toLocaleString() })
    : tr("consult.pts", { p: est.toLocaleString() });

  function addKeyword() {
    const t = kwInput.trim().replace(/^#+/, "").trim().slice(0, 12);
    if (!t) return;
    if (keywords.some((k) => k.toLowerCase() === t.toLowerCase())) { setKwInput(""); return; }
    if (keywords.length >= 8) { setMsg({ ok: false, tx: tr("consult.cset_kw_max") }); return; }
    setKeywords([...keywords, t]);
    setKwInput("");
  }

  async function save() {
    if (!bizName.trim()) { setMsg({ ok: false, tx: tr("consult.cset_err_bizname") }); return; }
    // 영업시간 정리·검증: 켠 요일만, open<close 확인. 하나라도 역전이면 저장 중단.
    const cleanHours: BusinessHours = {};
    for (const d of DAYS) {
      const ent = hours[d.k];
      if (!ent || !ent.open || !ent.close) continue;
      if (ent.open >= ent.close) {
        setMsg({ ok: false, tx: tr("consult.cset_err_time_reversed", { day: dayLabels[Number(d.k)] }) });
        return;
      }
      cleanHours[d.k] = { open: ent.open, close: ent.close };
    }
    // 상담사 확인 절차 — 영업시간이 바뀌었으면 요약을 보여주고 최종 확정받는다.
    const prevHours = JSON.stringify(profile?.business_hours || {});
    if (JSON.stringify(cleanHours) !== prevHours) {
      const ok = window.confirm(tr("consult.cset_save_confirm", { summary: bizSummary(cleanHours, dayLabels, tr("consult.cset_biz_always")) }));
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
      setMsg({ ok: true, tx: tr("consult.cset_saved") });
    } catch (e: any) {
      setMsg({ ok: false, tx: e?.message || tr("consult.cset_save_fail") });
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
      setMsg({ ok: true, tx: tr("consult.cset_sign_uploaded") });
    } catch (e: any) {
      setMsg({ ok: false, tx: e?.message || tr("consult.cset_sign_fail") });
    } finally {
      setSignUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className={embedded ? "cset-wrap embedded" : "cset-wrap"}>
      {!embedded && (
        <div className="cset-head">
          <h2>{tr("consult.cset_title")}</h2>
          <Link to="/consultation/console" className="cset-console-link">{tr("consult.cset_to_console")}</Link>
        </div>
      )}
      <p className="cset-biz">
        <b>{profile.business_name}</b>
        <span className="cset-spec">{profile.specialty === "both" ? tr("consult.spec_both") : profile.specialty === "tarot" ? tr("consult.cat_tarot") : tr("consult.cat_saju")}</span>
        <span className="cset-ro">{tr("consult.cset_ro_note")}</span>
      </p>

      {/* 상호 — 상담사 본인 입력(카드에 표시). 비우면 저장 불가 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_bizname_h")} <small>{tr("consult.cset_bizname_sub")}</small></h3>
        <input className="cset-biz-input" type="text" value={bizName} maxLength={120} disabled={locked}
          placeholder={tr("consult.cset_bizname_ph")} onChange={(e) => setBizName(e.target.value)} />
        <p className="cset-hint">{tr("consult.cset_bizname_hint")}</p>
      </section>

      {locked && (
        <p className="cset-locked">{tr("consult.cset_locked")}</p>
      )}
      {msg && <p className={`cset-msg ${msg.ok ? "ok" : "err"}`}>{msg.tx}</p>}

      {/* 간판/사진 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_sign_h")}</h3>
        <div className="cset-sign-row">
          <div className="cset-sign-preview">
            {profile.signboard_image_url
              ? <img src={profile.signboard_image_url} alt={tr("consult.cset_sign_alt")} />
              : <span className="cset-sign-ph" aria-hidden>🪧</span>}
          </div>
          <div className="cset-sign-side">
            <button className="cset-upload" disabled={locked || signUploading} onClick={() => fileRef.current?.click()}>
              {signUploading ? tr("consult.cset_uploading") : tr("consult.cset_sign_change")}
            </button>
            <p className="cset-hint">{tr("consult.cset_sign_hint")}</p>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickFile} />
          </div>
        </div>
      </section>

      {/* 요금 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_fee_h")}</h3>
        <div className="cset-field">
          <label>{tr("consult.cset_fee_mode")}</label>
          <select value={unit} disabled={locked} onChange={(e) => setUnit(e.target.value as ConsultantPriceUnit)}>
            <option value="session">{tr("consult.cset_opt_session")}</option>
            <option value="minute">{tr("consult.cset_unit_minute")}</option>
            <option value="hour">{tr("consult.cset_unit_hour")}</option>
          </select>
        </div>
        {unit === "session" && (
          <div className="cset-field">
            <label>{tr("consult.cset_rate_session")}</label>
            <input type="number" min={0} inputMode="numeric" value={rateP} disabled={locked}
              placeholder={tr("consult.cset_rate_ph")} onChange={(e) => setRateP(e.target.value)} />
          </div>
        )}
        {unit === "minute" && (
          <div className="cset-field">
            <label>{tr("consult.cset_rate_min")}</label>
            <input type="number" min={0} inputMode="numeric" value={perMin} disabled={locked}
              placeholder={tr("consult.cset_rate_min_ph")} onChange={(e) => setPerMin(e.target.value)} />
          </div>
        )}
        {unit === "hour" && (
          <div className="cset-field">
            <label>{tr("consult.cset_rate_hour")}</label>
            <input type="number" min={0} inputMode="numeric" value={perHour} disabled={locked}
              placeholder={tr("consult.cset_rate_hour_ph")} onChange={(e) => setPerHour(e.target.value)} />
          </div>
        )}
        <p className="cset-est">
          <Trans i18nKey="consult.cset_est_line" components={{ b: <b /> }}
            values={{ label: UNIT_LABEL[unit], dur, est: estDisplay }} />
          {floor > 0 && <span className="cset-floor"> {tr("consult.cset_floor", { p: floor.toLocaleString() })}</span>}
        </p>
        <p className="cset-hint">{tr("consult.cset_fee_hint", { dur })}</p>
      </section>

      {/* #키워드 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_kw_h")} <small>{tr("consult.cset_kw_sub")}</small></h3>
        <div className="cset-kw-list">
          {keywords.map((k) => (
            <span key={k} className="cset-kw">
              #{k}
              {!locked && <button aria-label={tr("consult.cset_kw_del", { k })} onClick={() => setKeywords(keywords.filter((x) => x !== k))}>×</button>}
            </span>
          ))}
          {keywords.length === 0 && <span className="cset-kw-empty">{tr("consult.cset_kw_empty")}</span>}
        </div>
        {!locked && (
          <div className="cset-kw-add">
            <input
              type="text" value={kwInput} maxLength={12} placeholder={tr("consult.cset_kw_ph")}
              onChange={(e) => setKwInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addKeyword(); } }}
            />
            <button onClick={addKeyword}>{tr("consult.cset_kw_add")}</button>
          </div>
        )}
      </section>

      {/* 소개 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_intro_h")}</h3>
        <textarea className="cset-intro" value={intro} disabled={locked} maxLength={2000} rows={3}
          placeholder={tr("consult.cset_intro_ph")} onChange={(e) => setIntro(e.target.value)} />
      </section>

      {/* 노출 상태 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_status_h")}</h3>
        <div className="cset-status">
          <label className={status === "active" ? "on" : ""}>
            <input type="radio" name="cstatus" checked={status === "active"} disabled={locked} onChange={() => setStatus("active")} />
            {tr("consult.cset_status_active")}
          </label>
          <label className={status === "coming_soon" ? "on" : ""}>
            <input type="radio" name="cstatus" checked={status === "coming_soon"} disabled={locked} onChange={() => setStatus("coming_soon")} />
            {tr("consult.cset_status_soon")}
          </label>
        </div>
      </section>

      {/* 영업시간(요일별) — 상시 예약 가능 범위. 미설정=상시(제한 없음) */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_hours_h")} <small>{tr("consult.cset_hours_sub")}</small></h3>
        <p className="cset-hint">
          <Trans i18nKey="consult.cset_hours_hint" components={{ b: <b /> }} />
        </p>
        <div className="cset-biz-presets">
          <button type="button" disabled={locked} onClick={() => applyPreset(["0", "1", "2", "3", "4"], DEFAULT_SLOT)}>{tr("consult.cset_preset_weekday")}</button>
          <button type="button" disabled={locked} onClick={() => applyPreset(DAYS.map((d) => d.k), DEFAULT_SLOT)}>{tr("consult.cset_preset_daily")}</button>
          <button type="button" disabled={locked} onClick={() => setHours({})}>{tr("consult.cset_preset_clear")}</button>
        </div>
        <div className="cset-biz-grid">
          {DAYS.map((d) => {
            const ent = hours[d.k];
            const on = !!ent;
            return (
              <div key={d.k} className={`cset-biz-row ${on ? "on" : "off"}`}>
                <label className="cset-biz-day">
                  <input type="checkbox" checked={on} disabled={locked} onChange={(e) => setDayOn(d.k, e.target.checked)} />
                  <span>{dayLabels[Number(d.k)]}</span>
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
                  <span className="cset-biz-rest">{tr("consult.cset_day_off")}</span>
                )}
              </div>
            );
          })}
        </div>
        <p className="cset-est">
          <Trans i18nKey="consult.cset_hours_current" components={{ b: <b /> }}
            values={{ summary: bizSummary(hours, dayLabels, tr("consult.cset_biz_always")) }} />
        </p>
      </section>

      {/* 상담 요청 알림(Web Push) — 오프라인에도 접수 알림 받기 */}
      <section className="cset-sec">
        <h3>{tr("consult.cset_push_h")}</h3>
        {pushSt && !pushSt.supported && (
          <p className="cset-hint"><Trans i18nKey="consult.cset_push_unsupported" components={{ b: <b /> }} /></p>
        )}
        {pushSt && pushSt.supported && pushSt.permission === "denied" && (
          <p className="cset-hint"><Trans i18nKey="consult.cset_push_denied" components={{ b: <b /> }} /></p>
        )}
        {pushSt && pushSt.supported && pushSt.permission !== "denied" && (
          <div className="cset-push-row">
            <span className={`cset-push-state ${pushSt.subscribed ? "on" : "off"}`}>
              {pushSt.subscribed ? tr("consult.cset_push_on") : tr("consult.cset_push_off")}
            </span>
            <button className="cset-push-btn" onClick={togglePush} disabled={pushBusy}>
              {pushBusy ? tr("consult.push_setting") : pushSt.subscribed ? tr("consult.cset_push_disable") : tr("consult.cset_push_enable")}
            </button>
          </div>
        )}
        <p className="cset-hint">{tr("consult.cset_push_hint")}</p>
      </section>

      <button className="cset-save" disabled={locked || saving} onClick={save}>
        {saving ? tr("consult.cset_saving") : tr("consult.cset_save_btn")}
      </button>
    </div>
  );
}
