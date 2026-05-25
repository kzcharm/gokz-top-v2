import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import { type UserPublic, UsersService } from "@/client"
import { redirectToSteamLogin } from "@/lib/auth"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: UsersService.readUserMe,
    enabled: isLoggedIn(),
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  const loginWithSteam = () => {
    redirectToSteamLogin()
  }

  const logout = () => {
    localStorage.removeItem("access_token")
    queryClient.setQueryData(["currentUser"], null)
    queryClient.removeQueries({ queryKey: ["currentUser"] })
    queryClient.clear()
    navigate({ to: "/login" })
  }

  return {
    loginWithSteam,
    logout,
    user: isLoggedIn() ? user : null,
  }
}

export { isLoggedIn }
export default useAuth
