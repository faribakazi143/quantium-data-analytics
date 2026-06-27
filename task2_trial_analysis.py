"""
Quantium Virtual Internship - Retail Strategy and Analytics - Task 2
Trial vs Control store analysis (Python implementation)

Requires QVI_data.csv (produced by task1_customer_analytics.py).
"""
import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

plt.rcParams.update({
    "figure.dpi": 130,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
})
OUT = "figs_t2"
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------
# 1. Loaded the data
# ----------------------------------------------------------------------
data = pd.read_csv("QVI_data.csv")
data["DATE"] = pd.to_datetime(data["DATE"])
data["YEARMONTH"] = data["DATE"].dt.year * 100 + data["DATE"].dt.month

# ----------------------------------------------------------------------
# 2. Built monthly measures per store
# ----------------------------------------------------------------------
def make_measures(df):
    g = df.groupby(["STORE_NBR", "YEARMONTH"])
    m = g.agg(
        totSales=("TOT_SALES", "sum"),
        nCustomers=("LYLTY_CARD_NBR", "nunique"),
        nTxn=("TXN_ID", "nunique"),
        totQty=("PROD_QTY", "sum"),
    ).reset_index()
    m["nTxnPerCust"] = m["nTxn"] / m["nCustomers"]
    m["nChipsPerTxn"] = m["totQty"] / m["nTxn"]
    m["avgPricePerUnit"] = m["totSales"] / m["totQty"]
    return m.sort_values(["STORE_NBR", "YEARMONTH"]).reset_index(drop=True)

measureOverTime = make_measures(data)
counts = measureOverTime.groupby("STORE_NBR").size()
storesWithFullObs = counts[counts == 12].index
preTrial = measureOverTime[
    (measureOverTime["YEARMONTH"] < 201902)
    & (measureOverTime["STORE_NBR"].isin(storesWithFullObs))
].copy()

# ----------------------------------------------------------------------
# 3. Defined control-store selection metrics: correlation & magnitude distance
# ----------------------------------------------------------------------
def calculateCorrelation(inputTable, metricCol, trial_store):
    rows = []
    trial_vec = inputTable[inputTable["STORE_NBR"] == trial_store].set_index("YEARMONTH")[metricCol]
    for s in inputTable["STORE_NBR"].unique():
        cand = inputTable[inputTable["STORE_NBR"] == s].set_index("YEARMONTH")[metricCol]
        joined = pd.concat([trial_vec, cand], axis=1, join="inner")
        joined.columns = ["a", "b"]
        if len(joined) > 1 and joined["a"].std() > 0 and joined["b"].std() > 0:
            corr = joined["a"].corr(joined["b"])
        else:
            corr = 0.0
        rows.append({"Store1": trial_store, "Store2": s, "corr_measure": corr})
    return pd.DataFrame(rows)

def calculateMagnitudeDistance(inputTable, metricCol, trial_store):
    trial_vec = inputTable[inputTable["STORE_NBR"] == trial_store].set_index("YEARMONTH")[metricCol]
    recs = []
    for s in inputTable["STORE_NBR"].unique():
        cand = inputTable[inputTable["STORE_NBR"] == s].set_index("YEARMONTH")[metricCol]
        joined = pd.concat([trial_vec, cand], axis=1, join="inner")
        joined.columns = ["a", "b"]
        for ym, r in joined.iterrows():
            recs.append({"Store1": trial_store, "Store2": s,
                         "YEARMONTH": ym, "measure": abs(r["a"] - r["b"])})
    dist = pd.DataFrame(recs)
    mm = dist.groupby(["Store1", "YEARMONTH"])["measure"].agg(minDist="min", maxDist="max").reset_index()
    dist = dist.merge(mm, on=["Store1", "YEARMONTH"])
    rng = (dist["maxDist"] - dist["minDist"]).replace(0, np.nan)
    dist["magnitudeMeasure"] = 1 - (dist["measure"] - dist["minDist"]) / rng
    dist["magnitudeMeasure"] = dist["magnitudeMeasure"].fillna(1.0)
    out = dist.groupby(["Store1", "Store2"])["magnitudeMeasure"].mean().reset_index()
    out.columns = ["Store1", "Store2", "mag_measure"]
    return out

