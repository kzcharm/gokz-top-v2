import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useState,
} from "react"

type UsePersistedPageSizeOptions = {
  storageKey: string
  defaultPageSize?: number
  pageSizeOptions?: readonly number[]
}

const DEFAULT_PAGE_SIZE = 20
const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const

function readStoredPageSize(
  storageKey: string,
  defaultPageSize: number,
  pageSizeOptions: readonly number[],
) {
  if (typeof window === "undefined") {
    return defaultPageSize
  }

  const storedPageSize = Number(window.localStorage.getItem(storageKey))
  return pageSizeOptions.includes(storedPageSize)
    ? storedPageSize
    : defaultPageSize
}

export function usePersistedPageSize({
  storageKey,
  defaultPageSize = DEFAULT_PAGE_SIZE,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
}: UsePersistedPageSizeOptions): [number, Dispatch<SetStateAction<number>>] {
  const [pageSize, setPageSizeState] = useState(() =>
    readStoredPageSize(storageKey, defaultPageSize, pageSizeOptions),
  )

  const setPageSize = useCallback<Dispatch<SetStateAction<number>>>(
    (nextPageSize) => {
      setPageSizeState((currentPageSize) => {
        const resolvedPageSize =
          typeof nextPageSize === "function"
            ? nextPageSize(currentPageSize)
            : nextPageSize

        if (typeof window !== "undefined") {
          window.localStorage.setItem(storageKey, `${resolvedPageSize}`)
        }

        return resolvedPageSize
      })
    },
    [storageKey],
  )

  return [pageSize, setPageSize]
}
