import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { LoaderCircle, Plus } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import {
  type ReactionEmojiPublic,
  type ReactionGroupPublic,
  type ReactionSummaryPublic,
  ReactionsService,
  type ReactionTargetType,
} from "@/client"
import {
  Avatar,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
  AvatarImage,
} from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { isLoggedIn } from "@/hooks/useAuth"
import { redirectToSteamLogin } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { getInitials } from "@/utils"

const REACTORS_PAGE_SIZE = 20
const COLLAPSED_REACTOR_COUNT = 10
const REACTOR_HOVER_DELAY_MS = 900

function ReactionMenuIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 16 16"
      fill="currentColor"
    >
      <path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm3.82 1.636a.75.75 0 0 1 1.044.184c.323.44.927.955 1.636.955.708 0 1.313-.518 1.636-.955a.75.75 0 0 1 1.208.888c-.521.709-1.538 1.562-2.844 1.562-1.309 0-2.324-.85-2.844-1.562a.75.75 0 0 1 .164-1.044ZM6.25 6.25a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm4.5 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z" />
    </svg>
  )
}

function optimisticAdd(
  summary: ReactionSummaryPublic,
  emoji: ReactionEmojiPublic,
) {
  const groups = [...(summary.groups ?? [])]
  const index = groups.findIndex((group) => group.emoji.key === emoji.key)
  if (index === -1) {
    groups.push({ emoji, count: 1, reacted_by_me: true })
  } else if (!groups[index].reacted_by_me) {
    groups[index] = {
      ...groups[index],
      count: groups[index].count + 1,
      reacted_by_me: true,
    }
  }
  return { groups }
}

function optimisticRemove(summary: ReactionSummaryPublic, emojiKey: string) {
  return {
    groups: (summary.groups ?? []).flatMap((group) => {
      if (group.emoji.key !== emojiKey || !group.reacted_by_me) return [group]
      if (group.count <= 1) return []
      return [
        {
          ...group,
          count: group.count - 1,
          reacted_by_me: false,
          reaction_id: null,
        },
      ]
    }),
  }
}

function ReactorList({
  emojiKey,
  open,
  targetId,
  targetType,
}: {
  emojiKey: string
  open: boolean
  targetId: string
  targetType: ReactionTargetType
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const query = useInfiniteQuery({
    queryKey: ["reaction-users", targetType, targetId, emojiKey],
    queryFn: ({ pageParam }) =>
      ReactionsService.readReactors({
        targetType,
        targetId,
        emojiKey,
        offset: pageParam,
        limit: REACTORS_PAGE_SIZE,
      }),
    initialPageParam: 0,
    getNextPageParam: (page, pages) => {
      const loaded = pages.reduce((total, item) => total + item.data.length, 0)
      return loaded < page.count ? loaded : undefined
    },
    enabled: open,
  })
  const users = query.data?.pages.flatMap((page) => page.data) ?? []
  const total = query.data?.pages[0]?.count ?? 0
  const visibleUsers = expanded
    ? users
    : users.slice(0, COLLAPSED_REACTOR_COUNT)
  const remaining = Math.max(
    0,
    total - (expanded ? users.length : COLLAPSED_REACTOR_COUNT),
  )

  if (query.isLoading) {
    return (
      <div className="flex h-24 items-center justify-center text-muted-foreground">
        <LoaderCircle
          className="animate-spin"
          aria-label={t("reactions.loading")}
        />
      </div>
    )
  }
  if (query.isError) {
    return (
      <p className="text-sm text-destructive">{t("reactions.loadError")}</p>
    )
  }
  if (!users.length) {
    return (
      <p className="text-sm text-muted-foreground">{t("reactions.empty")}</p>
    )
  }

  return (
    <ScrollArea className="max-h-52">
      <div className="flex items-start gap-2 py-1 pr-3">
        <AvatarGroup
          className={cn(
            "min-w-0 flex-1",
            expanded && "flex-wrap gap-y-1 pl-3.5 [&>*]:-ml-3.5",
          )}
          data-testid="reaction-reactor-avatars"
        >
          {visibleUsers.map(({ player, created_at }) => {
            const avatarUrl = player.avatar_hash
              ? `https://avatars.steamstatic.com/${player.avatar_hash}_medium.jpg`
              : undefined
            return (
              <Tooltip key={`${player.steamid64}-${created_at}`}>
                <TooltipTrigger asChild>
                  <Link
                    to="/profile/$identifier"
                    params={{ identifier: player.steamid64 }}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={player.display_name}
                  >
                    <Avatar className="size-7 border-2 border-background transition-transform hover:scale-110">
                      <AvatarImage src={avatarUrl} alt={player.display_name} />
                      <AvatarFallback className="text-[10px]">
                        {getInitials(player.display_name)}
                      </AvatarFallback>
                    </Avatar>
                  </Link>
                </TooltipTrigger>
                <TooltipContent>{player.display_name}</TooltipContent>
              </Tooltip>
            )
          })}
          {remaining > 0 ? (
            <AvatarGroupCount asChild className="size-7 text-[10px]">
              <button
                type="button"
                disabled={query.isFetchingNextPage}
                aria-label={t("reactions.showAllReactors", { count: total })}
                onClick={() => {
                  setExpanded(true)
                  if (query.hasNextPage) void query.fetchNextPage()
                }}
              >
                {query.isFetchingNextPage ? (
                  <LoaderCircle className="size-3 animate-spin" />
                ) : (
                  `+${remaining}`
                )}
              </button>
            </AvatarGroupCount>
          ) : null}
        </AvatarGroup>
        {expanded && total > COLLAPSED_REACTOR_COUNT ? (
          <button
            type="button"
            className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded(false)}
          >
            {t("reactions.showLess")}
          </button>
        ) : null}
      </div>
    </ScrollArea>
  )
}

