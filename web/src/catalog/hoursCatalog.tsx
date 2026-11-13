/**
 * React implementations for the Project Hours catalog.
 *
 * The contract lives in /catalog/hours_catalog.json. The agent reads that file
 * to build its prompt and validate what the model produces; this file pairs
 * each component in it with a React component. Names, property names and the
 * catalog id must match the JSON.
 */
import {z} from 'zod';

import {createComponentImplementation} from '@a2ui/react';
import {
  ActionSchema,
  Catalog,
  DynamicBooleanSchema,
  DynamicNumberSchema,
  DynamicStringSchema,
  DynamicValueSchema,
} from '@a2ui/web_core/v1_0';

import catalogJson from '../../../catalog/hours_catalog.json';

export const HOURS_CATALOG_ID: string = catalogJson.catalogId;

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

const text = (value: unknown): string => (value == null ? '' : String(value));
const num = (value: unknown): number => (typeof value === 'number' ? value : Number(value) || 0);
const fmt = (hours: number): string => (Number.isInteger(hours) ? String(hours) : hours.toFixed(1));

const StatusPill = createComponentImplementation(
  {
    name: 'StatusPill',
    schema: z.object({
      label: DynamicStringSchema,
      tone: z.enum(['ok', 'warning', 'over']),
    }),
  },
  ({props}) => <span className={`hours-pill hours-pill--${props.tone}`}>{text(props.label)}</span>,
);

const ProjectBudgetCard = createComponentImplementation(
  {
    name: 'ProjectBudgetCard',
    schema: z.object({
      project: DynamicStringSchema,
      client: DynamicStringSchema.optional(),
      hoursUsed: DynamicNumberSchema,
      budgetHours: DynamicNumberSchema,
      onSelect: ActionSchema.optional(),
    }),
  },
  ({props}) => {
    const used = num(props.hoursUsed);
    const budget = num(props.budgetHours);
    const ratio = budget > 0 ? used / budget : 0;
    const tone = ratio > 1 ? 'over' : ratio >= 0.8 ? 'warning' : 'ok';
    const onSelect = props.onSelect;

    return (
      <article
        className={`hours-budget hours-budget--${tone}${onSelect ? ' hours-budget--clickable' : ''}`}
        onClick={onSelect ? () => void onSelect() : undefined}
      >
        <header>
          <strong>{text(props.project)}</strong>
          {props.client ? <span className="hours-muted">{text(props.client)}</span> : null}
        </header>
        <div className="hours-bar">
          <div className="hours-bar__fill" style={{width: `${Math.min(ratio, 1) * 100}%`}} />
        </div>
        <footer>
          <span>
            {fmt(used)} / {fmt(budget)} h
          </span>
          <span className="hours-muted">{Math.round(ratio * 100)}%</span>
        </footer>
      </article>
    );
  },
);

interface WeekRow {
  project: string;
  hours: number[];
}

function toRows(value: unknown): WeekRow[] {
  if (!Array.isArray(value)) return [];
  return value.map(row => {
    const r = (row ?? {}) as Record<string, unknown>;
    const hours = Array.isArray(r.hours) ? r.hours : [];
    return {project: text(r.project), hours: DAYS.map((_, i) => num(hours[i]))};
  });
}

const WeekGrid = createComponentImplementation(
  {
    name: 'WeekGrid',
    schema: z.object({
      week: DynamicStringSchema,
      entries: DynamicValueSchema,
      approved: DynamicBooleanSchema.optional(),
      onApprove: ActionSchema.optional(),
    }),
  },
  ({props}) => {
    const rows = toRows(props.entries);
    const dayTotals = DAYS.map((_, i) => rows.reduce((sum, r) => sum + r.hours[i], 0));
    const total = dayTotals.reduce((sum, h) => sum + h, 0);
    const approved = props.approved === true;
    const onApprove = props.onApprove;

    return (
      <section className="hours-week">
        <header>
          <strong>Week {text(props.week)}</strong>
          {approved ? <span className="hours-pill hours-pill--ok">Approved</span> : null}
        </header>
        <table>
          <thead>
            <tr>
              <th>Project</th>
              {DAYS.map(d => (
                <th key={d}>{d}</th>
              ))}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.project}>
                <td>{r.project}</td>
                {r.hours.map((h, i) => (
                  <td key={i} className={h === 0 ? 'hours-muted' : undefined}>
                    {fmt(h)}
                  </td>
                ))}
                <td>
                  <strong>{fmt(r.hours.reduce((s, h) => s + h, 0))}</strong>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total</td>
              {dayTotals.map((h, i) => (
                <td key={i}>{fmt(h)}</td>
              ))}
              <td>
                <strong>{fmt(total)}</strong>
              </td>
            </tr>
          </tfoot>
        </table>
        {onApprove && !approved ? (
          <button type="button" onClick={() => void onApprove()}>
            Approve week
          </button>
        ) : null}
      </section>
    );
  },
);

export const hoursCatalog = new Catalog(HOURS_CATALOG_ID, '1.0', [
  StatusPill,
  ProjectBudgetCard,
  WeekGrid,
]);
