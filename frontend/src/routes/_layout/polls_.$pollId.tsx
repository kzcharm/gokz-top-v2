import { createFileRoute } from "@tanstack/react-router"
import { PollsPage } from "@/components/Polls/PollsPage"
import { getPageTitle } from "@/lib/site"

export const Route = createFileRoute("/_layout/polls_/$pollId")({
  component: PollDetailRoute,
  head: () => ({ meta: [{ title: getPageTitle("Poll") }] }),
})

function PollDetailRoute() {
  const { pollId } = Route.useParams()

  return <PollsPage pollId={pollId} />
}
