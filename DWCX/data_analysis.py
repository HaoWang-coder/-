from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import warnings

import pandas as pd


QUOTE_COLUMNS = [
    "订单号", "交强险投保单号", "交强险起保日期", "商业险投保单号", "商业险起保日期", "业务方案号",
    "车牌号", "被保险人", "录入时间", "出单员名称", "业务员名称", "订单状态代码", "核保信息",
    "订单来源", "订单来源-中文", "代理人", "车架号", "发动机号",
]
POLICY_COLUMNS = [
    "保单号", "投保单号", "订单号", "类型", "起保日期", "终保日期", "保险费", "车牌号", "被保险人",
    "出单员", "业务员", "状态", "录单日期", "非车汇总保费", "车船税汇总金额",
]
RISK_KEYWORDS = ["下发修改", "异地", "违法", "影像与录入信息不一致", "高风险", "脱保", "关系证明", "审核通过"]
MISSING_MARKERS = {"", "nan", "none", "null", "nat", "1"}


@dataclass
class TableData:
    columns: list[str]
    rows: list[list[Any]]


@dataclass
class AnalysisReport:
    title: str
    kpis: list[tuple[str, str, str]]
    tables: dict[str, TableData]
    charts: dict[str, list[tuple[str, float]]]
    insights: list[str]


def _clean_text(series: pd.Series, missing_label: str = "未填写") -> pd.Series:
    text = series.astype("string").str.strip()
    return text.mask(text.str.lower().isin(MISSING_MARKERS), pd.NA).fillna(missing_label)


def _find_header(path: Path, expected: list[str]) -> int:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style.*")
        preview = pd.read_excel(path, header=None, nrows=10)
    expected_set = set(expected)
    best_row, best_score = 0, -1
    for index, row in preview.iterrows():
        values = {str(value).strip() for value in row if pd.notna(value)}
        score = len(values & expected_set)
        if score > best_score:
            best_row, best_score = int(index), score
    if best_score < max(5, int(len(expected) * 0.6)):
        raise ValueError(f"未识别到兼容表头：{path.name}。请上传与样例表头相同的 Excel 文件。")
    return best_row


