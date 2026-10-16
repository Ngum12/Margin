import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
import { Brand } from "./Brand";
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

  if (!me || location.pathname === "/student" || location.pathname.startsWith("/student/")) {
    // One layout for "loading" and "signed out", so the sign-in form keeps what was typed.
    // Until the session is known there is no language menu: a choice made now would be lost.
    return (
      <div className="shell-public">
        <header className="public-header">
          <Link to="/signin" className="public-brand" aria-label={t("app.title")}>
            <Brand />
          </Link>
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
      <header className="studio-header">
        <Link to="/" className="studio-brand" aria-label={t("app.title")}>
          <Brand />
        </Link>
        <nav className="studio-navigation" aria-label={t("nav.label")}>
          <ul>
            <WorkspaceLink to="/" icon="exams" label={t("nav.exams")} active={examsActive} />
            <WorkspaceLink to="/queue" icon="queue" label={t("nav.queue")} />
            {me.user.role === "admin" && (
              <WorkspaceLink to="/admin/classes" icon="classes" label={t("nav.classes")} />
            )}
            <WorkspaceLink to="/settings" icon="settings" label={t("nav.settings")} />
          </ul>
        </nav>
        <div className="studio-institution">
          <Icon name="school" size={17} />
          <span>{me.school.name}</span>
        </div>
      </header>
      <div className="workspace">
        <TopBar />
        <main id="main" className={wide ? "content content-wide" : "content"} tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

function WorkspaceLink({
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
        className={({ isActive }) =>
          (active ?? isActive) ? "studio-nav-link active" : "studio-nav-link"
        }
        aria-current={active ? "page" : undefined}
      >
        <Icon name={icon} size={20} />
        <span>{label}</span>
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
        <span className="topbar-user">
          <span className="user-monogram" aria-hidden="true">
            {me.user.display_name.slice(0, 1)}
          </span>
          {me.user.display_name}
        </span>
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
