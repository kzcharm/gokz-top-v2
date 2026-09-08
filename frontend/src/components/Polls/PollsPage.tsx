import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { OpenAPI } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useAuth from "@/hooks/useAuth"

type Option = {
  id: string
  label: string
  description?: string | null
  votes?: number | null
  percentage?: number | null
}
type Poll = {
  id: string
  title: string
  description?: string | null
  status: "active" | "closed"
  ends_at?: string | null
  total_votes: number
  max_selections: number
  allow_vote_change: boolean
  has_voted: boolean
  can_view_results: boolean
  selected_option_ids: string[]
  options: Option[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("access_token")
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  })
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => null))?.detail ?? "Request failed",
    )
  return response.json() as Promise<T>
}

export function PollsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState("")
  const [sort, setSort] = useState("created")
  const [selections, setSelections] = useState<Record<string, string[]>>({})
  const [openPollId, setOpenPollId] = useState<string | null>(null)
  const polls = useQuery({
    queryKey: ["polls", status, sort],
    queryFn: () =>
      request<{ data: Poll[]; count: number }>(
        `/v1/polls?limit=100&sort=${sort}${status ? `&status=${status}` : ""}`,
      ),
  })
  const vote = useMutation({
    mutationFn: ({
      pollId,
      optionIds,
    }: {
      pollId: string
      optionIds: string[]
    }) =>
      request<Poll>(`/v1/polls/${pollId}/votes`, {
        method: "POST",
        body: JSON.stringify({ option_ids: optionIds }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["polls"] }),
  })

  const openPoll = polls.data?.data.find((poll) => poll.id === openPollId)
  const selected = openPoll
    ? (selections[openPoll.id] ?? openPoll.selected_option_ids)
    : []
  const maxSelections = openPoll
    ? openPoll.max_selections === 0
      ? openPoll.options.length
      : openPoll.max_selections
    : 0

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {t("titles.polls")}
          </h1>
        </div>
        <div className="flex gap-2">
          <Select
            value={status || "all"}
            onValueChange={(v) => setStatus(v === "all" ? "" : v)}
          >
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("polls.filters.all")}</SelectItem>
              <SelectItem value="active">
                {t("polls.filters.active")}
              </SelectItem>
              <SelectItem value="closed">
                {t("polls.filters.closed")}
              </SelectItem>
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="created">{t("polls.sort.created")}</SelectItem>
              <SelectItem value="activity">
                {t("polls.sort.activity")}
              </SelectItem>
              <SelectItem value="votes">{t("polls.sort.votes")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        {polls.data?.data.map((poll) => {
          const previewOptions = poll.options.slice(0, 3)
          const remainingOptions = poll.options.length - previewOptions.length

          return (
            <button
              key={poll.id}
              type="button"
              className="bg-card text-card-foreground flex flex-col gap-0 overflow-hidden rounded-xl border py-0 text-left shadow-sm transition-colors hover:border-primary/60 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
              onClick={() => setOpenPollId(poll.id)}
            >
              <span className="flex flex-col gap-3 p-5 sm:p-6">
                <span className="flex items-start justify-between gap-3">
                  <span className="text-xl font-medium leading-tight">
                    {poll.title}
                  </span>
                  {poll.status === "closed" ? (
                    <Badge variant="outline" className="shrink-0">
                      {t("polls.closed")}
                    </Badge>
                  ) : null}
                </span>
              </span>
              <span className="flex flex-col gap-3 px-5 pb-5 sm:px-6 sm:pb-6">
                <span className="grid gap-2">
                  {previewOptions.map((option) => (
                    <span
                      key={option.id}
                      className="rounded-md border border-border/70 px-3 py-2 text-sm"
                    >
                      {option.label}
                    </span>
                  ))}
                  {remainingOptions > 0 ? (
                    <span className="self-end text-right text-sm text-muted-foreground">
                      {t("polls.moreOptions", { count: remainingOptions })}
                    </span>
                  ) : null}
                </span>
                <span className="self-end text-right text-sm text-muted-foreground">
                  {poll.total_votes} {t("polls.votes")}
                </span>
              </span>
            </button>
          )
        })}
      </div>

      <Dialog
        open={Boolean(openPoll)}
        onOpenChange={(open) => {
          if (!open) setOpenPollId(null)
        }}
      >
        {openPoll ? (
          <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-2xl">
            <DialogHeader>
              <div className="flex items-start gap-3 pr-6">
                <DialogTitle>{openPoll.title}</DialogTitle>
                {openPoll.status === "closed" ? (
                  <Badge variant="outline" className="shrink-0">
                    {t("polls.closed")}
                  </Badge>
                ) : null}
              </div>
              {openPoll.description ? (
                <DialogDescription>{openPoll.description}</DialogDescription>
              ) : null}
            </DialogHeader>
            <div className="grid gap-3">
              {openPoll.options.map((option) => {
                const checked = selected.includes(option.id)
                const disabled =
                  !user ||
                  openPoll.status === "closed" ||
                  (!openPoll.allow_vote_change && openPoll.has_voted) ||
                  (!checked && selected.length >= maxSelections)

                return (
                  <label
                    key={option.id}
                    htmlFor={`poll-${openPoll.id}-${option.id}`}
                    className={`flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40 focus-within:border-primary ${
                      checked
                        ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                        : "border-border/70"
                    } ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
                  >
                    <Checkbox
                      id={`poll-${openPoll.id}-${option.id}`}
                      checked={checked}
                      disabled={disabled}
                      onCheckedChange={(value) =>
                        setSelections((current) => {
                          const currentSelected =
                            current[openPoll.id] ?? openPoll.selected_option_ids
                          return {
                            ...current,
                            [openPoll.id]: value
                              ? [...currentSelected, option.id]
                              : currentSelected.filter(
                                  (id) => id !== option.id,
                                ),
                          }
                        })
                      }
                    />
                    <span>
                      <span className="font-medium">{option.label}</span>
                      {option.description ? (
                        <span className="block text-sm text-muted-foreground">
                          {option.description}
                        </span>
                      ) : null}
                      {openPoll.can_view_results &&
                      option.votes !== null &&
                      option.votes !== undefined ? (
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {option.votes} · {option.percentage?.toFixed(1)}%
                        </span>
                      ) : null}
                    </span>
                  </label>
                )
              })}
            </div>
            <DialogFooter className="items-center sm:justify-between">
              <div className="text-sm text-muted-foreground">
                {openPoll.status === "closed"
                  ? t("polls.closed")
                  : !user
                    ? t("polls.signInToVote")
                    : null}
              </div>
              <Button
                disabled={
                  !user ||
                  openPoll.status === "closed" ||
                  selected.length === 0 ||
                  (openPoll.has_voted && !openPoll.allow_vote_change) ||
                  vote.isPending
                }
                onClick={() =>
                  vote.mutate({ pollId: openPoll.id, optionIds: selected })
                }
              >
                {openPoll.has_voted ? t("polls.changeVote") : t("polls.vote")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  )
}
