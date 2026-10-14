import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import fr from "./locales/fr.json";

export const SUPPORTED_LANGUAGES = ["en", "fr"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

const STORAGE_KEY = "margin.language";

export const resources = {
  en: { translation: en },
  fr: { translation: fr },
} as const;

export function isLanguage(value: unknown): value is Language {
  return SUPPORTED_LANGUAGES.includes(value as Language);
}

/** Language chosen before signing in, remembered on this device only. */
export function storedLanguage(): Language {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return isLanguage(value) ? value : "en";
  } catch {
    return "en";
  }
}

export function rememberLanguage(language: Language): void {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Storage may be unavailable (private mode); the choice then lasts for this visit only.
  }
}

void i18n.use(initReactI18next).init({
  resources,
  lng: storedLanguage(),
  fallbackLng: "en",
  supportedLngs: SUPPORTED_LANGUAGES,
  interpolation: { escapeValue: false }, // React already escapes output.
  returnNull: false,
});

export default i18n;
