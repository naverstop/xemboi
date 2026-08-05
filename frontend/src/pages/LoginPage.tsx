import LoginForm from "../components/LoginForm";
import LanguageSwitch from "../components/LanguageSwitch";

export default function LoginPage() {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <LanguageSwitch compact />{/* ko/vi 전환 — 카드 좌상단 국기 배지(로고와 겹침 방지 위해 compact). auth-card(relative) 기준 */}
        <LoginForm variant="page" />
      </div>
    </div>
  );
}
