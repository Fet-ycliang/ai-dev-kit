# Databricks SQL 中的 Geospatial SQL 與 Collations

---

## 第 1 部分：Geospatial SQL

Databricks SQL 透過兩大函式家族提供完整的地理空間支援：用於六角形網格索引的 **H3 functions**，以及用於標準空間運算的 **ST functions**。兩者搭配可實現可擴展且高效能的地理空間分析。

### 地理空間資料型別

| 類型 | 說明 | 座標系統 | SRID 支援 |
|------|------|----------|-----------|
| `GEOMETRY` | 使用歐幾里得座標（X、Y，可選 Z）的空間物件 -- 將地球視為平面 | 任何投影 CRS | 11,000+ 個 SRID |
| `GEOGRAPHY` | 使用經度/緯度、位於地球表面的地理物件 | WGS 84 | 僅支援 SRID 4326 |

**何時該用哪一種：**
- `GEOMETRY` 適用於投影座標系統、歐幾里得距離計算，以及使用公尺或英尺處理本地/區域資料的情境。
- `GEOGRAPHY` 適用於使用經度/緯度座標的全球資料，以及球面距離計算。

### 支援的 Geometry 子類型

`GEOMETRY` 與 `GEOGRAPHY` 都支援：**Point**、**LineString**、**Polygon**、**MultiPoint**、**MultiLineString**、**MultiPolygon** 與 **GeometryCollection**。

### 格式支援

| 格式 | 說明 | 匯入函式 | 匯出函式 |
|------|------|----------|----------|
| WKT | Well-Known Text | `ST_GeomFromWKT`, `ST_GeogFromWKT` | `ST_AsWKT`, `ST_AsText` |
| WKB | Well-Known Binary | `ST_GeomFromWKB`, `ST_GeogFromWKB` | `ST_AsWKB`, `ST_AsBinary` |
| EWKT | Extended WKT（包含 SRID） | `ST_GeomFromEWKT`, `ST_GeogFromEWKT` | `ST_AsEWKT` |
| EWKB | Extended WKB（包含 SRID） | `ST_GeomFromEWKB` | `ST_AsEWKB` |
| GeoJSON | 以 JSON 為基礎的格式 | `ST_GeomFromGeoJSON`, `ST_GeogFromGeoJSON` | `ST_AsGeoJSON` |
| Geohash | 階層式網格編碼 | `ST_GeomFromGeoHash`, `ST_PointFromGeoHash` | `ST_GeoHash` |

---

### H3 地理空間函式

H3 是 Uber 的六角形階層式空間索引。它會在 16 個解析度層級（0-15）將地球切分為六角形 cell。自 Databricks Runtime 11.2 起可用（H3 Java library 3.7.0）。不需要另行安裝。

#### H3 匯入函式（座標/Geometry 轉 H3）

| 函式 | 說明 | 回傳值 |
|------|------|--------|
| `h3_longlatash3(lon, lat, resolution)` | 將經度/緯度轉換為 H3 cell ID | `BIGINT` |
| `h3_longlatash3string(lon, lat, resolution)` | 將經度/緯度轉換為 H3 cell ID | `STRING`（hex） |
| `h3_pointash3(geogExpr, resolution)` | 將 GEOGRAPHY point 轉換為 H3 cell ID | `BIGINT` |
| `h3_pointash3string(geogExpr, resolution)` | 將 GEOGRAPHY point 轉換為 H3 cell ID | `STRING`（hex） |
| `h3_polyfillash3(geogExpr, resolution)` | 以 polygon 內含的 H3 cells 進行填滿 | `ARRAY<BIGINT>` |
| `h3_polyfillash3string(geogExpr, resolution)` | 以 polygon 內含的 H3 cells 進行填滿 | `ARRAY<STRING>` |
| `h3_coverash3(geogExpr, resolution)` | 使用最少數量的 H3 cells 覆蓋 geography | `ARRAY<BIGINT>` |
| `h3_coverash3string(geogExpr, resolution)` | 使用最少數量的 H3 cells 覆蓋 geography | `ARRAY<STRING>` |
| `h3_tessellateaswkb(geogExpr, resolution)` | 使用 H3 cells 對 geography 進行鑲嵌 | `ARRAY<STRUCT>` |
| `h3_try_polyfillash3(geogExpr, resolution)` | 安全 polyfill（發生錯誤時回傳 NULL） | `ARRAY<BIGINT>` |
| `h3_try_polyfillash3string(geogExpr, resolution)` | 安全 polyfill（發生錯誤時回傳 NULL） | `ARRAY<STRING>` |
| `h3_try_coverash3(geogExpr, resolution)` | 安全 cover（發生錯誤時回傳 NULL） | `ARRAY<BIGINT>` |
| `h3_try_coverash3string(geogExpr, resolution)` | 安全 cover（發生錯誤時回傳 NULL） | `ARRAY<STRING>` |
| `h3_try_tessellateaswkb(geogExpr, resolution)` | 安全 tessellate（發生錯誤時回傳 NULL） | `ARRAY<STRUCT>` |

