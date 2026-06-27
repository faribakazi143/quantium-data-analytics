"""
Quantium Virtual Internship - Task 1
Data preparation and customer analytics (Python implementation)
"""
import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os, json

plt.rcParams.update({
    "figure.dpi": 130,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
})
OUT = "figs_t1"
os.makedirs(OUT, exist_ok=True)
PREMIUM_COLORS = {"Budget": "#2e86ab", "Mainstream": "#d1495b", "Premium": "#edae49"}

# ----------------------------------------------------------------------
# 1. Loaded the data
# ----------------------------------------------------------------------
txn = pd.read_excel("QVI_transaction_data.xlsx")
beh = pd.read_csv("QVI_purchase_behaviour.csv")
audit = {"txn_rows_raw": len(txn), "beh_rows": len(beh)}

# ----------------------------------------------------------------------
# 2. Fixed data formats - DATE came in as an Excel serial integer
# ----------------------------------------------------------------------
txn["DATE"] = pd.to_datetime(txn["DATE"], unit="D", origin="1899-12-30")
audit["date_min"] = str(txn["DATE"].min().date())
audit["date_max"] = str(txn["DATE"].max().date())

# ----------------------------------------------------------------------
# 3. Removed non-chip items (salsa)
# ----------------------------------------------------------------------
is_salsa = txn["PROD_NAME"].str.contains("salsa", case=False)
audit["salsa_rows_removed"] = int(is_salsa.sum())
txn = txn[~is_salsa].copy()

# ----------------------------------------------------------------------
# 4. Checked outliers on PROD_QTY (one card bought 200 packs twice)
# ----------------------------------------------------------------------
big = txn[txn["PROD_QTY"] >= 200]
outlier_cards = big["LYLTY_CARD_NBR"].unique().tolist()
audit["outlier_cards"] = outlier_cards
txn = txn[~txn["LYLTY_CARD_NBR"].isin(outlier_cards)].copy()
audit["txn_rows_clean"] = len(txn)

# ----------------------------------------------------------------------
# 5. Derived features: PACK_SIZE and BRAND from PROD_NAME
# ----------------------------------------------------------------------
txn["PACK_SIZE"] = txn["PROD_NAME"].str.extract(r"(\d+)\s*[gG]").astype(float)
txn["BRAND"] = txn["PROD_NAME"].str.strip().str.split().str[0].str.upper()
brand_fix = {
    "RED": "RRD", "SNBTS": "SUNBITES", "INFZNS": "INFUZIONS", "WW": "WOOLWORTHS",
    "SMITH": "SMITHS", "NCC": "NATURAL", "DORITO": "DORITOS", "GRAIN": "GRNWVES",
}
txn["BRAND"] = txn["BRAND"].replace(brand_fix)
audit["n_brands"] = int(txn["BRAND"].nunique())

# ----------------------------------------------------------------------
# 6. Merged with customer behaviour
# ----------------------------------------------------------------------
df = txn.merge(beh, on="LYLTY_CARD_NBR", how="left")
audit["merged_rows"] = len(df)
audit["missing_after_merge"] = int(df["LIFESTAGE"].isna().sum())

# ----------------------------------------------------------------------
# 7. Built segment metrics
# ----------------------------------------------------------------------
seg = df.groupby(["LIFESTAGE", "PREMIUM_CUSTOMER"])
segment_summary = seg.agg(
    totalSales=("TOT_SALES", "sum"),
    nCustomers=("LYLTY_CARD_NBR", "nunique"),
    nUnits=("PROD_QTY", "sum"),
    nTxn=("TXN_ID", "nunique"),
).reset_index()
segment_summary["unitsPerCust"] = segment_summary["nUnits"] / segment_summary["nCustomers"]
segment_summary["avgPricePerUnit"] = segment_summary["totalSales"] / segment_summary["nUnits"]

LIFESTAGE_ORDER = ["NEW FAMILIES", "YOUNG SINGLES/COUPLES", "YOUNG FAMILIES",
                   "MIDAGE SINGLES/COUPLES", "OLDER FAMILIES", "OLDER SINGLES/COUPLES",
                   "RETIREES"]

