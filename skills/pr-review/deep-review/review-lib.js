// Shared by deep-review-pr.js and quick-review-pr.js. prefetch.py inlines this
// file right after INPUTS in each generated run.js (workflow scripts can't
// import); it is never run on its own.

if (!INPUTS) {
  throw new Error('review-lib: run the run.js that prefetch.py generates, not a template')
}

const SEVERITY_RANK = { high: 0, medium: 1, low: 2 }

// The four bug-finder focuses, in report order.
const BUG_FOCUSES = {
  completeness: 'Completeness: does the PR do all of what its description and linked ticket promise; every path the change should reach — callers and contracts not updated, branches and error paths missed, resource or state leaks.',
  mechanism: 'Mechanism and compatibility: does the new logic do what the description says — wrong conditions, edge cases, races, regressions against the prior behavior — and does it break clients, SDKs, older deployed versions, or persisted/serialized data and wire formats.',
  'removed-behavior': 'Removed behavior: everything the PR deletes, bypasses, or stops doing — code, branches, validation, side effects, defaults — and who still relies on it.',
  operational: 'Operational: unbounded loops and waits with no timeout, retry storms, work lost or inconsistent on cancellation or partial failure, silent failures, status not propagated, missing authorization, config/secret/migration dependencies and deploy order, hot-path performance regressions.',
}

// Bugs face skeptics and die on a majority of refutes; simplifications face
// defenders of the current code and die if any defender wins.
const PANELS = {
  bug: {
    angles: {
      trace: 'Trace it: follow the code at headSha from a real entry point to the flagged line. Does the triggering input actually reach it, and does the claimed bad outcome follow?',
      intent: 'Check intent: do the PR description, commits, history, existing comments, or docs show this behavior is deliberate?',
      guard: 'Look for a guard: is it already prevented elsewhere — a caller that validates, a type that rules it out, framework behavior, a retry or fallback?',
    },
    stance: 'Try to REFUTE this finding. Set refuted=true only with concrete evidence from your angle. If it stands, rate its severity yourself (downgrade non-blockers) and give simpler_fix if the proposed fix overcomplicates the code.',
    kills: (refutes, cast) => refutes * 2 > cast,
  },
  simplification: {
    angles: {
      behavior: 'Name behavior the replacement would lose: a caller, runtime path, or test that depends on the current code, or a replacement that does not actually exist or does a different job at headSha.',
      requirement: 'Name a requirement for the current code: the PR description, a linked ticket or planned work, an AGENTS.md/CLAUDE.md rule, or a repo convention that prescribes this shape.',
    },
    stance: 'Argue for KEEPING the code this finding wants removed, replaced, or restructured. Set refuted=true only with concrete evidence (file:line, a quoted rule, a ticket); if the replacement loses nothing, set refuted=false.',
    kills: refutes => refutes > 0,
  },
}

// Identical leading text across every agent, so it's cache-friendly.
const RULES = `You are one subagent inside the ${INPUTS.workflow} workflow for PR ${INPUTS.pr} at ${INPUTS.headSha}.
${INPUTS.mine
  ? 'This is William\'s own PR, about to go to human review: catch what a reviewer would.'
  : `This is a teammate's PR (author ${INPUTS.author}): assume competence; simplification and structure findings must clearly pay for the churn of restructuring their nearly-done work.`}
PR description (the spec):
${INPUTS.description}

