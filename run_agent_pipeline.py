# run_agent_pipeline.py
from agents_core import build_features, forecast_qty_used, optimize_inventory, summarize_plan

def run_agentic_planner(
    restaurant_id: str,
    start_date: str,
    end_date: str,
    menu_categories,
):
    """
    menu_categories example:
    [{"category": "Meat"}, {"category": "Vegetables"}, {"category": "Dairy"}, {"category": "Fish"}]
    """

    # DataAgent step
    features = build_features(restaurant_id, start_date, end_date, menu_categories)

    # ForecastAgent step
    forecast = forecast_qty_used(features)

    # OptimizerAgent step
    plan = optimize_inventory(forecast)

    # ReporterAgent step
    summary = summarize_plan(plan)

    return plan, summary


if __name__ == "__main__":
    menu = [
        {"category": "Meat"},
        {"category": "Vegetables"},
        {"category": "Dairy"},
        {"category": "Fish"},
        {"category": "Other"},
    ]

    plan_df, text_summary = run_agentic_planner(
        restaurant_id="R1",
        start_date="2026-03-14",
        end_date="2026-03-20",
        menu_categories=menu,
    )

    print(text_summary)
    print(plan_df.head())
