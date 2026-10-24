import { usePronunciation } from "./usePronunciation"

export function useMapPronunciation(
  mapName: string | null | undefined,
  mapId?: number | null,
) {
  return usePronunciation({ kind: "map", name: mapName ?? "", id: mapId })
}
