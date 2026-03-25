import pathlib

content = """\
# Databricks SQL 中的地理空間 SQL 與定序

---

## 第一部分：地理空間 SQL

Databricks SQL 透過兩個函式家族提供完整的地理空間支援：**H3 函式**用於六邊形格網索引，**ST 函式**用於標準空間操作。兩者合力在大規模環境下實現高效能地理空間分析。

### 地理空間資料型別

| 型別 | 說明 | 座標系統 | SRID 支援 |
|------|-------------|-------------------|--------------|
| `GEOMETRY` | 使用歐幾里得座標（X、Y，選用 Z）的空間物件 -- 將地球視為平面 | 任何投影 CRS | 11,000+ SRIDs |
| `GEOGRAPHY` | 使用經緯度在地球表面上的地理物件 | WGS 84 | 僅 SRID 4326 |

**使用時機：**
- 使用 `GEOMETRY` 處理投影座標系統、歐幾里得距離計算，以及以公尺或英尺為單位的本地/區域資料。
- 使用 `GEOGRAPHY` 處理使用經緯度座標的全球資料及球面距離計算。

### 支援的幾何子型別

`GEOMETRY` 與 `GEOGRAPHY` 均支援：**Point**、**LineString**、**Polygon**、**MultiPoint**、**MultiLineString**、**MultiPolygon** 及 **GeometryCollection**。

### 格式支援

| 格式 | 說明 | 匯入函式 | 匯出函式 |
|--------|-------------|-----------------|-----------------|
| WKT | Well-Known Text | `ST_GeomFromWKT`, `ST_GeogFromWKT` | `ST_AsWKT`, `ST_AsText` |
| WKB | Well-Known Binary | `ST_GeomFromWKB`, `ST_GeogFromWKB` | `ST_AsWKB`, `ST_AsBinary` |
| EWKT | Extended WKT（包含 SRID） | `ST_GeomFromEWKT`, `ST_GeogFromEWKT` | `ST_AsEWKT` |
| EWKB | Extended WKB（包含 SRID） | `ST_GeomFromEWKB` | `ST_AsEWKB` |
| GeoJSON | 基於 JSON 的格式 | `ST_GeomFromGeoJSON`, `ST_GeogFromGeoJSON` | `ST_AsGeoJSON` |
| Geohash | 階層式格網編碼 | `ST_GeomFromGeoHash`, `ST_PointFromGeoHash` | `ST_GeoHash` |

---

### H3 地理空間函式

H3 是 Uber 的六邊形階層式空間索引。它以 16 種解析度（0-15）將地球劃分為六邊形格子。自 Databricks Runtime 11.2 起可用（H3 Java 函式庫 3.7.0）。無需另行安裝。

#### H3 匯入函式（座標/幾何轉 H3）

| 函式 | 說明 | 回傳 |
|----------|-------------|---------|
| `h3_longlatash3(lon, lat, resolution)` | 將經緯度轉換為 H3 格子 ID | `BIGINT` |
| `h3_longlatash3string(lon, lat, resolution)` | 將經緯度轉換為 H3 格子 ID | `STRING`（十六進位） |
| `h3_pointash3(geogExpr, resolution)` | 將 GEOGRAPHY 點轉換為 H3 格子 ID | `BIGINT` |
| `h3_pointash3string(geogExpr, resolution)` | 將 GEOGRAPHY 點轉換為 H3 格子 ID | `STRING`（十六進位） |
| `h3_polyfillash3(geogExpr, resolution)` | 以包含的 H3 格子填充多邊形 | `ARRAY<BIGINT>` |
| `h3_polyfillash3string(geogExpr, resolution)` | 以包含的 H3 格子填充多邊形 | `ARRAY<STRING>` |
| `h3_coverash3(geogExpr, resolution)` | 以最小集合的 H3 格子覆蓋地理區域 | `ARRAY<BIGINT>` |
| `h3_coverash3string(geogExpr, resolution)` | 以最小集合的 H3 格子覆蓋地理區域 | `ARRAY<STRING>` |
| `h3_tessellateaswkb(geogExpr, resolution)` | 使用 H3 格子對地理區域進行鑲嵌 | `ARRAY<STRUCT>` |
| `h3_try_polyfillash3(geogExpr, resolution)` | 安全填充（錯誤時回傳 NULL） | `ARRAY<BIGINT>` |
| `h3_try_polyfillash3string(geogExpr, resolution)` | 安全填充（錯誤時回傳 NULL） | `ARRAY<STRING>` |
| `h3_try_coverash3(geogExpr, resolution)` | 安全覆蓋（錯誤時回傳 NULL） | `ARRAY<BIGINT>` |
| `h3_try_coverash3string(geogExpr, resolution)` | 安全覆蓋（錯誤時回傳 NULL） | `ARRAY<STRING>` |
| `h3_try_tessellateaswkb(geogExpr, resolution)` | 安全鑲嵌（錯誤時回傳 NULL） | `ARRAY<STRUCT>` |

#### H3 匯出函式（H3 轉幾何/格式）

| 函式 | 說明 | 回傳 |
|----------|-------------|---------|
| `h3_boundaryaswkt(h3CellId)` | H3 格子邊界（WKT 多邊形） | `STRING` |
| `h3_boundaryaswkb(h3CellId)` | H3 格子邊界（WKB 多邊形） | `BINARY` |
| `h3_boundaryasgeojson(h3CellId)` | H3 格子邊界（GeoJSON） | `STRING` |
| `h3_centeraswkt(h3CellId)` | H3 格子中心（WKT 點） | `STRING` |
| `h3_centeraswkb(h3CellId)` | H3 格子中心（WKB 點） | `BINARY` |
| `h3_centerasgeojson(h3CellId)` | H3 格子中心（GeoJSON 點） | `STRING` |

#### H3 轉換函式

| 函式 | 說明 |
|----------|-------------|
| `h3_h3tostring(h3CellId)` | 將 BIGINT 格子 ID 轉換為十六進位 STRING |
| `h3_stringtoh3(h3CellIdString)` | 將十六進位 STRING 轉換為 BIGINT 格子 ID |

#### H3 階層 / 遍歷函式

| 函式 | 說明 |
|----------|-------------|
| `h3_resolution(h3CellId)` | 取得格子的解析度 |
| `h3_toparent(h3CellId, resolution)` | 取得較粗解析度的父格子 |
| `h3_tochildren(h3CellId, resolution)` | 取得較細解析度的所有子格子 |
| `h3_maxchild(h3CellId, resolution)` | 取得值最大的子格子 |
| `h3_minchild(h3CellId, resolution)` | 取得值最小的子格子 |
| `h3_ischildof(h3CellId1, h3CellId2)` | 測試 cell1 是否等於或為 cell2 的子格子 |

#### H3 距離 / 鄰域函式

| 函式 | 說明 |
|----------|-------------|
| `h3_distance(h3CellId1, h3CellId2)` | 兩格子之間的格網距離 |
| `h3_try_distance(h3CellId1, h3CellId2)` | 格網距離，未定義時回傳 NULL |
| `h3_kring(h3CellId, k)` | 格網距離 k 以內的所有格子（填充圓盤） |
| `h3_kringdistances(h3CellId, k)` | 距離 k 以內的格子及其距離 |
| `h3_hexring(h3CellId, k)` | 恰好在距離 k 的空心環形格子 |

#### H3 壓縮函式

| 函式 | 說明 |
|----------|-------------|
| `h3_compact(h3CellIds)` | 將格子陣列壓縮為最小表示 |
| `h3_uncompact(h3CellIds, resolution)` | 將壓縮格子展開至目標解析度 |

#### H3 驗證函式

| 函式 | 說明 |
|----------|-------------|
| `h3_isvalid(expr)` | 檢查 BIGINT 或 STRING 是否為有效的 H3 格子 |
| `h3_validate(h3CellId)` | 有效時回傳格子 ID，否則報錯 |
| `h3_try_validate(h3CellId)` | 有效時回傳格子 ID，否則回傳 NULL |
| `h3_ispentagon(h3CellId)` | 檢查格子是否為五邊形（每種解析度 12 個） |

#### H3 範例

```sql
-- 以解析度 9 將座標轉換為 H3 格子
SELECT h3_longlatash3(-73.985428, 40.748817, 9) AS h3_cell;

-- 依接送地點對計程車行程建立 H3 索引
CREATE TABLE trips_h3 AS
SELECT
  h3_longlatash3(pickup_longitude, pickup_latitude, 12) AS pickup_cell,
  h3_longlatash3(dropoff_longitude, dropoff_latitude, 12) AS dropoff_cell,
  *
FROM taxi_trips;

-- 以 H3 格子填充郵遞區號多邊形以建立空間索引
CREATE TABLE zipcode_h3 AS
SELECT
  explode(h3_polyfillash3(geom_wkt, 12)) AS cell,
  zipcode, city, state
FROM zipcodes;

-- 使用 H3 join 尋找特定郵遞區號內的所有行程
SELECT t.*
FROM trips_h3 t
INNER JOIN zipcode_h3 z ON t.pickup_cell = z.cell
WHERE z.zipcode = '10001';

-- 鄰近搜尋：尋找某位置 2 環內的所有 H3 格子
SELECT explode(h3_kring(h3_longlatash3(-73.985, 40.748, 9), 2)) AS nearby_cell;

-- 彙總行程數量並取得視覺化用的中心點
SELECT
  dropoff_cell,
  h3_centerasgeojson(dropoff_cell):coordinates[0] AS lon,
  h3_centerasgeojson(dropoff_cell):coordinates[1] AS lat,
  count(*) AS trip_count
FROM trips_h3
GROUP BY dropoff_cell;

-- 上捲至較粗解析度
SELECT
  h3_toparent(pickup_cell, 7) AS parent_cell,
  count(*) AS trip_count
FROM trips_h3
GROUP BY h3_toparent(pickup_cell, 7);

-- 壓縮一組格子以利高效儲存
SELECT h3_compact(collect_set(cell)) AS compacted
FROM zipcode_h3
WHERE zipcode = '10001';
```

---

### ST 地理空間函式

在 `GEOMETRY` 和 `GEOGRAPHY` 型別上操作的原生空間 SQL 函式。需要 Databricks Runtime 17.1+。公開預覽版。提供超過 80 個函式。

#### ST 匯入函式（建立 Geometry/Geography）

| 函式 | 說明 | 輸出型別 |
|----------|-------------|-------------|
| `ST_GeomFromText(wkt [, srid])` | 從 WKT 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromWKT(wkt [, srid])` | 從 WKT 建立 GEOMETRY（別名） | `GEOMETRY` |
| `ST_GeomFromWKB(wkb [, srid])` | 從 WKB 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromEWKT(ewkt)` | 從 Extended WKT 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromEWKB(ewkb)` | 從 Extended WKB 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromGeoJSON(geojson)` | 從 GeoJSON 建立 GEOMETRY(4326) | `GEOMETRY` |
| `ST_GeomFromGeoHash(geohash)` | 從 geohash 建立多邊形 GEOMETRY | `GEOMETRY` |
| `ST_GeogFromText(wkt)` | 從 WKT 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_GeogFromWKT(wkt)` | 從 WKT 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_GeogFromWKB(wkb)` | 從 WKB 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_GeogFromEWKT(ewkt)` | 從 Extended WKT 建立 GEOGRAPHY | `GEOGRAPHY` |
| `ST_GeogFromGeoJSON(geojson)` | 從 GeoJSON 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_Point(x, y [, srid])` | 從座標建立點 | `GEOMETRY` |
| `ST_PointFromGeoHash(geohash)` | 從 geohash 中心建立點 | `GEOMETRY` |
| `to_geometry(georepExpr)` | 自動偵測格式並建立 GEOMETRY | `GEOMETRY` |
| `to_geography(georepExpr)` | 自動偵測格式並建立 GEOGRAPHY | `GEOGRAPHY` |
| `try_to_geometry(georepExpr)` | 安全建立幾何（錯誤時回傳 NULL） | `GEOMETRY` |
| `try_to_geography(georepExpr)` | 安全建立地理（錯誤時回傳 NULL） | `GEOGRAPHY` |

#### ST 匯出函式

| 函式 | 說明 | 輸出 |
|----------|-------------|--------|
| `ST_AsText(geo)` | 匯出為 WKT | `STRING` |
| `ST_AsWKT(geo)` | 匯出為 WKT（別名） | `STRING` |
| `ST_AsBinary(geo)` | 匯出為 WKB | `BINARY` |
| `ST_AsWKB(geo)` | 匯出為 WKB（別名） | `BINARY` |
| `ST_AsEWKT(geo)` | 匯出為 Extended WKT | `STRING` |
| `ST_AsEWKB(geo)` | 匯出為 Extended WKB | `BINARY` |
| `ST_AsGeoJSON(geo)` | 匯出為 GeoJSON | `STRING` |
| `ST_GeoHash(geo)` | 匯出為 geohash 字串 | `STRING` |

#### ST 建構函式

| 函式 | 說明 |
|----------|-------------|
| `ST_Point(x, y [, srid])` | 建立點幾何 |
| `ST_MakeLine(pointArray)` | 從點陣列建立線段 |
| `ST_MakePolygon(outer [, innerArray])` | 從外環及選用洞建立多邊形 |

#### ST 存取函式

| 函式 | 說明 | 回傳 |
|----------|-------------|---------|
| `ST_X(geo)` | 點的 X 座標 | `DOUBLE` |
| `ST_Y(geo)` | 點的 Y 座標 | `DOUBLE` |
| `ST_Z(geo)` | 點的 Z 座標 | `DOUBLE` |
| `ST_M(geo)` | 點的 M 座標 | `DOUBLE` |
| `ST_XMin(geo)` | 包圍框的最小 X | `DOUBLE` |
| `ST_XMax(geo)` | 包圍框的最大 X | `DOUBLE` |
| `ST_YMin(geo)` | 包圍框的最小 Y | `DOUBLE` |
| `ST_YMax(geo)` | 包圍框的最大 Y | `DOUBLE` |
| `ST_ZMin(geo)` | 最小 Z 座標 | `DOUBLE` |
| `ST_ZMax(geo)` | 最大 Z 座標 | `DOUBLE` |
| `ST_Dimension(geo)` | 拓撲維度（0=點，1=線，2=多邊形） | `INT` |
| `ST_NDims(geo)` | 座標維度數 | `INT` |
| `ST_NPoints(geo)` | 總點數 | `INT` |
| `ST_NumGeometries(geo)` | 集合中的幾何數量 | `INT` |
| `ST_NumInteriorRings(geo)` | 內環數量（多邊形） | `INT` |
| `ST_GeometryType(geo)` | 幾何型別（字串） | `STRING` |
| `ST_GeometryN(geo, n)` | 集合中第 N 個幾何（從 1 起算） | `GEOMETRY` |
| `ST_PointN(geo, n)` | 線段中第 N 個點 | `GEOMETRY` |
| `ST_StartPoint(geo)` | 線段的起始點 | `GEOMETRY` |
| `ST_EndPoint(geo)` | 線段的終止點 | `GEOMETRY` |
| `ST_ExteriorRing(geo)` | 多邊形的外環 | `GEOMETRY` |
| `ST_InteriorRingN(geo, n)` | 多邊形的第 N 個內環 | `GEOMETRY` |
| `ST_Envelope(geo)` | 最小包圍矩形 | `GEOMETRY` |
| `ST_Envelope_Agg(geo)` | 彙總：所有幾何的包圍框 | `GEOMETRY` |
| `ST_Dump(geo)` | 將多重幾何展開為單一幾何陣列 | `ARRAY` |
| `ST_IsEmpty(geo)` | 若幾何無點則為 True | `BOOLEAN` |

#### ST 量測函式

| 函式 | 說明 |
|----------|-------------|
| `ST_Area(geo)` | 多邊形面積（以 CRS 單位） |
| `ST_Length(geo)` | 線段長度（以 CRS 單位） |
| `ST_Perimeter(geo)` | 多邊形周長（以 CRS 單位） |
| `ST_Distance(geo1, geo2)` | 幾何之間的平面距離 |
| `ST_DistanceSphere(geo1, geo2)` | 球面距離（公尺，快速但近似） |
| `ST_DistanceSpheroid(geo1, geo2)` | WGS84 橢球面上的測地線距離（公尺，精確） |
| `ST_Azimuth(geo1, geo2)` | 以北為基準的方位角（弧度） |
| `ST_ClosestPoint(geo1, geo2)` | geo1 上距 geo2 最近的點 |

#### ST 拓撲關係函式（斷言）

| 函式 | 說明 |
|----------|-------------|
| `ST_Contains(geo1, geo2)` | geo1 完全包含 geo2 時為 True |
| `ST_Within(geo1, geo2)` | geo1 完全在 geo2 內時為 True（Contains 的反向） |
| `ST_Intersects(geo1, geo2)` | 幾何共享任意空間時為 True |
| `ST_Disjoint(geo1, geo2)` | 幾何不共享任何空間時為 True |
| `ST_Touches(geo1, geo2)` | 邊界相觸但內部不相交時為 True |
| `ST_Covers(geo1, geo2)` | geo1 覆蓋 geo2（geo2 無外部點）時為 True |
| `ST_Equals(geo1, geo2)` | 幾何拓撲相等時為 True |
| `ST_DWithin(geo1, geo2, distance)` | 幾何在指定距離內時為 True |

#### ST 疊置函式（集合操作）

| 函式 | 說明 |
|----------|-------------|
| `ST_Intersection(geo1, geo2)` | 共享空間的幾何 |
| `ST_Union(geo1, geo2)` | 合併兩個輸入的幾何 |
| `ST_Union_Agg(geo)` | 彙總：欄中所有幾何的聯集 |
| `ST_Difference(geo1, geo2)` | geo1 減去 geo2 的幾何 |

#### ST 處理函式

| 函式 | 說明 |
|----------|-------------|
| `ST_Buffer(geo, radius)` | 將幾何擴展指定半徑距離 |
| `ST_Centroid(geo)` | 幾何的中心點 |
| `ST_ConvexHull(geo)` | 包含幾何的最小凸多邊形 |
| `ST_ConcaveHull(geo, ratio [, allowHoles])` | 帶長度比的凹多邊形外殼 |
| `ST_Boundary(geo)` | 幾何的邊界（並非所有 SQL Warehouse 版本均支援） |
| `ST_Simplify(geo, tolerance)` | 使用 Douglas-Peucker 演算法簡化 |

#### ST 編輯函式

| 函式 | 說明 |
|----------|-------------|
| `ST_AddPoint(linestring, point [, index])` | 在線段中新增點 |
| `ST_RemovePoint(linestring, index)` | 從線段移除點 |
| `ST_SetPoint(linestring, index, point)` | 替換線段中的點 |
| `ST_FlipCoordinates(geo)` | 互換 X 與 Y 座標 |
| `ST_Multi(geo)` | 將單一幾何轉換為多重幾何 |
| `ST_Reverse(geo)` | 反轉頂點順序 |

#### ST 仿射變換函式

| 函式 | 說明 |
|----------|-------------|
| `ST_Translate(geo, xOffset, yOffset [, zOffset])` | 依偏移量移動幾何 |
| `ST_Scale(geo, xFactor, yFactor [, zFactor])` | 依係數縮放幾何 |
| `ST_Rotate(geo, angle)` | 繞原點旋轉幾何（弧度） |

#### ST 空間參考系統函式

| 函式 | 說明 |
|----------|-------------|
| `ST_SRID(geo)` | 取得幾何的 SRID |
| `ST_SetSRID(geo, srid)` | 設定 SRID 值（不重投影） |
| `ST_Transform(geo, targetSrid)` | 重投影至目標座標系統 |

#### ST 驗證

| 函式 | 說明 |
|----------|-------------|
| `ST_IsValid(geo)` | 檢查幾何是否符合 OGC 規範 |

#### ST 實用範例

> **注意：** `CREATE TABLE` 中的 `GEOMETRY` 和 `GEOGRAPHY` 欄位型別需要 DBR 17.1+ 的 serverless 運算。對於不支援這些欄位型別的 SQL Warehouse，請使用 `STRING` 欄位搭配 WKT 表示法，並在查詢時以 `ST_GeomFromText()` / `ST_GeogFromText()` 進行轉換。

```sql
-- 建立包含幾何欄位的資料表（需要 serverless DBR 17.1+）
CREATE TABLE retail_stores (
  store_id INT,
  name STRING,
  location GEOMETRY
);

INSERT INTO retail_stores VALUES
  (1, 'Downtown Store', ST_Point(-73.9857, 40.7484, 4326)),
  (2, 'Midtown Store',  ST_Point(-73.9787, 40.7614, 4326)),
  (3, 'Uptown Store',   ST_Point(-73.9680, 40.7831, 4326));

-- 建立多邊形配送區域
CREATE TABLE delivery_zones (
  zone_id INT,
  zone_name STRING,
  boundary GEOMETRY
);

INSERT INTO delivery_zones VALUES
  (1, 'Zone A', ST_GeomFromText(
    'POLYGON((-74.00 40.74, -73.97 40.74, -73.97 40.76, -74.00 40.76, -74.00 40.74))', 4326
  ));

-- 點在多邊形內：尋找配送區域內的店家
SELECT s.name, z.zone_name
FROM retail_stores s
JOIN delivery_zones z
  ON ST_Contains(z.boundary, s.location);

-- 距離計算：尋找某店家 5km 內的客戶
-- 注意：to_geography() 接受 STRING（WKT/GeoJSON）或 BINARY（WKB）輸入，而非 GEOMETRY。
-- 請先使用 ST_AsText() 將 GEOMETRY 轉換為 WKT。
SELECT c.customer_id, c.name,
  ST_DistanceSphere(c.location, s.location) AS distance_meters
FROM customers c
CROSS JOIN retail_stores s
WHERE s.store_id = 1
  AND ST_DWithin(
    ST_GeogFromText(ST_AsText(c.location)),
    ST_GeogFromText(ST_AsText(s.location)),
    5000  -- 5km，單位公尺
  );

-- 緩衝區：在店家周圍建立 1km 緩衝區（使用投影 CRS 以公尺為單位）
SELECT ST_Buffer(
  ST_Transform(location, 5070),  -- 投影至 NAD83/Albers（公尺）
  1000                            -- 1000 公尺
) AS buffer_zone
FROM retail_stores
WHERE store_id = 1;

-- 面積計算
SELECT zone_name,
  ST_Area(ST_Transform(boundary, 5070)) AS area_sq_meters
FROM delivery_zones;

-- 重疊區域的聯集
SELECT ST_Union_Agg(boundary) AS combined_coverage
FROM delivery_zones;

-- 格式間轉換
SELECT
  ST_AsText(location) AS wkt,
  ST_AsGeoJSON(location) AS geojson,
  ST_GeoHash(location) AS geohash
FROM retail_stores;

-- 使用 BROADCAST 提示進行效能空間 JOIN
SELECT /*+ BROADCAST(zones) */
  c.customer_id, z.zone_name
FROM customers c
JOIN delivery_zones zones
  ON ST_Contains(zones.boundary, c.location);
```

### 結合 H3 與 ST 函式

```sql
-- 使用 H3 進行快速前置篩選，再以 ST 進行精確空間操作
-- 步驟 1：以 H3 索引店家位置
CREATE TABLE store_h3 AS
SELECT store_id, name, location,
  h3_longlatash3(ST_X(location), ST_Y(location), 9) AS h3_cell
FROM retail_stores;

-- 步驟 2：以 H3 索引客戶位置
CREATE TABLE customer_h3 AS
SELECT customer_id, name, location,
  h3_longlatash3(ST_X(location), ST_Y(location), 9) AS h3_cell
FROM customers;

-- 步驟 3：使用 H3 前置篩選 + 精確 ST 距離的快速鄰近搜尋
SELECT s.name AS store, c.name AS customer,
  ST_DistanceSphere(s.location, c.location) AS distance_m
FROM store_h3 s
JOIN customer_h3 c
  ON c.h3_cell IN (SELECT explode(h3_kring(s.h3_cell, 2)))
WHERE ST_DistanceSphere(s.location, c.location) < 2000;
```

### 空間 JOIN 效能

Databricks 使用內建空間索引自動最佳化空間 JOIN。JOIN 條件中的空間斷言如 `ST_Intersects`、`ST_Contains` 與 `ST_Within`，相較於傳統叢集可獲得高達 **17 倍的效能提升**。無需修改程式碼 -- 最佳化器會自動套用空間索引。

**效能提示：**
- 當 JOIN 的某一側足夠小可放入記憶體時，使用 `BROADCAST` 提示。
- 使用投影座標系統（例如以公尺為單位的 SRID 5070）進行距離計算，以避免昂貴的橢球函式。
- 結合 H3 進行粗略前置篩選，再以 ST 進行精確操作。
- 在 H3 格子欄位上使用 Delta Lake Liquid Clustering 以最佳化資料佈局。
- 啟用自動最佳化：`delta.autoOptimize.optimizeWrite` 與 `delta.autoOptimize.autoCompact`。

---

## 第二部分：定序

定序定義字串比較與排序的規則。Databricks 使用 ICU 函式庫支援二進位、不區分大小寫、不區分重音及語地區特定的定序。自 Databricks Runtime 16.1+ 起可用。

### 定序型別

| 定序 | 說明 | 行為 |
|-----------|-------------|----------|
| `UTF8_BINARY` | 預設。UTF-8 編碼的逐位元組比較 | `'A' < 'Z' < 'a'` -- 二進位順序，區分大小寫/重音 |
| `UTF8_LCASE` | 不區分大小寫的二進位。轉為小寫後以 UTF8_BINARY 比較 | `'A' == 'a'`，但 `'e' != 'é'`（區分重音） |
| `UNICODE` | ICU 根語地區。語言無關的 Unicode 排序 | `'a' < 'A' < 'À' < 'b'` -- 將相似字元分組 |
| 語地區特定 | 基於 ICU 語地區（例如 `DE`、`FR`、`JA`） | 語言感知的排序規則 |

### 定序語法

```
{ UTF8_BINARY | UTF8_LCASE | { UNICODE | locale } [ _ modifier [...] ] }
```

其中 `locale` 為：
```
language_code [ _ script_code ] [ _ country_code ]
```

- `language_code`：ISO 639-1（例如 `EN`、`DE`、`FR`、`JA`、`ZH`）
- `script_code`：ISO 15924（例如 `Hant` 代表繁體中文，`Latn` 代表拉丁文）
- `country_code`：ISO 3166-1（例如 `US`、`DE`、`CAN`）

### 定序修飾符（DBR 16.2+）

| 修飾符 | 說明 | 預設 |
|----------|-------------|---------|
| `CS` | 區分大小寫：`'A' != 'a'` | 是（預設） |
| `CI` | 不區分大小寫：`'A' == 'a'` | 否 |
| `AS` | 區分重音：`'e' != 'é'` | 是（預設） |
| `AI` | 不區分重音：`'e' == 'é'` | 否 |
| `RTRIM` | 忽略尾端空格：`'Hello' == 'Hello '` | 否 |

每對（CS/CI、AS/AI）最多指定一個，加上選用的 RTRIM。順序不重要。

### 語地區範例

| 定序名稱 | 說明 |
|----------------|-------------|
| `UNICODE` | ICU 根語地區，語言無關 |
| `UNICODE_CI` | Unicode，不區分大小寫 |
| `UNICODE_CI_AI` | Unicode，不區分大小寫與重音 |
| `DE` | 德文排序規則 |
| `DE_CI_AI` | 德文，不區分大小寫與重音 |
| `FR_CAN` | 法文（加拿大） |
| `EN_US` | 英文（美國） |
| `ZH_Hant_MAC` | 繁體中文（澳門） |
| `SR` | 塞爾維亞文（從 `SR_CYR_SRN_CS_AS` 正規化） |
| `JA` | 日文 |
| `EN_CS_AI` | 英文，區分大小寫，不區分重音 |
| `UTF8_LCASE_RTRIM` | 不區分大小寫並修剪尾端空格 |

### 定序優先順序

由高至低：

1. **明確（Explicit）** -- 透過 `COLLATE` 運算式指定
2. **隱含（Implicit）** -- 從欄位、欄位或變數定義衍生
3. **預設（Default）** -- 套用於字串字面值與函式結果
4. **無（None）** -- 結合不同隱含定序時

在同一運算式中混用兩個不同的**明確**定序會產生錯誤。

### 在不同層級設定定序

#### 目錄層級（DBR 17.1+）

```sql
-- 建立帶有預設定序的目錄
CREATE CATALOG customer_cat
  DEFAULT COLLATION UNICODE_CI_AI;

-- 在此目錄中建立的所有 schema、資料表及字串欄位
-- 若未覆寫，均繼承 UNICODE_CI_AI
```

#### Schema 層級（DBR 17.1+）

```sql
-- 建立帶有預設定序的 schema
CREATE SCHEMA my_schema
  DEFAULT COLLATION UNICODE_CI;

-- 變更新物件的預設定序（現有物件不受影響）
ALTER SCHEMA my_schema
  DEFAULT COLLATION UNICODE_CI_AI;
```

#### 資料表層級（DBR 16.3+）

```sql
-- 資料表層級預設定序
CREATE TABLE users (
  id INT,
  username STRING,           -- 繼承資料表預設的 UNICODE_CI
  email STRING,              -- 繼承資料表預設的 UNICODE_CI
  password_hash STRING COLLATE UTF8_BINARY  -- 明確覆寫
) DEFAULT COLLATION UNICODE_CI;
```

#### 欄位層級（DBR 16.1+）

```sql
-- 欄位層級定序
CREATE TABLE products (
  id INT,
  name STRING COLLATE UNICODE_CI,
  sku STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UNICODE_CI_AI
);

-- 新增帶有定序的欄位
ALTER TABLE products
  ADD COLUMN category STRING COLLATE UNICODE_CI;

-- 變更欄位定序（需要 DBR 17.2+；並非所有 SQL Warehouse 版本均支援）
ALTER TABLE products
  ALTER COLUMN name SET COLLATION UNICODE_CI_AI;
```

#### 運算式層級

```sql
-- 在查詢中行內套用定序
SELECT *
FROM products
WHERE name COLLATE UNICODE_CI = 'laptop';

-- 檢查運算式的定序
SELECT collation('test' COLLATE UNICODE_CI);
-- 回傳：UNICODE_CI
```

### 定序繼承階層

```
Catalog DEFAULT COLLATION
  -> Schema DEFAULT COLLATION（覆寫目錄）
    -> Table DEFAULT COLLATION（覆寫 schema）
      -> Column COLLATE（覆寫資料表）
        -> Expression COLLATE（覆寫欄位）
```

若任何層級均未指定定序，則使用 `UTF8_BINARY`。

### 定序感知字串函式

大多數字串函式遵循定序。主要的定序感知操作：

| 函式/運算子 | 定序行為 |
|-------------------|-------------------|
| `=`, `!=`, `<`, `>`, `<=`, `>=` | 比較使用欄位/運算式定序 |
| `LIKE` | 模式比對遵循定序 |
| `CONTAINS(str, substr)` | 子字串搜尋遵循定序 |
| `STARTSWITH(str, prefix)` | 前綴比對遵循定序 |
| `ENDSWITH(str, suffix)` | 後綴比對遵循定序 |
| `IN (...)` | 成員測試遵循定序 |
| `BETWEEN` | 範圍比較遵循定序 |
| `ORDER BY` | 排序遵循定序 |
| `GROUP BY` | 分組遵循定序 |
| `DISTINCT` | 去重複遵循定序 |
| `REPLACE(str, old, new)` | 搜尋遵循定序 |
| `TRIM` / `LTRIM` / `RTRIM` | 修剪字元遵循定序 |

**效能說明：** `STARTSWITH` 與 `ENDSWITH` 搭配 `UTF8_LCASE` 定序，相較於等效的 `LOWER()` 解決方案可獲得高達 **10 倍的效能加速**。

### 工具函式

```sql
-- 取得運算式的定序
SELECT collation(name) FROM products;

-- 列出所有支援的定序
SELECT * FROM collations();

-- 以 COLLATE 測試定序
SELECT collation('hello' COLLATE DE_CI_AI);
-- 回傳：DE_CI_AI
```

### 定序實用範例

#### 不區分大小寫的搜尋

```sql
-- 使用欄位定序（建議 -- 可利用索引）
CREATE TABLE users (
  id INT,
  username STRING COLLATE UTF8_LCASE,
  email STRING COLLATE UTF8_LCASE
);

INSERT INTO users VALUES
  (1, 'JohnDoe', 'John@Example.com'),
  (2, 'janedoe', 'JANE@EXAMPLE.COM');

-- 自動進行不區分大小寫比對
SELECT * FROM users WHERE username = 'johndoe';
-- 回傳：JohnDoe

SELECT * FROM users WHERE email = 'john@example.com';
-- 回傳：John@Example.com
```

#### 使用運算式定序的不區分大小寫搜尋

```sql
-- 在 UTF8_BINARY 欄位上進行臨時不區分大小寫比較
SELECT * FROM products
WHERE name COLLATE UNICODE_CI = 'MacBook Pro';
-- 比對：macbook pro, MACBOOK PRO, MacBook Pro 等
```

#### 不區分重音的搜尋

```sql
-- 不區分重音的比對
CREATE TABLE cities (
  id INT,
  name STRING COLLATE UNICODE_CI_AI
);

INSERT INTO cities VALUES (1, 'Montreal'), (2, 'Montréal');

SELECT * FROM cities WHERE name = 'Montreal';
-- 回傳兩筆：Montreal 和 Montréal（將 e 和 é 視為相等）
```

#### 語地區感知排序

```sql
-- 德文排序（變音符號排序正確）
SELECT name
FROM german_customers
ORDER BY name COLLATE DE;
-- 排序：Ärzte 在 Bauer 之前（德文排序中 Ä 視為 A+e）

-- 瑞典文排序（Å, Ä, Ö 排在 Z 之後）
SELECT name
FROM swedish_customers
ORDER BY name COLLATE SV;
```

#### 尾端空格處理

```sql
-- RTRIM 修飾符忽略尾端空格
SELECT 'Hello' COLLATE UTF8_BINARY_RTRIM = 'Hello   ';
-- 回傳：true

SELECT 'Hello' COLLATE UTF8_BINARY = 'Hello   ';
-- 回傳：false
```

#### 目錄級不區分大小寫設定

```sql
-- 建立預設不區分大小寫的目錄
CREATE CATALOG app_data DEFAULT COLLATION UNICODE_CI;

USE CATALOG app_data;
CREATE SCHEMA users_schema;
USE SCHEMA users_schema;

-- 所有 STRING 欄位自動使用 UNICODE_CI
CREATE TABLE accounts (
  id INT,
  username STRING,  -- 從目錄繼承 UNICODE_CI
  email STRING       -- 從目錄繼承 UNICODE_CI
);

-- 查詢自動不區分大小寫
SELECT * FROM accounts WHERE username = 'admin';
-- 比對：Admin, ADMIN, admin, aDmIn 等
```

### 限制與注意事項

- `CHECK` 約束與生成欄位運算式需要 `UTF8_BINARY` 預設定序。
- `hive_metastore` 目錄資料表不支援定序約束。
- `ALTER SCHEMA ... DEFAULT COLLATION` 僅影響新建立的物件，不影響現有物件。
- 在同一運算式中混用兩個不同的明確定序會引發錯誤。
- `UTF8_LCASE` 在 Databricks 內部用於識別碼解析（目錄、schema、資料表、欄位名稱）。
- Databricks 透過移除預設值來正規化定序名稱（例如 `SR_CYR_SRN_CS_AS` 簡化為 `SR`）。
- 定序修飾符需要 Databricks Runtime 16.2+。
- 目錄/Schema 層級的 `DEFAULT COLLATION` 需要 Databricks Runtime 17.1+。
"""

out = pathlib.Path(r'D:\azure_code\ai-dev-kit\databricks-skills\databricks-dbsql\geospatial-collations.md')
out.write_text(content, encoding='utf-8')
print(f"Written {len(content)} chars, no BOM")
raw = out.read_bytes()
assert raw[:3] != b'\xef\xbb\xbf', "BOM detected!"
print("BOM check passed")
