import type { ServerPublic } from "@/client"

export function buildWebGokzUrl(target: { map?: string; room?: number }) {
  const url = new URL("/web-gokz/connect", window.location.origin)
  url.searchParams.set("launch", "1")
  if (target.map) url.searchParams.set("map", target.map)
  if (target.room) url.searchParams.set("room", String(target.room))
  return url.toString()
}

export function getWebGokzRoomId(server: ServerPublic): number | null {
  const room = server.source.room_id
  return server.source.type === "web_gokz" && (room === 1 || room === 2)
    ? room
    : null
}

export async function webGokzRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(
    `${(import.meta.env.VITE_WEB_GOKZ_API_URL || import.meta.env.VITE_API_URL).replace(/\/$/, "")}/v1/web-gokz${path}`,
    init,
  )
  if (!response.ok)
    throw new Error("Web GOKZ is unavailable. Please try again.")
  return response.json()
}