#### H3 匯出函式（H3 轉 Geometry/Format）

| 函式 | 說明 | 回傳值 |
|------|------|--------|
| `h3_boundaryaswkt(h3CellId)` | 將 H3 cell 邊界輸出為 WKT polygon | `STRING` |
| `h3_boundaryaswkb(h3CellId)` | 將 H3 cell 邊界輸出為 WKB polygon | `BINARY` |
| `h3_boundaryasgeojson(h3CellId)` | 將 H3 cell 邊界輸出為 GeoJSON | `STRING` |
| `h3_centeraswkt(h3CellId)` | 將 H3 cell 中心輸出為 WKT point | `STRING` |
| `h3_centeraswkb(h3CellId)` | 將 H3 cell 中心輸出為 WKB point | `BINARY` |
| `h3_centerasgeojson(h3CellId)` | 將 H3 cell 中心輸出為 GeoJSON point | `STRING` |

#### H3 轉換函式

| 函式 | 說明 |
|------|------|
| `h3_h3tostring(h3CellId)` | 將 BIGINT cell ID 轉換為 hex STRING |
| `h3_stringtoh3(h3CellIdString)` | 將 hex STRING 轉換為 BIGINT cell ID |

#### H3 階層 / 巡訪函式

| 函式 | 說明 |
|------|------|
| `h3_resolution(h3CellId)` | 取得 cell 的解析度 |
| `h3_toparent(h3CellId, resolution)` | 取得較粗解析度的父 cell |
| `h3_tochildren(h3CellId, resolution)` | 取得較細解析度的所有子 cells |
| `h3_maxchild(h3CellId, resolution)` | 取得值最大的子 cell |
| `h3_minchild(h3CellId, resolution)` | 取得值最小的子 cell |
| `h3_ischildof(h3CellId1, h3CellId2)` | 測試 cell1 是否等於 cell2 或為其子 cell |

#### H3 距離 / 鄰近函式

| 函式 | 說明 |
|------|------|
| `h3_distance(h3CellId1, h3CellId2)` | 兩個 cells 之間的網格距離 |
| `h3_try_distance(h3CellId1, h3CellId2)` | 網格距離；若未定義則回傳 NULL |
| `h3_kring(h3CellId, k)` | 網格距離 k 內的所有 cells（填滿圓盤） |
| `h3_kringdistances(h3CellId, k)` | 距離 k 內的 cells 及其距離 |
| `h3_hexring(h3CellId, k)` | 距離恰為 k 的空心 cell 環 |

#### H3 壓縮函式

| 函式 | 說明 |
|------|------|
| `h3_compact(h3CellIds)` | 將 cell 陣列壓縮為最小表示 |
| `h3_uncompact(h3CellIds, resolution)` | 將壓縮後的 cells 展開至目標解析度 |

#### H3 驗證函式

| 函式 | 說明 |
|------|------|
| `h3_isvalid(expr)` | 檢查 BIGINT 或 STRING 是否為有效的 H3 cell |
| `h3_validate(h3CellId)` | 若有效則回傳 cell ID，否則拋出錯誤 |
| `h3_try_validate(h3CellId)` | 若有效則回傳 cell ID，否則回傳 NULL |
| `h3_ispentagon(h3CellId)` | 檢查 cell 是否為五邊形（每個解析度 12 個） |

#### H3 範例

