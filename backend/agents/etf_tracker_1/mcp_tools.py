import os
import sys
from typing import Dict, Any, List, Optional
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Container, MetricCard, ProgressBar,
    Alert, Grid, BarChart, LineChart, PieChart, PlotlyChart, List_,
    Collapsible, Divider, CodeBlock, Image, Tabs,
    FileDownload, FileUpload, Button, Input, ColorPicker,
    create_ui_response
)

def search_stocks_by_criteria(sector: Optional[str] = None, industry: Optional[str] = None, dividend_yield_min: Optional[float] = None, market_cap_min: Optional[float] = None, market_cap_max: Optional[float] = None, volatility_max: Optional[float] = None, limit: int = 20, **kwargs) -> Dict[str, Any]:
    """Search for stocks based on various financial criteria like sector, dividend yield, and market cap."""
    try:
        criteria_description = []
        if sector:
            criteria_description.append(f"Sector: {sector}")
        if industry:
            criteria_description.append(f"Industry: {industry}")
        if dividend_yield_min is not None:
            criteria_description.append(f"Min Dividend Yield: {dividend_yield_min}%")
        if market_cap_min is not None:
            criteria_description.append(f"Min Market Cap: ${market_cap_min:.2f}B")
        if market_cap_max is not None:
            criteria_description.append(f"Max Market Cap: ${market_cap_max:.2f}B")
        if volatility_max is not None:
            criteria_description.append(f"Max Volatility (beta): {volatility_max}")

        criteria_text = ", ".join(criteria_description) if criteria_description else "No specific criteria"

        simulated_stocks = [
            {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "industry": "Pharmaceuticals", "price": 155.30, "dividend_yield": 2.9, "market_cap": 375.2, "beta": 0.55},
            {"ticker": "PFE", "name": "Pfizer Inc.", "sector": "Healthcare", "industry": "Pharmaceuticals", "price": 27.45, "dividend_yield": 5.8, "market_cap": 155.1, "beta": 0.62},
            {"ticker": "MRK", "name": "Merck & Co.", "sector": "Healthcare", "industry": "Pharmaceuticals", "price": 128.75, "dividend_yield": 2.4, "market_cap": 326.5, "beta": 0.35},
            {"ticker": "ABBV", "name": "AbbVie Inc.", "sector": "Healthcare", "industry": "Biotechnology", "price": 165.20, "dividend_yield": 3.7, "market_cap": 292.3, "beta": 0.70},
            {"ticker": "AMGN", "name": "Amgen Inc.", "sector": "Healthcare", "industry": "Biotechnology", "price": 272.10, "dividend_yield": 3.1, "market_cap": 145.8, "beta": 0.65},
            {"ticker": "T", "name": "AT&T Inc.", "sector": "Communication Services", "industry": "Telecom", "price": 17.65, "dividend_yield": 6.3, "market_cap": 126.0, "beta": 0.78},
            {"ticker": "VZ", "name": "Verizon Communications", "sector": "Communication Services", "industry": "Telecom", "price": 40.22, "dividend_yield": 6.5, "market_cap": 169.5, "beta": 0.42},
            {"ticker": "KO", "name": "Coca-Cola Co", "sector": "Consumer Defensive", "industry": "Beverages", "price": 62.30, "dividend_yield": 3.0, "market_cap": 269.8, "beta": 0.58},
            {"ticker": "PG", "name": "Procter & Gamble", "sector": "Consumer Defensive", "industry": "Household Products", "price": 167.45, "dividend_yield": 2.4, "market_cap": 395.2, "beta": 0.40},
            {"ticker": "XOM", "name": "Exxon Mobil", "sector": "Energy", "industry": "Oil & Gas", "price": 118.75, "dividend_yield": 3.2, "market_cap": 475.6, "beta": 0.95},
        ]

        filtered_stocks = []
        for stock in simulated_stocks:
            if sector and stock["sector"].lower() != sector.lower():
                continue
            if industry and stock["industry"].lower() != industry.lower():
                continue
            if dividend_yield_min is not None and stock["dividend_yield"] < dividend_yield_min:
                continue
            if market_cap_min is not None and stock["market_cap"] < market_cap_min:
                continue
            if market_cap_max is not None and stock["market_cap"] > market_cap_max:
                continue
            if volatility_max is not None and stock["beta"] > volatility_max:
                continue
            filtered_stocks.append(stock)
            if len(filtered_stocks) >= limit:
                break

        rows = []
        for stock in filtered_stocks:
            rows.append([
                stock["ticker"],
                stock["name"],
                stock["sector"],
                stock["industry"],
                f"${stock['price']:.2f}",
                f"{stock['dividend_yield']}%",
                f"${stock['market_cap']:.1f}B",
                f"{stock['beta']:.2f}"
            ])

        components = [
            Card(
                title="Stock Search Results",
                content=[
                    Text(content=f"Criteria: {criteria_text}", variant="body"),
                    Text(content=f"Found {len(filtered_stocks)} stocks matching criteria.", variant="body"),
                    Divider(variant="solid"),
                    Table(
                        headers=["Ticker", "Name", "Sector", "Industry", "Price", "Div Yield", "Market Cap", "Beta"],
                        rows=rows,
                        variant="default"
                    ) if filtered_stocks else Alert(message="No stocks found matching the criteria.", variant="warning"),
                ]
            )
        ]

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {
                "criteria": {
                    "sector": sector,
                    "industry": industry,
                    "dividend_yield_min": dividend_yield_min,
                    "market_cap_min": market_cap_min,
                    "market_cap_max": market_cap_max,
                    "volatility_max": volatility_max,
                    "limit": limit
                },
                "stocks": filtered_stocks,
                "count": len(filtered_stocks)
            }
        }
    except Exception as e:
        return create_ui_response([
            Alert(message=f"Failed to search stocks: {str(e)}", variant="error")
        ])

