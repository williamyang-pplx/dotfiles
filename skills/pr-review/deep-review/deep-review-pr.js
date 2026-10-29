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

// prefetch.py replaces this line with the PR's inputs plus review-lib.js (RULES,
// schemas, PANELS, BUG_FOCUSES, dedupe, ...) in a per-run copy
// (<git-common-dir>/deep-review/<pr>-<sha>/run.js). Run that copy, never this file.
const INPUTS = null  // @prefetch
if (typeof RULES === 'undefined') {
  throw new Error('deep-review-pr: run the run.js that prefetch.py generates, not this template')
}

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
    focus: BUG_FOCUSES.completeness },
  { axis: 1, label: 'bug', name: 'bug:mechanism', family: 'bug', shard: true, tuning: TUNING.findBug, lenses: BUG_LENSES, verifyLenses: BUG_LENSES,
    focus: BUG_FOCUSES.mechanism },
  { axis: 1, label: 'bug', name: 'bug:removed-behavior', family: 'bug', shard: true, tuning: TUNING.findBug, lenses: BUG_LENSES, verifyLenses: BUG_LENSES,
    focus: BUG_FOCUSES['removed-behavior'] },
  { axis: 1, label: 'bug', name: 'bug:operational', family: 'bug', shard: true, tuning: TUNING.findBug, lenses: BUG_LENSES, verifyLenses: BUG_LENSES,
    focus: BUG_FOCUSES.operational },
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

const panelFor = f => (f.family === 'bug' ? PANELS.bug : f.axis === 'simplification' ? PANELS.simplification : null)

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

const DEPTH = {
  lens: 'Go deep in your scope: read whole files at headSha, not just hunks; follow callers and callees at least two hops; check configs, tests, and other languages that consume the same names. Expect 20-40 tool calls. Stop when every changed symbol in your scope is covered, then return a detailed report with file:line evidence.',
  find: 'Read every changed file in your scope in full at headSha, not just the hunks, and follow each changed path to its callers before judging it. Expect 15-30 tool calls.',
  critic: 'Spot-check before naming a gap: confirm it in the code, so every probe is worth a fresh agent. Expect 10-20 tool calls.',
  verify: 'Check the evidence yourself in the code. Expect under 15 tool calls.',
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

const REPRO_ROOT = `/tmp/deep-review-repro/${INPUTS.pr}-${INPUTS.headSha.slice(0, 12)}`

const failed = []
const SHARDS = shardFiles(INPUTS.files, SHARD_LINES, MAX_SHARDS)

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

function verifyFinding(raw, t, extra, index) {
  const f = { ...raw, axis: t.label, family: t.family, order: t.order }
  const label = `verify:${f.file}:${f.start}`
  const dupNote = 'Set duplicate_of_comment if an existing comment already raises it.'
  const panel = panelFor(f)
  if (!panel) {
    return agent(`${verifyPrompt(f, raw, extra, DEPTH.verify)}\nTry to REFUTE it. Default refuted=true if uncertain. ${dupNote}`,
      { label, phase: 'Verify', schema: VERDICT_SCHEMA, ...TUNING.verify })
      .then(v => ({ f, v }), () => ({ f, v: null }))
  }
  const tuning = panel === PANELS.bug ? TUNING.verifyBug : TUNING.defend
  const votes = parallel(Object.entries(panel.angles).map(([angle, text]) => () => agent(
    `${verifyPrompt(f, raw, extra, DEPTH.verify)}\n${panel.stance}\nYour angle: ${text}\n${dupNote}`,
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
// Saved as result.json next to run.js, so a later quick-review can reuse the research.
const lensReports = Object.fromEntries(await Promise.all(LENSES.map(async ({ name }) => [name, await lensRuns[name]])))
return {
  kind: 'deep',
  pr: INPUTS.pr,
  headSha: INPUTS.headSha,
  mine: INPUTS.mine,
  lensReports,
  findings,
  unverified: unverified.map(summary),
  failed,
}
