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
  identifier,
  canonicalIdentifier,
}: {
  enabled: boolean
  scope: AppScope
  identifier: string
  canonicalIdentifier: string | null
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
      for (const queryKey of [
        ["profile-records", steamid64],
        ["profile-player", identifier],
        ["profile-stats", canonicalIdentifier],
        ["profile-points-standing", canonicalIdentifier],
        ["profile-pinned-records", steamid64],
        ["profile-record-ranks"],
        ["player-leaderboard"],
        ["graphql", "players"],
      ]) {
        void queryClient.invalidateQueries({ queryKey })
      }
      void queryClient.invalidateQueries({
        queryKey: ["profile-map-wrs", scope],
      })
    }

    const connect = () => {
      websocket = new WebSocket(
        buildRecentRecordsWebSocketUrl("OVR", steamid64),
      )

      websocket.onopen = () => {
        attempt = 0
        // Reconcile records missed while this page had no subscription.
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
  }, [canonicalIdentifier, enabled, identifier, queryClient, scope, steamid64])
}
