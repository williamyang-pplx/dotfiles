export const meta = {
  name: 'deep-review-pr',
  description: 'Deep-review a PR on three axes (bugs, simplification/structure, style): sharded lenses → finders → completeness critic and probes → adversarial verify with bug repros, all streaming',
  phases: [
    { title: 'Gather', detail: 'context lenses, sharded by file, all started at once' },
    { title: 'Review', detail: 'four bug finders per file shard, a structure finder, style finders per shard; each starts when its lenses finish' },
    { title: 'Simplify', detail: 'inventory the PR\'s components; a challenger per batch argues each one shouldn\'t exist' },
    { title: 'Probe', detail: 'a critic names what the first pass missed; one targeted finder per gap' },
    { title: 'Verify', detail: 'three skeptics per bug plus a repro for high/medium, two defenders per simplification, one skeptic per style finding' },
  ],
}

// prefetch.py replaces this line with the PR's inputs in a per-run copy
// (<git-common-dir>/deep-review/<pr>-<sha>/run.js). Run that copy, never this file.
const INPUTS = null  // @prefetch

const TUNING = {
  lens: { agentType: 'Explore', model: 'sonnet', effort: 'medium' },
  find: { effort: 'medium' },
  findBug: { effort: 'high' },
  critic: { effort: 'high' },
  inventory: { model: 'sonnet', effort: 'low' },
  challenge: { effort: 'high' },
  verify: { agentType: 'Explore', model: 'sonnet', effort: 'low' },
  verifyBug: { effort: 'medium' },
  repro: { effort: 'medium' },
  defend: { effort: 'medium' },
}
// Changed lines per shard for sharded lenses and axes. One huge file stays one shard.
const SHARD_LINES = 400
const MAX_SHARDS = 6
const MAX_PROBES = 6
// Components per simplification challenger; batches grow past this rather than
// leave components unchallenged once MAX_SIMPLIFY_BATCHES is reached.
const SIMPLIFY_BATCH = 6
const MAX_SIMPLIFY_BATCHES = 8

// Lens names must match the bold bullets in SKILL.md's "## Gather context".
// Sharded lenses run once per file shard and their reports are concatenated.
const LENSES = [
  { name: 'Linear lineage' },
  { name: 'Callers and contracts', shard: true },
  { name: 'Neighboring patterns' },
  { name: 'History', shard: true },
  { name: 'Past review comments' },
  { name: 'Duplication sweep', shard: true },
  { name: 'Reuse candidates' },
  { name: 'Docs and conventions' },
]

// Axis labels come from here, never from the model. `lenses` are the only
// reports a finder waits on. `family` groups findings at overlapping lines as
// the same finding. Finders are listed in SKILL.md's "## Report" order.
// Correctness gets the most: four focused finders per file shard at high effort.
const BUG_LENSES = ['Callers and contracts', 'History']
const FINDERS = [
  { axis: 1, label: 'bug', name: 'bug:completeness', family: 'bug', shard: true, tuning: TUNING.findBug,
    lenses: [...BUG_LENSES, 'Linear lineage'], verifyLenses: BUG_LENSES,
    focus: 'Completeness: does the PR do all of what its description and linked ticket promise; every path the change should reach — callers and contracts not updated, branches and error paths missed, resource or state leaks.' },
  { axis: 1, label: 'bug', name: 'bug:mechanism', family: 'bug', shard: true, tuning: TUNING.findBug, lenses: BUG_LENSES, verifyLenses: BUG_LENSES,
    focus: 'Mechanism and compatibility: does the new logic do what the description says — wrong conditions, edge cases, races, regressions against the prior behavior — and does it break clients, SDKs, older deployed versions, or persisted/serialized data and wire formats.' },
  { axis: 1, label: 'bug', name: 'bug:removed-behavior', family: 'bug', shard: true, tuning: TUNING.findBug, lenses: BUG_LENSES, verifyLenses: BUG_LENSES,
    focus: 'Removed behavior: everything the PR deletes, bypasses, or stops doing — code, branches, validation, side effects, defaults — and who still relies on it.' },
  { axis: 1, label: 'bug', name: 'bug:operational', family: 'bug', shard: true, tuning: TUNING.findBug, lenses: BUG_LENSES, verifyLenses: BUG_LENSES,
    focus: 'Operational: unbounded loops and waits with no timeout, retry storms, work lost or inconsistent on cancellation or partial failure, silent failures, status not propagated, missing authorization, config/secret/migration dependencies and deploy order, hot-path performance regressions.' },
  { axis: 2, label: 'simplification', name: 'simplification:structure', family: 'shape',
    focus: 'The change as a whole: structure and design, duplication, reuse, and file and project layout.',
    lenses: ['Callers and contracts', 'Neighboring patterns', 'Duplication sweep', 'Reuse candidates', 'Linear lineage', 'Docs and conventions'] },
  // Not sharded by file: an inventory agent lists the PR's components and each
  // batch of them gets its own challenger (see simplifyRound).
  { axis: 2, label: 'simplification', name: 'simplification:components', family: 'shape', inventory: true, tuning: TUNING.challenge,
    focus: 'Whether each listed component needs to exist.',
    lenses: ['Docs and conventions', 'Duplication sweep', 'Neighboring patterns', 'Callers and contracts'] },
  { axis: 3, label: 'style', family: 'surface', shard: true,
    lenses: ['Docs and conventions', 'Neighboring patterns', 'Past review comments'] },
]

