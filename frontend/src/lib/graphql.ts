import { GraphQLClient } from "graphql-request"

import { OpenAPI } from "@/client/core/OpenAPI"

const graphQLClient = new GraphQLClient(`${OpenAPI.BASE}/v1/graphql`)

export async function requestGraphQL<TData>(
  query: string,
  variables?: Record<string, unknown>,
) {
  return await graphQLClient.request<TData>(query, variables)
}
