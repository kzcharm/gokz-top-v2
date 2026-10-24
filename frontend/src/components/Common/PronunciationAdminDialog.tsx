import { useMutation, useQuery } from "@tanstack/react-query"
import { LoaderCircle, RefreshCw } from "lucide-react"
import { useEffect, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import {
  MapsService,
  type PronunciationRegenerate,
  PronunciationsService,
} from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useAuth from "@/hooks/useAuth"
import {
  type PronunciationTarget,
  usePronunciation,
} from "@/hooks/usePronunciation"
import { canAccessAdminMaps, canModerateBansAndRecords } from "@/lib/user-roles"

export function PronunciationAdminDialog({
  target,
  menu = false,
  closeMenu,
}: {
  target: PronunciationTarget
  menu?: boolean
  closeMenu?: () => void
}) {
  const { user } = useAuth()
  const allowed =
    canModerateBansAndRecords(user) ||
    (target.kind === "map" && canAccessAdminMaps(user))
  if (!allowed) return null
  return (
    <PronunciationEditor target={target} menu={menu} closeMenu={closeMenu} />
  )
}

function PronunciationEditor({
  target,
  menu,
  closeMenu,
}: {
  target: PronunciationTarget
  menu: boolean
  closeMenu?: () => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const [voice, setVoice] = useState("")
  const [language, setLanguage] = useState("")
  const { play } = usePronunciation(target)
  const key =
    target.kind === "map" ? (target.id ?? target.name) : target.identifier
  const query = useQuery({
    queryKey: ["pronunciation-editor", target.kind, key],
    enabled: open,
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      if (target.kind === "player")
        return {
          current: await PronunciationsService.readAdminPlayerPronunciation({
            identifier: target.identifier,
          }),
          mapId: null,
        }
      const mapId =
        target.id ??
        (
          await MapsService.readMaps({
            name: target.name,
            limit: 1,
            includeInvalid: true,
          })
        )[0]?.id
      if (mapId == null) throw new Error("Map not found")
      return {
        current: await PronunciationsService.readAdminMapPronunciation({
          mapId,
        }),
        mapId,
      }
    },
  })
  const options = useQuery({
    queryKey: ["pronunciation-options"],
    enabled: open,
    staleTime: 600_000,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: () => PronunciationsService.readPronunciationOptions(),
  })
  useEffect(() => {
    if (query.data && open) {
      setText(query.data.current.spoken_text)
      setVoice(query.data.current.voice_id)
      setLanguage(query.data.current.language_code ?? "")
    }
  }, [query.data, open])
  function changeOpen(value: boolean) {
    setOpen(value)
    if (!value) closeMenu?.()
  }
  const mutation = useMutation({
    mutationFn: (requestBody: PronunciationRegenerate) =>
      target.kind === "player"
        ? PronunciationsService.regeneratePlayerPronunciation({
            identifier: target.identifier,
            requestBody,
          })
        : PronunciationsService.regenerateMapPronunciation({
            mapId: query.data!.mapId!,
            requestBody,
          }),
    onSuccess: () => {
      changeOpen(false)
      play()
    },
    onError: () => toast.error(t("pronunciationAdmin.failed")),
  })
  const loaded =
    query.data && options.data && !query.isFetching && !options.isFetching
  const failed = query.isError || options.isError
  const controlClass =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
  return (
    <>
      {menu ? (
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            setOpen(true)
          }}
        >
          <RefreshCw />
          {t("pronunciationAdmin.open")}
        </DropdownMenuItem>
      ) : (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="shrink-0 rounded-full"
          aria-label={t("pronunciationAdmin.open")}
          title={t("pronunciationAdmin.open")}
          onClick={() => setOpen(true)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
        </Button>
      )}
      <Dialog open={open} onOpenChange={changeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("pronunciationAdmin.open")}</DialogTitle>
            <DialogDescription>{target.name}</DialogDescription>
          </DialogHeader>
          {failed ? (
            <div className="flex flex-col gap-3">
              <p role="alert" className="text-sm text-destructive">
                {t("pronunciationAdmin.loadFailed")}
              </p>
              <Button
                variant="outline"
                onClick={() => {
                  void query.refetch()
                  void options.refetch()
                }}
              >
                {t("pronunciationAdmin.retry")}
              </Button>
            </div>
          ) : !loaded ? (
            <output className="flex items-center gap-2 py-4 text-sm">
              <LoaderCircle className="animate-spin" data-icon="inline-start" />
              {t("pronunciationAdmin.loading")}
            </output>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                mutation.mutate({
                  text: text.trim(),
                  voice_id: voice,
                  language_code: language || null,
                })
              }}
              className="flex flex-col gap-4"
            >
              <FieldGroup>
                <Field data-disabled={mutation.isPending}>
                  <FieldLabel htmlFor={`${id}-voice`}>
                    {t("pronunciationAdmin.voice")}
                  </FieldLabel>
                  <Select
                    value={voice}
                    onValueChange={setVoice}
                    disabled={mutation.isPending}
                  >
                    <SelectTrigger id={`${id}-voice`} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {!options.data.voices.some(
                          (item) => item.id === voice,
                        ) &&
                          voice && (
                            <SelectItem value={voice}>{voice}</SelectItem>
                          )}
                        {options.data.voices.map((item) => (
                          <SelectItem key={item.id} value={item.id}>
                            {item.name}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
                <Field data-disabled={mutation.isPending}>
                  <FieldLabel htmlFor={`${id}-language`}>
                    {t("pronunciationAdmin.language")}
                  </FieldLabel>
                  <Select
                    value={language || "auto"}
                    onValueChange={(value) =>
                      setLanguage(value === "auto" ? "" : value)
                    }
                    disabled={mutation.isPending}
                  >
                    <SelectTrigger id={`${id}-language`} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem value="auto">
                          {t("pronunciationAdmin.auto")}
                        </SelectItem>
                        {options.data.languages.map((item) => (
                          <SelectItem key={item.code} value={item.code}>
                            {item.name}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
                <Field data-disabled={mutation.isPending}>
                  <FieldLabel htmlFor={`${id}-text`}>
                    {t("pronunciationAdmin.text")}
                  </FieldLabel>
                  <textarea
                    id={`${id}-text`}
                    className={`${controlClass} min-h-24 resize-y`}
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    maxLength={500}
                    required
                    disabled={mutation.isPending}
                  />
                </Field>
              </FieldGroup>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  disabled={mutation.isPending}
                  onClick={() => {
                    setText(query.data.current.source_text)
                    setVoice(options.data.default_voice_id)
                    setLanguage("")
                  }}
                >
                  {t("pronunciationAdmin.defaults")}
                </Button>
                <Button
                  type="submit"
                  disabled={mutation.isPending || !text.trim() || !voice}
                >
                  {mutation.isPending ? (
                    <LoaderCircle
                      className="animate-spin"
                      data-icon="inline-start"
                      aria-hidden="true"
                    />
                  ) : (
                    <RefreshCw data-icon="inline-start" aria-hidden="true" />
                  )}
                  {t("pronunciationAdmin.generate")}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
