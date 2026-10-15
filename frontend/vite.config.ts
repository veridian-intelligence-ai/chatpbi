import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// Endereços públicos dos serviços do backend (login e API). O código não tem
// endereço padrão, então o build só segue com os dois definidos.
const ENDERECOS_DO_BACKEND = ["VITE_AUTH_BASE_URL", "VITE_API_BASE_URL"];

function enderecosQueFaltam(mode: string): string[] {
  const env = { ...loadEnv(mode, __dirname, "VITE_"), ...process.env };
  return ENDERECOS_DO_BACKEND.filter((nome) => !env[nome]?.trim());
}

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  const faltam = enderecosQueFaltam(mode);
  if (faltam.length) {
    const aviso =
      `Faltam ${faltam.join(" e ")}: os endereços públicos dos serviços auth e backend, sem barra no fim. ` +
      "Na Vercel, em Settings, Environment Variables; no computador, em frontend/.env (veja o .env.example).";
    if (command === "build") throw new Error(aviso);
    console.warn(`\n[app] ${aviso}\n`);
  }

  return {
    server: {
      host: "::",
      port: 8080,
      hmr: {
        overlay: false,
      },
    },
    plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
      dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
    },
  };
});
