export const meta = {
  name: 'implement-bundles',
  description: '사용자가 허락한 구현 계획의 묶음을 coder 로 돌리고(공통 묶음 먼저, 소스마다 first 묶음 먼저, 나머지는 파일이 겹치지 않아 같은 소스도 동시에 셋까지), 모두 끝나면 doc-writer 하나가 문서를 맞춘다. git 쓰기는 하지 않는다',
  whenToUse: '사용자가 "implement-bundles 로 구현한다" 고 적힌 구현 계획을 허락했을 때만 주 에이전트가 부른다 (AGENTS.md 작업 절차, CLAUDE.md). args: { bundles: [{ name, source: zigbang|naver|daangn|dabang|common, files: [고칠 파일], brief: 지시서, first?: true(같은 소스의 다른 묶음이 기대는 묶음, 먼저 돈다), effort?: high|xhigh }], baseline: 주 에이전트가 묶음을 띄우기 전에 바뀔 명령·바뀌면 안 되는 명령의 출력을 저장한 scratchpad 경로(없으면 시작하지 않는다), docs?: { brief, files?, effort? }, workerLiveChecks?: true(작업자도 실제 조회 1회. 기본은 주 에이전트가 고치기 전·후 비교를 해서 작업자는 하지 않는다) }. 작업자·문서 작업자 모델은 sonnet 고정이라 지시서에 고칠 함수·부르는 곳·바뀌면 안 되는 동작, 문서에 들어갈 사실을 적는다 (CLAUDE.md, docs/development/agents.md "맡길 때 지시서에 넣는 것"). 작업자는 자기 files 만 고치고 CHANGELOG·docs/llm.md·감시 목록 같은 공용 파일은 보고만 한다. args 없이 불렸으면 아무것도 띄우지 않는다.',
  phases: [
    { title: '공통 구현', detail: '소스에 매이지 않은 묶음, 차례로 먼저' },
    { title: '소스별 구현', detail: '소스마다 first 묶음을 차례로 먼저, 나머지는 같은 소스도 동시에 셋까지, 소스끼리는 동시에' },
    { title: '문서', detail: '모든 묶음이 끝난 뒤 doc-writer 하나' },
  ],
}

const SOURCES = ['zigbang', 'naver', 'daangn', 'dabang']
// 같은 소스의 묶음을 동시에 돌리는 수 (docs/development/agents.md "동시에 띄울 때"). 동시 실행 상한(SAME_SOURCE_MAX)은
// 두 워크플로(web-parity-panel·implement-bundles)와 그 절을 같이 고친다. 워크플로 스크립트는 다른 파일을 불러올
// 수 없어 파일마다 둔다. 두 파일의 상한이 다르거나 한 파일만 소스별 예외를 두면
// tests/test_cli.py::test_workflow_concurrency_limits_match 가 실패한다.
// 네이버도 같은 상한이다. 예전에는 하나씩 돌렸는데, 2026-11-16 에 조사원 셋을 동시에 돌려 429 가 없어 풀었다 (그 절에 실측).
const SAME_SOURCE_MAX = 3
// 코드·문서 작업자 모델. 얽힌 일에도 올리지 않고, 얽힘은 주 에이전트가 지시서에서 푼다 (CLAUDE.md, 2026-11-16 사용자 결정).
// 더 생각해야 하는 묶음은 effort 를 xhigh 로 올린다
const MODEL = 'sonnet'
const EFFORTS = ['high', 'xhigh']

