import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, DIALECTS, useMe, setCachedMe } from "../api";
import type { SajuProfile, SajuProfileInput } from "../api";
import TimeSelect from "../components/TimeSelect";
import AdvancedBirthSettings from "../components/AdvancedBirthSettings";

export default function SettingsPage() {
  const me = useMe();

  if (!me) {
    return (
      <div style={{ padding: 20 }}>
        <h3>설정</h3>
        <p>로그인이 필요합니다. <Link to="/login">로그인</Link></p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 560, margin: "0 auto", display: "grid", gap: 16 }}>
      <h2 style={{ marginBottom: 0 }}>설정</h2>
      <ProfileCard />
      <SajuProfilesCard />
      <DialectCard />
      <PasswordCard />
      <div className="card">
        <h3 style={{ marginTop: 0 }}>결제 / 충전</h3>
        <p style={{ color: "var(--ink-600, #666)", fontSize: 14 }}>
          보유 포인트: <strong>{me.balance.toLocaleString()} P</strong>
        </p>
        <Link to="/payments"><button>충전하러 가기</button></Link>
      </div>
    </div>
  );
}

function ProfileCard() {
  const me = useMe();
  const [nickname, setNickname] = useState(me?.nickname || "");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true); setMsg(null); setErr(null);
    try {
      const res = await api.updateProfile({ nickname });
      setCachedMe(res);
      setMsg("저장되었습니다.");
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>기본 정보</h3>
      <div style={{ fontSize: 13, color: "var(--ink-600, #666)", marginBottom: 8 }}>
        이메일: {me?.email}
      </div>
      <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>닉네임</label>
      <input
        style={{ width: "100%", marginBottom: 8 }}
        value={nickname}
        onChange={(e) => setNickname(e.target.value)}
        placeholder="닉네임"
      />
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={save} disabled={saving}>{saving ? "저장중..." : "저장"}</button>
        {msg && <span style={{ color: "green", fontSize: 13 }}>{msg}</span>}
        {err && <span style={{ color: "crimson", fontSize: 13 }}>{err}</span>}
      </div>
    </div>
  );
}

function DialectCard() {
  const me = useMe();
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
      setMsg("답변 말투가 변경되었습니다.");
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>답변 말투(사투리)</h3>
      <p style={{ color: "var(--ink-600, #666)", fontSize: 13, marginTop: 0 }}>
        상담친구가 답변할 때 사용할 말투를 선택하세요.
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
              border: dialect === d.value ? "1px solid var(--brand-600, #0496d8)" : "1px solid #d0d7de",
              background: dialect === d.value ? "rgba(4,150,216,.10)" : "transparent",
              color: dialect === d.value ? "var(--brand-600, #0496d8)" : "inherit",
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
      setMsg("비밀번호가 변경되었습니다.");
    } catch (e: any) { setErr(e?.message || String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>비밀번호 변경</h3>
      <input
        type="password"
        style={{ width: "100%", marginBottom: 8 }}
        placeholder="현재 비밀번호"
        value={cur}
        onChange={(e) => setCur(e.target.value)}
      />
      <input
        type="password"
        style={{ width: "100%", marginBottom: 8 }}
        placeholder="새 비밀번호"
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={save} disabled={saving || !cur || !next}>{saving ? "변경중..." : "변경"}</button>
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
  birth_longitude: 126.98,       // 서울 기본(출생지 선택 시 갱신)
  apply_equation_of_time: false,
  night_zi_mode: "yaja",
  is_default: false,
};

function SajuProfilesCard() {
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
      birth_longitude: p.birth_longitude ?? 126.98,
      apply_equation_of_time: p.apply_equation_of_time ?? false,
      night_zi_mode: p.night_zi_mode ?? "yaja",
      is_default: p.is_default,
    });
  }

  async function save() {
    if (!editing || !editing.label.trim()) {
      setErr("이름(라벨)을 입력하세요.");
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
      setErr(m.includes("profile_limit_reached") ? "프로필은 최대 개수까지만 저장할 수 있습니다." : m);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("이 프로필을 삭제할까요?")) return;
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
      <h3 style={{ marginTop: 0 }}>사주 프로필 (가족·지인)</h3>
      <p style={{ color: "var(--ink-600, #666)", fontSize: 13, marginTop: 0 }}>
        본인 외 가족·지인의 사주를 저장해 두면 상담 시작 시 빠르게 불러올 수 있습니다.
      </p>
      {err && <div style={{ color: "crimson", fontSize: 13, marginBottom: 8 }}>{err}</div>}
      {loading ? (
        <div style={{ fontSize: 13, color: "#888" }}>불러오는 중...</div>
      ) : (
        <div className="profile-list">
          {items.length === 0 && (
            <div style={{ fontSize: 13, color: "#888" }}>저장된 프로필이 없습니다.</div>
          )}
          {items.map((p) => (
            <div key={p.id} className={`profile-row${p.is_default ? " is-default" : ""}`}>
              <span className="profile-info">
                <strong>{p.label}</strong>
                {p.is_default && <span className="badge">기본</span>}
                <br />
                {p.birth_date}
                {p.birth_time ? ` ${p.birth_time}` : ""} ·{" "}
                {p.calendar === "lunar" ? "음력" : "양력"} ·{" "}
                {p.gender === "female" ? "여성" : "남성"}
              </span>
              <span className="profile-actions">
                {!p.is_default && (
                  <button className="ghost" onClick={() => makeDefault(p.id)}>
                    기본
                  </button>
                )}
                <button className="ghost" onClick={() => startEdit(p)}>
                  수정
                </button>
                <button className="ghost" onClick={() => remove(p.id)}>
                  삭제
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {editing ? (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--border, #eee)", paddingTop: 12 }}>
          <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>이름(라벨)</label>
          <input
            style={{ width: "100%", marginBottom: 8 }}
            value={editing.label}
            onChange={(e) => setEditing({ ...editing, label: e.target.value })}
            placeholder="예: 어머니, 김친구"
          />
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>생년월일</label>
              <input
                type="date"
                style={{ width: "100%" }}
                value={editing.birth_date}
                onChange={(e) => setEditing({ ...editing, birth_date: e.target.value })}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>태어난 시각</label>
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
                <option value="solar">양력</option>
                <option value="lunar">음력</option>
              </select>
            </label>
            <label style={{ fontSize: 13 }}>
              <select
                value={editing.gender}
                onChange={(e) => setEditing({ ...editing, gender: e.target.value as "male" | "female" })}
              >
                <option value="male">남성</option>
                <option value="female">여성</option>
              </select>
            </label>
            <label style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={!!editing.is_leap_month}
                onChange={(e) => setEditing({ ...editing, is_leap_month: e.target.checked })}
              />
              윤달
            </label>
            <label style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={!!editing.is_default}
                onChange={(e) => setEditing({ ...editing, is_default: e.target.checked })}
              />
              기본 프로필
            </label>
          </div>
          <AdvancedBirthSettings
            value={editing}
            onChange={(patch) => setEditing((prev) => (prev ? { ...prev, ...patch } : prev))}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button onClick={save} disabled={saving}>
              {saving ? "저장중..." : editId == null ? "추가" : "저장"}
            </button>
            <button className="ghost" onClick={() => { setEditing(null); setEditId(null); }}>
              취소
            </button>
          </div>
        </div>
      ) : (
        <button style={{ marginTop: 12 }} onClick={startCreate}>
          + 프로필 추가
        </button>
      )}
    </div>
  );
}
