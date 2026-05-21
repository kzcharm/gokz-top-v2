function getReplayViewerBaseUrl() {
  const configuredBase = import.meta.env.VITE_REPLAY_VIEWER_URL?.trim()
  const fallbackBase = import.meta.env.DEV
    ? "http://localhost:5180"
    : "https://replay-viewer.kzcharm.com"

  return new URL(configuredBase || fallbackBase, window.location.origin)
}

export function buildRunReplayViewerUrl(recordUuid: string) {
  const url = getReplayViewerBaseUrl()
  url.searchParams.set("replay", recordUuid)
  return url.toString()
}

export function buildJumpReplayViewerUrl(jumpstatId: string) {
  const url = getReplayViewerBaseUrl()
  url.searchParams.set("jump_id", jumpstatId)
  return url.toString()
}

export function openReplayViewer(url: string) {
  window.open(url, "_blank", "noopener,noreferrer")
}
