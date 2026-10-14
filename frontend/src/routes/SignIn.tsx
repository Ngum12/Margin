import { useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
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
    <section className="card narrow">
      <h1>{t("signIn.title")}</h1>
      <p className="muted">{t("signIn.intro")}</p>
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
        </button>
      </form>
    </section>
  );
}