```sql
-- 將座標轉換為解析度 9 的 H3 cell
SELECT h3_longlatash3(-73.985428, 40.748817, 9) AS h3_cell;

-- 依上車地點為 taxi 行程建立 H3 索引
CREATE TABLE trips_h3 AS
SELECT
  h3_longlatash3(pickup_longitude, pickup_latitude, 12) AS pickup_cell,
  h3_longlatash3(dropoff_longitude, dropoff_latitude, 12) AS dropoff_cell,
  *
FROM taxi_trips;

-- 以 H3 cells 填滿郵遞區號 polygon，以便進行空間索引
CREATE TABLE zipcode_h3 AS
SELECT
  explode(h3_polyfillash3(geom_wkt, 12)) AS cell,
  zipcode, city, state
FROM zipcodes;

-- 使用 H3 join 找出在特定郵遞區號上車的所有行程
SELECT t.*
FROM trips_h3 t
INNER JOIN zipcode_h3 z ON t.pickup_cell = z.cell
WHERE z.zipcode = '10001';

-- 鄰近搜尋：找出某位置周圍 2 圈內的所有 H3 cells
SELECT explode(h3_kring(h3_longlatash3(-73.985, 40.748, 9), 2)) AS nearby_cell;

-- 彙總行程數並取得質心座標以供視覺化
SELECT
  dropoff_cell,
  h3_centerasgeojson(dropoff_cell):coordinates[0] AS lon,
  h3_centerasgeojson(dropoff_cell):coordinates[1] AS lat,
  count(*) AS trip_count
FROM trips_h3
GROUP BY dropoff_cell;

-- 向上彙總至較粗的解析度
SELECT
  h3_toparent(pickup_cell, 7) AS parent_cell,
  count(*) AS trip_count
FROM trips_h3
GROUP BY h3_toparent(pickup_cell, 7);

-- 壓縮一組 cells 以利高效率儲存
SELECT h3_compact(collect_set(cell)) AS compacted
FROM zipcode_h3
WHERE zipcode = '10001';
```

---

### ST 地理空間函式

原生空間 SQL 函式，可對 `GEOMETRY` 與 `GEOGRAPHY` 類型運作。需要 Databricks Runtime 17.1+。目前為 Public Preview。提供超過 80 個函式。

#### ST 匯入函式（建立 Geometry/Geography）

| 函式 | 說明 | 輸出型別 |
|------|------|----------|
| `ST_GeomFromText(wkt [, srid])` | 從 WKT 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromWKT(wkt [, srid])` | 從 WKT 建立 GEOMETRY（別名） | `GEOMETRY` |
| `ST_GeomFromWKB(wkb [, srid])` | 從 WKB 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromEWKT(ewkt)` | 從 Extended WKT 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromEWKB(ewkb)` | 從 Extended WKB 建立 GEOMETRY | `GEOMETRY` |
| `ST_GeomFromGeoJSON(geojson)` | 從 GeoJSON 建立 GEOMETRY(4326) | `GEOMETRY` |
| `ST_GeomFromGeoHash(geohash)` | 從 geohash 建立 polygon GEOMETRY | `GEOMETRY` |
| `ST_GeogFromText(wkt)` | 從 WKT 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_GeogFromWKT(wkt)` | 從 WKT 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_GeogFromWKB(wkb)` | 從 WKB 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_GeogFromEWKT(ewkt)` | 從 Extended WKT 建立 GEOGRAPHY | `GEOGRAPHY` |
| `ST_GeogFromGeoJSON(geojson)` | 從 GeoJSON 建立 GEOGRAPHY(4326) | `GEOGRAPHY` |
| `ST_Point(x, y [, srid])` | 從座標建立 point | `GEOMETRY` |
| `ST_PointFromGeoHash(geohash)` | 從 geohash 中心建立 point | `GEOMETRY` |
| `to_geometry(georepExpr)` | 自動偵測格式並建立 GEOMETRY | `GEOMETRY` |
| `to_geography(georepExpr)` | 自動偵測格式並建立 GEOGRAPHY | `GEOGRAPHY` |
| `try_to_geometry(georepExpr)` | 安全建立 geometry（發生錯誤時回傳 NULL） | `GEOMETRY` |
| `try_to_geography(georepExpr)` | 安全建立 geography（發生錯誤時回傳 NULL） | `GEOGRAPHY` |

#### ST 匯出函式

| 函式 | 說明 | 輸出 |
|------|------|------|
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
|------|------|
| `ST_Point(x, y [, srid])` | 建立 point geometry |
| `ST_MakeLine(pointArray)` | 從點陣列建立 linestring |
| `ST_MakePolygon(outer [, innerArray])` | 以外環與可選的洞建立 polygon |

#### ST 存取函式

