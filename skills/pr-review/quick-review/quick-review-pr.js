export const meta = {
  name: 'quick-review-pr',
  description: 'Quick PR review on the deep-review axes: prefetched context → parallel finders → one verifier each (three for high bugs); re-reviews only what changed since the last review',
  phases: [
    { title: 'Review', detail: 'four bug finders, a simplification finder, and a style finder, all started at once' },
    { title: 'Recheck', detail: 'status of the last review\'s findings' },
    { title: 'Verify', detail: 'one verifier per finding, three skeptics per high bug' },
  ],
}

// `prefetch.py --template quick` (in deep-review/) replaces this line with the
// PR's inputs plus review-lib.js (RULES, schemas, PANELS, BUG_FOCUSES, dedupe,
// ...) in a per-run copy. Run that copy, never this file.
const INPUTS = null  // @prefetch
if (typeof RULES === 'undefined') {
  throw new Error('quick-review-pr: run the run.js that prefetch.py --template quick generates, not this template')
}

// Speed comes from what's skipped — lens agents, the critic and probes, the
// component inventory, repros — not from fewer parallel finders.
const TUNING = {
  findBug: { effort: 'medium' },
  find: { effort: 'low' },
  verifyBug: { effort: 'medium' },
  verify: { agentType: 'Explore', model: 'sonnet', effort: 'low' },
  recheck: { agentType: 'Explore', model: 'sonnet', effort: 'low' },
}
const SHARD_LINES = 600
const MAX_SHARDS = 3
const RECHECK_BATCH = 5
// Past this many changed lines, a cold quick review notes that /deep-review fits better.
const DEEP_REVIEW_LINES = 1500

// Same axes and report order as deep-review; correctness keeps all four focuses.
const FINDERS = [
  ...Object.entries(BUG_FOCUSES).map(([name, focus]) => (
    { axis: 1, label: 'bug', name: `bug:${name}`, family: 'bug', shard: true, tuning: TUNING.findBug, focus })),
  { axis: 2, label: 'simplification', family: 'shape',
    focus: 'Both passes at once: whether each component the PR adds needs to exist, and the shape of the change as a whole.' },
  { axis: 3, label: 'style', family: 'surface' },
]

const missingAxes = [...new Set(FINDERS.map(f => f.axis))].filter(n => !INPUTS.rubric.axis[n])
if (missingAxes.length) {
  throw new Error(`quick-review-pr: deep-review's SKILL.md is missing "## Axis N" sections [${missingAxes.join(', ')}]`)
}

const RECHECK_SCHEMA = {
  type: 'object',
  required: ['statuses'],
  properties: {
    statuses: {
      type: 'array',
      items: {
        type: 'object',
        required: ['index', 'status', 'reason'],
        properties: {
          index: { type: 'integer' },
          status: { type: 'string', enum: ['addressed', 'partial', 'not_addressed', 'no_longer_applies'] },
          reason: { type: 'string', description: 'evidence with file:line at headSha' },
        },
      },
    },
  },
}

const DEPTH = {
  find: 'Be quick: the context above replaces a research pass. Read the changed code and its call sites there; open other files only to confirm a specific suspicion. Expect under 10 tool calls.',
  verify: 'Check the evidence in the code. Expect under 8 tool calls.',
}

const prior = INPUTS.prior
const since = INPUTS.since
const priorFindings = prior?.findings ?? []
// A re-review covers only what changed since the last review; with no new commits it only rechecks.
const diff = since ? { files: since.files, patches: since.patches, dir: since.dir } : PR_DIFF
const scopeNote = since
  ? `This is a re-review: review only what changed since the last review at ${since.base}. The full PR diff is in ${INPUTS.ctxDir}/diff.patch for reference;
if the branch was rebased, changes that came from the base branch rather than the PR are not findings.\n`
  : ''

const context = INPUTS.context
const priorResearch = Object.entries(prior?.lensReports ?? {}).filter(([, report]) => report)
// Shared by every finder after RULES, so it's cache-friendly too.
const SHARED = [
  RULES,
  priorResearch.length
    ? `## Research from the last ${prior.kind} review (at ${prior.headSha}; the code may have moved since)\n${priorResearch.map(([name, report]) => `### ${name}\n${report}`).join('\n\n')}`
    : '',
  `## AGENTS.md / CLAUDE.md on the touched paths\n${context.docs}`,
  `## Call sites of the changed symbols (git grep at headSha)\n${context.callSites}`,
  context.files
    ? `## Changed files at headSha\n${Object.entries(context.files).map(([path, text]) => `--- ${path}\n${text}`).join('\n\n')}`
    : `## Changed files at headSha\nRead them from ${context.headDir}/<path>.`,
  priorFindings.length
    ? `## Raised by the last review (rechecked separately; don't re-raise)\n${JSON.stringify(priorFindings.map(summary))}`
    : '',
].filter(Boolean).join('\n\n')

const failed = []

function runFinder(t) {
  return agent(
    `${SHARED}\n\nYour axis:\n${INPUTS.rubric.axis[t.axis]}
${t.focus ? `\nYour focus within it: ${t.focus}\n` : ''}
${scopeNote}${scopeText(t.paths, diff)}

${DEPTH.find}
Flag changed lines only, and only what would survive the rubric's verification bar.`,
    { label: `find:${t.key}`, phase: 'Review', schema: FINDINGS_SCHEMA, ...(t.tuning ?? TUNING.find) })
    .catch(() => null)
    .then(r => { if (r == null) failed.push(`find:${t.key}`); return r })
}

