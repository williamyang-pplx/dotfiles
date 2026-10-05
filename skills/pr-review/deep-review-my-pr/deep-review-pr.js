export const meta = {
  name: 'deep-review-pr',
  description: 'Deep-review a PR with no barriers: lenses → per-axis finders → per-finding verify, all streaming',
  phases: [
    { title: 'Gather', detail: 'context lenses, all started at once' },
    { title: 'Review', detail: 'one finder per axis, sharded by file; each starts when its lenses finish' },
    { title: 'Verify', detail: 'one skeptic per finding, started as soon as its finder returns' },
  ],
}

// prefetch.py replaces this line with the PR's inputs in a per-run copy
// (<git-common-dir>/deep-review/<pr>-<sha>/run.js). Run that copy, never this file.
const INPUTS = null  // @prefetch

const TUNING = {
  lens: { agentType: 'Explore', model: 'sonnet', effort: 'low' },
  find: { effort: 'medium' },
  verify: { agentType: 'Explore', model: 'sonnet', effort: 'low' },
  // Low effort plus default-refuted would kill real bugs, so high/medium bugs get more.
  verifyBug: { agentType: 'Explore', model: 'sonnet', effort: 'medium' },
}
// Changed lines per shard for sharded axes. One huge file stays one shard.
const SHARD_LINES = 400
const MAX_SHARDS = 6

// Axis labels come from here, never from the model. `lenses` are the only
// reports a finder waits on; `verifyLenses` are awaited by its verifiers
// instead, off the finder's critical path. `family` groups axes whose findings
// at overlapping lines are the same finding. Finders are listed in each
// skill's "## Report" order.
const MODES = {
  mine: {
    lenses: ['Linear lineage', 'Related code', 'History', 'Duplication sweep', 'Reuse candidates', 'Docs and conventions', 'Test landscape'],
    finders: [
      { axis: 2, label: 'bug', family: 'bug', lenses: [], verifyLenses: ['History'], shard: true },
      { axis: 3, label: 'testing', family: 'testing', lenses: ['Test landscape'] },
      { axis: 7, label: 'structure/design', family: 'shape', lenses: ['Related code'] },
      { axis: 8, label: 'layout', family: 'shape', lenses: ['Docs and conventions'] },
      { axis: 4, label: 'duplication', family: 'shape', lenses: ['Duplication sweep', 'Related code'] },
      { axis: 5, label: 'reuse', family: 'shape', lenses: ['Reuse candidates', 'Linear lineage'] },
      { axis: 1, label: 'slop', family: 'surface', lenses: ['Docs and conventions'], shard: true },
      { axis: 6, label: 'style', family: 'surface', lenses: ['Docs and conventions'] },
    ],
  },
  other: {
    lenses: ['Related code', 'Duplication sweep', 'Reuse candidates', 'Docs and conventions', 'Test landscape'],
    finders: [
      { axis: 1, label: 'correctness', family: 'bug', lenses: [], shard: true },
      { axis: 2, label: 'testing', family: 'testing', lenses: ['Test landscape'] },
      { axis: 6, label: 'design', family: 'shape', lenses: ['Related code'] },
      { axis: 3, label: 'duplication', family: 'shape', lenses: ['Duplication sweep', 'Related code'] },
      { axis: 4, label: 'reuse', family: 'shape', lenses: ['Reuse candidates'] },
      { axis: 5, label: 'style', family: 'surface', lenses: ['Docs and conventions'] },
    ],
  },
}

if (!INPUTS || !MODES[INPUTS.mode]) {
  throw new Error('deep-review-pr: run the run.js that prefetch.py generates, not this template')
}

const LENS_EXTRA = {
  // Folds the roadmap search into the one Linear trip.
  'Linear lineage': () => INPUTS.rubric.helper,
  'Docs and conventions': () => 'Explore agents get no CLAUDE.md: read every AGENTS.md/CLAUDE.md on the touched paths yourself.',
}

// Identical leading text across every agent, so it's cache-friendly.
const RULES = `You are one subagent inside the deep-review-pr workflow for PR ${INPUTS.pr} at ${INPUTS.headSha}.
PR description (the spec):
${INPUTS.description}

The repo is ${INPUTS.repoDir}: cd there before any git command or search. Read PR code at that commit only
(\`git show ${INPUTS.headSha}:<path>\`, \`git grep <pat> ${INPUTS.headSha}\`); the working tree may be another branch. Patches not inlined below are in ${INPUTS.ctxDir}/files/<path>.patch.
Strictly read-only: no edits, checkouts, test runs, pushes, or GitHub posts; never call Workflow or spawn agents.
Be fast: stay inside your scope, stop once your answer is solid, aim for under 10 tool calls, return only the structured output.`

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
          fix: { type: 'string' },
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
  },
}

const SEVERITY_RANK = { high: 0, medium: 1, low: 2 }

// [null] means "the whole diff", so a sharded axis is never silently skipped.
function shardFiles(files) {
  const total = files.reduce((n, f) => n + f.changes, 0)
  if (!files.length || total <= SHARD_LINES) return [null]
  const bins = Array.from({ length: Math.min(MAX_SHARDS, Math.ceil(total / SHARD_LINES)) }, () => ({ lines: 0, paths: [] }))
  for (const f of [...files].sort((a, b) => b.changes - a.changes)) {
    const bin = bins.reduce((min, b) => (b.lines < min.lines ? b : min))
    bin.lines += f.changes
    bin.paths.push(f.path)
  }
  return bins.filter(b => b.paths.length).map(b => b.paths)
}

