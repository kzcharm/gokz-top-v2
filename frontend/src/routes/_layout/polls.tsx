import { createFileRoute } from "@tanstack/react-router"
import { PollsPage } from "@/components/Polls/PollsPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/polls")({
  component: PollsPage,
  head: () => ({ meta: [{ title: getPageTitle("Polls") }] }),
})
