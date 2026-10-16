import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorNotice, Notice } from '@/components/ui/notice'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { currencySign, money } from '@/lib/format'
import {
  EDITIONS_MODULE,
  PRICE_BOOKS_MODULE,
  PRICES_MODULE,
  useEditions,
  usePriceBooks,
  usePriceGrid,
  useSavePrices,
  type CellChange,
  type PriceCell,
  type PriceRow,
  type PriceShape,
} from '@/lib/priceBooks'
import { fieldOf, labelForValue } from '@/lib/spec'
import { useUnsavedChangesStore } from '@/store/useUnsavedChangesStore'
import { cn } from '@/lib/utils'

const PRODUCTS = 'products'

/** A percentage as people type it: 0.18 is "18". Rounded so 0.28 is not 28.000000000000004. */
const asPercent = (fraction: number) => Math.round(fraction * 1_000_000) / 10_000
const asFraction = (percent: number) => Math.round(percent * 10_000) / 1_000_000

const keyOf = (product: string, size: string | null) => `${product}|${size ?? ''}`

/** What was typed, as a number — or null for an emptied box, undefined for something that is not one. */
function parse(text: string): number | null | undefined {
  const trimmed = text.replace(/,/g, '').trim()
  if (trimmed === '') return null
  const n = Number(trimmed)
  return Number.isFinite(n) && n >= 0 ? n : undefined
}

interface Props {
  /**
   * The book whose prices these are — a price book's own Prices tab. Left out
   * (an edition's Prices tab), the reader chooses the book, starting from the
   * Standard one.
   */
  bookId?: string
  /**
   * The edition these prices are in — an edition's own Prices tab. Left out
   * (a price book's Prices tab), the reader chooses, starting from the edition
   * in use.
   */
  editionId?: string
  /**
   * Draw the boxes. PRICES ARE CHANGED IN ONE PLACE (decided 13 Oct 2026):
   * Price Books -> Editions -> an edition -> Prices. A price book's own Prices
   * tab passes false and is read-only whoever is looking. Presentation only —
   * the server refuses a save it would not allow, whatever is drawn.
   */
  canEdit: boolean
  /** On a read-only grid: point someone who MAY change prices at the edition's page. */
  editHint?: boolean
}

/**
 * Every product's price in one book and one edition — the price book as a
 * grid, the way the pricing workbook lays it out: products down, sizes across.
 *
 * Three tables, because a price has one of three shapes (the product's Pricing
 * Basis decides, on the server): a price per size; one price whatever the
 * size; a percentage of the licence. Every heading is the register's, and each
 * money column says the currency its figures are in.
 *
 * What may be typed into is the server's answer, not this component's guess:
 * `can_change` (a draft edition) and `can_add` (the edition in use takes a
 * first price, in the Standard book). In a regional book a box left empty
 * shows the price worked out from the Standard one; typing gives the book a
 * price of its own, and emptying it goes back.
 */
