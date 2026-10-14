import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/useAuth";
import { isLanguage, SUPPORTED_LANGUAGES } from "../i18n";

export function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  const { changeLanguage } = useAuth();

  return (
    <label className="language-switch">
      <span>{t("language.label")}</span>
      <select
        value={i18n.language}
        onChange={(event) => {
          if (isLanguage(event.target.value)) void changeLanguage(event.target.value);
        }}
      >
        {SUPPORTED_LANGUAGES.map((lng) => (
          <option key={lng} value={lng}>
            {t(`language.${lng}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
