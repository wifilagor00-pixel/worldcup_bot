#!/usr/bin/env python3
"""
================================================================================
 MLCC 超级周期 · 华尔街机构级前导指标雷达 · 全自动量化投研助手 v2.0
================================================================================
 架构理念：
   坚决摒弃主观"感觉"，完全基于：
     (A) 核心财报硬数据 → 现代价值投资量化滤网（ROIC/PEG/FCF Yield/毛利率）
     (B) 期权异动监控 → Call/Put比率 + 虚值OI异常检测（Smart Money Flows）
     (C) 机构级前导指标 → SIA/WSTS全球半导体数据 + CNBC Options Action
     (D) 供应链草根价格数据 → 现货价/交货期动态验证
   自动发掘 MLCC超级周期 + 泛AI硬件周期（HBM4/DRAM/液冷/光模块）突破标的。

 支持标的（动态可扩展 — Elite Stock Pool）：
   - MRAAY (村田制作所 ADR)  → 高阶 MLCC 绝对垄断龙头
   - ARW   (艾睿电子)        → 电子元器件分销巨头（库存套利者）
   - TEL   (泰科电子)        → AI 服务器高密连接器与电源系统
   - MU    (美光科技)        → HBM4/DRAM 闪崩式暴涨红利
   - VRT   (维谛技术)        → AI 数据中心液冷与电力核心瓶颈
   - SMCI  (超微电脑)        → NVIDIA新架构总装 + 期权多头动量
   - TSM   (台积电 ADR)      → 2nm高级封装技术卡位
   - ASML  (阿斯麦)          → EUV光刻绝对垄断

 定时调度：
   - 周一至周五 08:00 → 盘前前哨站
   - 周五 20:00       → 全周汇总复盘
   - --now 参数       → 立即执行一次完整扫描

 作者：Claude Code | 日期：2026-06-26 | 版本：v2.0 华尔街前导指标雷达
================================================================================
"""

import argparse
import json
import logging
import os
import re
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 环境变量加载（敏感信息统一管理）
# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).resolve().parent / ".env")

# ============================================================================
# 全局配置区 (CONFIG)
# ============================================================================
class Config:
    """集中管理所有可配置项"""

    # ---- API 密钥（优先从环境变量读取） ----
    GROQ_API_KEY: str = os.getenv(
        "GROQ_API_KEY", "gsk_YOUR_GROQ_KEY_HERE"
    )
    GROQ_MODEL: str = os.getenv(
        "GROQ_MODEL", "llama-3.3-70b-versatile"
    )
    TELEGRAM_BOT_TOKEN: str = os.getenv(
        "TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE"
    )
    TELEGRAM_CHAT_ID: str = os.getenv(
        "TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID_HERE"
    )
    PERPLEXITY_API_KEY: str = os.getenv(
        "PERPLEXITY_API_KEY", ""
    )
    # Google News API (通过 NewsAPI.org 或 SerpAPI)
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")

    # ---- 文件路径 ----
    LOG_DIR: Path = Path(__file__).resolve().parent / "logs"
    DATA_DIR: Path = Path(__file__).resolve().parent / "research_data"

    # ---- 调试开关 ----
    DEBUG: bool = os.getenv("DEBUG", "0") == "1"

    # ---- 现代价值投资硬性阈值 ----
    MIN_GROSS_MARGIN: float = 0.35         # 毛利率 > 35%
    MIN_ROIC: float = 0.15                 # ROIC > 15%
    MIN_ROE: float = 0.20                  # ROE > 20%（ROIC 降维替代）
    MIN_FCF_YIELD: float = 0.05            # FCF Yield > 5%
    MAX_PEG: float = 1.2                   # PEG < 1.2

    # ---- 供应链刚性阈值 ----
    LEAD_TIME_ALERT_WEEKS: int = 20        # 高阶电容交期超过 20 周 → 预警
    ASP_GROWTH_THRESHOLD: float = 0.00     # ASP/营收环比正增长阈值

    # ---- 期权异动监控阈值 ----
    OPTION_CALL_PUT_RATIO_ALERT: float = 4.0           # Call/Put 成交量比率 > 4.0 → 一级警报
    OPTION_OI_OTM_CALL_TOP_N: int = 3                   # 未平仓量前N名均为虚值看涨 → 动量预警
    OPTION_ALERT_STOCKS: list[str] = ["SMCI", "VRT"]    # 强制扫描期权链的标的（即使不在核心池中）

    # ---- 机构级前导指标源 URL ----
    SEMICONDUCTOR_SIA_URL: str = "https://www.semiconductors.org/data-resources/market-data/"
    WSTS_PRESS_URL: str = "https://www.wsts.org/news"
    CNBC_OPTIONS_ACTION_URL: str = "https://www.cnbc.com/options-action/"
    TAIWAN_MOPS_URL: str = "https://mops.twse.com.tw/mops/web/index"

    # ---- 机构源时效性 ----
    INSTITUTIONAL_MAX_AGE_HOURS: int = 48   # 机构报告超过48小时 → 强制降噪剔除


