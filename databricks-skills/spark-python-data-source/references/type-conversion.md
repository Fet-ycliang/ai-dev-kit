# 型別轉換

Spark 型別與外部系統型別間的雙向對應。

## Spark 轉換至外部系統

將 Spark/Python 值轉換至外部系統型別：

```python
def convert_spark_to_external(value, external_type):
    """將 Spark/Python 值轉換至外部系統型別。"""
    if value is None:
        return None

    external_type_lower = external_type.lower()

    # UUID 轉換
    if "uuid" in external_type_lower:
        import uuid
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))

    # 時間戳記轉換
    if "timestamp" in external_type_lower:
        from datetime import datetime
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)

    # IP 位址轉換
    if "inet" in external_type_lower:
        import ipaddress
        if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return value
        return ipaddress.ip_address(str(value))

    # 十進位轉換
    if "decimal" in external_type_lower:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    # 集合
    if "list" in external_type_lower or "set" in external_type_lower:
        if not isinstance(value, (list, set)):
            raise ValueError(f"預期清單/集合，得到 {type(value)}")
        return list(value)

    if "map" in external_type_lower:
        if not isinstance(value, dict):
            raise ValueError(f"預期字典，得到 {type(value)}")
        return value

    # 數值型別
    if "int" in external_type_lower:
        return int(value)
    if "float" in external_type_lower or "double" in external_type_lower:
        return float(value)

    # 布林值
    if "bool" in external_type_lower:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    # 預設：按原樣傳回
    return value
```

## 外部系統轉換至 Spark

將外部值轉換至 Spark 型別：

```python
def convert_external_to_spark(value, spark_type):
    """將外部系統值轉換至 Spark 型別。"""
    from pyspark.sql.types import (
        StringType, IntegerType, LongType, FloatType, DoubleType,
        BooleanType, TimestampType, DateType
    )
    from datetime import datetime, date

    if value is None:
        return None

    try:
        if isinstance(spark_type, StringType):
            return str(value)

        elif isinstance(spark_type, BooleanType):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)

        elif isinstance(spark_type, (IntegerType, LongType)):
            if isinstance(value, bool):
                raise ValueError("無法將布林值轉換為整數")
            return int(value)

        elif isinstance(spark_type, (FloatType, DoubleType)):
            if isinstance(value, bool):
                raise ValueError("無法將布林值轉換為浮點數")
            return float(value)

        elif isinstance(spark_type, TimestampType):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            raise ValueError(f"無法將 {type(value)} 轉換為時間戳記")

        elif isinstance(spark_type, DateType):
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            raise ValueError(f"無法將 {type(value)} 轉換為日期")

        else:
            return value

    except (ValueError, TypeError) as e:
        raise ValueError(
            f"無法轉換 '{value}'（型別：{type(value).__name__}）"
            f"至 {spark_type}：{e}"
        )
```

## Cassandra 特定型別

處理 Cassandra 複雜型別：

```python
def convert_cassandra_to_spark(value):
    """處理 Cassandra 特定複雜型別。"""
    if value is None:
        return None

    from cassandra.util import (
        Date, Time, Duration, OrderedMap, SortedSet,
        Point, LineString, Polygon
    )
    import uuid

    # Cassandra Date 至 Python date
    if isinstance(value, Date):
        return value.date()

    # Cassandra Time 至奈秒 (LongType)
    if isinstance(value, Time):
        return value.nanosecond

    # UUID 至字符串
    if isinstance(value, uuid.UUID):
        return str(value)

    # Duration 至結構化字典
    if isinstance(value, Duration):
        return {
            "months": value.months,
            "days": value.days,
            "nanoseconds": value.nanoseconds
        }

    # OrderedMap 至字典
    if isinstance(value, OrderedMap):
        return dict(value)

    # SortedSet 至清單
    if isinstance(value, SortedSet):
        return list(value)

    # 地理空間型別至 WKT 字符串
    if isinstance(value, (Point, LineString, Polygon)):
        return str(value)

    return value
```

## 綱要推斷

從 Python 值推斷 Spark 型別：