// Every bug faces three skeptics (plus a repro for high/medium) and dies on a
// majority of refutes; a simplification faces two defenders and dies if either wins.
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
const panelFor = f => (f.family === 'bug' ? PANELS.bug : f.axis === 'simplification' ? PANELS.simplification : null)

if (!INPUTS) {
  throw new Error('deep-review-pr: run the run.js that prefetch.py generates, not this template')
}
const missingLenses = LENSES.map(l => l.name).filter(n => !INPUTS.rubric.lens[n])
const missingAxes = [...new Set(FINDERS.map(f => f.axis))].filter(n => !INPUTS.rubric.axis[n])
if (missingLenses.length || missingAxes.length) {
  throw new Error(`deep-review-pr: SKILL.md is missing lens bullets [${missingLenses.join(', ')}] or "## Axis N" sections [${missingAxes.join(', ')}]`)
}

const LENS_EXTRA = {
  // Folds the roadmap search into the one Linear trip.
  'Linear lineage': () => INPUTS.rubric.helper,
  'Docs and conventions': () => 'Read every AGENTS.md/CLAUDE.md on the touched paths in the PR repo yourself; only the session repo\'s are preloaded.',
}

// Identical leading text across every agent, so it's cache-friendly.
const RULES = `You are one subagent inside the deep-review-pr workflow for PR ${INPUTS.pr} at ${INPUTS.headSha}.
${INPUTS.mine
  ? 'This is William\'s own PR, about to go to human review: catch what a reviewer would.'
  : `This is a teammate's PR (author ${INPUTS.author}): assume competence; simplification and structure findings must clearly pay for the churn of restructuring their nearly-done work.`}
PR description (the spec):
${INPUTS.description}

The repo is ${INPUTS.repoDir}: cd there before any git command or search. Read PR code at that commit only
(\`git show ${INPUTS.headSha}:<path>\`, \`git grep <pat> ${INPUTS.headSha}\`); the working tree may be another branch. Patches not inlined below are in ${INPUTS.ctxDir}/files/<path>.patch.
Strictly read-only: no edits, checkouts, test runs, pushes, or GitHub posts (gh reads are fine); never call Workflow or spawn agents.
Return only the structured output or report.`

const DEPTH = {
  lens: 'Go deep in your scope: read whole files at headSha, not just hunks; follow callers and callees at least two hops; check configs, tests, and other languages that consume the same names. Expect 20-40 tool calls. Stop when every changed symbol in your scope is covered, then return a detailed report with file:line evidence.',
  find: 'Read every changed file in your scope in full at headSha, not just the hunks, and follow each changed path to its callers before judging it. Expect 15-30 tool calls.',
  critic: 'Spot-check before naming a gap: confirm it in the code, so every probe is worth a fresh agent. Expect 10-20 tool calls.',
  verify: 'Check the evidence yourself in the code. Expect under 15 tool calls.',
}

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

const PROBES_SCHEMA = {
  type: 'object',
  required: ['probes'],
  properties: {
    probes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['axis', 'files', 'question'],
        properties: {
          axis: { type: 'string', enum: [...new Set(FINDERS.map(f => f.label))] },
          files: { type: 'array', items: { type: 'string' }, description: 'changed files the probe reviews' },
          question: { type: 'string', description: 'what the fresh finder must answer, with the code it should read' },
        },
      },
    },
  },
}

