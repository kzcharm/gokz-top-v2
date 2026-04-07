import path from "node:path"
import { fileURLToPath } from "node:url"
import dotenv from "dotenv"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

dotenv.config({ path: path.join(__dirname, "../../.env") })

function getEnvVar(name: string): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(`Environment variable ${name} is undefined`)
  }
  return value
}

export const superUserSteamid64 = Number(getEnvVar("SUPER_USER_STEAMID64"))
export const apiUrl = process.env.VITE_API_URL || "http://localhost:8000"
export const testAuthHelpersEnabled =
  process.env.ENABLE_TEST_AUTH_HELPERS === "true"
