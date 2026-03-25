import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

// 類似 Claude Code 的趣味載入訊息
const FUN_MESSAGES = [
  '思考中...',
  '斟酌中...',
  '推敲中...',
  '反覆思量中...',
  '縝密分析中...',
  '審慎規劃中...',
  '構思中...',
  '反思中...',
  '分析中...',
  '處理中...',
  '運算中...',
  '整合中...',
  '擬定中...',
  '架構設計中...',
  '策略規劃中...',
  '深入檢視中...',
  '研究中...',
  '探索中...',
  '腦力激盪中...',
  '發想中...',
];

interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

interface FunLoaderProps {
  todos?: TodoItem[];
  className?: string;
}

export function FunLoader({ todos = [], className }: FunLoaderProps) {
  const [messageIndex, setMessageIndex] = useState(() =>
    Math.floor(Math.random() * FUN_MESSAGES.length)
  );

  // 每 2.5 秒輪換一次訊息
  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % FUN_MESSAGES.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  // 計算進度
  const completedCount = todos.filter((t) => t.status === 'completed').length;
  const totalCount = todos.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const currentTodo = todos.find((t) => t.status === 'in_progress');

  return (
    <div className={cn('flex flex-col items-start gap-3', className)}>
      {/* 主要載入器與輪換訊息 */}
      <div className="flex items-center gap-3 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/50 px-4 py-3 shadow-sm">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent-primary)]" />
        <span className="text-sm text-[var(--color-text-primary)] font-medium min-w-[120px]">
          {FUN_MESSAGES[messageIndex]}
        </span>
      </div>

      {/* 進度區塊 - 只有在有待辦時才顯示 */}
      {totalCount > 0 && (
        <div className="w-full max-w-md space-y-2">
          {/* 進度條 */}
          <div className="relative h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/30">
            <div
              className="absolute inset-y-0 left-0 bg-[var(--color-accent-primary)] transition-all duration-500 ease-out rounded-full"
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* 進度文字 */}
          <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
            <span>
              已完成 {completedCount} / {totalCount} 項任務
            </span>
            <span>{Math.round(progress)}%</span>
          </div>

          {/* 目前任務指示 */}
          {currentTodo && (
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] bg-[var(--color-bg-secondary)]/50 rounded-md px-2 py-1.5 border border-[var(--color-border)]/30">
              <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent-primary)] animate-pulse" />
              <span className="truncate">{currentTodo.content}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
