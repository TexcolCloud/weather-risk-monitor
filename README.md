# 示例区域机房天气灾害预警

该工具读取 `weather_analysis/data/sites.example.json` 中的示例区域机房清单，调用和风天气日预报、小时预报和官方预警接口，生成供管理人员转发的极端天气风险简报。

## 运行

项目使用 Python 3.10 或更高版本：

```powershell
uv sync
uv run weather-analysis daemon
```

首次运行前，在项目根目录创建 `.env` 并配置和风天气 API Key；可参考 `.env.example`：

```dotenv
QWEATHER_API_KEY=your-api-key
```

### 常驻定时任务

```powershell
weather-analysis daemon
```

守护进程会在每个整点执行一次机房风险预测，并分别输出下一小时风险和未来3小时重点过程；每天 `08:30`、`20:30` 执行完整7天预测。启动后默认立即检查下一完整小时，可用 `--no-immediate` 关闭；若启动时间距离下一整点不超过60秒，则跳过即时检查并交由正式整点任务执行。

风险等级以和风天气按机房经纬度返回的温度、风力、降水和天气现象为准；官方预警仅附在已经达到数据风险阈值的机房中，作为辅助信息。

守护进程使用运行数据目录下的 `runtime/` 保存完整预测的执行状态并防止重复启动。启动后会补跑当天已错过且尚未完成的 `08:10` 或 `20:10` 完整预测；启动即时检查仅生成本地预览，正式整点任务会绕过缓存重新获取数据并登记待外发结果。

```powershell
weather-analysis hourly --at 2026-07-15T09:00+08:00
```

运行日志保存在运行数据目录的 `logs/weather-analysis.log`，按日轮转并保留30天。完整报告和逐小时审计结果保存在 `reports/`，待外发清单保存在 `outbox/`；默认不会发送网络消息。

运行数据目录暂时默认为项目根目录，因此 `logs/`、`cache/`、`reports/`、`outbox/` 和 `runtime/` 都直接保存在项目内。可通过 `WEATHER_ANALYSIS_DATA_DIR` 统一指定其他目录。

报告、审计与待外发文件默认保留365天，可通过 `WEATHER_ANALYSIS_ARTIFACT_RETENTION_DAYS` 调整。和风天气请求默认限制为每秒10次，可通过 `WEATHER_ANALYSIS_MAX_REQUESTS_PER_SECOND` 调整。

清除本地天气缓存：

```powershell
weather-analysis --clear-cache
```

缓存默认写入运行数据目录的 `cache/`，仍可通过 `WEATHER_ANALYSIS_CACHE_DIR` 单独指定其他目录。

## 测试

```powershell
python -m unittest discover -s tests -v
```

天气接口全部失败时，命令仍会输出数据缺失报告，并以状态码 `2` 退出，便于定时任务识别异常。

## 目录结构

```text
.
├── .env.example             # API Key 配置示例
├── .gitignore               # 本地配置和运行产物忽略规则
├── README.md
├── pyproject.toml           # 项目元数据、依赖与命令行入口
├── uv.lock                  # 锁定的依赖版本
├── tests/                   # 单元测试
└── weather_analysis/
    ├── __init__.py
    ├── aggregation.py       # 机房到区县的风险聚合
    ├── artifacts.py         # 报告、审计结果与 outbox 存储
    ├── cache.py             # 本地接口缓存
    ├── cli.py               # 命令行入口
    ├── config.py            # 环境配置和机房清单加载
    ├── data/
    │   └── sites.example.json  # 示例区域机房基础数据
    ├── hourly_report.py     # 逐小时风险简报
    ├── logging_config.py    # 日志配置与轮转
    ├── models.py            # 模块间数据结构
    ├── paths.py             # 项目内运行数据目录解析
    ├── qweather_client.py   # 和风天气请求与响应归一化
    ├── report.py            # 完整预测报告文案与排版
    ├── runtime_state.py     # 守护进程锁和执行状态
    ├── scheduler.py         # 定时任务调度
    ├── selectors.py         # 重点机房选择
    ├── warning_rules.py     # 灾害规则、等级与排序
    ├── weather.py           # 多数据源采集编排
    └── weather_stats.py     # 小时和日预报统计
```
