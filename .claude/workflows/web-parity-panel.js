export const meta = {
  name: 'web-parity-panel',
  description: '소스마다 web-parity-investigator 하나를 동시에 돌려 jibsa 명령이 그 사이트 웹과 어긋나는지(A 어긋남·B 의도한 차이·C 같음·D 웹에만 있음) 조사한다. 읽기 전용',
  whenToUse: '/web-parity 명령이 소스가 둘 이상일 때 부른다. args.targets 에 [{source, scope}] 를 소스당 하나씩 넘긴다. args 없이 불렸으면 아무것도 띄우지 않고 /web-parity 를 쓰라고 안내한다.',
  phases: [
    { title: '조사', detail: '소스마다 조사원 하나, 동시에' },
  ],
}

const SOURCES = ['zigbang', 'naver', 'daangn', 'dabang']
const EFFORTS = ['high', 'xhigh']  // 브라우저 조작이 든 조사라 모델은 Opus 만 쓴다 (CLAUDE.md)

let a = args
if (typeof a === 'string') {
  try { a = JSON.parse(a) } catch { a = null }
}
const targets = a && Array.isArray(a.targets) ? a.targets : []
if (!targets.length) {
  log('조사할 소스(targets) 없이 불렸다. 아무것도 띄우지 않았다')
  return { started: false, next: '이 워크플로는 /web-parity 명령이 소스와 범위를 정해 부른다. 사용자에게 /web-parity 를 쓰라고 알리고, 직접 다시 부르지 않는다.' }
}
const bad = targets.filter(t => !t || !SOURCES.includes(t.source) || typeof t.scope !== 'string' || !t.scope.trim())
const names = targets.map(t => t && t.source)
const dup = names.filter((s, i) => names.indexOf(s) !== i)
if (bad.length || dup.length) {
  log(`targets 가 잘못됐다 (모르는 소스·빈 범위 ${bad.length}건, 겹친 소스: ${dup.join(', ') || '없음'}). 아무것도 띄우지 않았다`)
  return {
    started: false,
    reason: 'bad-targets',
    next: `targets 는 [{source, scope}] 이고 source 는 ${SOURCES.join('·')} 중 하나, 소스당 하나다 (실제 API 를 부르는 에이전트는 소스당 하나). 같은 소스의 범위는 한 scope 에 합쳐 다시 부른다.`,
  }
}

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          command: { type: 'string', description: '명령·옵션' },
          verdict: { type: 'string', enum: ['A', 'B', 'C', 'unconfirmed'] },
          web: { type: 'string', description: '웹 동작: API·파라미터·기본값과 캡처 근거' },
          jibsa: { type: 'string', description: 'jibsa 동작과 파일:줄' },
          reason: { type: 'string', description: '판정 이유 한두 문장' },
          documented: { type: 'boolean', description: 'B 일 때 그 소스 가이드 "웹과 다른 점" 에 이미 적혔는지' },
        },
        required: ['command', 'verdict', 'web', 'jibsa', 'reason'],
      },
    },
    webOnly: {
      type: 'array',
      description: 'D: 웹에는 있는데 jibsa 에 없는 기능 (로그인 없이 되는 것만)',
      items: { type: 'object', properties: { feature: { type: 'string' }, endpoint: { type: 'string' } }, required: ['feature', 'endpoint'] },
    },
    files: { type: 'array', items: { type: 'string' }, description: 'scratchpad 에 만든 캡처·작업 파일 경로' },
  },
  required: ['findings', 'webOnly', 'files'],
}

for (const t of targets) {
  if (t.model && t.model !== 'opus') log(`조사원 ${t.source}: 브라우저 조사라 ${t.model} 대신 opus 로 돌린다`)
  if (t.effort && !EFFORTS.includes(t.effort)) log(`조사원 ${t.source}: effort ${t.effort} 대신 xhigh 로 돌린다`)
}

// agent() 가 예외를 던져도 그 소스만 실패로 두고 이어 간다.
const tryAgent = async (prompt, opts) => {
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: 예외로 끝났다 (${String(e && e.message || e).slice(0, 120)})`); return null }
}

phase('조사')
const reports = await parallel(targets.map(t => () => tryAgent(
  [
    `조사할 소스: ${t.source}`,
    `범위: ${t.scope}`,
    '',
    '저장소 파일은 고치지 않는다. 작업 파일은 scratchpad 에만 만든다.',
    `다른 조사원이 다른 소스를 동시에 조사하고 있다. ${t.source} 사이트와 jibsa ${t.source} 명령만 부른다.`,
    '판정 기준·방법·요청 한도는 네 정의를 따른다. A 는 캡처나 실제 조회로 근거를 대고, 확인하지 못한 것은 unconfirmed 로 둔다.',
    'B 는 그 소스 가이드 "웹과 다른 점" 에 이미 적혔는지 documented 로 적는다. C 는 범위 안에서 확인한 것만 짧게 적는다.',
  ].join('\n'),
  {
    label: `조사:${t.source}`,
    phase: '조사',
    agentType: 'web-parity-investigator',
    model: 'opus',
    effort: EFFORTS.includes(t.effort) ? t.effort : 'xhigh',
    schema: FINDINGS,
  },
)))

const results = targets.map((t, i) => ({ source: t.source, scope: t.scope, ok: Boolean(reports[i]), ...(reports[i] || {}) }))
const failed = results.filter(r => !r.ok).map(r => r.source)
if (failed.length) log(`결과를 내지 못한 소스: ${failed.join(', ')}`)
const count = v => results.reduce((n, r) => n + (r.findings || []).filter(f => f.verdict === v).length, 0)
log(`A ${count('A')}, B ${count('B')}, C ${count('C')}, 미확인 ${count('unconfirmed')}, D ${results.reduce((n, r) => n + (r.webOnly || []).length, 0)}`)
return { started: true, failed, results }