export function PriceGrid({ bookId, editionId, canEdit, editHint }: Props) {
  const editions = useEditions()
  const books = usePriceBooks()
  const [chosenEdition, setChosenEdition] = useState<string | undefined>()
  const [chosenBook, setChosenBook] = useState<string | undefined>()
  const book = bookId ?? chosenBook ?? books.data?.find((b) => b.is_standard)?.id
  const grid = usePriceGrid(book, editionId ?? chosenEdition)
  const save = useSavePrices()
  const [typed, setTyped] = useState<Record<string, string>>({})

  const data = grid.data
  const formId = `price-grid:${bookId ?? ''}:${editionId ?? ''}`
  const dirty = Object.keys(typed).length > 0
  const setFormDirty = useUnsavedChangesStore((s) => s.setFormDirty)
  useEffect(() => {
    setFormDirty(formId, dirty)
    return () => setFormDirty(formId, false)
  }, [formId, dirty, setFormDirty])

  // Another edition, another book: what was typed belonged to the old one.
  useEffect(() => setTyped({}), [data?.price_book, data?.edition])

  const statusLabel = (status: string) => labelForValue(fieldOf(EDITIONS_MODULE, 'status')?.picklist, status) || status

  /** May this box be typed into? The server's rules, read off what it sent. */
  const open = (row: PriceRow, cell: PriceCell) => {
    if (!canEdit || !data) return false
    if (row.shape === 'percent' && !data.is_standard) return false
    if (data.can_change) return true
    return data.can_add && cell.price === null
  }

  /** The value a box starts from: the book's own price, shown as typed. */
  const held = (row: PriceRow, cell: PriceCell): string => {
    if (!cell.own || cell.price === null) return ''
    return String(row.shape === 'percent' ? asPercent(cell.price) : cell.price)
  }

  const changes = useMemo(() => {
    const out: CellChange[] = []
    let invalid = 0
    for (const row of data?.rows ?? []) {
      for (const cell of row.cells) {
        const text = typed[keyOf(row.product, cell.size)]
        if (text === undefined) continue
        const value = parse(text)
        if (value === undefined) {
          invalid += 1
          continue
        }
        const before = cell.own ? cell.price : null
        const after = value === null ? null : row.shape === 'percent' ? asFraction(value) : value
        if (before !== after) out.push({ product: row.product, size: cell.size, value: after })
      }
    }
    return { cells: out, invalid }
  }, [data, typed])

  if (grid.isLoading || (!book && books.isLoading)) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>
  if (!book) return <p className="py-6 text-sm text-muted-foreground">There is no Standard price book yet.</p>
  if (grid.isError || !data) return <ErrorNotice className="my-3" error={grid.error} fallback="The prices couldn't be loaded. Try again." />

  const submit = () => {
    if (changes.invalid > 0 || changes.cells.length === 0) return
    save.mutate({ book: data.price_book, edition: data.edition, cells: changes.cells }, { onSuccess: () => setTyped({}) })
  }

  const byShape = (shape: PriceShape) => data.rows.filter((r) => r.shape === shape)
  const category = fieldOf(PRODUCTS, 'catalogue_category')
  const unit = fieldOf(PRODUCTS, 'unit_of_measure')
  // "$" for USD, "₹" for INR, the code itself where a currency has no sign (AED).
  const sign = currencySign(data.currency)
  const inCurrency = (label: string) => (sign ? `${label} (${sign})` : label)
  // The Standard book's price field already names its currency: "List Price (USA USD)".
  const priceLabel = data.is_standard ? (fieldOf(PRICES_MODULE, 'list_price_usa_usd')?.label ?? 'List Price') : inCurrency('Price')
  const pctLabel = fieldOf(PRICES_MODULE, 'pct_of_annual_licence')?.label ?? '% of Annual Licence'
  const standardLabel = fieldOf(PRICE_BOOKS_MODULE, 'is_standard')?.label ?? 'Standard Price Book'

  const box = (row: PriceRow, cell: PriceCell) => {
    const key = keyOf(row.product, cell.size)
    const percent = row.shape === 'percent'
    const shown = cell.price === null ? '' : percent ? `${asPercent(cell.price)}%` : money(cell.price)
    if (!open(row, cell)) {
      return (
        <span
          className={cn('tabular-nums', !cell.own && cell.price !== null && 'text-muted-foreground')}
          title={!cell.own && cell.price !== null && !data.is_standard ? 'Worked out from the Standard price' : undefined}
        >
          {shown || <span className="text-muted-foreground">—</span>}
        </span>
      )
    }
    const text = typed[key]
    const value = text ?? held(row, cell)
    // A regional box left empty shows the worked-out price it stands for.
    const placeholder = !cell.own && cell.price !== null ? (percent ? String(asPercent(cell.price)) : money(cell.price)) : ''
    return (
      <Input
        inputMode="decimal"
        aria-label={`${row.item_name}${cell.size ? ` at ${data.sizes.find((s) => s.id === cell.size)?.size_code ?? ''}` : ''}`}
        aria-invalid={text !== undefined && parse(text) === undefined}
        className={cn('ml-auto h-8 w-28 px-2 text-right tabular-nums', text !== undefined && 'border-ring')}
        value={value}
        placeholder={placeholder}
        onChange={(e) =>
          setTyped((current) => {
            const next = { ...current }
            // Back to what the box held: not a change any more.
            if (e.target.value === held(row, cell)) delete next[key]
            else next[key] = e.target.value
            return next
          })
        }
      />
    )
  }

  /** The two columns every table opens with: the product, and its SKU Code in a column of its own. */
  const product = (row: PriceRow) => (
    <>
      <td className="px-3 py-1.5">
        <Link className={cn('underline-offset-2 hover:underline', !row.active && 'text-muted-foreground')} to={`/products/${row.product}`}>
          {row.item_name}
        </Link>
        {!row.active && <span className="text-muted-foreground ml-2 text-xs">Inactive</span>}
      </td>
      <td className="text-muted-foreground px-3 py-1.5 whitespace-nowrap">{row.sku_code}</td>
    </>
  )

  const head = 'px-3 py-2 font-medium'
  const table = (title: string, rows: PriceRow[], columns: { label: string; numeric?: boolean }[], cells: (row: PriceRow) => ReactNode) =>
    rows.length === 0 ? null : (
      <section className="space-y-1.5">
        <h3 className="text-sm font-medium">{title}</h3>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className={cn(head, 'text-left')}>{fieldOf(PRODUCTS, 'item_name')?.label ?? 'Item Name'}</th>
                <th className={cn(head, 'text-left')}>{fieldOf(PRODUCTS, 'sku_code')?.label ?? 'SKU Code'}</th>
                <th className={cn(head, 'text-left')}>{category?.label ?? 'Category'}</th>
                {columns.map((c) => (
                  <th key={c.label} className={cn(head, 'whitespace-nowrap', c.numeric ? 'text-right' : 'text-left')}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((row) => (
                <tr key={row.product}>
                  {product(row)}
                  <td className="text-muted-foreground px-3 py-1.5">{labelForValue(category?.picklist, row.catalogue_category)}</td>
                  {cells(row)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    )

  const lead =
    data.edition_status === 'DRAFT'
      ? `${data.edition_name} is a draft. Nothing is sold from it yet.`
      : data.edition_status === 'CURRENT'
        ? `${data.edition_name} is the edition in use.`
        : `${data.edition_name} is a past edition.`
  // What can be done here — said only where something can.
  const bullets = !canEdit
    ? []
    : data.edition_status === 'DRAFT'
      ? [
          data.is_standard ? 'Change any price, then save.' : 'Type a price to give this book its own. Empty the box to go back to the worked-out price.',
          'Make the edition current when its prices are ready.',
        ]
      : data.edition_status === 'CURRENT'
        ? [
            data.is_standard ? 'A product with no price can be given one here.' : 'This book’s prices follow the Standard book and its rate.',
            'To change a price, start a new edition and change it there.',
          ]
        : ['Its prices are kept as they were and can’t be changed.']

  const picker = 'h-8 w-64'
  return (
    <div className="space-y-3 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            {!bookId && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Price book</span>
                <Select value={data.price_book} onValueChange={setChosenBook} disabled={dirty}>
                  <SelectTrigger className={picker}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(books.data ?? []).map((b) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.price_book_name}
                        {b.is_standard ? ` · ${standardLabel}` : ''}
                        {b.active ? '' : ' · Inactive'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {!editionId && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Edition</span>
                <Select value={data.edition} onValueChange={setChosenEdition} disabled={dirty}>
                  <SelectTrigger className={picker}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(editions.data ?? []).map((e) => (
                      <SelectItem key={e.id} value={e.id}>
                        {e.price_book_version} · {statusLabel(e.status)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          <Notice lead={lead} bullets={bullets} />
          {!canEdit && editHint && (
            <p className="text-sm">
              Prices are changed on the edition’s own page:{' '}
              <Link className="text-primary underline-offset-2 hover:underline" to={`/price_books/editions/${data.edition}`}>
                open {data.edition_name}
              </Link>
              .
            </p>
          )}
          {!data.is_standard && (
            <p className="text-muted-foreground text-sm">
              Prices in {data.currency}: the Standard price × {data.multiplier.toLocaleString('en-US', { maximumFractionDigits: 6 })}, unless
              this book has a price of its own.
            </p>
          )}
        </div>
        {canEdit && (data.can_change || data.can_add) && (
          <div className="flex items-center gap-2">
            {dirty && (
              <Button type="button" variant="outline" size="sm" onClick={() => setTyped({})} disabled={save.isPending}>
                Discard
              </Button>
            )}
            <Button type="button" size="sm" onClick={submit} disabled={save.isPending || changes.cells.length === 0 || changes.invalid > 0}>
              {save.isPending
                ? 'Saving…'
                : changes.cells.length > 0
                  ? `Save ${changes.cells.length} ${changes.cells.length === 1 ? 'price' : 'prices'}`
                  : 'Save prices'}
            </Button>
          </div>
        )}
      </div>

      {changes.invalid > 0 && (
        <p className="text-sm text-destructive">
          {changes.invalid} {changes.invalid === 1 ? 'price is' : 'prices are'} not a number. Each is marked below.
        </p>
      )}
      {save.isError && <ErrorNotice error={save.error} fallback="The prices weren't saved. Try again." />}

      {table(
        'Priced by size',
        byShape('sized'),
        data.sizes.map((s) => ({ label: inCurrency(s.size_code), numeric: true })),
        (row) =>
          data.sizes.map((s) => {
            const cell = row.cells.find((c) => c.size === s.id) ?? { size: s.id, standard: null, price: null, own: false }
            return (
              <td key={s.id} className="px-3 py-1.5 text-right">
                {box(row, cell)}
              </td>
            )
          })
      )}
      {table(
        'One price, whatever the size',
        byShape('single'),
        [{ label: unit?.label ?? 'Unit of Measure' }, { label: priceLabel, numeric: true }],
        (row) => (
          <>
            <td className="text-muted-foreground px-3 py-1.5">{labelForValue(unit?.picklist, row.unit_of_measure)}</td>
            <td className="px-3 py-1.5 text-right">{box(row, row.cells[0])}</td>
          </>
        )
      )}
      {table('A percentage of the licence', byShape('percent'), [{ label: pctLabel, numeric: true }], (row) => (
        <td className="px-3 py-1.5 text-right">{box(row, row.cells[0])}</td>
      ))}
      {data.rows.length === 0 && <p className="text-sm text-muted-foreground">There are no products yet.</p>}
    </div>
  )
}
