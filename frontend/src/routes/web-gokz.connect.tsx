import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { AppShell } from "@/components/Common/AppShell"
import { Button } from "@/components/ui/button"
import { redirectToSteamLogin } from "@/lib/auth"
import { getReplayViewerBaseUrl } from "@/lib/replay-viewer"
import { webGokzRequest } from "@/lib/web-gokz"

export const Route = createFileRoute("/web-gokz/connect")({
  component: Connect,
})

function Connect() {
  const [error, setError] = useState("")
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const launch = params.get("launch") === "1"
    const returnTo = `/web-gokz/connect${window.location.search}`
    const game = new URL("/practice", getReplayViewerBaseUrl())
    const room = params.get("room")
    const map = params.get("map")
    if (room === "1" || room === "2") game.searchParams.set("room", room)
    else if (map && /^[A-Za-z0-9_-]{1,128}$/.test(map))
      game.searchParams.set("map", map)
    if (!launch && !window.opener) {
      setError("Open this sign-in window from Web GOKZ.")
      return
    }
    const token = localStorage.getItem("access_token")
    if (!token) {
      if (launch && !game.searchParams.has("room")) {
        window.location.replace(game.toString())
        return
      }
      redirectToSteamLogin({ returnTo })
      return
    }
    let cancelled = false
    if (launch) {
      void webGokzRequest<{ code: string }>("/launch", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(({ code }) => {
          if (cancelled) return
          game.hash = new URLSearchParams({ login_code: code }).toString()
          window.location.replace(game.toString())
        })
        .catch(() => {
          if (!cancelled)
            setError("Web GOKZ could not be opened. Sign in again to continue.")
        })
      return () => {
        cancelled = true
      }
    }
    void webGokzRequest<{ access_token: string; player: unknown }>("/session", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((session) => {
        if (cancelled) return
        window.opener?.postMessage(
          { type: "web-gokz-session", ...session },
          getReplayViewerBaseUrl().origin,
        )
        window.close()
      })
      .catch(() => {
        if (!cancelled)
          setError(
            "Your session could not be shared. Sign in again to continue.",
          )
      })
    return () => {
      cancelled = true
    }
  }, [])
  return (
    <AppShell>
      <div className="mx-auto max-w-lg space-y-4 py-16">
        <h1 className="text-2xl font-semibold">Sign in to Web GOKZ</h1>
        <output>{error || "Connecting your GOKZ.TOP account…"}</output>
        {error ? (
          <Button
            onClick={() =>
              redirectToSteamLogin({
                returnTo: `/web-gokz/connect${window.location.search}`,
              })
            }
          >
            Sign in with Steam
          </Button>
        ) : null}
      </div>
    </AppShell>
  )
}
