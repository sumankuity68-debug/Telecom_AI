from database import query_database


# ============================================================
# BUILD USER CONTEXT
# ============================================================

def build_user_context(customer_id):

    if not customer_id:

        return None


    # ========================================================
    # CUSTOMER PROFILE
    # ========================================================

    customer_df = query_database(
        """
        SELECT
            customer_id,
            name,
            phone,
            email,
            location,
            customer_type,
            account_status
        FROM customers
        WHERE customer_id = ?
        """,
        (customer_id,)
    )


    if customer_df.empty:

        return None


    customer = customer_df.iloc[0].to_dict()


    # ========================================================
    # CURRENT PLAN
    # ========================================================

    plan_df = query_database(
        """
        SELECT
            s.plan_id,
            s.start_date,
            s.expiry_date,
            s.status,
            p.plan_name,
            p.price,
            p.data_gb,
            p.calls,
            p.sms,
            p.technology
        FROM subscriptions s

        JOIN plans p
            ON s.plan_id = p.plan_id

        WHERE s.customer_id = ?

        ORDER BY s.start_date DESC

        LIMIT 1
        """,
        (customer_id,)
    )


    current_plan = {}

    if not plan_df.empty:

        current_plan = (
            plan_df.iloc[0].to_dict()
        )


    # ========================================================
    # RECENT USAGE
    # ========================================================

    usage_df = query_database(
        """
        SELECT
            COALESCE(
                SUM(data_used_gb),
                0
            ) AS data_used_gb,

            COALESCE(
                SUM(call_minutes),
                0
            ) AS call_minutes,

            COALESCE(
                SUM(sms_count),
                0
            ) AS sms_count

        FROM usage

        WHERE customer_id = ?

        AND date >= date(
            'now',
            '-7 day'
        )
        """,
        (customer_id,)
    )


    usage = {}

    if not usage_df.empty:

        usage = (
            usage_df.iloc[0].to_dict()
        )


    # ========================================================
    # LATEST BILL
    # ========================================================

    bill_df = query_database(
        """
        SELECT
            bill_id,
            billing_date,
            base_plan,
            addon_charges,
            roaming_charges,
            taxes,
            total_amount,
            status

        FROM bills

        WHERE customer_id = ?

        ORDER BY billing_date DESC

        LIMIT 1
        """,
        (customer_id,)
    )


    latest_bill = {}

    if not bill_df.empty:

        latest_bill = (
            bill_df.iloc[0].to_dict()
        )


    # ========================================================
    # OPEN TICKETS
    # ========================================================

    ticket_df = query_database(
        """
        SELECT
            COUNT(*) AS open_tickets

        FROM tickets

        WHERE customer_id = ?

        AND status IN (
            'open',
            'pending',
            'assigned'
        )
        """,
        (customer_id,)
    )


    open_tickets = 0

    if not ticket_df.empty:

        open_tickets = int(
            ticket_df.iloc[0]["open_tickets"]
        )


    # ========================================================
    # FINAL CONTEXT
    # ========================================================

    context = {

        "customer_id":
            customer.get(
                "customer_id"
            ),

        "name":
            customer.get(
                "name"
            ),

        "phone":
            customer.get(
                "phone"
            ),

        "email":
            customer.get(
                "email"
            ),

        "location":
            customer.get(
                "location"
            ),

        "customer_type":
            customer.get(
                "customer_type"
            ),

        "account_status":
            customer.get(
                "account_status"
            ),

        "current_plan":
            current_plan,

        "recent_usage":
            usage,

        "latest_bill":
            latest_bill,

        "open_tickets":
            open_tickets
    }


    return context


# ============================================================
# FORMAT CONTEXT FOR LLM
# ============================================================

def format_user_context(context):

    if not context:

        return (
            "No authenticated customer context is available."
        )


    plan = context.get(
        "current_plan",
        {}
    )

    usage = context.get(
        "recent_usage",
        {}
    )

    bill = context.get(
        "latest_bill",
        {}
    )


    return f"""
AUTHENTICATED CUSTOMER CONTEXT

Customer ID:
{context.get("customer_id", "Unknown")}

Customer name:
{context.get("name", "Unknown")}

Location:
{context.get("location", "Unknown")}

Account status:
{context.get("account_status", "Unknown")}

Current plan:
{plan.get("plan_name", "Unknown")}

Plan technology:
{plan.get("technology", "Unknown")}

Plan data allowance:
{plan.get("data_gb", "Unknown")} GB

Plan expiry:
{plan.get("expiry_date", "Unknown")}

Recent 7-day data usage:
{usage.get("data_used_gb", 0)} GB

Recent 7-day call minutes:
{usage.get("call_minutes", 0)}

Recent 7-day SMS:
{usage.get("sms_count", 0)}

Latest bill:
₹{bill.get("total_amount", "Unknown")}

Latest bill status:
{bill.get("status", "Unknown")}

Open support tickets:
{context.get("open_tickets", 0)}

IMPORTANT:
This context belongs to the authenticated user.
Do not ask the user for their customer ID unless the
system context is unavailable.
Do not reveal internal customer IDs unless necessary.
"""