import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { OpenAPI } from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {t("titles.polls")}
          </h1>
          <p className="mt-2 text-muted-foreground">{t("polls.description")}</p>
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
                {t("polls.filters.archive")}
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
      <div className="divide-y divide-border/70">
        {polls.data?.data.map((poll) => {
          const selected = selections[poll.id] ?? poll.selected_option_ids
          const max =
            poll.max_selections === 0
              ? poll.options.length
              : poll.max_selections
          return (
            <section key={poll.id} className="py-6 first:pt-0">
              <div className="flex flex-wrap justify-between gap-3">
                <div>
                  <h2 className="text-xl font-medium">{poll.title}</h2>
                  {poll.description ? (
                    <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                      {poll.description}
                    </p>
                  ) : null}
                </div>
                <span className="text-sm text-muted-foreground">
                  {poll.total_votes} {t("polls.votes")}
                </span>
              </div>
              <div className="mt-4 grid gap-3">
                {poll.options.map((option) => {
                  const checked = selected.includes(option.id)
                  return (
                    <label
                      key={option.id}
                      htmlFor={`poll-${poll.id}-${option.id}`}
                      className="flex cursor-pointer gap-3 rounded-lg border border-border/70 p-3 hover:bg-muted/40"
                    >
                      <Checkbox
                        id={`poll-${poll.id}-${option.id}`}
                        checked={checked}
                        disabled={
                          !user ||
                          poll.status === "closed" ||
                          (!poll.allow_vote_change && poll.has_voted) ||
                          (!checked && selected.length >= max)
                        }
                        onCheckedChange={(value) =>
                          setSelections((current) => ({
                            ...current,
                            [poll.id]: value
                              ? [...selected, option.id]
                              : selected.filter((id) => id !== option.id),
                          }))
                        }
                      />
                      <span>
                        <span className="font-medium">{option.label}</span>
                        {option.description ? (
                          <span className="block text-sm text-muted-foreground">
                            {option.description}
                          </span>
                        ) : null}
                        {poll.can_view_results &&
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
              <div className="mt-4 flex items-center gap-3">
                <Button
                  disabled={
                    !user ||
                    poll.status === "closed" ||
                    selected.length === 0 ||
                    (poll.has_voted && !poll.allow_vote_change) ||
                    vote.isPending
                  }
                  onClick={() =>
                    vote.mutate({ pollId: poll.id, optionIds: selected })
                  }
                >
                  {poll.has_voted ? t("polls.changeVote") : t("polls.vote")}
                </Button>
                {!user && poll.status === "active" ? (
                  <span className="text-sm text-muted-foreground">
                    {t("polls.signInToVote")}
                  </span>
                ) : null}
                {poll.status === "closed" ? (
                  <span className="text-sm text-muted-foreground">
                    {t("polls.closed")}
                  </span>
                ) : null}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
