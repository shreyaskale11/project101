import streamlit as st
import requests
import pandas as pd
import os

# Load API URL from Streamlit secrets or environment variable
API_URL = st.secrets.get("API_URL", os.getenv("API_URL", None))


def fetch_research(query: str, api_url: str) -> dict:
    """
    Send a POST request to the Investment Research API and return the JSON response.
    """
    payload = {"query": query}
    response = requests.post(api_url, json=payload)
    response.raise_for_status()
    return response.json()


def main():
    st.set_page_config(page_title="Investment Research Screener", layout="wide")
    st.title("📈 Investment Research Screener")
    st.markdown(
        "Enter a query to run through the investment research pipeline and get structured results."
    )

    # Ensure API URL is configured
    if not API_URL:
        st.error(
            "API_URL is not configured. Please add it to Streamlit secrets or set the API_URL environment variable."
        )
        st.stop()

    # Example queries for quick start (SQL-like syntax)
    example_queries = {
        "Select an example...": "",
        "Long-term Growth": (
            "Show me companies that have grown revenue and profits by more than 10% each year over the past five years, "
            "with return on equity above 15% and an earnings yield over 7%."
        ),
        "High Dividend Yield": (
            "Find companies offering a dividend yield above 4%, a payout ratio below 60%, "
            "and debt-to-equity under 0.5."
        ),
        "Value Screening": (
            "Identify undervalued stocks trading at a price-to-earnings ratio under 15, "
            "price-to-book under 1.5, and return on equity above 12%."
        ),
        "Momentum": (
            "List stocks that have gained more than 20% in price over the last six months "
            "and over 40% in the last year."
        ),
        "GARP": (
            "Show me stocks with a PEG ratio below 1 and earnings per share growth over 15% in the past five years."
        ),
    }
    selected_example = st.selectbox("Example Queries", list(example_queries.keys()))
    default_query = example_queries.get(selected_example, "")

    # Popular screening themes (descriptive)
    popular_investing_themes = {
        "Low on 10-year Avg Earnings": "Graham liked to value stocks based on average earnings of multiple years. This screen uses 10-year average earnings.",
        "Capacity Expansion": "Companies where fixed assets have doubled over the last 3 years or increased by over 50% in the last year.",
        "Debt Reduction": "Companies reducing net debt year-over-year.",
        "New 52-week Highs": "Companies trading near their 52-week high.",
        "Growth without Dilution": "Companies with less than 10% share dilution over the past 10 years.",
        "FII Buying": "Stocks with significant recent Foreign Institutional Investor purchases.",
    }
    popular_formulas = {
        "Piotroski F-Score": "Piotroski score of 9 reflecting profitability, leverage, and operating efficiency.",
        "Magic Formula": "Rank stocks by earnings yield and ROIC per Joel Greenblatt's Magic Formula.",
        "Coffee Can Portfolio": "Based on the book by Saurabh Mukherjee: focus on high-quality compounding businesses.",
    }
    price_volume_screens = {
        "Darvas Scan": "Within 10% of 52-week high, within 100% of 52-week low, volume > 100k & price > 10.",
        "Golden Crossover": "50-day MA crosses above 200-day MA.",
        "Bearish Crossover": "50-day MA crosses below 200-day MA.",
        "RSI Oversold": "Stocks with 14-day RSI < 30.",
    }
    quarterly_screens = {
        "The Bull Cartel": "Strong latest quarterly growth; set alerts for new results.",
        "Quarterly Growers": "Sequential QoQ growth: Q0 > Q1 > Q2 > Q3.",
        "Best of Latest Quarter": "Top performers in the most recent quarter.",
    }
    valuation_screens = {
        "Highest Dividend Yield": "Stocks with consistently high dividend yields.",
        "Loss to Profit Turnaround": "Companies that moved from quarterly losses to profits.",
        "High FCF Yield": "Strong free cash flow yield and growth.",
    }

    # Display popular themes
    with st.expander("📊 Popular Investing Themes", expanded=False):
        for name, desc in popular_investing_themes.items():
            st.markdown(f"**{name}**: {desc}")
    with st.expander("📈 Popular Formulas", expanded=False):
        for name, desc in popular_formulas.items():
            st.markdown(f"**{name}**: {desc}")
    with st.expander("💹 Price/Volume Screens", expanded=False):
        for name, desc in price_volume_screens.items():
            st.markdown(f"**{name}**: {desc}")
    with st.expander("📅 Quarterly Results Screens", expanded=False):
        for name, desc in quarterly_screens.items():
            st.markdown(f"**{name}**: {desc}")
    with st.expander("💰 Valuation Screens", expanded=False):
        for name, desc in valuation_screens.items():
            st.markdown(f"**{name}**: {desc}")

    # Query input
    query_input = st.text_area("Your Screener Query", value=default_query, height=100)

    # Run button
    if st.button("Run Screener"):
        if not query_input.strip():
            st.error("Please enter a non-empty query.")
        else:
            with st.spinner("Fetching results..."):
                try:
                    result = fetch_research(query_input, API_URL)
                    st.success("✅ Results fetched successfully!")
                    if result.get("message"): st.info(result["message"])
                    data = result.get("data", {})
                    analysis = data.get("analysis", {})
                    thought = analysis.get("thought")
                    objectives = analysis.get("objectives", [])
                    if thought:
                        st.subheader("💭 Thought")
                        st.write(thought)
                    if objectives:
                        st.subheader("🎯 Objectives")
                        for obj in objectives: st.markdown(f"- {obj}")
                    query_str = data.get("query")
                    if query_str:
                        st.subheader("🔍 Generated Query")
                        st.code(query_str, language="sql")
                    st.subheader("📦 Raw JSON Response")
                    st.json(result)
                except requests.exceptions.HTTPError as http_err:
                    st.error(f"HTTP error occurred: {http_err}")
                except Exception as err:
                    st.error(f"An unexpected error occurred: {err}")


if __name__ == "__main__":
    main()