| 函式 | 說明 | 回傳值 |
|------|------|--------|
| `ST_X(geo)` | 點的 X 座標 | `DOUBLE` |
| `ST_Y(geo)` | 點的 Y 座標 | `DOUBLE` |
| `ST_Z(geo)` | 點的 Z 座標 | `DOUBLE` |
| `ST_M(geo)` | 點的 M 座標 | `DOUBLE` |
| `ST_XMin(geo)` | 邊界框的最小 X 值 | `DOUBLE` |
| `ST_XMax(geo)` | 邊界框的最大 X 值 | `DOUBLE` |
| `ST_YMin(geo)` | 邊界框的最小 Y 值 | `DOUBLE` |
| `ST_YMax(geo)` | 邊界框的最大 Y 值 | `DOUBLE` |
| `ST_ZMin(geo)` | 最小 Z 座標 | `DOUBLE` |
| `ST_ZMax(geo)` | 最大 Z 座標 | `DOUBLE` |
| `ST_Dimension(geo)` | 拓樸維度（0=point、1=line、2=polygon） | `INT` |
| `ST_NDims(geo)` | 座標維度數量 | `INT` |
| `ST_NPoints(geo)` | 點的總數 | `INT` |
| `ST_NumGeometries(geo)` | 集合中的 geometry 數量 | `INT` |
| `ST_NumInteriorRings(geo)` | 內環數量（polygon） | `INT` |
| `ST_GeometryType(geo)` | 以字串表示的 geometry 類型 | `STRING` |
| `ST_GeometryN(geo, n)` | 從集合取得第 N 個 geometry（從 1 開始） | `GEOMETRY` |
| `ST_PointN(geo, n)` | 從 linestring 取得第 N 個點 | `GEOMETRY` |
| `ST_StartPoint(geo)` | linestring 的第一個點 | `GEOMETRY` |
| `ST_EndPoint(geo)` | linestring 的最後一個點 | `GEOMETRY` |
| `ST_ExteriorRing(geo)` | polygon 的外環 | `GEOMETRY` |
| `ST_InteriorRingN(geo, n)` | polygon 的第 N 個內環 | `GEOMETRY` |
| `ST_Envelope(geo)` | 最小外接矩形 | `GEOMETRY` |
| `ST_Envelope_Agg(geo)` | 彙總：欄位中所有 geometries 的邊界框 | `GEOMETRY` |
| `ST_Dump(geo)` | 將 multi-geometry 展開為單一 geometry 陣列 | `ARRAY` |
| `ST_IsEmpty(geo)` | 若 geometry 沒有任何點則為 true | `BOOLEAN` |

#### ST 測量函式

| 函式 | 說明 |
|------|------|
| `ST_Area(geo)` | polygon 的面積（以 CRS 單位計） |
| `ST_Length(geo)` | linestring 的長度（以 CRS 單位計） |
| `ST_Perimeter(geo)` | polygon 的周長（以 CRS 單位計） |
| `ST_Distance(geo1, geo2)` | geometries 之間的笛卡兒距離 |
| `ST_DistanceSphere(geo1, geo2)` | 以公尺計的球面距離（快速、近似） |
| `ST_DistanceSpheroid(geo1, geo2)` | WGS84 上以公尺計的測地線距離（精確） |
| `ST_Azimuth(geo1, geo2)` | 以正北為基準、以弧度表示的方位角 |
| `ST_ClosestPoint(geo1, geo2)` | geo1 上最接近 geo2 的點 |

#### ST 拓樸關係函式（Predicates）

| 函式 | 說明 |
|------|------|
| `ST_Contains(geo1, geo2)` | 若 geo1 完全包含 geo2 則為 true |
| `ST_Within(geo1, geo2)` | 若 geo1 完全位於 geo2 內則為 true（Contains 的反向） |
| `ST_Intersects(geo1, geo2)` | 若 geometries 共享任何空間則為 true |
| `ST_Disjoint(geo1, geo2)` | 若 geometries 沒有共享空間則為 true |
| `ST_Touches(geo1, geo2)` | 若邊界接觸但內部不相交則為 true |
| `ST_Covers(geo1, geo2)` | 若 geo1 覆蓋 geo2 則為 true（geo2 沒有任何點位於 exterior） |
| `ST_Equals(geo1, geo2)` | 若 geometries 在拓樸上相等則為 true |
| `ST_DWithin(geo1, geo2, distance)` | 若 geometries 位於給定距離內則為 true |

#### ST Overlay 函式（集合運算）

| 函式 | 說明 |
|------|------|
| `ST_Intersection(geo1, geo2)` | 共用空間的 geometry |
| `ST_Union(geo1, geo2)` | 合併兩個輸入的 geometry |
| `ST_Union_Agg(geo)` | 彙總：欄位中所有 geometries 的聯集 |
| `ST_Difference(geo1, geo2)` | geo1 扣除 geo2 後的 geometry |

#### ST 處理函式

| 函式 | 說明 |
|------|------|
| `ST_Buffer(geo, radius)` | 依半徑距離擴張 geometry |
| `ST_Centroid(geo)` | geometry 的中心點 |
| `ST_ConvexHull(geo)` | 包含 geometry 的最小凸 polygon |
| `ST_ConcaveHull(geo, ratio [, allowHoles])` | 依長度比例建立 concave hull |
| `ST_Boundary(geo)` | geometry 的邊界（並非所有 SQL Warehouse 版本都提供） |
| `ST_Simplify(geo, tolerance)` | 使用 Douglas-Peucker 演算法簡化 |

