import express from "express";
import ViteExpress from "vite-express";
import { execFile } from "child_process";
import { promises as fs } from "fs";
import http from "http";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const app = express();
app.use(express.json());

const EXEC_OPTS = {
  cwd: repoRoot,
  maxBuffer: 1024 * 1024 * 10,
  timeout: 60_000,
  env: { ...process.env, PYTHONPATH: path.join(repoRoot, "src") },
};

// The single place a target directory is trusted. execFile never touches a
// shell, so there is no injection vector regardless of what the string
// contains — but a request for a path that doesn't exist should fail with a
// clear 400, not run contextlint against a nonsense argument.
async function resolveTarget(raw) {
  const candidate = typeof raw === "string" && raw.trim() ? raw.trim() : ".";
  const resolved = path.resolve(repoRoot, candidate);
  const stat = await fs.stat(resolved).catch(() => null);
  if (!stat || !stat.isDirectory()) {
    const err = new Error(`Not a directory: ${resolved}`);
    err.status = 400;
    throw err;
  }
  return resolved;
}

function auditArgs({ noGlobal, mcpProbe, target, format }) {
  const args = ["-m", "contextlint", "audit"];
  if (format) args.push("--format", format);
  if (noGlobal) args.push("--no-global");
  if (mcpProbe) args.push("--mcp-probe", "--yes");
  args.push(target);
  return args;
}

function run(args) {
  return new Promise((resolve) => {
    execFile("python", args, EXEC_OPTS, (error, stdout, stderr) => {
      resolve({ error, stdout, stderr });
    });
  });
}

function noStore(res) {
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
}

// API: JSON audit report
app.get("/api/report", async (req, res) => {
  noStore(res);
  try {
    const target = await resolveTarget(req.query.path);
    const args = auditArgs({
      noGlobal: req.query.no_global !== "false",
      mcpProbe: req.query.mcp_probe === "true",
      target,
      format: "json",
    });
    const { error, stdout, stderr } = await run(args);
    if (error) {
      console.error("contextlint audit failed:", stderr || error.message);
      return res.status(500).json({ error: "Failed to generate report", details: stderr || error.message });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      res.status(500).json({ error: "Invalid JSON from contextlint", output: stdout });
    }
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
});

// API: raw CLI terminal output, for the "view CLI output" modal
app.get("/api/terminal-report", async (req, res) => {
  noStore(res);
  try {
    const target = await resolveTarget(req.query.path);
    const args = auditArgs({
      noGlobal: req.query.no_global !== "false",
      mcpProbe: req.query.mcp_probe === "true",
      target,
    });
    const { error, stdout, stderr } = await run(args);
    res.json({ success: !error, output: stdout || stderr, error: error ? error.message : null });
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
});

// API: mutating actions. "fix" defaults to the CLI's own git-dirty-tree guard
// rather than silently bypassing it with --allow-dirty — the UI has to make
// the same safety decision a terminal user would, not skip it on their behalf.
app.post("/api/run-command", async (req, res) => {
  try {
    const { action, path: rawPath, allow_dirty: allowDirty } = req.body || {};
    const target = await resolveTarget(rawPath);

    let args;
    if (action === "audit") {
      args = ["-m", "contextlint", "audit", "--no-global", target];
    } else if (action === "fix") {
      args = ["-m", "contextlint", "fix", "--apply", "--yes"];
      if (allowDirty) args.push("--allow-dirty");
      args.push(target);
    } else {
      return res.status(400).json({ error: "Invalid action" });
    }

    const { error, stdout, stderr } = await run(args);
    const output = stdout || stderr || "";
    const dirty = action === "fix" && !allowDirty && /uncommitted changes|not a git repository/i.test(output);

    res.json({ success: !error, output, error: error ? error.message : null, dirty });
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
});

// Bind to loopback only. This process shells out to a Python CLI on request;
// exposing that on the LAN (Express's default when no host is given) turns
// every device on the network into something that can trigger it.
// ViteExpress.listen() doesn't take a host argument, so this replicates its
// internals — a plain http server bound to 127.0.0.1, then ViteExpress.bind()
// attaches the dev middleware exactly the way .listen() would have.
const server = http.createServer(app);
server.listen(3535, "127.0.0.1", () => {
  ViteExpress.bind(app, server, () =>
    console.log("Server is listening on http://127.0.0.1:3535 (loopback only)")
  );
});
