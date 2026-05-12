import { AxiosError } from "axios"
import type { ApiError } from "./client"

export function extractErrorMessage(err: ApiError | Error | unknown): string {
  const apiError = err as Partial<ApiError> | undefined
  const errBody = apiError?.body
  const errDetail =
    typeof errBody === "object" && errBody !== null && "detail" in errBody
      ? (errBody.detail as string | { msg?: string }[] | undefined)
      : undefined

  if (Array.isArray(errDetail) && errDetail.length > 0) {
    return errDetail[0]?.msg || apiError?.message || "Something went wrong."
  }

  if (typeof errDetail === "string") {
    return errDetail
  }

  if (err instanceof Error && !(err instanceof AxiosError)) {
    return err.message || "Something went wrong."
  }

  if (err instanceof AxiosError) {
    return err.message
  }

  return "Something went wrong."
}

export const handleError = function (
  this: (msg: string) => void,
  err: ApiError,
) {
  const errorMessage = extractErrorMessage(err)
  this(errorMessage)
}

export const getInitials = (name: string): string => {
  return name
    .split(" ")
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase()
}
