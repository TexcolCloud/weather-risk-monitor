# Weather Risk Monitor

**按站点位置分析天气风险，定时生成可核查的预警报告。**

一个基于 Python 的天气分析命令行工具。接入和风天气逐小时预报与官方预警，分析温度、风力、降水和天气现象，输出完整预测摘要及整点风险报告。

[快速开始](#快速开始) · [使用方式](#使用方式) · [工作原理](#工作原理) · [开发](#开发)

## 功能概览

- **完整预测：** 汇总 168 小时预报，按区域和站点生成风险摘要。
- **整点检查：** 分别报告下一小时和未来 3 小时的重点风险。
- **定时运行：** 支持任务互斥、执行状态记录及当天错过的完整预测补跑。
- **请求管理：** 并发与速率限制、缓存、失败重试，记录数据缺失情况。
- **本地产物：** 文本报告、JSON 审计结果及待投递清单，便于检查和后续接入通知服务。

> 仓库只包含虚构站点样例。实际查询必须指定本地站点文件和天气凭据；本项目不自动发送网络消息。

## 快速开始

需要 **Python 3.10+** 和 [uv](https://docs.astral.sh/uv/)。下面使用 PowerShell：

```powershell
git clone https://github.com/TexcolCloud/weather-risk-monitor.git
cd weather-risk-monitor

uv sync
uv run python -m unittest discover -s tests -v
```

测试使用模拟天气响应，不需要 API Key，也不请求真实天气。

## 使用方式

准备仅在本机保存的配置：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force private-data
Copy-Item weather_analysis/data/sites.example.json private-data/sites.local.json
```

在 `.env` 中填写自己的 `QWEATHER_API_KEY`，并保持 `WEATHER_ANALYSIS_SITES_FILE=private-data/sites.local.json`。将站点文件替换为获准使用的数据：

```json
[
  {"county": "示例区域", "name": "示例站点", "lon": 0.0, "lat": 0.0}
]
```

样例坐标仅说明格式，不代表真实设施。名称和区域不能为空，经纬度必须有效。准备好配置后运行：

```powershell
# 单次完整预测
uv run weather-analysis

# 常驻：整点风险检查，每天 08:30 和 20:30 完整预测
uv run weather-analysis daemon
```

时区为 `Asia/Shanghai`，用 `Ctrl+C` 停止。`hourly`、`--no-immediate`、缓存及保留策略见 [配置与运行](docs/USAGE.md)。

## 工作原理

```text
本地站点配置 → 和风天气请求 → 统计与风险规则 → 报告
                    │                           │
                 缓存 / 重试             reports / outbox
                                                │
                                     本地审计与后续通知接入
```

风险提示以预报数据和项目规则为依据，官方预警作为辅助信息。接口全部失败时仍保留缺失数据报告，并返回退出码 `2`；不能将缺失数据理解为无风险。

阈值属于应用规则，不代表官方预警标准。真实账户需具备对应接口权限；接口地址及预测长度见 `weather_analysis/config.py`。

## 输出与配置

| 目录 | 内容 |
| --- | --- |
| `reports/` | 文本报告、JSON 审计结果 |
| `outbox/` | 本地待投递清单，不自动发送 |
| `runtime/` | 进程锁及任务执行状态 |
| `cache/` | 天气接口缓存 |
| `logs/` | 按日轮转的日志 |

默认写入项目根目录，可用 `WEATHER_ANALYSIS_DATA_DIR` 调整。其他环境变量、任务时序与保留时间见 [配置与运行](docs/USAGE.md)。

`.env`、`private-data/`、`*.local.json` 及运行目录已加入忽略规则。运行报告可能包含本机站点信息，不应提交真实位置或业务报告。

## 开发

```powershell
uv run python -m unittest discover -s tests -v
```

测试覆盖响应归一化、天气统计、风险规则、报告、调度、运行状态和站点配置；不代表真实天气预测的准确率。

| 模块 | 职责 |
| --- | --- |
| `qweather_client.py` / `weather.py` | 请求与多站点采集 |
| `warning_rules.py` / `weather_stats.py` | 规则与统计 |
| `report.py` / `hourly_report.py` | 报告生成 |
| `scheduler.py` / `runtime_state.py` | 调度与执行状态 |
| `artifacts.py` | 报告和审计产物 |

提交问题请使用虚构站点与脱敏日志。修改风险规则或报告逻辑时，请附上可复现的测试。