#### ST 編輯函式

| 函式 | 說明 |
|------|------|
| `ST_AddPoint(linestring, point [, index])` | 將點加入 linestring |
| `ST_RemovePoint(linestring, index)` | 從 linestring 移除點 |
| `ST_SetPoint(linestring, index, point)` | 取代 linestring 中的點 |
| `ST_FlipCoordinates(geo)` | 交換 X 與 Y 座標 |
| `ST_Multi(geo)` | 將單一 geometry 轉成 multi-geometry |
| `ST_Reverse(geo)` | 反轉頂點順序 |

#### ST 仿射轉換函式

| 函式 | 說明 |
|------|------|
| `ST_Translate(geo, xOffset, yOffset [, zOffset])` | 依位移量移動 geometry |
| `ST_Scale(geo, xFactor, yFactor [, zFactor])` | 依縮放係數縮放 geometry |
| `ST_Rotate(geo, angle)` | 以原點為中心旋轉 geometry（弧度） |

#### ST 空間參考系統函式

| 函式 | 說明 |
|------|------|
| `ST_SRID(geo)` | 取得 geometry 的 SRID |
| `ST_SetSRID(geo, srid)` | 設定 SRID 值（不重新投影） |
| `ST_Transform(geo, targetSrid)` | 重新投影到目標座標系統 |

#### ST 驗證

| 函式 | 說明 |
|------|------|
| `ST_IsValid(geo)` | 檢查 geometry 是否符合 OGC validity |

#### ST 實務範例

> **注意：** `CREATE TABLE` 中的 `GEOMETRY` 與 `GEOGRAPHY` 欄位型別需要 serverless compute 搭配 DBR 17.1+。若 SQL Warehouses 不支援這些欄位型別，請改用以 WKT 表示的 `STRING` 欄位，並在查詢時使用 `ST_GeomFromText()` / `ST_GeogFromText()` 進行轉換。

```sql
-- 建立含 geometry 欄位的資料表（需要 serverless DBR 17.1+）
CREATE TABLE retail_stores (
  store_id INT,
  name STRING,
  location GEOMETRY
);

INSERT INTO retail_stores VALUES
  (1, '市中心門市', ST_Point(-73.9857, 40.7484, 4326)),
  (2, '中城門市',  ST_Point(-73.9787, 40.7614, 4326)),
  (3, '上城門市',   ST_Point(-73.9680, 40.7831, 4326));

-- 建立作為 polygon 的配送區域
CREATE TABLE delivery_zones (
  zone_id INT,
  zone_name STRING,
  boundary GEOMETRY
);

INSERT INTO delivery_zones VALUES
  (1, 'A 區', ST_GeomFromText(
    'POLYGON((-74.00 40.74, -73.97 40.74, -73.97 40.76, -74.00 40.76, -74.00 40.74))', 4326
  ));

-- 點在多邊形內：找出位於配送區域內的門市
SELECT s.name, z.zone_name
FROM retail_stores s
JOIN delivery_zones z
  ON ST_Contains(z.boundary, s.location);

-- 距離計算：找出距離某門市 5km 內的客戶
-- 注意：to_geography() 預期輸入為 STRING（WKT/GeoJSON）或 BINARY（WKB），而不是 GEOMETRY。
-- 請先使用 ST_AsText() 將 GEOMETRY 轉為 WKT。
SELECT c.customer_id, c.name,
  ST_DistanceSphere(c.location, s.location) AS distance_meters
FROM customers c
CROSS JOIN retail_stores s
WHERE s.store_id = 1
  AND ST_DWithin(
    ST_GeogFromText(ST_AsText(c.location)),
    ST_GeogFromText(ST_AsText(s.location)),
    5000  -- 5km（公尺）
  );

-- 緩衝區：在門市周圍建立 1km 緩衝區（使用公尺時請採用投影 CRS）
SELECT ST_Buffer(
  ST_Transform(location, 5070),  -- 投影到 NAD83/Albers（公尺）
  1000                            -- 1000 公尺
) AS buffer_zone
FROM retail_stores
WHERE store_id = 1;

-- 面積計算
SELECT zone_name,
  ST_Area(ST_Transform(boundary, 5070)) AS area_sq_meters
FROM delivery_zones;

-- 合併重疊區域
SELECT ST_Union_Agg(boundary) AS combined_coverage
FROM delivery_zones;

-- 在不同格式之間轉換
SELECT
  ST_AsText(location) AS wkt,
  ST_AsGeoJSON(location) AS geojson,
  ST_GeoHash(location) AS geohash
FROM retail_stores;

-- 為了效能，使用帶有 BROADCAST hint 的 spatial join
SELECT /*+ BROADCAST(zones) */
  c.customer_id, z.zone_name
FROM customers c
JOIN delivery_zones zones
  ON ST_Contains(zones.boundary, c.location);
```

