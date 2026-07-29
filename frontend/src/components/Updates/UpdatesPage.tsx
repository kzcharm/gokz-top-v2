import { useQuery } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { Fragment, type ReactNode, useMemo } from "react"
import { useTranslation } from "react-i18next"

import { LeaderboardsService, MapsService } from "@/client"
import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { useScope } from "@/components/scope-provider"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

const GITHUB_RELEASES_URL =
  "https://api.github.com/repos/kzcharm/gokz-top-v2/releases?per_page=20"
const PREVIEW_RELEASES: GitHubRelease[] = [
  {
    id: 1,
    tag_name: "v-preview",
    name: "v-preview",
    html_url: "https://github.com/kzcharm/gokz-top-v2/releases",
    published_at: "2026-06-18T12:00:00Z",
    body: [
      "## Features",
      "- feat(maps): improve /maps/:mapName reviews",
      "- feat(profile): show rank on /profile/:identifier",
      "",
      "## Fixes",
      "- fix(leaderboards): keep filters stable on /leaderboards",
      "",
      "## Other",
      "- docs(updates): mention /updates route enrichment",
    ].join("\n"),
  },
]
const PREVIEW_ROUTE_DEFAULTS: RouteDefaults = {
  mapName: "kz_beginnerblock_go",
  profileIdentifier: "76561198000000001",
}

type GitHubRelease = {
  id: number
  tag_name: string
  name: string | null
  html_url: string
  published_at: string | null
  body: string | null
}

type ReleaseSection = {
  title: string
  items: string[]
}

type RouteDefaults = {
  mapName?: string
  profileIdentifier?: string
}

async function fetchReleases(): Promise<GitHubRelease[]> {
  const response = await fetch(GITHUB_RELEASES_URL, {
    headers: {
      Accept: "application/vnd.github+json",
    },
  })

  if (!response.ok) {
    throw new Error(`GitHub releases request failed: ${response.status}`)
  }

  return response.json()
}

function parseReleaseBody(body: string | null | undefined): ReleaseSection[] {
  if (!body) {
    return []
  }

  const sections: ReleaseSection[] = []
  let currentSection: ReleaseSection | null = null

  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim()

    if (!line) {
      continue
    }

    const headingMatch = line.match(/^##\s+(.+)$/)
    if (headingMatch) {
      currentSection = {
        title: headingMatch[1],
        items: [],
      }
      sections.push(currentSection)
      continue
    }

    const itemMatch = line.match(/^[-*]\s+(.+)$/)
    if (itemMatch) {
      if (!currentSection) {
        currentSection = {
          title: "",
          items: [],
        }
        sections.push(currentSection)
      }
      currentSection.items.push(itemMatch[1])
      continue
    }

    if (currentSection) {
      currentSection.items.push(line)
    }
  }

  return sections.filter((section) => section.items.length > 0)
}

function releaseBodyIncludes(
  releases: GitHubRelease[] | undefined,
  value: string,
) {
  return releases?.some((release) => release.body?.includes(value)) ?? false
}

function resolveReleaseRoutePath(path: string, defaults: RouteDefaults) {
  if (path.includes(":mapName")) {
    if (!defaults.mapName) {
      return null
    }

    return path.split(":mapName").join(encodeURIComponent(defaults.mapName))
  }

  if (path.includes(":identifier")) {
    if (!defaults.profileIdentifier) {
      return null
    }

    return path
      .split(":identifier")
      .join(encodeURIComponent(defaults.profileIdentifier))
  }

  if (path.includes(":")) {
    return null
  }

  return path
}

function RouteLinkedReleaseText({
  text,
  defaults,
}: {
  text: string
  defaults: RouteDefaults
}) {
  const routePathPattern = /\/[A-Za-z0-9:_-]+(?:\/[A-Za-z0-9:_-]+)*/g
  const parts: ReactNode[] = []
  let lastIndex = 0

  for (const match of text.matchAll(routePathPattern)) {
    const rawPath = match[0]
    const index = match.index ?? 0
    const resolvedPath = resolveReleaseRoutePath(rawPath, defaults)

    if (index > lastIndex) {
      parts.push(text.slice(lastIndex, index))
    }

    parts.push(
      resolvedPath ? (
        <a
          key={`${rawPath}-${index}`}
          href={resolvedPath}
          className="rounded-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          {rawPath}
        </a>
      ) : (
        rawPath
      ),
    )
    lastIndex = index + rawPath.length
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  if (parts.length === 0) {
    return text
  }

  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={typeof part === "string" ? `${part}-${index}` : index}>
          {part}
        </Fragment>
      ))}
    </>
  )
}

