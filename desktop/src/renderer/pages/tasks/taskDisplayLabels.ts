import {PLATFORMS, type PlatformConnection} from '../../domain/models';

export function taskAccountLabel(connection: PlatformConnection, connections: PlatformConnection[]) {
  const index=connections.filter(row=>row.platform===connection.platform).indexOf(connection);
  return connection.accountName?.trim() || `${PLATFORMS.find(row=>row.id===connection.platform)?.name || '平台'}账号${Math.max(0,index)+1}`;
}

export function scheduleRegionLabel(timezone: string) {
  const known: Record<string,string>={'Asia/Shanghai':'北京时间','Asia/Hong_Kong':'香港时间','Asia/Singapore':'新加坡时间','Europe/London':'伦敦时间','America/New_York':'纽约时间',UTC:'世界标准时间'};
  if(known[timezone])return known[timezone];
  try { return new Intl.DateTimeFormat('zh-CN',{timeZone:timezone,timeZoneName:'longGeneric'}).formatToParts(new Date()).find(part=>part.type==='timeZoneName')?.value || '原任务地区时间'; }
  catch { return '原任务地区时间'; }
}
