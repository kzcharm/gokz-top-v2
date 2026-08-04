import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"

import {
  type AdminTournamentAchievementPublic,
  AdminTournamentsService,
  type TournamentLevel,
  type TournamentPublic,
  UsersService,
} from "@/client"
import {
  AdminControlsCard,
  AdminPageHeader,
  AdminTableCard,
} from "@/components/Admin/AdminPageLayout"
import {
  PlayerDisplay,
  type PlayerDisplayPlayer,
} from "@/components/Common/PlayerDisplay"
import { PlayerSearchSelect } from "@/components/Common/PlayerSearchSelect"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { getPageTitle } from "@/lib/site"
import { isSuperuser } from "@/lib/user-roles"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/admin/tournaments")({
  component: AdminTournaments,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
    const user = await UsersService.readUserMe().catch(() => {
      localStorage.removeItem("access_token")
      throw redirect({ to: "/login" })
    })
    if (!isSuperuser(user)) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({ meta: [{ title: getPageTitle() }] }),
})

type TournamentDialogState =
  | { mode: "create"; tournament: null }
  | { mode: "edit"; tournament: TournamentPublic }

type AchievementDialogState =
  | { mode: "create"; achievement: null }
  | { mode: "edit"; achievement: AdminTournamentAchievementPublic }

type DeleteTarget =
  | { type: "tournament"; tournament: TournamentPublic }
  | { type: "achievement"; achievement: AdminTournamentAchievementPublic }
  | null

const LEVELS: TournamentLevel[] = ["S", "A", "B", "C"]
const PLACEMENTS = [
  { value: 1, label: "Champion" },
  { value: 2, label: "Runner-up" },
  { value: 3, label: "Third Place" },
  { value: 4, label: "Semifinalist" },
] as const
const PLACEMENT_LABELS = Object.fromEntries(
  PLACEMENTS.map(({ label, value }) => [value, label]),
)

