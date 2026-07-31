import LoginForm from "../components/LoginForm";

export default function LoginPage() {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <LoginForm variant="page" />
      </div>
    </div>
  );
}
