"""
GDELT Environmental Conflict Media Coverage Pipeline
=====================================================

For: "Media Representation and Environmental Conflict: Narratives, Power,
and Public Engagement in the Anthropocene"

This script has THREE parts you can run independently:

  PART 1 — Doc API quick test (no setup needed, works immediately)
           Good for: sanity-checking keywords, pulling recent example
           headlines to quote/discuss in the text.

  PART 2 — BigQuery GKG pull (needs a free Google Cloud account)
           Good for: multi-year time series, theme frequency, tone —
           the actual data behind your charts.

  PART 3 — Visualization
           Turns the BigQuery output into the charts suggested earlier:
           coverage-volume-over-time line chart, small multiples,
           and a theme-frequency bar chart.

------------------------------------------------------------------------
SETUP FOR PART 2 (BigQuery) — do this once, outside this script:
------------------------------------------------------------------------
1. Go to https://console.cloud.google.com and create a project
   (free tier is enough — GDELT's public dataset queries fall well
   within the 1TB/month free BigQuery quota for most chapter-scale work).
2. Enable the "BigQuery API" for that project (Console > APIs & Services).
3. Install the Google Cloud CLI, then run in your terminal:
       gcloud auth application-default login
   This lets the script authenticate without a hardcoded key.
4. Note your project ID (shown on the Cloud Console dashboard) and paste
   it into GCP_PROJECT_ID below.

If you don't have this set up yet, just run PART 1 for now — it needs
nothing but `pip install requests pandas`.
------------------------------------------------------------------------
"""

import time
import requests
import pandas as pd

# =========================================================================
# PART 1 — GDELT Doc API (recent articles, last ~3 months only)
# =========================================================================

DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# General environmental-conflict keyword groups.
# Each is queried separately so you can compare volumes across categories.
ENV_CONFLICT_QUERIES = {
    "drought": '"drought" OR "water scarcity" OR "water crisis"',
    "wildfire": '"wildfire" OR "forest fire" OR "bushfire"',
    "mining_conflict": '"mining conflict" OR "mine protest" OR "extractive industry"',
    "conservation_dispute": '"conservation dispute" OR "protected area conflict" OR "land rights"',
    "illegal_logging": '"illegal logging" OR "deforestation crime"',
    "wildlife_trade": '"wildlife trafficking" OR "poaching" OR "illegal wildlife trade"',
    "pollution": '"industrial pollution" OR "oil spill" OR "toxic waste"',
}


def query_doc_api(query: str, max_records: int = 50, lang: str = "eng") -> pd.DataFrame:
    """
    Query the GDELT Doc 2.0 API for a list of matching recent articles.
    Only searches roughly the last 3 months of coverage.
    """
    params = {
        "query": f"({query}) sourcelang:{lang}",
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records,
        "sort": "datedesc",
    }
    r = requests.get(DOC_API_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data.get("articles", []))
    if not df.empty:
        df["seendate"] = pd.to_datetime(df["seendate"], format="%Y%m%dT%H%M%SZ", errors="coerce")
    return df


def run_part1_doc_api_test():
    print("=== PART 1: Doc API test ===")
    all_results = []
    for label, query in ENV_CONFLICT_QUERIES.items():
        try:
            df = query_doc_api(query, max_records=25)
            df["category"] = label
            all_results.append(df)
            print(f"  {label:22s} -> {len(df)} articles fetched")
        except requests.exceptions.HTTPError as e:
            print(f"  {label:22s} -> request failed ({e}). GDELT may be rate-limiting; wait and retry.")
        time.sleep(2)  # be polite to the API, avoid 429s

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined.to_csv("gdelt_doc_api_sample.csv", index=False)
        print(f"\nSaved {len(combined)} total articles to gdelt_doc_api_sample.csv")
        return combined
    else:
        print("\nNo results retrieved — check network access or try again later.")
        return pd.DataFrame()


# =========================================================================
# PART 2 — BigQuery GKG pull (multi-year historical data)
# =========================================================================

GCP_PROJECT_ID = "YOUR-GCP-PROJECT-ID-HERE"  # <-- replace with your project ID

# GDELT GKG theme tags relevant to each category.
# Full theme list: http://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf
GKG_THEMES = {
    "drought": ["NATURAL_DISASTER_DROUGHT", "WATER_SECURITY"],
    "wildfire": ["NATURAL_DISASTER_WILDFIRE"],
    "mining_conflict": ["ENV_MINING", "MINING"],
    "conservation_dispute": ["ENV_PROTECTEDAREAS", "TAX_FNCACT_CONSERVATIONIST"],
    "illegal_logging": ["CRIME_ILLEGAL_LOGGING", "ENV_DEFORESTATION"],
    "wildlife_trade": ["ENV_POACHING", "ENV_TRAFFICKING"],
    "pollution": ["ENV_POLLUTION", "SOC_POINTSOFINTEREST_TOXICWASTE"],
}


