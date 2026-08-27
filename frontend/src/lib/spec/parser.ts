// Recursive-descent parser for the small expression language used by
// visibility_condition, condition, computed_expr and lookup_filter_expr.
//
// There is no eval() and no Function() anywhere in this file, and there must
// never be one: these strings come from the field register, which is edited by
// people who are not developers.

export type Node =
  | { k: 'num'; v: number }
  | { k: 'str'; v: string }
  | { k: 'bool'; v: boolean }
  | { k: 'null' }
  | { k: 'ident'; name: string }
  | { k: 'unary'; op: '!' | '-'; arg: Node }
  | { k: 'bin'; op: BinOp; l: Node; r: Node }
  | { k: 'cond'; test: Node; a: Node; b: Node }
  | { k: 'call'; name: string; args: Node[] }

export type BinOp =
  | '||'
  | '&&'
  | '=='
  | '!='
  | '<'
  | '<='
  | '>'
  | '>='
  | 'includes'
  | '+'
  | '-'
  | '*'
  | '/'

export class SpecExprError extends Error {
  readonly expr: string
  readonly where?: string

  constructor(message: string, expr: string, where?: string) {
    super(where ? `${message}\n  in: ${expr}\n  at: ${where}` : `${message}\n  in: ${expr}`)
    this.name = 'SpecExprError'
    this.expr = expr
    this.where = where
  }
}

// ---------------------------------------------------------------- tokeniser

type Tok =
  | { t: 'num'; v: number }
  | { t: 'str'; v: string }
  | { t: 'ident'; v: string }
  | { t: 'op'; v: string }
  | { t: 'end' }

// api_names in this register are not JS identifiers. They may start with a
// digit (3rd_party_one_time, 5_year_tco) and may contain an em-dash
// (guarantee_—_value). Anything more awkward than that — the single api_name
// containing a "+" — is reachable with backtick quoting.
// A dot is included in the run so that 1.5 lexes as one token. No api_name
// contains a dot and the language has no member access, so nothing else can
// claim it.
const IDENT_CHAR = /[A-Za-z0-9_—.]/
const NUMERIC = /^\d+(\.\d+)?$/

const SQUOTE = String.fromCharCode(39)
const DQUOTE = String.fromCharCode(34)
const BACKTICK = String.fromCharCode(96)

const OPERATORS = [
  '==',
  '!=',
  '<=',
  '>=',
  '&&',
  '||',
  '<',
  '>',
  '+',
  '-',
  '*',
  '/',
  '?',
  ':',
  '(',
  ')',
  ',',
  '!',
]

function tokenise(src: string): Tok[] {
  const out: Tok[] = []
  let i = 0

  while (i < src.length) {
    const c = src[i]

    if (/\s/.test(c)) {
      i++
      continue
    }

    // Backtick-quoted identifier: an escape hatch for api_names the bare
    // identifier rule cannot express, such as conversion_rate_to_stage_4+.
    if (c === BACKTICK) {
      const end = src.indexOf(BACKTICK, i + 1)
      if (end === -1) throw new SpecExprError('Unterminated backtick identifier', src, src.slice(i))
      out.push({ t: 'ident', v: src.slice(i + 1, end) })
      i = end + 1
      continue
    }

    if (c === SQUOTE || c === DQUOTE) {
      let j = i + 1
      let v = ''
      while (j < src.length && src[j] !== c) {
        if (src[j] === '\\' && j + 1 < src.length) {
          v += src[j + 1]
          j += 2
        } else {
          v += src[j]
          j++
        }
      }
      if (j >= src.length) throw new SpecExprError('Unterminated string', src, src.slice(i))
      out.push({ t: 'str', v })
      i = j + 1
      continue
    }

    if (IDENT_CHAR.test(c)) {
      let j = i
      while (j < src.length && IDENT_CHAR.test(src[j])) j++
      const word = src.slice(i, j)
      // A run that starts with a digit is a number only if the whole run is
      // numeric. "3" is a number; "3rd_party_one_time" is an identifier.
      out.push(NUMERIC.test(word) ? { t: 'num', v: Number(word) } : { t: 'ident', v: word })
      i = j
      continue
    }

    const op = OPERATORS.find((o) => src.startsWith(o, i))
    if (op) {
      out.push({ t: 'op', v: op })
      i += op.length
      continue
    }

    throw new SpecExprError(`Unexpected character ${JSON.stringify(c)}`, src, src.slice(i, i + 12))
  }

  out.push({ t: 'end' })
  return out
}

// ------------------------------------------------------------------- parser

function describe(t: Tok): string {
  if (t.t === 'end') return 'end of expression'
  return JSON.stringify(String((t as { v: unknown }).v))
}