```python
def infer_spark_type(value):
    """從 Python 值推斷 Spark 型別。"""
    from pyspark.sql.types import (
        StringType, IntegerType, LongType, FloatType, DoubleType,
        BooleanType, TimestampType, DateType
    )
    from datetime import datetime, date

    if value is None:
        return StringType()

    # 檢查布林值先於整數（布林值為整數的子類別）
    if isinstance(value, bool):
        return BooleanType()

    if isinstance(value, int):
        return LongType()

    if isinstance(value, float):
        return DoubleType()

    if isinstance(value, datetime):
        return TimestampType()

    if isinstance(value, date):
        return DateType()

    # 預設為字符串
    return StringType()
```

## 外部型別至 Spark 型別對應

將外部系統型別對應至 Spark 型別：

```python
def map_external_type_to_spark(external_type):
    """將外部系統型別對應至 Spark 型別。"""
    from pyspark.sql.types import (
        StringType, IntegerType, LongType, FloatType, DoubleType,
        BooleanType, TimestampType, DateType, BinaryType
    )

    type_str = str(external_type).lower()

    # 字符串型別
    if any(t in type_str for t in ["varchar", "text", "char", "string", "uuid"]):
        return StringType()

    # 整數型別
    if "int" in type_str and "big" not in type_str:
        return IntegerType()
    if "bigint" in type_str or "long" in type_str:
        return LongType()

    # 浮點
    if "float" in type_str:
        return FloatType()
    if "double" in type_str or "decimal" in type_str:
        return DoubleType()

    # 布林值
    if "bool" in type_str:
        return BooleanType()

    # 時間型別
    if "timestamp" in type_str:
        return TimestampType()
    if "date" in type_str:
        return DateType()

    # 二進位
    if "blob" in type_str or "binary" in type_str:
        return BinaryType()

    # 預設回復
    return StringType()
```

## JSON 編碼

處理 JSON API 的 datetime 序列化：

```python
import json
from datetime import date, datetime
from decimal import Decimal

class ExtendedJsonEncoder(json.JSONEncoder):
    """處理 datetime、date 和 Decimal 的 JSON 編碼器。"""

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()

        if isinstance(o, Decimal):
            return float(o)

        return super().default(o)

# 用法
def send_as_json(data):
    import requests

    payload = json.dumps(data, cls=ExtendedJsonEncoder)
    requests.post(url, data=payload, headers={"Content-Type": "application/json"})
```

## 完整列轉換

使用綱要轉換整個列：

```python
def convert_row_to_external(row, column_types):
    """將整個 Spark 列轉換至外部系統格式。"""
    row_dict = row.asDict() if hasattr(row, "asDict") else dict(row)

    converted = {}
    for col, value in row_dict.items():
        external_type = column_types.get(col, "text")
        converted[col] = convert_spark_to_external(value, external_type)

    return converted

def convert_external_to_row(data, schema):
    """將外部資料轉換至 Spark Row。"""
    from pyspark.sql import Row

    # 建立欄名至型別的對應
    schema_map = {field.name: field.dataType for field in schema.fields}

    row_dict = {}
    for col, value in data.items():
        if col in schema_map:
            spark_type = schema_map[col]
            row_dict[col] = convert_external_to_spark(value, spark_type)

    # 為缺少欄新增 None
    for field in schema.fields:
        if field.name not in row_dict:
            row_dict[field.name] = None

    return Row(**row_dict)
```

## 驗證

驗證型別轉換：

```python
def validate_conversion(value, expected_type):
    """驗證值在轉換後符合預期型別。"""
    type_checks = {
        "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "long": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "double": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "timestamp": lambda v: isinstance(v, datetime),
        "date": lambda v: isinstance(v, date) and not isinstance(v, datetime),
    }

    expected_type_lower = expected_type.lower()
    for type_name, check in type_checks.items():
        if type_name in expected_type_lower:
            if not check(value):
                raise ValueError(
                    f"值 {value}（型別：{type(value)}）不符合"
                    f"預期型別 {expected_type}"
                )
            return

    # 無特定檢查 - 接受任何值
```
