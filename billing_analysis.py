from typing import Dict, Any, List


def analyze_bill(customer_id: str) -> Dict[str, Any]:
    """
    Deterministic bill analysis engine.
    Analyzes itemized charges, detects unusual spikes, identifies major cost drivers,
    and performs neutral historical bill variance comparisons using authentic backend data.
    """
    from tools import get_bill
    from database import query_database

    cust_id = customer_id.strip().upper() if customer_id else "CUST001"

    # 1. Fetch Latest Bill via API / Tools
    bill = get_bill(cust_id)
    if isinstance(bill, str) or not bill:
        # Fallback to DB
        df = query_database("SELECT * FROM bills WHERE customer_id = ? ORDER BY billing_date DESC LIMIT 1", (cust_id,))
        if df.empty:
            return {
                "customer_id": cust_id,
                "error": f"No billing records found for customer {cust_id}."
            }
        bill = df.iloc[0].to_dict()

    bill_id = bill.get("bill_id", "N/A")
    billing_date = bill.get("billing_date", "")
    base_plan = float(bill.get("base_plan", 0.0))
    addon_charges = float(bill.get("addon_charges", 0.0))
    roaming_charges = float(bill.get("roaming_charges", 0.0))
    taxes = float(bill.get("taxes", 0.0))
    total_amount = float(bill.get("total_amount", 0.0))
    status = bill.get("status", "pending")

    # 2. Proportion & Percentage Contributions
    denominator = total_amount if total_amount > 0 else 1.0
    base_pct = round((base_plan / denominator) * 100, 1)
    addon_pct = round((addon_charges / denominator) * 100, 1)
    roaming_pct = round((roaming_charges / denominator) * 100, 1)
    tax_pct = round((taxes / denominator) * 100, 1)

    analysis_points: List[str] = []

    # Major charge contributor
    if base_plan >= (total_amount * 0.7):
        analysis_points.append(f"Most of the bill comes from the base plan (₹{base_plan:.2f}, {base_pct}% of total)")
    elif addon_charges > base_plan:
        analysis_points.append(f"Add-on services represent the largest cost component (₹{addon_charges:.2f}, {addon_pct}% of total)")

    # Roaming analysis
    if roaming_charges > 0:
        analysis_points.append(f"Roaming charge detected: ₹{roaming_charges:.2f} ({roaming_pct}% of total)")
    else:
        analysis_points.append("No roaming charges detected")

    # Add-on analysis
    if addon_charges > 0:
        analysis_points.append(f"Add-on charges detected: ₹{addon_charges:.2f} ({addon_pct}% of total)")
    else:
        analysis_points.append("No optional add-on pack charges detected")

    # Statutory taxes
    analysis_points.append(f"Statutory GST and regulatory taxes amount to ₹{taxes:.2f} ({tax_pct}%)")

    # Payment Status
    if status.lower() == "paid":
        analysis_points.append("Payment status: fully paid and settled")
    elif status.lower() == "overdue":
        analysis_points.append("Payment status: overdue — immediate payment advised")
    else:
        analysis_points.append(f"Payment status: {status}")

    # 3. Historical Bill Comparison
    historical_df = query_database(
        "SELECT * FROM bills WHERE customer_id = ? ORDER BY billing_date DESC",
        (cust_id,)
    )

    comparison = None
    if len(historical_df) > 1:
        prev_bill = historical_df.iloc[1].to_dict()
        prev_total = float(prev_bill.get("total_amount", 0.0))
        diff = round(total_amount - prev_total, 2)
        pct_change = round(((total_amount - prev_total) / prev_total) * 100, 1) if prev_total > 0 else 0.0

        if diff > 0 and pct_change >= 20.0:
            analysis_points.append(f"Higher than previous bill by ₹{diff:.2f} ({pct_change}% unusual increase)")
        elif diff > 0:
            analysis_points.append(f"Higher than previous bill by ₹{diff:.2f} (+{pct_change}%)")
        elif diff < 0:
            analysis_points.append(f"Lower than previous bill by ₹{abs(diff):.2f} ({pct_change}%)")
        else:
            analysis_points.append("Bill amount is identical to the previous billing cycle")

        comparison = {
            "previous_bill_id": prev_bill.get("bill_id"),
            "previous_billing_date": prev_bill.get("billing_date"),
            "previous_total": prev_total,
            "variance_amount": diff,
            "variance_percentage": pct_change,
        }

    return {
        "customer_id": cust_id,
        "bill_id": bill_id,
        "billing_date": billing_date,
        "total_amount": total_amount,
        "base_plan": base_plan,
        "addon_charges": addon_charges,
        "roaming_charges": roaming_charges,
        "taxes": taxes,
        "status": status,
        "breakdown_percentages": {
            "base_plan": base_pct,
            "addon_charges": addon_pct,
            "roaming_charges": roaming_pct,
            "taxes": tax_pct,
        },
        "analysis": analysis_points,
        "historical_comparison": comparison,
    }
