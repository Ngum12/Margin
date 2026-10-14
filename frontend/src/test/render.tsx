import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import App from "../App";
import { AuthProvider } from "../auth/AuthContext";

export function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
