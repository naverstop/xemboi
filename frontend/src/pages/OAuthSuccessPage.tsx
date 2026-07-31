/** OAuth callback이 fragment(#token=...&role=...)로 보내는 토큰을 캡처해 저장 후 /chat 로 이동. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setCachedMe, setRefreshToken, setToken } from "../api";

export default function OAuthSuccessPage() {
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
        setErr("토큰을 찾을 수 없습니다.");
        return;
      }
      setToken(token);
      setRefreshToken(params.get("refresh"));  // 무음 갱신용 refresh 저장(없으면 무시)
      try {
        const me = await api.me();
        setCachedMe(me);
        nav("/chat");
      } catch (e: any) {
        setErr(e?.message || "프로필 조회 실패");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ maxWidth: 480, margin: "60px auto", textAlign: "center" }}>
      {err ? (
        <div style={{ color: "crimson" }}>{err}</div>
      ) : (
        <div>로그인 처리 중...</div>
      )}
    </div>
  );
}
