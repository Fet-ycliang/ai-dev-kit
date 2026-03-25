# SQL 指令稿、預存程序、遞迴 CTE 和交易

> Databricks SQL 基於 SQL/PSM 標準的程序延伸。涵蓋 SQL 指令稿（複合陳述式、控制流、異常處理）、預存程序、遞迴 CTE 和多陳述式交易。

---

## 目錄

- [SQL 指令稿](#sql-指令稿)
  - [複合陳述式 (BEGIN...END)](#複合陳述式-beginend)
  - [變數宣告 (DECLARE)](#變數宣告-declare)
  - [變數賦值 (SET)](#變數賦值-set)
  - [控制流](#控制流)
    - [IF / ELSEIF / ELSE](#if--elseif--else)
    - [CASE 陳述式](#case-陳述式)
    - [WHILE 迴圈](#while-迴圈)
    - [FOR 迴圈](#for-迴圈)
    - [LOOP 陳述式](#loop-陳述式)
    - [REPEAT 陳述式](#repeat-陳述式)
    - [LEAVE 和 ITERATE](#leave-和-iterate)
  - [異常處理](#異常處理)
    - [條件宣告](#條件宣告)
    - [處理器宣告](#處理器宣告)
    - [SIGNAL 和 RESIGNAL](#signal-和-resignal)
  - [EXECUTE IMMEDIATE (動態 SQL)](#execute-immediate-動態-sql)
- [預存程序](#預存程序)
  - [CREATE PROCEDURE](#create-procedure)
  - [CALL (叫用程序)](#call-叫用程序)
  - [DROP PROCEDURE](#drop-procedure)
  - [DESCRIBE PROCEDURE](#describe-procedure)
  - [SHOW PROCEDURES](#show-procedures)
- [遞迴 CTE](#遞迴-cte)
  - [WITH RECURSIVE 語法](#with-recursive-語法)
  - [基礎與遞迴成員](#基礎與遞迴成員)
  - [MAX RECURSION LEVEL](#max-recursion-level)
  - [使用案例和範例](#使用案例和範例)
  - [限制](#限制)
- [多陳述式交易](#多陳述式交易)
  - [概述和現狀](#概述和現狀)
  - [SQL 指令稿原子塊](#sql-指令稿原子塊)
  - [Python 連接器交易 API](#python-連接器交易-api)
  - [隔離層級](#隔離層級)
  - [寫入衝突和並行處理](#寫入衝突和並行處理)
  - [最佳實踐](#最佳實踐)

---

## SQL 指令稿

**可用性**：Databricks Runtime 16.3+ 和 Databricks SQL

SQL 指令稿使用 SQL/PSM 標準啟用程序邏輯。每個 SQL 指令稿以複合陳述式區塊 (`BEGIN...END`) 開始。

### 複合陳述式 (BEGIN...END)

複合陳述式是基本建構區塊，包含變數宣告、條件/處理器宣告和可執行陳述式。

**語法**：

```sql
[ label : ] BEGIN
  [ { declare_variable | declare_condition } ; [...] ]
  [ declare_handler ; [...] ]
  [ SQL_statement ; [...] ]
END [ label ]
```

**關鍵規則**：

- 宣告必須在可執行陳述式之前出現
- 變數宣告先於條件宣告，條件宣告先於處理器宣告
- 頂層複合陳述式無法指定標籤
- `NOT ATOMIC` 為預設且唯一行為（失敗時無自動回復）
- 在筆記本中，複合陳述式必須為儲存格中的唯一陳述式

**主體中支援的陳述式類型**：

| 類別 | 陳述式 |
|------|--------|
| DDL | ALTER, CREATE, DROP |
| DCL | GRANT, REVOKE |
| DML | INSERT, UPDATE, DELETE, MERGE |
| 查詢 | SELECT |
| 賦值 | SET |
| 動態 SQL | EXECUTE IMMEDIATE |
| 控制流 | IF, CASE, WHILE, FOR, LOOP, REPEAT, LEAVE, ITERATE |
| 巢狀 | 巢狀 BEGIN...END 區塊 |

**最小範例**：

```sql
BEGIN
  SELECT 'Hello, SQL Scripting!';
END;
```

### 變數宣告 (DECLARE)

**語法**：

```sql
DECLARE variable_name [, ...] data_type [ DEFAULT default_expr ];
```

- 若未指定 `DEFAULT`，變數初始化為 `NULL`
- 提供 `DEFAULT` 時，資料類型可省略（從運算式推斷）
- Runtime 17.2+ 支援單一 `DECLARE` 中的多個變數名稱
- 變數範圍為其封閉複合陳述式
- 變數名稱解析從最內部範圍向外；使用標籤消除歧義

**範例**：

```sql
BEGIN
  DECLARE counter INT DEFAULT 0;
  DECLARE name STRING DEFAULT 'unknown';
  DECLARE x, y, z DOUBLE DEFAULT 0.0;        -- Runtime 17.2+
  DECLARE inferred DEFAULT current_date();    -- 型別從 current_date() 推斷為 DATE

  SET counter = counter + 1;
  VALUES (counter, name);
END;
```

### 變數賦值 (SET)

**語法**：

```sql
SET variable_name = expression;
SET VAR variable_name = expression;          -- 明確指定本地變數
SET (var1, var2, ...) = (expr1, expr2, ...); -- 多重賦值
```

當存在同名工作階段變數時，使用 `SET VAR` 明確指定本地變數。

**範例**：

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  DECLARE label STRING;
  SET total = 100;
  SET label = 'final';
  VALUES (total, label);
END;
```

### 控制流

#### IF / ELSEIF / ELSE

根據第一個條件評估為 `TRUE` 來執行陳述式。

**語法**：

```sql
IF condition THEN
  { stmt ; } [...]
[ ELSEIF condition THEN
  { stmt ; } [...] ] [...]
[ ELSE
  { stmt ; } [...] ]
END IF;
```

**範例**：

```sql
BEGIN
  DECLARE score INT DEFAULT 85;
  DECLARE grade STRING;

  IF score >= 90 THEN
    SET grade = 'A';
  ELSEIF score >= 80 THEN
    SET grade = 'B';
  ELSEIF score >= 70 THEN
    SET grade = 'C';
  ELSE
    SET grade = 'F';
  END IF;

  VALUES (grade);  -- 傳回 'B'
END;
```

#### CASE 陳述式

兩種形式：**簡單 CASE**（比較運算式）和**搜尋 CASE**（評估布林條件）。

**簡單 CASE 語法**：

```sql
CASE expr
  WHEN opt1 THEN { stmt ; } [...]
  WHEN opt2 THEN { stmt ; } [...]
  [ ELSE { stmt ; } [...] ]
END CASE;
```

**搜尋 CASE 語法**：

```sql
CASE
  WHEN cond1 THEN { stmt ; } [...]
  WHEN cond2 THEN { stmt ; } [...]
  [ ELSE { stmt ; } [...] ]
END CASE;
```

僅第一個符合分支執行。

**範例**：

```sql
BEGIN
  DECLARE status STRING DEFAULT 'active';

  CASE status
    WHEN 'active'   THEN VALUES ('Processing');
    WHEN 'paused'   THEN VALUES ('On hold');
    WHEN 'archived' THEN VALUES ('Read-only');
    ELSE VALUES ('Unknown status');
  END CASE;
END;
```

#### WHILE 迴圈

在條件為 `TRUE` 時重複。

**語法**：

```sql
[ label : ] WHILE condition DO
  { stmt ; } [...]
END WHILE [ label ];
```

**範例** -- 求 1 至 10 的奇數和：

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  DECLARE i INT DEFAULT 0;

  sum_odds: WHILE i < 10 DO
    SET i = i + 1;
    IF i % 2 = 0 THEN
      ITERATE sum_odds;   -- 跳過偶數
    END IF;
    SET total = total + i;
  END WHILE sum_odds;

  VALUES (total);  -- 傳回 25
END;
```

#### FOR 迴圈

在查詢結果列上反覆。

**語法**：

```sql
[ label : ] FOR [ variable_name AS ] query DO
  { stmt ; } [...]
END FOR [ label ];
```

- 使用 `variable_name`（非標籤）限定游標中的欄參考
- 對於 Delta 表，在迭代期間修改來源不影響游標結果
- 若提前由 `LEAVE` 或錯誤終止，迴圈可能不會完全執行查詢

**範例** -- 處理查詢中的每一行：

```sql
BEGIN
  DECLARE total_revenue DOUBLE DEFAULT 0.0;

  process_orders: FOR row AS
    SELECT order_id, amount FROM orders WHERE status = 'completed'
  DO
    SET total_revenue = total_revenue + row.amount;
    IF total_revenue > 1000000 THEN
      LEAVE process_orders;
    END IF;
  END FOR process_orders;

  VALUES (total_revenue);
END;
```

#### LOOP 陳述式

無條件迴圈；必須使用 `LEAVE` 退出。

**語法**：

```sql
[ label : ] LOOP
  { stmt ; } [...]
END LOOP [ label ];
```

**範例**：

```sql
BEGIN
  DECLARE counter INT DEFAULT 0;

  count_up: LOOP
    SET counter = counter + 1;
    IF counter >= 5 THEN
      LEAVE count_up;
    END IF;
  END LOOP count_up;

  VALUES (counter);  -- 傳回 5
END;
```

#### REPEAT 陳述式

至少執行一次，然後在條件為 `TRUE` 時重複。

**語法**：

```sql
[ label : ] REPEAT
  { stmt ; } [...]
  UNTIL condition
END REPEAT [ label ];
```

**範例**：

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  DECLARE i INT DEFAULT 0;

  sum_loop: REPEAT
    SET i = i + 1;
    IF i % 2 != 0 THEN
      SET total = total + i;
    END IF;
    UNTIL i >= 10
  END REPEAT sum_loop;

  VALUES (total);  -- 傳回 25
END;
```

#### LEAVE 和 ITERATE

| 陳述式 | 用途 | 對等 |
|--------|------|------|
| `LEAVE label` | 退出標籤迴圈或複合區塊 | 其他語言的 `BREAK` |
| `ITERATE label` | 跳到標籤迴圈的下次反覆 | 其他語言的 `CONTINUE` |

兩者都需要一個標籤迴圈作為目標。

### 異常處理

#### 條件宣告

定義特定 SQLSTATE 碼的具名條件。

**語法**：

```sql
DECLARE condition_name CONDITION [ FOR SQLSTATE [ VALUE ] sqlstate ];
```

- `sqlstate` 為 5 字元英數字符串（A-Z, 0-9, 大小寫不敏感）
- 不能以 `'00'`、`'01'` 或 `'XX'` 開始
- 未指定時預設為 `'45000'`

**範例**：

```sql
BEGIN
  DECLARE divide_by_zero CONDITION FOR SQLSTATE '22012';
  -- 在下面的處理器宣告中使用
END;
```

#### 處理器宣告

在複合陳述式內捕捉並處理異常。

**語法**：

```sql
DECLARE handler_type HANDLER FOR condition_value [, ...] handler_action;
```

| 參數 | 選項 | 描述 |
|------|------|------|
| `handler_type` | `EXIT` | 處理後退出封閉複合陳述式 |
| `condition_value` | `SQLSTATE 'xxxxx'`、`condition_name`、`SQLEXCEPTION`、`NOT FOUND` | 要捕捉的內容 |
| `handler_action` | 單一陳述式或巢狀 `BEGIN...END` | 執行內容 |

- `SQLEXCEPTION` 捕捉所有錯誤狀態（SQLSTATE 類別非 `'00'` 或 `'01'`）
- `NOT FOUND` 捕捉 `'02xxx'` 狀態（未找到資料）
- 處理器不能套用到其本體內的陳述式

**範例** -- 捕捉除以零：

```sql
BEGIN
  DECLARE result DOUBLE;
  DECLARE EXIT HANDLER FOR SQLSTATE '22012'
    BEGIN
      SET result = -1;
    END;

  SET result = 10 / 0;  -- 觸發處理器
  VALUES (result);       -- 傳回 -1
END;
```

**範例** -- 一般異常處理器：

```sql
BEGIN
  DECLARE error_msg STRING DEFAULT 'none';

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
      SET error_msg = 'An error occurred';
      INSERT INTO error_log (message, ts) VALUES (error_msg, current_timestamp());
    END;

  -- 可能失敗的陳述式
  INSERT INTO target_table SELECT * FROM source_table;
END;
```

#### SIGNAL 和 RESIGNAL

引發或重新引發異常。

**SIGNAL 語法**：

```sql
SIGNAL condition_name
  [ SET { MESSAGE_ARGUMENTS = argument_map | MESSAGE_TEXT = message_str } ];

SIGNAL SQLSTATE [ VALUE ] sqlstate
  [ SET MESSAGE_TEXT = message_str ];
```

**RESIGNAL 語法**（在處理器中使用以保留診斷堆疊）：

```sql
RESIGNAL [ condition_name | SQLSTATE [ VALUE ] sqlstate ]
  [ SET { MESSAGE_ARGUMENTS = argument_map | MESSAGE_TEXT = message_str } ];
```

- 在處理器中傾向使用 `RESIGNAL` 而非 `SIGNAL` -- `RESIGNAL` 保留診斷堆疊，而 `SIGNAL` 清除堆疊
- `MESSAGE_ARGUMENTS` 接收 `MAP<STRING, STRING>` 字面值

**範例** -- 驗證輸入並引發自訂錯誤：

```sql
BEGIN
  DECLARE input_value INT DEFAULT 150;

  IF input_value > 100 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Input value must be <= 100';
  END IF;

  VALUES (input_value);
END;
```

**範例** -- 使用具名條件和 MESSAGE_ARGUMENTS：

```sql
BEGIN
  DECLARE input INT DEFAULT 5;
  DECLARE arg_map MAP<STRING, STRING>;

  IF input > 4 THEN
    SET arg_map = map('errorMessage', 'Input must be <= 4.');
    SIGNAL USER_RAISED_EXCEPTION
      SET MESSAGE_ARGUMENTS = arg_map;
  END IF;
END;
```

### EXECUTE IMMEDIATE (動態 SQL)

在執行時執行構造為字符串的 SQL 陳述式。

**可用性**：Runtime 14.3+；運算式型 `sql_string` 和巢狀執行自 Runtime 17.3+。

**語法**：

```sql
EXECUTE IMMEDIATE sql_string
  [ INTO var_name [, ...] ]
  [ USING { arg_expr [ AS ] [ alias ] } [, ...] ];
```

- `sql_string`：常數運算式，產生格式正確的 SQL 陳述式
- `INTO`：將單行結果捕捉到變數（零行傳回 `NULL`；多行出錯）
- `USING`：將值繫結至位置 (`?`) 或具名 (`:param`) 參數標記（無法混合樣式）

**範例**：

```sql
-- 位置參數
EXECUTE IMMEDIATE 'SELECT SUM(c1) FROM VALUES(?), (?) AS t(c1)' USING 5, 6;

-- 具名參數和 INTO
BEGIN
  DECLARE total INT;
  EXECUTE IMMEDIATE 'SELECT SUM(c1) FROM VALUES(:a), (:b) AS t(c1)'
    INTO total USING (5 AS a, 6 AS b);
  VALUES (total);  -- 傳回 11
END;

-- 動態表操作
BEGIN
  DECLARE table_name STRING DEFAULT 'my_catalog.my_schema.staging';
  EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || table_name;
  EXECUTE IMMEDIATE 'INSERT INTO ' || table_name || ' SELECT * FROM source';
END;
```

---

## 預存程序

**可用性**：公開預覽版 -- Databricks Runtime 17.0+

預存程序在 Unity Catalog 中持久化 SQL 指令稿，並透過 `CALL` 叫用。

### CREATE PROCEDURE

**語法**：

```sql
CREATE [ OR REPLACE ] PROCEDURE [ IF NOT EXISTS ]
    procedure_name ( [ parameter [, ...] ] )
    characteristic [...]
    AS compound_statement
```

**參數定義**：

```sql
[ IN | OUT | INOUT ] parameter_name data_type
  [ DEFAULT default_expression ]
  [ COMMENT parameter_comment ]
```

| 參數模式 | 行為 |
|---------|------|
| `IN`（預設） | 僅輸入；值傳入程序 |
| `OUT` | 僅輸出；初始化為 `NULL`；成功時傳回最終值 |
| `INOUT` | 輸入和輸出；接收值並在成功時傳回修改值 |

**必要特性**：

| 特性 | 描述 |
|------|------|
| `LANGUAGE SQL` | 指定實作語言 |
| `SQL SECURITY INVOKER` | 在叫用者的權限下執行 |

**選用特性**：

| 特性 | 描述 |
|------|------|
| `NOT DETERMINISTIC` | 程序可能以相同輸入傳回不同結果 |
| `MODIFIES SQL DATA` | 程序修改 SQL 資料 |
| `COMMENT 'description'` | 人類可讀描述 |
| `DEFAULT COLLATION UTF8_BINARY` | 當綱要使用非 UTF8_BINARY 校系時需要（Runtime 17.1+） |

**規則**：

- `OR REPLACE` 和 `IF NOT EXISTS` 無法併用
- 程序內參數名稱必須唯一
- `OUT` 參數不支援 `DEFAULT`
- 參數具有 `DEFAULT` 後，所有後續參數也必須具有預設值
- 預設運算式無法參考其他參數或包含子查詢
- 主體在建立時進行語法驗證，但僅在叫用時進行語義驗證

**範例** -- 具輸出參數的 ETL 程序：

```sql
CREATE OR REPLACE PROCEDURE run_daily_etl(
    IN source_schema STRING,
    IN target_schema STRING,
    OUT rows_processed INT,
    OUT status STRING DEFAULT 'pending'
)
LANGUAGE SQL
SQL SECURITY INVOKER
COMMENT '每日訂單處理的 ETL 管道'
AS BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
      SET status = 'failed';
      SET rows_processed = 0;
    END;

  -- 截斷並重新載入
  EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || target_schema || '.orders_daily';

  EXECUTE IMMEDIATE
    'INSERT INTO ' || target_schema || '.orders_daily '
    || 'SELECT * FROM ' || source_schema || '.orders '
    || 'WHERE order_date = current_date()';

  EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM ' || target_schema || '.orders_daily'
    INTO rows_processed;

  SET status = 'success';
END;
```

### CALL (叫用程序)

**語法**：

```sql
CALL procedure_name( [ argument [, ...] ] );
CALL procedure_name( [ named_param => argument ] [, ...] );
```

**規則**：

- 支援最多 64 層巢狀
- 對 `IN` 參數：任何可轉換為參數類型的運算式，或 `DEFAULT`
- 對 `OUT`/`INOUT` 參數：必須為工作階段變數或本地變數
- 引數必須符合參數的資料類型（使用類型字面值，如 `DATE'2025-01-01'`）
- 若其餘參數具有 `DEFAULT` 值，允許更少引數
- 不透過 ODBC 支援

**範例**：

```sql
-- 位置叫用
DECLARE rows_out INT;
DECLARE status_out STRING;
CALL run_daily_etl('raw', 'silver', rows_out, status_out);
SELECT rows_out, status_out;

-- 具名參數叫用
CALL run_daily_etl(
  target_schema => 'silver',
  source_schema => 'raw',
  rows_processed => rows_out,
  status => status_out
);
```

### DROP PROCEDURE

**語法**：

```sql
DROP PROCEDURE [ IF EXISTS ] procedure_name;
```

- 不含 `IF EXISTS` 時，刪除不存在程序會引發 `ROUTINE_NOT_FOUND`
- 需要 `MANAGE` 權限、程序擁有權，或包含綱要/目錄/中繼儲存體的擁有權

**範例**：

```sql
DROP PROCEDURE IF EXISTS run_daily_etl;
```

### DESCRIBE PROCEDURE

**語法**：

```sql
{ DESC | DESCRIBE } PROCEDURE [ EXTENDED ] procedure_name;
```

- 基本：傳回程序名稱和參數列表
- `EXTENDED`：額外傳回擁有者、建立時間、主體、語言、安全類型、決定性、資料存取和組態

**範例**：

```sql
DESCRIBE PROCEDURE EXTENDED run_daily_etl;
```

### SHOW PROCEDURES

**語法**：

```sql
SHOW PROCEDURES [ { FROM | IN } schema_name ];
```

傳回欄：`catalog`、`namespace`、`schema`、`procedure_name`。

**範例**：

```sql
SHOW PROCEDURES IN my_catalog.my_schema;
```

---

## 遞迴 CTE

**可用性**：Databricks Runtime 17.0+ 和 DBSQL 2025.20+

遞迴 CTE 為層級資料、圖形遍歷和系列生成啟用自我參考查詢。

### WITH RECURSIVE 語法

```sql
WITH RECURSIVE cte_name [ ( column_name [, ...] ) ]
  [ MAX RECURSION LEVEL max_level ] AS (
    base_case_query
    UNION ALL
    recursive_query
  )
SELECT ... FROM cte_name;
```

### 基礎與遞迴成員

| 元件 | 描述 |
|------|------|
| **基礎（基底情況）** | 初始查詢提供種子列；必須不參考 CTE 名稱 |
| **遞迴成員** | 參考 CTE 名稱；處理前次反覆的列 |
| **UNION ALL** | 結合基礎和遞迴結果（必要） |

遞迴成員讀取前次反覆產生的列並產生新列。當遞迴成員產生零列時遞迴終止。

### MAX RECURSION LEVEL

```sql
WITH RECURSIVE cte_name MAX RECURSION LEVEL 200 AS (...)
```

| 設定 | 預設 | 描述 |
|------|------|------|
| 最大遞迴深度 | 100 | 超過會引發 `RECURSION_LEVEL_LIMIT_EXCEEDED` |
| 最大結果列 | 1,000,000 | 超過會引發錯誤 |
| `LIMIT ALL` | N/A | 暫停列限制（Runtime 17.2+） |

### 使用案例和範例

**生成數字系列**：

```sql
WITH RECURSIVE numbers(n) AS (
  VALUES (1)
  UNION ALL
  SELECT n + 1 FROM numbers WHERE n < 100
)
SELECT * FROM numbers;
```

**組織層級遍歷**：

```sql
WITH RECURSIVE org_tree AS (
  -- 基礎：從 CEO 開始
  SELECT employee_id, name, manager_id, name AS root_name, 0 AS depth
  FROM employees
  WHERE manager_id IS NULL

  UNION ALL

  -- 遞迴：尋找直屬下屬
  SELECT e.employee_id, e.name, e.manager_id, t.root_name, t.depth + 1
  FROM employees e
  JOIN org_tree t ON e.manager_id = t.employee_id
)
SELECT * FROM org_tree ORDER BY depth, name;
```

**圖形遍歷和循環偵測**：

```sql
WITH RECURSIVE search_graph(f, t, label, path, cycle) AS (
  -- 基礎：所有邊作為起始路徑
  SELECT *, array(struct(g.f, g.t)), false
  FROM graph g

  UNION ALL

  -- 遞迴：擴展路徑、偵測循環
  SELECT g.f, g.t, g.label,
         sg.path || array(struct(g.f, g.t)),
         array_contains(sg.path, struct(g.f, g.t))
  FROM graph g
  JOIN search_graph sg ON g.f = sg.t
  WHERE NOT sg.cycle
)
SELECT * FROM search_graph WHERE NOT cycle;
```

**字符串累積**：

```sql
WITH RECURSIVE r(col) AS (
  SELECT 'a'
  UNION ALL
  SELECT col || char(ascii(substr(col, -1)) + 1)
  FROM r
  WHERE length(col) < 10
)
SELECT * FROM r;
-- a, ab, abc, abcd, ..., abcdefghij
```

**物料清單 (BOM) 爆炸**：

```sql
WITH RECURSIVE bom AS (
  -- 基礎：頂層產品
  SELECT part_id, component_id, quantity, 1 AS level
  FROM bill_of_materials
  WHERE part_id = 'PROD-001'

  UNION ALL

  -- 遞迴：子元件
  SELECT b.part_id, b.component_id, b.quantity * bom.quantity, bom.level + 1
  FROM bill_of_materials b
  JOIN bom ON b.part_id = bom.component_id
)
SELECT component_id, SUM(quantity) AS total_quantity, MAX(level) AS max_depth
FROM bom
GROUP BY component_id
ORDER BY total_quantity DESC;
```

### 限制

- UPDATE、DELETE 或 MERGE 陳述式中不支援
- 步驟（遞迴）查詢無法包含與 CTE 名稱的相關欄參考
- 隨機數字產生器可能在各反覆間產生相同值
- 預設列限制 1,000,000 列（Runtime 17.2+ 使用 `LIMIT ALL` 覆蓋）
- 預設遞迴深度 100（使用 `MAX RECURSION LEVEL` 覆蓋）

---

## 多陳述式交易

### 概述和現狀

多陳述式交易 (MST) 允許將多個 SQL 陳述式分組為原子單位，要不完全成功，要不完全失敗。

| 功能 | 狀態 | 說明 |
|------|------|------|
| 單表交易 | GA | Delta Lake 預設；每個 DML 陳述式為原子 |
| 多陳述式交易 (SQL 指令稿) | 預覽版 | `BEGIN ATOMIC...END` 區塊 |
| 多陳述式交易 (Python 連接器) | 預覽版 | `connection.autocommit = False` 模式 |
| 跨表交易 | 預覽版 | 在多個 Delta 表中原子更新 |

### SQL 指令稿原子塊

使用 `BEGIN ATOMIC...END` 以單一原子單位執行多個陳述式：

```sql
BEGIN ATOMIC
  INSERT INTO customers (id, name) VALUES (1, 'Alice');
  INSERT INTO orders (id, customer_id, amount) VALUES (1, 1, 250.00);
  INSERT INTO audit_log (action, ts) VALUES ('new_customer_order', current_timestamp());
END;
```

若任何陳述式失敗，所有變更會回復。

> **注意**：在 `BEGIN ATOMIC` 區塊中使用的表必須啟用 `catalogManaged` 表功能。使用 `TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')` 建立表。現有表無法就地升級 -- 必須使用此屬性重新建立。

### Python 連接器交易 API

Databricks SQL Python 連接器提供明確交易控制：

```python
from databricks import sql

connection = sql.connect(
    server_hostname="...",
    http_path="...",
    access_token="..."
)

# 禁用自動認可以啟動明確交易
connection.autocommit = False
cursor = connection.cursor()

try:
    cursor.execute("INSERT INTO customers VALUES (1, 'Alice')")
    cursor.execute("INSERT INTO orders VALUES (1, 1, 100.00)")
    cursor.execute("INSERT INTO shipments VALUES (1, 1, 'pending')")
    connection.commit()    # 三者以原子方式成功
except Exception:
    connection.rollback()  # 三者都捨棄
finally:
    connection.autocommit = True
```

**關鍵 API 方法**：

| 方法 | 描述 |
|------|------|
| `connection.autocommit = False` | 啟動明確交易模式 |
| `connection.commit()` | 認可目前交易 |
| `connection.rollback()` | 捨棄目前交易中的所有變更 |
| `connection.get_transaction_isolation()` | 傳回目前隔離層級 |
| `connection.set_transaction_isolation(level)` | 設定隔離層級 |

**錯誤處理**：

- 在無作用交易時認可會引發 `sql.TransactionError`
- 交易作用時無法變更 `autocommit`
- 無交易作用時 `rollback()` 為安全無操作

### 隔離層級

Databricks 使用**快照隔離**（在標準 SQL 術語中對應至 `REPEATABLE_READ`）。

| 層級 | 描述 | 預設 |
|------|------|------|
| `WriteSerializable` | 僅寫入可序列化；並行寫入可能重新排序 | 是（表預設） |
| `Serializable` | 讀取和寫入都可序列化；最嚴格隔離 | 否 |
| `REPEATABLE_READ` | 連接器層級交易的快照隔離 | 連接器預設 |

**在表層級設定隔離**：

```sql
ALTER TABLE my_table
SET TBLPROPERTIES ('delta.isolationLevel' = 'Serializable');
```

**在 Python 連接器中設定隔離**：

```python
from databricks.sql import TRANSACTION_ISOLATION_LEVEL_REPEATABLE_READ

connection.set_transaction_isolation(TRANSACTION_ISOLATION_LEVEL_REPEATABLE_READ)
# 僅支援 REPEATABLE_READ；其他會引發 NotSupportedError
```

**快照隔離行為**：

- **可重複讀取**：交易內讀取的資料保持一致
- **原子認可**：變更對其他連接不可見，直到認可
- **寫入衝突**：對同表的並行寫入導致衝突
- **跨表寫入**：對不同表的並行寫入可成功

### 寫入衝突和並行處理

**列層級並行處理**（Runtime 14.2+）減少具有刪除向量或液體叢集的表衝突：

| 操作 | WriteSerializable | Serializable |
|------|------------------|--------------|
| INSERT 對 INSERT | 無衝突 | 無衝突 |
| UPDATE/DELETE/MERGE 對相同 | 無衝突（不同列） | 可能衝突 |
| OPTIMIZE 對並行 DML | 僅與 ZORDER BY 衝突 | 可能衝突 |

**常見衝突例外**：

| 例外 | 原因 |
|------|------|
| `ConcurrentAppendException` | 對相同分割區的並行附加 |
| `ConcurrentDeleteReadException` | 正讀取檔案的並行刪除 |
| `MetadataChangedException` | 並行 ALTER TABLE 或綱要變更 |
| `ProtocolChangedException` | 寫入期間通訊協定版本升級 |

### 最佳實踐

1. **保持交易簡短**以最小化衝突窗口
2. **始終用 try/except/finally 包裝**，失敗時回復
3. **在 `finally` 區塊中還原自動認可**
4. **在 MERGE 條件中使用分割區修剪**以減少衝突範圍
5. **啟用列層級並行處理**（刪除向量 + 液體叢集）以進行高並行工作負載
6. **傾向於單一陳述式 MERGE** 而非多陳述式交易（更新單表時）
7. **認可並重啟交易**以查看其他連接所進行的變更

---

## Runtime 版本參考

| 功能 | 最低 Runtime | 狀態 |
|------|-------------|------|
| SQL 指令稿（複合陳述式、控制流） | 16.3 | GA |
| 預存程序 (CREATE/CALL/DROP PROCEDURE) | 17.0 | 公開預覽版 |
| 遞迴 CTE (WITH RECURSIVE) | 17.0 / DBSQL 2025.20 | GA |
| 多變數 DECLARE | 17.2 | GA |
| EXECUTE IMMEDIATE（基本） | 14.3 | GA |
| EXECUTE IMMEDIATE（運算式、巢狀） | 17.3 | GA |
| 遞迴 CTE LIMIT ALL | 17.2 | GA |
| 多陳述式交易 | 依功能而異 | 預覽版 |
| 列層級並行處理 | 14.2 | GA |

---

## 快速參考卡

### SQL 指令稿骨架

```sql
BEGIN
  -- 1. 宣告
  DECLARE var1 INT DEFAULT 0;
  DECLARE var2 STRING;
  DECLARE my_error CONDITION FOR SQLSTATE '45000';
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
      -- 錯誤處理邏輯
    END;

  -- 2. 邏輯
  IF var1 > 0 THEN
    SET var2 = 'positive';
  ELSE
    SET var2 = 'non-positive';
  END IF;

  -- 3. 輸出
  VALUES (var1, var2);
END;
```

### 預存程序骨架

```sql
CREATE OR REPLACE PROCEDURE my_schema.my_proc(
    IN  input_param STRING,
    OUT output_param INT
)
LANGUAGE SQL
SQL SECURITY INVOKER
COMMENT '此程序執行的操作描述'
AS BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
    SET output_param = -1;

  -- 程序主體
  SET output_param = (SELECT COUNT(*) FROM my_table WHERE col = input_param);
END;

-- 叫用
DECLARE result INT;
CALL my_schema.my_proc('value', result);
SELECT result;
```

### 遞迴 CTE 骨架

```sql
WITH RECURSIVE cte_name (col1, col2) MAX RECURSION LEVEL 50 AS (
  -- 基礎
  SELECT seed_col1, seed_col2
  FROM base_table
  WHERE condition

  UNION ALL

  -- 遞迴步驟
  SELECT derived_col1, derived_col2
  FROM source_table s
  JOIN cte_name c ON s.parent = c.col1
)
SELECT * FROM cte_name;
```
