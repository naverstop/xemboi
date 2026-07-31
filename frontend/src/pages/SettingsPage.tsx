import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { Link } from "react-router-dom";
import { api, DIALECTS, useMe, setCachedMe } from "../api";
import type { SajuProfile, SajuProfileInput } from "../api";
import { fmtNum } from "../lib/money";
import { DEFAULT_LON } from "../lib/regions";
import TimeSelect from "../components/TimeSelect";
import AdvancedBirthSettings from "../components/AdvancedBirthSettings";

export default function SettingsPage() {
  const me = useMe();
  const { t: tr } = useTranslation();

  if (!me) {
    return (
      <div style={{ padding: 20 }}>
        <h3>{tr("settings.title")}</h3>
        <p><Trans i18nKey="settings.login_required" components={{ a: <Link to="/login" /> }} /></p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 560, margin: "0 auto", display: "grid", gap: 16 }}>
      <h2 style={{ marginBottom: 0 }}>{tr("settings.title")}</h2>
      <ProfileCard />
      <SajuProfilesCard />
      <DialectCard />
      <PasswordCard />
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("settings.pay_section")}</h3>
        <p style={{ color: "var(--ink-600, #666)", fontSize: 14 }}>
          {tr("settings.balance_label")}: <strong>{fmtNum(me.balance)} {tr("pay.pt")}</strong>
        </p>
        <Link to="/payments"><button>{tr("settings.go_charge")}</button></Link>
      </div>
    </div>
  );
}

function ProfileCard() {
  const me = useMe();
  const { t: tr } = useTranslation();
  const [nickname, setNickname] = useState(me?.nickname || "");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true); setMsg(null); setErr(null);
    try {
      const res = await api.updateProfile({ nickname });
      setCachedMe(res);
      setMsg(tr("settings.saved"));
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{tr("settings.basic_info")}</h3>
      <div style={{ fontSize: 13, color: "var(--ink-600, #666)", marginBottom: 8 }}>
        {tr("settings.email_label")}: {me?.email}
      </div>
      <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>{tr("settings.nickname")}</label>
      <input
        style={{ width: "100%", marginBottom: 8 }}
        value={nickname}
        onChange={(e) => setNickname(e.target.value)}
        placeholder={tr("settings.nickname")}
      />
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={save} disabled={saving}>{saving ? tr("settings.saving") : tr("settings.save")}</button>
        {msg && <span style={{ color: "green", fontSize: 13 }}>{msg}</span>}
        {err && <span style={{ color: "crimson", fontSize: 13 }}>{err}</span>}
      </div>
    </div>
  );
}

