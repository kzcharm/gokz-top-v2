import { useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { useMemo, useState } from "react"

import { type UserPublic, UsersService } from "@/client"
import { columns, type UserTableData } from "@/components/Admin/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingUsers from "@/components/Pending/PendingUsers"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/admin/users")({
  component: AdminUsers,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
    let user
    try {
      user = await UsersService.readUserMe()
    } catch {
      localStorage.removeItem("access_token")
      throw redirect({
        to: "/login",
      })
    }
    if (!user.is_superuser) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: getPageTitle(),
      },
    ],
  }),
})

function AdminUsers() {
  const { user: currentUser } = useAuth()
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(20)

  const { data, isLoading } = useQuery({
    queryFn: () =>
      UsersService.readUsers({
        skip: pageIndex * pageSize,
        limit: pageSize,
      }),
    queryKey: ["users", pageIndex, pageSize],
  })

  const tableData = useMemo<UserTableData[]>(
    () =>
      (data?.data ?? []).map((user: UserPublic) => ({
        ...user,
        isCurrentUser: currentUser?.steamid64 === user.steamid64,
      })),
    [data?.data, currentUser?.steamid64],
  )

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Users</h1>
        <p className="text-muted-foreground">Website users for this project</p>
      </div>
      {isLoading ? (
        <PendingUsers />
      ) : (
        <DataTable
          columns={columns}
          data={tableData}
          serverPagination={{
            pageIndex,
            pageSize,
            totalCount: data?.count ?? 0,
            onPageChange: setPageIndex,
            onPageSizeChange: (size) => {
              setPageSize(size)
              setPageIndex(0)
            },
          }}
        />
      )}
    </div>
  )
}
