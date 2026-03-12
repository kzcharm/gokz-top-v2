import { createFileRoute } from "@tanstack/react-router"

import { AppShell } from "@/components/Common/AppShell"
import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/login")({
  component: Login,
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function Login() {
  const { loginWithSteam } = useAuth()

  return (
    <AppShell
      mainClassName="flex flex-1 items-center justify-center p-6 md:p-8"
      contentClassName="max-w-sm"
    >
      <div className="w-full rounded-lg border bg-card p-6 shadow-sm">
        <div className="flex flex-col gap-6">
          <div className="flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-bold">Login with Steam</h1>
            <p className="text-muted-foreground">
              Continue using your Steam account.
            </p>
          </div>
          <Button
            type="button"
            data-testid="steam-login-button"
            onClick={loginWithSteam}
            className="w-full"
          >
            Continue with Steam
          </Button>
        </div>
      </div>
    </AppShell>
  )
}

export default Login
