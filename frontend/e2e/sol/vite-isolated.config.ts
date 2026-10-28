import { defineConfig } from "vitest/config";
import base from "../../vite.config";
// Only used by the fixture suite. No proxy, credentials or API writes can reach a backend.
export default defineConfig({
  ...base,
  server: { host: "127.0.0.1", port: 5176, strictPort: true },
  plugins: [
    ...(base.plugins ?? []),
    {
      name: "sol-isolated-api",
      configureServer(server) {
        server.middlewares.use("/api", (_request, response) => {
          response.statusCode = 503;
          response.setHeader("content-type", "application/problem+json");
          response.end(
            JSON.stringify({
              title: "Isolated browser environment: API fixture required",
              status: 503,
            }),
          );
        });
      },
    },
  ],
});