### 結合 H3 與 ST 函式

```sql
-- 先用 H3 快速預篩，再用 ST 進行精確的空間運算
-- 第 1 步：使用 H3 為門市位置建立索引
CREATE TABLE store_h3 AS
SELECT store_id, name, location,
  h3_longlatash3(ST_X(location), ST_Y(location), 9) AS h3_cell
FROM retail_stores;

-- 第 2 步：使用 H3 為客戶位置建立索引
CREATE TABLE customer_h3 AS
SELECT customer_id, name, location,
  h3_longlatash3(ST_X(location), ST_Y(location), 9) AS h3_cell
FROM customers;

-- 第 3 步：使用 H3 預篩 + 精確 ST 距離，快速進行鄰近搜尋
SELECT s.name AS store, c.name AS customer,
  ST_DistanceSphere(s.location, c.location) AS distance_m
FROM store_h3 s
JOIN customer_h3 c
  ON c.h3_cell IN (SELECT explode(h3_kring(s.h3_cell, 2)))
WHERE ST_DistanceSphere(s.location, c.location) < 2000;
```

### Spatial Join 效能

Databricks 會利用內建空間索引自動最佳化 spatial joins。當在 JOIN 條件中使用 `ST_Intersects`、`ST_Contains` 與 `ST_Within` 等 spatial predicates 時，與傳統 clusters 相比，效能最多可提升 **17 倍**。不需要修改程式碼 -- 最佳化器會自動套用空間索引。

**效能建議：**
- 當 join 的其中一側足夠小、可放入記憶體時，使用 `BROADCAST` hint。
- 距離計算請使用投影座標系統（例如以公尺為單位的 SRID 5070），以避免昂貴的 spheroid 函式。
- 使用 H3 進行粗略預篩，再以 ST 執行精確運算。
- 在 H3 cell 欄位上使用 Delta Lake liquid clustering，以最佳化資料配置。
- 啟用自動最佳化：`delta.autoOptimize.optimizeWrite` 與 `delta.autoOptimize.autoCompact`。

---

## 第 2 部分：Collations

Collations 定義字串比較與排序的規則。Databricks 使用 ICU library 支援二進位、不區分大小寫、不區分重音，以及語系特定的 collations。自 Databricks Runtime 16.1+ 起可用。

### Collation 類型

| Collation | 說明 | 行為 |
|-----------|------|------|
| `UTF8_BINARY` | 預設值。逐位元組比較 UTF-8 編碼 | `'A' < 'Z' < 'a'` -- 二進位順序，區分大小寫/重音 |
| `UTF8_LCASE` | 不區分大小寫的二進位定序。先轉成小寫，再以 UTF8_BINARY 比較 | `'A' == 'a'` 但 `'e' != 'é'`（區分重音） |
| `UNICODE` | ICU 根語系。與語言無關的 Unicode 排序 | `'a' < 'A' < 'á' < 'b'` -- 會將相近字元分組 |
| 語系特定 | 依 ICU locale 決定（例如 `DE`、`FR`、`JA`） | 具語言意識的排序規則 |

### Collation 語法

```
{ UTF8_BINARY | UTF8_LCASE | { UNICODE | locale } [ _ modifier [...] ] }
```

其中 `locale` 的格式為：
```
language_code [ _ script_code ] [ _ country_code ]
```

- `language_code`：ISO 639-1（例如 `EN`、`DE`、`FR`、`JA`、`ZH`）
- `script_code`：ISO 15924（例如繁體中文使用 `Hant`、拉丁文字使用 `Latn`）
- `country_code`：ISO 3166-1（例如 `US`、`DE`、`CAN`）

### Collation 修飾詞（DBR 16.2+）

| 修飾詞 | 說明 | 預設 |
|--------|------|------|
| `CS` | 區分大小寫：`'A' != 'a'` | 是（預設） |
| `CI` | 不區分大小寫：`'A' == 'a'` | 否 |
| `AS` | 區分重音：`'e' != 'é'` | 是（預設） |
| `AI` | 不區分重音：`'e' == 'é'` | 否 |
| `RTRIM` | 忽略尾端空白：`'Hello' == 'Hello '` | 否 |

每一組配對（CS/CI、AS/AI）最多只能指定一個，另外可選擇性加入 RTRIM。順序不影響結果。

