export const meta = {
  name: 'review-panel',
  description: 'jibsa 변경을 관점 묶음별 리뷰어로 리뷰하고, 모은 지적을 소스마다 review-verifier 하나가 실제 조회로 재현해 진짜 문제·오탐으로 가른다',
  whenToUse: '/review 명령이 부른다 (docs/development/agents.md "코드 리뷰"). args: target(리뷰 대상과 diff 를 보는 명령), groups(관점 키 묶음의 목록), 그 밖은 선택. args 없이 불렸으면 아무것도 띄우지 않고 /review 를 쓰라고 안내한다.',
  phases: [
    { title: '리뷰', detail: '관점 묶음마다 리뷰어 하나, 동시에. 코드만 읽는다' },
    { title: '재검증', detail: '소스마다 review-verifier 하나가 지적을 실제 조회로 재현한다. 공통 코드 지적은 소스별 검증이 끝난 뒤' },
  ],
}

// 관점 다섯 가지 (docs/development/agents.md "코드 리뷰" 1단계). /review 는 이 키로 묶음을 정해 넘긴다.
const PERSPECTIVES = {
  convention: '규약 위반: AGENTS.md "꼭 지킬 것" (로그인 없는 기능만, 금액은 만원, 결과는 stdout JSON·에러는 stderr JSON, 만료 매물 제외, 서버가 거른 결과를 같은 조건으로 다시 거르지 않기, 소스끼리 import 금지, 모든 요청은 브라우저 transport 와 요청 제한 훅, 사진·중개사 연락처·본문·매물 좌표 출력 금지)와 docs/development/code-style.md.',
  correctness: '정확성·버그: 잘못된 분기, 누락값 규칙(해당 없음은 키 삭제·모름은 null·비어 있음은 []), 단위 환산(만원), 이어 받기(--next) 커서·offset.',
  contract: '출력 계약: docs/development/output-contract.md 와 docs/<source>.md 의 필드·에러 코드·exit code 와 코드가 맞는지, 바뀐 동작이 문서에 반영됐는지.',
  web: '웹 대응: docs/development/provider-conventions.md "웹 화면과의 대응" 의 "안 되는 것" 에 해당하는 결과를 만드는지 ("되는 것" 에 든 예외는 위반이 아니다), 웹과 다르게 한 곳이 그 소스 가이드 "웹과 다른 점" 에 적혔는지. 두 목록은 그 문서에서 읽는다.',
  requests: '요청 수·차단 위험: 매물마다 추가 조회처럼 요청을 늘리는 변경, 요청 제한 훅을 거치지 않는 요청, 재시도가 요청을 불리는 곳, 네이버 차단 위험.',
}
const SOURCES = ['zigbang', 'naver', 'daangn', 'dabang']
const MODELS = ['sonnet', 'opus']  // Haiku 는 쓰지 않는다 (CLAUDE.md)
const EFFORTS = ['high', 'xhigh']
const CHUNK = 10  // 검증자 한 명이 한 번에 받는 지적 수. 넘치면 같은 소스 안에서 차례로 나눈다
// 리뷰 오탐 (2026-11-13): 검증 요청의 총량 상한이 없어 네이버 요청이 몰린다는 지적. 같은 소스의 검증자는 차례로만 돌고,
// jibsa 요청 제한기가 프로세스 간 공유 상태로 소스별 속도를 막아(네이버 1초 간격·분당 60회, `jibsa limits`) 몰리지 않는다.

let a = args
if (typeof a === 'string') {
  try { a = JSON.parse(a) } catch { a = null }
}
if (!a || typeof a !== 'object' || typeof a.target !== 'string' || !a.target.trim() || !Array.isArray(a.groups) || a.groups.length === 0) {
  log('리뷰 대상(target)과 관점 묶음(groups) 없이 불렸다. 아무것도 띄우지 않았다')
  return {
    started: false,
    next: '이 워크플로는 /review 명령이 변경 크기를 보고 대상과 관점 묶음을 정해 부른다. 사용자에게 /review 를 쓰라고 알리고, 직접 다시 부르지 않는다.',
  }
}

