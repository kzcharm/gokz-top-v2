export const COMPARE_PLAYERS = ["player1", "player2"] as const
export type ComparePlayerSlot = (typeof COMPARE_PLAYERS)[number]
export const COMPARE_PLAYER_COLORS = { player1: "#6366f1", player2: "#e85d8a" }
export type CompareHighlightProps = {
  activePlayer: ComparePlayerSlot | null
  onHighlightPlayer: (player: ComparePlayerSlot | null) => void
}
