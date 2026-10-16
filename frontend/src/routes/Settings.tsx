import { PortalSettings } from "../components/PortalControls";
import { SchoolHardware } from "../components/SchoolHardware";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icon";

/** The teacher's own settings, and the school's administration for administrators. */
export default function Settings() {
  const { t } = useTranslation();
  const { state } = useAuth();
  if (state.status !== "signed_in") return null;
  const { user, school } = state.me;

  return (
    <section className="settings">
      <header className="page-header">
        <h1>{t("settings.title")}</h1>
      </header>
      <section className="panel" aria-labelledby="account-heading">
        <h2 id="account-heading">{t("settings.account")}</h2>
        <dl className="facts">
          <dt>{t("users.displayName")}</dt>
          <dd>{user.display_name}</dd>
          <dt>{t("users.username")}</dt>
          <dd>{user.username}</dd>
          <dt>{t("users.role")}</dt>
          <dd>{t(`roles.${user.role}`)}</dd>
          <dt>{t("settings.school")}</dt>
          <dd>{school.name}</dd>
        </dl>
      </section>
      <section className="panel" aria-labelledby="language-heading">
        <h2 id="language-heading">{t("settings.languageTitle")}</h2>
        <p>{t("settings.languageHelp")}</p>
      </section>
      {user.role === "admin" && (
        <>
          <SchoolHardware />
          <PortalSettings />
        </>
      )}
      {user.role === "admin" && (
        <section className="panel" aria-labelledby="admin-heading">
          <h2 id="admin-heading">{t("settings.adminTitle")}</h2>
          <ul className="link-list">
            <li>
              <Link to="/admin/users">
                <Icon name="classes" />
                <span>
                  <span className="link-list-label">{t("nav.users")}</span>
                  <span className="link-list-detail">{t("settings.usersHelp")}</span>
                </span>
              </Link>
            </li>
            <li>
              <Link to="/admin/classes">
                <Icon name="school" />
                <span>
                  <span className="link-list-label">{t("nav.classes")}</span>
                  <span className="link-list-detail">{t("settings.classesHelp")}</span>
                </span>
              </Link>
            </li>
            <li>
              <Link to="/admin/training-data">
                <Icon name="settings" />
                <span>
                  <span className="link-list-label">{t("nav.trainingData")}</span>
                  <span className="link-list-detail">{t("settings.trainingHelp")}</span>
                </span>
              </Link>
            </li>
          </ul>
        </section>
      )}
    </section>
  );
}
