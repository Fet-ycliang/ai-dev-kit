import React, { useState } from 'react';
import {
  Home,
  Database,
  Server,
  BookOpen,
  Layers,
  Code,
  Cpu,
  ArrowRight,
  ChevronRight,
  Terminal,
  Sparkles
} from 'lucide-react';
import { MainLayout } from '@/components/layout/MainLayout';

type DocSection = 'overview' | 'app';

interface NavItem {
  id: DocSection;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { id: 'overview', label: '總覽', icon: <Home className="h-4 w-4" /> },
  { id: 'app', label: 'MCP 應用程式', icon: <Sparkles className="h-4 w-4" /> },
];

function OverviewSection() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-[var(--color-text-heading)]">
          Databricks AI Dev Kit
        </h1>
        <p className="mt-2 text-lg text-[var(--color-text-muted)]">
          使用 MCP（Model Context Protocol）與 AI 程式設計助理建置 Databricks 專案
        </p>
      </div>

      <div className="rounded-xl border border-[var(--color-accent-primary)]/20 bg-[var(--color-accent-primary)]/5 p-6">
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          什麼是 AI Dev Kit？
        </h2>
        <p className="text-[var(--color-text-secondary)]">
          AI Dev Kit 提供你在 Databricks 上結合 Claude Code、Cursor 等 AI 助理進行開發所需的一切：
        </p>
        <ul className="mt-4 space-y-2">
          <li className="flex items-start gap-3">
            <BookOpen className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-skills/</code> - 教導 AI 助理最佳實務、常見模式，以及該使用哪些工具</span>
          </li>
          <li className="flex items-start gap-3">
            <Database className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-tools-core/</code> - 提供 sql/、unity_catalog/、compute/、spark_declarative_pipelines/、agent_bricks/ 的 Python 函式</span>
          </li>
          <li className="flex items-start gap-3">
            <Server className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-mcp-server/</code> - 封裝工具並透過 MCP protocol 對外提供</span>
          </li>
          <li className="flex items-start gap-3">
            <Sparkles className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-builder-app/</code> - 在 Web UI 中使用 Claude Code 來部署 Databricks 資源</span>
          </li>
        </ul>
      </div>

      {/* 視覺化架構 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          運作方式
        </h2>
        <div className="space-y-4">
          {/* 外層包裝：ai-dev-kit */}
          <div className="rounded-xl border-2 border-[var(--color-border)] p-4">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="h-5 w-5 text-[var(--color-text-heading)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">ai-dev-kit/</h3>
            </div>

            {/* Skills（左）與含 Tools 的 MCP Server（右） */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Skills 層 - 左側 */}
              <div className="rounded-xl border-2 border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)]/5 p-4 h-fit">
                <div className="flex items-center gap-2 mb-3">
                  <BookOpen className="h-5 w-5 text-[var(--color-accent-primary)]" />
                  <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-skills/</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-accent-primary)]/20 text-[var(--color-accent-primary)]">知識</span>
                </div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  Skills 說明事情該如何完成，並引用 databricks-tools-core 中的工具。
                </p>
                <div className="flex flex-wrap gap-2">
                  {['databricks-bundles/', 'databricks-app-apx/', 'databricks-app-python/', 'databricks-python-sdk/', 'databricks-mlflow-evaluation/', 'databricks-spark-declarative-pipelines/', 'databricks-synthetic-data-gen/'].map((skill) => (
                    <span key={skill} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-text-secondary)] font-mono">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>

              {/* MCP Server 封裝 Tools Core - 右側 */}
              <div className="rounded-xl border-2 border-dashed border-green-500/40 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Server className="h-5 w-5 text-green-400" />
                  <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-mcp-server/</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">MCP Protocol</span>
                </div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  封裝 databricks-tools-core，並透過 MCP protocol 暴露函式。
                </p>

                {/* Tools Core 層（巢狀於 MCP Server 內） */}
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Database className="h-5 w-5 text-[var(--color-accent-primary)]" />
                    <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-tools-core/</h3>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-accent-primary)]/20 text-[var(--color-accent-primary)]">Python</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {['sql/', 'unity_catalog/', 'compute/', 'spark_declarative_pipelines/', 'agent_bricks/', 'file/'].map((module) => (
                      <span key={module} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-text-secondary)] font-mono">
                        {module}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 箭頭 */}
          <div className="flex justify-center">
            <ArrowRight className="h-6 w-6 text-[var(--color-text-muted)] rotate-90" />
          </div>

          {/* 使用端 */}
          <div className="grid gap-4 md:grid-cols-2">
          {/* AI 工具（Claude Code、Cursor 等） */}
            <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Terminal className="h-5 w-5 text-purple-400" />
                <h3 className="font-semibold text-[var(--color-text-heading)]">AI 程式設計工具</h3>
              </div>
              <p className="text-sm text-[var(--color-text-muted)] mb-3">
                為你的 AI 程式設計工具加入 Databricks 能力
              </p>
              <div className="flex flex-wrap gap-2">
                {['Cursor', 'Claude Code', 'Windsurf', '自訂 Agents'].map((tool) => (
                  <span key={tool} className="text-xs px-2 py-1 rounded bg-purple-500/10 text-purple-300">
                    {tool}
                  </span>
                ))}
              </div>
            </div>

            {/* MCP 應用程式 */}
            <div className="rounded-xl border border-orange-500/30 bg-orange-500/5 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-5 w-5 text-orange-400" />
                <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-builder-app/</h3>
              </div>
              <p className="text-sm text-[var(--color-text-muted)] mb-3">
                在 UI 中使用 Claude Code，作為處理與部署 Databricks 資源的 Agent
              </p>
              <div className="flex flex-wrap gap-2">
                {['Web UI', '專案管理', '部署資源', '對話紀錄'].map((feature) => (
                  <span key={feature} className="text-xs px-2 py-1 rounded bg-orange-500/10 text-orange-300">
                    {feature}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 範例工作流程 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          範例：產生合成資料
        </h2>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-6">
          <div className="space-y-4">
            {/* 使用者需求 */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--color-accent-primary)]/20 flex items-center justify-center">
                <span className="text-sm font-medium text-[var(--color-accent-primary)]">1</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">使用者需求</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  「產生具有真實模式的合成客服資料」
                </p>
              </div>
            </div>

            {/* 讀取 Skill */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--color-accent-primary)]/20 flex items-center justify-center">
                <span className="text-sm font-medium text-[var(--color-accent-primary)]">2</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">讀取 Skill</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Claude 會讀取 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">databricks-synthetic-data-gen/</code> Skill 以學習最佳實務
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {['非線性分布', '參照完整性', '時間模式', '資料列一致性'].map((item) => (
                    <span key={item} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-text-secondary)]">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* 了解儲存方式 */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--color-accent-primary)]/20 flex items-center justify-center">
                <span className="text-sm font-medium text-[var(--color-accent-primary)]">3</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">了解如何在 Databricks UC 上寫入並儲存原始資料</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  從 Skill 學習：將原始檔儲存到 Volume、在腳本中建立 catalog/schema/volume、向使用者詢問 schema 名稱，並在 cluster 上安裝函式庫
                </p>
              </div>
            </div>

            {/* 撰寫程式碼 */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-green-400">4</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">在本機撰寫 Python</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  建立 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">scripts/generate_data.py</code>，使用 Faker、pandas 與真實分布
                </p>
              </div>
            </div>

            {/* 遠端執行 */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-green-400">5</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">在 Databricks 上執行</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  呼叫 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">run_python_file_on_databricks()</code>，自動選擇最佳 cluster、建立執行 context，並安裝所需函式庫
                </p>
              </div>
            </div>

            {/* 處理錯誤 */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-orange-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-orange-400">6</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">修正並重試</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  若發生錯誤，請編輯本機檔案，並使用相同的 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">cluster_id</code> + <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">context_id</code> 重新執行（更快，且可保留狀態）
                </p>
              </div>
            </div>

            {/* 驗證 */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-purple-400">7</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">驗證結果</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  呼叫 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">get_volume_folder_details()</code> 驗證已寫入的檔案，例如 schema、資料列數與欄位統計
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 為何有效 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          為何有效
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <BookOpen className="h-5 w-5 text-[var(--color-accent-primary)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">Skills 傳授最新功能</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              AI 透過精心整理的 Skills 學習 Databricks 最佳實務，不會使用過時模式或已淘汰 API。
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Code className="h-5 w-5 text-green-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">經過驗證的抽象層</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              像「run this file」這類高階工具，封裝了 2000 多行經過驗證、含快取、重試與最佳化的程式碼。
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Cpu className="h-5 w-5 text-purple-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">更快的執行速度</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              整合式操作可減少 LLM 的推理步驟，不必拼裝數十個 API 呼叫，只需少數高階工具。
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Database className="h-5 w-5 text-orange-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">降低幻覺</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Tools 會回傳真實資料與錯誤，AI 能清楚知道哪些成功、哪些失敗，無需猜測。
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <ArrowRight className="h-5 w-5 text-[var(--color-accent-primary)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">內建回饋迴圈</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Skills 會教導如何處理錯誤，Tools 則回傳結構化結果，讓 AI 可以反覆迭代並自我修正。
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Layers className="h-5 w-5 text-green-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">完全解耦</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              可原生使用工具（LangChain、Claude SDK、OpenAI），也可透過 MCP 使用；可搭配或不搭配 Skills，適用於任何 Agent framework。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function AppSection() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-[var(--color-text-heading)]">
          databricks-builder-app
        </h1>
        <p className="mt-2 text-lg text-[var(--color-text-muted)]">
          Claude Code in a web UI - an agent to work on and deploy Databricks resources
        </p>
      </div>

      <div className="rounded-xl border border-[var(--color-accent-primary)]/20 bg-[var(--color-accent-primary)]/5 p-6">
        <p className="text-[var(--color-text-secondary)]">
          你現在就在使用它！這個應用程式提供 Web 介面，讓你可以與 Claude 和 Databricks tools 互動，並以專案方式管理與保留對話紀錄。
        </p>
      </div>

      {/* 架構圖 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          架構
        </h2>
        <div className="rounded-xl border border-[var(--color-border)] p-6 space-y-4">
          {/* React 前端 - 上方 */}
          <div className="rounded-xl border border-[var(--color-accent-primary)]/30 bg-[var(--color-accent-primary)]/5 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Code className="h-5 w-5 text-[var(--color-accent-primary)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">React 前端</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              聊天 UI、專案管理、資源設定與檔案瀏覽器
            </p>
          </div>

          {/* 箭頭 */}
          <div className="flex justify-center">
            <ArrowRight className="h-6 w-6 text-[var(--color-text-muted)] rotate-90" />
          </div>

          {/* 後端 + PostgreSQL 並排 */}
          <div className="grid gap-4 md:grid-cols-3">
            {/* FastAPI 後端 - 2 欄 */}
            <div className="md:col-span-2 space-y-4">
              <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Server className="h-5 w-5 text-green-400" />
                  <h3 className="font-semibold text-[var(--color-text-heading)]">FastAPI 後端</h3>
                </div>
                <p className="text-sm text-[var(--color-text-muted)]">
                  Claude Agent SDK、MCP tools 與檔案管理
                </p>
              </div>

              {/* 箭頭 */}
              <div className="flex justify-center">
                <ArrowRight className="h-6 w-6 text-[var(--color-text-muted)] rotate-90" />
              </div>

              {/* Claude Code 工作階段 */}
              <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Terminal className="h-5 w-5 text-purple-400" />
                  <h3 className="font-semibold text-[var(--color-text-heading)]">透過 SDK 建立 Claude Code 工作階段</h3>
                </div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  Claude Code 會在應用程式資料夾 <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">project/&lt;project_id&gt;/</code> 中於本機讀寫檔案
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  建立新專案時，我們會載入 Skills，並在 Claude Code 工作階段中提供 tools：
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-[var(--color-accent-primary)]/30 bg-[var(--color-accent-primary)]/5 p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <BookOpen className="h-4 w-4 text-[var(--color-accent-primary)]" />
                      <span className="font-semibold text-sm text-[var(--color-text-heading)]">Skills</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      最佳實務、常見模式，以及如何使用 tools
                    </p>
                  </div>
                  <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <Cpu className="h-4 w-4 text-green-400" />
                      <span className="font-semibold text-sm text-[var(--color-text-heading)]">Tools</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      用來與 Databricks 互動的 MCP 函式
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* PostgreSQL - 右側單欄 */}
            <div className="rounded-xl border border-orange-500/30 bg-orange-500/5 p-4 h-fit">
              <div className="flex items-center gap-2 mb-3">
                <Database className="h-5 w-5 text-orange-400" />
                <h3 className="font-semibold text-[var(--color-text-heading)]">PostgreSQL</h3>
              </div>
              <ul className="space-y-2 text-sm text-[var(--color-text-muted)]">
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  儲存對話
                </li>
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  Claude Code 工作階段
                </li>
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  備份專案檔案
                </li>
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  專案詳細資料／資源
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* 運作方式 - 核心概念 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          運作方式
        </h2>
        <div className="space-y-6">
          {/* 專案建立 */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-[var(--color-accent-primary)]/20 flex items-center justify-center text-[var(--color-accent-primary)] font-semibold text-sm">1</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">專案建立</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  每個專案都以 UUID 做為使用者範圍區隔。磁碟上會建立一個 <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">project/&lt;project_id&gt;/</code> 目錄，並將 <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">databricks-skills/</code> 中的 Skills 複製到專案資料夾內的 <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">.claude/skills/</code>。
                </p>
              </div>
            </div>
          </div>

          {/* Claude Code 工作階段 */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400 font-semibold text-sm">2</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">透過 SDK 的 Claude Code 工作階段</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  當你傳送訊息時，後端會使用 <strong>Claude Agent SDK</strong> 建立 Claude Code 工作階段。
                  該工作階段的 <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">cwd</code> 會設為專案目錄（檔案存取範圍因此受限）。
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mt-2">
                  此工作階段的設定包含：
                </p>
                <ul className="mt-2 space-y-1 text-sm text-[var(--color-text-muted)]">
                  <li className="flex items-center gap-2">
                    <ChevronRight className="h-3 w-3 text-purple-400" />
                    <strong>內建 tools：</strong>Read、Write、Edit、Glob、Grep、Skill
                  </li>
                  <li className="flex items-center gap-2">
                    <ChevronRight className="h-3 w-3 text-purple-400" />
                    <strong>Databricks tools：</strong>從 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">databricks-tools-core</code> 動態載入
                  </li>
                  <li className="flex items-center gap-2">
                    <ChevronRight className="h-3 w-3 text-purple-400" />
                    <strong>System Prompt：</strong>包含來自 UI 選擇的 cluster/catalog 內容脈絡
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* 工作階段續接 */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center text-green-400 font-semibold text-sm">3</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">多輪對話</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  每段對話都會儲存一個 <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">session_id</code>。當你繼續對話時，SDK 會從該工作階段續接，因此 Claude 會記得先前訊息的內容脈絡。
                </p>
              </div>
            </div>
          </div>

          {/* 檔案備份 */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-orange-500/20 flex items-center justify-center text-orange-400 font-semibold text-sm">4</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">檔案備份與還原</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  每次 Agent 查詢後，專案檔案都會標記為待備份。背景工作程序會每 10 分鐘將專案資料夾壓縮成 ZIP，並儲存到 PostgreSQL。
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mt-2">
                  應用程式重新啟動時，若專案目錄遺失，系統會自動從備份還原，並重新注入 Skills。
                </p>
              </div>
            </div>
          </div>

          {/* 串流 */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-[var(--color-accent-primary)]/20 flex items-center justify-center text-[var(--color-accent-primary)] font-semibold text-sm">5</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">即時串流</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  後端會透過 Server-Sent Events（SSE）串流事件：<code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">text</code>、<code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">thinking</code>、<code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">tool_use</code>、<code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">tool_result</code>。你可以即時看到 Claude 的推理與 tool 呼叫。
                </p>
              </div>
            </div>
          </div>

          {/* 每位使用者的認證 */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400 font-semibold text-sm">6</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">每位使用者的 Databricks 認證</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Databricks 憑證會透過 Python <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">contextvars</code> 依請求注入。每位使用者的 tools 都會以自己的 Databricks 權限執行，不共用憑證。
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 認證與 MCP Server */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          認證與 MCP Server
        </h2>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
          <h3 className="font-semibold text-[var(--color-text-heading)] mb-3">程序內工具執行</h3>
          <p className="text-sm text-[var(--color-text-muted)] mb-3">
            我們<strong>不會</strong>將 MCP server 作為獨立程序執行。相反地，我們直接以 Claude Agent SDK 封裝 Databricks tools，因此所有內容都在同一個 Python 程序與記憶體空間中執行。
          </p>
          <p className="text-sm text-[var(--color-text-muted)] mb-3">
            這種設計讓我們可以在請求時透過 Python <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">contextvars</code> 注入每位使用者的 Databricks 憑證。每次 tool 呼叫都知道是哪位使用者在操作，而不必透過工具介面傳遞 auth tokens。
          </p>
          <div className="rounded-lg border border-[var(--color-accent-primary)]/30 bg-[var(--color-accent-primary)]/5 p-3 mt-4">
            <p className="text-sm text-[var(--color-text-secondary)]">
              <strong>優點：</strong>沒有 subprocess 額外負擔、可共用記憶體、可做到依請求的 auth 隔離，並能從 <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">databricks-tools-core</code> 動態探索工具。
            </p>
          </div>
        </div>
      </div>

      {/* 安全性警告 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          安全性注意事項
        </h2>
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-5">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center">
              <span className="text-red-400 font-bold">!</span>
            </div>
            <div>
              <h3 className="font-semibold text-red-400 mb-2">MVP - 僅限受信任環境</h3>
              <p className="text-sm text-[var(--color-text-muted)]">
                此 MVP <strong>不適合用於正式環境</strong>。Claude Code 可以在專案目錄內執行任意本機程式碼、讀寫檔案，並執行 shell 指令。
              </p>
              <p className="text-sm text-[var(--color-text-muted)] mt-2">
                惡意使用者可能在伺服器上執行程式碼。請僅在所有使用者皆已授權且可信任的環境中部署此應用程式。
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 技術堆疊 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          技術堆疊
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <h3 className="font-semibold text-[var(--color-text-heading)] mb-2">前端</h3>
            <div className="flex flex-wrap gap-2">
              {['React', 'TypeScript', 'TailwindCSS', 'Vite'].map((tech) => (
                <span key={tech} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]">
                  {tech}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <h3 className="font-semibold text-[var(--color-text-heading)] mb-2">後端</h3>
            <div className="flex flex-wrap gap-2">
              {['FastAPI', 'Claude Agent SDK', 'PostgreSQL'].map((tech) => (
                <span key={tech} className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-400">
                  {tech}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <h3 className="font-semibold text-[var(--color-text-heading)] mb-2">整合</h3>
            <div className="flex flex-wrap gap-2">
              {['MCP Protocol', 'Databricks SDK', 'OAuth'].map((tech) => (
                <span key={tech} className="text-xs px-2 py-1 rounded bg-purple-500/10 text-purple-400">
                  {tech}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DocPage() {
  const [activeSection, setActiveSection] = useState<DocSection>('overview');

  const renderSection = () => {
    switch (activeSection) {
      case 'overview':
        return <OverviewSection />;
      case 'app':
        return <AppSection />;
      default:
        return <OverviewSection />;
    }
  };

  const docSidebar = (
    <nav className="w-64 h-full border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)] overflow-y-auto">
      <div className="p-4 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveSection(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
              activeSection === item.id
                ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-heading)]'
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </div>
    </nav>
  );

  return (
    <MainLayout sidebar={docSidebar}>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-8 py-8">
          {renderSection()}
        </div>
      </div>
    </MainLayout>
  );
}
