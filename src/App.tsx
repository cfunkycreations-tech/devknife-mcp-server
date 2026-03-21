import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Wrench, FileText, Code, CheckCircle, Copy, Play } from 'lucide-react';

const TOOLS = [
  { id: 'json_format', name: 'JSON Format/Validate', param: 'json', placeholder: '{"key": "value"}' },
  { id: 'base64_encode', name: 'Base64 Encode', param: 'text', placeholder: 'Hello World' },
  { id: 'base64_decode', name: 'Base64 Decode', param: 'base64', placeholder: 'SGVsbG8gV29ybGQ=' },
  { id: 'uuid_generate', name: 'UUID Generation', param: '', placeholder: '(No input required)' },
  { id: 'hash_compute', name: 'Hash Computation', param: 'text', placeholder: 'Hello World', extraParam: { name: 'algorithm', type: 'select', options: ['md5', 'sha1', 'sha256', 'sha512'] } },
  { id: 'regex_test', name: 'Regex Testing', param: 'text', placeholder: 'Text to test against', extraParam: { name: 'pattern', type: 'text', placeholder: 'Regex pattern (e.g., ^[a-z]+$)' } },
  { id: 'jwt_decode', name: 'JWT Decode', param: 'token', placeholder: 'eyJhbGciOiJIUzI1NiIsInR5cCI...' },
  { id: 'cron_parse', name: 'Cron Parsing', param: 'expression', placeholder: '*/5 * * * *' },
  { id: 'timestamp_convert', name: 'Timestamp Conversion', param: 'value', placeholder: '1672531200 or 2023-01-01T00:00:00Z' },
  { id: 'markdown_to_html', name: 'Markdown to HTML', param: 'markdown', placeholder: '# Hello\n\n**World**' },
  { id: 'url_encode', name: 'URL Encode', param: 'text', placeholder: 'https://example.com/?q=hello world' },
  { id: 'url_decode', name: 'URL Decode', param: 'text', placeholder: 'https%3A%2F%2Fexample.com%2F%3Fq%3Dhello%20world' },
  { id: 'html_encode', name: 'HTML Encode', param: 'text', placeholder: '<div>Hello & Welcome</div>' },
  { id: 'html_decode', name: 'HTML Decode', param: 'text', placeholder: '&#60;div&#62;Hello &#38; Welcome&#60;/div&#62;' },
  { id: 'lorem_ipsum', name: 'Lorem Ipsum', param: 'paragraphs', placeholder: '3', type: 'number' },
];

