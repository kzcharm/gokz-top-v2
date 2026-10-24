import { useSyncExternalStore } from "react"
import { toast } from "sonner"

import { MapsService, PlayersService } from "@/client"
import i18n from "@/i18n"

export type PronunciationTarget =
  | { kind: "map"; name: string; id?: number | null }
  | { kind: "player"; name: string; identifier: string }

function targetKey(target: PronunciationTarget) {
  return target.kind === "map"
    ? `map:${target.name}`
    : `player:${target.identifier}`
}

type PlaybackState = {
  key: string | null
  phase: "idle" | "loading" | "playing" | "blocked"
}

const listeners = new Set<() => void>()
let state: PlaybackState = { key: null, phase: "idle" }
let activeAudio: HTMLAudioElement | null = null
let requestVersion = 0
const toastId = "map-pronunciation"

function publish(next: PlaybackState) {
  state = next
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

async function playReady(
  audio: HTMLAudioElement,
  key: string,
  version: number,
) {
  if (version !== requestVersion) return
  try {
    await audio.play()
    if (version !== requestVersion) {
      audio.pause()
      return
    }
    toast.dismiss(toastId)
    publish({ key, phase: "playing" })
  } catch (error) {
    if (version !== requestVersion) return
    if (error instanceof DOMException && error.name === "NotAllowedError") {
      publish({ key, phase: "blocked" })
      toast.error(i18n.t("mapPronunciation.playbackBlocked"), {
        id: toastId,
        action: {
          label: i18n.t("mapPronunciation.retry"),
          onClick: () => void playReady(audio, key, version),
        },
      })
    } else {
      publish({ key, phase: "idle" })
      toast.error(i18n.t("mapPronunciation.failed"), { id: toastId })
    }
  }
}

async function playPronunciation(target: PronunciationTarget) {
  const key = targetKey(target)
  // Retry playback immediately inside the new user gesture, without an API await.
  if (state.key === key && state.phase === "blocked" && activeAudio) {
    await playReady(activeAudio, key, requestVersion)
    return
  }
  const version = ++requestVersion
  activeAudio?.pause()
  activeAudio = null
  publish({ key, phase: "loading" })
  toast.loading(i18n.t("mapPronunciation.loading"), { id: toastId })
  try {
    const mapId =
      target.kind === "map"
        ? (target.id ??
          (
            await MapsService.readMaps({
              name: target.name,
              limit: 1,
              includeInvalid: true,
            })
          )[0]?.id)
        : null
    if (version !== requestVersion) return
    if (target.kind === "map" && mapId == null) throw new Error("Map not found")
    let result =
      target.kind === "map"
        ? await MapsService.createMapPronunciation({ mapId: mapId! })
        : await PlayersService.createPlayerPronunciation({
            identifier: target.identifier,
          })
    for (
      let attempt = 0;
      result.status === "pending" || result.status === "generating";
      attempt++
    ) {
      if (version !== requestVersion) return
      if (attempt >= 120) throw new Error("Generation timed out")
      await new Promise((resolve) => setTimeout(resolve, 1500))
      if (version !== requestVersion) return
      result =
        target.kind === "map"
          ? await MapsService.readMapPronunciation({ mapId: mapId! })
          : await PlayersService.readPlayerPronunciation({
              identifier: target.identifier,
            })
    }
    if (version !== requestVersion) return
    if (result.status !== "ready" || !result.audio_url)
      throw new Error("Audio unavailable")
    const audio = new Audio(result.audio_url)
    activeAudio = audio
    audio.addEventListener(
      "ended",
      () => {
        if (version === requestVersion) publish({ key, phase: "idle" })
      },
      { once: true },
    )
    audio.addEventListener(
      "error",
      () => {
        if (version !== requestVersion) return
        publish({ key, phase: "idle" })
        toast.error(i18n.t("mapPronunciation.failed"), { id: toastId })
      },
      { once: true },
    )
    await playReady(audio, key, version)
  } catch {
    if (version !== requestVersion) return
    publish({ key, phase: "idle" })
    toast.error(i18n.t("mapPronunciation.failed"), { id: toastId })
  }
}

export function usePronunciation(target: PronunciationTarget) {
  const playback = useSyncExternalStore(
    subscribe,
    () => state,
    () => state,
  )
  const key = targetKey(target)
  return {
    play: () => {
      void playPronunciation(target)
    },
    loading: playback.key === key && playback.phase === "loading",
    playing: playback.key === key && playback.phase === "playing",
  }
}
