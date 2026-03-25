/**
 * 與後端 API 與資料庫模型對應的型別。
 */

/** 來自 GET /api/me 的目前使用者資訊 */
export interface UserInfo {
  user: string;
  workspace_url: string | null;
  lakebase_configured: boolean;
  lakebase_project_id: string | null;
  lakebase_error: string | null;
}

/** 來自 API 的專案（專案列表 / 詳細資料） */
export interface Project {
  id: string;
  name: string;
  user_email: string;
  created_at: string | null;
  conversation_count: number;
}

/** 對話摘要（列表）或完整內容（含訊息的詳細資料） */
export interface Conversation {
  id: string;
  project_id: string;
  title: string;
  created_at: string | null;
  session_id?: string | null;
  cluster_id?: string | null;
  default_catalog?: string | null;
  default_schema?: string | null;
  warehouse_id?: string | null;
  workspace_folder?: string | null;
  messages?: Message[];
  message_count?: number;
}

/** 對話中的單一訊息 */
export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string | null;
  is_error: boolean;
}

/** 來自 GET /api/clusters 的 Databricks cluster */
export interface Cluster {
  cluster_id: string;
  cluster_name: string | null;
  state: string;
  creator_user_name?: string | null;
}

/** 來自 GET /api/warehouses 的 Databricks SQL warehouse */
export interface Warehouse {
  warehouse_id: string;
  warehouse_name: string | null;
  state: string;
  cluster_size?: string | null;
  creator_name?: string | null;
  is_serverless?: boolean;
}

/** 來自代理 TodoWrite 工具的待辦項目 */
export interface TodoItem {
  id?: string;
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

/** 來自 GET .../skills/available、帶有啟用狀態的 Skill */
export interface AvailableSkill {
  name: string;
  description: string;
  enabled: boolean;
}

/** 來自 GET .../executions 的進行中或最近執行資料 */
export interface Execution {
  id: string;
  conversation_id: string;
  project_id: string;
  status: string;
  events: unknown[];
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}
