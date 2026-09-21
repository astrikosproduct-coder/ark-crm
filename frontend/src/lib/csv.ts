/**
 * Build a CSV and hand it to the browser as a download.
 *
 * Every cell is quoted, and a cell starting with = + - @ is prefixed with an
 * apostrophe — free text written by users is opened in Excel, and a message
 * beginning "=HYPERLINK(" must stay text rather than run as a formula.
 */
export function toCsv(rows: (string | number | null | undefined)[][]): string {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          let text = cell === null || cell === undefined ? '' : String(cell)
          if (/^[=+\-@]/.test(text)) text = `'${text}`
          return `"${text.replace(/"/g, '""')}"`
        })
        .join(',')
    )
    .join('\r\n')
}

export function downloadCsv(filename: string, rows: (string | number | null | undefined)[][]): void {
  // BOM first, so Excel reads UTF-8 rather than mangling Arabic names and dashes.
  const blob = new Blob(['﻿', toCsv(rows)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
