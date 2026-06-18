import { useQuery } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"

import { FormattedDateTime } from "@/components/Common/FormattedDateTime"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

const GITHUB_RELEASES_URL =
  "https://api.github.com/repos/kzcharm/gokz-top-v2/releases?per_page=20"

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
  const releasesQuery = useQuery({
    queryKey: ["github-releases", "kzcharm/gokz-top-v2"],
    queryFn: fetchReleases,
    staleTime: 5 * 60 * 1000,
  })

  if (releasesQuery.isLoading) {
    return <UpdatesPageSkeleton />
  }

  if (releasesQuery.isError) {
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

  const releases = releasesQuery.data ?? []

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
                              {item}
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