let a = args
// args 가 JSON 문자열로, 때로는 문자열이 한 번 더 감싸여 올 수 있어 객체가 될 때까지 푼다. 읽지 못하면 묶음 없이 불린 것과
// 가르게 따로 알린다 (2026-11-16: 첫 호출의 args 가 문자열로 와 '묶음 없이 불렸다' 로 끝났고, 감싼 문자열인지 읽지 못한
// 문자열인지 가릴 수 없었다)
// 빈 글자·공백뿐인 글자는 읽지 못한 것이 아니라 인자 없이 불린 것이라, 아래 '대상 없이 불림' 안내로 보낸다
if (typeof a === 'string' && !a.trim()) a = null
let parseError = null
for (let i = 0; i < 3 && typeof a === 'string'; i++) {
  try { a = JSON.parse(a) } catch (e) { parseError = String(e); a = null }
}
if (parseError) {
  log(`args 를 JSON 으로 읽지 못해 아무것도 띄우지 않았다: ${parseError}`)
  return {
    started: false,
    reason: 'bad-args',
    error: parseError,
    next: 'args 를 문자열로 감싸지 않고 객체(JSON 값)로 다시 넘긴다.',
  }
}
const bundles = a && Array.isArray(a.bundles) ? a.bundles : []
if (!bundles.length) {
  log('구현 묶음(bundles) 없이 불렸다. 아무것도 띄우지 않았다')
  return {
    started: false,
    next: '이 워크플로는 사용자가 허락한 구현 계획을 묶음으로 나눠 부른다. 계획을 먼저 설명하고 허락받는다 (AGENTS.md 작업 절차). 직접 다시 부르지 않는다.',
  }
}

const norm = f => String(f).trim().replace(/^(\.\/)+/, '')
const problems = []
const names = bundles.map(b => b && b.name)
for (const [i, b] of bundles.entries()) {
  const label = b && b.name ? b.name : `${i + 1}번 묶음`
  if (!b || typeof b.name !== 'string' || !b.name) problems.push(`${label}: name 이 없다`)
  else if (names.indexOf(b.name) !== i) problems.push(`묶음 이름 ${b.name}: 겹친다`)
  if (!b || !(SOURCES.includes(b.source) || b.source === 'common')) problems.push(`${label}: source 는 ${SOURCES.join('·')}·common 중 하나다`)
  if (!b || !Array.isArray(b.files) || !b.files.length) problems.push(`${label}: 고칠 파일(files)이 없다`)
  if (!b || typeof b.brief !== 'string' || !b.brief.trim()) problems.push(`${label}: 지시서(brief)가 없다`)
  if (b && b.first != null && typeof b.first !== 'boolean') problems.push(`${label}: first 는 true·false 다`)
}
// 고치기 전 출력이 없으면 고친 뒤 무엇이 바뀌었는지 비교할 수 없다 (docs/development/agents.md "검증 분담"). 워크플로는 파일을
// 열 수 없어 그 경로에 파일이 있는지는 보지 못하고, 저장하는 단계를 빠뜨리는 것만 막는다.
const baseline = typeof a.baseline === 'string' ? a.baseline.trim() : ''
if (!baseline) {
  problems.push('고치기 전 출력을 저장한 경로(baseline)가 없다. 바뀔 명령과 바뀌면 안 되는 명령의 지금 출력을 scratchpad 에 먼저 저장하고 그 경로를 넘긴다')
}
if (a.docs != null && !(typeof a.docs === 'object' && typeof a.docs.brief === 'string' && a.docs.brief.trim())) {
  problems.push('docs 를 넘겼는데 지시서(docs.brief)가 비었다')
}
const docs = a.docs != null ? a.docs : null

