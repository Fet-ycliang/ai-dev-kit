import { type ClassValue, clsx } from 'clsx';
import { zhTW } from 'date-fns/locale';
import { twMerge } from 'tailwind-merge';
import { formatDistanceToNow } from 'date-fns';

/**
 * 使用 clsx 與 tailwind-merge 合併 Tailwind CSS class。
 * 這是標準的 shadcn/ui 工具函式。
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * 將日期字串或 Date 格式化為相對時間（例如「5 分鐘前」）。
 */
export function formatRelativeTime(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true, locale: zhTW });
}
