import React, { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Check, Copy } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TableBlock, TableColumn } from '../../types'
import { formatNumber, tableToCsv } from '../lib/chartFormat'
import { UiCard, UiCardAction } from './UiCard'

interface Props {
  block: TableBlock
}

const COLLAPSED_ROW_LIMIT = 10

export function TableCard({ block }: Props) {
  const { t, i18n } = useTranslation()
  const { title, columns, rows, sort } = block
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [sortKey, setSortKey] = useState<string>(sort?.key || '')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(sort?.dir || 'asc')
  const locale = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  const colMap = useMemo(() => {
    const map = new Map<string, TableColumn>()
    for (const c of columns) {
      map.set(c.key, c)
    }
    return map
  }, [columns])

  const sortedRows = useMemo(() => {
    if (!sortKey || !colMap.has(sortKey)) return rows
    const col = colMap.get(sortKey)!
    const copy = [...rows]

    copy.sort((a, b) => {
      const valA = a[sortKey]
      const valB = b[sortKey]

      if (valA === null || valA === undefined) return 1
      if (valB === null || valB === undefined) return -1

      let cmp = 0
      if (col.kind === 'number') {
        const numA = typeof valA === 'number' ? valA : Number(valA)
        const numB = typeof valB === 'number' ? valB : Number(valB)
        cmp = numA - numB
      } else if (col.kind === 'date') {
        cmp = String(valA).localeCompare(String(valB))
      } else {
        cmp = String(valA).localeCompare(String(valB), locale, { numeric: true, sensitivity: 'base' })
      }

      return sortDir === 'desc' ? -cmp : cmp
    })

    return copy
  }, [rows, sortKey, sortDir, colMap, locale])

  const visibleRows = useMemo(() => {
    if (sortedRows.length <= COLLAPSED_ROW_LIMIT || expanded) {
      return sortedRows
    }
    return sortedRows.slice(0, COLLAPSED_ROW_LIMIT)
  }, [sortedRows, expanded])

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const handleCopy = async () => {
    const csv = tableToCsv(columns, rows)
    try {
      await navigator.clipboard.writeText(csv)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard indisponível */
    }
  }

  const renderCell = (col: TableColumn, val: unknown) => {
    if (val === null || val === undefined || val === '') {
      return <span className="nexus-ui-table__empty">—</span>
    }

    if (col.kind === 'number') {
      const num = typeof val === 'number' ? val : Number(val)
      if (!Number.isFinite(num)) {
        return <span className="nexus-ui-table__empty">—</span>
      }
      const formatted = formatNumber(num, locale, false)
      return (
        <span className="nexus-ui-table__num-wrap">
          <span className="nexus-ui-table__num">{formatted}</span>
          {col.unit && <span className="nexus-ui-table__unit">{col.unit}</span>}
        </span>
      )
    }

    return String(val)
  }

  const hasExpandToggle = rows.length > COLLAPSED_ROW_LIMIT

  return (
    <UiCard
      title={title || t('intelligentUi.tableTitle', 'Tabela')}
      actions={
        <UiCardAction
          icon={copied ? <Check size={14} /> : <Copy size={14} />}
          label={t('intelligentUi.copyData') || 'Copiar dados'}
          pressedLabel={t('intelligentUi.copied') || 'Copiado'}
          pressed={copied}
          onClick={handleCopy}
          hideLabel
        />
      }
      footer={
        hasExpandToggle ? (
          <div className="nexus-ui-table-footer">
            <button
              type="button"
              className="nexus-ui-table-toggle-btn"
              onClick={() => setExpanded((prev) => !prev)}
            >
              {expanded
                ? t('intelligentUi.tableShowLess', 'Mostrar menos')
                : t('intelligentUi.tableShowAll', {
                    count: rows.length,
                    defaultValue: `Mostrar todas (${rows.length})`,
                  })}
            </button>
          </div>
        ) : undefined
      }
    >
      <div className="nexus-ui-table-container">
        <table className="nexus-ui-table">
          <thead>
            <tr>
              {columns.map((col) => {
                const isSorted = sortKey === col.key
                const sortAria = isSorted ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined

                return (
                  <th
                    key={col.key}
                    scope="col"
                    aria-sort={sortAria}
                    className={col.kind === 'number' ? 'nexus-ui-table__cell--number' : undefined}
                  >
                    <button
                      type="button"
                      className="nexus-ui-table-header-btn"
                      onClick={() => handleSort(col.key)}
                    >
                      <span className="nexus-ui-table-header-label">
                        {col.label}
                        {col.unit && col.kind === 'number' && ` (${col.unit})`}
                      </span>
                      <span className="nexus-ui-table-sort-icon" aria-hidden="true">
                        {isSorted ? (
                          sortDir === 'asc' ? (
                            <ArrowUp size={12} />
                          ) : (
                            <ArrowDown size={12} />
                          )
                        ) : (
                          <ArrowUpDown size={12} />
                        )}
                      </span>
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rIdx) => (
              <tr key={rIdx}>
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={col.kind === 'number' ? 'nexus-ui-table__cell--number' : undefined}
                  >
                    {renderCell(col, row[col.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </UiCard>
  )
}

export default TableCard
