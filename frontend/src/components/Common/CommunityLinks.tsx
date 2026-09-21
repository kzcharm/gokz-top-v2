import { useTranslation } from "react-i18next"
import { FaDiscord } from "react-icons/fa"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { COMMUNITY_LINKS } from "@/lib/community-links"

interface CommunityLinksProps {
  location: "navbar" | "footer"
}

export function CommunityLinks({ location }: CommunityLinksProps) {
  const { t } = useTranslation()

  if (location === "footer") {
    return (
      <>
        <span aria-hidden="true">|</span>
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
      </>
    )
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          asChild
          variant="ghost"
          size="icon"
          className="text-muted-foreground"
          aria-label={t("nav.joinDiscord")}
        >
          <a
            href={COMMUNITY_LINKS.discord}
            target="_blank"
            rel="noopener noreferrer"
          >
            <FaDiscord className="size-5" />
          </a>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t("nav.joinDiscordHelp")}</TooltipContent>
    </Tooltip>
  )
}
