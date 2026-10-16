import { useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
import { MarkingPreview } from "../components/MarkingPreview";
import { Icon } from "../components/Icon";
import { ErrorMessage, Field } from "../components/ui";

export default function SignIn() {
  const { t } = useTranslation();
  const { state, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (state.status === "signed_in") return <Navigate to={from} replace />;

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(username, password);
      void navigate(from, { replace: true });
    } catch (err) {
      setError(err);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="signin-experience">
      <Link to="/student" className="student-entry">
        {t("portal.signin")}
      </Link>
      <section className="signin-story" aria-labelledby="story-title">
        <div className="story-intro">
          <p className="eyebrow story-eyebrow">
            <span />
            {t("studio.forTeachers")}
          </p>
          <h2 id="story-title">
            {t("studio.heroLine1")}
            <br />
            <em>{t("studio.heroLine2")}</em>
          </h2>
          <p className="story-description">{t("studio.heroDescription")}</p>
        </div>
        <MarkingPreview />
        <div className="story-footer">
          <span>{t("studio.privateByDesign")}</span>
          <span>{t("studio.youDecide")}</span>
        </div>
      </section>
      <section className="signin-panel">
        <div className="signin-form-wrap">
          <p className="eyebrow signin-kicker">{t("studio.yourWorkspace")}</p>
          <h1>{t("signIn.title")}</h1>
          <p className="signin-intro">{t("signIn.intro")}</p>
          <form onSubmit={(e) => void submit(e)} className="form">
            <Field label={t("signIn.username")}>
              <input
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                required
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                }}
              />
            </Field>
            <Field label={t("signIn.password")}>
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                }}
              />
            </Field>
            <ErrorMessage error={error} />
            <button type="submit" disabled={busy}>
              {busy ? t("signIn.submitting") : t("signIn.submit")}
              <Icon name="next" size={20} />
            </button>
          </form>
          <p className="signin-help">{t("studio.accessHelp")}</p>
          <div className="signin-assurance">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z" />
              <path d="m8 12 3 3 5-6" />
            </svg>
            <div>
              <strong>{t("studio.localTitle")}</strong>
              <span>{t("studio.localDescription")}</span>
            </div>
          </div>
        </div>
        <footer className="signin-footer">
          <span>{t("studio.builtFor")}</span>
          <span>© {new Date().getFullYear()} Margin</span>
        </footer>
      </section>
    </div>
  );
}
