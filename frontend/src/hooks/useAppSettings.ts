import { useQuery } from "@tanstack/react-query"

import { AppSettingsService } from "@/client"

export const appSettingsQueryKey = ["app-settings"] as const

export function useAppSettings() {
  return useQuery({
    queryKey: appSettingsQueryKey,
    queryFn: AppSettingsService.readAppSettings,
    staleTime: 60_000,
  })
}
