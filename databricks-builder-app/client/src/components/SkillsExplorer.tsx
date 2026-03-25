import { useCallback, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Code,
  Eye,
  File,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  fetchAvailableSkills,
  fetchSkillFile,
  fetchSkillsTree,
  fetchSystemPrompt,
  reloadProjectSkills,
  updateEnabledSkills,
  type FetchSystemPromptParams,
  type SkillTreeNode,
} from '@/lib/api';
import type { AvailableSkill } from '@/lib/types';

interface TreeNodeProps {
  node: SkillTreeNode;
  level: number;
  selectedPath: string | null;
  expandedPaths: Set<string>;
  onSelect: (path: string) => void;
  onToggle: (path: string) => void;
}

function TreeNode({
  node,
  level,
  selectedPath,
  expandedPaths,
  onSelect,
  onToggle,
}: TreeNodeProps) {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;
  const isDirectory = node.type === 'directory';
  const isMarkdown = node.name.endsWith('.md');

  const handleClick = () => {
    if (isDirectory) {
      onToggle(node.path);
    } else {
      onSelect(node.path);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs transition-colors',
          isSelected
            ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
            : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)]'
        )}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
      >
        {isDirectory ? (
          <>
            {isExpanded ? (
              <ChevronDown className="h-3 w-3 flex-shrink-0 text-[var(--color-text-muted)]" />
            ) : (
              <ChevronRight className="h-3 w-3 flex-shrink-0 text-[var(--color-text-muted)]" />
            )}
            {isExpanded ? (
              <FolderOpen className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-warning)]" />
            ) : (
              <Folder className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-warning)]" />
            )}
          </>
        ) : (
          <>
            <span className="w-3" />
            {isMarkdown ? (
              <FileText className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-accent-secondary)]" />
            ) : (
              <File className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-muted)]" />
            )}
          </>
        )}
        <span className="truncate">{node.name}</span>
      </button>

      {isDirectory && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              level={level + 1}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              onSelect={onSelect}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 切換開關元件
function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className={cn(
        'relative inline-flex h-4 w-7 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/50 focus:ring-offset-1',
        checked ? 'bg-[var(--color-accent-primary)]' : 'bg-[var(--color-text-muted)]/50',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <span
        className={cn(
          'pointer-events-none inline-block h-3 w-3 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
          checked ? 'translate-x-3' : 'translate-x-0'
        )}
      />
    </button>
  );
}

interface SkillsExplorerProps {
  projectId: string;
  systemPromptParams: FetchSystemPromptParams;
  onClose: () => void;
}

export function SkillsExplorer({
  projectId,
  systemPromptParams,
  onClose,
}: SkillsExplorerProps) {
  const [tree, setTree] = useState<SkillTreeNode[]>([]);
  const [isLoadingTree, setIsLoadingTree] = useState(true);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<'system_prompt' | 'skill'>('system_prompt');
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [content, setContent] = useState<string>('');
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [showRawCode, setShowRawCode] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  // Skill 管理狀態
  const [availableSkills, setAvailableSkills] = useState<AvailableSkill[]>([]);
  const [isUpdatingSkills, setIsUpdatingSkills] = useState(false);

  // 載入 Skills 樹狀結構與可用 Skills
  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoadingTree(true);
        const [treeData, skillsData] = await Promise.all([
          fetchSkillsTree(projectId),
          fetchAvailableSkills(projectId),
        ]);
        setTree(treeData);
        setAvailableSkills(skillsData.skills);

        // 自動展開第一層目錄
        const initialExpanded = new Set<string>();
        treeData.forEach((node) => {
          if (node.type === 'directory') {
            initialExpanded.add(node.path);
          }
        });
        setExpandedPaths(initialExpanded);
      } catch (error) {
        console.error('載入 Skills 資料失敗:', error);
      } finally {
        setIsLoadingTree(false);
      }
    };

    loadData();
  }, [projectId]);

  // 預設載入 System Prompt
  useEffect(() => {
    const loadSystemPrompt = async () => {
      try {
        setIsLoadingContent(true);
        const prompt = await fetchSystemPrompt(systemPromptParams);
        setContent(prompt);
        setSelectedType('system_prompt');
      } catch (error) {
        console.error('載入 System Prompt 失敗:', error);
        setContent('載入 System Prompt 時發生錯誤');
      } finally {
        setIsLoadingContent(false);
      }
    };

    loadSystemPrompt();
  }, [systemPromptParams]);

  const handleSelectSystemPrompt = useCallback(async () => {
    setSelectedPath(null);
    setSelectedType('system_prompt');
    setIsLoadingContent(true);
    try {
      const prompt = await fetchSystemPrompt(systemPromptParams);
      setContent(prompt);
    } catch (error) {
      console.error('載入 System Prompt 失敗:', error);
      setContent('載入 System Prompt 時發生錯誤');
    } finally {
      setIsLoadingContent(false);
    }
  }, [systemPromptParams]);

  const handleSelectSkill = useCallback(
    async (path: string) => {
      setSelectedPath(path);
      setSelectedType('skill');
      setIsLoadingContent(true);
      try {
        const file = await fetchSkillFile(projectId, path);
        setContent(file.content);
      } catch (error) {
        console.error('載入 Skill 檔案失敗:', error);
        setContent('載入檔案時發生錯誤');
      } finally {
        setIsLoadingContent(false);
      }
    },
    [projectId]
  );

  const handleToggle = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleReloadSkills = useCallback(async () => {
    setIsReloading(true);
    try {
      await reloadProjectSkills(projectId);
      // 重新整理後重新載入樹狀結構與可用 Skills
      const [treeData, skillsData] = await Promise.all([
        fetchSkillsTree(projectId),
        fetchAvailableSkills(projectId),
      ]);
      setTree(treeData);
      setAvailableSkills(skillsData.skills);
      // 自動展開第一層目錄
      const initialExpanded = new Set<string>();
      treeData.forEach((node) => {
        if (node.type === 'directory') {
          initialExpanded.add(node.path);
        }
      });
      setExpandedPaths(initialExpanded);
      // 將選取重設為 System Prompt
      setSelectedPath(null);
      setSelectedType('system_prompt');
      toast.success('已重新載入 Skills');
    } catch (error) {
      console.error('重新載入 Skills 失敗:', error);
      toast.error('重新載入 Skills 失敗');
    } finally {
      setIsReloading(false);
    }
  }, [projectId]);

  // 切換單一 Skill
  const handleToggleSkill = useCallback(
    async (skillName: string, enabled: boolean) => {
      setIsUpdatingSkills(true);
      try {
        // 計算新的啟用清單
        const allEnabled = availableSkills.every((s) => s.enabled) && availableSkills.some((s) => s.name !== skillName);
        let newEnabledList: string[] | null;

        if (enabled) {
          // 啟用 Skill
          const currentEnabled = availableSkills.filter((s) => s.enabled).map((s) => s.name);
          const newEnabled = [...currentEnabled, skillName];
          // 若所有 Skills 都將被啟用，則設為 null（全部）
          if (newEnabled.length >= availableSkills.length) {
            newEnabledList = null;
          } else {
            newEnabledList = newEnabled;
          }
        } else {
          // 停用 Skill
          const currentEnabled = availableSkills.filter((s) => s.enabled).map((s) => s.name);
          newEnabledList = currentEnabled.filter((n) => n !== skillName);
          if (newEnabledList.length === 0) {
            toast.error('至少必須啟用一個 Skill');
            setIsUpdatingSkills(false);
            return;
          }
        }

        await updateEnabledSkills(projectId, newEnabledList);

        // 更新本機狀態
        setAvailableSkills((prev) =>
          prev.map((s) => (s.name === skillName ? { ...s, enabled } : s))
        );

        // 重新整理樹狀結構以反映檔案系統變更
        const treeData = await fetchSkillsTree(projectId);
        setTree(treeData);

        // 若目前正在檢視 System Prompt，則重新整理內容（讓停用的 Skills 消失）
        if (selectedType === 'system_prompt') {
          const prompt = await fetchSystemPrompt(systemPromptParams);
          setContent(prompt);
        }
      } catch (error) {
        console.error('更新 Skill 狀態失敗:', error);
        toast.error('更新 Skill 失敗');
      } finally {
        setIsUpdatingSkills(false);
      }
    },
    [projectId, availableSkills, selectedType, systemPromptParams]
  );

  // 啟用或停用所有 Skills
  const handleToggleAll = useCallback(
    async (enableAll: boolean) => {
      setIsUpdatingSkills(true);
      try {
        if (enableAll) {
          await updateEnabledSkills(projectId, null);
          setAvailableSkills((prev) => prev.map((s) => ({ ...s, enabled: true })));
        } else {
          // 停用除第一個以外的所有 Skills（至少必須保留一個）
          const firstSkill = availableSkills[0]?.name;
          if (!firstSkill) return;
          await updateEnabledSkills(projectId, [firstSkill]);
          setAvailableSkills((prev) =>
            prev.map((s) => ({ ...s, enabled: s.name === firstSkill }))
          );
        }

        // 重新整理樹狀結構
        const treeData = await fetchSkillsTree(projectId);
        setTree(treeData);

        // 若目前正在檢視 System Prompt，則重新整理內容
        if (selectedType === 'system_prompt') {
          const prompt = await fetchSystemPrompt(systemPromptParams);
          setContent(prompt);
        }

        toast.success(enableAll ? '已啟用所有 Skills' : '已將 Skills 精簡為最小集合');
      } catch (error) {
        console.error('更新所有 Skills 狀態失敗:', error);
        toast.error('更新 Skills 失敗');
      } finally {
        setIsUpdatingSkills(false);
      }
    },
    [projectId, availableSkills, selectedType, systemPromptParams]
  );

  const enabledCount = availableSkills.filter((s) => s.enabled).length;
  const totalCount = availableSkills.length;
  const isMarkdownFile = selectedType === 'system_prompt' || selectedPath?.endsWith('.md');

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 內容 */}
      <div className="relative z-10 flex w-full h-full m-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] shadow-2xl overflow-hidden">
        {/* 左側邊欄 - 導覽 */}
        <div className="w-72 flex-shrink-0 border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]/30 flex flex-col">
          {/* 標頭 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
            <h2 className="text-sm font-semibold text-[var(--color-text-heading)]">
              Skills 與 Docs
            </h2>
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]">
              {enabledCount}/{totalCount}
            </span>
          </div>

          {/* 導覽內容 */}
          <div className="flex-1 overflow-y-auto p-2">
            {/* System Prompt */}
            <button
              onClick={handleSelectSystemPrompt}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors mb-2',
                selectedType === 'system_prompt'
                  ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)]'
              )}
            >
              <Sparkles className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="font-medium">System Prompt</span>
            </button>

            {/* 分隔線 */}
            <div className="my-2 border-t border-[var(--color-border)]" />

            {/* 操作按鈕列 */}
            <div className="flex gap-1.5 mb-3">
              {/* 重新載入 Skills 按鈕 */}
              <button
                onClick={handleReloadSkills}
                disabled={isReloading}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-medium bg-[var(--color-accent-primary)] text-white hover:bg-[var(--color-accent-secondary)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
              >
                <RefreshCw className={cn('h-3 w-3 flex-shrink-0', isReloading && 'animate-spin')} />
                <span>{isReloading ? '重新載入中...' : '重新載入'}</span>
              </button>

              {/* 全部啟用 / 全部停用 */}
              <button
                onClick={() => handleToggleAll(true)}
                disabled={isUpdatingSkills || enabledCount === totalCount}
                className="flex items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                全部開啟
              </button>
              <button
                onClick={() => handleToggleAll(false)}
                disabled={isUpdatingSkills || enabledCount <= 1}
                className="flex items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                最小化
              </button>
            </div>

            {/* Skills 標籤 */}
            <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              Skills
            </div>

            {/* Skills 清單與切換開關 */}
            {isLoadingTree ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-muted)]" />
              </div>
            ) : availableSkills.length === 0 ? (
              <div className="px-2 py-4 text-xs text-[var(--color-text-muted)]">
                目前沒有可用的 Skills
              </div>
            ) : (
              <div className="space-y-0.5">
                {availableSkills.map((skill) => (
                  <div
                    key={skill.name}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors group',
                      !skill.enabled && 'opacity-50'
                    )}
                  >
                    <Toggle
                      checked={skill.enabled}
                      onChange={(checked) => handleToggleSkill(skill.name, checked)}
                      disabled={isUpdatingSkills}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-[var(--color-text-primary)] truncate text-[11px]">
                        {skill.name}
                      </div>
                      <div className="text-[var(--color-text-muted)] truncate text-[10px] leading-tight">
                        {skill.description}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 檔案樹（預設收合並置於分隔線後方） */}
            {tree.length > 0 && (
              <>
                <div className="my-3 border-t border-[var(--color-border)]" />
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  Skill 檔案
                </div>
                <div className="space-y-0.5">
                  {tree.map((node) => (
                    <TreeNode
                      key={node.path}
                      node={node}
                      level={0}
                      selectedPath={selectedPath}
                      expandedPaths={expandedPaths}
                      onSelect={handleSelectSkill}
                      onToggle={handleToggle}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* 右側面板 - 內容 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 標頭 */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
            <div className="flex items-center gap-2 min-w-0">
              {selectedType === 'system_prompt' ? (
                <>
                  <Sparkles className="h-4 w-4 flex-shrink-0 text-[var(--color-accent-primary)]" />
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-[var(--color-text-heading)] truncate">
                      System Prompt
                    </h3>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      注入至 Claude Code 的指示
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4 flex-shrink-0 text-[var(--color-accent-secondary)]" />
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-[var(--color-text-heading)] truncate">
                      {selectedPath?.split('/').pop() || '選擇檔案'}
                    </h3>
                    <p className="text-xs text-[var(--color-text-muted)] truncate">
                      {selectedPath || '從側邊欄選擇一個 Skill 檔案'}
                    </p>
                  </div>
                </>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* 切換 Markdown 的原始碼／渲染檢視 */}
              {isMarkdownFile && (
                <button
                  onClick={() => setShowRawCode(!showRawCode)}
                  className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors',
                    showRawCode
                      ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]'
                  )}
                >
                  {showRawCode ? (
                    <>
                      <Eye className="h-3 w-3" />
                      渲染檢視
                    </>
                  ) : (
                    <>
                      <Code className="h-3 w-3" />
                      原始碼
                    </>
                  )}
                </button>
              )}

              {/* 關閉按鈕 */}
              <button
                onClick={onClose}
                className="p-1 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* 內容區域 */}
          <div className="flex-1 overflow-y-auto p-5">
            {isLoadingContent ? (
              <div className="flex items-center justify-center py-20">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent-primary)]" />
                  <p className="text-xs text-[var(--color-text-muted)]">載入中...</p>
                </div>
              </div>
            ) : showRawCode || !isMarkdownFile ? (
              <pre className="text-xs font-mono text-[var(--color-text-primary)] whitespace-pre-wrap break-words bg-[var(--color-bg-secondary)]/50 p-4 rounded-lg border border-[var(--color-border)]">
                {content}
              </pre>
            ) : (
              <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-xs leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