// Lowest precedence first. Each level consumes the level below it:
//   ternary -> or -> and -> equality -> relational -> additive
//           -> multiplicative -> unary -> primary
export function parse(src: string): Node {
  const toks = tokenise(src)
  let p = 0

  const peek = () => toks[p]
  const atOp = (...vs: string[]) => {
    const t = toks[p]
    return t.t === 'op' && vs.includes(t.v)
  }
  const opValue = () => (toks[p] as { v: string }).v as BinOp
  const atWord = (v: string) => {
    const t = toks[p]
    return t.t === 'ident' && t.v === v
  }
  const eat = (v: string) => {
    if (!atOp(v)) {
      throw new SpecExprError(
        `Expected ${JSON.stringify(v)} but found ${describe(peek())}`,
        src
      )
    }
    p++
  }

  function ternary(): Node {
    const test = or()
    if (!atOp('?')) return test
    p++
    const a = ternary()
    eat(':')
    const b = ternary()
    return { k: 'cond', test, a, b }
  }

  function or(): Node {
    let l = and()
    while (atOp('||')) {
      p++
      l = { k: 'bin', op: '||', l, r: and() }
    }
    return l
  }

  function and(): Node {
    let l = equality()
    while (atOp('&&')) {
      p++
      l = { k: 'bin', op: '&&', l, r: equality() }
    }
    return l
  }

  function equality(): Node {
    let l = relational()
    while (atOp('==', '!=')) {
      const op = opValue()
      p++
      l = { k: 'bin', op, l, r: relational() }
    }
    return l
  }

  function relational(): Node {
    let l = additive()
    for (;;) {
      if (atOp('<', '<=', '>', '>=')) {
        const op = opValue()
        p++
        l = { k: 'bin', op, l, r: additive() }
      } else if (atWord('includes')) {
        p++
        l = { k: 'bin', op: 'includes', l, r: additive() }
      } else {
        return l
      }
    }
  }

  function additive(): Node {
    let l = multiplicative()
    while (atOp('+', '-')) {
      const op = opValue()
      p++
      l = { k: 'bin', op, l, r: multiplicative() }
    }
    return l
  }

  function multiplicative(): Node {
    let l = unary()
    while (atOp('*', '/')) {
      const op = opValue()
      p++
      l = { k: 'bin', op, l, r: unary() }
    }
    return l
  }

  function unary(): Node {
    if (atOp('!')) {
      p++
      return { k: 'unary', op: '!', arg: unary() }
    }
    if (atOp('-')) {
      p++
      return { k: 'unary', op: '-', arg: unary() }
    }
    return primary()
  }

  function primary(): Node {
    const t = peek()

    if (t.t === 'num') {
      p++
      return { k: 'num', v: t.v }
    }
    if (t.t === 'str') {
      p++
      return { k: 'str', v: t.v }
    }
    if (t.t === 'ident') {
      p++
      if (t.v === 'true') return { k: 'bool', v: true }
      if (t.v === 'false') return { k: 'bool', v: false }
      if (t.v === 'null') return { k: 'null' }

      if (atOp('(')) {
        p++
        const args: Node[] = []
        if (!atOp(')')) {
          args.push(ternary())
          while (atOp(',')) {
            p++
            args.push(ternary())
          }
        }
        eat(')')
        return { k: 'call', name: t.v, args }
      }
      return { k: 'ident', name: t.v }
    }
    if (t.t === 'op' && t.v === '(') {
      p++
      const inner = ternary()
      eat(')')
      return inner
    }

    throw new SpecExprError(`Unexpected token ${describe(t)}`, src)
  }

  const ast = ternary()
  if (peek().t !== 'end') {
    throw new SpecExprError(`Unexpected trailing input ${describe(peek())}`, src)
  }
  return ast
}

// Every bare identifier the expression reads. sum()'s first two arguments name
// a child collection and a column inside it, so they are not fields of the
// module and are skipped here.
export function identifiersOf(node: Node): string[] {
  const found = new Set<string>()

  const walk = (n: Node) => {
    switch (n.k) {
      case 'ident':
        found.add(n.name)
        break
      case 'unary':
        walk(n.arg)
        break
      case 'bin':
        walk(n.l)
        walk(n.r)
        break
      case 'cond':
        walk(n.test)
        walk(n.a)
        walk(n.b)
        break
      case 'call':
        // sum(lines, net_line_total, filter) — args 0 and 1 name things inside
        // the child collection, and arg 2 is evaluated in the child row's
        // scope, so none of them are fields of this module.
        if (n.name !== 'sum') n.args.forEach(walk)
        break
      default:
        break
    }
  }

  walk(node)
  return [...found]
}
