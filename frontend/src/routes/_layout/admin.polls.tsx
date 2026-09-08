import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ChangeEvent } from "react"
import { useState } from "react"

import { OpenAPI } from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"

type Poll = {
  id: string
  title: string
  description?: string | null
  status: string
  total_votes: number
  options: {
    id: string
    label: string
    description?: string | null
    votes?: number | null
  }[]
  voters: { steamid64: string; option_ids: string[] }[]
}

type DraftOption = {
  label: string
  description: string
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("access_token")
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  })
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => null))?.detail ?? "Request failed",
    )
  return response.json() as Promise<T>
}

export const Route = createFileRoute("/_layout/admin/polls")({
  component: AdminPolls,
  beforeLoad: async () => {
    if (!isLoggedIn()) throw redirect({ to: "/login" })
    const user = await request<{ roles?: string[] }>("/v1/users/me")
    if (!isSuperuser(user as never)) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: getPageTitle("Admin Polls") }] }),
})

function AdminPolls() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [endsAt, setEndsAt] = useState("")
  const [maxSelections, setMaxSelections] = useState("1")
  const [allowVoteChange, setAllowVoteChange] = useState(true)
  const [options, setOptions] = useState<DraftOption[]>([
    { label: "", description: "" },
    { label: "", description: "" },
  ])
  const polls = useQuery({
    queryKey: ["admin-polls"],
    queryFn: () =>
      request<{ data: Poll[]; count: number }>("/v1/admin/polls?limit=100"),
  })
  const create = useMutation({
    mutationFn: () =>
      request<Poll>("/v1/admin/polls", {
        method: "POST",
        body: JSON.stringify({
          title,
          description: description || null,
          ends_at: endsAt ? new Date(endsAt).toISOString() : null,
          max_selections: Number.parseInt(maxSelections, 10) || 0,
          allow_vote_change: allowVoteChange,
          options: options
            .filter((option) => option.label.trim())
            .map((option) => ({
              label: option.label,
              description: option.description.trim() || null,
            })),
        }),
      }),
    onSuccess: () => {
      setTitle("")
      setDescription("")
      setEndsAt("")
      setMaxSelections("1")
      setAllowVoteChange(true)
      setOptions([
        { label: "", description: "" },
        { label: "", description: "" },
      ])
      queryClient.invalidateQueries({ queryKey: ["admin-polls"] })
    },
  })
  const lifecycle = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "active" | "closed" }) =>
      request(`/v1/admin/polls/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["admin-polls"] }),
  })
  const remove = useMutation({
    mutationFn: (id: string) =>
      request(`/v1/admin/polls/${id}`, { method: "DELETE" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["admin-polls"] }),
  })
  if (!user) return null
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-semibold">Admin Polls</h1>
        <p className="mt-2 text-muted-foreground">
          Create and manage community polls.
        </p>
      </header>
      <section className="max-w-2xl space-y-4 border-b border-border/70 pb-8">
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
          <label htmlFor="poll-max-selections" className="space-y-1 text-sm">
            <span className="text-muted-foreground">
              Maximum selections (0 = unlimited)
            </span>
            <Input
              id="poll-max-selections"
              type="number"
              min={0}
              max={100}
              value={maxSelections}
              onChange={(e) => setMaxSelections(e.target.value)}
            />
          </label>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Checkbox
            id="poll-allow-vote-change"
            checked={allowVoteChange}
            onCheckedChange={(checked) => setAllowVoteChange(checked === true)}
          />
          <label htmlFor="poll-allow-vote-change">
            Allow voters to change their selection
          </label>
        </div>
        <div className="space-y-2">
          {options.map((option, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-2">
              <Input
                placeholder={`Option ${index + 1}`}
                value={option.label}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setOptions((current) =>
                    current.map((item, i) =>
                      i === index ? { ...item, label: e.target.value } : item,
                    ),
                  )
                }
              />
              <Input
                placeholder="Option description (optional)"
                value={option.description}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setOptions((current) =>
                    current.map((item, i) =>
                      i === index
                        ? { ...item, description: e.target.value }
                        : item,
                    ),
                  )
                }
              />
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              setOptions((current) => [
                ...current,
                { label: "", description: "" },
              ])
            }
          >
            Add option
          </Button>
          <Button
            disabled={
              create.isPending ||
              !title.trim() ||
              options.filter((option) => option.label.trim()).length < 2 ||
              !Number.isInteger(Number(maxSelections)) ||
              Number(maxSelections) < 0 ||
              Number(maxSelections) > 100
            }
            onClick={() => create.mutate()}
          >
            Create poll
          </Button>
        </div>
      </section>
      <div className="divide-y divide-border/70">
        {polls.data?.data.map((poll) => (
          <section key={poll.id} className="py-5">
            <div className="flex justify-between">
              <div>
                <h2 className="text-lg font-medium">{poll.title}</h2>
                <p className="text-sm text-muted-foreground">
                  {poll.status} · {poll.total_votes} votes
                </p>
              </div>
              <div className="flex gap-2">
                {poll.status === "active" ? (
                  <Button
                    variant="outline"
                    onClick={() =>
                      lifecycle.mutate({ id: poll.id, status: "closed" })
                    }
                  >
                    Close
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    onClick={() =>
                      lifecycle.mutate({ id: poll.id, status: "active" })
                    }
                  >
                    Reopen
                  </Button>
                )}
                <Button variant="ghost" onClick={() => remove.mutate(poll.id)}>
                  Delete
                </Button>
              </div>
            </div>
            <div className="mt-3 space-y-1 text-sm">
              {poll.options.map((option) => (
                <div key={option.id}>
                  <div className="flex justify-between">
                    <span>{option.label}</span>
                    <span>{option.votes ?? 0}</span>
                  </div>
                  {option.description ? (
                    <p className="text-xs text-muted-foreground">
                      {option.description}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {poll.voters.length} voter records
            </p>
          </section>
        ))}
      </div>
    </div>
  )
}
