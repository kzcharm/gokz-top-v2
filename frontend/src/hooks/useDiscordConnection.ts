import { useMutation } from "@tanstack/react-query"
import { useCallback, useEffect, useRef } from "react"

import { OpenAPI } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { extractErrorMessage } from "@/utils"

const MESSAGE_TYPE = "discord-social-link-verification"
const POPUP_NAME = "discord-social-link"

export default function useDiscordConnection(onLinked: () => void) {
  const popupRef = useRef<Window | null>(null)
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const handleResult = useCallback(
    (status: "success" | "error", message?: string) => {
      if (status === "success") {
        showSuccessToast("Discord account linked")
        onLinked()
      } else {
        showErrorToast(
          message || "Unable to link your Discord account; try again",
        )
      }
    },
    [onLinked, showErrorToast, showSuccessToast],
  )

  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (
        event.origin !== window.location.origin ||
        !popupRef.current ||
        event.source !== popupRef.current
      ) {
        return
      }
      const result = event.data
      if (
        !result ||
        result.type !== MESSAGE_TYPE ||
        (result.status !== "success" && result.status !== "error")
      ) {
        return
      }
      popupRef.current = null
      handleResult(
        result.status,
        typeof result.message === "string" ? result.message : undefined,
      )
    }
    window.addEventListener("message", listener)
    return () => window.removeEventListener("message", listener)
  }, [handleResult])

  useEffect(() => {
    const url = new URL(window.location.href)
    const status = url.searchParams.get("discordVerification")
    if (status !== "success" && status !== "error") return
    const message = url.searchParams.get("message") || undefined
    url.searchParams.delete("discordVerification")
    url.searchParams.delete("message")
    window.history.replaceState(window.history.state, "", url)
    if (window.opener) {
      window.opener.postMessage(
        { type: MESSAGE_TYPE, status, message },
        window.location.origin,
      )
      window.close()
      return
    }
    handleResult(status, message)
  }, [handleResult])

  const mutation = useMutation({
    mutationFn: async (popup: Window) => {
      const response = await fetch(
        `${OpenAPI.BASE}/v1/player-social-links/me/social-links/discord/connection-requests`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
          },
        },
      )
      const body = await response.json()
      if (!response.ok) {
        throw new Error(body.detail || "Unable to start Discord linking")
      }
      if (popup.closed)
        throw new Error("Discord linking window was closed; try again")
      popup.location.replace(body.authorization_url)
      popup.focus()
    },
    onError: (error) => {
      popupRef.current?.close()
      popupRef.current = null
      showErrorToast(extractErrorMessage(error))
    },
  })

  const connect = () => {
    if (mutation.isPending) return
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.focus()
      return
    }
    // Open synchronously during the click so browsers retain the user gesture.
    const popup = window.open("about:blank", POPUP_NAME)
    if (!popup) {
      showErrorToast("Allow popups to continue Discord linking")
      return
    }
    popupRef.current = popup
    mutation.mutate(popup)
  }

  return { connect, isPending: mutation.isPending }
}
