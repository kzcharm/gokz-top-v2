import { useQuery } from "@tanstack/react-query"
import { useEffect, useEffectEvent, useState } from "react"

import { useAdminMode } from "@/components/admin-mode-provider"
import { Alert, AlertDescription } from "@/components/ui/alert"
import useAuth from "@/hooks/useAuth"
import { canModerateBansAndRecords } from "@/lib/user-roles"

import {
  DeleteCourseRecordsButton,
  useRecordAdminActions,
} from "./admin-actions"
import { RecentRecordsTable } from "./RecentRecordsTable"
import {
  buildRecentRecordsWebSocketUrl,
  compareRecentRecords,
  fetchRecentRecords,
  RECENT_RECORDS_LIVE_LIMIT,
  type RecentRecord,
  type RecentRecordRealtimeEvent,
  upsertRecentRecord,
} from "./utils"

export function RecentRecordsPanel() {
  const { enabled: adminModeEnabled } = useAdminMode()
  const { user } = useAuth()
  const { bulkDeleteMutation } = useRecordAdminActions()
  const [records, setRecords] = useState<RecentRecord[]>([])
  const canAdministerRecords =
    adminModeEnabled && canModerateBansAndRecords(user)

  const recordsQuery = useQuery({
    queryKey: ["recent-records", "dashboard"],
    queryFn: () => fetchRecentRecords(RECENT_RECORDS_LIVE_LIMIT),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  useEffect(() => {
    if (!recordsQuery.data) {
      return
    }

    setRecords(
      [...recordsQuery.data.data]
        .sort(compareRecentRecords)
        .slice(0, RECENT_RECORDS_LIVE_LIMIT),
    )
  }, [recordsQuery.data])

  const handleRealtimeEvent = useEffectEvent(
    (event: RecentRecordRealtimeEvent) => {
      setRecords((currentRecords) => {
        if (event.type === "record.snapshot") {
          return [...event.records]
            .sort(compareRecentRecords)
            .slice(0, RECENT_RECORDS_LIVE_LIMIT)
        }

        return upsertRecentRecord(
          currentRecords,
          event.record,
          RECENT_RECORDS_LIVE_LIMIT,
        )
      })
    },
  )

  useEffect(() => {
    let websocket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let shouldReconnect = true

    const connect = () => {
      websocket = new WebSocket(buildRecentRecordsWebSocketUrl())

      websocket.onopen = () => {
        attempt = 0
      }

      websocket.onmessage = (message) => {
        try {
          handleRealtimeEvent(
            JSON.parse(message.data) as RecentRecordRealtimeEvent,
          )
        } catch {
          websocket?.close()
        }
      }

      websocket.onclose = () => {
        if (!shouldReconnect) {
          return
        }

        attempt += 1
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        reconnectTimer = setTimeout(connect, delay)
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
  }, [])

  return (
    <div className="flex flex-col gap-4">
      {recordsQuery.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load recent records. Reload the page and try again.
          </AlertDescription>
        </Alert>
      ) : null}

      <RecentRecordsTable
        records={records}
        renderAdminActions={
          canAdministerRecords
            ? (record) => (
                <DeleteCourseRecordsButton
                  bulkDeleteMutation={bulkDeleteMutation}
                  record={{
                    player: {
                      display_name: record.player.alias ?? record.player.name,
                      steamid64: record.player.steamid64,
                    },
                    map_id: record.map.id,
                    map_name: record.map.name,
                    stage: record.stage,
                  }}
                />
              )
            : undefined
        }
      />
    </div>
  )
}