// 동시에 돌 수 있는 두 묶음이 같은 파일을 고치면 거절한다. 공통 묶음은 먼저 차례로, 문서는 마지막이라 겹쳐도 된다. 소스끼리는
// 동시에 돌아 서로 다른 소스의 두 묶음은 언제든 겹칠 수 있다. 같은 소스 안에서는 first 묶음이 차례로 먼저 끝난 뒤 나머지가
// 동시에 돌아, first 가 아닌 두 묶음만 겹칠 수 있다.
const sourced = bundles.filter(b => b && SOURCES.includes(b.source) && Array.isArray(b.files))
const overlap = []
for (const [i, x] of sourced.entries()) {
  for (const y of sourced.slice(i + 1)) {
    if (x.source === y.source && (x.first || y.first)) continue
    const shared = x.files.map(norm).filter(f => y.files.map(norm).includes(f))
    if (shared.length) overlap.push(`${shared.join(', ')} (${x.name}·${y.name})`)
  }
}
if (overlap.length) problems.push(`동시에 돌 수 있는 묶음이 같은 파일을 고친다: ${overlap.join('; ')}`)
if (problems.length) {
  log(`묶음이 잘못돼 아무것도 띄우지 않았다: ${problems.join(' / ')}`)
  return {
    started: false,
    reason: 'bad-bundles',
    problems,
    next: 'problems 를 고쳐서 다시 부른다. 동시에 도는 묶음이 같은 파일을 고치면 묶음을 합치거나, 다른 묶음이 기대는 쪽을 first 묶음(같은 소스)·공통 묶음(여러 소스)으로 뺀다. baseline 이 없으면 고치기 전 출력을 먼저 저장한다.',
  }
}

for (const b of bundles) {
  if (b.model && b.model !== MODEL) log(`묶음 ${b.name}: 작업자는 ${MODEL} 고정이라 ${b.model} 대신 ${MODEL} 으로 돌린다`)
  if (b.effort && !EFFORTS.includes(b.effort)) log(`묶음 ${b.name}: effort ${b.effort} 대신 high 로 돌린다`)
}
if (docs && docs.model && docs.model !== MODEL) log(`문서 작업자는 ${MODEL} 고정이라 ${docs.model} 대신 ${MODEL} 으로 돌린다`)

const REPORT = {
  type: 'object',
  properties: {
    changed: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, what: { type: 'string', description: '바꾼 함수·내용 한 줄' } }, required: ['file', 'what'] } },
    checks: { type: 'string', description: 'ruff check·mypy·바꾼 부분 테스트 결과' },
    liveChecks: {
      type: 'array',
      description: '바꾼 동작마다 실제 조회 1건 (지시가 실제 조회를 하지 말라고 했으면 빈 목록)',
      items: { type: 'object', properties: { command: { type: 'string' }, keyFields: { type: 'string', description: '응답의 핵심 필드만' } }, required: ['command', 'keyFields'] },
    },
    deviations: {
      type: 'array',
      description: '지시서와 다르게 한 것 (docs/development/agents.md "지시서와 다르게 할 때" 의 작은 차이). 없으면 빈 목록',
      items: { type: 'object', properties: { what: { type: 'string', description: '지시서는 무엇이었고 실제로는 어떻게 했는지' }, why: { type: 'string' } }, required: ['what', 'why'] },
    },
    notDone: { type: 'array', items: { type: 'object', properties: { what: { type: 'string' }, why: { type: 'string' } }, required: ['what', 'why'] } },
    othersToTouch: { type: 'array', items: { type: 'string' }, description: '네 files 밖이라 고치지 않은 곳: "파일 — 고칠 내용" (문서, CHANGELOG, 감시 목록 GROUPS 등)' },
  },
  required: ['changed', 'checks', 'deviations', 'notDone', 'othersToTouch'],
}

