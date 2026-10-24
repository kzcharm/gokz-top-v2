import { PronunciationButton } from "@/components/Common/PronunciationControls"

export function MapPronunciationButton({
  mapName,
  mapId,
}: {
  mapName: string
  mapId: number
}) {
  return (
    <PronunciationButton target={{ kind: "map", name: mapName, id: mapId }} />
  )
}
