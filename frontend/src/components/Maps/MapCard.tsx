import { Link } from "@tanstack/react-router"

import type { MapPublic } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { getMapImageUrl } from "@/components/Common/MapDisplay"
import { TierBadge } from "@/components/Servers/TierBadge"
import { Card, CardContent } from "@/components/ui/card"

interface MapCardProps {
  map: MapPublic
}

export function MapCard({ map }: MapCardProps) {
  const imageUrl = getMapImageUrl(map.name)

  return (
    <Link
      to="/maps/$mapName"
      params={{ mapName: map.name }}
      className="group block h-full rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      data-testid={`map-card-${map.name}`}
    >
      <Card className="h-full gap-0 overflow-hidden border-border/70 py-0 transition-all duration-200 group-hover:-translate-y-1 group-hover:border-primary/40 group-hover:shadow-lg">
        <div className="relative aspect-video overflow-hidden bg-muted">
          {imageUrl ? (
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
              style={{ backgroundImage: `url(${imageUrl})` }}
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/35 to-black/85" />
          <div className="absolute inset-x-4 top-4 flex items-start justify-between gap-3">
            <TierBadge
              tier={map.difficulty}
              className="bg-black/55 text-white backdrop-blur-sm"
            />
          </div>
          <div className="absolute inset-x-4 bottom-4">
            <h2 className="truncate text-lg font-semibold text-white drop-shadow-sm">
              {map.name}
            </h2>
          </div>
        </div>

        <CardContent className="space-y-4 px-5 py-5">
          <dl className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <dt className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                Created
              </dt>
              <dd className="text-sm font-medium text-foreground">
                <FormattedDateTime value={map.created_on} fallback="-" />
              </dd>
            </div>
            <div className="space-y-1">
              <dt className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                Updated
              </dt>
              <dd className="text-sm font-medium text-foreground">
                <FormattedDateTime value={map.updated_on} fallback="-" />
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </Link>
  )
}
