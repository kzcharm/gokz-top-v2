import { useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useEffect } from "react"

import { OpenAPI } from "@/client"
import { invalidateDisplayPlayerCache } from "@/lib/player-graphql"

type PlayerSteamProfileRealtimeEvent = {
  type: "player.steam-profile-updated"
  steamid64: string
}

function buildPlayerSteamProfileWebSocketUrl() {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const protocol = baseUrl.protocol === "https:" ? "wss:" : "ws:"
  const normalizedPath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")

  return `${protocol}//${baseUrl.host}${normalizedPath}/v1/ws/players`
}

function isPlayerSteamProfileRealtimeEvent(
  value: unknown,
): value is PlayerSteamProfileRealtimeEvent {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    value.type === "player.steam-profile-updated" &&
    "steamid64" in value &&
    typeof value.steamid64 === "string"
  )
}

export function PlayerSteamProfileUpdatesProvider({
  children,
}: {
  children: ReactNode
}) {
  const queryClient = useQueryClient()

  useEffect(() => {
    let websocket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let shouldReconnect = true

    const connect = () => {
      websocket = new WebSocket(buildPlayerSteamProfileWebSocketUrl())

      websocket.onopen = () => {
        attempt = 0
      }

      websocket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as unknown
          if (!isPlayerSteamProfileRealtimeEvent(event)) {
            return
          }
          invalidateDisplayPlayerCache(event.steamid64)
          void queryClient.invalidateQueries({
            queryKey: ["graphql", "player", event.steamid64],
          })
          void queryClient.invalidateQueries({
            queryKey: ["profile-player"],
          })
        } catch {
          websocket?.close()
        }
      }

      websocket.onclose = () => {
        if (!shouldReconnect) {
          return
        }
        attempt += 1
        reconnectTimer = setTimeout(
          connect,
          Math.min(1000 * 2 ** attempt, 15_000),
        )
      }

      websocket.onerror = () => {
        websocket?.close()
      }
    }

    connect()

    return () => {
      shouldReconnect = false
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      websocket?.close()
    }
  }, [queryClient])

  return children
}