function UpdatesPageSkeleton() {
  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <Skeleton className="h-10 w-52" />
      </div>
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="space-y-4 border-border border-l pl-6">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-4 w-48" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-full max-w-3xl" />
            <Skeleton className="h-4 w-full max-w-2xl" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function UpdatesPage() {
  const { t } = useTranslation()
  const { scope } = useScope()
  const isPreview =
    import.meta.env.DEV &&
    new URLSearchParams(window.location.search).get("preview") === "enrichment"
  const releasesQuery = useQuery({
    queryKey: ["github-releases", "kzcharm/gokz-top-v2"],
    queryFn: fetchReleases,
    enabled: !isPreview,
    staleTime: 5 * 60 * 1000,
  })
  const releasesData = isPreview ? PREVIEW_RELEASES : releasesQuery.data
  const needsMapDefault = releaseBodyIncludes(releasesData, "/maps/:")
  const needsProfileDefault = releaseBodyIncludes(releasesData, "/profile/:")
  const defaultMapQuery = useQuery({
    queryKey: ["updates", "default-route-map", scope],
    queryFn: () =>
      MapsService.readMaps({
        offset: 0,
        limit: 1,
        isValidated: true,
        scope,
      }),
    enabled: needsMapDefault && !isPreview,
    staleTime: 5 * 60 * 1000,
  })
  const defaultProfileQuery = useQuery({
    queryKey: ["updates", "default-route-profile", scope],
    queryFn: () =>
      LeaderboardsService.readPlayerLeaderboard({
        scope,
        offset: 0,
        limit: 1,
        sortBy: "rating",
        sortOrder: "desc",
        includeCount: false,
      }),
    enabled: needsProfileDefault && !isPreview,
    staleTime: 5 * 60 * 1000,
  })
  const routeDefaults = useMemo<RouteDefaults>(
    () => ({
      mapName: isPreview
        ? PREVIEW_ROUTE_DEFAULTS.mapName
        : defaultMapQuery.data?.[0]?.name,
      profileIdentifier: isPreview
        ? PREVIEW_ROUTE_DEFAULTS.profileIdentifier
        : defaultProfileQuery.data?.data[0]?.player.steamid64,
    }),
    [defaultMapQuery.data, defaultProfileQuery.data, isPreview],
  )

  if (releasesQuery.isLoading && !isPreview) {
    return <UpdatesPageSkeleton />
  }

  if (releasesQuery.isError && !isPreview) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <Alert variant="destructive">
          <AlertTitle>{t("updates.errorTitle")}</AlertTitle>
          <AlertDescription>
            <p>{t("updates.errorBody")}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => releasesQuery.refetch()}
            >
              <RefreshCw />
              {t("common.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const releases = releasesData ?? []

  return (
    <div className="space-y-8">
      <PageHeader />
      {releases.length === 0 ? (
        <div className="border-border border-l pl-6 text-muted-foreground">
          {t("updates.empty")}
        </div>
      ) : (
        <div className="space-y-8">
          {releases.map((release) => {
            const sections = parseReleaseBody(release.body)
            const releaseTitle = release.name || release.tag_name

            return (
              <article
                key={release.id}
                className="grid gap-5 border-border border-l pl-6 md:grid-cols-[12rem_minmax(0,1fr)] md:pl-0"
              >
                <div className="md:border-border md:border-l md:pl-6">
                  <h2 className="font-semibold text-2xl tracking-normal">
                    <a
                      href={release.html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-sm transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      {releaseTitle}
                    </a>
                  </h2>
                  <div className="mt-1 text-muted-foreground text-sm">
                    <FormattedDateTime
                      value={release.published_at}
                      dateOnly
                      fallback={t("common.unknown")}
                    />
                  </div>
                </div>
                <div className="space-y-4">
                  {sections.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      {t("updates.noNotes")}
                    </p>
                  ) : (
                    sections.map((section) => (
                      <section key={`${release.id}-${section.title}`}>
                        {section.title ? (
                          <h3 className="mb-2 font-medium text-sm text-muted-foreground uppercase tracking-normal">
                            {t(`updates.sections.${section.title}`, {
                              defaultValue: section.title,
                            })}
                          </h3>
                        ) : null}
                        <ul className="space-y-2 text-sm">
                          {section.items.map((item) => (
                            <li
                              key={`${release.id}-${section.title}-${item}`}
                              className="leading-6"
                            >
                              <RouteLinkedReleaseText
                                text={item}
                                defaults={routeDefaults}
                              />
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

function PageHeader() {
  const { t } = useTranslation()

  return (
    <div>
      <h1 className="font-bold text-2xl tracking-tight">
        {t("updates.title")}
      </h1>
    </div>
  )
}
