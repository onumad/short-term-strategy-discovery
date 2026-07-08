from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument


@dataclass(frozen=True)
class Phase10AConfig:
    max_specs: int = 48
    recent_sessions: int = 252
    branches: tuple[str, ...] = ("overnight_range_breakout", "overnight_range_fade")
    sides: tuple[str, ...] = ("long", "short")
    timeframes: tuple[int, ...] = (5, 15)
    entry_windows: tuple[str, ...] = ("opening_response", "midday_response")
    execution_exit_variants: tuple[str, ...] = (
        "next_bar_open_hard_stop_time_exit",
        "next_bar_open_hard_stop_structure_target_time_exit",
        "close_confirm_fill_next_open_hard_stop_time_exit",
    )
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    target_r: float = 1.5
    max_trades_per_day: int = 2
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_trades: int = 60
    min_active_days: int = 35
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08


@dataclass(frozen=True)
class Phase10ASpec:
    branch: str
    side: str
    timeframe: int
    entry_window: str
    entry_start: str
    entry_end: str
    execution_exit_variant: str
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    target_r: float = 1.5
    max_trades_per_day: int = 2
    min_minutes_between_entries: int = 30
    time_stop_minutes: int = 30

    @property
    def candidate_id(self) -> str:
        return f"MNQ_10a_onrange_{self.branch}_{self.side}_tf{self.timeframe}_{self.entry_window}_{self.execution_exit_variant}"

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "instrument": "MNQ", **self.__dict__}


def build_phase10a_specs(config: Phase10AConfig = Phase10AConfig()) -> list[Phase10ASpec]:
    specs: list[Phase10ASpec] = []
    for branch in config.branches:
        for side in config.sides:
            for timeframe in config.timeframes:
                for window in config.entry_windows:
                    start, end = ("09:35", "10:30") if window == "opening_response" else ("10:30", "13:30")
                    for variant in config.execution_exit_variants:
                        specs.append(
                            Phase10ASpec(
                                branch=branch,
                                side=side,
                                timeframe=timeframe,
                                entry_window=window,
                                entry_start=start,
                                entry_end=end,
                                execution_exit_variant=variant,
                                atr_cap_multiple=config.atr_cap_multiple,
                                buffer_ticks=config.buffer_ticks,
                                target_r=config.target_r,
                                max_trades_per_day=config.max_trades_per_day,
                                min_minutes_between_entries=30 if timeframe == 5 else 60,
                                time_stop_minutes=30 if timeframe == 5 else 45,
                            )
                        )
    return specs[: max(int(config.max_specs), 0)]


def compute_overnight_levels(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    df = bars.sort_values("timestamp").copy()
    minutes = _minutes(df["timestamp"])
    eth = df[(df["session_segment"].eq("ETH")) & ((minutes >= 18 * 60) | (minutes < 9 * 60 + 30))]
    levels = eth.groupby("trading_session").agg(
        overnight_high=("high", "max"),
        overnight_low=("low", "min"),
        overnight_volume=("volume", "sum"),
    )
    levels["overnight_midpoint"] = (levels["overnight_high"] + levels["overnight_low"]) / 2.0
    levels["overnight_range_points"] = levels["overnight_high"] - levels["overnight_low"]
    levels["overnight_range_percentile"] = levels["overnight_range_points"].rank(pct=True)
    rth_close = df[df["session_segment"].eq("RTH")].groupby("trading_session")["close"].last().shift(1)
    rth_open = df[df["session_segment"].eq("RTH")].groupby("trading_session")["open"].first()
    levels["gap_from_prior_rth_close"] = rth_open - rth_close
    return levels.reset_index()


def _feature_bars(bars: pd.DataFrame, spec: Phase10ASpec) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    if spec.timeframe > 1:
        frames = []
        for session, day in rth.groupby("trading_session", sort=True):
            day = day.set_index("timestamp")
            res = day.resample(f"{spec.timeframe}min", origin="start_day", offset="30min", label="left", closed="left").agg({"symbol":"last","open":"first","high":"max","low":"min","close":"last","volume":"sum","trading_session":"last","session_segment":"last"}).dropna(subset=["open","high","low","close"]).reset_index()
            frames.append(res)
        rth = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    levels = compute_overnight_levels(bars)
    out = rth.merge(levels, on="trading_session", how="left")
    out = out.dropna(subset=["overnight_high", "overnight_low"]).sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    tr = (out["high"] - out["low"]).abs()
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(14, min_periods=3).mean()).fillna(tr)
    return out