def create_etf_from_description(description: str, number_of_stocks: int = 10, **kwargs) -> Dict[str, Any]:
    """Generate a proposed ETF portfolio based on a natural language description."""
    try:
        components = [
            Card(
                title="ETF Creation Request",
                content=[
                    Text(content=f"Description: {description}", variant="body"),
                    Text(content=f"Target number of stocks: {number_of_stocks}", variant="body"),
                    Divider(variant="solid"),
                    Alert(message="This tool simulates ETF creation. In a real implementation, this would use NLP to parse the description and query a financial database.", variant="info"),
                ]
            )
        ]

        if "healthcare" in description.lower() and "dividend" in description.lower():
            etf_name = "Healthcare Dividend Stability ETF"
            etf_ticker = "HDS"
            explanation = "The description emphasizes healthcare stocks with high dividends and stable values. Selected large-cap, established pharmaceutical and medical device companies with strong dividend histories and low beta (volatility)."
            simulated_constituents = [
                {"ticker": "JNJ", "name": "Johnson & Johnson", "weight": 0.20, "reason": "Diversified healthcare giant, dividend king, low volatility"},
                {"ticker": "PFE", "name": "Pfizer Inc.", "weight": 0.15, "reason": "High dividend yield, strong cash flow"},
                {"ticker": "MRK", "name": "Merck & Co.", "weight": 0.15, "reason": "Stable pharmaceuticals, consistent dividends"},
                {"ticker": "ABBV", "name": "AbbVie Inc.", "weight": 0.15, "reason": "High dividend, strong immunology portfolio"},
                {"ticker": "AMGN", "name": "Amgen Inc.", "weight": 0.10, "reason": "Biotech leader with growing dividend"},
                {"ticker": "MDT", "name": "Medtronic plc", "weight": 0.10, "reason": "Medical device leader, stable dividend payer"},
                {"ticker": "BMY", "name": "Bristol-Myers Squibb", "weight": 0.08, "reason": "Pharmaceuticals with high yield"},
                {"ticker": "GILD", "name": "Gilead Sciences", "weight": 0.07, "reason": "Biotech with solid dividend and value characteristics"},
            ]
        elif "technology" in description.lower() and "growth" in description.lower():
            etf_name = "Technology Growth Leaders ETF"
            etf_ticker = "TGL"
            explanation = "Focus on high-growth technology companies across software, semiconductors, and internet services."
            simulated_constituents = [
                {"ticker": "AAPL", "name": "Apple Inc.", "weight": 0.22, "reason": "Tech giant with strong ecosystem"},
                {"ticker": "MSFT", "name": "Microsoft Corporation", "weight": 0.20, "reason": "Cloud and software leader"},
                {"ticker": "NVDA", "name": "NVIDIA Corporation", "weight": 0.18, "reason": "AI and semiconductor dominance"},
                {"ticker": "GOOGL", "name": "Alphabet Inc.", "weight": 0.15, "reason": "Digital advertising and cloud growth"},
                {"ticker": "AMD", "name": "Advanced Micro Devices", "weight": 0.10, "reason": "High-growth semiconductor company"},
                {"ticker": "ADBE", "name": "Adobe Inc.", "weight": 0.08, "reason": "Creative software leader"},
                {"ticker": "CRM", "name": "Salesforce Inc.", "weight": 0.07, "reason": "CRM market leader"},
            ]
        elif "renewable" in description.lower() or "green" in description.lower():
            etf_name = "Renewable Energy Future ETF"
            etf_ticker = "REF"
            explanation = "Companies involved in renewable energy production, technology, and infrastructure."
            simulated_constituents = [
                {"ticker": "NEE", "name": "NextEra Energy", "weight": 0.25, "reason": "World's largest renewable energy producer"},
                {"ticker": "ENPH", "name": "Enphase Energy", "weight": 0.15, "reason": "Solar microinverter technology leader"},
                {"ticker": "FSLR", "name": "First Solar", "weight": 0.15, "reason": "Thin-film solar panel manufacturer"},
                {"ticker": "PLUG", "name": "Plug Power", "weight": 0.12, "reason": "Hydrogen fuel cell solutions"},
                {"ticker": "RUN", "name": "Sunrun Inc.", "weight": 0.10, "reason": "Residential solar installation leader"},
                {"ticker": "SEDG", "name": "SolarEdge Technologies", "weight": 0.10, "reason": "Solar inverter and optimizer systems"},
                {"ticker": "CWEN", "name": "Clearway Energy", "weight": 0.08, "reason": "Renewable energy project owner/operator"},
                {"ticker": "AY", "name": "Atlantica Sustainable Infrastructure", "weight": 0.05, "reason": "Sustainable infrastructure yieldco"},
            ]
        else:
            etf_name = "Custom Thematic ETF"
            etf_ticker = "CTE"
            explanation = "A diversified portfolio constructed based on the described theme."
            simulated_constituents = [
                {"ticker": "JNJ", "name": "Johnson & Johnson", "weight": 0.12, "reason": "Stable healthcare giant"},
                {"ticker": "PG", "name": "Procter & Gamble", "weight": 0.11, "reason": "Consumer defensive stability"},
                {"ticker": "XOM", "name": "Exxon Mobil", "weight": 0.11, "reason": "Energy sector representation"},
                {"ticker": "JPM", "name": "JPMorgan Chase", "weight": 0.10, "reason": "Financial services leader"},
                {"ticker": "V", "name": "Visa Inc.", "weight": 0.10, "reason": "Payment technology growth"},
                {"ticker": "WMT", "name": "Walmart Inc.", "weight": 0.09, "reason": "Consumer staples retailer"},
                {"ticker": "UNH", "name": "UnitedHealth Group", "weight": 0.09, "reason": "Healthcare services leader"},
                {"ticker": "HD", "name": "Home Depot", "weight": 0.08, "reason": "Home improvement retail"},
                {"ticker": "BAC", "name": "Bank of America", "weight": 0.07, "reason": "Diversified banking"},
                {"ticker": "MA", "name": "Mastercard Inc.", "weight": 0.07, "reason": "Global payments network"},
            ]

        if len(simulated_constituents) > number_of_stocks:
            simulated_constituents = simulated_constituents[:number_of_stocks]
            total_weight = sum(item["weight"] for item in simulated_constituents)
            for item in simulated_constituents:
                item["weight"] = round(item["weight"] / total_weight, 3)

        table_rows = []
        for stock in simulated_constituents:
            table_rows.append([
                stock["ticker"],
                stock["name"],
                f"{stock['weight']*100:.1f}%",
                stock["reason"]
            ])

        components.append(
            Card(
                title=f"Proposed ETF: {etf_name} ({etf_ticker})",
                content=[
                    Text(content=explanation, variant="body"),
                    Divider(variant="solid"),
                    Grid(
                        columns=2,
                        children=[
                            MetricCard(title="ETF Ticker", value=etf_ticker),
                            MetricCard(title="Number of Holdings", value=str(len(simulated_constituents))),
                        ]
                    ),
                    Table(
                        headers=["Ticker", "Name", "Weight", "Inclusion Reason"],
                        rows=table_rows,
                        variant="default"
                    ),
                    Divider(variant="solid"),
                    Text(content="Note: This is a simulated ETF proposal for illustrative purposes. Actual ETF creation requires regulatory approval and detailed financial analysis.", variant="caption"),
                ]
            )
        )

        chart_labels = [s["ticker"] for s in simulated_constituents]
        chart_data = [s["weight"] * 100 for s in simulated_constituents]

        components.append(
            Card(
                title="ETF Allocation Visualization",
                content=[
                    PieChart(
                        title="Portfolio Weight by Holding",
                        labels=chart_labels,
                        data=chart_data,
                        colors=["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#6366f1"]
                    )
                ]
            )
        )

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {
                "description": description,
                "etf_name": etf_name,
                "etf_ticker": etf_ticker,
                "explanation": explanation,
                "constituents": simulated_constituents,
                "total_holdings": len(simulated_constituents)
            }
        }
    except Exception as e:
        return create_ui_response([
            Alert(message=f"Failed to create ETF from description: {str(e)}", variant="error")
        ])

