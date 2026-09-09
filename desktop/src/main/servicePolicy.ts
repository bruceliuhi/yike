import {z} from 'zod';

const empty = z.object({}).strict().optional();
const identifier = z.string().min(1).max(128).regex(/^[A-Za-z0-9_-][A-Za-z0-9_.:-]*$/);
const text = z.string().max(8000).refine(value => value.trim().length > 0);
const phone = z.string().length(11).regex(/^1[0-9]{10}$/);
const schemas = {
  'session.get': empty,
  'session.login': z.object({token: z.string().min(1).max(8192)}).strict(),
  'session.logout': empty,
  'session.requestCode': z.object({phone}).strict(),
  'session.loginPhone': z.object({phone, code: z.string().length(6).regex(/^[0-9]{6}$/), trial_code: z.string().max(128).optional()}).strict(),
  'profiles.list': empty,
  'profiles.save': z.object({description: text}).strict(),
  'profiles.confirm': z.object({version_id: identifier}).strict(),
  'opportunities.list': empty,
  'opportunities.get': z.object({id: identifier}).strict(),
  'followups.list': empty,
  'followups.add': z.object({
    opportunity_id: identifier,
    status: z.enum(['CONTACTED', 'REPLIED', 'MEETING', 'QUOTED', 'LOST', 'WON']),
    note: text
  }).strict(),
  'capabilities.get': empty
} as const;

export interface ServiceOperation {
  path: string;
  method: 'GET' | 'POST' | 'DELETE';
  body?: string;
  logout: boolean;
}

export function validatedOperation(input: unknown): ServiceOperation | null {
  const request = z.object({operation: z.enum(Object.keys(schemas) as [keyof typeof schemas, ...(keyof typeof schemas)[]]), payload: z.unknown().optional()}).strict().safeParse(input);
  if (!request.success) return null;
  const {operation, payload} = request.data;
  const parsed = schemas[operation].safeParse(payload);
  if (!parsed.success) return null;
  const data = parsed.data as Record<string, string> | undefined;
  switch (operation) {
    case 'session.get': return {path: '/api/ui/session', method: 'GET', logout: false};
    case 'session.login': return {path: '/api/ui/session', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'session.logout': return {path: '/api/ui/session', method: 'DELETE', logout: true};
    case 'session.requestCode': return {path: '/api/ui/auth/sms-code', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'session.loginPhone': return {path: '/api/ui/auth/sms-session', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'profiles.list': return {path: '/api/ui/profiles', method: 'GET', logout: false};
    case 'profiles.save': return {path: '/api/ui/profiles', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'profiles.confirm': return {path: `/api/ui/profiles/${encodeURIComponent(data!.version_id)}/confirm`, method: 'POST', logout: false};
    case 'opportunities.list': return {path: '/api/ui/opportunities', method: 'GET', logout: false};
    case 'opportunities.get': return {path: `/api/ui/opportunities/${encodeURIComponent(data!.id)}`, method: 'GET', logout: false};
    case 'followups.list': return {path: '/api/ui/followups', method: 'GET', logout: false};
    case 'followups.add': return {path: '/api/ui/followups', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'capabilities.get': return {path: '/api/ui/capabilities', method: 'GET', logout: false};
  }
}

export function validatedExternalUrl(input: unknown): string | null {
  if (typeof input !== 'string' || input.length > 8192 || /[\x00-\x20\x7f\\]/.test(input)) return null;
  try {
    const url = new URL(input);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
    return url.href;
  } catch { return null; }
}

export function validClipboardText(input: unknown): input is string {
  return typeof input === 'string' && input.length > 0 && input.length <= 20_000 && !input.includes('\0');
}
