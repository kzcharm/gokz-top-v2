import type { ComponentType, SVGProps } from "react"
import { FaGithub, FaTwitch, FaYoutube } from "react-icons/fa"
import { FaXTwitter } from "react-icons/fa6"
import { SiBilibili } from "react-icons/si"

import type { PlayerSocialPlatform } from "@/client"

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>

type SocialPlatformConfig = {
  icon: IconComponent
  label: string
  placeholder: string
}

export const socialPlatformOrder: PlayerSocialPlatform[] = [
  "bilibili",
  "github",
  "twitch",
  "x",
  "youtube",
]

export const socialPlatformConfig: Record<
  PlayerSocialPlatform,
  SocialPlatformConfig
> = {
  bilibili: {
    icon: SiBilibili,
    label: "Bilibili",
    placeholder: "https://space.bilibili.com/123456",
  },
  github: {
    icon: FaGithub,
    label: "GitHub",
    placeholder: "https://github.com/username",
  },
  twitch: {
    icon: FaTwitch,
    label: "Twitch",
    placeholder: "https://www.twitch.tv/username",
  },
  x: {
    icon: FaXTwitter,
    label: "X",
    placeholder: "https://x.com/username",
  },
  youtube: {
    icon: FaYoutube,
    label: "YouTube",
    placeholder: "https://www.youtube.com/@handle",
  },
}

export function getSocialPlatformLabel(platform: PlayerSocialPlatform) {
  return socialPlatformConfig[platform].label
}

export function SocialPlatformIcon({
  platform,
  className,
}: {
  platform: PlayerSocialPlatform
  className?: string
}) {
  const Icon = socialPlatformConfig[platform].icon
  return <Icon aria-hidden="true" className={className} />
}

export function detectSocialPlatformFromUrl(
  value: string,
): PlayerSocialPlatform | null {
  const rawUrl = value.trim()
  if (!rawUrl) {
    return null
  }

  try {
    const url = new URL(
      rawUrl.startsWith("http://") || rawUrl.startsWith("https://")
        ? rawUrl
        : `https://${rawUrl}`,
    )
    const host = url.hostname.toLowerCase().replace(/^www\./, "")
    if (host === "x.com" || host === "twitter.com") {
      return "x"
    }
    if (host === "space.bilibili.com") {
      return "bilibili"
    }
    if (host === "youtube.com" || host === "m.youtube.com") {
      return "youtube"
    }
    if (host === "github.com") {
      return "github"
    }
    if (host === "twitch.tv") {
      return "twitch"
    }
  } catch {
    return null
  }

  return null
}
