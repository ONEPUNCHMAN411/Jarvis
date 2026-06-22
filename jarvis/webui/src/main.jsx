import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { StoreProvider } from "./store.jsx";
import "@fontsource-variable/onest";
import "@fontsource-variable/jetbrains-mono";
import "./theme.css";

createRoot(document.getElementById("root")).render(
  <StoreProvider>
    <App />
  </StoreProvider>
);