const groups = a.groups.map(g => (Array.isArray(g) ? g : g && Array.isArray(g.perspectives) ? g.perspectives : []))
const keys = groups.flat()
const unknown = keys.filter(k => typeof k !== 'string' || !Object.hasOwn(PERSPECTIVES, k))
const repeated = keys.filter((k, i) => keys.indexOf(k) !== i)
if (groups.some(g => g.length === 0) || unknown.length || repeated.length) {
  log(`관점 묶음이 잘못됐다 (빈 묶음, 모르는 키: ${unknown.join(', ') || '없음'}, 두 번 들어간 키: ${repeated.join(', ') || '없음'}). 아무것도 띄우지 않았다`)
  return { started: false, reason: 'bad-groups', next: `groups 는 ${Object.keys(PERSPECTIVES).join('·')} 키를 한 번씩만 넣은 묶음의 목록이다. 고쳐서 다시 부른다.` }
}
const covered = new Set(groups.flat())
const missing = Object.keys(PERSPECTIVES).filter(k => !covered.has(k))
if (missing.length) log(`빠진 관점: ${missing.join(', ')} — 이 관점은 리뷰하지 않는다`)

let reviewerModel = a.reviewerModel || 'sonnet'
if (!MODELS.includes(reviewerModel)) {
  log(`리뷰어: 쓰지 않는 모델(${reviewerModel})이라 sonnet 으로 돌린다`)
  reviewerModel = 'sonnet'
}
const reviewerEffort = EFFORTS.includes(a.reviewerEffort) ? a.reviewerEffort : 'high'
if (a.reviewerEffort && reviewerEffort !== a.reviewerEffort) log(`리뷰어: effort ${a.reviewerEffort} 대신 high 로 돌린다`)

