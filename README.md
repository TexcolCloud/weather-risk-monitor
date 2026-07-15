# 示例区域机房天气灾害预警

该工具读取 `weather_analysis/data/sites.example.json` 中的示例区域机房清单，调用和风天气日预报、小时预报和官方预警接口，生成供管理人员转发的极端天气风险简报。

## 运行

项目使用 Python 3.10 或更高版本：

```powershell
python -m pip install -e .
weather-analysis
```

### 常驻定时任务

```powershell
weather-analysis daemon
```

守护进程会在每个整点执行一次机房风险预测，并分别输出下一小时风险和未来3小时重点过程；每天 `08:10`、`20:10` 执行完整7天预测。启动后默认立即检查下一完整小时，可用 `--no-immediate` 关闭。

风险等级以和风天气按机房经纬度返回的温度、风力、降水和天气现象为准；官方预警仅附在已经达到数据风险阈值的机房中，作为辅助信息。

```powershell
weather-analysis hourly --at 2026-07-15T09:00+08:00
```

运行日志保存在 `logs/weather-analysis.log`，按日轮转并保留30天。完整报告和逐小时审计结果保存在 `reports/`，待外发清单保存在 `outbox/`；默认不会发送网络消息。

清除本地天气缓存：

```powershell
weather-analysis --clear-cache
```

缓存默认写入项目根目录的 `.cache/`，可通过 `WEATHER_ANALYSIS_CACHE_DIR` 指定其他目录。

## 测试

```powershell
python -m unittest discover -s tests -v
```

天气接口全部失败时，命令仍会输出数据缺失报告，并以状态码 `2` 退出，便于定时任务识别异常。

## 目录结构

```text
weather_analysis/
├── data/sites.example.json  # 示例区域机房基础数据
├── models.py                # 模块间数据结构
├── qweather_client.py       # 和风天气请求与响应归一化
├── weather_stats.py         # 小时和日预报统计
├── weather.py               # 多数据源采集编排
├── warning_rules.py         # 灾害规则、等级与排序
├── aggregation.py           # 机房到区县的风险聚合
├── selectors.py             # 重点机房选择
├── report.py                # 报告文案与排版
├── cache.py                 # 本地接口缓存
├── config.py                # 运行配置和机房清单加载
└── cli.py                   # 命令行入口
```
