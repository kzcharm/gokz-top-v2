import { CommunityLinks } from "@/components/Common/CommunityLinks"
import { getCopyrightYearRange, SITE_NAME } from "@/lib/site"

interface FooterProps {
  communityLinksLocation: "navbar" | "footer"
}

export function Footer({ communityLinksLocation }: FooterProps) {
  return (
    <footer className="shrink-0 border-t px-6 py-3">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-center text-center text-sm text-muted-foreground">
        <div className="inline-flex flex-wrap items-center justify-center gap-2 leading-none">
          <span>
            {SITE_NAME} {getCopyrightYearRange()}
          </span>
          {communityLinksLocation === "footer" ? (
            <CommunityLinks location="footer" />
          ) : null}
        </div>
      </div>
    </footer>
  )
}
