import { createContext, useContext, useEffect } from "react";

/** One step of the top bar's breadcrumb (School / Class / Exam). */
export interface Crumb {
  label: string;
  to?: string;
}

export interface BreadcrumbState {
  crumbs: Crumb[];
  setCrumbs: (crumbs: Crumb[]) => void;
}

export const BreadcrumbContext = createContext<BreadcrumbState>({
  crumbs: [],
  setCrumbs: () => undefined,
});

export function useCrumbs(): Crumb[] {
  return useContext(BreadcrumbContext).crumbs;
}

/** A screen names where it is; the crumbs are cleared when it leaves. */
export function useBreadcrumb(crumbs: Crumb[]): void {
  const { setCrumbs } = useContext(BreadcrumbContext);
  const key = JSON.stringify(crumbs);
  useEffect(() => {
    setCrumbs(JSON.parse(key) as Crumb[]);
    return () => {
      setCrumbs([]);
    };
  }, [key, setCrumbs]);
}
