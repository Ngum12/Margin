import { createContext, useContext } from "react";

import type { Language, Me } from "../api/types";

export type AuthState =
  | { status: "loading" }
  | { status: "signed_out" }
  | { status: "signed_in"; me: Me }
  | { status: "unavailable" };

interface AuthContextValue {
  state: AuthState;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  changeLanguage: (language: Language) => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

/** The signed-in session. Only call inside routes wrapped by RequireAuth. */
export function useMe(): Me {
  const { state } = useAuth();
  if (state.status !== "signed_in") throw new Error("useMe requires a signed-in user");
  return state.me;
}
