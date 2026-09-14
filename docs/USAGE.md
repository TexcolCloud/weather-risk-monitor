# 配置与运行

## 运行方式

```powershell
# 单次完整预测
uv run weather-analysis

# 整点风险检查，每天 08:30、20:30 完整预测
uv run weather-analysis daemon

# 不执行启动时的即时检查
uv run weather-analysis daemon --no-immediate

# 指定时间的逐小时风险检查
uv run weather-analysis hourly --at 2026-01-01T09:00+08:00

# 清除缓存
uv run weather-analysis --clear-cache
```

时区为 `Asia/Shanghai`。启动默认检查下一完整小时；距离下一整点不超过 60 秒时交由正式任务执行。使用 `Ctrl+C` 停止。

接口全部失败时保留缺失数据报告，并返回退出码 `2`。部分数据失败应结合报告和日志判断，不应将缺失数据当成无风险。风险规则是应用阈值，不代表官方预警标准。

## 配置与输出

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `QWEATHER_API_KEY` | 天气凭据 | 空，查询时必填 |
| `WEATHER_ANALYSIS_SITES_FILE` | 本地站点 JSON | CLI 查询时必须指定 |
| `WEATHER_ANALYSIS_DATA_DIR` | 运行数据根目录 | 项目根目录 |
| `WEATHER_ANALYSIS_CACHE_DIR` | 缓存位置 | 数据目录下 `cache/` |
| `WEATHER_ANALYSIS_MAX_REQUESTS_PER_SECOND` | 请求速率 | `10` |
| `WEATHER_ANALYSIS_ARTIFACT_RETENTION_DAYS` | 产物保留天数 | `365` |

| 目录 | 内容 |
| --- | --- |
| `reports/` | 文本报告和 JSON 审计结果 |
| `outbox/` | 本地待投递清单，不自动发送 |
| `runtime/` | 进程锁及任务状态 |
| `cache/` | 接口缓存 |
| `logs/` | 按日轮转的日志，默认保留 30 天 |

运行产物可能包含本机填入的站点信息。`.env`、`private-data/`、`*.local.json` 和运行目录已加入忽略规则，不应提交真实位置或报告。
