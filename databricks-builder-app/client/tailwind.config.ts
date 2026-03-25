import type { Config } from 'tailwindcss';

/**
 * Tailwind CSS 設定。
 *
 * 色彩對應 globals.css 中定義的 CSS 變數。
 * 以範本主題系統為基礎。
 */
const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      // ============================================================
      // 色彩 - 對應至 CSS 變數
      // ============================================================
      colors: {
        // 核心色彩
        border: 'var(--color-border)',
        ring: 'var(--color-ring)',
        background: 'var(--color-background)',
        foreground: 'var(--color-foreground)',

        // 主要色彩（按鈕、連結的強調色）
        primary: {
          DEFAULT: 'var(--color-primary)',
          foreground: 'var(--color-primary-foreground)',
        },

        // 次要色彩（次要按鈕使用）
        secondary: {
          DEFAULT: 'var(--color-secondary)',
          foreground: 'var(--color-secondary-foreground)',
        },

        // 警示色彩（錯誤狀態）
        destructive: {
          DEFAULT: 'var(--color-destructive)',
          foreground: '#ffffff',
        },

        // 柔和色彩（較低調的背景）
        muted: {
          DEFAULT: 'var(--color-muted)',
          foreground: 'var(--color-muted-foreground)',
        },

        // 強調色彩（滑過狀態）
        accent: {
          DEFAULT: 'var(--color-accent)',
          foreground: 'var(--color-accent-foreground)',
        },

        // 卡片與 Popover
        card: {
          DEFAULT: 'var(--color-background)',
          foreground: 'var(--color-foreground)',
        },
        popover: {
          DEFAULT: 'var(--color-background)',
          foreground: 'var(--color-foreground)',
        },
      },

      // ============================================================
      // 字型 - 對應至 CSS 變數
      // ============================================================
      fontFamily: {
        sans: 'var(--font-body)',
        heading: 'var(--font-heading)',
        mono: 'var(--font-mono)',
      },

      // ============================================================
      // 版面配置
      // ============================================================
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },
      spacing: {
        sidebar: 'var(--sidebar-width)',
        header: 'var(--header-height)',
      },
    },
  },
  plugins: [],
};

export default config;
