import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/auth/callback")({
  component: AuthCallback,
  beforeLoad: async () => {
    if (typeof window !== "undefined") {
      const hash = window.location.hash
      if (hash) {
        const params = new URLSearchParams(hash.substring(1))
        const accessToken = params.get("access_token")
        if (accessToken) {
          localStorage.setItem("access_token", accessToken)
          throw redirect({ to: "/" })
        }
      }
    }
    throw redirect({ to: "/login" })
  },
})

function AuthCallback() {
  return null
}