The repo is ${INPUTS.repoDir}: cd there before any git command or search. Read PR code at that commit only
(\`git show ${INPUTS.headSha}:<path>\`, \`git grep <pat> ${INPUTS.headSha}\`); the working tree may be another branch. Patches not inlined below are in ${INPUTS.ctxDir}/files/<path>.patch.
Strictly read-only: no edits, checkouts, test runs, pushes, or GitHub posts (gh reads are fine); never call Workflow or spawn agents.
Return only the structured output or report.`

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['file', 'start', 'end', 'why', 'fix'],
        properties: {
          file: { type: 'string', description: 'repo-relative path, no a/ b/ prefix' },
          start: { type: 'integer', description: 'file line number at headSha (not a patch offset)' },
          end: { type: 'integer' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'], description: 'bug/correctness only' },
          why: { type: 'string', description: 'one line, used as the summary' },
          fix: { type: 'string', description: 'bugs: a minimal plain-text diff, naming any out-of-diff file it must touch' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['refuted', 'duplicate_of_comment', 'reason'],
  properties: {
    refuted: { type: 'boolean' },
    duplicate_of_comment: { type: 'boolean' },
    reason: { type: 'string', description: 'evidence with file:line at headSha' },
    severity: { type: 'string', enum: ['high', 'medium', 'low'], description: 'bugs only, if it stands: your own rating — downgrade non-blockers' },
    simpler_fix: { type: 'string', description: 'bugs only, if it stands and the proposed fix overcomplicates the code: a simpler diff' },
  },
}

// The PR's diff. A re-review swaps in the diff since the last review.
const PR_DIFF = { files: INPUTS.files, patches: INPUTS.patches, dir: INPUTS.ctxDir }

// [null] means "the whole diff", so a sharded axis is never silently skipped.
function shardFiles(files, maxLines, maxShards) {
  const total = files.reduce((n, f) => n + f.changes, 0)
  if (!files.length || total <= maxLines) return [null]
  const bins = Array.from({ length: Math.min(maxShards, Math.ceil(total / maxLines)) }, () => ({ lines: 0, paths: [] }))
  for (const f of [...files].sort((a, b) => b.changes - a.changes)) {
    const bin = bins.reduce((min, b) => (b.lines < min.lines ? b : min))
    bin.lines += f.changes
    bin.paths.push(f.path)
  }
  return bins.filter(b => b.paths.length).map(b => b.paths)
}

function scopeText(paths, diff = PR_DIFF) {
  const all = paths ?? diff.files.map(f => f.path)
  if (!paths && !diff.patches) return `Review the whole diff: ${diff.dir}/diff.patch`
  const inline = all.filter(p => diff.patches?.[p] != null)
  const toRead = all.filter(p => diff.patches?.[p] == null)
  return [
    `Review only these files: ${all.join(', ')}`,
    ...inline.map(p => `--- patch: ${p}\n${diff.patches[p]}`),
    toRead.length ? `Read their patches: ${toRead.map(p => `${diff.dir}/files/${p}.patch`).join(', ')}` : '',
  ].join('\n')
}

const overlaps = (a, b) => a.file === b.file && a.family === b.family && a.start <= b.end && b.start <= a.end
const summary = ({ file, start, end, axis, severity, why, fix, simpler_fix, repro }) => ({ file, start, end, axis, severity, why, fix, simpler_fix, repro })

// Within a file + family, overlapping findings collapse to the most severe
// (ties: the earlier finder). Output is in report order.
function dedupe(confirmed) {
  const ranked = [...confirmed].sort((a, b) =>
    (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) || a.order - b.order)
  const kept = []
  for (const f of ranked) {
    if (!kept.some(k => overlaps(k, f))) kept.push(f)
  }
  return kept
    .sort((a, b) => a.order - b.order || (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) ||
      a.file.localeCompare(b.file) || a.start - b.start)
    .map(summary)
}

// Upholding skeptics re-rate the bug (median, ties toward less severe) and may
// offer a simpler fix than the finder's.
function triage(f, cast) {
  const upheld = cast.filter(v => !v.refuted)
  const ratings = upheld.map(v => v.severity).filter(Boolean).sort((a, b) => SEVERITY_RANK[a] - SEVERITY_RANK[b])
  const severity = ratings.length ? ratings[Math.floor(ratings.length / 2)] : f.severity
  const simpler_fix = upheld.map(v => v.simpler_fix).find(Boolean)
  return { ...f, severity, ...(simpler_fix ? { simpler_fix } : {}) }
}

function verifyPrompt(f, raw, extra, depth) {
  const patch = INPUTS.patches?.[f.file]
  return `${RULES}\n\n${INPUTS.rubric.verify}${extra}
${patch ? `\n--- patch: ${f.file}\n${patch}` : ''}
Existing comments on ${f.file}: ${JSON.stringify(INPUTS.comments[f.file] ?? [])}
PR-level comments: ${JSON.stringify(INPUTS.comments[''] ?? [])}

${depth}
The ${f.axis} finding: ${JSON.stringify(raw)}`
}
