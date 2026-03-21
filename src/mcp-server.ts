import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import crypto from 'node:crypto';
import { marked } from 'marked';
import cronParser from 'cron-parser';

export function createDevKnifeServer() {
  const mcp = new McpServer({
    name: "DevKnife",
    version: "1.0.0"
  });

  // 1. JSON Format/Validate
  mcp.tool("json_format", "Format and validate JSON string", {
    json: z.string().describe("The JSON string to format")
  }, async ({ json }) => {
    try {
      const parsed = JSON.parse(json);
      return { content: [{ type: "text", text: JSON.stringify(parsed, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `Invalid JSON: ${e.message}` }], isError: true };
    }
  });

  // 2. Base64 Encode
  mcp.tool("base64_encode", "Encode a string to Base64", {
    text: z.string().describe("The text to encode")
  }, async ({ text }) => {
    return { content: [{ type: "text", text: Buffer.from(text).toString('base64') }] };
  });

  // 3. Base64 Decode
  mcp.tool("base64_decode", "Decode a Base64 string", {
    base64: z.string().describe("The base64 string to decode")
  }, async ({ base64 }) => {
    try {
      return { content: [{ type: "text", text: Buffer.from(base64, 'base64').toString('utf-8') }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `Invalid Base64: ${e.message}` }], isError: true };
    }
  });

  // 4. UUID Generation
  mcp.tool("uuid_generate", "Generate a random UUID v4", {}, async () => {
    return { content: [{ type: "text", text: crypto.randomUUID() }] };
  });

  // 5. Hash Computation
  mcp.tool("hash_compute", "Compute MD5, SHA-1, SHA-256, or SHA-512 hash", {
    text: z.string().describe("The text to hash"),
    algorithm: z.enum(['md5', 'sha1', 'sha256', 'sha512']).describe("The hash algorithm")
  }, async ({ text, algorithm }) => {
    const hash = crypto.createHash(algorithm).update(text).digest('hex');
    return { content: [{ type: "text", text: hash }] };
  });

  // 6. Regex Testing
  mcp.tool("regex_test", "Test a regular expression against a string", {
    pattern: z.string().describe("The regex pattern (without slashes)"),
    flags: z.string().optional().describe("Regex flags (e.g., 'g', 'i')"),
    text: z.string().describe("The text to test against")
  }, async ({ pattern, flags, text }) => {
    try {
      const regex = new RegExp(pattern, flags);
      const matches = [...text.matchAll(regex)];
      const result = {
        isMatch: regex.test(text),
        matches: matches.map(m => ({ match: m[0], index: m.index, groups: m.groups }))
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `Regex Error: ${e.message}` }], isError: true };
    }
  });

  // 7. JWT Decode
  mcp.tool("jwt_decode", "Decode a JWT (Header and Payload) without verifying signature", {
    token: z.string().describe("The JWT string")
  }, async ({ token }) => {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) throw new Error("Invalid JWT format");
      const header = JSON.parse(Buffer.from(parts[0], 'base64').toString('utf-8'));
      const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString('utf-8'));
      return { content: [{ type: "text", text: JSON.stringify({ header, payload }, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `JWT Decode Error: ${e.message}` }], isError: true };
    }
  });

  // 8. Cron Parsing
  mcp.tool("cron_parse", "Parse a cron expression and get next 5 occurrences", {
    expression: z.string().describe("The cron expression (e.g., '*/5 * * * *')")
  }, async ({ expression }) => {
    try {
      const interval = cronParser.parseExpression(expression);
      const nextOccurrences = [];
      for (let i = 0; i < 5; i++) {
        nextOccurrences.push(interval.next().toString());
      }
      return { content: [{ type: "text", text: JSON.stringify({ nextOccurrences }, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `Cron Parse Error: ${e.message}` }], isError: true };
    }
  });

  // 9. Timestamp Conversion
  mcp.tool("timestamp_convert", "Convert between epoch timestamp and ISO 8601 string", {
    value: z.string().describe("Epoch timestamp (seconds/ms) or ISO 8601 string")
  }, async ({ value }) => {
    try {
      let date;
      const numValue = Number(value);
      if (!isNaN(numValue)) {
        date = new Date(numValue < 10000000000 ? numValue * 1000 : numValue);
      } else {
        date = new Date(value);
      }
      if (isNaN(date.getTime())) throw new Error("Invalid date/timestamp");
      
      const result = {
        iso: date.toISOString(),
        utc: date.toUTCString(),
        epochSeconds: Math.floor(date.getTime() / 1000),
        epochMilliseconds: date.getTime()
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `Timestamp Error: ${e.message}` }], isError: true };
    }
  });

  // 10. Markdown to HTML
  mcp.tool("markdown_to_html", "Convert Markdown to HTML", {
    markdown: z.string().describe("The markdown string")
  }, async ({ markdown }) => {
    try {
      const html = await marked.parse(markdown);
      return { content: [{ type: "text", text: html }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `Markdown Error: ${e.message}` }], isError: true };
    }
  });

  // 11. URL Encode
  mcp.tool("url_encode", "URL encode a string", {
    text: z.string().describe("The text to encode")
  }, async ({ text }) => {
    return { content: [{ type: "text", text: encodeURIComponent(text) }] };
  });

  // 12. URL Decode
  mcp.tool("url_decode", "URL decode a string", {
    text: z.string().describe("The text to decode")
  }, async ({ text }) => {
    try {
      return { content: [{ type: "text", text: decodeURIComponent(text) }] };
    } catch (e: any) {
      return { content: [{ type: "text", text: `URL Decode Error: ${e.message}` }], isError: true };
    }
  });

  // 13. HTML Entity Encode
  mcp.tool("html_encode", "Encode HTML entities", {
    text: z.string().describe("The text to encode")
  }, async ({ text }) => {
    const encoded = text.replace(/[\u00A0-\u9999<>\&]/g, (i) => '&#' + i.charCodeAt(0) + ';');
    return { content: [{ type: "text", text: encoded }] };
  });

  // 14. HTML Entity Decode
  mcp.tool("html_decode", "Decode HTML entities", {
    text: z.string().describe("The text to decode")
  }, async ({ text }) => {
    const decoded = text.replace(/&#([0-9]{1,3});/gi, (match, numStr) => String.fromCharCode(parseInt(numStr, 10)));
    return { content: [{ type: "text", text: decoded }] };
  });

  // 15. Lorem Ipsum Generator
  mcp.tool("lorem_ipsum", "Generate dummy text", {
    paragraphs: z.number().min(1).max(10).default(1).describe("Number of paragraphs")
  }, async ({ paragraphs }) => {
    const text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.";
    const result = Array(paragraphs).fill(text).join('\n\n');
    return { content: [{ type: "text", text: result }] };
  });

  return mcp;
}
