/** OAuth callback이 fragment(#token=...&role=...)로 보내는 토큰을 캡처해 저장 후 /chat 로 이동. */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, setCachedMe, setRefreshToken, setToken } from "../api";

export default function OAuthSuccessPage() {
  const { t: tr } = useTranslation();
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const hash = window.location.hash.startsWith("#")
        ? window.location.hash.slice(1)
        : window.location.hash;
      const params = new URLSearchParams(hash);
      const token = params.get("token");
      if (!token) {
        setErr(tr("misc.oauth_no_token"));
        return;
      }
      setToken(token);
      setRefreshToken(params.get("refresh"));  // 무음 갱신용 refresh 저장(없으면 무시)
      try {
        const me = await api.me();
        setCachedMe(me);
        nav("/chat");
      } catch (e: any) {
        setErr(e?.message || tr("misc.oauth_profile_fail"));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ maxWidth: 480, margin: "60px auto", textAlign: "center" }}>
      {err ? (
        <div style={{ color: "crimson" }}>{err}</div>
      ) : (
        <div>{tr("misc.oauth_processing")}</div>
      )}
    </div>
  );
}
