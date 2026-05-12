# chaogu

个人量化投资工具 MVP，目标是先把策略研发、回测、纸面交易和风控闭环跑起来，再按你的券商/交易所接口接入实盘。

当前版本只内置纸面交易执行器，不会真实下单。实盘接入需要你明确选择券商 API，并在 `chaogu/broker.py` 里实现 `LiveBrokerAdapter`，同时保留预交易风控。

## 已实现

- CSV 行情读取，字段为 `timestamp,symbol,open,high,low,close,volume`
- 策略：均线交叉、区间突破、RSI 均值回归、动量过滤
- 预交易风控：最大仓位、单笔最大金额、现金缓冲、日内最大亏损、止损、止盈、最小下单金额、A 股一手数量约束
- 回测：输出收益、最大回撤、成交次数、胜率、资金曲线和成交明细
- 纸面交易：可重复读取追加到 CSV 的新 K 线，维护本地状态
- 历史数据下载：可选接入 AkShare 或 xtquant，导出为本项目 CSV 格式
- 本地 HTML 控制台：页面完成配置、数据下载、历史验证、Python 选股、实盘轮询启停，后台 API 执行任务并用图表和完整表格展示结果
- 零第三方依赖，直接用 Python 标准库运行

## 快速运行

启动本地控制台：

```bash
python3 -m chaogu web --host 127.0.0.1 --port 8765
```

然后打开：

```text
http://127.0.0.1:8765/
```

控制台提供两个模式：

- 历史验证：选择/编辑配置，下载历史数据，启动后台回测任务，查看收益、回撤、资金曲线、全部成交、全部资金流水和输出文件。
- 实盘操作：选择模拟实盘或真实券商通道，启动/停止后台轮询任务，查看资金曲线、持仓、全部成交、全部资金流水和任务日志。

如果端口已被占用，说明本地已有控制台进程在运行；直接打开上面的地址，或者换端口：

```bash
python3 -m chaogu web --port 8766
```

命令行仍可直接运行回测：

```bash
python3 -m chaogu backtest --config config.example.json --out runs/backtest
```

也可以直接跑 A 股预设：

```bash
python3 -m chaogu backtest --config configs/a_share_sma_trend.json --out runs/backtest/a_share_sma_trend
python3 -m chaogu backtest --config configs/a_share_breakout_20d.json --out runs/backtest/a_share_breakout_20d
python3 -m chaogu backtest --config configs/a_share_rsi_mean_reversion.json --out runs/backtest/a_share_rsi_mean_reversion
python3 -m chaogu backtest --config configs/a_share_momentum_20d.json --out runs/backtest/a_share_momentum_20d
```

输出文件：

- `runs/backtest/summary.json`
- `runs/backtest/equity_curve.csv`
- `runs/backtest/fills.csv`

纸面交易处理 CSV 中尚未处理的新行情：

```bash
python3 -m chaogu paper --config config.example.json --state runs/paper_state.json
```

持续轮询 CSV：

```bash
python3 -m chaogu paper --config config.example.json --state runs/paper_state.json --watch
```

运行测试：

```bash
python3 -m unittest discover -s tests
```

## 历史数据

本项目回测只要求 CSV 字段为 `timestamp,symbol,open,high,low,close,volume`。你可以用自己的数据源生成这个格式，也可以使用内置下载命令。

用 AkShare 下载 A 股日线前复权数据：

```bash
python3 -m pip install akshare
python3 -m chaogu download \
  --provider akshare \
  --symbol 000001.SZ \
  --start 2020-01-01 \
  --end 2025-12-31 \
  --adjust qfq \
  --out data/000001.SZ.daily.qfq.csv
```

用迅投 `xtquant` 下载历史数据：

```bash
python3 -m chaogu download \
  --provider xtquant \
  --symbol 000001.SZ \
  --start 2020-01-01 \
  --end 2025-12-31 \
  --adjust front \
  --out data/000001.SZ.daily.front.csv
```

然后把配置里的 `symbol` 和 `market_data_csv` 指向下载后的文件：

```json
{
  "symbol": "000001.SZ",
  "market_data_csv": "data/000001.SZ.daily.qfq.csv"
}
```

## Python 选股

选股基于本地 CSV 历史行情，不直接依赖券商接口。先把多个股票的历史数据下载到 `data/`，再使用控制台里的“Python 选股”，或用命令行：