const allFiles = [...new Set(bundles.flatMap(b => b.files.map(norm)))]
const coderPrompt = b => [
  `묶음: ${b.name} (소스: ${b.source})`,
  `고칠 파일: ${b.files.map(norm).join(', ')}`,
  '',
  '지시서:',
  b.brief,
  '',
  '위 고칠 파일만 고친다. 그 밖의 파일은 열어 보기만 한다. 네 정의가 같은 작업에서 고치라는 문서·CHANGELOG·docs/llm.md·scripts/monitor/api_check.py 의 GROUPS 도',
  '고칠 파일에 없으면 고치지 말고 othersToTouch 에 "파일 — 고칠 내용" 으로 적는다. 다른 묶음과 같은 파일을 덮어쓰지 않기 위해서다.',
  `다른 묶음이 동시에 다른 파일을 고칠 수 있다: ${allFiles.filter(f => !b.files.map(norm).includes(f)).join(', ') || '없음'}. ruff·mypy 오류가 네 파일 밖에서 나면 고치지 말고 보고에 적는다.`,
  b.first ? '같은 소스의 다른 묶음이 이 묶음이 만드는 함수·상수를 쓴다. 지시서에 정한 이름·인자·뜻을 바꾸지 않는다.' : '',
  '지시서대로 할 수 없거나 다르게 하는 편이 맞아 보이면 docs/development/agents.md 의 "지시서와 다르게 할 때" 문단을 따른다. 그 문단의 작은 차이는 deviations 에, 하지 않은 것은 notDone 에 적는다.',
  a.workerLiveChecks !== true
    ? '실제 조회(.venv/bin/jibsa)는 하지 않는다. 주 에이전트가 묶음을 띄우기 전에 남긴 출력과 고친 뒤 출력을 비교한다 (docs/development/agents.md "검증 분담"). 검증은 ruff·mypy·바꾼 부분 테스트만 한다.'
    : b.source === 'common'
      ? '실제 조회는 바꾼 동작을 볼 수 있는 소스 하나로 최소로 한다.'
      : `실제 조회는 ${b.source} 명령만 최소로 한다. 다른 소스는 다른 묶음이 부르고 있을 수 있다.`,
].filter(Boolean).join('\n')

