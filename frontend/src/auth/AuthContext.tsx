import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, setCsrfToken } from "../api/client";
import { api } from "../api/endpoints";
import type { Language, Me } from "../api/types";
import { rememberLanguage } from "../i18n";
import { AuthContext } from "./useAuth";
import type { AuthState } from "./useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const applySession = useCallback(
    (me: Me) => {
      setCsrfToken(me.csrf_token);
      setState({ status: "signed_in", me });
      void i18n.changeLanguage(me.user.preferred_language);
      rememberLanguage(me.user.preferred_language);
    },
    [i18n],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((me) => {
        if (!cancelled) applySession(me);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const unavailable = error instanceof ApiError && error.status !== 401;
        setState({ status: unavailable ? "unavailable" : "signed_out" });
      });
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      applySession(await api.login(username, password));
    },
    [applySession],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setCsrfToken(null);
      setState({ status: "signed_out" });
    }
  }, []);

  const changeLanguage = useCallback(
    async (language: Language) => {
      await i18n.changeLanguage(language);
      rememberLanguage(language);
      if (state.status === "signed_in") {
        setState({ status: "signed_in", me: await api.setLanguage(language) });
      }
    },
    [i18n, state.status],
  );

  const value = useMemo(
    () => ({ state, signIn, signOut, changeLanguage }),
    [state, signIn, signOut, changeLanguage],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