// agent() 가 예외를 던져도 그 에이전트만 실패로 두고 이어 간다.
const tryAgent = async (prompt, opts) => {
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: 예외로 끝났다 (${String(e && e.message || e).slice(0, 120)})`); return null }
}
const verify = a.verify !== false
const date = typeof a.date === 'string' && a.date ? a.date : 'YYYY-MM-DD'

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string', description: '한 줄 요지' },
          file: { type: 'string', description: '저장소 기준 경로' },
          line: { type: 'integer' },
          source: { type: 'string', enum: [...SOURCES, 'common'], description: '지적이 걸린 소스. 소스에 매이지 않은 공통 코드면 common' },
          perspective: { type: 'string', enum: Object.keys(PERSPECTIVES) },
          problem: { type: 'string', description: '무엇이 틀리는지' },
          scenario: { type: 'string', description: '어떤 입력·상태에서 드러나는지. 재현할 jibsa 명령이 있으면 그 명령' },
        },
        required: ['title', 'file', 'line', 'source', 'perspective', 'problem', 'scenario'],
      },
    },
  },
  required: ['findings'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['real', 'false_positive', 'impossible', 'unconfirmed', 'duplicate'] },
          evidence: { type: 'string', description: '재현한 명령, 응답의 핵심 필드, 파일:줄' },
          note: { type: 'string', description: '오탐이면 남길 자리와 문장, 미확인이면 더 볼 것' },
          duplicate_of: { type: 'string', description: 'duplicate 이면 같은 문제를 가리키는 지적 id' },
        },
        required: ['id', 'verdict', 'evidence'],
      },
    },
  },
  required: ['results'],
}

phase('리뷰')
const reviews = await parallel(groups.map(group => () => tryAgent(
  [
    `리뷰 대상: ${a.target}`,
    '',
    '이 관점만 본다:',
    ...group.map(k => `- ${PERSPECTIVES[k]}`),
    '',
    '지적이 없으면 빈 목록을 낸다.',
  ].join('\n'),
  { label: `리뷰:${group.join('+')}`, phase: '리뷰', agentType: 'jibsa-reviewer', model: reviewerModel, effort: reviewerEffort, schema: FINDINGS },
)))

const failedReviewers = groups.filter((_, i) => !reviews[i]).map(group => group.join('+'))
if (failedReviewers.length) log(`리뷰어가 결과를 내지 못한 묶음: ${failedReviewers.join(', ')} — 이 관점은 리뷰되지 않았다`)

// 소스는 파일 경로로 정한다. 리뷰어마다 같은 파일에 다른 소스를 붙여도 같은 검증자에게 가게 하려는 것이다.
// 경로로 정할 수 없는 파일(core/·docs/common.md 등)만 리뷰어가 붙인 값을 쓴다.
const PATH_SOURCE = [
  /^src\/jibsa\/providers\/([a-z]+)\//,
  /^src\/jibsa\/cli\/([a-z]+)\.py$/,
  /^docs\/development\/providers\/([a-z]+)\.md$/,
  /^docs\/([a-z]+)\.md$/,
  /^tests\/test_([a-z]+)\.py$/,
  /^tests\/fixtures\/([a-z]+)\//,
]
const sourceOf = f => {
  const path = String(f.file).trim().replace(/^(\.\/)+/, '')
  for (const re of PATH_SOURCE) {
    const m = path.match(re)
    if (m && SOURCES.includes(m[1])) return m[1]
  }
  return f.source
}

// 지적은 합치지 않고 하나씩 판정받는다. 합치면 뒤 지적의 재현 단서가 빠지고, 다른 문제가 판정 하나에 묻힌다.
// 파일·줄 순으로 늘어놓고 소스를 경로로 정해 같은 파일의 지적이 같은 검증자에게 가게 하고(묶음 경계에서도 같은 파일·줄은
// 자르지 않는다), 같은 문제는 검증자가 duplicate 로 묶는다. 그래도 남은 중복은 주 에이전트가 보고할 때 묶는다 (/review 4단계).
// 모든 리뷰어의 결과가 있어야 늘어놓을 수 있어 여기서 기다린다.
const found = reviews.filter(Boolean).flatMap(r => r.findings)
  .sort((x, y) => x.file.localeCompare(y.file) || x.line - y.line)
  .map((f, i) => ({ id: `F${i + 1}`, title: f.title, file: f.file, line: f.line, source: sourceOf(f), perspectives: [f.perspective], problem: f.problem, scenario: f.scenario }))
log(`지적 ${found.length}건 (리뷰어 ${groups.length}명)`)

// ok 가 false 면 리뷰가 덜 된 것이다: 지적 0건이어도 깨끗한 리뷰가 아니다.
const base = { started: true, ok: failedReviewers.length === 0, reviewers: groups.length, missingPerspectives: missing, failedReviewers, findings: found.length }
if (!found.length) return { ...base, real: [], falsePositive: [], unconfirmed: [], impossible: [], duplicate: [] }
if (!verify) {
  log('재검증은 건너뛴다 (verify: false). 주 에이전트가 직접 재현한다')
  return { ...base, verified: false, items: found }
}

phase('재검증')
const bySource = {}
for (const f of found) (bySource[f.source] ||= []).push(f)

const verifyPrompt = (source, items) => [
  '아래 리뷰 지적을 하나씩 실제로 재현해 판정한다. 저장소 파일은 고치지 않는다.',
  `리뷰 대상: ${a.target}`,
  source === 'common'
    ? '공통 코드 지적이다. 재현에 API 가 필요하면 소스 하나를 골라 최소로 부른다. 네이버는 차단 위험이 커서 다른 소스로 재현할 수 없을 때만 고른다. 소스별 검증은 끝났다.'
    : `${source} 의 실제 API 만 부른다. 다른 검증자가 다른 소스를 동시에 부르고 있다.`,
  '요청은 지적당 1~2회로 아낀다 (네이버는 특히). RATE_LIMITED 면 오래 기다리지 말고 미확인으로 둔다.',
  'jibsa 동작과 상관없는 지적(문서·설정·스크립트 문장끼리 어긋남 등)은 API 를 부르지 않고 원문을 대조해 판정한다.',
  '판정: real(재현됨) / false_positive(코드는 맞는데 그렇게 보임) / impossible(응답에 없는 값, 요청 모델이 막는 입력 등) / unconfirmed(재현도 반박도 못 함) / duplicate(다른 지적과 같은 문제).',
  '지적은 파일·줄 순이다. 이웃한 지적이 같은 문제를 가리키면 하나만 판정하고 나머지는 duplicate 로 두어 duplicate_of 에 그 id 를 적는다. 같은 줄이라도 문제가 다르면 따로 판정한다.',
  `오탐이면 note 에 남길 자리와 문장을 제안한다: 웹과의 차이면 그 소스 가이드 "웹과 다른 점", 그 밖은 코드 자리의 \`# 리뷰 오탐 (${date}): 이유\` 주석. 이미 적혀 있으면 그 위치를 댄다.`,
  '',
  '지적:',
  ...items.map(f => `${f.id} [${f.file}:${f.line}] (${f.perspectives.join('+')}) ${f.title}\n  문제: ${f.problem}\n  상황: ${f.scenario}`),
].join('\n')

