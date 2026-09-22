import { z } from 'zod';

const declarationText = (max: number) => z.string().min(1).refine(value =>
  Array.from(value).length <= max && value.trim() === value &&
  !/[\x00-\x1f\x7f-\x9f]/.test(value) && !/[\uD800-\uDFFF]/u.test(value),
);

/** Strict publisher spelling only; local/date precision never supplies a timezone. */
function normalizePublication(raw: string): { value: string; precision: string } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})?)?$/.exec(raw);
  if (!match) return null;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, zone] = match;
  const year = Number(yearText), month = Number(monthText), day = Number(dayText);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1]) return null;
  if (hourText === undefined) return { value: raw, precision: 'DATE' };
  if (Number(hourText) > 23 || Number(minuteText) > 59 || Number(secondText) > 59) return null;
  const local = `${raw.slice(0, 10)}T${hourText}:${minuteText}:${secondText}`;
  if (zone === undefined) return { value: local, precision: 'LOCAL_SECOND' };
  if (zone !== 'Z') {
    const hours = Number(zone.slice(1, 3)), minutes = Number(zone.slice(4, 6));
    if (hours > 14 || minutes > 59 || (hours === 14 && minutes !== 0)) return null;
  }
  const instant = new Date(local + zone);
  if (!Number.isFinite(instant.getTime())) return null;
  const value = instant.toISOString().replace('.000Z', 'Z');
  // Offset conversion must remain within Python's four-digit calendar range.
  if (!/^\d{4}-/.test(value) || value.startsWith('0000-')) return null;
  return { value, precision: 'SECOND' };
}

const publicationSchema = z.object({
  raw: declarationText(128),
  declaration: z.enum(['article:published_time', 'datepublished']),
  value: z.string(),
  precision: z.enum(['DATE', 'SECOND', 'LOCAL_SECOND']),
}).strict().refine(publication => {
  const normalized = normalizePublication(publication.raw);
  return normalized !== null && normalized.value === publication.value && normalized.precision === publication.precision;
});

export const publicPageMetadataSchema = z.object({
  schema_version: z.literal('public-page-metadata-v1'),
  publication: publicationSchema.nullable(),
  author: z.object({
    raw: declarationText(256), declaration: z.literal('author'), value: declarationText(256),
  }).strict().refine(author => author.raw === author.value).nullable(),
}).strict().refine(metadata => metadata.publication !== null || metadata.author !== null);

export type PublicPageMetadata = z.infer<typeof publicPageMetadataSchema>;

export function validPageMetadataTimes(
  metadata: PublicPageMetadata | undefined,
  publishedAt: string | null,
  observedAt: string,
): boolean {
  if (metadata === undefined) return true;
  const publication = metadata.publication;
  if (publishedAt !== (publication?.precision === 'SECOND' ? publication.value : null)) return false;
  if (publication === null) return true;
  const observed = Date.parse(observedAt);
  if (!Number.isFinite(observed)) return false;
  if (publication.precision === 'SECOND') return Date.parse(publication.value) <= observed;
  // Compare uncertain wall-clock values only with the greatest possible UTC+14
  // local time at observation; this does not assign a zone or a midnight instant.
  const latestLocal = new Date(observed + 14 * 60 * 60 * 1000).toISOString();
  return publication.value <= latestLocal.slice(0, publication.precision === 'DATE' ? 10 : 19);
}