```bash
python3 -m chaogu screen \
  --pattern 'data/*.csv' \
  --lookback 20 \
  --short-window 5 \
  --long-window 20 \
  --min-return-pct 0.03 \
  --min-avg-volume 1000000 \
  --limit 50
```

当前内置的是一个轻量动量趋势筛选器：

- 最近 `lookback` 根 K 线收益率达到阈值。
- 短均线高于长均线，且收盘价高于长均线。
- 最近 `lookback` 根 K 线平均成交量达到阈值。
- 按收益、趋势状态和均线强度打分排序。

选股逻辑在 `chaogu/screener.py`。它的输出是候选股票列表，不是买入指令；候选标的仍需要进入策略回测、风控检查和实盘灰度。

## 图形化结果

控制台右侧“结果”区域会按任务类型展示：

- 回测：指标卡、权益/现金曲线、全部成交记录、全部资金流水、全部资金曲线数据。
- 模拟实盘：指标卡、实时权益/现金曲线、当前持仓、全部成交记录、全部资金流水、每轮轮询资金记录。
- 选股：候选股指标卡和候选列表。
- 数据下载：下载源、标的、日期、行数和输出文件。

资金流水由成交记录计算得到，字段包括成交额、手续费、现金变化、累计现金影响和已实现盈亏；实现位置在 `chaogu/ledger.py`。

## 配置说明

核心参数在 `config.example.json`：

- `market_data_csv`: 行情 CSV 路径
- `starting_cash`: 初始资金
- `strategy.name`: 策略名，可选 `moving_average_cross`、`breakout`、`rsi_mean_reversion`、`momentum`
- `strategy.target_weight`: 策略看多时的目标仓位
- `strategy.short_window` / `strategy.long_window`: 均线策略短/长窗口
- `strategy.entry_window` / `strategy.exit_window`: 突破策略入场/退出窗口
- `strategy.rsi_window` / `strategy.buy_below` / `strategy.sell_above`: RSI 策略窗口和阈值
- `strategy.lookback_window` / `strategy.entry_return_pct` / `strategy.exit_return_pct`: 动量策略回看窗口和收益率阈值
- `risk.max_position_pct`: 单标的最大仓位比例
- `risk.max_order_value`: 单笔最大下单金额
- `risk.max_daily_loss_pct`: 当日亏损达到阈值后只允许降风险
- `risk.stop_loss_pct`: 持仓相对成本价止损
- `risk.take_profit_pct`: 持仓相对成本价止盈
- `risk.lot_size`: 下单股数交易单位，A 股通常配置为 `100`
- `execution.commission_bps`: 手续费，单位 bps
- `execution.slippage_bps`: 滑点，单位 bps

## A 股策略预设

- `configs/a_share_sma_trend.json`: 5/20 日均线趋势跟随。
- `configs/a_share_breakout_20d.json`: 20 日高点突破入场，10 日低点退出。
- `configs/a_share_rsi_mean_reversion.json`: 14 日 RSI 低吸，高于阈值退出。
- `configs/a_share_momentum_20d.json`: 20 日收益率动量过滤。

这些预设都使用 `lot_size=100`，但仍然是日线级单标的 MVP；尚未模拟涨跌停、停牌、T+1、融券、印花税、复权和集合竞价等真实 A 股细节。

## 接实盘的边界

实盘只应该替换执行层，不应该绕开策略、回测和风控：

1. 在券商侧申请 API 权限，并确认可交易品种、账户类型、限速、订单类型和程序化交易报备要求。
2. 在 `LiveBrokerAdapter.place_order()` 中实现真实下单。
3. 先用最小资金和最小订单权限灰度运行。
4. 保留 `RiskManager` 的预交易检查，并在券商侧再配置账户级风控。

迅投 Linux 版 `xtquant` 只适合做行情数据接入。官方说明 Linux 环境目前需要投研专业版以上权限，且只支持 `xtdata`，不支持 `xttrade`；如果要通过 QMT/miniQMT 做实盘交易，交易端通常仍需要在 Windows 客户端环境完成，再由本项目对接交易适配层。

本项目不是投资建议，也不保证盈利。自动交易可能在很短时间内放大错误，所有策略必须先通过历史回测、纸面交易和小规模验证。