// High bugs keep deep-review's three-skeptic panel (parallel, so it costs no
// wall-clock); everything else gets one verifier holding every angle at once.
function verifyFinding(raw, t) {
  const f = { ...raw, axis: t.label, family: t.family, order: t.order }
  const label = `verify:${f.file}:${f.start}`
  const dupNote = 'Set duplicate_of_comment if an existing comment already raises it.'
  const base = verifyPrompt(f, raw, '', DEPTH.verify)
  if (f.family === 'bug' && f.severity === 'high') {
    return parallel(Object.entries(PANELS.bug.angles).map(([angle, text]) => () => agent(
      `${base}\n${PANELS.bug.stance}\nYour angle: ${text}\n${dupNote}`,
      { label: `${label}:${angle}`, phase: 'Verify', schema: VERDICT_SCHEMA, ...TUNING.verifyBug })))
      .then(votes => {
        const cast = votes.filter(Boolean)
        if (!cast.length) return { f, v: null }
        const refutes = cast.filter(v => v.refuted).length
        return { f: triage(f, cast), v: { refuted: PANELS.bug.kills(refutes, cast.length), duplicate_of_comment: cast.some(v => v.duplicate_of_comment) } }
      })
  }
  const panel = f.family === 'bug' ? PANELS.bug : f.axis === 'simplification' ? PANELS.simplification : null
  const stance = panel
    ? `${panel.stance}\nCheck every angle: ${Object.values(panel.angles).join(' ')}`
    : 'Try to REFUTE it. Default refuted=true if uncertain.'
  const tuning = f.family === 'bug' && f.severity === 'medium' ? TUNING.verifyBug : TUNING.verify
  return agent(`${base}\n${stance}\n${dupNote}`, { label, phase: 'Verify', schema: VERDICT_SCHEMA, ...tuning })
    .then(v => ({ f: f.family === 'bug' ? triage(f, [v]) : f, v }), () => ({ f, v: null }))
}

function recheck(batch, offset) {
  return agent(
    `${RULES}\n\nThe last review (at ${prior.headSha}) raised these findings; their line numbers are from that commit.
For each, find the code it was about at headSha and say whether it was addressed, partially addressed, not addressed,
or no longer applies (the code is gone or the premise changed).
Findings: ${JSON.stringify(batch.map((f, i) => ({ index: offset + i, ...summary(f) })))}

Expect under 8 tool calls.`,
    { label: `recheck#${offset / RECHECK_BATCH + 1}`, phase: 'Recheck', schema: RECHECK_SCHEMA, ...TUNING.recheck })
    .catch(() => null)
    .then(r => { if (r == null) failed.push(`recheck#${offset / RECHECK_BATCH + 1}`); return r?.statuses ?? [] })
}

const batches = Array.from({ length: Math.ceil(priorFindings.length / RECHECK_BATCH) }, (_, i) => i * RECHECK_BATCH)
const rechecked = Promise.all(batches.map(offset => recheck(priorFindings.slice(offset, offset + RECHECK_BATCH), offset)))
  .then(results => {
    const byIndex = Object.fromEntries(results.flat().map(s => [s.index, s]))
    return priorFindings.map((f, i) => ({ ...summary(f), status: byIndex[i]?.status ?? 'unchecked', statusReason: byIndex[i]?.reason }))
  })

const shards = shardFiles(diff.files, SHARD_LINES, MAX_SHARDS)
const tasks = !diff.files.length ? [] : FINDERS.flatMap((f, order) => {
  const key = f.name ?? f.label
  if (!f.shard) return [{ ...f, order, paths: null, key }]
  return shards.map((paths, i) => ({ ...f, order, paths, key: shards.length > 1 ? `${key}#${i + 1}` : key }))
})
if (!tasks.length) log(`no changes since the last review at ${since?.base}; rechecking its findings only`)

// Each finder's findings go to verification the moment it returns.
const verified = tasks.map(t => runFinder(t).then(r => (r ? parallel(r.findings.map(raw => () => verifyFinding(raw, t))) : [])))
const [entries, priorStatus] = await Promise.all([Promise.all(verified).then(rs => rs.flat().filter(Boolean)), rechecked])

const confirmed = [], unverified = []
for (const { f, v } of entries) {
  if (v == null) unverified.push(f)
  else if (!v.refuted && !v.duplicate_of_comment) confirmed.push(f)
}
const findings = dedupe(confirmed)

const changed = INPUTS.files.reduce((n, f) => n + f.changes, 0)
const note = prior && !since
  ? `the last review's commit ${prior.headSha} isn't available locally, so the whole diff was reviewed`
  : !prior && changed > DEEP_REVIEW_LINES
    ? `${changed} changed lines: a quick pass is shallow at this size; consider /deep-review`
    : null
log(`${findings.length} confirmed, ${unverified.length} unverified, ${priorStatus.length} rechecked, ${failed.length} stages failed`)

// Saved as result.json next to run.js. openFindings carries everything still
// unresolved into the next re-review, and lensReports carries the research.
const stillOpen = priorStatus.filter(p => ['partial', 'not_addressed', 'unchecked'].includes(p.status))
return {
  kind: 'quick',
  pr: INPUTS.pr,
  headSha: INPUTS.headSha,
  mine: INPUTS.mine,
  mode: since ? 'rereview' : 'cold',
  since: since?.base ?? null,
  note,
  findings,
  prior: priorStatus,
  unverified: unverified.map(summary),
  failed,
  openFindings: [...findings, ...stillOpen.map(summary)],
  lensReports: prior?.lensReports ?? {},
}