function ReactionGroup({
  disabled,
  group,
  onToggle,
  targetId,
  targetType,
}: {
  disabled: boolean
  group: ReactionGroupPublic
  onToggle: (group: ReactionGroupPublic) => void
  targetId: string
  targetType: ReactionTargetType
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const label = group.emoji.value ?? group.emoji.name

  const cancelHoverOpen = () => {
    if (hoverTimerRef.current === null) return
    clearTimeout(hoverTimerRef.current)
    hoverTimerRef.current = null
  }
  const openReactors = () => {
    cancelHoverOpen()
    setOpen(true)
  }
  const scheduleHoverOpen = () => {
    if (open || hoverTimerRef.current !== null) return
    hoverTimerRef.current = setTimeout(openReactors, REACTOR_HOVER_DELAY_MS)
  }
  useEffect(
    () => () => {
      if (hoverTimerRef.current !== null) {
        clearTimeout(hoverTimerRef.current)
      }
    },
    [],
  )

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        cancelHoverOpen()
        setOpen(nextOpen)
      }}
    >
      <PopoverAnchor asChild>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={cn(
            "h-7 gap-1.5 px-2 text-base tabular-nums",
            group.reacted_by_me &&
              "border-primary bg-primary/10 text-primary ring-1 ring-primary/30 hover:bg-primary/15 hover:text-primary dark:border-primary",
          )}
          aria-pressed={group.reacted_by_me}
          aria-label={t("reactions.toggle", { emoji: group.emoji.name })}
          aria-description={t("reactions.reactorsHint", {
            emoji: group.emoji.name,
          })}
          disabled={disabled}
          onClick={() => onToggle(group)}
          onMouseEnter={scheduleHoverOpen}
          onMouseLeave={cancelHoverOpen}
          onContextMenu={(event) => {
            event.preventDefault()
            openReactors()
          }}
          onKeyDown={(event) => {
            if (
              event.key === "ContextMenu" ||
              (event.shiftKey && event.key === "F10")
            ) {
              event.preventDefault()
              openReactors()
            }
          }}
        >
          <span>{label}</span>
          <span className="text-xs">{group.count}</span>
        </Button>
      </PopoverAnchor>
      <PopoverContent align="start" className="w-72">
        <PopoverHeader>
          <PopoverTitle className="flex items-center gap-2">
            <span className="text-lg">{label}</span>
            {t("reactions.reactors")}
          </PopoverTitle>
          <PopoverDescription>
            {t("reactions.reactorCount", { count: group.count })}
          </PopoverDescription>
        </PopoverHeader>
        <div className="mt-3">
          <ReactorList
            emojiKey={group.emoji.key}
            open={open}
            targetId={targetId}
            targetType={targetType}
          />
        </div>
      </PopoverContent>
    </Popover>
  )
}

