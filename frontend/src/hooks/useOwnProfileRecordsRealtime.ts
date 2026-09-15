import { useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

import { buildRecentRecordsWebSocketUrl } from "@/components/Records/utils"
import type { AppScope } from "@/components/scope-provider"

function getUpsertedRecordSteamid64(value: unknown) {
  if (
    typeof value !== "object" ||
    value === null ||
    !("type" in value) ||
    value.type !== "record.upserted" ||
    !("record" in value) ||
    typeof value.record !== "object" ||
    value.record === null ||
    !("player" in value.record) ||
    typeof value.record.player !== "object" ||
    value.record.player === null ||
    !("steamid64" in value.record.player) ||
    typeof value.record.player.steamid64 !== "string"
  ) {
    return null
  }

  return value.record.player.steamid64
}

export function useOwnProfileRecordsRealtime({
  enabled,
  scope,
  steamid64,
}: {
  enabled: boolean
  scope: AppScope
  steamid64: string | null
}) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!enabled || !steamid64) {
      return
    }

    let websocket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let shouldReconnect = true

    const invalidateProfileRecords = () => {
      void queryClient.invalidateQueries({
        queryKey: ["profile-records", steamid64],
      })
      void queryClient.invalidateQueries({
        queryKey: ["profile-map-wrs", scope],
      })
    }

    const connect = () => {
      websocket = new WebSocket(
        buildRecentRecordsWebSocketUrl(scope, steamid64),
      )

      websocket.onopen = () => {
        attempt = 0
        invalidateProfileRecords()
      }

      websocket.onmessage = (message) => {
        try {
          const eventSteamid64 = getUpsertedRecordSteamid64(
            JSON.parse(message.data) as unknown,
          )
          if (eventSteamid64 === steamid64) {
            invalidateProfileRecords()
          }
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
  }, [enabled, queryClient, scope, steamid64])
}
