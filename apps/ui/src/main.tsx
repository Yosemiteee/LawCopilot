import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";

import { AppProvider } from "./app/AppContext";
import { AppRouter } from "./app/Router";
import "./styles/tokens.css";
import "./styles/globals.css";

const app = (
  <HashRouter>
    <AppProvider>
      <AppRouter />
    </AppProvider>
  </HashRouter>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  import.meta.env.DEV ? (
    <React.StrictMode>
      {app}
    </React.StrictMode>
  ) : (
    app
  )
);
