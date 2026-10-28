export const COMPARE_PLAYERS = ["player1", "player2"] as const
export type ComparePlayerSlot = (typeof COMPARE_PLAYERS)[number]
export const COMPARE_PLAYER_COLORS = { player1: "#0f9d8b", player2: "#e8792f" }
export type CompareHighlightProps = {
  activePlayer: ComparePlayerSlot | null
  onHighlightPlayer: (player: ComparePlayerSlot | null) => void
}
