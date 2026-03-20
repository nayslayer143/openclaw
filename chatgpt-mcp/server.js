#!/usr/bin/env node
/**
 * OpenClaw ChatGPT MCP Server
 *
 * Gives Claude Code two tools:
 *   1. deep_research  — sends a research query to GPT-4o for thorough analysis
 *   2. terminal_insights — sends terminal output to GPT-4o-mini for fast pattern recognition
 *
 * Runs as a stdio MCP server. Claude Code spawns it automatically.
 *
 * Budget controls:
 *   - Per-call token caps (configurable via env)
 *   - Model routing: expensive model for research, cheap model for terminal
 *   - Session token counter logged to stderr
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import OpenAI from "openai";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
  console.error("FATAL: OPENAI_API_KEY not set. Add it to ~/openclaw/.env or export it.");
  process.exit(1);
}

const RESEARCH_MODEL    = process.env.CHATGPT_RESEARCH_MODEL    || "gpt-4o";
const TERMINAL_MODEL    = process.env.CHATGPT_TERMINAL_MODEL    || "gpt-4o-mini";
const RESEARCH_MAX_TOKENS  = parseInt(process.env.CHATGPT_RESEARCH_MAX_TOKENS  || "4096", 10);
const TERMINAL_MAX_TOKENS  = parseInt(process.env.CHATGPT_TERMINAL_MAX_TOKENS  || "1024", 10);

const openai = new OpenAI({ apiKey: OPENAI_API_KEY });

// Simple session-level token counter (logged to stderr so Claude Code doesn't see it)
let sessionTokens = { research: 0, terminal: 0 };

function logUsage(tool, usage) {
  const total = (usage?.total_tokens || 0);
  sessionTokens[tool] += total;
  console.error(
    `[chatgpt-mcp] ${tool} call: ${total} tokens | session total: research=${sessionTokens.research} terminal=${sessionTokens.terminal}`
  );
}

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------
const server = new McpServer({
  name: "openclaw-chatgpt",
  version: "1.0.0",
});

// Tool 1: Deep Research
server.tool(
  "deep_research",
  "Send a research query to ChatGPT (GPT-4o) for thorough, multi-source analysis. " +
  "Use for market research, competitive analysis, technical deep-dives, or any question " +
  "that benefits from GPT-4o's broad training data. Returns a structured research brief.",
  {
    query: z.string().describe("The research question or topic to investigate"),
    context: z.string().optional().describe(
      "Optional context about why this research is needed (helps focus the response)"
    ),
    format: z.enum(["brief", "detailed", "bullet_points"]).default("brief").describe(
      "Output format: 'brief' (2-3 paragraphs), 'detailed' (full analysis), 'bullet_points' (scannable list)"
    ),
  },
  async ({ query, context, format }) => {
    const systemPrompt = `You are a research analyst for OpenClaw, a web business operating system.
Provide accurate, well-sourced analysis. Be direct and actionable.
${format === "brief" ? "Keep response to 2-3 focused paragraphs." : ""}
${format === "bullet_points" ? "Use concise bullet points. Lead with the insight, not the source." : ""}
${format === "detailed" ? "Provide comprehensive analysis with sections. Include competing perspectives." : ""}
Always note confidence level (high/medium/low) and flag anything that needs verification.`;

    const userMessage = context
      ? `Research query: ${query}\n\nContext: ${context}`
      : `Research query: ${query}`;

    try {
      const response = await openai.chat.completions.create({
        model: RESEARCH_MODEL,
        max_tokens: RESEARCH_MAX_TOKENS,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userMessage },
        ],
      });

      logUsage("research", response.usage);

      const result = response.choices[0]?.message?.content || "No response generated.";
      return {
        content: [
          {
            type: "text",
            text: `## Research: ${query}\n\n**Model:** ${RESEARCH_MODEL} | **Tokens:** ${response.usage?.total_tokens || "?"}\n\n${result}`,
          },
        ],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Research failed: ${err.message}` }],
        isError: true,
      };
    }
  }
);

// Tool 2: Terminal Insights
server.tool(
  "terminal_insights",
  "Send terminal/CLI output to ChatGPT (GPT-4o-mini) for fast analysis. " +
  "Use for: error diagnosis, log pattern detection, build output analysis, " +
  "test result summarization, or any terminal output that needs quick interpretation. " +
  "Cheap and fast — designed for frequent use.",
  {
    output: z.string().describe("The terminal output to analyze (paste stdout/stderr)"),
    question: z.string().optional().describe(
      "Specific question about the output (e.g., 'why did the build fail?', 'any warnings I should care about?')"
    ),
    output_type: z.enum(["error", "build", "test", "logs", "general"]).default("general").describe(
      "Type of terminal output — helps focus the analysis"
    ),
  },
  async ({ output, question, output_type }) => {
    const typeHints = {
      error: "Focus on: root cause, fix suggestions, and whether this is a known issue pattern.",
      build: "Focus on: success/failure status, warnings worth addressing, performance notes.",
      test: "Focus on: which tests failed and why, flaky test patterns, coverage gaps.",
      logs: "Focus on: anomalies, error spikes, patterns, and anything that needs attention.",
      general: "Provide a concise summary of what this output tells us and any action items.",
    };

    const systemPrompt = `You are a terminal output analyst for a developer running OpenClaw (a web business OS).
Be concise and actionable. Lead with the most important finding.
${typeHints[output_type]}
If the output is clean/normal, just say so briefly — don't over-analyze.`;

    const userMessage = question
      ? `Terminal output (${output_type}):\n\`\`\`\n${output}\n\`\`\`\n\nQuestion: ${question}`
      : `Terminal output (${output_type}):\n\`\`\`\n${output}\n\`\`\``;

    // Truncate very long outputs to stay within budget
    const truncated = output.length > 12000
      ? output.slice(0, 6000) + "\n\n... [truncated middle] ...\n\n" + output.slice(-6000)
      : output;

    const finalMessage = question
      ? `Terminal output (${output_type}):\n\`\`\`\n${truncated}\n\`\`\`\n\nQuestion: ${question}`
      : `Terminal output (${output_type}):\n\`\`\`\n${truncated}\n\`\`\``;

    try {
      const response = await openai.chat.completions.create({
        model: TERMINAL_MODEL,
        max_tokens: TERMINAL_MAX_TOKENS,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: finalMessage },
        ],
      });

      logUsage("terminal", response.usage);

      const result = response.choices[0]?.message?.content || "No analysis generated.";
      return {
        content: [
          {
            type: "text",
            text: `**Terminal Analysis** (${TERMINAL_MODEL}, ${response.usage?.total_tokens || "?"} tokens)\n\n${result}`,
          },
        ],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Terminal analysis failed: ${err.message}` }],
        isError: true,
      };
    }
  }
);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[chatgpt-mcp] Server started. Tools: deep_research, terminal_insights");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