export default function App() {
  const [selectedTool, setSelectedTool] = useState(TOOLS[0]);
  const [inputValue, setInputValue] = useState('');
  const [extraValue, setExtraValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleTest = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    
    try {
      const params: any = {};
      if (selectedTool.param) {
        params[selectedTool.param] = selectedTool.type === 'number' ? Number(inputValue) : inputValue;
      }
      if (selectedTool.extraParam) {
        params[selectedTool.extraParam.name] = extraValue || (selectedTool.extraParam.options ? selectedTool.extraParam.options[0] : '');
      }

      const response = await fetch('/api/test-tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ toolName: selectedTool.id, params })
      });
      
      const data = await response.json();
      
      if (!response.ok || data.error) {
        throw new Error(data.error || 'Failed to execute tool.');
      }
      
      if (data.isError) {
        setError(data.result);
      } else {
        setResult(data.result);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const copyConfig = () => {
    navigator.clipboard.writeText(`${window.location.origin}/mcp/sse`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 font-sans selection:bg-indigo-100">
      <header className="border-b border-zinc-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-lg tracking-tight">
            <Wrench className="w-5 h-5 text-indigo-600" />
            <span>DevKnife MCP Server</span>
          </div>
          <div className="text-sm font-medium text-zinc-500 bg-zinc-100 px-3 py-1 rounded-full">
            Status: Online
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-16">
        <div className="grid md:grid-cols-2 gap-16 items-start">
          
          {/* Left Column: Info */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-8"
          >
            <div className="space-y-4">
              <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-zinc-900 leading-tight">
                The Developer Swiss Army Knife for AI.
              </h1>
              <p className="text-lg text-zinc-600 leading-relaxed">
                Bundle 15+ essential developer utilities into a single, blazing-fast MCP server. Give your AI agents the tools they need to validate, encode, decode, and parse data instantly.
              </p>
            </div>

            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
              <h3 className="font-semibold text-zinc-900 mb-4 flex items-center gap-2">
                <Code className="w-5 h-5 text-zinc-400" />
                Connection Details
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-1 block">SSE Endpoint</label>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 bg-zinc-100 text-zinc-800 px-3 py-2 rounded-lg text-sm border border-zinc-200 overflow-x-auto whitespace-nowrap">
                      {typeof window !== 'undefined' ? window.location.origin : 'https://your-app.run.app'}/mcp/sse
                    </code>
                    <button 
                      onClick={copyConfig}
                      className="p-2 text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 rounded-lg transition-colors"
                      title="Copy URL"
                    >
                      {copied ? <CheckCircle className="w-5 h-5 text-emerald-500" /> : <Copy className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
                
                <div className="pt-4 border-t border-zinc-100">
                  <h4 className="text-sm font-medium text-zinc-900 mb-2">Included Tools ({TOOLS.length})</h4>
                  <div className="flex flex-wrap gap-2">
                    {TOOLS.map(t => (
                      <span key={t.id} className="text-xs bg-zinc-100 text-zinc-600 px-2 py-1 rounded-md border border-zinc-200">
                        {t.id}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            
            <div className="prose prose-zinc text-sm text-zinc-600">
              <p>
                <strong>Zero-Cost Hosting:</strong> This server runs entirely on standard Node.js libraries (with minimal dependencies). It is designed to be deployed to Vercel Serverless, Cloudflare Workers, or Render for $0/month.
              </p>
            </div>
          </motion.div>

          {/* Right Column: Playground */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="bg-white border border-zinc-200 rounded-2xl shadow-xl shadow-zinc-200/50 overflow-hidden flex flex-col h-[600px]"
          >
            <div className="bg-zinc-900 px-4 py-3 flex items-center gap-3">
              <div className="flex gap-1.5">
                <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                <div className="w-3 h-3 rounded-full bg-amber-500/80"></div>
                <div className="w-3 h-3 rounded-full bg-emerald-500/80"></div>
              </div>
              <div className="text-xs font-mono text-zinc-400">Tool Playground</div>
            </div>
            
            <div className="p-6 border-b border-zinc-100 space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-1">Select Tool</label>
                <select 
                  className="w-full bg-zinc-50 border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                  value={selectedTool.id}
                  onChange={(e) => {
                    const tool = TOOLS.find(t => t.id === e.target.value)!;
                    setSelectedTool(tool);
                    setInputValue('');
                    setExtraValue('');
                    setResult(null);
                    setError(null);
                  }}
                >
                  {TOOLS.map(t => (
                    <option key={t.id} value={t.id}>{t.name} ({t.id})</option>
                  ))}
                </select>
              </div>

              <form onSubmit={handleTest} className="space-y-4">
                {selectedTool.extraParam && (
                  <div>
                    <label className="block text-sm font-medium text-zinc-700 mb-1">{selectedTool.extraParam.name}</label>
                    {selectedTool.extraParam.type === 'select' ? (
                      <select 
                        className="w-full bg-zinc-50 border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                        value={extraValue}
                        onChange={(e) => setExtraValue(e.target.value)}
                      >
                        <option value="" disabled>Select {selectedTool.extraParam.name}</option>
                        {selectedTool.extraParam.options?.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    ) : (
                      <input 
                        type="text"
                        className="w-full bg-zinc-50 border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                        placeholder={selectedTool.extraParam.placeholder}
                        value={extraValue}
                        onChange={(e) => setExtraValue(e.target.value)}
                        required
                      />
                    )}
                  </div>
                )}

                {selectedTool.param && (
                  <div>
                    <label className="block text-sm font-medium text-zinc-700 mb-1">{selectedTool.param}</label>
                    <textarea 
                      required
                      rows={3}
                      placeholder={selectedTool.placeholder}
                      className="w-full bg-zinc-50 border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all resize-none"
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                    />
                  </div>
                )}
                
                <button 
                  type="submit"
                  disabled={loading}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-70"
                >
                  {loading ? (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  Execute Tool
                </button>
              </form>
            </div>
            
            <div className="flex-1 bg-zinc-50 p-6 overflow-y-auto font-mono text-xs leading-relaxed">
              {error ? (
                <div className="text-red-600 bg-red-50 p-4 rounded-xl border border-red-100 whitespace-pre-wrap">
                  {error}
                </div>
              ) : result ? (
                <div className="text-zinc-800 whitespace-pre-wrap">
                  {result}
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-zinc-400 space-y-3">
                  <FileText className="w-8 h-8 opacity-50" />
                  <p>Output will appear here.</p>
                </div>
              )}
            </div>
          </motion.div>

        </div>
      </main>
    </div>
  );
}
