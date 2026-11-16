import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En dev local (npm run dev) on proxifie /api vers le back lancé à côté.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node" },
});