def generate_phase10a_signals(bars: pd.DataFrame, spec: Phase10ASpec) -> list[dict[str, Any]]:
    featured = _feature_bars(bars, spec)
    signals: list[dict[str, Any]] = []
    if featured.empty:
        return signals
    start, end = _hhmm(spec.entry_start), _hhmm(spec.entry_end)
    for _, day in featured.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        touched_high = touched_low = False
        for i in range(len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            touched_high = touched_high or float(row["high"]) > float(row["overnight_high"])
            touched_low = touched_low or float(row["low"]) < float(row["overnight_low"])
            if minute < start or minute >= end or minute < 9 * 60 + 35:
                continue
            signal = False
            if spec.branch == "overnight_range_breakout":
                signal = float(row["close"]) > float(row["overnight_high"]) if spec.side == "long" else float(row["close"]) < float(row["overnight_low"])
                sweep_extreme = float(row["high"] if spec.side == "short" else row["low"])
            else:
                if spec.side == "short":
                    signal = touched_high and float(row["close"]) < float(row["overnight_high"]) and float(row["close"]) > float(row["overnight_low"])
                    sweep_extreme = float(day.loc[:i, "high"].max())
                else:
                    signal = touched_low and float(row["close"]) > float(row["overnight_low"]) and float(row["close"]) < float(row["overnight_high"])
                    sweep_extreme = float(day.loc[:i, "low"].min())
            if not signal:
                continue
            entry_idx = i + 1
            confirmation_time = row["timestamp"]
            if spec.execution_exit_variant.startswith("close_confirm"):
                confirm = day.iloc[i + 1]
                if spec.branch == "overnight_range_breakout":
                    ok = float(confirm["close"]) > float(row["overnight_high"]) if spec.side == "long" else float(confirm["close"]) < float(row["overnight_low"])
                elif spec.side == "short":
                    ok = float(confirm["close"]) < float(row["overnight_high"]) and float(confirm["close"]) > float(row["overnight_low"])
                else:
                    ok = float(confirm["close"]) > float(row["overnight_low"]) and float(confirm["close"]) < float(row["overnight_high"])
                if not ok:
                    continue
                confirmation_time = confirm["timestamp"]
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            signals.append({"candidate_id": spec.candidate_id, "signal_time": row["timestamp"], "confirmation_time": confirmation_time, "entry_time": entry["timestamp"], "trading_session": str(row["trading_session"]), "side": spec.side, "branch": spec.branch, "signal_close": float(row["close"]), "overnight_high": float(row["overnight_high"]), "overnight_low": float(row["overnight_low"]), "overnight_midpoint": float(row["overnight_midpoint"]), "overnight_range_points": float(row["overnight_range_points"]), "overnight_range_percentile": float(row["overnight_range_percentile"]), "gap_from_prior_rth_close": float(row.get("gap_from_prior_rth_close", 0.0) or 0.0), "atr": float(row.get("atr", 0.0) or 0.0), "sweep_extreme": sweep_extreme, "first_touch": int((spec.side == "long" and not touched_low) or (spec.side == "short" and not touched_high))})
    return signals


def run_phase10a_retest(bars: pd.DataFrame, config: Phase10AConfig = Phase10AConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase10a_specs(config)
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    all_trades=[]; all_folds=[]; rows=[]
    for spec in specs:
        featured = _feature_bars(bars, spec)
        trades = _simulate_trades(featured, generate_phase10a_signals(bars, spec), spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            all_trades.append(trades)
            all_folds.append(_fold_rows(trades, spec, sessions, config))
        rows.append(_candidate_row(spec, trades, sessions, split_map, config))
    trade_logs = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    folds = pd.concat(all_folds, ignore_index=True) if all_folds else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase10a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase10a_rank", range(1, len(candidates)+1))
    return {"candidate_results": candidates, "trade_logs": trade_logs, "walk_forward_folds": folds, "daily_pnl": _daily_pnl(trade_logs), "concentration_diagnostics": _concentration(trade_logs), "level_diagnostics": compute_overnight_levels(bars), "branch_summary": _summary(trade_logs,"branch"), "side_summary": _summary(trade_logs,"side"), "time_window_summary": _summary(trade_logs,"entry_window"), "exit_reason_summary": _summary(trade_logs,"exit_reason"), "range_regime_summary": _summary(trade_logs,"range_bucket"), "specs": pd.DataFrame([s.to_dict() for s in specs])}


def _simulate_trades(featured: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase10ASpec) -> pd.DataFrame:
    if featured.empty or not signals: return pd.DataFrame()
    inst = get_instrument("MNQ"); day_map={str(s):d.sort_values("timestamp").reset_index(drop=True) for s,d in featured.groupby("trading_session", sort=True)}
    rows=[]; counts={}; last={}
    for sig in sorted(signals, key=lambda x:x["entry_time"]):
        sess=str(sig["trading_session"]); et=pd.Timestamp(sig["entry_time"])
        if counts.get(sess,0)>=spec.max_trades_per_day: continue
        if sess in last and (et-last[sess]).total_seconds()/60 < spec.min_minutes_between_entries: continue
        day=day_map.get(sess); matches=[] if day is None else day.index[day["timestamp"].eq(et)].tolist()
        if not matches: continue
        trade=_simulate_one(day, matches[0], sig, spec, inst)
        rows.append({**sig, **trade, **spec.to_dict()}); counts[sess]=counts.get(sess,0)+1; last[sess]=et
    out=pd.DataFrame(rows)
    if not out.empty:
        out["range_bucket"] = pd.cut(out["overnight_range_percentile"], bins=[0,.33,.66,1], labels=["narrow","middle","wide"], include_lowest=True).astype(str)
        out["gap_bucket"] = pd.cut(out["gap_from_prior_rth_close"].fillna(0), bins=[-999,-10,10,999], labels=["gap_down","flat","gap_up"]).astype(str)
        out["entry_time_bucket"] = out["entry_time"].map(lambda x: "opening_response" if _minute(x) < 10*60+30 else "midday_response")
    return out


def _simulate_one(day: pd.DataFrame, entry_pos: int, sig: dict[str, Any], spec: Phase10ASpec, inst) -> dict[str, Any]:
    entry=day.iloc[entry_pos]; entry_price=float(entry["open"]); buf=spec.buffer_ticks*inst.tick_size; atr=max(float(sig.get("atr",0)), inst.tick_size*8); cap=atr*spec.atr_cap_multiple
    if spec.branch=="overnight_range_breakout" and spec.side=="long": structural=float(sig["overnight_high"])-buf; actual=max(structural, entry_price-cap); target=entry_price+(entry_price-actual)*spec.target_r
    elif spec.branch=="overnight_range_breakout" and spec.side=="short": structural=float(sig["overnight_low"])+buf; actual=min(structural, entry_price+cap); target=entry_price-(actual-entry_price)*spec.target_r
    elif spec.side=="long": structural=float(sig["sweep_extreme"])-buf; actual=max(structural, entry_price-cap); target=float(sig["overnight_midpoint"])
    else: structural=float(sig["sweep_extreme"])+buf; actual=min(structural, entry_price+cap); target=float(sig["overnight_midpoint"])
    max_exit=pd.Timestamp(entry["timestamp"])+pd.Timedelta(minutes=spec.time_stop_minutes); exit_price=float(entry["close"]); exit_time=entry["timestamp"]; reason="time_stop"; mfe=mae=0.0; amb=0
    for pos in range(entry_pos, len(day)):
        row=day.iloc[pos]; ts=pd.Timestamp(row["timestamp"])
        if spec.side=="long": fav=float(row["high"])-entry_price; adv=entry_price-float(row["low"]); stop_hit=float(row["low"])<=actual; target_hit=float(row["high"])>=target
        else: fav=entry_price-float(row["low"]); adv=float(row["high"])-entry_price; stop_hit=float(row["high"])>=actual; target_hit=float(row["low"])<=target
        mfe=max(mfe, fav*inst.point_value); mae=max(mae, adv*inst.point_value)
        if stop_hit:
            exit_price=actual; exit_time=ts; reason="stop_same_bar_conservative" if target_hit else "stop"; amb=int(target_hit); break
        if "structure_target" in spec.execution_exit_variant and target_hit:
            exit_price=target; exit_time=ts; reason="target"; break
        if ts>=max_exit or _minute(ts)>=15*60+45:
            exit_price=float(row["close"]); exit_time=ts; reason="session_flatten" if _minute(ts)>=15*60+45 else "time_stop"; break
    gross=(exit_price-entry_price)*(1 if spec.side=="long" else -1)*inst.point_value
    return {"entry_price":round(entry_price,4),"exit_time":exit_time,"exit_price":round(exit_price,4),"exit_reason":reason,"structural_stop":round(structural,4),"atr_cap_stop":round(entry_price-cap if spec.side=="long" else entry_price+cap,4),"actual_stop":round(actual,4),"target_price":round(target,4),"gross_pnl":round(gross,2),"net_pnl":round(gross-inst.base_cost,2),"stress_pnl":round(gross-inst.stress_cost,2),"mfe":round(mfe,2),"mae":round(mae,2),"mfe_to_mae_ratio":_div(mfe,mae),"same_bar_ambiguity":amb,"distance_from_midpoint_at_entry":round((entry_price-float(sig["overnight_midpoint"]))*inst.point_value,2)}


def _candidate_row(spec, trades, sessions, split_map, c):
    row=spec.to_dict()
    if trades.empty: row.update(_zero())
    else:
        t=trades.copy(); t["split"]=t["trading_session"].astype(str).map(split_map); net=float(t["net_pnl"].sum()); eq=t["net_pnl"].cumsum(); daily=t.groupby("trading_session")["net_pnl"].sum(); folds=_fold_rows(t,spec,sessions,c)
        row.update({"trades":len(t),"active_days":int(t["trading_session"].nunique()),"trades_per_active_day":_div(len(t),t["trading_session"].nunique()),"net_pnl":round(net,2),"stress_pnl":round(float(t["stress_pnl"].sum()),2),"validation_pnl":round(float(t.loc[t["split"].eq("validation"),"net_pnl"].sum()),2),"holdout_pnl":round(float(t.loc[t["split"].eq("holdout"),"net_pnl"].sum()),2),"max_drawdown":round(float((eq-eq.cummax()).min()),2),"best_day_concentration":_conc(float(daily.max()),net),"best_trade_concentration":_conc(float(t["net_pnl"].max()),net),"avg_mfe":round(float(t["mfe"].mean()),2),"avg_mae":round(float(t["mae"].mean()),2),**_fold_summary(folds)})
    row["phase10a_label"]=_label(row,c); row["phase10a_score"]=round(float(row.get("stress_pnl",0))+float(row.get("walk_forward_stress_pnl",0))-abs(float(row.get("max_drawdown",0))),4); row["reject_reasons"]=_reasons(row,c); return row


def _label(r,c):
    if r.get("trades",0)<c.min_trades or r.get("active_days",0)<c.min_active_days or not(1<=r.get("trades_per_active_day",0)<=3): return "phase10a_rejected_low_activity"
    if r.get("net_pnl",0)<=0 or r.get("stress_pnl",0)<=0: return "phase10a_rejected_negative_stress"
    if r.get("validation_pnl",0)<=0: return "phase10a_rejected_negative_validation"
    if r.get("holdout_pnl",0)<=0: return "phase10a_rejected_negative_holdout"
    if r.get("max_drawdown",0)<c.drawdown_limit: return "phase10a_rejected_drawdown"
    if r.get("walk_forward_stress_pnl",0)<=0 or r.get("positive_wf_test_folds_pct",0)<.9 or r.get("worst_wf_test_fold",0)<c.worst_fold_limit: return "phase10a_rejected_fold_instability"
    if r.get("best_day_concentration",1)>c.concentration_limit or r.get("best_trade_concentration",1)>c.trade_concentration_limit: return "phase10a_rejected_concentration"
    return "phase10a_candidate_for_paper_review"

def _reasons(r,c):
    items=[("low activity", r.get("trades",0)<c.min_trades), ("negative stress", r.get("stress_pnl",0)<=0), ("negative validation", r.get("validation_pnl",0)<=0), ("negative holdout", r.get("holdout_pnl",0)<=0), ("fold instability", r.get("positive_wf_test_folds_pct",0)<.9), ("concentration", r.get("best_day_concentration",1)>c.concentration_limit or r.get("best_trade_concentration",1)>c.trade_concentration_limit)]
    return "; ".join(k for k,v in items if v) or "survived Phase 10A gates; review packet only"

def make_phase10a_recommendation(result):
    c=result["candidate_results"]
    if c.empty: return {"next_action":"phase10b_opening_range_fade_stricter_confirmation","rationale":"No Phase 10A candidates were produced."}
    paper=c[c["phase10a_label"].eq("phase10a_candidate_for_paper_review")]
    if not paper.empty: return {"next_action":"prepare_phase10a_review_packet","rationale":"At least one candidate passed strict Phase 10A gates; review only, not paper approval.","top_candidate":paper.iloc[0].to_dict()}
    positive=c[(c["stress_pnl"]>0)&(c["holdout_pnl"]>0)]
    if not positive.empty: return {"next_action":"phase10b_targeted_overnight_range_diagnostic_retest","rationale":"One branch had positive stress/holdout but failed activity, fold, or concentration gates.","top_candidate":positive.iloc[0].to_dict()}
    return {"next_action":"phase10b_opening_range_fade_stricter_confirmation","rationale":"No candidate and no clearly positive diagnostic axis survived Phase 10A."}

def render_phase10a_report(result, recommendation, report_path: Path) -> str:
    c=result["candidate_results"]; counts=c["phase10a_label"].value_counts().to_dict() if not c.empty else {}
    lines=["# Phase 10A MNQ Overnight Range Breakout/Fade", "", "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.", "", "## Summary", "", f"- Specs evaluated: `{len(c)}`", f"- Trade rows: `{len(result['trade_logs'])}`", f"- Label counts: `{counts}`", f"- Next action: `{recommendation.get('next_action')}`", f"- Rationale: {recommendation.get('rationale')}", "", "| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Notes |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for _,r in c.head(12).iterrows(): lines.append(f"| `{r['candidate_id']}` | {r['phase10a_label']} | ${float(r['net_pnl']):.2f} | ${float(r['stress_pnl']):.2f} | ${float(r['validation_pnl']):.2f} | ${float(r['holdout_pnl']):.2f} | ${float(r['walk_forward_stress_pnl']):.2f} | {r['reject_reasons']} |")
    lines += ["", "## Outputs", "", "- `outputs/phase10a_candidate_results.csv`", "- `outputs/phase10a_trade_logs.csv`", "- `outputs/phase10a_walk_forward_folds.csv`", "- `outputs/phase10a_daily_pnl.csv`", "- `outputs/phase10a_concentration_diagnostics.csv`", "- `outputs/phase10a_level_diagnostics.csv`", "- `outputs/phase10a_branch_summary.csv`", "- `outputs/phase10a_side_summary.csv`", "- `outputs/phase10a_time_window_summary.csv`", "- `outputs/phase10a_exit_reason_summary.csv`", "- `outputs/phase10a_range_regime_summary.csv`", "- `outputs/phase10a_strategy_specs.json`", "- `outputs/phase10a_next_action_recommendation.json`", f"- `{report_path.as_posix()}`"]
    return "\n".join(lines)+"\n"

def _fold_rows(trades,spec,sessions,c):
    rows=[]; window=c.train_sessions+c.validation_sessions+c.test_sessions; start=0; fold=1
    while start+window<=len(sessions):
        test=sessions[start+c.train_sessions+c.validation_sessions:start+window]; seg=trades[trades["trading_session"].astype(str).isin(test)]
        rows.append({"candidate_id":spec.candidate_id,"fold":fold,"net_pnl":round(float(seg["net_pnl"].sum()),2),"stress_pnl":round(float(seg["stress_pnl"].sum()),2),"trades":len(seg)}); start+=c.step_sessions; fold+=1
    return pd.DataFrame(rows)
def _fold_summary(f):
    if f.empty: return {"walk_forward_test_pnl":0.0,"walk_forward_stress_pnl":0.0,"positive_wf_test_folds_pct":0.0,"worst_wf_test_fold":0.0}
    return {"walk_forward_test_pnl":round(float(f["net_pnl"].sum()),2),"walk_forward_stress_pnl":round(float(f["stress_pnl"].sum()),2),"positive_wf_test_folds_pct":_div(int((f["stress_pnl"]>0).sum()),len(f)),"worst_wf_test_fold":round(float(f["stress_pnl"].min()),2)}
def _zero():
    return {"trades":0,"active_days":0,"trades_per_active_day":0.0,"net_pnl":0.0,"stress_pnl":0.0,"validation_pnl":0.0,"holdout_pnl":0.0,"max_drawdown":0.0,"best_day_concentration":1.0,"best_trade_concentration":1.0,"avg_mfe":0.0,"avg_mae":0.0,**_fold_summary(pd.DataFrame())}
def _daily_pnl(t): return pd.DataFrame() if t.empty else t.groupby(["candidate_id","trading_session"]).agg(trades=("net_pnl","size"),net_pnl=("net_pnl","sum"),stress_pnl=("stress_pnl","sum")).reset_index()
def _concentration(t): return pd.DataFrame() if t.empty else t.groupby(["candidate_id","trading_session"]).agg(pnl=("net_pnl","sum"),trades=("net_pnl","size")).reset_index().sort_values("pnl",ascending=False)
def _summary(t,col):
    if t.empty or col not in t: return pd.DataFrame()
    return t.groupby(col).agg(trades=("net_pnl","size"),net_pnl=("net_pnl","sum"),stress_pnl=("stress_pnl","sum"),avg_mfe=("mfe","mean"),avg_mae=("mae","mean")).reset_index().rename(columns={col:"group"}).sort_values("stress_pnl",ascending=False)
def serialize_phase10a_specs(specs): return json.dumps([s.to_dict() for s in specs], indent=2, sort_keys=True, default=str)
def recommendation_to_json(rec): return json.dumps(rec, indent=2, sort_keys=True, default=str)
def _hhmm(s): h,m=s.split(":"); return int(h)*60+int(m)
def _minute(ts): ts=pd.Timestamp(ts); return ts.hour*60+ts.minute
def _minutes(s): return pd.to_datetime(s).dt.hour*60+pd.to_datetime(s).dt.minute
def _div(a,b): return round(float(a/b),6) if b else 0.0
def _conc(best,total): return _div(max(best,0.0),total) if total>0 else 1.0