def analyze_etf_portfolio(tickers: List[str], weights: Optional[List[float]] = None, **kwargs) -> Dict[str, Any]:
    """Analyze a proposed ETF portfolio with metrics like sector breakdown and estimated performance."""
    try:
        if not tickers:
            return create_ui_response([
                Alert(message="Please provide at least one ticker to analyze.", variant="warning")
            ])

        if weights and len(weights) != len(tickers):
            return create_ui_response([
                Alert(message="Number of weights must match number of tickers.", variant="error")
            ])

        if not weights:
            weights = [1.0 / len(tickers)] * len(tickers)

        normalized_weights = [w / sum(weights) for w in weights]

        stock_db = {
            "JNJ": {"name": "Johnson & Johnson", "sector": "Healthcare", "industry": "Pharmaceuticals", "price": 155.30, "dividend_yield": 2.9, "beta": 0.55, "market_cap": 375.2},
            "PFE": {"name": "Pfizer Inc.", "sector": "Healthcare", "industry": "Pharmaceuticals", "price": 27.45, "dividend_yield": 5.8, "beta": 0.62, "market_cap": 155.1},
            "MRK": {"name": "Merck & Co.", "sector": "Healthcare", "industry": "Pharmaceuticals", "price": 128.75, "dividend_yield": 2.4, "beta": 0.35, "market_cap": 326.5},
            "ABBV": {"name": "AbbVie Inc.", "sector": "Healthcare", "industry": "Biotechnology", "price": 165.20, "dividend_yield": 3.7, "beta": 0.70, "market_cap": 292.3},
            "AMGN": {"name": "Amgen Inc.", "sector": "Healthcare", "industry": "Biotechnology", "price": 272.10, "dividend_yield": 3.1, "beta": 0.65, "market_cap": 145.8},
            "T": {"name": "AT&T Inc.", "sector": "Communication Services", "industry": "Telecom", "price": 17.65, "dividend_yield": 6.3, "beta": 0.78, "market_cap": 126.0},
            "VZ": {"name": "Verizon Communications", "sector": "Communication Services", "industry": "Telecom", "price": 40.22, "dividend_yield": 6.5, "beta": 0.42, "market_cap": 169.5},
            "KO": {"name": "Coca-Cola Co", "sector": "Consumer Defensive", "industry": "Beverages", "price": 62.30, "dividend_yield": 3.0, "beta": 0.58, "market_cap": 269.8},
            "PG": {"name": "Procter & Gamble", "sector": "Consumer Defensive", "industry": "Household Products", "price": 167.45, "dividend_yield": 2.4, "beta": 0.40, "market_cap": 395.2},
            "XOM": {"name": "Exxon Mobil", "sector": "Energy", "industry": "Oil & Gas", "price": 118.75, "dividend_yield": 3.2, "beta": 0.95, "market_cap": 475.6},
            "AAPL": {"name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics", "price": 189.25, "dividend_yield": 0.5, "beta": 1.20, "market_cap": 2900.0},
            "MSFT": {"name": "Microsoft Corporation", "sector": "Technology", "industry": "Software", "price": 425.52, "dividend_yield": 0.7, "beta": 0.90, "market_cap": 3160.0},
            "NVDA": {"name": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors", "price": 950.02, "dividend_yield": 0.02, "beta": 1.50, "market_cap": 2350.0},
            "JPM": {"name": "JPMorgan Chase", "sector": "Financial Services", "industry": "Banks", "price": 195.40, "dividend_yield": 2.3, "beta": 1.05, "market_cap": 570.3},
            "V": {"name": "Visa Inc.", "sector": "Financial Services", "industry": "Credit Services", "price": 275.80, "dividend_yield": 0.8, "beta": 0.95, "market_cap": 555.2},
        }

        portfolio_data = []
        sector_breakdown = {}
        total_dividend_yield = 0
        portfolio_beta = 0
        valid_tickers = []

        for i, ticker in enumerate(tickers):
            ticker_upper = ticker.upper()
            if ticker_upper in stock_db:
                stock_info = stock_db[ticker_upper]
                weight = normalized_weights[i]
                portfolio_data.append({
                    "ticker": ticker_upper,
                    "name": stock_info["name"],
                    "sector": stock_info["sector"],
                    "weight": weight,
                    "price": stock_info["price"],
                    "dividend_yield": stock_info["dividend_yield"],
                    "beta": stock_info["beta"],
                    "market_cap": stock_info["market_cap"]
                })
                valid_tickers.append(ticker_upper)

                sector = stock_info["sector"]
                sector_breakdown[sector] = sector_breakdown.get(sector, 0) + weight
                total_dividend_yield += weight * stock_info["dividend_yield"]
                portfolio_beta += weight * stock_info["beta"]
            else:
                portfolio_data.append({
                    "ticker": ticker_upper,
                    "name": "Unknown",
                    "sector": "Unknown",
                    "weight": normalized_weights[i],
                    "price": 0,
                    "dividend_yield": 0,
                    "beta": 1.0,
                    "market_cap": 0
                })

        if not valid_tickers:
            return create_ui_response([
                Alert(message="No valid tickers found in the database.", variant="error")
            ])

        table_rows = []
        for item in portfolio_data:
            table_rows.append([
                item["ticker"],
                item["name"],
                item["sector"],
                f"{item['weight']*100:.1f}%",
                f"${item['price']:.2f}" if item["price"] > 0 else "N/A",
                f"{item['dividend_yield']}%" if item["dividend_yield"] > 0 else "N/A",
                f"{item['beta']:.2f}"
            ])

        sector_chart_labels = list(sector_breakdown.keys())
        sector_chart_data = [sector_breakdown[s] * 100 for s in sector_chart_labels]

        components = [
            Card(
                title="ETF Portfolio Analysis",
                content=[
                    Text(content=f"Analyzing portfolio with {len(portfolio_data)} holdings", variant="body"),
                    Grid(
                        columns=4,
                        children=[
                            MetricCard(title="Estimated Dividend Yield", value=f"{total_dividend_yield:.2f}%"),
                            MetricCard(title="Portfolio Beta", value=f"{portfolio_beta:.2f}"),
                            MetricCard(title="High Volatility" if portfolio_beta > 1.1 else "Low Volatility" if portfolio_beta < 0.9 else "Market Volatility", value="High" if portfolio_beta > 1.1 else "Low" if portfolio_beta < 0.9 else "Market"),
                            MetricCard(title="Sectors", value=str(len(sector_breakdown))),
                        ]
                    ),
                    Divider(variant="solid"),
                    Table(
                        headers=["Ticker", "Name", "Sector", "Weight", "Price", "Div Yield", "Beta"],
                        rows=table_rows,
                        variant="default"
                    ),
                ]
            ),
            Card(
                title="Sector Allocation",
                content=[
                    PieChart(
                        title="Portfolio Weight by Sector",
                        labels=sector_chart_labels,
                        data=sector_chart_data,
                        colors=["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#84cc16"]
                    )
                ]
            )
        ]

        if len(valid_tickers) < len(tickers):
            components.insert(0, Alert(
                message=f"Warning: {len(tickers) - len(valid_tickers)} ticker(s) not found in database. Analysis based on {len(valid_tickers)} valid tickers.",
                variant="warning"
            ))

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {
                "tickers": tickers,
                "weights": normalized_weights,
                "portfolio_data": portfolio_data,
                "sector_breakdown": sector_breakdown,
                "estimated_dividend_yield": total_dividend_yield,
                "portfolio_beta": portfolio_beta,
                "valid_tickers": valid_tickers
            }
        }
    except Exception as e:
        return create_ui_response([
            Alert(message=f"Failed to analyze ETF portfolio: {str(e)}", variant="error")
        ])

