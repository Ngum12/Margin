import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCrumbs } from "./breadcrumb";
import { BreadcrumbProvider } from "./BreadcrumbProvider";
import { Icon } from "./Icon";
import type { IconName } from "./icons";
import { LanguageSwitch } from "./LanguageSwitch";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <BreadcrumbProvider>
      <Shell>{children}</Shell>
    </BreadcrumbProvider>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { state } = useAuth();
  const location = useLocation();
  const me = state.status === "signed_in" ? state.me : null;

  if (!me) {
    // One layout for "loading" and "signed out", so the sign-in form keeps what was typed.
    // Until the session is known there is no language menu: a choice made now would be lost.
    return (
      <div className="shell-public">
        <header className="public-header">
          <span className="public-brand">{t("app.title")}</span>
          {state.status !== "loading" && <LanguageSwitch />}
        </header>
        <main className="public-main">{children}</main>
      </div>
    );
  }

  // The review desk uses the whole width; other screens keep a readable measure.
  const wide = /\/review\//.test(location.pathname);
  const examsActive = location.pathname === "/" || location.pathname.startsWith("/exams");
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t("nav.skip")}
      </a>
      <aside className="rail">
        <Link to="/" className="rail-school">
          <Icon name="school" size={20} />
          <span className="rail-label">
            <span className="rail-school-name">{me.school.name}</span>
            <span className="rail-app">{t("app.title")}</span>
          </span>
        </Link>
        <nav aria-label={t("nav.label")}>
          <ul className="rail-nav">
            {me.user.role === "admin" && (
              <RailLink to="/admin/classes" icon="classes" label={t("nav.classes")} />
            )}
            <RailLink to="/" icon="exams" label={t("nav.exams")} active={examsActive} />
            <RailLink to="/queue" icon="queue" label={t("nav.queue")} />
            <RailLink to="/settings" icon="settings" label={t("nav.settings")} />
          </ul>
        </nav>
      </aside>
      <div className="workspace">
        <TopBar />
        <main id="main" className={wide ? "content content-wide" : "content"} tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

function RailLink({
  to,
  icon,
  label,
  active,
}: {
  to: string;
  icon: IconName;
  label: string;
  active?: boolean;
}) {
  return (
    <li>
      <NavLink
        to={to}
        end
        title={label}
        className={({ isActive }) => ((active ?? isActive) ? "rail-link active" : "rail-link")}
        aria-current={active ? "page" : undefined}
      >
        <Icon name={icon} size={20} />
        <span className="rail-label">{label}</span>
      </NavLink>
    </li>
  );
}

function TopBar() {
  const { t } = useTranslation();
  const { state, signOut } = useAuth();
  const navigate = useNavigate();
  const crumbs = useCrumbs();
  const me = state.status === "signed_in" ? state.me : null;
  if (!me) return null;

  return (
    <header className="topbar">
      <nav className="breadcrumb" aria-label={t("nav.breadcrumb")}>
        <ol>
          <li>
            <Link to="/">{me.school.name}</Link>
          </li>
          {crumbs.map((crumb, index) => (
            <li key={`${crumb.label}-${String(index)}`}>
              {crumb.to && index < crumbs.length - 1 ? (
                <Link to={crumb.to}>{crumb.label}</Link>
              ) : (
                <span aria-current={index === crumbs.length - 1 ? "page" : undefined}>
                  {crumb.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>
      <div className="topbar-actions">
        <LanguageSwitch />
        <span className="topbar-user">{me.user.display_name}</span>
        <button
          type="button"
          className="button-quiet"
          onClick={() => {
            void signOut().finally(() => {
              void navigate("/signin");
            });
          }}
        >
          <Icon name="signOut" />
          {t("nav.signOut")}
        </button>
      </div>
    </header>
  );
}
