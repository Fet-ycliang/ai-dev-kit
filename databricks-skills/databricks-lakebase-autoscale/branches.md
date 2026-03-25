# Lakebase 自動擴展分支

## 概觀

Lakebase 自動擴展中的分支是隔離的資料庫環境，透過寫時複製機制與父分支共享存儲。它們為資料庫啟用類似 Git 的工作流程：建立隔離的開發/測試環境、安全地測試架構變更，並從錯誤中恢復。

## 分支類型

| 選項 | 說明 | 使用場景 |
|--------|-------------|----------|
| **最新資料** | 從父分支的最新狀態建立分支 | 開發、使用最新資料進行測試 |
| **過去資料** | 從特定時間點建立分支 | 時間點恢復、歷史分析 |

## 建立分支

### 設定過期時間（TTL）

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

w = WorkspaceClient()

# 建立具有 7 天過期時間的分支
result = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(
        spec=BranchSpec(
            source_branch="projects/my-app/branches/production",
            ttl=Duration(seconds=604800)  # 7 天
        )
    ),
    branch_id="development"
).wait()

print(f"分支已建立：{result.name}")
print(f"過期時間：{result.status.expire_time}")
```

### 永久分支（無過期時間）

```python
result = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(
        spec=BranchSpec(
            source_branch="projects/my-app/branches/production",
            no_expiry=True
        )
    ),
    branch_id="staging"
).wait()
```

### CLI

```bash
# 設定 TTL
databricks postgres create-branch projects/my-app development \
    --json '{
        "spec": {
            "source_branch": "projects/my-app/branches/production",
            "ttl": "604800s"
        }
    }'

# 永久
databricks postgres create-branch projects/my-app staging \
    --json '{
        "spec": {
            "source_branch": "projects/my-app/branches/production",
            "no_expiry": true
        }
    }'
```

## 取得分支詳細資訊

```python
branch = w.postgres.get_branch(
    name="projects/my-app/branches/development"
)

print(f"分支：{branch.name}")
print(f"受保護：{branch.status.is_protected}")
print(f"預設值：{branch.status.default}")
print(f"狀態：{branch.status.current_state}")
print(f"大小：{branch.status.logical_size_bytes} 位元組")
```

## 列出分支

```python
branches = list(w.postgres.list_branches(
    parent="projects/my-app"
))

for branch in branches:
    print(f"分支：{branch.name}")
    print(f"  預設值：{branch.status.default}")
    print(f"  受保護：{branch.status.is_protected}")
```

## 保護分支

受保護的分支無法刪除、重設或封存。

```python
from databricks.sdk.service.postgres import Branch, BranchSpec, FieldMask

w.postgres.update_branch(
    name="projects/my-app/branches/production",
    branch=Branch(
        name="projects/my-app/branches/production",
        spec=BranchSpec(is_protected=True)
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected"])
).wait()
```

移除保護：

```python
w.postgres.update_branch(
    name="projects/my-app/branches/production",
    branch=Branch(
        name="projects/my-app/branches/production",
        spec=BranchSpec(is_protected=False)
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected"])
).wait()
```

## 更新分支過期時間

```python
# 延長至 14 天
w.postgres.update_branch(
    name="projects/my-app/branches/development",
    branch=Branch(
        name="projects/my-app/branches/development",
        spec=BranchSpec(
            is_protected=False,
            ttl=Duration(seconds=1209600)  # 14 天
        )
    ),
    update_mask=FieldMask(field_mask=["spec.is_protected", "spec.expiration"])
).wait()

# 移除過期時間
w.postgres.update_branch(
    name="projects/my-app/branches/development",
    branch=Branch(
        name="projects/my-app/branches/development",
        spec=BranchSpec(no_expiry=True)
    ),
    update_mask=FieldMask(field_mask=["spec.expiration"])
).wait()
```

## 從父分支重設分支

重設會完全將分支的資料和架構替換為來自父分支的最新資料。本機變更會遺失。

```python
w.postgres.reset_branch(
    name="projects/my-app/branches/development"
).wait()
```

**限制：**
- 根分支（如 `production`）無法重設（沒有父分支）
- 有子分支的分支無法重設（先刪除子分支）
- 在重設期間，連線會暫時中斷

## 刪除分支

```python
w.postgres.delete_branch(
    name="projects/my-app/branches/development"
).wait()
```

**限制：**
- 無法刪除有子分支的分支（先刪除子分支）
- 無法刪除受保護的分支（先移除保護）
- 無法刪除預設分支

## 分支過期

分支過期設定自動刪除時戳。適用於：
- **CI/CD 環境**：2-4 小時
- **示範**：24-48 小時
- **功能開發**：1-7 天
- **長期測試**：最多 30 天

**最大過期期間：** 自目前時間起 30 天。

### 過期限制

- 無法過期受保護的分支
- 無法過期預設分支
- 無法過期有子分支的分支
- 分支過期時，所有計算資源也會被刪除

## 最佳實務

1. **對臨時分支使用 TTL**：為開發/測試分支設定過期時間以避免累積
2. **保護生產分支**：防止意外刪除或重設
3. **重設而不是重新建立**：當需要新鮮資料但無需新建分支開銷時，使用從父分支重設
4. **合併前比較架構**：在將變更應用到生產環境之前，比較分支間的架構
5. **監控未封存限制**：每個專案最多允許 10 個未封存分支
