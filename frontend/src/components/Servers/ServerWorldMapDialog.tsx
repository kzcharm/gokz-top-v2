import type { EChartsOption, EChartsType } from "echarts"
import * as echarts from "echarts"
import { useEffect, useMemo, useRef, useState } from "react"

import type { ServerPublic } from "@/client"
import { getCountryName } from "@/components/Common/CountryFlag"
import { useTheme } from "@/components/theme-provider"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import worldMapGeoJson from "@/data/world.geo.json"

import { getServerAddress, getServerHostname, isServerOnline } from "./utils"

const SERVER_WORLD_MAP_NAME = "gokz-server-world"
const SERVER_WORLD_MAP_ASPECT_SCALE = 0.78
const SERVER_WORLD_MAP_INITIAL_ZOOM = 1
const SERVER_WORLD_MAP_MIN_ZOOM = SERVER_WORLD_MAP_INITIAL_ZOOM

let serverWorldMapRegistered = false

interface ServerLocationAggregate {
  key: string
  latitude: number
  longitude: number
  country: string | null
  city: string | null
  serverCount: number
  servers: ServerPublic[]
}

interface ServerWorldMapDialogProps {
  open: boolean
  servers: ServerPublic[]
  onOpenChange: (open: boolean) => void
  onSelectServer: (server: ServerPublic) => void
}

interface ServerMapPoint {
  name: string
  value: [number, number, number]
  aggregate: ServerLocationAggregate
}

interface ServerMapView {
  center?: [number, number]
  zoom?: number
}

