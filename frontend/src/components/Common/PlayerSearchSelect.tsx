import { useQuery } from "@tanstack/react-query"
import { Search, X } from "lucide-react"
import { useDeferredValue, useEffect, useRef, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { type GraphqlPlayer, searchPlayersGraphql } from "@/lib/player-graphql"

import {
  getPlayerDisplayName,
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "./PlayerDisplay"

type PlayerSearchSelectProps = {
  ariaLabel: string
  clearButtonLabel?: string
  id?: string
  label?: ReactNode
  placeholder?: string
  required?: boolean
  resultLimit?: number
  searchQueryKey?: string
  selectedPlayer: PlayerDisplayPlayer | null
  onClearPlayer: () => void
  onSelectPlayer: (player: GraphqlPlayer) => void
}

export function PlayerSearchSelect({
  ariaLabel,
  clearButtonLabel = "Clear selected player",
  id,
  label,
  placeholder = "Search player ...",
  required = false,
  resultLimit = 8,
  searchQueryKey = "default",
  selectedPlayer,
  onClearPlayer,
  onSelectPlayer,
}: PlayerSearchSelectProps) {
  const [searchInput, setSearchInput] = useState("")
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const searchBlurTimeoutRef = useRef<number | null>(null)
  const deferredSearchInput = useDeferredValue(searchInput)
  const playerSearchQuery = deferredSearchInput.trim()

  useEffect(() => {
    setSearchInput(
      selectedPlayer ? getPlayerDisplayName(selectedPlayer) : "",
    )
  }, [selectedPlayer])

  useEffect(() => {
    return () => {
      if (searchBlurTimeoutRef.current !== null) {
        window.clearTimeout(searchBlurTimeoutRef.current)
      }
    }
  }, [])

  const playerSearchQueryResult = useQuery({
    queryKey: [
      "graphql",
      "players",
      "search",
      searchQueryKey,
      playerSearchQuery,
    ],
    enabled: playerSearchQuery.length > 0,
    queryFn: async () => (await searchPlayersGraphql(playerSearchQuery, resultLimit)).data,
    staleTime: 30_000,
  })

  const searchResults: GraphqlPlayer[] = playerSearchQueryResult.data ?? []
  const showSearchResults =
    isSearchFocused && selectedPlayer === null && playerSearchQuery.length > 0

  const handleSelectPlayer = (player: GraphqlPlayer) => {
    setSearchInput(getPlayerDisplayName(player))
    setIsSearchFocused(false)
    onSelectPlayer(player)
  }

  return (
    <div className="grid gap-2">
      {label ? (
        <label className="text-sm font-medium" htmlFor={id}>
          {label}
          {required ? (
            <span aria-hidden="true" className="ml-1 text-destructive">
              *
            </span>
          ) : null}
        </label>
      ) : null}
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id={id}
          aria-label={ariaLabel}
          value={searchInput}
          onChange={(event) => {
            if (searchBlurTimeoutRef.current !== null) {
              window.clearTimeout(searchBlurTimeoutRef.current)
            }
            setSearchInput(event.target.value)
            setIsSearchFocused(true)
            if (selectedPlayer !== null) {
              onClearPlayer()
            }
          }}
          onFocus={() => {
            if (searchBlurTimeoutRef.current !== null) {
              window.clearTimeout(searchBlurTimeoutRef.current)
            }
            setIsSearchFocused(true)
          }}
          onBlur={() => {
            searchBlurTimeoutRef.current = window.setTimeout(() => {
              setIsSearchFocused(false)
            }, 100)
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && searchResults.length > 0) {
              event.preventDefault()
              handleSelectPlayer(searchResults[0])
            }
            if (event.key === "Escape") {
              setIsSearchFocused(false)
            }
          }}
          placeholder={placeholder}
          className="pr-10 pl-9"
        />
        {selectedPlayer ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="absolute top-1/2 right-1 -translate-y-1/2"
            onClick={() => {
              onClearPlayer()
              setSearchInput("")
              setIsSearchFocused(false)
            }}
            aria-label={clearButtonLabel}
          >
            <X className="size-4" />
          </Button>
        ) : null}
        {showSearchResults ? (
          <div className="absolute top-[calc(100%+0.5rem)] right-0 left-0 z-20 overflow-hidden rounded-xl border border-border/70 bg-card shadow-lg">
            {playerSearchQueryResult.isLoading ? (
              <div className="px-4 py-3 text-sm text-muted-foreground">
                Searching players...
              </div>
            ) : playerSearchQueryResult.isError ? (
              <div className="px-4 py-3 text-sm text-destructive">
                Unable to search players right now.
              </div>
            ) : searchResults.length === 0 ? (
              <div className="px-4 py-3 text-sm text-muted-foreground">
                No players found.
              </div>
            ) : (
              <div className="py-1">
                {searchResults.map((player) => (
                  <button
                    key={player.steamid64}
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors hover:bg-muted/60"
                    onMouseDown={(event) => {
                      event.preventDefault()
                      handleSelectPlayer(player)
                    }}
                  >
                    <PlayerDisplay
                      player={player}
                      disableProfileLink
                      className="min-w-0"
                    />
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>
      {selectedPlayer ? (
        <div className="rounded-xl border border-border/70 bg-muted/20 px-3 py-2">
          <PlayerDisplay player={selectedPlayer} disableProfileLink />
        </div>
      ) : null}
    </div>
  )
}
