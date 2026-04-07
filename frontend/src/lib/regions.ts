import { queryOptions } from "@tanstack/react-query"

import { RegionsService, type RegionPublic } from "@/client"

export function getRegionsQueryOptions() {
  return queryOptions({
    queryKey: ["regions"],
    queryFn: async (): Promise<RegionPublic[]> => {
      const response = await RegionsService.readRegions()
      return response.data
    },
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  })
}