function registerServerWorldMap() {
  if (serverWorldMapRegistered) {
    return
  }

  echarts.registerMap(SERVER_WORLD_MAP_NAME, worldMapGeoJson as never)
  serverWorldMapRegistered = true
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function formatCount(value: number, singular: string, plural: string) {
  return `${value} ${value === 1 ? singular : plural}`
}

function getLocationLabel(aggregate: ServerLocationAggregate) {
  const countryName = getCountryName(aggregate.country)
  return [aggregate.city, countryName ?? aggregate.country]
    .filter(Boolean)
    .join(", ")
}

function getLocationKey({
  city,
  country,
  latitude,
  longitude,
}: {
  city: string | null
  country: string | null
  latitude: number
  longitude: number
}) {
  const locationKey = [city, country]
    .filter(Boolean)
    .map((value) => value!.trim().toLowerCase())
    .join("|")

  return locationKey || `${latitude.toFixed(4)},${longitude.toFixed(4)}`
}

function buildAggregates(servers: ServerPublic[]) {
  const aggregates = new Map<string, ServerLocationAggregate>()
  let unmappedCount = 0

  for (const server of servers) {
    if (!isServerOnline(server)) {
      continue
    }

    const latitude = server.latitude
    const longitude = server.longitude
    if (
      typeof latitude !== "number" ||
      !Number.isFinite(latitude) ||
      typeof longitude !== "number" ||
      !Number.isFinite(longitude)
    ) {
      unmappedCount += 1
      continue
    }

    const city = server.city ?? null
    const country = server.country ?? null
    const key = getLocationKey({ city, country, latitude, longitude })
    const current = aggregates.get(key)
    if (current) {
      current.serverCount += 1
      current.servers.push(server)
      continue
    }

    aggregates.set(key, {
      key,
      latitude,
      longitude,
      country,
      city,
      serverCount: 1,
      servers: [server],
    })
  }

  return {
    aggregates: Array.from(aggregates.values()).sort((left, right) => {
      const serverComparison = right.serverCount - left.serverCount
      return serverComparison !== 0
        ? serverComparison
        : getLocationLabel(left).localeCompare(getLocationLabel(right))
    }),
    unmappedCount,
  }
}

function getMarkerSize(serverCount: number) {
  return Math.min(36, Math.max(12, 10 + Math.sqrt(serverCount) * 8))
}

function buildTooltip(aggregate: ServerLocationAggregate) {
  const location = getLocationLabel(aggregate) || "Unknown location"
  const serverLines = aggregate.servers
    .slice()
    .sort(
      (left, right) =>
        getServerHostname(left).localeCompare(getServerHostname(right)) ||
        left.ip.localeCompare(right.ip) ||
        left.port - right.port,
    )
    .map(
      (server) =>
        `<div>${escapeHtml(getServerHostname(server))} - ${escapeHtml(
          getServerAddress(server),
        )}</div>`,
    )
    .join("")

  return [
    `<div class="space-y-1">`,
    `<div class="font-semibold">${escapeHtml(location)}</div>`,
    `<div>${escapeHtml(formatCount(aggregate.serverCount, "server", "servers"))}</div>`,
    `<div class="pt-1 text-xs">${serverLines}</div>`,
    `</div>`,
  ].join("")
}

function buildChartOption({
  includeDefaultView = true,
  mapView,
  pointData,
  resolvedTheme,
}: {
  includeDefaultView?: boolean
  mapView?: ServerMapView
  pointData: ServerMapPoint[]
  resolvedTheme: string | undefined
}): EChartsOption {
  const isDark = resolvedTheme === "dark"
  const zoom =
    mapView?.zoom ??
    (includeDefaultView ? SERVER_WORLD_MAP_INITIAL_ZOOM : undefined)
  return {
    backgroundColor: "transparent",
    animation: false,
    animationDuration: 0,
    animationDurationUpdate: 0,
    tooltip: {
      trigger: "item",
      confine: true,
      backgroundColor: isDark ? "rgba(15, 23, 42, 0.96)" : "#ffffff",
      borderColor: isDark
        ? "rgba(148, 163, 184, 0.32)"
        : "rgba(15, 23, 42, 0.12)",
      textStyle: {
        color: isDark ? "#e5e7eb" : "#0f172a",
        fontSize: 12,
      },
      formatter: (params) => {
        const point = (params as { data?: ServerMapPoint }).data
        return point ? buildTooltip(point.aggregate) : ""
      },
    },
    geo: {
      map: SERVER_WORLD_MAP_NAME,
      aspectScale: SERVER_WORLD_MAP_ASPECT_SCALE,
      roam: true,
      scaleLimit: {
        min: SERVER_WORLD_MAP_MIN_ZOOM,
      },
      ...(typeof zoom === "number" ? { zoom } : {}),
      ...(mapView?.center ? { center: mapView.center } : {}),
      top: 8,
      bottom: 8,
      left: 8,
      right: 8,
      itemStyle: {
        areaColor: isDark
          ? "rgba(71, 85, 105, 0.42)"
          : "rgba(203, 213, 225, 0.72)",
        borderColor: isDark
          ? "rgba(148, 163, 184, 0.45)"
          : "rgba(100, 116, 139, 0.45)",
        borderWidth: 0.8,
      },
      emphasis: {
        disabled: true,
      },
    },
    series: [
      {
        type: "scatter",
        coordinateSystem: "geo",
        data: pointData,
        symbolSize: (_value, params) => {
          const point = (params as { data?: ServerMapPoint }).data
          return getMarkerSize(point?.aggregate.serverCount ?? 1)
        },
        itemStyle: {
          color: "#f97316",
          borderColor: isDark ? "#fed7aa" : "#fff7ed",
          borderWidth: 2,
          shadowBlur: 10,
          shadowColor: "rgba(249, 115, 22, 0.35)",
        },
        emphasis: {
          scale: 1.15,
          itemStyle: {
            color: "#2563eb",
            shadowBlur: 16,
            shadowColor: "rgba(37, 99, 235, 0.35)",
          },
        },
      },
    ],
  }
}

function readCurrentMapView(chart: EChartsType): ServerMapView {
  const option = chart.getOption() as {
    geo?: Array<{ center?: unknown; zoom?: unknown }>
  }
  const geo = option.geo?.[0]
  const center =
    Array.isArray(geo?.center) &&
    geo.center.length === 2 &&
    geo.center.every((value) => typeof value === "number")
      ? (geo.center as [number, number])
      : undefined
  const zoom =
    typeof geo?.zoom === "number"
      ? Math.max(SERVER_WORLD_MAP_MIN_ZOOM, geo.zoom)
      : undefined

  return { center, zoom }
}

export function ServerWorldMapDialog({
  open,
  servers,
  onOpenChange,
  onSelectServer,
}: ServerWorldMapDialogProps) {
  const [chartElement, setChartElement] = useState<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<EChartsType | null>(null)
  const mapViewRef = useRef<ServerMapView>({})
  const onSelectServerRef = useRef(onSelectServer)
  const pointDataRef = useRef<ServerMapPoint[]>([])
  const resolvedThemeRef = useRef<string | undefined>(undefined)
  const { resolvedTheme } = useTheme()
  const aggregateResult = useMemo(() => buildAggregates(servers), [servers])
  const pointData: ServerMapPoint[] = useMemo(
    () =>
      aggregateResult.aggregates.map((aggregate) => ({
        name: getLocationLabel(aggregate) || "Unknown location",
        value: [aggregate.longitude, aggregate.latitude, aggregate.serverCount],
        aggregate,
      })),
    [aggregateResult.aggregates],
  )
  const hasMapPoints = pointData.length > 0

  useEffect(() => {
    onSelectServerRef.current = onSelectServer
  }, [onSelectServer])

  useEffect(() => {
    pointDataRef.current = pointData
    resolvedThemeRef.current = resolvedTheme
  }, [pointData, resolvedTheme])

  useEffect(() => {
    if (!open || !hasMapPoints || !chartElement) {
      return
    }

    registerServerWorldMap()

    const chart = echarts.init(chartElement, undefined, { renderer: "canvas" })
    chartInstanceRef.current = chart
    chart.setOption(
      buildChartOption({
        mapView: mapViewRef.current,
        pointData: pointDataRef.current,
        resolvedTheme: resolvedThemeRef.current,
      }),
    )
    chart.on("georoam", () => {
      mapViewRef.current = readCurrentMapView(chart)
    })
    chart.on("click", (params) => {
      const point = (params as { data?: ServerMapPoint }).data
      if (!point) {
        return
      }

      if (point.aggregate.servers.length === 1) {
        onSelectServerRef.current(point.aggregate.servers[0])
      }
    })

    const resizeObserver = new ResizeObserver(() => chart.resize())
    resizeObserver.observe(chartElement)
    window.requestAnimationFrame(() => chart.resize())

    return () => {
      resizeObserver.disconnect()
      chart.dispose()
      chartInstanceRef.current = null
    }
  }, [chartElement, hasMapPoints, open])

  useEffect(() => {
    const chart = chartInstanceRef.current
    if (!open || !chart) {
      return
    }

    const mapView = readCurrentMapView(chart)
    mapViewRef.current = mapView
    chart.setOption(
      buildChartOption({
        includeDefaultView: false,
        mapView,
        pointData,
        resolvedTheme,
      }),
    )
  }, [open, pointData, resolvedTheme])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-2rem)] max-h-[calc(100svh-2rem)] gap-4 overflow-hidden p-0 sm:max-w-7xl xl:max-w-[90rem]">
        <DialogHeader className="px-6 pt-6 pr-12">
          <DialogTitle>Server map</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 px-6 pb-6">
          <div className="self-start">
            {pointData.length > 0 ? (
              <div
                ref={setChartElement}
                className="h-[24rem] w-full overflow-hidden rounded-md border bg-muted/30 md:aspect-[1.94/1] md:h-auto"
                data-testid="server-world-map-chart"
                role="img"
                aria-label="World map of public servers"
              />
            ) : (
              <div className="flex h-[24rem] w-full items-center justify-center overflow-hidden rounded-md border bg-muted/30 px-6 text-center text-sm text-muted-foreground md:aspect-[1.94/1] md:h-auto">
                No loaded servers have map coordinates.
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
