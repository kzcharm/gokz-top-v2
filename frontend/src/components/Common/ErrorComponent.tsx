import { Link } from "@tanstack/react-router"
import { Check, Copy } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"

type ErrorComponentProps = {
  error?: unknown
}

const ErrorComponent = ({ error }: ErrorComponentProps = {}) => {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const errorDetails =
    error instanceof Error
      ? `${error.name}: ${error.message}${error.stack ? `\n\n${error.stack}` : ""}`
      : typeof error === "string"
        ? error
        : error
          ? JSON.stringify(error, null, 2)
          : "No error details were provided."

  return (
    <div
      className="flex min-h-screen items-center justify-center flex-col p-4"
      data-testid="error-component"
    >
      <div className="flex items-center z-10">
        <div className="flex flex-col ml-4 items-center justify-center p-4">
          <span className="text-6xl md:text-8xl font-bold leading-none mb-4">
            {t("errors.errorTitle")}
          </span>
          <span className="text-2xl font-bold mb-2">
            {t("errors.notFoundTitle")}
          </span>
        </div>
      </div>

      <p className="text-lg text-muted-foreground mb-4 text-center z-10">
        {t("errors.errorMessage")}
      </p>
      {import.meta.env.DEV ? (
        <div className="mb-4 w-full max-w-3xl rounded-md border border-destructive/40 bg-destructive/5 p-4 text-left">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium text-destructive">
              Development error details
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void navigator.clipboard.writeText(errorDetails).then(() => {
                  setCopied(true)
                  window.setTimeout(() => setCopied(false), 2000)
                })
              }}
            >
              {copied ? (
                <Check className="mr-2 size-4" />
              ) : (
                <Copy className="mr-2 size-4" />
              )}
              {copied ? "Copied" : "Copy details"}
            </Button>
          </div>
          <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
            {errorDetails}
          </pre>
        </div>
      ) : null}
      <Link to="/">
        <Button>{t("common.goHome")}</Button>
      </Link>
    </div>
  )
}

export default ErrorComponent
