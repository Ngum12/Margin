import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

import i18n from "../i18n";

// Generous waits: school laptops and CI machines can be slow under load.
configure({ asyncUtilTimeout: 5000 });

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage("en");
});