export function ReactionBar({
  className,
  floatingWhenEmpty = false,
  reactions,
  targetId,
  targetType,
}: {
  className?: string
  floatingWhenEmpty?: boolean
  reactions?: ReactionSummaryPublic | null
  targetId: string
  targetType: ReactionTargetType
}) {
  const { t } = useTranslation()
  const [summary, setSummary] = useState<ReactionSummaryPublic>(
    reactions ?? { groups: [] },
  )
  const [pickerOpen, setPickerOpen] = useState(false)
  useEffect(() => {
    setSummary(reactions ?? { groups: [] })
  }, [reactions])

  const catalogQuery = useQuery({
    queryKey: ["reaction-emojis"],
    queryFn: () => ReactionsService.readReactionEmojis(),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  })
  const mutation = useMutation({
    mutationFn: async ({
      emoji,
      group,
    }: {
      emoji: ReactionEmojiPublic
      group?: ReactionGroupPublic
    }) => {
      if (group?.reacted_by_me && group.reaction_id) {
        return ReactionsService.deleteReaction({
          reactionId: group.reaction_id,
        })
      }
      return ReactionsService.putReaction({
        targetType,
        targetId,
        requestBody: { emoji_key: emoji.key },
      })
    },
    onMutate: ({ emoji, group }) => {
      const previous = summary
      setSummary((current) =>
        group?.reacted_by_me
          ? optimisticRemove(current, emoji.key)
          : optimisticAdd(current, emoji),
      )
      return { previous }
    },
    onSuccess: (result) => setSummary(result),
    onError: (_error, _variables, context) => {
      if (context?.previous) setSummary(context.previous)
      toast.error(t("reactions.updateError"))
    },
  })

  const requireLogin = () => {
    if (isLoggedIn()) return false
    redirectToSteamLogin()
    return true
  }
  const toggleGroup = (group: ReactionGroupPublic) => {
    if (requireLogin()) return
    mutation.mutate({ emoji: group.emoji, group })
  }
  const addEmoji = (emoji: ReactionEmojiPublic) => {
    if (requireLogin()) return
    const group = summary.groups?.find((item) => item.emoji.key === emoji.key)
    if (group?.reacted_by_me) return
    setPickerOpen(false)
    mutation.mutate({ emoji, group })
  }
  const isEmpty = (summary.groups?.length ?? 0) === 0

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5",
        floatingWhenEmpty &&
          isEmpty &&
          "pointer-events-auto absolute right-3 bottom-3 z-20 opacity-100 transition-[opacity,transform] duration-150 md:pointer-events-none md:translate-y-1 md:opacity-0 md:group-hover/card:pointer-events-auto md:group-hover/card:translate-y-0 md:group-hover/card:opacity-100 md:group-focus-within/card:pointer-events-auto md:group-focus-within/card:translate-y-0 md:group-focus-within/card:opacity-100",
        className,
      )}
      data-testid={`reaction-bar-${targetType}-${targetId}`}
    >
      {(summary.groups ?? []).map((group) => (
        <ReactionGroup
          key={group.emoji.key}
          disabled={mutation.isPending}
          group={group}
          onToggle={toggleGroup}
          targetId={targetId}
          targetType={targetType}
        />
      ))}
      <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <Button
                type="button"
                size={floatingWhenEmpty && isEmpty ? "sm" : "icon-sm"}
                variant="outline"
                className={cn(
                  "h-7 rounded-full bg-background/95 shadow-none backdrop-blur-sm hover:border-primary/50 hover:text-primary",
                  floatingWhenEmpty && isEmpty ? "px-2.5" : "size-7",
                )}
                aria-label={t("reactions.add")}
                disabled={mutation.isPending}
              >
                {isEmpty ? (
                  <ReactionMenuIcon className="size-4" />
                ) : (
                  <Plus aria-hidden="true" />
                )}
                {floatingWhenEmpty && isEmpty ? (
                  <span>{t("reactions.react")}</span>
                ) : null}
              </Button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent>{t("reactions.add")}</TooltipContent>
        </Tooltip>
        <PopoverContent align="start" className="w-64">
          <PopoverHeader>
            <PopoverTitle>{t("reactions.choose")}</PopoverTitle>
            {!isLoggedIn() ? (
              <PopoverDescription>
                {t("reactions.signInHint")}
              </PopoverDescription>
            ) : null}
          </PopoverHeader>
          {catalogQuery.isLoading ? (
            <div className="flex h-24 items-center justify-center text-muted-foreground">
              <LoaderCircle className="animate-spin" />
            </div>
          ) : catalogQuery.isError ? (
            <p className="mt-3 text-sm text-destructive">
              {t("reactions.catalogError")}
            </p>
          ) : (
            <div className="mt-3 grid grid-cols-6 gap-1">
              {catalogQuery.data?.map((emoji) => {
                const selected = summary.groups?.some(
                  (group) =>
                    group.emoji.key === emoji.key && group.reacted_by_me,
                )
                return (
                  <Button
                    key={emoji.key}
                    type="button"
                    size="icon-sm"
                    variant={selected ? "outline" : "ghost"}
                    className={cn(
                      selected &&
                        "border-primary bg-primary/10 text-primary ring-1 ring-primary/30",
                    )}
                    aria-label={emoji.name}
                    aria-pressed={selected}
                    disabled={selected || mutation.isPending}
                    onClick={() => addEmoji(emoji)}
                  >
                    <span className="text-lg">{emoji.value}</span>
                  </Button>
                )
              })}
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}
