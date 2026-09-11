import {z} from 'zod';

export const nativeLoginPlatformSchema = z.enum(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU']);
export type NativeLoginPlatform = z.infer<typeof nativeLoginPlatformSchema>;

const accountPatterns: Record<NativeLoginPlatform, RegExp> = {
  XIAOHONGSHU: /^[A-Za-z0-9]{8,32}$/,
  DOUYIN: /^[A-Za-z0-9_.-]{1,64}$/,
  BILIBILI: /^[1-9][0-9]{0,19}$/,
  ZHIHU: /^[1-9][0-9]{0,19}$/,
};

export function validNativeAccount(platform: NativeLoginPlatform, account: string): boolean {
  return accountPatterns[platform].test(account);
}
