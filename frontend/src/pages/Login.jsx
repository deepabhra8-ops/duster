import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Database,
  Eye,
  EyeOff,
  Lock,
  LogIn,
  ShieldCheck,
  User,
} from "lucide-react";

import { useAuth } from "../hooks/useAuth.js";
import { useLocalStorage } from "../hooks/useLocalStorage.js";
import { DEFAULT_ROUTE } from "../constants/appConfig.js";
import "../styles/login.css";

const FEATURES = [
  {
    icon: Database,
    tone: "is-blue",
    title: "Discover Your Data",
    body: "Profile your data structure, patterns and key statistics.",
  },
  {
    icon: ShieldCheck,
    tone: "is-green",
    title: "Ensure Data Quality",
    body: "Apply business rules and validation checks.",
  },
  {
    icon: BarChart3,
    tone: "is-violet",
    title: "Drive Better Decisions",
    body: "Identify issues early and build trust in your data.",
  },
];

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
    <div className="auth-screen">
      <section className="auth-brand">
        <div className="auth-brand-body">
          <span className="auth-rule" aria-hidden="true" />
          <h1 className="auth-headline">
            <span className="auth-headline-accent">DUSTER</span>
          </h1>
          <p className="auth-tagline">
            Data Quality Validator - profile, validate and monitor your data quality
          </p>

          <ul className="auth-features">
            {FEATURES.map(({ icon: Icon, tone, title, body }) => (
              <li className="auth-feature" key={title}>
                <span className={`auth-feature-icon ${tone}`} aria-hidden="true">
                  <Icon size={22} />
                </span>
                <span className="auth-feature-text">
                  <span className="auth-feature-title">{title}</span>
                  <span className="auth-feature-body">{body}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="auth-brand-foot">
          <span className="auth-rule" aria-hidden="true" />
          <p className="auth-strapline">Trusted data. Brighter outcomes.</p>
        </div>
      </section>

      <section className="auth-panel">
        <form className="auth-card" onSubmit={handleSubmit} noValidate>
          <div className="auth-card-brand">
            <span className="auth-card-logo">DUSTER</span>
          </div>

          <span className="auth-card-icon" aria-hidden="true">
            <LogIn size={26} />
          </span>
          <h2 className="auth-card-title">Sign In</h2>
          <p className="auth-card-sub">Continue to DUSTER</p>

          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="login-username">Username</label>
            <span className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">
                <User size={16} />
              </span>
              <input
                id="login-username"
                type="text"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </span>
          </div>

          <div className="auth-field">
            <label htmlFor="login-password">Password</label>
            <span className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">
                <Lock size={16} />
              </span>
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="auth-reveal"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <Eye size={16} aria-hidden="true" /> : <EyeOff size={16} aria-hidden="true" />}
              </button>
            </span>
          </div>

          <label className="auth-remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            Remember me
          </label>

          <button
            type="submit"
            className="btn btn-primary auth-submit"
            disabled={submitting || !username || !password}
          >
            {submitting ? (
              <>
                <span className="metadata-spinner" aria-hidden="true" />
                Logging in…
              </>
            ) : (
              <>
                Login
                <ArrowRight size={17} aria-hidden="true" />
              </>
            )}
          </button>

          <p className="auth-copyright">
            &copy; {new Date().getFullYear()} DUSTER. All rights reserved.
          </p>
        </form>
      </section>
    </div>
  );
}
