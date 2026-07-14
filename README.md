# 示例区域机房天气灾害预警

该工具读取示例区域机房清单，调用和风天气日预报、小时预报和官方预警接口，生成供管理人员转发的极端天气风险简报。

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
