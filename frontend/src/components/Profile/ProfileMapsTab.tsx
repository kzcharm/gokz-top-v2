import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { type MapPublic, MapsService, type MapWrPublic } from "@/client"
import { MapCard } from "@/components/Maps/MapCard"
import { getMapTierForScope } from "@/components/Maps/map-utils"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

function ProfileMapsSkeleton() {
  return (
    <section className="grid grid-cols-1 gap-5 sm:grid-cols-2 2xl:grid-cols-3">
      {Array.from({ length: 3 }, (_, index) => (
        <Skeleton key={index} className="h-[31rem] rounded-xl" />
      ))}
    </section>
  )
}

export function ProfileMapsTab({
  maps,
  mapsError,
  mapsLoading,
}: {
  maps: MapPublic[]
  mapsError: boolean
  mapsLoading: boolean
}) {
  const { t } = useTranslation()
  const { scope } = useScope()
  const wrsQuery = useQuery({
    queryKey: ["profile-authored-maps", "wrs", scope, "NUB"],
    queryFn: () =>
      MapsService.readMapWrs({
        scope,
        type: "NUB",
      }),
    enabled: maps.length > 0,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const wrByMapId = useMemo(() => {
    const nextMap = new Map<number, MapWrPublic>()
    for (const record of wrsQuery.data ?? []) {
      if (!nextMap.has(record.map_id)) {
        nextMap.set(record.map_id, record)
      }
    }
    return nextMap
  }, [wrsQuery.data])

  if (mapsError) {
    return (
      <Alert>
        <AlertTitle>{t("profile.maps.loadFailedTitle")}</AlertTitle>
        <AlertDescription>{t("profile.maps.loadFailedBody")}</AlertDescription>
      </Alert>
    )
  }

  if (mapsLoading) {
    return <ProfileMapsSkeleton />
  }

  if (maps.length === 0) {
    return (
      <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
        <CardContent className="px-6 py-16 text-center text-muted-foreground">
          {t("profile.maps.empty")}
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="grid grid-cols-1 gap-5 sm:grid-cols-2 2xl:grid-cols-3">
      {maps.map((map) => (
        <MapCard
          key={map.id}
          activeTier={getMapTierForScope(map, scope)}
          map={map}
          wrRecord={wrByMapId.get(map.id) ?? null}
          wrLoading={wrsQuery.isLoading}
        />
      ))}
    </section>
  )
}
