# 苍穹织网 数据字典与验收状态 (Data Dictionary & Status)

**当前状态**：第一阶段原始数据募集与 Python 预处理**已全部竣工验收**。所有前端页面目前直接从 `data/processed/` 加载格式化好的可用数据。

**覆盖城市**：深圳南山、北京核心（朝阳+海淀+西城）、上海核心（浦东+静安+黄浦）、广州核心（天河+越秀+海珠）、成都核心（锦江+武侯+高新）、重庆主城（渝中+南岸+江北+沙坪坝）

---

## 1. 无人机轨迹数据集 (UAV Trajectories)

用于记录每一架无人机在空中的三维活动与姿态数据。
**存储位置**: `data/processed/trajectories/uav_trajectories.csv`

| 字段名 (Field Name) | 数据类型 (Type) | 单位 (Unit) | 描述 (Description) | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| `flight_id` | String | - | 航班/任务唯一标识符 | 用于区分不同的飞行架次 |
| `timestamp` | Float/Int | Unix/ms | 记录当前时间戳 | 秒级Unix时间戳偏移 |
| `lat` | Float | Degree | WGS84 纬度 | 如 22.5333 |
| `lon` | Float | Degree | WGS84 经度 | 如 113.9300 |
| `alt_abs` | Float | Meters (m) | 绝对海拔高度 | 基于MSL |
| `alt_rel` | Float | Meters (m) | 相对起飞点高度 | 50m - 120m巡航区间 |
| `speed_x` | Float | m/s | X轴速度分量 (东西向) | - |
| `speed_y` | Float | m/s | Y轴速度分量 (南北向) | - |
| `speed_z` | Float | m/s | Z轴速度分量 (垂直向上) | - |
| `roll` | Float | Degree/Rad | 滚转角 | 飞行器绕纵轴旋转角 |
| `pitch` | Float | Degree/Rad | 俯仰角 | 飞行器绕横轴旋转角 |
| `yaw` | Float | Degree/Rad | 偏航角 | 飞行器绕立轴旋转角 |
| `battery_rem` | Float | % / mAh | 剩余电量 | 评估耗能模型的核心字段 |

---

## 2. 城市三维建筑地理底座 (Urban 3D Buildings)

用于碰撞检测与微气象生成的城市物理空间多边形。
**存储位置**: `data/processed/{city}/buildings_3d.geojson`

*数据格式: GeoJSON (FeatureCollection)*

| 属性名 (Property) | 数据类型 (Type) | 描述 (Description) |
| :--- | :--- | :--- |
| `osm_id` | String | OpenStreetMap 中的原始建筑 ID。 |
| `name` | String | 建筑名称。 |
| `building` | String | 建筑类型 (如 `commercial`, `residential`, `yes`)。 |
| `height` | Float | 建筑绝对高度(米)。由 Python 脚本依据真实楼层乘3米推断，或基于高区正态分布随机生成兜底。 |
| `geometry` | Polygon | 建筑底部轮廓经纬度多边形集合。 |

---

## 3. 敏感禁飞区与需求起降点 (POI Nodes)

用于规划审批的避障红区和机坪选址的热力源。
**存储位置**: 
- `data/processed/{city}/poi_sensitive.geojson` (红色禁飞基站)
- `data/processed/{city}/poi_demand.geojson` (绿色起降热力点)

*数据格式: GeoJSON (FeatureCollection)*

| 属性名 (Property) | 数据类型 (Type) | 描述 (Description) |
| :--- | :--- | :--- |
| `poi_id` | String | 抓取来源的唯一ID。 |
| `name` | String | POI 名称 (如 "南山区人民医院")。 |
| `type` | String | 类别 (如 `hospital`, `school`, `office`, `residential`)。 |
| `weight` | Float | 权重值 (例如：禁飞权重或物流吞吐量权重)。 |
| `geometry` | Point | 真实的经纬度坐标点。 |

---

## 4. 真实无人机飞行能耗数据集 (AirLab Flight Energy)

来自卡内基梅隆大学 AirLab 的 DJI Matrice 100 真实飞行实验数据，共 188 次飞行。

**来源**: CMU AirLab — [DOI: 10.1184/R1/12683453](https://doi.org/10.1184/R1/12683453)  
**设备**: DJI Matrice 100 (工业级四旋翼)  
**存储位置**: `data/raw/airlab_energy/data/{flight_number}/processed.csv`  
**实验参数**: 载荷 0g/250g/500g，高度 25-100m，速度 4-12 m/s  
**采样率**: 10 Hz

| 字段名 (Field Name) | 数据类型 (Type) | 单位 (Unit) | 描述 (Description) |
| :--- | :--- | :--- | :--- |
| `time` | Float | Seconds (s) | 飞行时间戳 |
| `airspeed` | Float | m/s | 空速 (相对于空气的速度) |
| `vertspd` | Float | m/s | 垂直速度 |
| `psi` | Float | Radians | 风向角 (NED 坐标系) |
| `aoa` | Float | Radians | 攻角 (angle of attack) |
| `theta` | Float | Radians | 俯仰角 |
| `diffalt` | Float | Meters (m) | 相对起飞点高度差 |
| `density` | Float | kg/m³ | 当时空气密度 (由METAR气象站实测) |
| `payload` | Float | kg | 载荷重量 (0 / 0.25 / 0.5) |
| `power` | Float | Watts (W) | 瞬时功率 (= 电压 × 电流) |
| `airspeed_x` | Float | m/s | 空速 X 分量 |
| `airspeed_y` | Float | m/s | 空速 Y 分量 |
