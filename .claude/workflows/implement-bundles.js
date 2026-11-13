export const meta = {
  name: 'implement-bundles',
  description: '사용자가 허락한 구현 계획의 묶음을 jibsa-coder 로 돌리고(공통 묶음 먼저, 같은 소스는 차례로, 소스끼리는 동시에), 모두 끝나면 jibsa-docs 하나가 문서를 맞춘다. git 쓰기는 하지 않는다',
  whenToUse: '사용자가 "implement-bundles 로 구현한다" 고 적힌 구현 계획을 허락했을 때만 주 에이전트가 부른다 (AGENTS.md 작업 절차, CLAUDE.md). args: { bundles: [{ name, source: zigbang|naver|daangn|dabang|common, files: [고칠 파일], brief: 지시서, model?: sonnet|opus, effort?: high|xhigh }], docs?: { brief, files?, model?, effort? } }. 작업자는 자기 files 만 고치고 CHANGELOG·docs/llm.md·감시 목록 같은 공용 파일은 보고만 한다. args 없이 불렸으면 아무것도 띄우지 않는다.',
  phases: [
    { title: '공통 구현', detail: '소스에 매이지 않은 묶음, 차례로 먼저' },
    { title: '소스별 구현', detail: '소스마다 한 줄로 차례로, 소스끼리는 동시에' },
    { title: '문서', detail: '모든 묶음이 끝난 뒤 jibsa-docs 하나' },
  ],
}

const SOURCES = ['zigbang', 'naver', 'daangn', 'dabang']
const MODELS = ['sonnet', 'opus']  // Haiku 는 쓰지 않는다 (CLAUDE.md)
const EFFORTS = ['high', 'xhigh']

let a = args
if (typeof a === 'string') {
  try { a = JSON.parse(a) } catch { a = null }
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
}
if (a.docs != null && !(typeof a.docs === 'object' && typeof a.docs.brief === 'string' && a.docs.brief.trim())) {
  problems.push('docs 를 넘겼는데 지시서(docs.brief)가 비었다')
}
const docs = a.docs != null ? a.docs : null

// 동시에 도는 것은 서로 다른 소스의 줄뿐이다. 공통 묶음은 먼저 끝나고, 같은 소스 묶음은 차례로, 문서는 마지막이라
// 겹쳐도 안전하다. 서로 다른 소스 줄이 같은 파일을 고칠 때만 거절한다.
const sourceOwners = {}
for (const b of bundles.filter(b => b && SOURCES.includes(b.source) && Array.isArray(b.files))) {
  for (const f of b.files.map(norm)) (sourceOwners[f] ||= new Set()).add(b.source)
}
const overlap = Object.entries(sourceOwners).filter(([, s]) => s.size > 1).map(([f, s]) => `${f} (${[...s].join(', ')})`)
if (overlap.length) problems.push(`서로 다른 소스 묶음이 동시에 같은 파일을 고친다: ${overlap.join('; ')}`)
if (problems.length) {
  log(`묶음이 잘못돼 아무것도 띄우지 않았다: ${problems.join(' / ')}`)
  return {
    started: false,
    reason: 'bad-bundles',
    problems,
    next: '서로 다른 소스 묶음이 같은 파일을 고치면 그 파일을 공통 묶음으로 옮기거나 묶음을 합친다. 고쳐서 다시 부른다.',
  }
}

for (const b of bundles) {
  if (b.model && !MODELS.includes(b.model)) log(`묶음 ${b.name}: 쓰지 않는 모델(${b.model})이라 sonnet 으로 돌린다`)
  if (b.effort && !EFFORTS.includes(b.effort)) log(`묶음 ${b.name}: effort ${b.effort} 대신 high 로 돌린다`)
}

