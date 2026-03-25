import { ReactNode } from 'react';
import { TopBar } from './TopBar';

interface MainLayoutProps {
  children: ReactNode;
  projectName?: string;
  sidebar?: ReactNode;
}

export function MainLayout({ children, projectName, sidebar }: MainLayoutProps) {
  return (
    <div className="h-screen bg-[var(--color-background)] flex flex-col overflow-hidden">
      {/* 頂部列 - 固定位置 */}
      <TopBar projectName={projectName} />

      {/* 固定頁首的預留空間 */}
      <div className="flex-shrink-0 h-[var(--header-height)]" />

      {/* 主要版面 */}
      <div className="flex-1 flex relative overflow-hidden">
        {/* 側邊欄 */}
        {sidebar && (
          <div className="hidden lg:block flex-shrink-0">
            {sidebar}
          </div>
        )}

        {/* 主要內容區域 */}
        <main className="flex-1 flex flex-col h-full relative bg-[var(--color-background)] overflow-hidden">
          <div className="relative flex-1 flex flex-col min-h-0">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
