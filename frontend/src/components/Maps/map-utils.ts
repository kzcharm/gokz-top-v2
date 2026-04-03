import { MapsService } from "@/client"

export async function fetchMapByName(mapName: string) {
  return await MapsService.readMapByName({
    mapName,
  })
}
