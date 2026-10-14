import { useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/endpoints";
import type { Language, Role, User } from "../../api/types";
import { useMe } from "../../auth/useAuth";
import { ErrorMessage, Field, Loading } from "../../components/ui";
import { useLoad } from "../../components/useLoad";

const MIN_PASSWORD = 8;

export default function Users() {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => api.users(), []);
  const [error, setError] = useState<unknown>(null);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <h1>{t("users.title")}</h1>
      <NewUserForm onCreated={reload} />
      <ErrorMessage error={error} />
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorMessage error={state.error} />}
      {state.status === "ready" && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("users.username")}</th>
                <th>{t("users.displayName")}</th>
                <th>{t("users.role")}</th>
                <th>{t("users.status")}</th>
                <th>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {state.data.map((user) => (
                <UserRow key={user.id} user={user} act={act} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function UserRow({ user, act }: { user: User; act: (a: () => Promise<unknown>) => Promise<void> }) {
  const { t } = useTranslation();
  const me = useMe();
  const [password, setPassword] = useState("");
  const [resetting, setResetting] = useState(false);

  return (
    <tr className={user.is_active ? undefined : "inactive"}>
      <td>{user.username}</td>
      <td>{user.display_name}</td>
      <td>
        <select
          aria-label={t("users.role")}
          value={user.role}
          onChange={(e) =>
            void act(() => api.updateUser(user.id, { role: e.target.value as Role }))
          }
        >
          <option value="teacher">{t("roles.teacher")}</option>
          <option value="admin">{t("roles.admin")}</option>
        </select>
      </td>
      <td>{user.is_active ? t("users.active") : t("users.inactive")}</td>
      <td className="row-actions">
        {user.id !== me.user.id && (
          <button
            type="button"
            className="button-secondary"
            onClick={() => void act(() => api.updateUser(user.id, { is_active: !user.is_active }))}
          >
            {user.is_active ? t("users.deactivate") : t("users.reactivate")}
          </button>
        )}
        {resetting ? (
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                await api.resetPassword(user.id, password);
                setPassword("");
                setResetting(false);
              });
            }}
          >
            <input
              type="password"
              autoComplete="new-password"
              aria-label={t("users.newPassword")}
              placeholder={t("users.newPassword")}
              minLength={MIN_PASSWORD}
              required
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
              }}
            />
            <button type="submit">{t("common.save")}</button>
          </form>
        ) : (
          <button
            type="button"
            className="button-secondary"
            onClick={() => {
              setResetting(true);
            }}
          >
            {t("users.resetPassword")}
          </button>
        )}
      </td>
    </tr>
  );
}

function NewUserForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("teacher");
  const [language, setLanguage] = useState<Language>("en");
  const [error, setError] = useState<unknown>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createUser({
        username,
        display_name: displayName,
        password,
        role,
        preferred_language: language,
      });
      setUsername("");
      setDisplayName("");
      setPassword("");
      onCreated();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <details className="card">
      <summary>{t("users.add")}</summary>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <div className="form-row">
          <Field label={t("users.username")} hint={t("users.usernameHint")}>
            <input
              required
              autoCapitalize="none"
              pattern="[A-Za-z0-9][A-Za-z0-9._\-]*"
              minLength={3}
              maxLength={64}
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
              }}
            />
          </Field>
          <Field label={t("users.displayName")}>
            <input
              required
              maxLength={200}
              value={displayName}
              onChange={(e) => {
                setDisplayName(e.target.value);
              }}
            />
          </Field>
          <Field label={t("users.password")} hint={t("users.passwordHint", { min: MIN_PASSWORD })}>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
              }}
            />
          </Field>
          <Field label={t("users.role")}>
            <select
              value={role}
              onChange={(e) => {
                setRole(e.target.value as Role);
              }}
            >
              <option value="teacher">{t("roles.teacher")}</option>
              <option value="admin">{t("roles.admin")}</option>
            </select>
          </Field>
          <Field label={t("language.label")}>
            <select
              value={language}
              onChange={(e) => {
                setLanguage(e.target.value as Language);
              }}
            >
              <option value="en">{t("language.en")}</option>
              <option value="fr">{t("language.fr")}</option>
            </select>
          </Field>
        </div>
        <ErrorMessage error={error} />
        <button type="submit">{t("users.create")}</button>
      </form>
    </details>
  );
}