function DialectCard() {
  const me = useMe();
  const { t: tr } = useTranslation();
  const [dialect, setDialect] = useState(me?.answer_dialect || "standard");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save(next: string) {
    setDialect(next);
    setSaving(true); setMsg(null); setErr(null);
    try {
      const res = await api.updateProfile({ answer_dialect: next });
      setCachedMe(res);
      setMsg(tr("settings.dialect_saved"));
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{tr("settings.dialect_title")}</h3>
      <p style={{ color: "var(--ink-600, #666)", fontSize: 13, marginTop: 0 }}>
        {tr("settings.dialect_desc")}
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {DIALECTS.map((d) => (
          <button
            key={d.value}
            onClick={() => save(d.value)}
            disabled={saving}
            style={{
              padding: "6px 14px",
              borderRadius: 999,
              border: dialect === d.value ? "1px solid var(--brand-600, #0b7d73)" : "1px solid #d0d7de",
              background: dialect === d.value ? "rgba(13,148,136,.10)" : "transparent",
              color: dialect === d.value ? "var(--brand-600, #0b7d73)" : "inherit",
              cursor: "pointer",
            }}
          >
            {d.label}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 8, minHeight: 18 }}>
        {msg && <span style={{ color: "green", fontSize: 13 }}>{msg}</span>}
        {err && <span style={{ color: "crimson", fontSize: 13 }}>{err}</span>}
      </div>
    </div>
  );
}

function PasswordCard() {
  const { t: tr } = useTranslation();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!cur || !next) return;
    setSaving(true); setMsg(null); setErr(null);
    try {
      await api.changePassword(cur, next);
      setCur(""); setNext("");
      setMsg(tr("settings.pw_saved"));
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{tr("settings.pw_title")}</h3>
      <input
        type="password"
        style={{ width: "100%", marginBottom: 8 }}
        placeholder={tr("settings.pw_current_ph")}
        value={cur}
        onChange={(e) => setCur(e.target.value)}
      />
      <input
        type="password"
        style={{ width: "100%", marginBottom: 8 }}
        placeholder={tr("settings.pw_new_ph")}
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={save} disabled={saving || !cur || !next}>{saving ? tr("settings.changing") : tr("settings.change")}</button>
        {msg && <span style={{ color: "green", fontSize: 13 }}>{msg}</span>}
        {err && <span style={{ color: "crimson", fontSize: 13 }}>{err}</span>}
      </div>
    </div>
  );
}

const EMPTY_PROFILE: SajuProfileInput = {
  label: "",
  birth_date: "1990-01-01",
  birth_time: "12:00",
  calendar: "solar",
  is_leap_month: false,
  gender: "male",
  apply_true_solar_time: true,   // 메뉴 입력화면과 동일하게 진태양시 보정 기본 ON(일관성)
  birth_longitude: DEFAULT_LON,       // 서울 기본(출생지 선택 시 갱신)
  apply_equation_of_time: false,
  night_zi_mode: "yaja",
  is_default: false,
};

function SajuProfilesCard() {
  const { t: tr } = useTranslation();
  const [items, setItems] = useState<SajuProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<SajuProfileInput | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.listSajuProfiles();
      setItems(r.items);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function startCreate() {
    setEditId(null);
    setEditing({ ...EMPTY_PROFILE });
  }
  function startEdit(p: SajuProfile) {
    setEditId(p.id);
    setEditing({
      label: p.label,
      birth_date: p.birth_date,
      birth_time: p.birth_time || "",
      calendar: p.calendar,
      is_leap_month: p.is_leap_month,
      gender: p.gender,
      apply_true_solar_time: p.apply_true_solar_time,
      birth_longitude: p.birth_longitude ?? DEFAULT_LON,
      apply_equation_of_time: p.apply_equation_of_time ?? false,
      night_zi_mode: p.night_zi_mode ?? "yaja",
      is_default: p.is_default,
    });
  }

  async function save() {
    if (!editing || !editing.label.trim()) {
      setErr(tr("settings.label_required"));
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const body: SajuProfileInput = {
        ...editing,
        birth_time: editing.birth_time?.trim() ? editing.birth_time : null,
      };
      if (editId == null) await api.createSajuProfile(body);
      else await api.updateSajuProfile(editId, body);
      setEditing(null);
      setEditId(null);
      await refresh();
    } catch (e: any) {
      const m = String(e?.message || e);
      setErr(m.includes("profile_limit_reached") ? tr("settings.limit_reached") : m);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number) {
    if (!confirm(tr("settings.confirm_delete"))) return;
    try {
      await api.deleteSajuProfile(id);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  }

  async function makeDefault(id: number) {
    try {
      await api.updateSajuProfile(id, { is_default: true });
      await refresh();
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{tr("settings.profiles_title")}</h3>
      <p style={{ color: "var(--ink-600, #666)", fontSize: 13, marginTop: 0 }}>
        {tr("settings.profiles_desc")}
      </p>
      {err && <div style={{ color: "crimson", fontSize: 13, marginBottom: 8 }}>{err}</div>}
      {loading ? (
        <div style={{ fontSize: 13, color: "#888" }}>{tr("settings.loading")}</div>
      ) : (
        <div className="profile-list">
          {items.length === 0 && (
            <div style={{ fontSize: 13, color: "#888" }}>{tr("settings.empty")}</div>
          )}
          {items.map((p) => (
            <div key={p.id} className={`profile-row${p.is_default ? " is-default" : ""}`}>
              <span className="profile-info">
                <strong>{p.label}</strong>
                {p.is_default && <span className="badge">{tr("settings.badge_default")}</span>}
                <br />
                {p.birth_date}
                {p.birth_time ? ` ${p.birth_time}` : ""} ·{" "}
                {p.calendar === "lunar" ? tr("settings.lunar") : tr("settings.solar")} ·{" "}
                {p.gender === "female" ? tr("settings.female") : tr("settings.male")}
              </span>
              <span className="profile-actions">
                {!p.is_default && (
                  <button className="ghost" onClick={() => makeDefault(p.id)}>
                    {tr("settings.set_default")}
                  </button>
                )}
                <button className="ghost" onClick={() => startEdit(p)}>
                  {tr("settings.edit")}
                </button>
                <button className="ghost" onClick={() => remove(p.id)}>
                  {tr("settings.delete")}
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {editing ? (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--border, #eee)", paddingTop: 12 }}>
          <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>{tr("settings.label")}</label>
          <input
            style={{ width: "100%", marginBottom: 8 }}
            value={editing.label}
            onChange={(e) => setEditing({ ...editing, label: e.target.value })}
            placeholder={tr("settings.label_ph")}
          />
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>{tr("settings.birth_date")}</label>
              <input
                type="date"
                style={{ width: "100%" }}
                value={editing.birth_date}
                onChange={(e) => setEditing({ ...editing, birth_date: e.target.value })}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>{tr("settings.birth_time")}</label>
              <TimeSelect
                value={editing.birth_time || ""}
                onChange={(v) => setEditing({ ...editing, birth_time: v })}
              />
            </div>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
            <label style={{ fontSize: 13 }}>
              <select
                value={editing.calendar}
                onChange={(e) => setEditing({ ...editing, calendar: e.target.value as "solar" | "lunar" })}
              >
                <option value="solar">{tr("settings.solar")}</option>
                <option value="lunar">{tr("settings.lunar")}</option>
              </select>
            </label>
            <label style={{ fontSize: 13 }}>
              <select
                value={editing.gender}
                onChange={(e) => setEditing({ ...editing, gender: e.target.value as "male" | "female" })}
              >
                <option value="male">{tr("settings.male")}</option>
                <option value="female">{tr("settings.female")}</option>
              </select>
            </label>
            <label style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={!!editing.is_leap_month}
                onChange={(e) => setEditing({ ...editing, is_leap_month: e.target.checked })}
              />
              {tr("settings.leap_month")}
            </label>
            <label style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={!!editing.is_default}
                onChange={(e) => setEditing({ ...editing, is_default: e.target.checked })}
              />
              {tr("settings.default_profile")}
            </label>
          </div>
          <AdvancedBirthSettings
            value={editing}
            onChange={(patch) => setEditing((prev) => (prev ? { ...prev, ...patch } : prev))}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button onClick={save} disabled={saving}>
              {saving ? tr("settings.saving") : editId == null ? tr("settings.add") : tr("settings.save")}
            </button>
            <button className="ghost" onClick={() => { setEditing(null); setEditId(null); }}>
              {tr("settings.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <button style={{ marginTop: 12 }} onClick={startCreate}>
          {tr("settings.add_profile")}
        </button>
      )}
    </div>
  );
}