// 검증자 한 명에게 줄 묶음. CHUNK 건씩 나누되, 같은 파일·줄의 지적은 경계에서 자르지 않고 앞 묶음에 함께 넣는다.
const chunksOf = items => {
  const chunks = []
  for (const f of items) {
    const last = chunks[chunks.length - 1]
    const prev = last && last[last.length - 1]
    if (last && (last.length < CHUNK || (prev.file === f.file && prev.line === f.line))) last.push(f)
    else chunks.push([f])
  }
  return chunks
}

// 같은 소스의 실제 API 를 동시에 부르지 않는다: 소스 안에서는 차례로, 소스끼리는 동시에, 공통 코드는 마지막에.
const verifySource = async source => {
  const chunks = chunksOf(bySource[source])
  const out = []
  for (const [i, chunk] of chunks.entries()) {
    const r = await tryAgent(verifyPrompt(source, chunk), {
      label: `재검증:${source}${chunks.length > 1 ? `#${i + 1}` : ''}`,
      phase: '재검증', agentType: 'review-verifier', model: 'sonnet', effort: 'high', schema: VERDICTS,
    })
    if (r) out.push(...r.results)
    else log(`검증자 ${source}: 결과를 내지 못했다 (${chunk.map(f => f.id).join(', ')}, 미확인으로 둔다)`)
  }
  return out
}
const verdicts = (await parallel(Object.keys(bySource).filter(s => s !== 'common').map(s => () => verifySource(s)))).filter(Boolean).flat()
if (bySource.common) verdicts.push(...await verifySource('common'))

const byId = Object.fromEntries(verdicts.map(v => [v.id, v]))
// 중복은 가리키는 지적이 있고 그 지적이 중복이 아닐 때만 인정한다 (서로 가리켜 둘 다 사라지지 않게).
const isDuplicate = v => v.verdict === 'duplicate' && byId[v.duplicate_of] && byId[v.duplicate_of].verdict !== 'duplicate'
// 일어날 수 없음·중복도 근거와 함께 돌려준다. 사용자에게는 보여 주지 않지만 주 에이전트가 잘못 갈린 것이 없는지 훑는다.
const result = { ...base, verified: true, real: [], falsePositive: [], unconfirmed: [], impossible: [], duplicate: [] }
for (const f of found) {
  const v = byId[f.id]
  const item = { ...f, evidence: v ? v.evidence : '검증 결과 없음', note: v && v.note ? v.note : '' }
  if (!v || v.verdict === 'unconfirmed') result.unconfirmed.push(item)
  else if (v.verdict === 'real') result.real.push(item)
  else if (v.verdict === 'false_positive') result.falsePositive.push(item)
  else if (v.verdict === 'impossible') result.impossible.push(item)
  else if (isDuplicate(v)) result.duplicate.push({ ...item, duplicateOf: v.duplicate_of })
  else result.unconfirmed.push({ ...item, note: `중복이라 했지만 가리킨 지적(${v.duplicate_of || '없음'})이 없거나 그것도 중복이다` })
}
log(`진짜 문제 ${result.real.length}, 오탐 ${result.falsePositive.length}, 미확인 ${result.unconfirmed.length}, 일어날 수 없음 ${result.impossible.length}, 중복 ${result.duplicate.length}`)
return result