function scopeText(paths) {
  const all = paths ?? INPUTS.files.map(f => f.path)
  if (!paths && !INPUTS.patches) return `Review the whole diff: ${INPUTS.ctxDir}/diff.patch`
  const inline = all.filter(p => INPUTS.patches?.[p] != null)
  const toRead = all.filter(p => INPUTS.patches?.[p] == null)
  return [
    `Review only these files: ${all.join(', ')}`,
    ...inline.map(p => `--- patch: ${p}\n${INPUTS.patches[p]}`),
    toRead.length ? `Read their patches: ${toRead.map(p => `${INPUTS.ctxDir}/files/${p}.patch`).join(', ')}` : '',
  ].join('\n')
}

// Within a file + family, overlapping findings collapse to the most severe
// (ties: the earlier finder). Output is in report order.
function dedupe(confirmed) {
  const ranked = [...confirmed].sort((a, b) =>
    (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) || a.order - b.order)
  const kept = []
  for (const f of ranked) {
    const overlaps = kept.some(k => k.file === f.file && k.family === f.family && k.start <= f.end && f.start <= k.end)
    if (!overlaps) kept.push(f)
  }
  return kept
    .sort((a, b) => a.order - b.order || (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) ||
      a.file.localeCompare(b.file) || a.start - b.start)
    .map(({ file, start, end, axis, severity, why, fix }) => ({ file, start, end, axis, severity, why, fix }))
}

const mode = MODES[INPUTS.mode]
const failed = []

// Every lens starts now, ahead of any finder, so lenses take the first slots.
// Never rejects, so one dead lens can't sink the finders waiting on it.
const lensRuns = Object.fromEntries(mode.lenses.map(name => [name, agent(
  `${RULES}\n\nYour lens:\n${INPUTS.rubric.lens[name]}\n${LENS_EXTRA[name]?.() ?? ''}\nReturn a concise report.`,
  { label: `lens:${name}`, phase: 'Gather', ...TUNING.lens })
  .catch(() => null)
  .then(r => { if (r == null) failed.push(`lens:${name}`); return r })]))

const lensText = names => Promise.all(names.map(n => lensRuns[n] ?? null))
  .then(rs => rs.map((r, i) => `### ${names[i]}\n${r ?? '(lens unavailable)'}`).join('\n\n'))

const tasks = mode.finders.flatMap((f, order) => {
  if (!f.shard) return [{ ...f, order, paths: null, key: f.label }]
  const shards = shardFiles(INPUTS.files)
  return shards.map((paths, i) => ({ ...f, order, paths, key: shards.length > 1 ? `${f.label}#${i + 1}` : f.label }))
})

const results = await pipeline(tasks,
  // Review: lens-free finders start at t=0; the rest wait only on their own lenses.
  async t => agent(
    `${RULES}\n\n${t.lenses.length ? `Context:\n${await lensText(t.lenses)}` : 'Find callers/callees of the changed code in your files yourself.'}

Your axis:
${INPUTS.rubric.axis[t.axis]}

${scopeText(t.paths)}
Flag changed lines only, and only what would survive the rubric's verification bar.`,
    { label: `find:${t.key}`, phase: 'Review', schema: FINDINGS_SCHEMA, ...TUNING.find })
    .catch(() => null),
  // Verify: starts the moment this finder returns.
  async (r, t) => {
    if (r == null) {
      failed.push(`find:${t.key}`)
      return []
    }
    const extra = t.verifyLenses ? `\n\nContext:\n${await lensText(t.verifyLenses)}` : ''
    const prComments = JSON.stringify(INPUTS.comments[''] ?? [])
    return parallel(r.findings.map(raw => () => {
      const f = { ...raw, axis: t.label, family: t.family, order: t.order }
      const patch = INPUTS.patches?.[f.file]
      return agent(
        `${RULES}\n\n${INPUTS.rubric.verify}${extra}
${patch ? `\n--- patch: ${f.file}\n${patch}` : ''}
Existing comments on ${f.file}: ${JSON.stringify(INPUTS.comments[f.file] ?? [])}
PR-level comments: ${prComments}

Try to REFUTE this ${f.axis} finding: ${JSON.stringify(raw)}
Default refuted=true if uncertain. Set duplicate_of_comment if an existing comment already raises it.`,
        { label: `verify:${f.file}:${f.start}`, phase: 'Verify', schema: VERDICT_SCHEMA,
          ...(f.family === 'bug' && f.severity !== 'low' ? TUNING.verifyBug : TUNING.verify) })
        .then(v => ({ f, v }), () => ({ f, v: null }))
    }))
  })

const confirmed = [], unverified = []
for (const item of results) {
  for (const entry of item ?? []) {
    if (!entry) continue
    const { f, v } = entry
    if (v == null) unverified.push(f)
    else if (!v.refuted && !v.duplicate_of_comment) confirmed.push(f)
  }
}
const findings = dedupe(confirmed)
log(`${findings.length} confirmed, ${unverified.length} unverified, ${failed.length} stages failed`)
return {
  findings,
  unverified: unverified.map(({ file, start, end, axis, severity, why, fix }) => ({ file, start, end, axis, severity, why, fix })),
  failed,
}