const REPORT = {
  type: 'object',
  properties: {
    changed: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, what: { type: 'string', description: '바꾼 함수·내용 한 줄' } }, required: ['file', 'what'] } },
    checks: { type: 'string', description: 'ruff check·mypy·바꾼 부분 테스트 결과' },
    liveChecks: {
      type: 'array',
      description: '바꾼 동작마다 실제 조회 1건',
      items: { type: 'object', properties: { command: { type: 'string' }, keyFields: { type: 'string', description: '응답의 핵심 필드만' } }, required: ['command', 'keyFields'] },
    },
    notDone: { type: 'array', items: { type: 'object', properties: { what: { type: 'string' }, why: { type: 'string' } }, required: ['what', 'why'] } },
    othersToTouch: { type: 'array', items: { type: 'string' }, description: '네 files 밖이라 고치지 않은 곳: "파일 — 고칠 내용" (문서, CHANGELOG, 감시 목록 GROUPS 등)' },
  },
  required: ['changed', 'checks', 'liveChecks', 'notDone', 'othersToTouch'],
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
  b.source === 'common'
    ? '실제 조회는 바꾼 동작을 볼 수 있는 소스 하나로 최소로 한다.'
    : `실제 조회는 ${b.source} 명령만 최소로 한다. 다른 소스는 다른 묶음이 부르고 있을 수 있다.`,
].join('\n')

// agent() 가 예외를 던져도 실패로 기록하고 이어 간다.
const tryAgent = async (prompt, opts) => {
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: 예외로 끝났다 (${String(e && e.message || e).slice(0, 120)})`); return null }
}

const results = Object.fromEntries(bundles.map(b => [b.name, { name: b.name, source: b.source, status: 'skipped', report: null }]))

// 한 줄 안에서는 차례로 돌리고, 앞 묶음이 실패하면 뒤 묶음은 그 결과에 기댈 수 있어 건너뛴다.
const runLane = async (lane, phaseTitle) => {
  for (const b of lane) {
    results[b.name].status = 'running'
    const r = await tryAgent(coderPrompt(b), {
      label: `구현:${b.name}`,
      phase: phaseTitle,
      agentType: 'jibsa-coder',
      model: MODELS.includes(b.model) ? b.model : 'sonnet',
      effort: EFFORTS.includes(b.effort) ? b.effort : 'high',
      schema: REPORT,
    })
    results[b.name] = { name: b.name, source: b.source, status: r ? 'done' : 'failed', report: r }
    if (!r) {
      log(`묶음 ${b.name}: 결과를 내지 못했다. 파일을 일부 고쳤을 수 있다. 같은 줄의 나머지 묶음은 건너뛴다`)
      return false
    }
  }
  return true
}

phase('공통 구현')
const common = bundles.filter(b => b.source === 'common')
const commonOk = common.length ? await runLane(common, '공통 구현') : true

let lanesOk = commonOk
if (commonOk) {
  phase('소스별 구현')
  const lanes = SOURCES.map(s => bundles.filter(b => b.source === s)).filter(l => l.length)
  const oks = await parallel(lanes.map(lane => () => runLane(lane, '소스별 구현')))
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
    ...list.map(r => `- ${r.name} (${r.source}): ${(r.report.changed || []).map(c => `${c.file} — ${c.what}`).join('; ')}`),
    '',
    '묶음들이 손대지 않고 넘긴 곳:',
    ...(othersToTouch.length ? othersToTouch.map(t => `- ${t}`) : ['- 없음']),
    '',
    '문서(docs/·AGENTS.md·CHANGELOG.md·README.md)만 고친다. scripts/·src/·tests/ 처럼 문서가 아닌 곳은 고치지 말고 보고에 남겨 주 에이전트에게 넘긴다.',
    '코드와 어긋나 보여 고치지 못한 것도 보고에 적는다.',
  ].join('\n'), {
    label: '문서',
    phase: '문서',
    agentType: 'jibsa-docs',
    model: MODELS.includes(docs.model) ? docs.model : 'opus',
    effort: EFFORTS.includes(docs.effort) ? docs.effort : 'high',
  })
  if (!docsReport) log('문서 작업자가 결과를 내지 못했다')
} else if (docs) {
  log('실패한 묶음이 있어 문서 단계를 건너뛰었다')
}

const done = list.filter(r => r.status === 'done').length
const needsAttention = list.filter(r => r.report && (r.report.notDone || []).length).map(r => r.name)
if (needsAttention.length) log(`못 한 것이 남은 묶음: ${needsAttention.join(', ')}`)
if (!docs && othersToTouch.length) log(`문서 단계가 없어 주 에이전트가 처리할 곳 ${othersToTouch.length}건`)
log(`묶음 ${done}/${list.length} 완료${docs ? `, 문서 ${docsReport ? '완료' : '안 함'}` : ''}. 최종 검증은 주 에이전트가 한다`)
return {
  started: true,
  allReturned: done === list.length && (!docs || Boolean(docsReport)),
  needsAttention,
  othersToTouch,
  bundles: list,
  docs: docsReport,
}
