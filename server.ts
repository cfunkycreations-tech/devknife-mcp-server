import express from 'express';
import cors from 'cors';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import { createServer as createViteServer } from 'vite';
import path from 'path';
import { createDevKnifeServer } from './src/mcp-server.js';

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(cors());
  app.use(express.json());

  // Store active transports by session ID
  const transports = new Map<string, SSEServerTransport>();

  // MCP SSE Endpoint
  app.get('/mcp/sse', async (req, res) => {
    const transport = new SSEServerTransport('/mcp/messages', res);
    const mcp = createDevKnifeServer();
    
    transports.set(transport.sessionId, transport);
    
    res.on('close', () => {
      transports.delete(transport.sessionId);
    });

    await mcp.connect(transport);
  });

  // MCP Messages Endpoint
  app.post('/mcp/messages', async (req, res) => {
    const sessionId = req.query.sessionId as string;
    
    if (!sessionId) {
      res.status(400).send('Missing sessionId');
      return;
    }

    const transport = transports.get(sessionId);
    if (!transport) {
      res.status(404).send('Session not found');
      return;
    }

    await transport.handlePostMessage(req, res);
  });

  // API for the Playground UI to test tools directly
  app.post('/api/test-tool', async (req, res) => {
    const { toolName, params } = req.body;
    if (!toolName) {
      res.json({ error: 'toolName is required' });
      return;
    }

    try {
      // Create a temporary MCP server just to call the tool directly
      const mcp = createDevKnifeServer();
      // @ts-ignore - Accessing internal tools map for playground testing
      const tool = mcp._tools[toolName];
      
      if (!tool) {
        res.json({ error: `Tool ${toolName} not found` });
        return;
      }

      const result = await tool.execute(params || {});
      res.json({ result: result.content[0].text, isError: result.isError });
    } catch (error: any) {
      res.json({ error: error.message });
    }
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`MCP SSE Endpoint: http://localhost:${PORT}/mcp/sse`);
  });
}

startServer();
