import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import type { Subject } from "../api/types";
import { useLoad } from "../components/useLoad";

export function subjectLabel(subject: Subject, language: string): string {
  return language === "fr" ? subject.name_fr : subject.name_en;
}

/** Load the school's subjects and return a lookup from code to name in the current language. */
export function useSubjectName(): (code: string) => string {
  const { i18n } = useTranslation();
  const { state } = useLoad(() => api.subjects(), []);
  return useCallback(
    (code: string) => {
      const subject =
        state.status === "ready" ? state.data.find((s) => s.code === code) : undefined;
      return subject ? subjectLabel(subject, i18n.language) : code;
    },
    [state, i18n.language],
  );
}