def run_part2_bigquery_pull(start_date="2019-01-01", end_date="2024-12-31"):
    """
    Pulls monthly article counts and average tone per category from the
    GDELT GKG BigQuery table. Requires GCP setup (see docstring above).
    """
    from google.cloud import bigquery  # imported here so Part 1 works without this installed

    print("=== PART 2: BigQuery GKG pull ===")
    client = bigquery.Client(project=GCP_PROJECT_ID)

    start_int = start_date.replace("-", "")
    end_int = end_date.replace("-", "")

    all_rows = []
    for category, themes in GKG_THEMES.items():
        theme_filter = " OR ".join([f"V2Themes LIKE '%{t}%'" for t in themes])
        query = f"""
            SELECT
              CAST(SUBSTR(CAST(DATE AS STRING), 1, 6) AS INT64) AS year_month,
              COUNT(*) AS article_count,
              AVG(SAFE_CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64)) AS avg_tone
            FROM `gdelt-bq.gdeltv2.gkg`
            WHERE _PARTITIONTIME BETWEEN TIMESTAMP('{start_date}') AND TIMESTAMP('{end_date}')
              AND ({theme_filter})
            GROUP BY year_month
            ORDER BY year_month
        """
        print(f"  Querying category: {category} ...")
        df = client.query(query).to_dataframe()
        df["category"] = category
        all_rows.append(df)

    combined = pd.concat(all_rows, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["year_month"].astype(str), format="%Y%m")
    combined.to_csv("gdelt_gkg_monthly.csv", index=False)
    print(f"\nSaved aggregated monthly data to gdelt_gkg_monthly.csv")
    return combined


# =========================================================================
# PART 3 — Visualization
# =========================================================================

def run_part3_visualize(df: pd.DataFrame, date_col="date", value_col="article_count"):
    """
    Builds:
      (a) a single line chart of coverage volume over time, one line per category
      (b) small multiples (one panel per category)
      (c) a bar chart of total coverage by category
    Expects a DataFrame with columns: date_col, value_col, 'category'
    """
    import matplotlib.pyplot as plt

    if df.empty:
        print("No data to visualize.")
        return

    # (a) Combined line chart
    fig, ax = plt.subplots(figsize=(10, 6))
    for category, group in df.groupby("category"):
        ax.plot(group[date_col], group[value_col], marker="o", markersize=3, label=category)
    ax.set_title("Environmental Conflict Coverage Volume Over Time")
    ax.set_xlabel("Date")
    ax.set_ylabel("Article count")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig("chart_coverage_over_time.png", dpi=200)
    print("Saved chart_coverage_over_time.png")

    # (b) Small multiples
    categories = df["category"].unique()
    n = len(categories)
    cols = 2
    rows = (n + 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(12, 3 * rows), sharex=True)
    axes = axes.flatten()
    for i, category in enumerate(categories):
        group = df[df["category"] == category]
        axes[i].plot(group[date_col], group[value_col], color="tab:green")
        axes[i].set_title(category, fontsize=10)
    for j in range(i + 1, len(axes)):
        fig.delaxes(axes[j])
    fig.suptitle("Coverage Volume by Category (Small Multiples)", y=1.02)
    fig.tight_layout()
    fig.savefig("chart_small_multiples.png", dpi=200, bbox_inches="tight")
    print("Saved chart_small_multiples.png")

    # (c) Total coverage bar chart
    totals = df.groupby("category")[value_col].sum().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    totals.plot(kind="barh", ax=ax, color="tab:blue")
    ax.set_title("Total Coverage by Environmental Conflict Category")
    ax.set_xlabel("Total article count")
    fig.tight_layout()
    fig.savefig("chart_total_by_category.png", dpi=200)
    print("Saved chart_total_by_category.png")


# =========================================================================
# Run
# =========================================================================

if __name__ == "__main__":
    # Step 1: always safe to run, no setup needed
    sample_df = run_part1_doc_api_test()

    # Step 2: uncomment once your GCP project is set up
    # gkg_df = run_part2_bigquery_pull(start_date="2019-01-01", end_date="2024-12-31")
    # run_part3_visualize(gkg_df)
