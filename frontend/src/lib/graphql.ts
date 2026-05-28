import { GraphQLClient } from "graphql-request"

import { OpenAPI } from "@/client/core/OpenAPI"

export async function requestGraphQL<TData>(
  query: string,
  variables?: Record<string, unknown>,
) {
  const graphQLClient = new GraphQLClient(`${OpenAPI.BASE}/v1/graphql`)
  return await graphQLClient.request<TData>(query, variables)
}
