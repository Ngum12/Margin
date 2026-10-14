import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "./useAuth";

export function RequireAuth({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { state } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();

  if (state.status === "loading")
    return <p className="muted page-message">{t("common.loading")}</p>;
  if (state.status === "unavailable") {
    return (
      <p className="error page-message" role="alert">
        {t("errors.network.unreachable")}
      </p>
    );
  }
  if (state.status === "signed_out") {
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  }
  if (admin && state.me.user.role !== "admin") {
    return (
      <p className="error page-message" role="alert">
        {t("errors.auth.admin_required")}
      </p>
    );
  }
  return children;
}
