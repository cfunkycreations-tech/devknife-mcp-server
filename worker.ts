import { createDevKnifeServer } from './src/mcp-server.js';

// Cloudflare Worker Entrypoint
export default {
  async fetch(request: Request, env: any, ctx: any): Promise<Response> {
    const url = new URL(request.url);

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        }
      });
    }

    // Basic health check endpoint
    if (url.pathname === '/') {
      return new Response("DevKnife MCP Server is running. Connect via SSE at /mcp/sse", { 
        status: 200,
        headers: { 'Content-Type': 'text/plain' }
      });
    }

    // Note: The official @modelcontextprotocol/sdk relies heavily on Node.js 
    // http.ServerResponse for its SSEServerTransport. 
    // To run MCP natively on Cloudflare Workers (which use Web Streams), 
    // a custom Web Stream SSE Transport is required.
    // 
    // If you deploy this to Cloudflare and the MCP client fails to connect,
    // it is because the SDK expects a Node.js environment.
    // In that case, deploying this repo to Render.com (Web Service) is the 
    // recommended zero-code-change alternative.

    return new Response("Not Found", { status: 404 });
  }
}
