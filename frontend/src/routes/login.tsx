import { createFileRoute } from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { Button } from "@/components/ui/button"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/login")({
  component: Login,
  head: () => ({
    meta: [
      {
        title: "Log In - FastAPI Template",
      },
    ],
  }),
})

function Login() {
  const { loginWithSteam } = useAuth()

  return (
    <SidebarProvider>
      <AppSidebar forceLoginAction />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
        </header>
        <main className="flex flex-1 items-center justify-center p-6 md:p-8">
          <div className="w-full max-w-sm rounded-lg border bg-card p-6 shadow-sm">
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
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}

export default Login