# ----------------------------------------------------------------------
# 4. Selected the control store for each trial store
# ----------------------------------------------------------------------
def select_control(trial_store, corr_weight=0.5):
    cs = calculateCorrelation(preTrial, "totSales", trial_store)
    cc = calculateCorrelation(preTrial, "nCustomers", trial_store)
    ms = calculateMagnitudeDistance(preTrial, "totSales", trial_store)
    mc = calculateMagnitudeDistance(preTrial, "nCustomers", trial_store)
    sN = cs.merge(ms, on=["Store1", "Store2"])
    sN["scoreNSales"] = corr_weight * sN["corr_measure"] + (1 - corr_weight) * sN["mag_measure"]
    sC = cc.merge(mc, on=["Store1", "Store2"])
    sC["scoreNCust"] = corr_weight * sC["corr_measure"] + (1 - corr_weight) * sC["mag_measure"]
    score = sN[["Store1", "Store2", "scoreNSales"]].merge(
        sC[["Store1", "Store2", "scoreNCust"]], on=["Store1", "Store2"])
    score["finalControlScore"] = 0.5 * score["scoreNSales"] + 0.5 * score["scoreNCust"]
    ranked = score[score["Store2"] != trial_store].sort_values("finalControlScore", ascending=False)
    return int(ranked.iloc[0]["Store2"]), score

def ym_to_date(ym):
    return pd.to_datetime(f"{ym // 100}-{ym % 100:02d}-01")

# ----------------------------------------------------------------------
# 5. Assessed the trial against a 5/95 confidence band
# ----------------------------------------------------------------------
def assess_trial(trial_store, control_store, metric, ylabel, fname):
    pre = preTrial
    scaling = (pre[(pre.STORE_NBR == trial_store) & (pre.YEARMONTH < 201902)][metric].sum()
               / pre[(pre.STORE_NBR == control_store) & (pre.YEARMONTH < 201902)][metric].sum())
    mot = measureOverTime.copy()
    scaledControl = mot[mot.STORE_NBR == control_store][["YEARMONTH", metric]].copy()
    scaledControl["controlScaled"] = scaledControl[metric] * scaling
    trial = mot[mot.STORE_NBR == trial_store][["YEARMONTH", metric]].copy()
    pdiff = scaledControl.merge(trial, on="YEARMONTH", suffixes=("_ctrl", "_trial"))
    pdiff["percentageDiff"] = (np.abs(pdiff["controlScaled"] - pdiff[f"{metric}_trial"])
                               / pdiff["controlScaled"])
    stdDev = pdiff[pdiff.YEARMONTH < 201902]["percentageDiff"].std()
    dof = 7
    pdiff["tValue"] = (pdiff[f"{metric}_trial"] - pdiff["controlScaled"]) / pdiff["controlScaled"] / stdDev
    tcrit = stats.t.ppf(0.95, dof)
    trial_months = pdiff[(pdiff.YEARMONTH > 201901) & (pdiff.YEARMONTH < 201905)]

    plot = pdiff[["YEARMONTH"]].copy()
    plot["Trial"] = pdiff[f"{metric}_trial"]
    plot["Control"] = pdiff["controlScaled"]
    plot["Control 95th %"] = pdiff["controlScaled"] * (1 + stdDev * 2)
    plot["Control 5th %"] = pdiff["controlScaled"] * (1 - stdDev * 2)
    plot["TransactionMonth"] = plot["YEARMONTH"].apply(ym_to_date)
    plot = plot.sort_values("TransactionMonth")

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.axvspan(ym_to_date(201902), ym_to_date(201904), color="#ffe8a3", alpha=0.5)
    ax.fill_between(plot["TransactionMonth"], plot["Control 5th %"], plot["Control 95th %"],
                    color="#2e86ab", alpha=0.12, label="Control 5-95% band")
    ax.plot(plot["TransactionMonth"], plot["Control"], color="#2e86ab", lw=2, marker="o", ms=4, label="Control (scaled)")
    ax.plot(plot["TransactionMonth"], plot["Trial"], color="#d1495b", lw=2, marker="o", ms=4, label="Trial")
    ax.set_xlabel("Month of operation"); ax.set_ylabel(ylabel)
    ax.set_title(f"Trial assessment - {ylabel.lower()} (store {trial_store})")
    ax.legend(frameon=False, fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.autofmt_xdate(rotation=45); fig.tight_layout()
    fig.savefig(f"{OUT}/{fname}", bbox_inches="tight"); plt.close(fig)
    return {"control": control_store, "tcrit": tcrit,
            "trial_months": trial_months[["YEARMONTH", "tValue"]].to_dict("records")}

# ----------------------------------------------------------------------
# Ran the analysis for all three trial stores
# ----------------------------------------------------------------------
for trial_store in [77, 86, 88]:
    control_store, _ = select_control(trial_store)
    sales_res = assess_trial(trial_store, control_store, "totSales", "Total sales",
                             f"trial_sales_{trial_store}.png")
    cust_res = assess_trial(trial_store, control_store, "nCustomers", "Number of customers",
                            f"trial_cust_{trial_store}.png")
    print(f"Trial {trial_store} -> control {control_store}")
    for r in sales_res["trial_months"]:
        print(f"  sales {r['YEARMONTH']}: t={r['tValue']:.2f}")
    for r in cust_res["trial_months"]:
        print(f"  cust  {r['YEARMONTH']}: t={r['tValue']:.2f}")
print("DONE")