### Locale 範例

| Collation 名稱 | 說明 |
|----------------|------|
| `UNICODE` | ICU 根語系，與語言無關 |
| `UNICODE_CI` | Unicode，不區分大小寫 |
| `UNICODE_CI_AI` | Unicode，不區分大小寫與重音 |
| `DE` | 德文排序規則 |
| `DE_CI_AI` | 德文，不區分大小寫與重音 |
| `FR_CAN` | 法文（加拿大） |
| `EN_US` | 英文（美國） |
| `ZH_Hant_MAC` | 繁體中文（澳門） |
| `SR` | 塞爾維亞文（由 `SR_CYR_SRN_CS_AS` 正規化） |
| `JA` | 日文 |
| `EN_CS_AI` | 英文，區分大小寫、不區分重音 |
| `UTF8_LCASE_RTRIM` | 不區分大小寫，並忽略尾端空白 |

### Collation 優先順序

由高到低：

1. **Explicit** -- 透過 `COLLATE` 表達式明確指定
2. **Implicit** -- 由欄位、field 或變數定義推導而來
3. **Default** -- 套用於字串常值與函式結果
4. **None** -- 組合不同的 implicit collations 時

在同一個表達式中混用兩種不同的 **explicit** collations 會產生錯誤。

### 在不同層級設定 Collations

#### Catalog 層級（DBR 17.1+）

```sql
-- 建立具有預設 collation 的 catalog
CREATE CATALOG customer_cat
  DEFAULT COLLATION UNICODE_CI_AI;

-- 在此 catalog 中建立的所有 schemas、tables 與 string 欄位
-- 除非另行覆寫，否則都會繼承 UNICODE_CI_AI
```

#### Schema 層級（DBR 17.1+）

```sql
-- 建立具有預設 collation 的 schema
CREATE SCHEMA my_schema
  DEFAULT COLLATION UNICODE_CI;

-- 變更新物件的預設 collation（既有物件不受影響）
ALTER SCHEMA my_schema
  DEFAULT COLLATION UNICODE_CI_AI;
```

#### Table 層級（DBR 16.3+）

```sql
-- Table 層級預設 collation
CREATE TABLE users (
  id INT,
  username STRING,           -- 從 table 預設值繼承 UNICODE_CI
  email STRING,              -- 從 table 預設值繼承 UNICODE_CI
  password_hash STRING COLLATE UTF8_BINARY  -- 明確覆寫
) DEFAULT COLLATION UNICODE_CI;
```

#### Column 層級（DBR 16.1+）

```sql
-- Column 層級 collation
CREATE TABLE products (
  id INT,
  name STRING COLLATE UNICODE_CI,
  sku STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UNICODE_CI_AI
);

-- 新增帶有 collation 的欄位
ALTER TABLE products
  ADD COLUMN category STRING COLLATE UNICODE_CI;

-- 變更欄位 collation（需要 DBR 17.2+；可能並非所有 SQL Warehouse 版本都可用）
ALTER TABLE products
  ALTER COLUMN name SET COLLATION UNICODE_CI_AI;
```

#### Expression 層級

```sql
-- 在查詢中內嵌套用 collation
SELECT *
FROM products
WHERE name COLLATE UNICODE_CI = 'laptop';

-- 檢查表達式的 collation
SELECT collation('test' COLLATE UNICODE_CI);
-- 回傳：UNICODE_CI
```

### Collation 繼承階層

```
Catalog DEFAULT COLLATION
  -> Schema DEFAULT COLLATION（覆寫 Catalog）
    -> Table DEFAULT COLLATION（覆寫 Schema）
      -> Column COLLATE（覆寫 Table）
        -> Expression COLLATE（覆寫 Column）
```

若任何層級都未指定 collation，則使用 `UTF8_BINARY`。

### 具備 Collation 感知能力的字串函式

大多數字串函式都會遵循 collation。主要的 collation-aware 操作如下：

| 函式/運算子 | Collation 行為 |
|-------------|----------------|
| `=`, `!=`, `<`, `>`, `<=`, `>=` | 比較時使用欄位/表達式的 collation |
| `LIKE` | 模式比對會遵循 collation |
| `CONTAINS(str, substr)` | 子字串搜尋會遵循 collation |
| `STARTSWITH(str, prefix)` | 前綴比對會遵循 collation |
| `ENDSWITH(str, suffix)` | 後綴比對會遵循 collation |
| `IN (...)` | 成員測試會遵循 collation |
| `BETWEEN` | 範圍比較會遵循 collation |
| `ORDER BY` | 排序會遵循 collation |
| `GROUP BY` | 分組會遵循 collation |
| `DISTINCT` | 去重會遵循 collation |
| `REPLACE(str, old, new)` | 搜尋會遵循 collation |
| `TRIM` / `LTRIM` / `RTRIM` | 修剪字元時會遵循 collation |

