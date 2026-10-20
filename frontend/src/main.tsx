import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "@/App";
import { SessionProvider } from "@/features/auth/session";
import "@/i18n";
import "@/styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // Le sessioni scadute sono gestite dal modale di re-login, non con un retry.
      retry: (failureCount, error) =>
        failureCount < 2 && !(error instanceof Error && error.name === "ApiError"),
    },
  },
});

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Elemento #root non trovato.");
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
