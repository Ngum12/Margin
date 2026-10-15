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

// jsdom does not implement these browser methods; the review screen uses them.
Element.prototype.scrollIntoView = function scrollIntoView() {
  // Nothing to scroll in a test document.
};
Element.prototype.setPointerCapture = function setPointerCapture() {
  // Pointer capture has no effect in a test document.
};