function TournamentDialog({
  state,
  open,
  onOpenChange,
  onSaved,
}: {
  state: TournamentDialogState
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [name, setName] = useState("")
  const [startsOn, setStartsOn] = useState("")
  const [endsOn, setEndsOn] = useState("")
  const [officialUrl, setOfficialUrl] = useState("")
  const [level, setLevel] = useState<TournamentLevel>("C")

  useEffect(() => {
    if (!open) return
    if (state.mode === "create") {
      setName("")
      setStartsOn("")
      setEndsOn("")
      setOfficialUrl("")
      setLevel("C")
      return
    }
    setName(state.tournament.name)
    setStartsOn(state.tournament.starts_on)
    setEndsOn(state.tournament.ends_on)
    setOfficialUrl(state.tournament.official_url ?? "")
    setLevel(state.tournament.level)
  }, [open, state])

  const createMutation = useMutation({
    mutationFn: () =>
      AdminTournamentsService.createAdminTournament({
        requestBody: {
          name: name.trim(),
          starts_on: startsOn,
          ...(endsOn ? { ends_on: endsOn } : {}),
          official_url: officialUrl.trim() || null,
          level,
        },
      }),
    onSuccess: () => {
      showSuccessToast("Tournament created")
      onSaved()
    },
    onError: handleError.bind(showErrorToast),
  })
  const updateMutation = useMutation({
    mutationFn: () =>
      state.mode === "edit"
        ? AdminTournamentsService.updateAdminTournament({
            tournamentId: state.tournament.id,
            requestBody: {
              name: name.trim(),
              starts_on: startsOn,
              ...(endsOn ? { ends_on: endsOn } : { ends_on: null }),
              official_url: officialUrl.trim() || null,
              level,
            },
          })
        : Promise.reject(new Error("No tournament selected")),
    onSuccess: () => {
      showSuccessToast("Tournament updated")
      onSaved()
    },
    onError: handleError.bind(showErrorToast),
  })
  const pending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {state.mode === "create" ? "Create Tournament" : "Edit Tournament"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2 text-sm font-medium">
            <label htmlFor="tournament-name">
              Name
              <span aria-hidden="true" className="ml-1 text-destructive">
                *
              </span>
            </label>
            <Input
              id="tournament-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2 text-sm font-medium">
              <label htmlFor="tournament-start-date">
                Start Date
                <span aria-hidden="true" className="ml-1 text-destructive">
                  *
                </span>
              </label>
              <Input
                id="tournament-start-date"
                type="date"
                value={startsOn}
                onChange={(event) => setStartsOn(event.target.value)}
              />
            </div>
            <div className="grid gap-2 text-sm font-medium">
              <label htmlFor="tournament-end-date">End Date</label>
              <Input
                id="tournament-end-date"
                type="date"
                value={endsOn}
                onChange={(event) => setEndsOn(event.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-2 text-sm font-medium">
            <label htmlFor="tournament-official-url">
              Official / Results URL
            </label>
            <Input
              id="tournament-official-url"
              type="url"
              value={officialUrl}
              onChange={(event) => setOfficialUrl(event.target.value)}
            />
          </div>
          <div className="grid gap-2 text-sm font-medium">
            <label htmlFor="tournament-level">
              Level
              <span aria-hidden="true" className="ml-1 text-destructive">
                *
              </span>
            </label>
            <Select
              value={level}
              onValueChange={(value) => setLevel(value as TournamentLevel)}
            >
              <SelectTrigger id="tournament-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={pending}>
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton
            loading={pending}
            onClick={() =>
              state.mode === "create"
                ? createMutation.mutate()
                : updateMutation.mutate()
            }
          >
            Save
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AchievementDialog({
  state,
  tournaments,
  open,
  onOpenChange,
  onSaved,
}: {
  state: AchievementDialogState
  tournaments: TournamentPublic[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [tournamentId, setTournamentId] = useState("")
  const [selectedPlayer, setSelectedPlayer] =
    useState<PlayerDisplayPlayer | null>(null)
  const [placement, setPlacement] = useState("1")

  useEffect(() => {
    if (!open) return
    if (state.mode === "create") {
      setTournamentId(tournaments[0]?.id ?? "")
      setSelectedPlayer(null)
      setPlacement("1")
      return
    }
    setTournamentId(state.achievement.tournament.id)
    setSelectedPlayer(state.achievement.player)
    setPlacement(String(state.achievement.placement))
  }, [open, state, tournaments])

  const createMutation = useMutation({
    mutationFn: () =>
      AdminTournamentsService.createAdminTournamentAchievement({
        requestBody: {
          tournament_id: tournamentId,
          player_steamid64: selectedPlayer?.steamid64 ?? "",
          placement: Number(placement),
        },
      }),
    onSuccess: () => {
      showSuccessToast("Achievement assigned")
      onSaved()
    },
    onError: handleError.bind(showErrorToast),
  })
  const updateMutation = useMutation({
    mutationFn: () =>
      state.mode === "edit"
        ? AdminTournamentsService.updateAdminTournamentAchievement({
            achievementId: state.achievement.id,
            requestBody: { placement: Number(placement) },
          })
        : Promise.reject(new Error("No achievement selected")),
    onSuccess: () => {
      showSuccessToast("Achievement updated")
      onSaved()
    },
    onError: handleError.bind(showErrorToast),
  })
  const pending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {state.mode === "create"
              ? "Assign Achievement"
              : "Edit Achievement"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2 text-sm font-medium">
            <label htmlFor="achievement-tournament">
              Tournament
              <span aria-hidden="true" className="ml-1 text-destructive">
                *
              </span>
            </label>
            <Select
              value={tournamentId}
              onValueChange={setTournamentId}
              disabled={state.mode === "edit"}
            >
              <SelectTrigger id="achievement-tournament">
                <SelectValue placeholder="Select a tournament" />
              </SelectTrigger>
              <SelectContent>
                {tournaments.map((tournament) => (
                  <SelectItem key={tournament.id} value={tournament.id}>
                    {tournament.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <PlayerSearchSelect
            id="achievement-player"
            ariaLabel="Player"
            label="Player"
            required
            disabled={state.mode === "edit"}
            searchQueryKey="tournament-achievement"
            selectedPlayer={selectedPlayer}
            onSelectPlayer={setSelectedPlayer}
            onClearPlayer={() => setSelectedPlayer(null)}
          />
          <div className="grid gap-2 text-sm font-medium">
            <label htmlFor="achievement-placement">
              Placement
              <span aria-hidden="true" className="ml-1 text-destructive">
                *
              </span>
            </label>
            <Select value={placement} onValueChange={setPlacement}>
              <SelectTrigger id="achievement-placement">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLACEMENTS.map((value) => (
                  <SelectItem key={value.value} value={String(value.value)}>
                    {value.value} · {value.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={pending}>
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton
            loading={pending}
            onClick={() =>
              state.mode === "create"
                ? createMutation.mutate()
                : updateMutation.mutate()
            }
          >
            Save
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AdminTournaments() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [tournamentDialogState, setTournamentDialogState] =
    useState<TournamentDialogState>({ mode: "create", tournament: null })
  const [achievementDialogState, setAchievementDialogState] =
    useState<AchievementDialogState>({ mode: "create", achievement: null })
  const [tournamentDialogOpen, setTournamentDialogOpen] = useState(false)
  const [achievementDialogOpen, setAchievementDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null)
  const tournamentsQuery = useQuery({
    queryKey: ["admin-tournaments"],
    queryFn: () => AdminTournamentsService.readAdminTournaments({ limit: 100 }),
  })
  const achievementsQuery = useQuery({
    queryKey: ["admin-tournament-achievements"],
    queryFn: () =>
      AdminTournamentsService.readAdminTournamentAchievements({ limit: 100 }),
  })
  const tournaments = tournamentsQuery.data?.data ?? []
  const achievements = achievementsQuery.data?.data ?? []
  const refresh = () => {
    setTournamentDialogOpen(false)
    setAchievementDialogOpen(false)
    void queryClient.invalidateQueries({ queryKey: ["admin-tournaments"] })
    void queryClient.invalidateQueries({
      queryKey: ["admin-tournament-achievements"],
    })
  }
  const deleteTournament = useMutation({
    mutationFn: (id: string) =>
      AdminTournamentsService.deleteAdminTournament({ tournamentId: id }),
    onSuccess: () => {
      setDeleteTarget(null)
      showSuccessToast("Tournament deleted")
      refresh()
    },
    onError: handleError.bind(showErrorToast),
  })
  const deleteAchievement = useMutation({
    mutationFn: (id: string) =>
      AdminTournamentsService.deleteAdminTournamentAchievement({
        achievementId: id,
      }),
    onSuccess: () => {
      setDeleteTarget(null)
      showSuccessToast("Achievement revoked")
      refresh()
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <div className="flex flex-col gap-6">
      <AdminPageHeader title="Tournaments" />
      <Tabs defaultValue="tournaments" className="gap-5">
        <TabsList className="w-full justify-start sm:w-fit">
          <TabsTrigger value="tournaments">Tournaments</TabsTrigger>
          <TabsTrigger value="achievements">Achievements</TabsTrigger>
        </TabsList>
        <TabsContent value="tournaments" className="space-y-5">
          <AdminControlsCard>
            <Button
              onClick={() => {
                setTournamentDialogState({ mode: "create", tournament: null })
                setTournamentDialogOpen(true)
              }}
            >
              <Plus className="size-4" /> Create Tournament
            </Button>
          </AdminControlsCard>
          <AdminTableCard>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="px-6 py-3">Tournament</th>
                    <th className="px-6 py-3">Start Date</th>
                    <th className="px-6 py-3">End Date</th>
                    <th className="px-6 py-3">Level</th>
                    <th className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tournaments.map((tournament) => (
                    <tr key={tournament.id} className="border-b last:border-0">
                      <td className="px-6 py-4 font-medium">
                        {tournament.name}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {tournament.starts_on}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {tournament.ends_on}
                      </td>
                      <td className="px-6 py-4">{tournament.level}</td>
                      <td className="px-6 py-4">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              setTournamentDialogState({
                                mode: "edit",
                                tournament,
                              })
                              setTournamentDialogOpen(true)
                            }}
                            aria-label="Edit tournament"
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive hover:text-destructive"
                            onClick={() =>
                              setDeleteTarget({
                                type: "tournament",
                                tournament,
                              })
                            }
                            aria-label="Delete tournament"
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {tournamentsQuery.isLoading ? (
                <p className="p-6 text-sm text-muted-foreground">
                  Loading tournaments...
                </p>
              ) : null}
              {!tournamentsQuery.isLoading && tournaments.length === 0 ? (
                <p className="p-6 text-sm text-muted-foreground">
                  No tournaments found.
                </p>
              ) : null}
            </div>
          </AdminTableCard>
        </TabsContent>
        <TabsContent value="achievements" className="space-y-5">
          <AdminControlsCard>
            <Button
              disabled={tournaments.length === 0}
              onClick={() => {
                setAchievementDialogState({ mode: "create", achievement: null })
                setAchievementDialogOpen(true)
              }}
            >
              <Plus className="size-4" /> Assign Achievement
            </Button>
          </AdminControlsCard>
          <AdminTableCard>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="px-6 py-3">Player</th>
                    <th className="px-6 py-3">Tournament</th>
                    <th className="px-6 py-3">Placement</th>
                    <th className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {achievements.map((achievement) => (
                    <tr key={achievement.id} className="border-b last:border-0">
                      <td className="px-6 py-4">
                        <PlayerDisplay player={achievement.player} />
                      </td>
                      <td className="px-6 py-4">
                        {achievement.tournament.name}
                      </td>
                      <td className="px-6 py-4">
                        {PLACEMENT_LABELS[achievement.placement]}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              setAchievementDialogState({
                                mode: "edit",
                                achievement,
                              })
                              setAchievementDialogOpen(true)
                            }}
                            aria-label="Edit achievement"
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive hover:text-destructive"
                            onClick={() =>
                              setDeleteTarget({
                                type: "achievement",
                                achievement,
                              })
                            }
                            aria-label="Revoke achievement"
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {achievementsQuery.isLoading ? (
                <p className="p-6 text-sm text-muted-foreground">
                  Loading achievements...
                </p>
              ) : null}
              {!achievementsQuery.isLoading && achievements.length === 0 ? (
                <p className="p-6 text-sm text-muted-foreground">
                  No achievements found.
                </p>
              ) : null}
            </div>
          </AdminTableCard>
        </TabsContent>
      </Tabs>
      <TournamentDialog
        state={tournamentDialogState}
        open={tournamentDialogOpen}
        onOpenChange={setTournamentDialogOpen}
        onSaved={refresh}
      />
      <AchievementDialog
        state={achievementDialogState}
        tournaments={tournaments}
        open={achievementDialogOpen}
        onOpenChange={setAchievementDialogOpen}
        onSaved={refresh}
      />
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null)
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {deleteTarget?.type === "tournament"
                ? "Delete Tournament?"
                : "Revoke Achievement?"}
            </DialogTitle>
            <DialogDescription>
              {deleteTarget?.type === "tournament"
                ? `Delete ${deleteTarget.tournament.name} and permanently revoke all of its achievements?`
                : "This permanently revokes the player’s tournament achievement."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button
                variant="outline"
                disabled={
                  deleteTournament.isPending || deleteAchievement.isPending
                }
              >
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton
              variant="destructive"
              loading={
                deleteTournament.isPending || deleteAchievement.isPending
              }
              onClick={() => {
                if (deleteTarget?.type === "tournament") {
                  deleteTournament.mutate(deleteTarget.tournament.id)
                  return
                }
                if (deleteTarget?.type === "achievement") {
                  deleteAchievement.mutate(deleteTarget.achievement.id)
                }
              }}
            >
              {deleteTarget?.type === "tournament"
                ? "Delete Tournament"
                : "Revoke Achievement"}
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
