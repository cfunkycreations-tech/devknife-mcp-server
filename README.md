# 🛠️ DevKnife MCP Server

**The Developer Swiss Army Knife for AI Agents.**

DevKnife is a blazing-fast, zero-cost Model Context Protocol (MCP) server that bundles 15+ essential developer utilities. It gives your AI agents (like Claude Desktop, LangChain, or custom LLM apps) the ability to instantly validate, encode, decode, parse, and manipulate data without hallucinating.

## 🧰 Included Tools

1. **`json_format`**: Format and validate JSON strings.
2. **`base64_encode`**: Encode text to Base64.
3. **`base64_decode`**: Decode Base64 strings.
4. **`uuid_generate`**: Generate random UUID v4s.
5. **`hash_compute`**: Compute MD5, SHA-1, SHA-256, or SHA-512 hashes.
6. **`regex_test`**: Test regular expressions against strings and extract capture groups.
7. **`jwt_decode`**: Decode JWT headers and payloads (no secret required).
8. **`cron_parse`**: Parse cron expressions and get the next 5 occurrences.
9. **`timestamp_convert`**: Convert between epoch timestamps and ISO 8601 strings.
10. **`markdown_to_html`**: Convert Markdown to HTML.
11. **`url_encode`**: URL encode a string.
12. **`url_decode`**: URL decode a string.
13. **`html_encode`**: Encode HTML entities.
14. **`html_decode`**: Decode HTML entities.
15. **`lorem_ipsum`**: Generate dummy text for testing.

## 🚀 Getting Started Locally

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/devknife-mcp.git
   cd devknife-mcp
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server (includes a UI playground):
   ```bash
   npm run dev
   ```
4. The MCP SSE endpoint will be available at: `http://localhost:3000/mcp/sse`

## ☁️ Deployment Guide

This project is designed to be hosted for **$0/month**. 

### Option A: Render.com (Recommended)
Because the official `@modelcontextprotocol/sdk` relies on Node.js streams for Server-Sent Events (SSE), deploying to a native Node environment is highly recommended.
1. Go to [Render.com](https://render.com) and create a **New Web Service**.
2. Connect this GitHub repository.
3. Build Command: `npm run build`
4. Start Command: `npm start`
5. Render will automatically provision a free URL (e.g., `https://devknife-mcp.onrender.com/mcp/sse`).

### Option B: Cloudflare Workers
This repository includes a `worker.ts` and `wrangler.toml` for Edge deployment.
1. Go to the Cloudflare Dashboard -> Workers & Pages.
2. Click **Create Application** -> **Pages** -> **Connect to Git**.
3. Select this repository.
4. Framework preset: `None`
5. Build command: `npm install`
6. *Note: Running the official MCP SDK on Cloudflare Workers currently requires bridging Web Streams to Node streams. If your MCP client fails to connect via Cloudflare, use Render.com instead.*

## 🔌 Connecting to an MCP Client

DevKnife exposes an **SSE (Server-Sent Events)** transport. 

If you are using an MCP client that supports SSE (like many web-based AI agents), simply provide your deployed URL:
`https://your-deployed-app.com/mcp/sse`

*(Note: Claude Desktop currently natively supports `stdio` transports. To use an SSE server with Claude Desktop, you may need a lightweight `stdio-to-sse` bridge script).*