**效能注意：** 使用 `UTF8_LCASE` collation 的 `STARTSWITH` 與 `ENDSWITH`，相較於等效的 `LOWER()` workaround，效能最高可提升 **10 倍**。

### 公用函式

```sql
-- 取得表達式的 collation
SELECT collation(name) FROM products;

-- 列出所有支援的 collations
SELECT * FROM collations();

-- 使用 COLLATE 測試 collation
SELECT collation('hello' COLLATE DE_CI_AI);
-- 回傳：DE_CI_AI
```

### Collation 實務範例

#### 不區分大小寫的搜尋

```sql
-- 使用欄位 collation（建議方式 - 可利用索引）
CREATE TABLE users (
  id INT,
  username STRING COLLATE UTF8_LCASE,
  email STRING COLLATE UTF8_LCASE
);

INSERT INTO users VALUES
  (1, 'JohnDoe', 'John@Example.com'),
  (2, 'janedoe', 'JANE@EXAMPLE.COM');

-- 自動進行不區分大小寫的比對
SELECT * FROM users WHERE username = 'johndoe';
-- 回傳：JohnDoe

SELECT * FROM users WHERE email = 'john@example.com';
-- 回傳：John@Example.com
```

#### 使用 Expression Collation 的不區分大小寫搜尋

```sql
-- 在 UTF8_BINARY 欄位上臨時進行不區分大小寫的比較
SELECT * FROM products
WHERE name COLLATE UNICODE_CI = 'MacBook Pro';
-- 會比對到：macbook pro、MACBOOK PRO、MacBook Pro 等
```

#### 不區分重音的搜尋

```sql
-- 不區分重音的比對
CREATE TABLE cities (
  id INT,
  name STRING COLLATE UNICODE_CI_AI
);

INSERT INTO cities VALUES (1, 'Montréal'), (2, 'Montreal');

SELECT * FROM cities WHERE name = 'Montreal';
-- 會同時回傳：Montréal 與 Montreal（將 é 與 e 視為相同）
```

#### 依語系排序

```sql
-- 德文排序（umlaut 會正確排序）
SELECT name
FROM german_customers
ORDER BY name COLLATE DE;
-- 排序結果：Ärzte 會排在 Bauer 前面（在德文排序中，Ä 會視為 A+e）

-- 瑞典文排序（Å、Ä、Ö 會排在 Z 之後）
SELECT name
FROM swedish_customers
ORDER BY name COLLATE SV;
```

#### 尾端空白處理

```sql
-- RTRIM 修飾詞會忽略尾端空白
SELECT 'Hello' COLLATE UTF8_BINARY_RTRIM = 'Hello   ';
-- 回傳：true

SELECT 'Hello' COLLATE UTF8_BINARY = 'Hello   ';
-- 回傳：false
```

#### 整個 Catalog 的不區分大小寫設定

```sql
-- 建立一個預設全部不區分大小寫的 catalog
CREATE CATALOG app_data DEFAULT COLLATION UNICODE_CI;

USE CATALOG app_data;
CREATE SCHEMA users_schema;
USE SCHEMA users_schema;

-- 所有 STRING 欄位都會自動使用 UNICODE_CI
CREATE TABLE accounts (
  id INT,
  username STRING,  -- 從 catalog 繼承 UNICODE_CI
  email STRING       -- 從 catalog 繼承 UNICODE_CI
);

-- 查詢會自動變成不區分大小寫
SELECT * FROM accounts WHERE username = 'admin';
-- 會比對到：admin、ADMIN、admin、aDmIn 等
```

### 限制與注意事項

- `CHECK` 條件約束與 generated column expressions 需要 `UTF8_BINARY` 預設 collation。
- `hive_metastore` catalog tables 不支援 collation constraints。
- `ALTER SCHEMA ... DEFAULT COLLATION` 只會影響新建立的物件，不會影響既有物件。
- 在同一個表達式中混用兩種不同的 explicit collations 會引發錯誤。
- `UTF8_LCASE` 會在 Databricks 內部用於 identifier resolution（catalog、schema、table、column 名稱）。
- Databricks 會透過移除預設值來正規化 collation 名稱（例如 `SR_CYR_SRN_CS_AS` 會簡化為 `SR`）。
- Collation 修飾詞需要 Databricks Runtime 16.2+。
- Catalog/Schema 層級的 `DEFAULT COLLATION` 需要 Databricks Runtime 17.1+。