import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { ApiError, OpenAPI } from "./client"
import { AdminModeProvider } from "./components/admin-mode-provider"
import { WASDNavigationProvider } from "./components/Common/WASDNavigation"
import { DateTimeFormatProvider } from "./components/date-time-format-provider"
import { ScopeProvider } from "./components/scope-provider"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./i18n"
import "./index.css"
import { applyDevBranding } from "./lib/dev-branding"
import { routeTree } from "./routeTree.gen"

applyDevBranding()

OpenAPI.BASE = import.meta.env.VITE_API_URL
OpenAPI.TOKEN = async () => {
  return localStorage.getItem("access_token") || ""
}

const isAuthenticationApiError = (error: ApiError) => {
  if (error.status === 401) {
    return true
  }

  if (error.status !== 403) {
    return false
  }

  const detail =
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body &&
    typeof error.body.detail === "string"
      ? error.body.detail
      : null

  return (
    detail === "Could not validate credentials" || detail === "Inactive user"
  )
}

const handleApiError = (error: Error) => {
  if (error instanceof ApiError && isAuthenticationApiError(error)) {
    localStorage.removeItem("access_token")
    window.location.href = "/login"
  }
}
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <ScopeProvider defaultScope="OVR" storageKey="gokz-app-scope">
        <DateTimeFormatProvider>
          <QueryClientProvider client={queryClient}>
            <AdminModeProvider>
              <WASDNavigationProvider>
                <RouterProvider router={router} />
              </WASDNavigationProvider>
            </AdminModeProvider>
            <Toaster richColors closeButton />
          </QueryClientProvider>
        </DateTimeFormatProvider>
      </ScopeProvider>
    </ThemeProvider>
  </StrictMode>,
)
