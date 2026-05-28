import { execFileSync } from "node:child_process"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig, type Plugin } from "vite"

function getAppVersion(): string {
  const envVersion = process.env.VITE_APP_VERSION?.trim()

  if (envVersion) {
    return envVersion
  }

  try {
    return execFileSync(
      "bash",
      [path.resolve(__dirname, "../scripts/get-app-version.sh")],
      {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
        cwd: __dirname,
      },
    ).trim()
  } catch {
    return "dev"
  }
}

function localDevFavicon(): Plugin {
  return {
    name: "local-dev-favicon",
    apply: "serve",
    transformIndexHtml(html) {
      return html.replace(
        /<link rel="icon" type="image\/png" sizes="32x32" href="\/favicon-32x32\.png" \/>/,
        '<link rel="icon" type="image/svg+xml" href="/favicon-dev.svg" />',
      )
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(getAppVersion()),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    localDevFavicon(),
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
})
