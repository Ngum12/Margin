import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useNavigate } from "react-router";

import { useAuth } from "../auth/useAuth";
import { LanguageSwitch } from "./LanguageSwitch";

export function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { state, signOut } = useAuth();
  const navigate = useNavigate();
  const me = state.status === "signed_in" ? state.me : null;

  return (
    <div className="page">
      <header className="header">
        <div className="brand">
          <span className="brand-name">{t("app.title")}</span>
          {me && <span className="muted brand-school">{me.school.name}</span>}
        </div>
        {me && (
          <nav className="nav" aria-label={t("nav.label")}>
            <NavLink to="/" end>
              {t("nav.exams")}
            </NavLink>
            {me.user.role === "admin" && (
              <>
                <NavLink to="/admin/classes">{t("nav.classes")}</NavLink>
                <NavLink to="/admin/users">{t("nav.users")}</NavLink>
              </>
            )}
          </nav>
        )}
        <div className="header-actions">
          <LanguageSwitch />
          {me && (
            <>
              <span className="muted">{me.user.display_name}</span>
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  void signOut().finally(() => {
                    void navigate("/signin");
                  });
                }}
              >
                {t("nav.signOut")}
              </button>
            </>
          )}
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}