def grouped_bar(metric, ylabel, title, fname, money=False, price=False):
    piv = segment_summary.pivot(index="LIFESTAGE", columns="PREMIUM_CUSTOMER", values=metric)
    piv = piv.reindex(LIFESTAGE_ORDER)
    fig, ax = plt.subplots(figsize=(9.2, 4.3))
    x = np.arange(len(piv.index)); w = 0.26
    for i, prem in enumerate(["Budget", "Mainstream", "Premium"]):
        ax.bar(x + (i - 1) * w, piv[prem], w, label=prem, color=PREMIUM_COLORS[prem])
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace(" ", "\n") for s in piv.index], fontsize=8)
    ax.set_ylabel(ylabel); ax.set_title(title, pad=10)
    ax.set_ylim(0, np.nanmax(piv.values) * 1.12)
    ax.legend(frameon=False, fontsize=8.5, title="Premium segment",
              loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    if money:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    if price:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.1f}"))
    fig.tight_layout(); fig.savefig(f"{OUT}/{fname}", bbox_inches="tight"); plt.close(fig)

grouped_bar("totalSales", "Total sales", "Total chip sales by customer segment",
            "sales_by_segment.png", money=True)
grouped_bar("nCustomers", "Number of customers", "Customer count by segment",
            "customers_by_segment.png")
grouped_bar("unitsPerCust", "Units per customer", "Average units per customer by segment",
            "units_by_segment.png")
grouped_bar("avgPricePerUnit", "Avg price per unit ($)", "Average price per unit by segment",
            "price_by_segment.png", price=True)

# ----------------------------------------------------------------------
# 8. Tested significance: mainstream vs non-mainstream young/midage singles & couples
# ----------------------------------------------------------------------
from scipy import stats
target_life = ["YOUNG SINGLES/COUPLES", "MIDAGE SINGLES/COUPLES"]
df["pricePerUnit"] = df["TOT_SALES"] / df["PROD_QTY"]
main = df[(df.LIFESTAGE.isin(target_life)) & (df.PREMIUM_CUSTOMER == "Mainstream")]["pricePerUnit"]
other = df[(df.LIFESTAGE.isin(target_life)) & (df.PREMIUM_CUSTOMER != "Mainstream")]["pricePerUnit"]
tstat, pval = stats.ttest_ind(main, other, equal_var=False)
audit["ttest_price"] = {"t": round(float(tstat), 2), "p": float(pval),
                        "main_mean": round(float(main.mean()), 3),
                        "other_mean": round(float(other.mean()), 3)}

# ----------------------------------------------------------------------
# 9. Ranked top brands and pack sizes
# ----------------------------------------------------------------------
brand_sales = df.groupby("BRAND")["TOT_SALES"].sum().sort_values(ascending=False).head(10)
fig, ax = plt.subplots(figsize=(8, 4))
cmap = plt.cm.viridis(np.linspace(0.15, 0.9, len(brand_sales)))
ax.barh(brand_sales.index[::-1], brand_sales.values[::-1], color=cmap)
ax.set_xlabel("Total sales"); ax.set_title("Top 10 chip brands by total sales")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
fig.tight_layout(); fig.savefig(f"{OUT}/top_brands.png", bbox_inches="tight"); plt.close(fig)
audit["top_brand"] = brand_sales.index[0]

pack_units = df.groupby("PACK_SIZE")["PROD_QTY"].sum().sort_index()
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.bar(pack_units.index.astype(int).astype(str), pack_units.values, color="#2e86ab", width=0.7)
ax.set_xlabel("Pack size (g)"); ax.set_ylabel("Units sold"); ax.set_title("Units sold by pack size")
ax.tick_params(axis="x", labelrotation=45, labelsize=7.5)
fig.tight_layout(); fig.savefig(f"{OUT}/pack_size.png", bbox_inches="tight"); plt.close(fig)
audit["top_pack_size"] = int(pack_units.idxmax())

df.to_csv("QVI_data.csv", index=False)
print(json.dumps(audit, indent=2, default=str))
print("DONE")