def load_excel(path_value: str | Path, kind: str) -> pd.DataFrame:
    path = Path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    expected = QUOTE_COLUMNS if kind == "quote" else POLICY_COLUMNS
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style.*")
        frame = pd.read_excel(path, header=_find_header(path, expected))
    frame.columns = [str(column).strip() for column in frame.columns]
    missing = [column for column in expected if column not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} 缺少必要字段：{', '.join(missing)}")
    frame = frame[expected].copy()
    frame.attrs["source_name"] = path.name
    if kind == "quote":
        for column in ["录入时间", "交强险起保日期", "商业险起保日期"]:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    else:
        for column in ["起保日期", "终保日期", "录单日期"]:
            source = frame[column].astype("string").str.replace("24:00:00", "00:00:00", regex=False)
            frame[column] = pd.to_datetime(source, errors="coerce")
        for column in ["保险费", "非车汇总保费", "车船税汇总金额"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _money(value: float) -> str:
    return f"¥{value:,.2f}"


def _count_table(series: pd.Series, label: str, total: int, limit: int = 20) -> TableData:
    counts = series.value_counts(dropna=False).head(limit)
    return TableData([label, "数量", "占比"], [[str(key), int(value), _percent(value / total if total else 0)] for key, value in counts.items()])


def _count_chart(table: TableData) -> list[tuple[str, float]]:
    return [(str(row[0]), float(row[1])) for row in table.rows[:10]]


def analyze_quote(frame: pd.DataFrame) -> AnalysisReport:
    total = len(frame)
    statuses = _clean_text(frame["订单状态代码"])
    agents = _clean_text(frame["代理人"])
    plans = _clean_text(frame["业务方案号"])
    staff = _clean_text(frame["业务员名称"])
    effective_mask = statuses.eq("生效")
    effective = int(effective_mask.sum())
    active = int(statuses.isin(["暂存", "未提交", "下发修改", "待支付"]).sum())
    start, end = frame["录入时间"].min(), frame["录入时间"].max()

    status_table = _count_table(statuses, "订单状态", total)
    monthly = frame.assign(月份=frame["录入时间"].dt.strftime("%Y-%m")).groupby("月份", dropna=False).size()
    monthly_table = TableData(["月份", "订单数"], [[str(key), int(value)] for key, value in monthly.items()])

    agent_data = pd.DataFrame({"代理人": agents, "生效": effective_mask}).groupby("代理人").agg(订单数=("生效", "size"), 生效数=("生效", "sum")).sort_values("订单数", ascending=False)
    agent_table = TableData(["代理人/渠道", "订单数", "生效数", "生效率"], [[idx, int(row.订单数), int(row.生效数), _percent(row.生效数 / row.订单数)] for idx, row in agent_data.iterrows()])

    plan_data = pd.DataFrame({"方案": plans, "生效": effective_mask}).groupby("方案").agg(订单数=("生效", "size"), 生效数=("生效", "sum")).sort_values("订单数", ascending=False)
    plan_table = TableData(["业务方案", "订单数", "生效数", "生效率"], [[idx, int(row.订单数), int(row.生效数), _percent(row.生效数 / row.订单数)] for idx, row in plan_data.iterrows()])
    staff_table = _count_table(staff, "业务员", total)

    risk_text = frame["核保信息"].fillna("").astype(str)
    risk_rows = [[word, int(risk_text.str.contains(word, regex=False).sum())] for word in RISK_KEYWORDS]
    risk_rows.sort(key=lambda row: row[1], reverse=True)
    risk_table = TableData(["核保关键词", "命中订单数"], risk_rows)

    plate_text = _clean_text(frame["车牌号"])
    region = plate_text.str[:1].where(plate_text.ne("未填写") & plate_text.str[:1].str.match(r"[\u4e00-\u9fff]", na=False), "其他/未填写")
    region_table = _count_table(region, "车牌地区", total)

    delta = (frame["商业险起保日期"] - frame["交强险起保日期"]).dt.total_seconds().div(86400)
    buckets = pd.cut(delta, [-float("inf"), -1, 0, 1, 7, float("inf")], labels=["商业险更早", "同日", "相差1天", "相差2-7天", "相差超过7天"])
    delta_table = _count_table(buckets.astype("string").fillna("日期缺失"), "起保日期差异", total)

    missing_agents = int(agents.eq("未填写").sum())
    insights = [
        f"样本覆盖 {start:%Y-%m-%d} 至 {end:%Y-%m-%d}，共 {total:,} 个报价订单。" if pd.notna(start) and pd.notna(end) else f"共 {total:,} 个报价订单。",
        f"当前生效 {effective:,} 单，样本内状态生效率 {_percent(effective / total if total else 0)}；待跟进订单 {active:,} 单。",
        f"最大渠道为“{agent_data.index[0]}”，贡献 {int(agent_data.iloc[0].订单数):,} 个报价。" if not agent_data.empty else "暂无渠道数据。",
        f"代理人未填写 {missing_agents:,} 条，建议补齐以提高渠道分析准确度。" if missing_agents else "代理人字段完整。",
    ]
    tables = {"状态漏斗": status_table, "月度趋势": monthly_table, "渠道分析": agent_table, "业务方案": plan_table, "业务员工作量": staff_table, "核保风险": risk_table, "车牌地域": region_table, "起保日期差异": delta_table}
    charts = {"状态漏斗": _count_chart(status_table), "月度趋势": _count_chart(monthly_table), "渠道分析": [(str(row[0]), float(row[1])) for row in agent_table.rows[:10]], "业务方案": [(str(row[0]), float(row[1])) for row in plan_table.rows[:10]], "业务员工作量": _count_chart(staff_table), "核保风险": _count_chart(risk_table), "车牌地域": _count_chart(region_table), "起保日期差异": _count_chart(delta_table)}
    return AnalysisReport("报价数据分析", [("报价订单", f"{total:,}", "唯一订单"), ("生效订单", f"{effective:,}", _percent(effective / total if total else 0)), ("待跟进", f"{active:,}", "暂存/修改/待支付"), ("渠道数量", f"{agents[agents.ne('未填写')].nunique():,}", "有效代理人")], tables, charts, insights)


def _policy_order_summary(frame: pd.DataFrame, effective_only: bool = True) -> pd.DataFrame:
    source = frame[_clean_text(frame["状态"]).eq("生效")].copy() if effective_only else frame.copy()
    return source.groupby("订单号", dropna=True).agg(保单行数=("投保单号", "count"), 保险费=("保险费", "sum"), 非车保费=("非车汇总保费", "sum"), 车船税=("车船税汇总金额", "sum"), 录单日期=("录单日期", "min"), 业务员=("业务员", "first"), 出单员=("出单员", "first"), 车牌号=("车牌号", "first")).reset_index()


def analyze_policy(frame: pd.DataFrame) -> AnalysisReport:
    statuses = _clean_text(frame["状态"])
    total_rows, total_orders = len(frame), int(frame["订单号"].nunique())
    effective = frame[statuses.eq("生效")].copy()
    effective_orders = _policy_order_summary(frame)
    effective_count = len(effective_orders)
    premium = float(effective["保险费"].sum())
    avg = float(effective_orders["保险费"].mean()) if effective_count else 0
    cancelled_orders = int(frame[statuses.isin(["已注销", "已退保"])]["订单号"].nunique())

    status_table = _count_table(statuses, "保单状态", total_rows)
    daily = effective.assign(日期=effective["录单日期"].dt.strftime("%Y-%m-%d")).groupby("日期", dropna=False).agg(保单数=("投保单号", "count"), 保费=("保险费", "sum")).sort_index()
    daily_table = TableData(["录单日期", "保单数", "保险费"], [[str(idx), int(row.保单数), _money(row.保费)] for idx, row in daily.iterrows()])

    staff = effective.groupby(_clean_text(effective["业务员"])).agg(保单数=("投保单号", "count"), 订单数=("订单号", "nunique"), 保险费=("保险费", "sum")).sort_values("保险费", ascending=False)
    staff_table = TableData(["业务员", "保单数", "订单数", "保险费", "单均保费"], [[idx, int(row.保单数), int(row.订单数), _money(row.保险费), _money(row.保险费 / row.订单数 if row.订单数 else 0)] for idx, row in staff.iterrows()])
    issuer = effective.groupby(_clean_text(effective["出单员"])).agg(保单数=("投保单号", "count"), 订单数=("订单号", "nunique"), 保险费=("保险费", "sum")).sort_values("保险费", ascending=False)
    issuer_table = TableData(["出单员", "保单数", "订单数", "保险费"], [[idx, int(row.保单数), int(row.订单数), _money(row.保险费)] for idx, row in issuer.iterrows()])

    composition = [("保险费", float(effective["保险费"].sum())), ("非车保费", float(effective["非车汇总保费"].sum())), ("车船税", float(effective["车船税汇总金额"].sum()))]
    composition_table = TableData(["收入构成", "金额"], [[name, _money(value)] for name, value in composition])
    plate_text = _clean_text(effective["车牌号"])
    region = plate_text.str[:1].where(plate_text.ne("未填写") & plate_text.str[:1].str.match(r"[\u4e00-\u9fff]", na=False), "其他/未填写")
    region_data = effective.assign(地区=region).groupby("地区").agg(保单数=("投保单号", "count"), 保险费=("保险费", "sum")).sort_values("保险费", ascending=False)
    region_table = TableData(["车牌地区", "保单数", "保险费"], [[idx, int(row.保单数), _money(row.保险费)] for idx, row in region_data.iterrows()])

    bands = pd.cut(effective_orders["保险费"], [-0.01, 1000, 3000, 5000, 10000, float("inf")], labels=["0-1千", "1千-3千", "3千-5千", "5千-1万", "1万以上"])
    band_table = _count_table(bands.astype("string").fillna("未知"), "订单保费区间", effective_count)

    insights = [
        f"共有 {total_orders:,} 个订单、{total_rows:,} 条保单记录，其中生效订单 {effective_count:,} 个。",
        f"生效保险费合计 {_money(premium)}，生效订单平均保费 {_money(avg)}。",
        f"注销或退保订单 {cancelled_orders:,} 个，占全部订单 {_percent(cancelled_orders / total_orders if total_orders else 0)}。",
        f"保费贡献最高的业务员为“{staff.index[0]}”，生效保费 {_money(float(staff.iloc[0].保险费))}。" if not staff.empty else "暂无业务员保费数据。",
    ]
    tables = {"保单状态": status_table, "每日出单趋势": daily_table, "业务员绩效": staff_table, "出单员绩效": issuer_table, "保费构成": composition_table, "车牌地域": region_table, "订单保费区间": band_table}
    charts = {"保单状态": _count_chart(status_table), "每日出单趋势": [(str(idx), float(row.保费)) for idx, row in daily.tail(14).iterrows()], "业务员绩效": [(str(idx), float(row.保险费)) for idx, row in staff.head(10).iterrows()], "出单员绩效": [(str(idx), float(row.保险费)) for idx, row in issuer.head(10).iterrows()], "保费构成": composition, "车牌地域": [(str(idx), float(row.保险费)) for idx, row in region_data.head(10).iterrows()], "订单保费区间": _count_chart(band_table)}
    return AnalysisReport("保单数据分析", [("全部订单", f"{total_orders:,}", f"{total_rows:,} 条保单"), ("生效订单", f"{effective_count:,}", _percent(effective_count / total_orders if total_orders else 0)), ("生效保费", _money(premium), "不含车船税"), ("订单均费", _money(avg), "生效订单")], tables, charts, insights)


def analyze_joint(quotes: pd.DataFrame, policies: pd.DataFrame) -> AnalysisReport:
    policy_orders_all = policies.groupby("订单号", dropna=True).agg(保单状态=("状态", lambda values: "生效" if (_clean_text(values) == "生效").any() else str(_clean_text(values).iloc[0])), 保单行数=("投保单号", "count"), 保险费=("保险费", "sum"), 录单日期=("录单日期", "min")).reset_index()
    effective_orders = _policy_order_summary(policies)
    joined = quotes.merge(policy_orders_all, on="订单号", how="left")
    effective_joined = quotes.merge(effective_orders[["订单号", "保险费", "录单日期"]], on="订单号", how="left")
    joined["已关联"] = joined["保单行数"].notna()
    effective_joined["已生效"] = effective_joined["保险费"].notna()
    effective_joined["出单天数"] = (effective_joined["录单日期"] - effective_joined["录入时间"]).dt.days
    total = len(quotes); linked = int(joined["已关联"].sum()); converted = int(effective_joined["已生效"].sum())
    premium = float(effective_joined["保险费"].fillna(0).sum())

    agent = _clean_text(effective_joined["代理人"])
    agent_data = effective_joined.assign(渠道=agent).groupby("渠道").agg(报价数=("订单号", "nunique"), 生效数=("已生效", "sum"), 生效保费=("保险费", "sum")).sort_values("报价数", ascending=False)
    agent_table = TableData(["渠道", "报价数", "关联生效数", "关联生效率", "关联保费"], [[idx, int(row.报价数), int(row.生效数), _percent(row.生效数 / row.报价数 if row.报价数 else 0), _money(float(row.生效保费 or 0))] for idx, row in agent_data.iterrows()])
    plan = _clean_text(effective_joined["业务方案号"])
    plan_data = effective_joined.assign(方案=plan).groupby("方案").agg(报价数=("订单号", "nunique"), 生效数=("已生效", "sum"), 生效保费=("保险费", "sum")).sort_values("报价数", ascending=False)
    plan_table = TableData(["业务方案", "报价数", "关联生效数", "关联生效率", "关联保费"], [[idx, int(row.报价数), int(row.生效数), _percent(row.生效数 / row.报价数 if row.报价数 else 0), _money(float(row.生效保费 or 0))] for idx, row in plan_data.iterrows()])
    status_data = effective_joined.assign(报价状态=_clean_text(effective_joined["订单状态代码"])).groupby("报价状态").agg(报价数=("订单号", "size"), 生效数=("已生效", "sum"), 生效保费=("保险费", "sum")).sort_values("报价数", ascending=False)
    status_table = TableData(["报价状态", "报价数", "关联生效数", "关联生效率", "关联保费"], [[idx, int(row.报价数), int(row.生效数), _percent(row.生效数 / row.报价数 if row.报价数 else 0), _money(float(row.生效保费 or 0))] for idx, row in status_data.iterrows()])
    days = effective_joined["出单天数"].dropna()
    day_bands = pd.cut(days, [-float("inf"), 0, 1, 3, 7, float("inf")], labels=["当天及以前", "1天", "2-3天", "4-7天", "超过7天"])
    day_table = _count_table(day_bands.astype("string").fillna("未知"), "报价至录单耗时", len(days))
    q_start, q_end = quotes["录入时间"].min(), quotes["录入时间"].max()
    p_start, p_end = policies["录单日期"].min(), policies["录单日期"].max()
    insights = [
        f"报价范围 {q_start:%Y-%m-%d} 至 {q_end:%Y-%m-%d}；保单范围 {p_start:%Y-%m-%d} 至 {p_end:%Y-%m-%d}。" if all(pd.notna(v) for v in [q_start, q_end, p_start, p_end]) else "报价与保单日期范围存在缺失。",
        f"{total:,} 个报价订单中，有 {linked:,} 个能关联到保单记录，关联覆盖率 {_percent(linked / total if total else 0)}。",
        f"其中关联到生效保单 {converted:,} 个，关联生效保费 {_money(premium)}。",
        "关联覆盖率受两份文件时间范围影响，不应直接当作完整业务转化率。",
    ]
    tables = {"渠道关联表现": agent_table, "方案关联表现": plan_table, "状态关联表现": status_table, "报价至录单耗时": day_table}
    charts = {"渠道关联表现": [(str(idx), float(row.生效数)) for idx, row in agent_data.head(10).iterrows()], "方案关联表现": [(str(idx), float(row.生效数)) for idx, row in plan_data.head(10).iterrows()], "状态关联表现": [(str(idx), float(row.生效数)) for idx, row in status_data.head(10).iterrows()], "报价至录单耗时": _count_chart(day_table)}
    return AnalysisReport("报价 × 保单联合分析", [("报价订单", f"{total:,}", "上传样本"), ("关联订单", f"{linked:,}", _percent(linked / total if total else 0)), ("关联生效", f"{converted:,}", _percent(converted / total if total else 0)), ("关联保费", _money(premium), "生效保单")], tables, charts, insights)


def _quality_rows(frame: pd.DataFrame, kind: str, source: str) -> list[list[Any]]:
    important = QUOTE_COLUMNS if kind == "quote" else POLICY_COLUMNS
    rows = []
    for column in important:
        series = frame[column]
        text = series.astype("string").str.strip().str.lower()
        missing = int(series.isna().sum() + text.isin(MISSING_MARKERS - {"nan", "none", "null", "nat"}).sum())
        rows.append([source, column, len(frame), missing, _percent(1 - missing / len(frame) if len(frame) else 0), int(series.nunique(dropna=True))])
    return rows


def analyze_quality(quotes: pd.DataFrame | None = None, policies: pd.DataFrame | None = None) -> AnalysisReport:
    if quotes is None and policies is None:
        raise ValueError("请至少上传一份报价表或保单表。")
    rows: list[list[Any]] = []
    insights: list[str] = []
    total_rows = 0
    if quotes is not None:
        rows += _quality_rows(quotes, "quote", "报价表")
        total_rows += len(quotes)
        duplicates = int(quotes["订单号"].duplicated().sum())
        invalid_vin = int((~_clean_text(quotes["车架号"], "").str.match(r"^[A-HJ-NPR-Z0-9]{17}$", na=False)).sum())
        insights += [f"报价表订单号重复 {duplicates:,} 条。", f"车架号缺失或不符合17位规范 {invalid_vin:,} 条。"]
    if policies is not None:
        rows += _quality_rows(policies, "policy", "保单表")
        total_rows += len(policies)
        duplicate_apps = int(policies["投保单号"].dropna().duplicated().sum())
        insights += [f"保单表投保单号重复 {duplicate_apps:,} 条。"]
    table = TableData(["数据源", "字段", "总行数", "缺失/占位", "完整率", "唯一值"], rows)
    worst = sorted(rows, key=lambda row: float(str(row[4]).rstrip("%")))[:10]
    chart = [(f"{row[0]}·{row[1]}", float(str(row[4]).rstrip("%"))) for row in worst]
    complete_fields = sum(1 for row in rows if row[3] == 0)
    return AnalysisReport("数据质量分析", [("扫描记录", f"{total_rows:,}", "上传文件"), ("检查字段", f"{len(rows):,}", "必要表头"), ("完整字段", f"{complete_fields:,}", "无缺失/占位"), ("问题字段", f"{len(rows) - complete_fields:,}", "建议清洗")], {"字段完整度": table}, {"字段完整度": chart}, insights)


def run_analysis(mode: str, quote_path: str = "", policy_path: str = "") -> AnalysisReport:
    quotes = load_excel(quote_path, "quote") if quote_path else None
    policies = load_excel(policy_path, "policy") if policy_path else None
    if mode == "报价分析":
        if quotes is None: raise ValueError("请上传报价数据文件。")
        return analyze_quote(quotes)
    if mode == "保单分析":
        if policies is None: raise ValueError("请上传保单数据文件。")
        return analyze_policy(policies)
    if mode == "联合分析":
        if quotes is None or policies is None: raise ValueError("联合分析需要同时上传报价表和保单表。")
        return analyze_joint(quotes, policies)
    if mode == "数据质量":
        return analyze_quality(quotes, policies)
    raise ValueError(f"未知分析模式：{mode}")
