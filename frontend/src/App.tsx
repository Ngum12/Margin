import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchHealth } from "./api";
import { SUPPORTED_LANGUAGES } from "./i18n";

type ServerState = { kind: "checking" } | { kind: "ok"; version: string } | { kind: "unavailable" };

export default function App() {
  const { t, i18n } = useTranslation();
  const [server, setServer] = useState<ServerState>({ kind: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => {
        setServer({ kind: "ok", version: health.version });
      })
      .catch(() => {
        if (!controller.signal.aborted) setServer({ kind: "unavailable" });
      });
    return () => {
      controller.abort();
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = i18n.language;
    document.title = t("app.title");
  }, [i18n.language, t]);

  return (
    <div className="page">
      <header className="header">
        <h1>{t("app.title")}</h1>
        <label className="language-switch">
          <span>{t("language.label")}</span>
          <select
            value={i18n.language}
            onChange={(event) => void i18n.changeLanguage(event.target.value)}
          >
            {SUPPORTED_LANGUAGES.map((lng) => (
              <option key={lng} value={lng}>
                {t(`language.${lng}`)}
              </option>
            ))}
          </select>
        </label>
      </header>
      <main className="content">
        <p className="tagline">{t("app.tagline")}</p>
        <section className="card" aria-live="polite">
          <h2>{t("status.heading")}</h2>
          {server.kind === "checking" && <p>{t("status.checking")}</p>}
          {server.kind === "ok" && (
            <p className="status-ok">{t("status.ok", { version: server.version })}</p>
          )}
          {server.kind === "unavailable" && (
            <p className="status-error" role="alert">
              {t("status.unavailable")}
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
