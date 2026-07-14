# 示例区域机房天气灾害预警

该工具读取 `qweather_none_agent/data/sites.example.json` 中的示例区域机房清单，调用和风天气日预报、小时预报和官方预警接口，生成供管理人员转发的极端天气风险简报。

## 运行

项目使用 Python 3.10 或更高版本：

```powershell
python -m pip install -e .
qweather-none-agent
```

清除本地天气缓存：

```powershell
qweather-none-agent --clear-cache
```

缓存默认写入当前用户缓存目录，可通过 `QWEATHER_CACHE_DIR` 指定其他目录。

## 测试

```powershell
python -m unittest discover -s tests -v
```

天气接口全部失败时，命令仍会输出数据缺失报告，并以状态码 `2` 退出，便于定时任务识别异常。

## 目录结构

```text
qweather_none_agent/
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
