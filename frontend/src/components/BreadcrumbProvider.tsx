import { useState } from "react";
import type { ReactNode } from "react";

import { BreadcrumbContext } from "./breadcrumb";
import type { Crumb } from "./breadcrumb";

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  return (
    <BreadcrumbContext.Provider value={{ crumbs, setCrumbs }}>
      {children}
    </BreadcrumbContext.Provider>
  );
}