TOOL_REGISTRY = {
    "search_stocks_by_criteria": {
        "function": search_stocks_by_criteria,
        "description": "Search for stocks based on sector, industry, dividend yield, market cap, and volatility criteria.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "The sector to filter by (e.g., Healthcare, Technology)"},
                "industry": {"type": "string", "description": "The specific industry to filter by (e.g., Pharmaceuticals, Software)"},
                "dividend_yield_min": {"type": "number", "description": "Minimum dividend yield percentage"},
                "market_cap_min": {"type": "number", "description": "Minimum market cap in billions of dollars"},
                "market_cap_max": {"type": "number", "description": "Maximum market cap in billions of dollars"},
                "volatility_max": {"type": "number", "description": "Maximum beta (volatility measure, typically <1 is less volatile than market)"},
                "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 20}
            },
            "required": []
        },
        "scope": "tools:read"
    },
    "create_etf_from_description": {
        "function": create_etf_from_description,
        "description": "Generate a proposed ETF portfolio based on a natural language description of the desired investment theme.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Natural language description of the desired ETF (e.g., 'healthcare stocks with high dividends and stable values')"},
                "number_of_stocks": {"type": "integer", "description": "Target number of stocks in the ETF", "default": 10}
            },
            "required": ["description"]
        },
        "scope": "tools:read"
    },
    "analyze_etf_portfolio": {
        "function": analyze_etf_portfolio,
        "description": "Analyze a proposed ETF portfolio with metrics like sector breakdown, estimated dividend yield, and volatility.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}, "description": "List of stock tickers in the portfolio"},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Optional weights for each ticker (must sum to any positive number)"}
            },
            "required": ["tickers"]
        },
        "scope": "tools:read"
    }
}