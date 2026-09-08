import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus } from "lucide-react"
import { type ChangeEvent, useState } from "react"
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
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useAuth from "@/hooks/useAuth"
import { isSuperuser } from "@/lib/user-roles"

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
  created_by_steamid64?: string | null
}

type DraftOption = { label: string; description: string }

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
  const [editor, setEditor] = useState<"create" | Poll | null>(null)
  const [pendingAction, setPendingAction] = useState<{
    type: "delete" | "close" | "reopen"
    poll: Poll
  } | null>(null)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [endsAt, setEndsAt] = useState("")
  const [maxSelectionsDraft, setMaxSelectionsDraft] = useState("1")
  const [allowVoteChange, setAllowVoteChange] = useState(true)
  const [options, setOptions] = useState<DraftOption[]>([
    { label: "", description: "" },
    { label: "", description: "" },
  ])
  const admin = Boolean(user && isSuperuser(user))
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
  const save = useMutation({
    mutationFn: () => {
      const payload = {
        title: title.trim(),
        description: description.trim() || null,
        ends_at: endsAt ? new Date(endsAt).toISOString() : null,
        max_selections: Number.parseInt(maxSelectionsDraft, 10) || 0,
        allow_vote_change: allowVoteChange,
        options: options
          .filter((o) => o.label.trim())
          .map((o) => ({
            label: o.label.trim(),
            description: o.description.trim() || null,
          })),
      }
      return request<Poll>(
        editor === "create"
          ? "/v1/admin/polls"
          : `/v1/admin/polls/${editor?.id}`,
        {
          method: editor === "create" ? "POST" : "PATCH",
          body: JSON.stringify(payload),
        },
      )
    },
    onSuccess: () => {
      setEditor(null)
      queryClient.invalidateQueries({ queryKey: ["polls"] })
    },
  })
  const lifecycle = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "active" | "closed" }) =>
      request<Poll>(`/v1/admin/polls/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      setOpenPollId(null)
      queryClient.invalidateQueries({ queryKey: ["polls"] })
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) =>
      request(`/v1/admin/polls/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setOpenPollId(null)
      queryClient.invalidateQueries({ queryKey: ["polls"] })
    },
  })
  const openEditor = (poll?: Poll) => {
    setTitle(poll?.title ?? "")
    setDescription(poll?.description ?? "")
    setEndsAt(
      poll?.ends_at ? new Date(poll.ends_at).toISOString().slice(0, 16) : "",
    )
    setMaxSelectionsDraft(String(poll?.max_selections ?? 1))
    setAllowVoteChange(poll?.allow_vote_change ?? true)
    setOptions(
      poll?.options.map((o) => ({
        label: o.label,
        description: o.description ?? "",
      })) ?? [
        { label: "", description: "" },
        { label: "", description: "" },
      ],
    )
    setEditor(poll ?? "create")
  }

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
          {admin ? (
            <Button
              size="icon"
              aria-label="Create poll"
              onClick={() => openEditor()}
            >
              <Plus />
            </Button>
          ) : null}
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
          const previewOptions = (
            poll.can_view_results
              ? [...poll.options].sort(
                  (a, b) => (b.votes ?? 0) - (a.votes ?? 0),
                )
              : poll.options
          ).slice(0, 3)
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
                      className="relative flex items-center gap-3 overflow-hidden rounded-md border border-border/70 bg-background px-3 py-2 text-sm"
                    >
                      {poll.can_view_results &&
                      option.votes !== null &&
                      option.votes !== undefined ? (
                        <span
                          aria-hidden="true"
                          className="pointer-events-none absolute inset-y-0 left-0 bg-primary/20"
                          style={{
                            width: `${Math.max(
                              0,
                              Math.min(option.percentage ?? 0, 100),
                            )}%`,
                          }}
                        />
                      ) : null}
                      <span className="relative z-10 min-w-0 flex-1 truncate">
                        {option.label}
                      </span>
                      {poll.can_view_results &&
                      option.votes !== null &&
                      option.votes !== undefined ? (
                        <span className="relative z-10 shrink-0 whitespace-nowrap text-right text-muted-foreground">
                          {option.votes} · {option.percentage?.toFixed(1)}%
                        </span>
                      ) : null}
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
          <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto bg-background sm:max-w-2xl">
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
              <p className="text-sm text-muted-foreground">
                {openPoll.max_selections === 0
                  ? t("polls.maxVotesUnlimited")
                  : t("polls.maxVotes", { count: openPoll.max_selections })}
              </p>
            </DialogHeader>
            {admin ? (
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openEditor(openPoll)}
                >
                  <Pencil className="mr-2 size-4" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPendingAction({
                      type: openPoll.status === "closed" ? "reopen" : "close",
                      poll: openPoll,
                    })
                  }
                >
                  {openPoll.status === "closed" ? "Reopen" : "Close"}
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() =>
                    setPendingAction({ type: "delete", poll: openPoll })
                  }
                >
                  Delete
                </Button>
              </div>
            ) : null}
            <div className="grid gap-3">
              {openPoll.options.map((option, optionIndex) => {
                const checked = selected.includes(option.id)
                const percentage = Math.max(
                  0,
                  Math.min(option.percentage ?? 0, 100),
                )
                const disabled =
                  !user ||
                  openPoll.status === "closed" ||
                  (!openPoll.allow_vote_change && openPoll.has_voted) ||
                  (!checked && selected.length >= maxSelections)

                return (
                  <button
                    type="button"
                    key={option.id}
                    aria-pressed={checked}
                    disabled={disabled}
                    className={`relative flex w-full cursor-pointer gap-3 overflow-hidden rounded-lg border p-3 text-left transition-colors focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${
                      checked
                        ? "border-primary bg-primary/10 ring-1 ring-primary/20"
                        : "border-border/70 bg-secondary hover:bg-muted/50"
                    } ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
                    onClick={() =>
                      setSelections((current) => {
                        const currentSelected =
                          current[openPoll.id] ?? openPoll.selected_option_ids
                        return {
                          ...current,
                          [openPoll.id]: checked
                            ? currentSelected.filter((id) => id !== option.id)
                            : [...currentSelected, option.id],
                        }
                      })
                    }
                  >
                    {openPoll.can_view_results &&
                    option.votes !== null &&
                    option.votes !== undefined ? (
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-y-0 left-0 bg-primary/20 transition-[width]"
                        style={{ width: `${percentage}%` }}
                      />
                    ) : null}
                    <span className="relative z-10 shrink-0 pt-0.5 text-sm font-semibold tabular-nums text-muted-foreground">
                      {optionIndex + 1}.
                    </span>
                    <span className="relative z-10 flex min-w-0 flex-1 items-start justify-between gap-4">
                      <span className="min-w-0">
                        <span className="font-medium">{option.label}</span>
                        {option.description ? (
                          <span className="block text-sm text-muted-foreground">
                            {option.description}
                          </span>
                        ) : null}
                      </span>
                      {openPoll.can_view_results &&
                      option.votes !== null &&
                      option.votes !== undefined ? (
                        <span className="shrink-0 whitespace-nowrap text-right text-sm text-muted-foreground">
                          {option.votes} · {option.percentage?.toFixed(1)}%
                        </span>
                      ) : null}
                    </span>
                  </button>
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
      <Dialog
        open={editor !== null}
        onOpenChange={(open) => !open && setEditor(null)}
      >
        <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editor === "create" ? "Create poll" : "Edit poll"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              placeholder="Poll title"
              value={title}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setTitle(e.target.value)
              }
            />
            <Input
              placeholder="Description"
              value={description}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setDescription(e.target.value)
              }
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <label htmlFor="poll-ends-at" className="space-y-1 text-sm">
                <span className="text-muted-foreground">
                  Voting ends (optional)
                </span>
                <Input
                  id="poll-ends-at"
                  type="datetime-local"
                  value={endsAt}
                  onChange={(e) => setEndsAt(e.target.value)}
                />
              </label>
              <label
                htmlFor="poll-max-selections"
                className="space-y-1 text-sm"
              >
                <span className="text-muted-foreground">
                  Maximum selections (0 = unlimited)
                </span>
                <Input
                  id="poll-max-selections"
                  type="number"
                  min={0}
                  max={100}
                  value={maxSelectionsDraft}
                  onChange={(e) => setMaxSelectionsDraft(e.target.value)}
                />
              </label>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={allowVoteChange}
                onCheckedChange={(checked) =>
                  setAllowVoteChange(checked === true)
                }
              />
              <span>Allow voters to change their selection</span>
            </div>
            <div className="space-y-2">
              {options.map((option, index) => (
                <div key={index} className="grid gap-2 sm:grid-cols-2">
                  <Input
                    placeholder={`Option ${index + 1}`}
                    value={option.label}
                    onChange={(e) =>
                      setOptions((c) =>
                        c.map((x, i) =>
                          i === index ? { ...x, label: e.target.value } : x,
                        ),
                      )
                    }
                  />
                  <Input
                    placeholder="Option description (optional)"
                    value={option.description}
                    onChange={(e) =>
                      setOptions((c) =>
                        c.map((x, i) =>
                          i === index
                            ? { ...x, description: e.target.value }
                            : x,
                        ),
                      )
                    }
                  />
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              onClick={() =>
                setOptions((c) => [...c, { label: "", description: "" }])
              }
            >
              Add option
            </Button>
          </div>
          <DialogFooter>
            <Button
              disabled={
                save.isPending ||
                !title.trim() ||
                options.filter((o) => o.label.trim()).length < 2
              }
              onClick={() => save.mutate()}
            >
              {editor === "create" ? "Create poll" : "Save changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={pendingAction !== null}
        onOpenChange={(open) => !open && setPendingAction(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {pendingAction?.type === "delete"
                ? "Delete poll?"
                : pendingAction?.type === "close"
                  ? "Close poll?"
                  : "Reopen poll?"}
            </DialogTitle>
            <DialogDescription>
              {pendingAction
                ? pendingAction.type === "delete"
                  ? `This removes “${pendingAction.poll.title}” from public poll lists. Its votes are retained.`
                  : pendingAction.type === "close"
                    ? `Voting will stop for “${pendingAction.poll.title}”.`
                    : `Voting will resume for “${pendingAction.poll.title}”.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingAction(null)}>
              Cancel
            </Button>
            <Button
              variant={
                pendingAction?.type === "delete" ? "destructive" : "default"
              }
              disabled={lifecycle.isPending || remove.isPending}
              onClick={() => {
                if (!pendingAction) return
                if (pendingAction.type === "delete") {
                  remove.mutate(pendingAction.poll.id)
                } else {
                  lifecycle.mutate({
                    id: pendingAction.poll.id,
                    status:
                      pendingAction.type === "close" ? "closed" : "active",
                  })
                }
                setPendingAction(null)
              }}
            >
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
