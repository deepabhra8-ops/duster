import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Lock, LogIn, User } from "lucide-react";

import { Alert, Button, Panel } from "../design-system/components/index.js";
import { useAuth } from "../hooks/useAuth.js";
import { useLocalStorage } from "../hooks/useLocalStorage.js";
import { DEFAULT_ROUTE } from "../constants/appConfig.js";
import "./Login.css";

const REMEMBERED_USER_KEY = "dq_remembered_username";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [rememberedUser, setRememberedUser] = useLocalStorage(REMEMBERED_USER_KEY, "");
  const [username, setUsername] = useState(rememberedUser || "");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(Boolean(rememberedUser));
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    const result = await login({ username, password });

    setSubmitting(false);
    if (!result.ok) {
      setError(result.error || "Invalid username or password");
      return;
    }

    setRememberedUser(remember ? username : "");
    navigate(DEFAULT_ROUTE, { replace: true });
  }

  return (
    <div className="login-screen">
      <Panel>
        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="login-brand">
            <img src="/icons/dq-brand.svg" width={36} height={36} alt="" aria-hidden="true" />
            <div>
              <div className="login-title">Duster Console</div>
              <div className="login-subtitle">Sign in to continue</div>
            </div>
          </div>

          {error ? (
            <Alert tone="danger" title="Sign-in failed">
              {error}
            </Alert>
          ) : null}

          <label className="login-field">
            <span className="login-label">Username</span>
            <span className="login-input-wrap">
              <User size={15} aria-hidden="true" />
              <input
                type="text"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </span>
          </label>

          <label className="login-field">
            <span className="login-label">Password</span>
            <span className="login-input-wrap">
              <Lock size={15} aria-hidden="true" />
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="login-reveal"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <Eye size={15} aria-hidden="true" /> : <EyeOff size={15} aria-hidden="true" />}
              </button>
            </span>
          </label>

          <label className="login-remember">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span>Remember me</span>
          </label>

          <Button register="primary" type="submit" disabled={submitting || !username || !password} style={{ width: "100%", justifyContent: "center" }}>
            <LogIn size={15} aria-hidden="true" />
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Panel>
    </div>
  );
}
