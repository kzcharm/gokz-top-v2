import { useTranslation } from "react-i18next"
import { FaDiscord, FaQq } from "react-icons/fa"

import { COMMUNITY_LINKS } from "@/lib/community-links"
import { getCopyrightYearRange, SITE_NAME } from "@/lib/site"

export function Footer() {
  const { t, i18n } = useTranslation()
  const showQqGroup = i18n.resolvedLanguage === "zh-CN"

  return (
    <footer className="shrink-0 border-t px-6 py-3">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-center text-center text-sm text-muted-foreground">
        <div className="inline-flex flex-wrap items-center justify-center gap-2 leading-none">
          <span>
            {SITE_NAME} {getCopyrightYearRange()} |
          </span>
          <a
            href={COMMUNITY_LINKS.discord}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t("footer.joinDiscord")}
            className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
          >
            <span>{t("footer.joinDiscord")}</span>
            <FaDiscord className="h-4 w-4" />
          </a>
          {showQqGroup ? (
            <>
              <span>|</span>
              <a
                href={COMMUNITY_LINKS.qq}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t("footer.joinQqGroup")}
                className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
              >
                <span>{t("footer.joinQqGroup")}</span>
                <FaQq className="h-4 w-4" />
              </a>
            </>
          ) : null}
        </div>
      </div>
    </footer>
  )
}
