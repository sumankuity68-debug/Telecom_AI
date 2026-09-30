from typing import List, Optional, Dict, Any


def recommend_plans(
    customer_id: str,
    preferred_technology: Optional[str] = None,
    max_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Intelligent telecom plan recommendation engine.
    Analyzes actual consumption history, current tariff, and customer profile
    to deterministically recommend best-fit plans with financial impact analysis.
    """
    from tools import (
        get_customer_profile,
        get_current_plan,
        get_usage,
        get_bill,
        search_plans,
    )

    cust_id = customer_id.strip().upper() if customer_id else "CUST001"

    # 1. Customer Profile
    profile = get_customer_profile(cust_id)
    customer_name = profile.get("name", "Customer") if isinstance(profile, dict) else "Customer"

    # 2. Current Subscription
    curr_plan = get_current_plan(cust_id)
    if isinstance(curr_plan, str) or not curr_plan:
        curr_plan = {
            "plan_id": "UNKNOWN",
            "plan_name": "Standard Tariff",
            "price": 399.0,
            "validity_days": 28,
            "data_gb": 84.0,
            "technology": "5G",
            "calls": "unlimited",
            "sms": 100,
        }

    curr_price = float(curr_plan.get("price", 399.0))
    curr_validity = max(int(curr_plan.get("validity_days", 28)), 1)
    curr_data = float(curr_plan.get("data_gb", 84.0))
    curr_tech = curr_plan.get("technology", "5G")
    curr_monthly_cost = round((curr_price / curr_validity) * 30, 2)

    # 3. Usage Analytics
    usage_records = get_usage(cust_id)
    avg_daily_data = 2.0
    total_data_used = 0.0
    avg_call_mins = 20
    avg_sms = 5

    if isinstance(usage_records, list) and len(usage_records) > 0:
        data_points = [float(r.get("data_used_gb", 0.0)) for r in usage_records]
        call_points = [int(r.get("call_minutes", 0)) for r in usage_records]
        sms_points = [int(r.get("sms_count", 0)) for r in usage_records]

        total_data_used = round(sum(data_points), 2)
        avg_daily_data = round(total_data_used / len(data_points), 2)
        avg_call_mins = int(sum(call_points) / len(call_points))
        avg_sms = int(sum(sms_points) / len(sms_points))

    projected_monthly_data = round(avg_daily_data * 30, 2)
    daily_allowance = round(curr_data / curr_validity, 2)
    is_heavy_data_user = avg_daily_data > 5.0
    is_overutilizing = avg_daily_data > daily_allowance
    is_underutilizing = (avg_daily_data * curr_validity) < (curr_data * 0.4)

    # 4. Available Plans
    all_plans = search_plans()
    if isinstance(all_plans, str) or not all_plans:
        from database import query_database
        all_plans = query_database("SELECT * FROM plans").to_dict(orient="records")

    target_tech = preferred_technology or curr_tech
    recommendations = []

    for p in all_plans:
        p_id = p.get("plan_id")
        p_name = p.get("plan_name")
        p_price = float(p.get("price", 0.0))
        p_validity = max(int(p.get("validity_days", 28)), 1)
        p_data = float(p.get("data_gb", 0.0))
        p_tech = p.get("technology", "5G")

        # Skip current identical plan
        if p_id == curr_plan.get("plan_id"):
            continue

        # Budget constraint filter if provided
        if max_budget is not None and p_price > max_budget:
            continue

        p_monthly_cost = round((p_price / p_validity) * 30, 2)
        diff = round(p_monthly_cost - curr_monthly_cost, 2)

        # Match logic based on real usage patterns
        # Case A: Heavy 5G consumer exceeding current data allowance
        if is_heavy_data_user and p_tech.upper() == "5G" and p_data >= 250:
            if p_data >= 900:
                reason = (
                    f"You consume ~{avg_daily_data} GB/day ({projected_monthly_data} GB/mo). "
                    f"Unlimited 5G eliminates all daily FUP caps with superior long-term value over {p_validity} days."
                )
            else:
                reason = (
                    f"Your active daily usage ({avg_daily_data} GB/day) exceeds your current quota ({daily_allowance} GB/day). "
                    f"{p_name} gives you {p_data} GB over {p_validity} days to avoid speed throttling."
                )
            recommendations.append({
                "plan_id": p_id,
                "plan_name": p_name,
                "price": p_price,
                "validity_days": p_validity,
                "data_gb": p_data,
                "technology": p_tech,
                "reason": reason,
                "estimated_monthly_difference": diff,
                "fit_type": "Performance Upgrade"
            })

        # Case B: Balanced mid-tier value option
        elif is_overutilizing and p_data > curr_data and p_monthly_cost <= curr_monthly_cost * 1.3:
            reason = (
                f"Provides higher data quota ({p_data} GB vs {curr_data} GB) "
                f"at a very cost-effective monthly rate difference of ₹{abs(diff):.2f}/mo."
            )
            recommendations.append({
                "plan_id": p_id,
                "plan_name": p_name,
                "price": p_price,
                "validity_days": p_validity,
                "data_gb": p_data,
                "technology": p_tech,
                "reason": reason,
                "estimated_monthly_difference": diff,
                "fit_type": "Recommended Value"
            })

        # Case C: Cost-saving optimization for light users
        elif is_underutilizing and p_price < curr_price and p_data >= projected_monthly_data:
            reason = (
                f"Your historical usage ({projected_monthly_data} GB/mo) fits comfortably within this plan's {p_data} GB quota. "
                f"Saves ₹{abs(diff):.2f} per month without sacrificing connectivity."
            )
            recommendations.append({
                "plan_id": p_id,
                "plan_name": p_name,
                "price": p_price,
                "validity_days": p_validity,
                "data_gb": p_data,
                "technology": p_tech,
                "reason": reason,
                "estimated_monthly_difference": diff,
                "fit_type": "Cost Optimization"
            })

    # If no specific rule matched, offer top alternative plans
    if not recommendations:
        for p in all_plans[:2]:
            if p.get("plan_id") != curr_plan.get("plan_id"):
                p_validity = max(int(p.get("validity_days", 28)), 1)
                p_price = float(p.get("price", 0.0))
                p_monthly_cost = round((p_price / p_validity) * 30, 2)
                recommendations.append({
                    "plan_id": p.get("plan_id"),
                    "plan_name": p.get("plan_name"),
                    "price": p_price,
                    "validity_days": p_validity,
                    "data_gb": float(p.get("data_gb", 0.0)),
                    "technology": p.get("technology", "5G"),
                    "reason": f"Popular {p.get('technology')} tariff option offering {p.get('data_gb')} GB over {p_validity} days.",
                    "estimated_monthly_difference": round(p_monthly_cost - curr_monthly_cost, 2),
                    "fit_type": "Alternative Option"
                })

    return {
        "customer_id": cust_id,
        "customer_name": customer_name,
        "current_plan": {
            "plan_id": curr_plan.get("plan_id"),
            "plan_name": curr_plan.get("plan_name"),
            "price": curr_price,
            "validity_days": curr_validity,
            "data_gb": curr_data,
            "technology": curr_tech,
            "normalized_monthly_cost": curr_monthly_cost,
        },
        "usage_summary": {
            "recorded_days": len(usage_records) if isinstance(usage_records, list) else 0,
            "total_data_used_gb": total_data_used,
            "avg_daily_data_gb": avg_daily_data,
            "projected_monthly_data_gb": projected_monthly_data,
            "daily_allowance_gb": daily_allowance,
            "avg_call_minutes": avg_call_mins,
        },
        "recommendations": recommendations,
    }
