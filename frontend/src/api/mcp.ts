import client from './client'
import type { McpServer, McpTool, McpResource } from './types'

export const mcpApi = {
  listServers: () => client.get<Record<string, McpServer>>('/mcp/servers'),
  listTools: (serverName: string) =>
    client.get<{ server: string; tools: McpTool[] }>(`/mcp/servers/${serverName}/tools`),
  callTool: (serverName: string, toolName: string, arguments_?: Record<string, unknown>) =>
    client.post('/mcp/tools/call', {
      server_name: serverName,
      tool_name: toolName,
      arguments: arguments_ ?? {},
    }),
  listResources: (serverName: string) =>
    client.get<{ server: string; resources: McpResource[] }>(`/mcp/servers/${serverName}/resources`),
  reload: () => client.post('/mcp/servers/reload'),
  reconnect: (serverName: string) => client.post(`/mcp/servers/${serverName}/reconnect`),
}