const INVENTORY_SCHEMA = {
  type: 'object',
  required: ['components'],
  properties: {
    components: {
      type: 'array',
      items: {
        type: 'object',
        required: ['kind', 'name', 'file', 'start', 'end'],
        properties: {
          kind: { type: 'string', enum: ['file', 'class', 'function', 'parameter', 'config', 'constant', 'state', 'branch', 'test', 'dependency'] },
          name: { type: 'string' },
          file: { type: 'string', description: 'repo-relative path, no a/ b/ prefix' },
          start: { type: 'integer', description: 'file line number at headSha' },
          end: { type: 'integer' },
        },
      },
    },
  },
}

const REPRO_SCHEMA = {
  type: 'object',
  required: ['outcome', 'reason'],
  properties: {
    outcome: { type: 'string', enum: ['reproduced', 'not_reproduced', 'could_not_run'] },
    reason: { type: 'string', description: 'the command run and what it showed, or why it could not run' },
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

const SEVERITY_RANK = { high: 0, medium: 1, low: 2 }
const REPRO_ROOT = `/tmp/deep-review-repro/${INPUTS.pr}-${INPUTS.headSha.slice(0, 12)}`

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

const failed = []
const SHARDS = shardFiles(INPUTS.files)

// Every lens starts now, ahead of any finder, so lenses take the first slots.
// Never rejects, so one dead lens shard can't sink the finders waiting on it.
function runLens(name, paths, key) {
  return agent(
    `${RULES}\n\nYour lens:\n${INPUTS.rubric.lens[name]}\n${LENS_EXTRA[name]?.() ?? ''}\n\n${scopeText(paths)}\n\n${DEPTH.lens}`,
    { label: `lens:${key}`, phase: 'Gather', ...TUNING.lens })
    .catch(() => null)
    .then(r => { if (r == null) failed.push(`lens:${key}`); return r })
}

const lensRuns = Object.fromEntries(LENSES.map(({ name, shard }) => {
  const runs = shard && SHARDS.length > 1
    ? SHARDS.map((paths, i) => runLens(name, paths, `${name}#${i + 1}`))
    : [runLens(name, null, name)]
  return [name, Promise.all(runs).then(rs => rs.filter(r => r != null).join('\n\n') || null)]
}))

const lensText = names => Promise.all(names.map(n => lensRuns[n]))
  .then(rs => rs.map((r, i) => `### ${names[i]}\n${r ?? '(lens unavailable)'}`).join('\n\n'))

function runFinder(t) {
  return lensText(t.lenses)
    .then(context => agent(
      `${RULES}\n\nContext:\n${context}

Your axis:
${INPUTS.rubric.axis[t.axis]}
${t.focus ? `\nYour focus within it: ${t.focus}\n` : ''}${t.question ? `\nProbe from the completeness critic — answer this, and flag only what it uncovers: ${t.question}\n` : ''}${t.components ? `\nComponents to challenge — argue each should not exist, and flag only those you can replace:\n${JSON.stringify(t.components)}\n` : ''}
${scopeText(t.paths)}

${DEPTH.find}
Flag changed lines only, and only what would survive the rubric's verification bar.`,
      { label: `find:${t.key}`, phase: t.question ? 'Probe' : t.components ? 'Simplify' : 'Review',
        schema: FINDINGS_SCHEMA, ...(t.tuning ?? TUNING.find) }))
    .catch(() => null)
    .then(r => { if (r == null) failed.push(`find:${t.key}`); return r })
}

function verifyPrompt(f, raw, extra) {
  const patch = INPUTS.patches?.[f.file]
  return `${RULES}\n\n${INPUTS.rubric.verify}${extra}
${patch ? `\n--- patch: ${f.file}\n${patch}` : ''}
Existing comments on ${f.file}: ${JSON.stringify(INPUTS.comments[f.file] ?? [])}
PR-level comments: ${JSON.stringify(INPUTS.comments[''] ?? [])}

${DEPTH.verify}
The ${f.axis} finding: ${JSON.stringify(raw)}`
}

// The one agent allowed to write: a throwaway worktree outside the PR checkout.
function reproPrompt(f, raw, dir) {
  return `${RULES}

You are the repro verifier for this bug: ${JSON.stringify(raw)}
Exception to the read-only rule, for you only: you may create one scratch worktree and run tests or a small script in it.
1. \`git -C ${INPUTS.repoDir} worktree add --detach ${dir} ${INPUTS.headSha}\`
2. In ${dir}, run the narrowest existing test that exercises ${f.file}:${f.start}, or write a minimal repro test or script there
   (never in ${INPUTS.repoDir}). Use the repo's own runner (see AGENTS.md, Makefile, bin/). Keep each command under about 5 minutes;
   if it needs services, credentials, or a long build, stop and report could_not_run.
3. Always clean up, even on failure: \`git -C ${INPUTS.repoDir} worktree remove --force ${dir}\`
outcome: reproduced (you observed the claimed bad behavior), not_reproduced (the repro ran and behaved correctly), or could_not_run.`
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

function verifyFinding(raw, t, extra, index) {
  const f = { ...raw, axis: t.label, family: t.family, order: t.order }
  const label = `verify:${f.file}:${f.start}`
  const dupNote = 'Set duplicate_of_comment if an existing comment already raises it.'
  const panel = panelFor(f)
  if (!panel) {
    return agent(`${verifyPrompt(f, raw, extra)}\nTry to REFUTE it. Default refuted=true if uncertain. ${dupNote}`,
      { label, phase: 'Verify', schema: VERDICT_SCHEMA, ...TUNING.verify })
      .then(v => ({ f, v }), () => ({ f, v: null }))
  }
  const tuning = panel === PANELS.bug ? TUNING.verifyBug : TUNING.defend
  const votes = parallel(Object.entries(panel.angles).map(([angle, text]) => () => agent(
    `${verifyPrompt(f, raw, extra)}\n${panel.stance}\nYour angle: ${text}\n${dupNote}`,
    { label: `${label}:${angle}`, phase: 'Verify', schema: VERDICT_SCHEMA, ...tuning })))
  const dir = `${REPRO_ROOT}/${`${t.key}-${index}-${f.file}-${f.start}`.replace(/[^\w.-]+/g, '_')}`
  const repro = panel === PANELS.bug && f.severity !== 'low'
    ? agent(reproPrompt(f, raw, dir), { label: `${label}:repro`, phase: 'Verify', schema: REPRO_SCHEMA, ...TUNING.repro }).catch(() => null)
    : Promise.resolve(null)
  return Promise.all([votes, repro]).then(([all, run]) => {
    const cast = all.filter(Boolean)
    const ran = run != null && run.outcome !== 'could_not_run'
    if (!cast.length && !ran) return { f, v: null }
    const duplicate_of_comment = cast.some(v => v.duplicate_of_comment)
    const triaged = panel === PANELS.bug ? triage(f, cast) : f
    if (run?.outcome === 'reproduced') return { f: { ...triaged, repro: run.reason }, v: { refuted: false, duplicate_of_comment } }
    const refutes = cast.filter(v => v.refuted).length + (ran ? 1 : 0)
    return { f: triaged, v: { refuted: panel.kills(refutes, cast.length + (ran ? 1 : 0)), duplicate_of_comment } }
  })
}

async function verifyAll(findings, t) {
  const extra = t.verifyLenses ? `\n\nContext:\n${await lensText(t.verifyLenses)}` : ''
  return parallel(findings.map((raw, i) => () => verifyFinding(raw, t, extra, i)))
}

const tasks = FINDERS.flatMap((f, order) => {
  const key = f.name ?? f.label
  if (f.inventory) return []
  if (!f.shard) return [{ ...f, order, paths: null, key }]
  return SHARDS.map((paths, i) => ({ ...f, order, paths, key: SHARDS.length > 1 ? `${key}#${i + 1}` : key }))
})

// Each finder's findings go to verification the moment it returns.
function startTask(t) {
  const found = runFinder(t)
  return { t, found, verified: found.then(r => (r ? verifyAll(r.findings, t) : [])) }
}

const round1 = tasks.map(startTask)

// Simplification: the inventory starts alongside the lenses; each batch of
// components then gets a challenger, whose findings go to two defenders.
function runInventory() {
  return agent(
    `${RULES}\n\nList every component this PR adds or substantially grows, for an adversarial simplification pass:
files, classes, functions, parameters and flags, config keys and env vars, constants, fields and state, branches and special cases, tests, dependencies.
One entry per component, at its headSha lines. Skip one-line edits to existing code.

${scopeText(null)}

Expect under 15 tool calls.`,
    { label: 'simplify:inventory', phase: 'Simplify', schema: INVENTORY_SCHEMA, ...TUNING.inventory })
    .catch(() => null)
    .then(r => {
      if (r == null) {
        failed.push('simplify:inventory')
        return []
      }
      return r.components.filter(c => INPUTS.files.some(f => f.path === c.file))
    })
}

function batchComponents(components) {
  const sorted = [...components].sort((a, b) => a.file.localeCompare(b.file) || a.start - b.start)
  const size = Math.max(SIMPLIFY_BATCH, Math.ceil(sorted.length / MAX_SIMPLIFY_BATCHES))
  return Array.from({ length: Math.ceil(sorted.length / size) }, (_, i) => sorted.slice(i * size, (i + 1) * size))
}

const simplifier = FINDERS.find(f => f.inventory)
const simplifyRound = runInventory().then(components => {
  const batches = batchComponents(components)
  log(`simplification: challenging ${components.length} components in ${batches.length} batches`)
  return batches.map((batch, i) => startTask({
    ...simplifier, order: FINDERS.indexOf(simplifier), components: batch, paths: [...new Set(batch.map(c => c.file))],
    key: batches.length > 1 ? `${simplifier.name}#${i + 1}` : simplifier.name }))
})
const firstPass = simplifyRound.then(simplified => [...round1, ...simplified])

// Probe: the one barrier — the critic needs every round-1 candidate to judge what's missing.
const probed = firstPass.then(async pass => {
  const results = await Promise.all(pass.map(x => x.found))
  const candidates = results.flatMap((r, i) => (r?.findings ?? []).map(f => ({
    ...f, axis: pass[i].t.label, family: pass[i].t.family })))
  const plan = await agent(
    `${RULES}\n\nYou are the completeness critic. The first review pass is done; find what it missed.

Lens reports:
${await lensText(LENSES.map(l => l.name))}

Changed files (changed lines): ${INPUTS.files.map(f => `${f.path} (${f.changes})`).join(', ')}
Stages that failed: ${failed.length ? failed.join(', ') : 'none'}
Candidate findings so far: ${JSON.stringify(candidates.map(summary))}

Name up to ${MAX_PROBES} probes. Each is a specific gap no candidate covers: a changed file or hunk nobody examined deeply,
an interaction between changed files, a contract consumer the callers-and-contracts report lists but no finding checked,
or a risk a lens report raised that no finding addresses. Don't re-raise a candidate. Return no probes if coverage is solid.

${DEPTH.critic}`,
    { label: 'critic', phase: 'Probe', schema: PROBES_SCHEMA, ...TUNING.critic }).catch(() => null)
  if (plan == null) {
    failed.push('critic')
    return []
  }
  if (plan.probes.length > MAX_PROBES) log(`critic named ${plan.probes.length} gaps; probing the first ${MAX_PROBES}`)
  const probes = plan.probes.slice(0, MAX_PROBES).map((p, i) => {
    const base = FINDERS.find(f => f.label === p.axis)
    const files = p.files.filter(path => INPUTS.files.some(f => f.path === path))
    return { ...base, order: FINDERS.indexOf(base), paths: files.length ? files : null,
      question: p.question, key: `probe#${i + 1}:${p.axis}` }
  })
  log(`probing ${probes.length} gaps`)
  return parallel(probes.map(t => async () => {
    const r = await runFinder(t)
    if (r == null) return []
    // Skip what round 1 already raised, so verifiers aren't spent on it twice.
    const fresh = r.findings.filter(f => !candidates.some(c => overlaps(c, { ...f, family: t.family })))
    return verifyAll(fresh, t)
  }))
})

const entries = (await Promise.all([
  ...round1.map(x => x.verified),
  simplifyRound.then(simplified => Promise.all(simplified.map(x => x.verified))).then(rs => rs.flat()),
  probed.then(rs => rs.flat()),
]))
  .flat()
  .filter(Boolean)

const confirmed = [], unverified = []
for (const { f, v } of entries) {
  if (v == null) unverified.push(f)
  else if (!v.refuted && !v.duplicate_of_comment) confirmed.push(f)
}
const findings = dedupe(confirmed)
log(`${findings.length} confirmed, ${unverified.length} unverified, ${failed.length} stages failed`)
return {
  mine: INPUTS.mine,
  findings,
  unverified: unverified.map(summary),
  failed,
}