// agent() 가 예외를 던져도 실패로 기록하고 이어 간다.
const tryAgent = async (prompt, opts) => {
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: 예외로 끝났다 (${String(e && e.message || e).slice(0, 120)})`); return null }
}

const results = Object.fromEntries(bundles.map(b => [b.name, { name: b.name, source: b.source, status: 'skipped', report: null }]))

const runOne = async (b, phaseTitle) => {
  results[b.name].status = 'running'
  const r = await tryAgent(coderPrompt(b), {
    label: `구현:${b.name}`,
    phase: phaseTitle,
    agentType: 'coder',
    model: MODEL,
    effort: EFFORTS.includes(b.effort) ? b.effort : 'high',
    schema: REPORT,
  })
  results[b.name] = { name: b.name, source: b.source, status: r ? 'done' : 'failed', report: r }
  if (!r) log(`묶음 ${b.name}: 결과를 내지 못했다. 파일을 일부 고쳤을 수 있다`)
  return Boolean(r)
}

// 한 줄 안에서는 차례로 돌리고, 앞 묶음이 실패하면 뒤 묶음은 그 결과에 기댈 수 있어 건너뛴다.
const runLane = async (lane, phaseTitle) => {
  for (const b of lane) {
    if (!(await runOne(b, phaseTitle))) {
      log(`묶음 ${b.name} 이 실패해 같은 줄의 나머지 묶음은 건너뛴다`)
      return false
    }
  }
  return true
}

// 소스 하나: first 묶음을 차례로 먼저 돌리고(실패하면 나머지는 그 결과에 기대므로 건너뛴다), 나머지는 서로 기대지 않아
// SAME_SOURCE_MAX 개씩 동시에 돌린다. 하나가 실패해도 나머지는 이어 간다.
const runSource = async source => {
  const mine = bundles.filter(b => b.source === source)
  const firsts = mine.filter(b => b.first)
  const rest = mine.filter(b => !b.first)
  if (firsts.length && !(await runLane(firsts, '소스별 구현'))) {
    log(`${source}: first 묶음이 실패해 나머지 묶음(${rest.map(b => b.name).join(', ') || '없음'})은 시작하지 않았다`)
    return false
  }
  let ok = true
  for (let i = 0; i < rest.length; i += SAME_SOURCE_MAX) {
    const rs = await parallel(rest.slice(i, i + SAME_SOURCE_MAX).map(b => () => runOne(b, '소스별 구현')))
    ok = rs.every(Boolean) && ok
  }
  return ok
}

phase('공통 구현')
const common = bundles.filter(b => b.source === 'common')
const commonOk = common.length ? await runLane(common, '공통 구현') : true

let lanesOk = commonOk
if (commonOk) {
  phase('소스별 구현')
  const oks = await parallel(SOURCES.filter(s => bundles.some(b => b.source === s)).map(s => () => runSource(s)))
  lanesOk = oks.every(ok => ok === true)
} else {
  log('공통 묶음이 실패해 소스별 묶음을 시작하지 않았다')
}

const list = bundles.map(b => results[b.name])
const othersToTouch = list.flatMap(r => (r.report ? r.report.othersToTouch || [] : []).map(t => `${t} (묶음 ${r.name})`))
let docsReport = null
if (docs && lanesOk) {
  phase('문서')
  docsReport = await tryAgent([
    '구현 묶음이 모두 끝났다. 아래 보고의 바뀐 내용과 손댈 곳을 보고 문서를 맞춘다.',
    Array.isArray(docs.files) && docs.files.length ? `고칠 문서: ${docs.files.map(norm).join(', ')} (그 밖은 열어 보기만 한다)` : '',
    '',
    '지시서:',
    docs.brief,
    '',
    '구현 보고:',
    ...list.map(r => `- ${r.name} (${r.source}): ${(r.report.changed || []).map(c => `${c.file} — ${c.what}`).join('; ')}${(r.report.deviations || []).length ? ` (지시서와 다르게 한 것: ${r.report.deviations.map(d => `${d.what} — 이유: ${d.why}`).join('; ')})` : ''}`),
    '',
    '묶음들이 손대지 않고 넘긴 곳:',
    ...(othersToTouch.length ? othersToTouch.map(t => `- ${t}`) : ['- 없음']),
    '',
    '문서(docs/·AGENTS.md·CHANGELOG.md·README.md)만 고친다. scripts/·src/·tests/ 처럼 문서가 아닌 곳은 고치지 말고 보고에 남겨 주 에이전트에게 넘긴다.',
    '코드와 어긋나 보여 고치지 못한 것도 보고에 적는다.',
    '지시서와 구현 보고의 "지시서와 다르게 한 것" 이 어긋나면 docs/development/agents.md 의 "지시서와 다르게 할 때" 문단의 문서 작업자 규칙을 따른다 (주 에이전트가 그 차이를 받아들일지 아직 정하지 않았다).',
  ].join('\n'), {
    label: '문서',
    phase: '문서',
    agentType: 'doc-writer',
    model: MODEL,
    effort: EFFORTS.includes(docs.effort) ? docs.effort : 'high',
  })
  if (!docsReport) log('문서 작업자가 결과를 내지 못했다')
} else if (docs) {
  log('실패한 묶음이 있어 문서 단계를 건너뛰었다')
}

const done = list.filter(r => r.status === 'done').length
const needsAttention = list.filter(r => r.report && (r.report.notDone || []).length).map(r => r.name)
if (needsAttention.length) log(`못 한 것이 남은 묶음: ${needsAttention.join(', ')}`)
const deviated = list.filter(r => r.report && (r.report.deviations || []).length).map(r => r.name)
if (deviated.length) log(`지시서와 다르게 한 것이 있는 묶음: ${deviated.join(', ')} (받아들일지 주 에이전트가 정해 사용자에게 알린다)`)
if (!docs && othersToTouch.length) log(`문서 단계가 없어 주 에이전트가 처리할 곳 ${othersToTouch.length}건`)
log(`묶음 ${done}/${list.length} 완료${docs ? `, 문서 ${docsReport ? '완료' : '안 함'}` : ''}. 최종 검증은 주 에이전트가 한다 (지시서 항목 대조, 같은 명령의 지금 출력을 ${baseline} 와 비교)`)
return {
  started: true,
  baseline,
  allReturned: done === list.length && (!docs || Boolean(docsReport)),
  needsAttention,
  deviated,
  othersToTouch,
  bundles: list,
  docs: docsReport,
}