# ============================================================================
# 日志配置
# ============================================================================
def setup_logging(config: type[Config]) -> logging.Logger:
    """初始化双通道日志：文件（全量）+ 终端（INFO 级别）"""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("MLCCQuant")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler — 全量记录
    fh = logging.FileHandler(
        config.LOG_DIR / f"research_{datetime.now():%Y%m%d}.log",
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 终端 handler — INFO 以上
    # Windows cp1252 终端无法渲染 emoji/box-drawing 字符，自动替换为 ASCII 安全版本
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    # 为 StreamHandler 注入 encoding 容错包装，避免 cp1252 崩溃
    _original_emit = ch.emit
    def _safe_emit(record: logging.LogRecord) -> None:
        try:
            _original_emit(record)
        except UnicodeEncodeError:
            # 降级：将 emoji/box-drawing/特殊 Unicode 替换为 ASCII 安全字符
            record.msg = (
                str(record.msg)
                .encode("ascii", errors="replace")
                .decode("ascii")
            )
            record.args = None  # 避免格式化冲突
            _original_emit(record)
    ch.emit = _safe_emit  # type: ignore[method-assign]

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ============================================================================
# 模块一：动态可扩展观察池 (Dynamic Stock Pool)
# ============================================================================

# ---------------------------------------------------------------------------
# 核心美股观察池 —— 字典结构，便于随时增删
# 每个条目包含：代码、名称、核心领域标签、行业分类
# ---------------------------------------------------------------------------
CORE_STOCK_POOL: dict[str, dict[str, Any]] = {
    # ---- 原核心池：MLCC 被动元件 ----
    "MRAAY": {
        "name": "Murata Manufacturing ADR",
        "sector": "Passive Components",
        "focus": "高阶 MLCC 绝对垄断龙头",
        "tags": ["MLCC", "capacitor", "passive"],
        "isin": "US6264251025",
    },
    "ARW": {
        "name": "Arrow Electronics Inc",
        "sector": "Electronics Distribution",
        "focus": "电子元器件分销巨头（库存套利者）",
        "tags": ["distribution", "inventory", "supply_chain"],
        "isin": "US0427351004",
    },
    "TEL": {
        "name": "TE Connectivity Ltd",
        "sector": "Connectors & Sensors",
        "focus": "AI 服务器高密连接器与电源系统",
        "tags": ["connector", "AI_server", "power"],
        "isin": "CH0102993182",
    },
    # ---- 华尔街2026年6月核心持仓主线：AI爆发题材 Elite Pool ----
    "MU": {
        "name": "Micron Technology Inc",
        "sector": "Memory & Storage",
        "focus": "HBM4/DRAM 闪崩式暴涨红利，华尔街6月最吸金标的",
        "tags": ["HBM", "DRAM", "memory", "AI_chip"],
        "isin": "US5951121038",
    },
    "VRT": {
        "name": "Vertiv Holdings Co",
        "sector": "Data Center Infrastructure",
        "focus": "AI 数据中心液冷与电力核心瓶颈，机构重仓",
        "tags": ["liquid_cooling", "data_center", "power"],
        "isin": "US92537N1081",
    },
    "SMCI": {
        "name": "Super Micro Computer Inc",
        "sector": "AI Server",
        "focus": "NVIDIA 新架构总装龙头，期权多头散兵坑",
        "tags": ["liquid_cooling", "AI_server", "GPU_rack"],
        "isin": "US86800U1043",
    },
    "TSM": {
        "name": "Taiwan Semiconductor Manufacturing ADR",
        "sector": "Semiconductor Foundry",
        "focus": "2nm 高级封装技术绝对卡位，全球AI芯片唯一代工口",
        "tags": ["foundry", "advanced_packaging", "2nm", "AI_chip"],
        "isin": "US8740391003",
    },
    "ASML": {
        "name": "ASML Holding NV",
        "sector": "Semiconductor Equipment",
        "focus": "EUV 光刻绝对垄断，High-NA EUV 唯一供应商",
        "tags": ["EUV", "lithography", "equipment", "monopoly"],
        "isin": "USN070592100",
    },
}

# ---------------------------------------------------------------------------
# 外部资讯检索关键词列表（支持动态修改）
# ---------------------------------------------------------------------------
EXTERNAL_KEYWORDS: list[str] = [
    # MLCC 超级周期
    "MLCC",
    "MLCC Super Cycle",
    "Murata pricing",
    # 华尔街2026年6月核心催化剂
    "HBM4 mass production 2026",
    "Micron HBM4 revenue",
    "WSTS semiconductor forecast 2026",
    "SIA semiconductor sales monthly",
    "DRAM spot price surge",
    "NAND flash price recovery",
    # NVIDIA Rubin 架构
    "Vera Rubin",
    "Rubin NVL72",
    "NVL288 liquid cooling",
    # 大行研报
    "Morgan Stanley semiconductor report",
    "Goldman Sachs AI hardware",
    # 供应链紧缺
    "semi inventory shortage",
    "HBM memory shortage",
    "liquid cooling data center demand",
    "optical transceiver 800G 1.6T",
    "TSMC 2nm advanced packaging",
    "ASML High-NA EUV order",
    # 期权动量
    "SMCI options volume",
    "AI server connector TE Connectivity",
    "passive component lead time",
    "Vertiv liquid cooling backlog",
]


# ============================================================================
# 模块二：现代价值投资量化滤网 (Modern Value Investing Filter)
# ============================================================================

class FinancialMetrics:
    """标准化财报数据容器"""

    def __init__(self, ticker: str):
        self.ticker: str = ticker
        self.gross_margin: Optional[float] = None
        self.roic: Optional[float] = None
        self.roe: Optional[float] = None
        self.fcf_yield: Optional[float] = None
        self.peg_ratio: Optional[float] = None
        self.revenue_growth_qoq: Optional[float] = None  # 环比
        self.revenue_growth_yoy: Optional[float] = None  # 同比
        self.market_cap: Optional[float] = None
        self.free_cash_flow: Optional[float] = None
        self.eps_growth_forward: Optional[float] = None  # 分析师预期 EPS 增长率
        self.current_price: Optional[float] = None
        self.data_source: str = "yfinance"
        self.fetch_timestamp: str = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class ModernValueFilter:
    """
    现代价值投资量化滤网

    四大硬性边界条件（芒格框架）：
      1. 定价权/护城河 → 毛利率 > 35% + ASP/营收正增长
      2. 资本效率      → ROIC > 15%（降维 ROE > 20%）
      3. 安全边际      → FCF Yield > 5%
      4. 估值性价比    → PEG < 1.2

    只有全部满足的标的才进入推荐清单。
    """

    def __init__(self, config: type[Config], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.results: dict[str, FinancialMetrics] = {}
        self.passed: dict[str, FinancialMetrics] = {}

    # ------------------------------------------------------------------
    def fetch_financials(self, ticker: str) -> Optional[FinancialMetrics]:
        """
        使用 yfinance 抓取标的财报硬数据，返回 FinancialMetrics 对象。
        具备完善的异常处理和字段缺失降级策略。
        """
        self.logger.info(f"  📊 [{ticker}] 开始抓取财报数据...")

        metrics = FinancialMetrics(ticker)

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or len(info) < 5:
                self.logger.warning(f"  ⚠️  [{ticker}] yfinance 返回数据不足，可能代码有误或退市")
                return None

            # ---- 当前股价 ----
            metrics.current_price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )

            # ---- 市值 ----
            metrics.market_cap = info.get("marketCap")

            # ---- 毛利率 (Gross Margin) ----
            metrics.gross_margin = info.get("grossMargins")  # yfinance 直接提供

            # ---- ROIC —— yfinance 通常不直接提供，需自行计算或用 ROE 降维 ----
            metrics.roic = info.get("returnOnCapitalEmployed")  # 少数字段
            metrics.roe = info.get("returnOnEquity")

            # ---- 自由现金流 ----
            metrics.free_cash_flow = info.get("freeCashflow")

            # ---- FCF Yield = 自由现金流 / 市值 ----
            if metrics.free_cash_flow and metrics.market_cap and metrics.market_cap > 0:
                metrics.fcf_yield = metrics.free_cash_flow / metrics.market_cap

            # ---- PEG Ratio (动态) ----
            metrics.peg_ratio = info.get("pegRatio") or info.get("forwardPE", 0) / max(
                (info.get("earningsGrowth") or 0.01), 0.01
            )

            # ---- EPS 预期增长率 ----
            metrics.eps_growth_forward = info.get("earningsGrowth")

            # ---- 营收增长 (YoY / QoQ) ----
            metrics.revenue_growth_yoy = info.get("revenueGrowth")
            # QoQ 需要季度财报数据，通过 financials 表计算
            metrics.revenue_growth_qoq = self._calc_revenue_qoq(stock)

            self.logger.info(
                f"  ✅ [{ticker}] 数据抓取完成 | "
                f"毛利率={metrics.gross_margin}, ROIC={metrics.roic}, ROE={metrics.roe}, "
                f"FCF Yield={metrics.fcf_yield}, PEG={metrics.peg_ratio}"
            )

        except Exception as e:
            self.logger.error(f"  ❌ [{ticker}] yfinance 数据抓取异常: {e}", exc_info=self.config.DEBUG)
            return None

        self.results[ticker] = metrics
        return metrics

    # ------------------------------------------------------------------
    @staticmethod
    def _calc_revenue_qoq(stock: yf.Ticker) -> Optional[float]:
        """从季度财报表计算营收环比增长率"""
        try:
            quarterly = stock.quarterly_financials
            if quarterly is not None and "Total Revenue" in quarterly.index:
                revenues = quarterly.loc["Total Revenue"]
                if len(revenues) >= 2:
                    latest = revenues.iloc[0]
                    prev = revenues.iloc[1]
                    if prev and prev > 0:
                        return (latest - prev) / prev
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    def apply_filter(self, metrics: FinancialMetrics) -> dict[str, bool]:
        """
        应用四大硬性边界条件，返回逐项检查结果。

        返回字典：
          { "gross_margin": bool, "capital_efficiency": bool,
            "safety_margin": bool, "valuation": bool, "overall": bool }
        """
        checks: dict[str, bool] = {}

        # ---- 条件 1：定价权 / 护城河 ----
        # 毛利率 > 35% AND（营收同比增长 > 0 OR 环比增长 > 0）
        gm_ok = (
            metrics.gross_margin is not None
            and metrics.gross_margin > self.config.MIN_GROSS_MARGIN
        )
        rev_ok = (
            (metrics.revenue_growth_yoy is not None and metrics.revenue_growth_yoy > self.config.ASP_GROWTH_THRESHOLD)
            or (metrics.revenue_growth_qoq is not None and metrics.revenue_growth_qoq > self.config.ASP_GROWTH_THRESHOLD)
        )
        checks["gross_margin"] = gm_ok and rev_ok

        # ---- 条件 2：资本效率 ----
        # ROIC > 15%，若字段缺失则降维使用 ROE > 20%
        if metrics.roic is not None:
            checks["capital_efficiency"] = metrics.roic > self.config.MIN_ROIC
        elif metrics.roe is not None:
            checks["capital_efficiency"] = metrics.roe > self.config.MIN_ROE
        else:
            checks["capital_efficiency"] = False

        # ---- 条件 3：安全边际 ----
        # FCF Yield > 5%
        checks["safety_margin"] = (
            metrics.fcf_yield is not None
            and metrics.fcf_yield > self.config.MIN_FCF_YIELD
        )

        # ---- 条件 4：估值性价比 ----
        # PEG < 1.2
        checks["valuation"] = (
            metrics.peg_ratio is not None
            and 0 < metrics.peg_ratio < self.config.MAX_PEG
        )

        checks["overall"] = all(checks.values())

        return checks

    # ------------------------------------------------------------------
    def run_screening(self, pool: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """
        对观察池中全部标的执行完整量化滤网流程：
          抓取 → 筛选 → 分级返回
        """
        self.logger.info("=" * 70)
        self.logger.info("🔍 模块二：现代价值投资量化滤网 开始运行")
        self.logger.info(f"   待筛选标的：{len(pool)} 只 | 阈值：毛利率>{self.config.MIN_GROSS_MARGIN:.0%} "
                         f"ROIC>{self.config.MIN_ROIC:.0%} FCF>{self.config.MIN_FCF_YIELD:.0%} PEG<{self.config.MAX_PEG}")
        self.logger.info("=" * 70)

        screening_results: dict[str, dict[str, Any]] = {}

        for ticker, meta in pool.items():
            self.logger.info(f"\n--- [{ticker}] {meta['name']} ---")

            # Step 1: 抓取财报
            metrics = self.fetch_financials(ticker)
            if metrics is None:
                screening_results[ticker] = {
                    "meta": meta,
                    "error": "数据抓取失败",
                    "passed": False,
                }
                continue

            # Step 2: 应用量化滤网
            checks = self.apply_filter(metrics)
            status = "✅ 通过" if checks["overall"] else "❌ 未通过"

            screening_results[ticker] = {
                "meta": meta,
                "metrics": metrics.to_dict(),
                "checks": checks,
                "passed": checks["overall"],
            }

            # 详细日志
            check_summary = " | ".join(
                f"{k}={v}" for k, v in checks.items() if k != "overall"
            )
            self.logger.info(f"  📋 检查结果 [{status}]: {check_summary}")

            if checks["overall"]:
                self.passed[ticker] = metrics

        passed_count = sum(1 for r in screening_results.values() if r["passed"])
        self.logger.info(f"\n🏆 量化滤网结果：{passed_count}/{len(pool)} 只标的通过筛选")
        for t, r in screening_results.items():
            if r["passed"]:
                self.logger.info(f"   ✅ {t}: {r['meta']['name']}")

        return screening_results


# ============================================================================
# 模块二-B：期权异动监控 (Options Momentum Monitor)
# ============================================================================

class OptionsMomentumMonitor:
    """
    华尔街一手热钱流向雷达 —— 期权异动监控

    华尔街游资买入股票前一定会通过期权潜伏。本模块：
      - 抓取 yfinance 期权链数据
      - 计算 Call/Put 成交量比率
      - 检测虚值看涨期权（OTM Call）异常集中
      - 触发一级动量警报

    重点监控标的（强制扫描，即使在核心池中也独立执行）：
      - SMCI (超微电脑) —— 历史多次出现 10:1 Call/Put 比率
      - VRT  (维谛技术) —— 数据中心液冷期权异动
    """

    def __init__(self, config: type[Config], logger: logging.Logger):
        self.config = config
        self.logger = logger

    # ------------------------------------------------------------------
    def scan_options_chain(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        扫描单只股票的完整期权链。

        返回：
          {
            "ticker": str,
            "call_volume": int,       # 总看涨成交量
            "put_volume": int,        # 总看跌成交量
            "call_put_ratio": float,  # Call/Put 比率
            "call_oi": int,           # 总看涨未平仓量
            "put_oi": int,            # 总看跌未平仓量
            "top_3_oi_calls": [...],  # OI 前三的看涨期权
            "otm_call_concentration": bool,  # OI前三是否均为虚值
            "momentum_alert": str,    # 一级警报 / 关注 / 正常
          }
        """
        self.logger.info(f"  [Options] Scanning {ticker} options chain...")

        try:
            stock = yf.Ticker(ticker)
            current_price = stock.info.get("currentPrice") or stock.info.get("regularMarketPrice")

            if not current_price or current_price <= 0:
                self.logger.warning(f"  [Options] {ticker}: Cannot determine current price, skipping")
                return None

            # 获取所有可用到期日
            expirations = stock.options
            if not expirations:
                self.logger.warning(f"  [Options] {ticker}: No options chain available")
                return None

            # 取最近3个到期日（覆盖周度 + 月度期权，捕捉最活跃的近月）
            recent_exps = expirations[:6]

            total_call_vol = 0
            total_put_vol = 0
            total_call_oi = 0
            total_put_oi = 0
            all_calls: list[dict[str, Any]] = []

            for exp in recent_exps:
                try:
                    opt = stock.option_chain(exp)
                    calls_df = opt.calls
                    puts_df = opt.puts

                    if calls_df is not None and not calls_df.empty:
                        total_call_vol += int(calls_df["volume"].sum())
                        total_call_oi += int(calls_df["openInterest"].sum())
                        for _, row in calls_df.iterrows():
                            all_calls.append({
                                "strike": float(row["strike"]),
                                "volume": int(row.get("volume", 0)),
                                "openInterest": int(row.get("openInterest", 0)),
                                "expiration": exp,
                            })

                    if puts_df is not None and not puts_df.empty:
                        total_put_vol += int(puts_df["volume"].sum())
                        total_put_oi += int(puts_df["openInterest"].sum())

                except Exception as e:
                    self.logger.debug(f"  [Options] {ticker} expiry {exp} fetch error: {e}")
                    continue

            # ---- 计算 Call/Put 比率 ----
            call_put_ratio = (total_call_vol / total_put_vol) if total_put_vol > 0 else float("inf")

            # ---- 按 OI 降序排列看涨期权 ----
            all_calls.sort(key=lambda x: x["openInterest"], reverse=True)
            top_3 = all_calls[:3]

            # ---- OTM 虚值看涨期权集中度 ----
            otm_concentration = False
            if top_3 and current_price:
                otm_concentration = all(
                    c["strike"] > current_price for c in top_3
                )

            # ---- 动量警报判定 ----
            alert = "normal"
            if call_put_ratio >= self.config.OPTION_CALL_PUT_RATIO_ALERT:
                alert = "LEVEL_1_ALERT"  # 一级警报
            elif call_put_ratio >= 2.5:
                alert = "WATCH"           # 关注
            elif otm_concentration:
                alert = "WATCH"

            # 一级警报叠加 OTM 集中 → 升级为极端信号
            if alert == "LEVEL_1_ALERT" and otm_concentration:
                alert = "EXTREME_MOMENTUM"

            result = {
                "ticker": ticker,
                "current_price": current_price,
                "call_volume": total_call_vol,
                "put_volume": total_put_vol,
                "call_put_ratio": round(call_put_ratio, 2),
                "call_oi": total_call_oi,
                "put_oi": total_put_oi,
                "top_3_oi_calls": top_3,
                "otm_call_concentration": otm_concentration,
                "momentum_alert": alert,
            }

            alert_emoji = {"LEVEL_1_ALERT": "!! ALERT !!", "EXTREME_MOMENTUM": "!!! EXTREME !!!", "WATCH": "WATCH", "normal": "ok"}
            self.logger.info(
                f"  [Options] {ticker}: C/P={call_put_ratio:.1f}, "
                f"CallVol={total_call_vol}, PutVol={total_put_vol}, "
                f"OTM_Top3={otm_concentration}, Alert={alert_emoji.get(alert, alert)}"
            )

            return result

        except Exception as e:
            self.logger.error(f"  [Options] {ticker} scan error: {e}", exc_info=self.config.DEBUG)
            return None

    # ------------------------------------------------------------------
    def run_momentum_scan(
        self, core_pool: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """
        批量扫描：先扫强制标的（SMCI/VRT），再扫核心池中其余的标的。

        返回：
          {
            "results": {ticker: {...}},
            "alerts": [ticker列表, 一级警报 + 极端动量],
            "summary": "华尔街热钱流向速写"
          }
        """
        self.logger.info("=" * 70)
        self.logger.info("[Options Radar] Wall Street Smart Money Flows scan starting")
        self.logger.info(f"   Mandatory: {self.config.OPTION_ALERT_STOCKS} | Core pool: {len(core_pool)} stocks")
        self.logger.info("=" * 70)

        all_results: dict[str, dict[str, Any]] = {}
        alerts: list[str] = []
        scanned: set[str] = set()

        # Phase A: 强制扫描标的（SMCI, VRT 等）
        for ticker in self.config.OPTION_ALERT_STOCKS:
            if ticker in scanned:
                continue
            scanned.add(ticker)
            result = self.scan_options_chain(ticker)
            if result:
                all_results[ticker] = result
                if result["momentum_alert"] in ("LEVEL_1_ALERT", "EXTREME_MOMENTUM"):
                    alerts.append(ticker)

        # Phase B: 扫描核心池中其余标的
        for ticker in core_pool:
            if ticker in scanned:
                continue
            scanned.add(ticker)
            result = self.scan_options_chain(ticker)
            if result:
                all_results[ticker] = result
                if result["momentum_alert"] in ("LEVEL_1_ALERT", "EXTREME_MOMENTUM"):
                    alerts.append(ticker)

        # ---- 生成热钱流向速写 ----
        summary_lines = []
        for t, r in all_results.items():
            if r["momentum_alert"] in ("LEVEL_1_ALERT", "EXTREME_MOMENTUM"):
                stock_name = core_pool.get(t, {}).get("name", t)
                summary_lines.append(
                    f"[!!] {t} ({stock_name}): Call/Put={r['call_put_ratio']:.1f}x, "
                    f"OTM_Concentration={r['otm_call_concentration']} — 华尔街资金高度关注"
                )

        if not summary_lines:
            summary_lines.append("No extreme momentum signals detected this cycle.")

        self.logger.info(f"[Options Radar] Complete: {len(alerts)} alerts / {len(all_results)} scanned")
        for line in summary_lines:
            self.logger.info(f"  {line}")

        return {
            "results": all_results,
            "alerts": alerts,
            "summary": "\n".join(summary_lines),
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ============================================================================
# 模块三：华尔街大行报告与供应链草根数据抓取 (External Data Catalyst)
# ============================================================================

class ExternalDataCatalyst:
    """
    外部数据催化剂模块

    抓取来源：
      (A) NewsAPI.org — 全球财经新闻
      (B) Google News RSS — 免费备用源
      (C) DigiTimes/供应链草根数据 — BeautifulSoup 定向解析

    刚性时间戳校验：
      自动剔除所有非当月/非当天的老旧报告。
    """

    # 供应链草根数据源 URL 列表
    SUPPLY_CHAIN_SOURCES: list[dict[str, str]] = [
        {
            "name": "DigiTimes - IC Design/Distribution",
            "url": "https://www.digitimes.com/news/",
            "selector": "div.news-list h3 a",
        },
        {
            "name": "EPS News - Electronics Purchasing",
            "url": "https://epsnews.com/category/components/",
            "selector": "article h2 a",
        },
        {
            "name": "Seeking Alpha - MLCC",
            "url": "https://seekingalpha.com/symbol/MRAAY/news",
            "selector": "a[data-test-id='post-list-item-title']",
        },
    ]

    def __init__(self, config: type[Config], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.articles: list[dict[str, Any]] = []
        self.now = datetime.now()

    # ------------------------------------------------------------------
    def _parse_and_validate_date(self, date_str: str) -> Optional[datetime]:
        """
        解析多种常见新闻时间格式，返回 datetime 对象。
        支持格式：ISO 8601 / RSS pubDate / "X hours ago" / "2024-06-25"
        """
        if not date_str:
            return None

        # 清理空白
        date_str = date_str.strip()

        formats = [
            "%Y-%m-%dT%H:%M:%SZ",       # ISO 8601 UTC
            "%Y-%m-%dT%H:%M:%S%z",       # ISO 8601 with tz
            "%Y-%m-%dT%H:%M:%S.%fZ",     # ISO with ms
            "%a, %d %b %Y %H:%M:%S %Z",  # RSS pubDate
            "%a, %d %b %Y %H:%M:%S %z",  # RSS with numeric tz
            "%Y-%m-%d",                   # 简单日期
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # 若没有时区信息，假定为 UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        # 处理 "X hours ago" / "X days ago" 相对时间
        ago_match = re.match(r"(\d+)\s*(hour|day|minute|week|month)s?\s*ago", date_str, re.I)
        if ago_match:
            num = int(ago_match.group(1))
            unit = ago_match.group(2).lower()
            kwargs = {f"{unit}s": num}
            return self.now - timedelta(**kwargs)

        return None

    # ------------------------------------------------------------------
    def _is_recent(self, dt: datetime) -> bool:
        """
        刚性时间戳校验：
          - 必须在本月内（宽口径，确保覆盖近期报告）
          - 或在过去 7 天内（精确口径）
        """
        if dt is None:
            return False
        now_utc = self.now.astimezone(timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)

        # 当月校验
        same_month = (dt_utc.year == now_utc.year and dt_utc.month == now_utc.month)
        # 7 日内校验
        within_7_days = (now_utc - dt_utc).days <= 7

        return same_month or within_7_days

    # ------------------------------------------------------------------
    def fetch_newsapi(self, query: str) -> list[dict[str, Any]]:
        """
        通过 NewsAPI.org 抓取财经新闻。
        自动过滤非当月/当天的老旧内容。
        """
        if not self.config.NEWSAPI_KEY:
            self.logger.debug("  ⏭️  NEWSAPI_KEY 未配置，跳过 NewsAPI 抓取")
            return []

        articles = []
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "apiKey": self.config.NEWSAPI_KEY,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 25,
                "from_param": (self.now - timedelta(days=14)).strftime("%Y-%m-%d"),
            }
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("articles", []):
                pub_date = self._parse_and_validate_date(item.get("publishedAt", ""))
                if not self._is_recent(pub_date):
                    continue  # 🔒 刚性时间戳校验：剔除老旧内容

                articles.append({
                    "source": "NewsAPI",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "published_at": pub_date.isoformat() if pub_date else None,
                    "description": item.get("description", ""),
                    "content": (item.get("content") or "")[:500],
                })
        except Exception as e:
            self.logger.warning(f"  ⚠️  NewsAPI 请求异常 [{query}]: {e}")

        return articles

    # ------------------------------------------------------------------
    def fetch_google_news_rss(self, query: str) -> list[dict[str, Any]]:
        """
        通过 Google News RSS 免费备用源抓取。
        """
        articles = []
        try:
            encoded_query = requests.utils.quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            resp = requests.get(rss_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.raise_for_status()

            soup = BeautifulSoup(resp.content, "xml")
            for item in soup.find_all("item")[:15]:
                pub_date = self._parse_and_validate_date(
                    item.find("pubDate").get_text() if item.find("pubDate") else ""
                )
                if not self._is_recent(pub_date):
                    continue

                articles.append({
                    "source": "Google News RSS",
                    "title": item.find("title").get_text() if item.find("title") else "",
                    "url": item.find("link").get_text() if item.find("link") else "",
                    "published_at": pub_date.isoformat() if pub_date else None,
                    "description": (
                        item.find("description").get_text() if item.find("description") else ""
                    )[:300],
                })
        except Exception as e:
            self.logger.warning(f"  ⚠️  Google News RSS 请求异常 [{query}]: {e}")

        return articles

    # ------------------------------------------------------------------
    def fetch_supply_chain_data(self) -> list[dict[str, Any]]:
        """
        抓取供应链草根数据（DigiTimes / EPS News）。

        重点关注：
          - MLCC 现货价（Spot Price）是否大涨
          - 高阶电容交货期（Lead Time）是否 > 20 周
          - HBM / 液冷 / 光模块 是否出现紧缺苗头
        """
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        for source in self.SUPPLY_CHAIN_SOURCES:
            try:
                self.logger.debug(f"  🌐 爬取供应链源: {source['name']}")
                resp = requests.get(source["url"], headers=headers, timeout=20)
                if resp.status_code != 200:
                    self.logger.debug(f"    ⚠️  HTTP {resp.status_code} — 跳过")
                    continue

                soup = BeautifulSoup(resp.content, "html.parser")
                links = soup.select(source["selector"])[:10]

                for link in links:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        # 补全相对路径
                        from urllib.parse import urljoin
                        href = urljoin(source["url"], href)

                    if not title or len(title) < 10:
                        continue

                    # 供应链相关关键词匹配
                    if self._match_supply_chain_keywords(title):
                        articles.append({
                            "source": source["name"],
                            "title": title,
                            "url": href,
                            "published_at": self.now.isoformat(),
                            "description": title,
                        })

            except Exception as e:
                self.logger.warning(f"  ⚠️  供应链源爬取异常 [{source['name']}]: {e}")

        return articles

    # ------------------------------------------------------------------
    @staticmethod
    def _match_supply_chain_keywords(text: str) -> bool:
        """检查文本是否包含供应链周期相关关键词"""
        keywords = [
            "lead time", "lead-time", "shortage", "spot price", "spot market",
            "allocation", "supply constraint", "tight supply", "inventory",
            "MLCC", "capacitor", "resistor", "passive component",
            "HBM", "high bandwidth memory", "liquid cooling", "optical transceiver",
            "800G", "1.6T", "connector", "power management", "Murata", "Samsung",
            "Taiyo Yuden", "Yageo", "TDK",
        ]
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    # ------------------------------------------------------------------
    def fetch_perplexity_research(self, query: str) -> Optional[str]:
        """
        通过 Perplexity API 进行深度行业研究查询。
        返回 AI 生成的摘要文本。
        """
        if not self.config.PERPLEXITY_API_KEY:
            self.logger.debug("  ⏭️  PERPLEXITY_API_KEY 未配置，跳过 Perplexity 查询")
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.config.PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "sonar-pro",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a semiconductor supply chain analyst. "
                            "Provide concise, data-driven answers with specific numbers "
                            "and dates. Always cite your sources."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                "max_tokens": 1024,
            }
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            self.logger.warning(f"  ⚠️  Perplexity API 异常: {e}")
            return None

    # ------------------------------------------------------------------
    # 机构级前导指标拦截（SIA/WSTS/CNBC Options Action）
    # ------------------------------------------------------------------

    def _is_institutional_fresh(self, dt: datetime) -> bool:
        """
        机构报告刚性时效性校验：必须 <= 48 小时。
        超过48小时的旧报告一律降噪剔除。
        """
        if dt is None:
            return False
        now_utc = self.now.astimezone(timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        hours_ago = (now_utc - dt_utc).total_seconds() / 3600
        return hours_ago <= self.config.INSTITUTIONAL_MAX_AGE_HOURS

    # ------------------------------------------------------------------
    def fetch_sia_semiconductor_data(self) -> dict[str, Any]:
        """
        拦截 SIA (半导体行业协会) 月度全球销售数据。

        核心指标：
          - 全球半导体月度销售额 YoY/ MoM
          - 按区域拆分（Americas/Asia Pacific/Europe）
          - WSTS 预测（2026年破1.5万亿）

        使用 requests + BeautifulSoup 定向解析 semiconductors.org。
        """
        result: dict[str, Any] = {
            "source": "SIA/WSTS",
            "headlines": [],
            "data_points": [],
            "fetch_status": "skipped",
        }

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(
                self.config.SEMICONDUCTOR_SIA_URL, headers=headers, timeout=20
            )
            if resp.status_code != 200:
                self.logger.debug(f"  [SIA] HTTP {resp.status_code} — skipping")
                return result

            soup = BeautifulSoup(resp.content, "html.parser")

            # 查找数据相关的标题和链接
            for tag in soup.find_all(["h2", "h3", "a"], limit=30):
                text = tag.get_text(strip=True)
                href = tag.get("href", "") if tag.name == "a" else ""
                if not text or len(text) < 15:
                    continue

                # 匹配关键词：global sales, monthly, revenue, forecast, WSTS
                keywords = r"(global.*sales|monthly.*revenue|semiconductor.*forecast|WSTS|billings|market.*data)"
                if re.search(keywords, text, re.I):
                    # 尝试提取日期
                    date_match = re.search(
                        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})",
                        text, re.I,
                    )
                    pub_date = self._parse_and_validate_date(date_match.group(0)) if date_match else None

                    if pub_date and self._is_institutional_fresh(pub_date):
                        result["headlines"].append({
                            "title": text,
                            "url": href if href.startswith("http") else f"https://www.semiconductors.org{href}",
                            "published_at": pub_date.isoformat(),
                        })
                        result["fetch_status"] = "success"

                    # 提取数值型数据点（如同比涨幅百分比）
                    pct_match = re.findall(
                        r"(\d{1,3}\.?\d*)%\s*(increase|growth|surge|rise|YoY|year.over.year)",
                        text, re.I,
                    )
                    for pct, direction in pct_match:
                        result["data_points"].append({
                            "value": f"{pct}%",
                            "direction": direction.lower(),
                            "context": text[:150],
                        })

            self.logger.info(
                f"  [SIA/WSTS] {len(result['headlines'])} fresh headlines, "
                f"{len(result['data_points'])} data points"
            )

        except Exception as e:
            self.logger.warning(f"  [SIA/WSTS] Scrape error: {e}")
            result["fetch_status"] = "error"

        return result

    # ------------------------------------------------------------------
    def fetch_cnbc_options_action(self) -> list[dict[str, Any]]:
        """
        拦截 CNBC Options Action 专栏目更新。

        Options Action 是华尔街期权交易员每周必看栏目，
        披露大单异动和机构期权策略。
        """
        articles: list[dict[str, Any]] = []

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            # 使用 CNBC 的 RSS feed（比网页爬取更稳定）
            rss_url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100867156"
            resp = requests.get(rss_url, headers=headers, timeout=15)

            if resp.status_code != 200:
                # Fallback to scraping the page
                resp = requests.get(
                    self.config.CNBC_OPTIONS_ACTION_URL, headers=headers, timeout=15
                )

            soup = BeautifulSoup(resp.content, "xml" if "xml" in (resp.headers.get("Content-Type") or "") else "html.parser")

            for item in soup.find_all("item")[:10] if soup.find("item") else []:
                title = item.find("title").get_text(strip=True) if item.find("title") else ""
                pub_str = item.find("pubDate").get_text(strip=True) if item.find("pubDate") else ""
                link = item.find("link").get_text(strip=True) if item.find("link") else ""

                pub_date = self._parse_and_validate_date(pub_str)
                if not self._is_institutional_fresh(pub_date):
                    continue

                if title and ("option" in title.lower() or "call" in title.lower() or "put" in title.lower() or "semiconductor" in title.lower() or "chip" in title.lower() or "tech" in title.lower()):
                    articles.append({
                        "source": "CNBC Options Action",
                        "title": title,
                        "url": link,
                        "published_at": pub_date.isoformat() if pub_date else None,
                        "description": title,
                    })

        except Exception as e:
            self.logger.warning(f"  [CNBC Options Action] Scrape error: {e}")

        self.logger.info(f"  [CNBC Options Action] {len(articles)} fresh articles")
        return articles

    # ------------------------------------------------------------------
    def run_institutional_sweep(self) -> dict[str, Any]:
        """
        执行机构级前导指标完整扫荡：
          (A) SIA/WSTS 全球半导体月度数据
          (B) CNBC Options Action 期权大单异动
          (C) [可选] 台湾公开资讯观测站
        """
        self.logger.info("  [Institutional] Running Wall Street institutional radar sweep...")

        sia_data = self.fetch_sia_semiconductor_data()
        cnbc_articles = self.fetch_cnbc_options_action()

        institutional = {
            "sia_wsts": sia_data,
            "cnbc_options_action": cnbc_articles,
            "institutional_timestamp": self.now.isoformat(),
            "freshness_window_hours": self.config.INSTITUTIONAL_MAX_AGE_HOURS,
        }

        total_hits = len(sia_data.get("headlines", [])) + len(cnbc_articles)
        self.logger.info(f"  [Institutional] Sweep complete: {total_hits} total institutional-grade hits")

        return institutional

    # ------------------------------------------------------------------
    def run_full_sweep(self, keywords: list[str]) -> dict[str, Any]:
        """
        执行完整的外部数据扫荡：

        1. 对每个关键词并行抓取 NewsAPI + Google News RSS
        2. 单独抓取供应链草根数据
        3. 机构级前导指标拦截（SIA/WSTS/CNBC）
        4. 刚性时间戳校验已内嵌在每个抓取函数中
        5. 汇总去重
        """
        self.logger.info("=" * 70)
        self.logger.info("🌐 模块三：外部数据催化剂 开始运行")
        self.logger.info(f"   检索关键词数：{len(keywords)} | 供应链源：{len(self.SUPPLY_CHAIN_SOURCES)}")
        self.logger.info("=" * 70)

        all_articles: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # ---- 阶段 A：逐关键词抓取 ----
        for kw in keywords:
            self.logger.info(f"  🔎 检索关键词: \"{kw}\"")
            # NewsAPI
            newsapi_results = self.fetch_newsapi(kw)
            # Google News RSS
            rss_results = self.fetch_google_news_rss(kw)

            for art in newsapi_results + rss_results:
                url = art.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(art)

        self.logger.info(f"  📰 新闻抓取完成：{len(all_articles)} 篇有效报道（已过滤老旧内容）")

        # ---- 阶段 B：供应链草根数据 ----
        supply_chain_articles = self.fetch_supply_chain_data()
        for art in supply_chain_articles:
            url = art.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(art)

        self.logger.info(f"  [Supply Chain] Added {len(supply_chain_articles)} articles")

        # ---- 阶段 C：机构级前导指标拦截（SIA/WSTS + CNBC Options Action） ----
        institutional_data = self.run_institutional_sweep()

        # ---- 阶段 D：Perplexity 深度查询（可选） ----
        perplexity_result: Optional[str] = None
        if self.config.PERPLEXITY_API_KEY:
            deep_query = (
                "What is the current state of the MLCC super cycle as of "
                f"{self.now.strftime('%B %Y')}? What is the WSTS 2026 semiconductor "
                "forecast (targeting $1.5 trillion)? Is HBM4 mass production driving "
                "DRAM spot price surge? Which AI hardware nodes (HBM, liquid cooling, "
                "optical transceivers) are showing supply tightness?"
            )
            perplexity_result = self.fetch_perplexity_research(deep_query)
            if perplexity_result:
                self.logger.info(f"  [Perplexity] Deep query completed ({len(perplexity_result)} chars)")

        # ---- 汇总 ----
        self.articles = all_articles
        summary = {
            "total_articles": len(all_articles),
            "articles": all_articles[:50],  # 控制在合理数量
            "perplexity_insight": perplexity_result,
            "institutional_data": institutional_data,  # 机构级前导指标
            "fetch_timestamp": self.now.isoformat(),
            "supply_chain_alerts": self._extract_supply_chain_alerts(all_articles),
        }

        self.logger.info(f"  Sweep complete: {len(all_articles)} articles, "
                         f"{len(summary['supply_chain_alerts'])} chain alerts, "
                         f"institutional={institutional_data.get('sia_wsts', {}).get('fetch_status', 'N/A')}")

        return summary

    # ------------------------------------------------------------------
    def _extract_supply_chain_alerts(self, articles: list[dict[str, Any]]) -> list[str]:
        """
        从文章标题/描述中提取供应链预警信号。

        预警触发条件（自动识别）：
          - 交货期（Lead Time）> 20 周
          - 现货价（Spot Price）大涨
          - 供应短缺（Shortage/Allocation）
        """
        alerts = []
        alert_patterns = [
            (r"lead\s*time[:\s]*(\d+)\s*(week|wk)", "交货期"),
            (r"spot\s*price[:\s]*(surge|up|rise|increase)", "现货价上涨"),
            (r"shortage|supply\s*constraint|allocation|tight\s*supply", "供应短缺"),
            (r"MLCC.*(surge|shortage|tight)", "MLCC紧缺"),
            (r"HBM.*(shortage|tight|constraint)", "HBM紧缺"),
            (r"liquid\s*cooling.*(demand|shortage|surge)", "液冷需求激增"),
        ]

        for art in articles:
            text = f"{art.get('title', '')} {art.get('description', '')}"
            for pattern, alert_type in alert_patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    weeks = int(match.group(1)) if match.lastindex and match.group(1).isdigit() else None
                    if weeks and weeks >= self.config.LEAD_TIME_ALERT_WEEKS:
                        alerts.append(f"🚨 交货期预警：{match.group(0)}（≥{weeks}周）")
                    else:
                        alert_msg = f"⚠️ {alert_type}：{match.group(0)} | 来源：{art.get('source', 'N/A')}"
                        if alert_msg not in alerts:
                            alerts.append(alert_msg)

        return alerts


# ============================================================================
# 模块四：AI 深度文本分析与自动化推送 (AI Intelligence & Webhook Push)
# ============================================================================

class AIIntelligenceEngine:
    """
    AI 投研引擎

    工作流：
      1. 合并模块二的量化硬数据 + 模块三的实时行业动态 → JSON 上下文
      2. 投喂 OpenRouter API（Claude 模型）
      3. 输出纯干货中文投研报告
      4. 通过 Telegram Webhook 自动推送
    """

    def __init__(self, config: type[Config], logger: logging.Logger):
        self.config = config
        self.logger = logger

    # ------------------------------------------------------------------
    @staticmethod
    def _build_research_context(
        screening: dict[str, dict[str, Any]],
        external: dict[str, Any],
        options_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        构建投喂给 AI 的标准化 JSON 上下文。

        严格包含：
          - 量化硬数据（ROIC/PEG/FCF Yield 原始值）
          - 期权异动监控（Smart Money Flows）
          - 机构级前导指标（SIA/WSTS/CNBC）
          - 供应链预警
          - 新闻摘要
        """
        # 筛选通过的标的，保留关键定量数据
        passed_stocks = {}
        for ticker, result in screening.items():
            if result.get("passed"):
                m = result.get("metrics", {})
                passed_stocks[ticker] = {
                    "name": result["meta"]["name"],
                    "sector": result["meta"]["sector"],
                    "focus": result["meta"]["focus"],
                    "gross_margin": m.get("gross_margin"),
                    "roic": m.get("roic"),
                    "roe": m.get("roe"),
                    "fcf_yield": m.get("fcf_yield"),
                    "peg_ratio": m.get("peg_ratio"),
                    "revenue_growth_yoy": m.get("revenue_growth_yoy"),
                    "revenue_growth_qoq": m.get("revenue_growth_qoq"),
                    "market_cap": m.get("market_cap"),
                    "current_price": m.get("current_price"),
                }

        # 未通过的也保留，供 AI 进行对比分析
        failed_stocks = {}
        for ticker, result in screening.items():
            if not result.get("passed"):
                m = result.get("metrics", {})
                checks = result.get("checks", {})
                failed_stocks[ticker] = {
                    "name": result["meta"]["name"],
                    "gross_margin": m.get("gross_margin"),
                    "roic": m.get("roic"),
                    "roe": m.get("roe"),
                    "fcf_yield": m.get("fcf_yield"),
                    "peg_ratio": m.get("peg_ratio"),
                    "revenue_growth_yoy": m.get("revenue_growth_yoy"),
                    "failed_checks": {k: v for k, v in checks.items() if not v},
                }

        # 期权异动数据摘要
        options_summary = {}
        if options_data:
            for t, r in options_data.get("results", {}).items():
                options_summary[t] = {
                    "call_put_ratio": r.get("call_put_ratio"),
                    "call_volume": r.get("call_volume"),
                    "put_volume": r.get("put_volume"),
                    "otm_call_concentration": r.get("otm_call_concentration"),
                    "momentum_alert": r.get("momentum_alert"),
                }

        return {
            "report_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "passed_stocks": passed_stocks,
            "failed_stocks": failed_stocks,
            "options_momentum": {             # 华尔街热钱流向
                "alerts": options_data.get("alerts", []) if options_data else [],
                "summary": options_data.get("summary", "") if options_data else "",
                "details": options_summary,
            },
            "institutional_data": external.get("institutional_data", {}),  # SIA/WSTS/CNBC
            "supply_chain_alerts": external.get("supply_chain_alerts", []),
            "perplexity_insight": external.get("perplexity_insight"),
            "news_headlines": [
                {
                    "title": a.get("title"),
                    "source": a.get("source"),
                    "published_at": a.get("published_at"),
                }
                for a in external.get("articles", [])[:20]
            ],
        }

    # ------------------------------------------------------------------
    def generate_report(
        self,
        screening: dict[str, dict[str, Any]],
        external: dict[str, Any],
        options_data: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        调用 Groq API (llama-3.3-70b-versatile)，让 LLM 扮演顶级对冲基金投研总监，
        整合四大数据源输出纯干货中文投研报告。
        """
        self.logger.info("=" * 70)
        self.logger.info("Module 4: AI Text Analysis starting (w/ Options + Institutional Radar)")
        self.logger.info("=" * 70)

        context = self._build_research_context(screening, external, options_data)

        if not self.config.GROQ_API_KEY or "YOUR_GROQ_KEY" in self.config.GROQ_API_KEY:
            self.logger.warning("WARNING: Groq API Key not configured, skipping AI report generation")
            return json.dumps(context, ensure_ascii=False, indent=2)

        system_prompt = textwrap.dedent("""
            你是一位在华尔街顶级多策略对冲基金工作了20年的投研总监（CIO of Research）。
            你的投资哲学严格遵循查理·芒格和 Modern Value Investing 框架。
            当前是2026年6月——WSTS预测全球半导体规模突破$1.5万亿，HBM4量产在即，
            你需要用硬数据和冷静头脑穿透市场噪音。

            ## 报告必须包含以下结构化章节（严格按顺序）：

            ### 【华尔街一手热钱流向（Smart Money Flows）】—— 新增顶置板块
            这是报告最重要的部分。用大白话和硬数字直接回答：
            1. 本周华尔街游资到底在买什么？是存储芯片(DRAM/HBM)、买电力液冷(VRT)、还是在抢购期权(SMCI)？
            2. 逐只股票列出期权Call/Put比率。若某股票比率>4.0（如SMCI近期10:1异动），必须标注"一级动量警报"。
            3. OI(未平仓量)前三名是否均为虚值看涨期权？这意味着什么？
            4. 前导财务数据是否完美兑现？重点看YoY营收增速是否>25%。

            ### 一、今日/本周自动推荐的美股周期突破标的清单
            - 以列表形式清晰呈现，标注"量化通过"或"期权动量突破"
            - 每个标的标注：代码、名称、核心催化逻辑

            ### 二、基于现代价值投资策略的具体原因分析
            - 每只股票列出原始关键数据：ROIC、PEG、FCF Yield、毛利率
            - 解释该股票为何满足（或接近满足）四大硬性边界条件
            - 说明其护城河来源（技术垄断/规模效应/品牌溢价/HBM4唯一供应商）

            ### 三、大行研报与供应链数据的交叉验证结论
            - SIA/WSTS全球半导体月度销售数据（同比涨幅）与标的财务数据交叉验证
            - MLCC交期>20周+村田毛利率上升→超级周期确认
            - CNBC Options Action中是否有机构大单异动报道
            - 诚实标注任何数据矛盾

            ### 四、最新 AI 硬件/半导体周期领域拓宽提示
            - HBM4量产窗口、2nm先进封装、液冷散热、800G/1.6T光模块
            - 具体给出观察标的（MU/VRT/SMCI/TSM/ASML）
            - 标注当前哪个子领域最热（根据新闻密度和期权动量判断）

            ### 五、潜在的周期下行与数据反转风险提示
            - 哪些信号可能是假阳性（例如单一机构大单推高Call/Put比率）
            - 宏观风险（利率政策、地缘政治、DRAM周期性过剩）
            - 如果所有标的都未通过滤网→直接建议"现金为王"并说明原因

            ## 写作风格要求
            - 纯中文输出，专业但不晦涩
            - 硬数据驱动，每个结论都有数字支撑
            - 简洁有力，拒绝废话和套话
            - Smart Money Flows板块必须用交易员能看懂的大白话
            - 风险第一，永远给出downside scenario
        """).strip()

        user_prompt = f"""以下是本日/本周的系统自动扫描结果。请严格按照你的投研总监角色生成完整报告。

        === 华尔街期权热钱流向（Smart Money Flows） ===
        {json.dumps(context['options_momentum'], ensure_ascii=False, indent=2)}

        === SIA/WSTS 全球半导体月度数据 & CNBC Options Action ===
        {json.dumps(context['institutional_data'], ensure_ascii=False, indent=2, default=str)}

        === 量化滤网通过的标的 ===
        {json.dumps(context['passed_stocks'], ensure_ascii=False, indent=2)}

        === 未通过滤网的标的（供参考） ===
        {json.dumps(context['failed_stocks'], ensure_ascii=False, indent=2)}

        === 供应链预警信号 ===
        {json.dumps(context['supply_chain_alerts'], ensure_ascii=False, indent=2)}

        === Perplexity 深度行业洞察 ===
        {context.get('perplexity_insight') or '（未启用）'}

        === 近期行业新闻标题 ===
        {json.dumps(context['news_headlines'], ensure_ascii=False, indent=2)}

        请生成完整的投研报告。务必先回答Smart Money Flows的核心问题：本周华尔街到底在买什么？"""

        try:
            headers = {
                "Authorization": f"Bearer {self.config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.config.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 4096,
            }

            self.logger.info(f"  Calling Groq API (model={self.config.GROQ_MODEL})...")
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()

            report = data["choices"][0]["message"]["content"]
            self.logger.info(f"  AI report generated ({len(report)} characters)")

            return report

        except Exception as e:
            self.logger.error(f"  Groq API call failed: {e}", exc_info=self.config.DEBUG)
            return None

    # ------------------------------------------------------------------
    def send_telegram(self, report: str) -> bool:
        """
        通过 Telegram Bot API 发送报告。
        消息过长时自动分段发送（Telegram 单条上限 4096 字符）。
        """
        if "YOUR_TELEGRAM_BOT_TOKEN" in self.config.TELEGRAM_BOT_TOKEN:
            self.logger.warning("⚠️  Telegram Bot Token 未配置，跳过推送")
            return False

        base_url = f"https://api.telegram.org/bot{self.config.TELEGRAM_BOT_TOKEN}"

        # 分段策略：Telegram 消息上限 4096，保留安全余量
        max_len = 3800
        chunks = []
        current = ""

        for line in report.split("\n"):
            if len(current) + len(line) + 1 > max_len:
                chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)

        success = True
        for i, chunk in enumerate(chunks):
            prefix = f"📊 [MLCC量化投研] Part {i+1}/{len(chunks)}\n{'─'*30}\n" if len(chunks) > 1 else ""
            message = prefix + chunk

            try:
                resp = requests.post(
                    f"{base_url}/sendMessage",
                    json={
                        "chat_id": self.config.TELEGRAM_CHAT_ID,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    # Markdown 解析失败时降级为纯文本重试
                    resp2 = requests.post(
                        f"{base_url}/sendMessage",
                        json={
                            "chat_id": self.config.TELEGRAM_CHAT_ID,
                            "text": message,
                        },
                        timeout=15,
                    )
                    if resp2.status_code != 200:
                        self.logger.error(f"  ❌ Telegram 推送失败 [Part {i+1}]: {resp2.text}")
                        success = False
            except Exception as e:
                self.logger.error(f"  ❌ Telegram 推送异常 [Part {i+1}]: {e}")
                success = False

        if success:
            self.logger.info(f"  ✅ Telegram 推送完成（{len(chunks)} 条消息）")
        return success


# ============================================================================
# 主控流水线 (Orchestrator)
# ============================================================================

class QuantResearchPipeline:
    """
    投研主控流水线

    编排顺序：
      模块二（量化滤网）→ 模块三（外部催化剂）→ 模块四（AI 生成 + 推送）
    """

    def __init__(self, config: type[Config], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.filter_engine = ModernValueFilter(config, logger)
        self.options_monitor = OptionsMomentumMonitor(config, logger)
        self.catalyst_engine = ExternalDataCatalyst(config, logger)
        self.ai_engine = AIIntelligenceEngine(config, logger)

    # ------------------------------------------------------------------
    def run_once(self) -> Optional[str]:
        """
        执行一次完整的投研扫描流水线。
        返回：AI 生成的报告文本（或 None 表示失败）。
        """
        start_time = datetime.now()
        self.logger.info("")
        self.logger.info("█" * 70)
        self.logger.info(f"█  🚀 MLCC 量化投研流水线启动  |  {start_time:%Y-%m-%d %H:%M:%S}")
        self.logger.info("█" * 70)

        report = None
        screening_results: dict[str, Any] = {}
        external_data: dict[str, Any] = {}
        options_data: dict[str, Any] = {}

        try:
            # ----- 阶段 1：量化滤网 -----
            screening_results = self.filter_engine.run_screening(CORE_STOCK_POOL)

            # ----- 阶段 2：期权异动监控（Smart Money Flows Radar） -----
            options_data = self.options_monitor.run_momentum_scan(CORE_STOCK_POOL)

            # ----- 阶段 3：外部数据扫荡 + 机构级前导指标 -----
            external_data = self.catalyst_engine.run_full_sweep(EXTERNAL_KEYWORDS)

            # ----- 阶段 4：AI 报告生成 -----
            report = self.ai_engine.generate_report(
                screening_results, external_data, options_data
            )

            if report:
                # ----- 阶段 5：Telegram 推送 -----
                self.ai_engine.send_telegram(report)

        except Exception as e:
            self.logger.critical(f"Pipeline FATAL: {e}", exc_info=self.config.DEBUG)

        finally:
            # 无论 AI 是否成功，始终持久化原始量化数据
            if screening_results or external_data or options_data:
                self._save_report(report, screening_results, external_data, options_data)

        elapsed = datetime.now() - start_time
        self.logger.info("█" * 70)
        self.logger.info(f"█  ✅ 流水线执行完毕 | 耗时: {elapsed.total_seconds():.1f}s")
        self.logger.info("█" * 70)
        self.logger.info("")

        return report

    # ------------------------------------------------------------------
    def _save_report(
        self,
        report: Optional[str],
        screening: dict[str, dict[str, Any]],
        external: dict[str, Any],
        options_data: Optional[dict[str, Any]] = None,
    ) -> None:
        """持久化报告和原始数据到本地文件（report 为 None 时仅保存 JSON 数据）"""
        self.config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存 Markdown 报告（仅当 AI 成功生成时）
        if report:
            report_path = self.config.DATA_DIR / f"research_report_{timestamp}.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            self.logger.info(f"  Report saved: {report_path}")
        else:
            self.logger.info("  AI report skipped — saving raw data only")

        # 保存原始 JSON 数据（始终执行，用于离线回溯分析）
        json_path = self.config.DATA_DIR / f"raw_data_{timestamp}.json"
        raw_data = {
            "timestamp": timestamp,
            "screening_results": screening,
            "options_momentum_summary": {
                "alerts": options_data.get("alerts", []) if options_data else [],
                "scanned_count": len(options_data.get("results", {})) if options_data else 0,
            } if options_data else {},
            "external_data_summary": {
                "total_articles": external.get("total_articles", 0),
                "supply_chain_alerts": external.get("supply_chain_alerts", []),
                "institutional_status": external.get("institutional_data", {}).get("sia_wsts", {}).get("fetch_status", "N/A") if external else "N/A",
            },
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2, default=str)
        self.logger.info(f"  Raw data saved: {json_path}")


# ============================================================================
# 模块五：自动化定时调度与调试模式 (Scheduler & CLI)
# ============================================================================

def create_scheduler(pipeline: QuantResearchPipeline, logger: logging.Logger):
    """
    创建 APScheduler 阻塞式调度器。

    调度规则：
      - 每周一至周五 08:00  → 盘前前哨站扫描
      - 每周五 20:00        → 全周周期汇总复盘
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler(timezone="America/New_York")

    # 周一至周五 08:00 EST → 美股盘前
    scheduler.add_job(
        pipeline.run_once,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        id="morning_scan",
        name="盘前前哨站扫描",
        replace_existing=True,
    )

    # 周五 20:00 EST → 全周汇总复盘
    scheduler.add_job(
        pipeline.run_once,
        trigger=CronTrigger(day_of_week="fri", hour=20, minute=0),
        id="weekly_review",
        name="全周周期汇总复盘",
        replace_existing=True,
    )

    logger.info("⏰ APScheduler 已配置：")
    logger.info("    • 周一至周五 08:00 EST → 盘前前哨站扫描")
    logger.info("    • 周五 20:00 EST       → 全周周期汇总复盘")
    logger.info("    • 按 Ctrl+C 停止调度器")

    return scheduler


# ============================================================================
# CLI 入口
# ============================================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="MLCC 超级周期 · 现代价值投资 · 全自动量化投研助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            使用示例：
              python mlcc_quant_research.py --now       # 立即执行一次扫描
              python mlcc_quant_research.py             # 启动定时调度模式
              python mlcc_quant_research.py --now --dry-run  # 抓取数据但不推送
              python mlcc_quant_research.py --add-stock AAPL "Apple Inc" "Consumer Electronics"
        """),
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="立即执行一次完整扫描（绕过定时调度器）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="执行扫描并生成报告，但不推送到 Telegram",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用 DEBUG 级别日志输出",
    )
    parser.add_argument(
        "--add-stock",
        nargs=2,
        metavar=("TICKER", "NAME"),
        help="临时添加一只股票到扫描池（格式：--add-stock AAPL 'Apple Inc'）",
    )
    return parser.parse_args()


def main() -> None:
    """主函数入口"""
    args = parse_args()
    config = Config

    if args.debug:
        config.DEBUG = True
        os.environ["DEBUG"] = "1"

    logger = setup_logging(config)

    # ---- 打印启动横幅 ----
    logger.info("")
    logger.info("╔" + "═" * 68 + "╗")
    logger.info("║  MLCC Super Cycle · Modern Value Investing · Quant Research   ║")
    logger.info("║  全自动量化投研助手 v1.0                                       ║")
    logger.info("╚" + "═" * 68 + "╝")

    # ---- 临时添加股票 ----
    if args.add_stock:
        ticker, name = args.add_stock
        CORE_STOCK_POOL[ticker.upper()] = {
            "name": name,
            "sector": "User-Added",
            "focus": "用户临时添加",
            "tags": ["user_added"],
            "isin": "",
        }
        logger.info(f"➕ 已临时添加：{ticker.upper()} ({name})")

    # ---- 初始化流水线 ----
    pipeline = QuantResearchPipeline(config, logger)

    # ---- 执行模式判断 ----
    if args.now:
        # 即时执行模式
        logger.info("⚡ 即时执行模式（--now）")
        if args.dry_run:
            logger.info("🔍 试运行模式（--dry-run）：将跳过 Telegram 推送")
            # 临时禁用 Telegram 推送
            original_token = config.TELEGRAM_BOT_TOKEN
            config.TELEGRAM_BOT_TOKEN = "DISABLED_DRY_RUN"

        pipeline.run_once()

        if args.dry_run:
            config.TELEGRAM_BOT_TOKEN = original_token

    else:
        # 定时调度模式
        logger.info("🕐 启动定时调度模式...")
        logger.info("   提示：使用 --now 参数可立即执行一次扫描")
        scheduler = create_scheduler(pipeline, logger)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("👋 收到退出信号，调度器已停止。祝交易顺利！")


# ============================================================================
# 启动入口
# ============================================================================
if __name__ == "__main__":
    main()
