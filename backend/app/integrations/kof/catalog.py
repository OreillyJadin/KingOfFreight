from dataclasses import dataclass


@dataclass(frozen=True)
class ListDefinition:
    key: str
    label: str
    module: str
    filename: str


MASTER_LIST = ListDefinition(
    "master_record_sheet",
    "Master Record Sheet",
    "my_dispatch",
    "Master_Record_Sheet_list.php",
)

STAGE_LISTS = (
    (
        "awaiting_pickup",
        ListDefinition(
            "ready_for_pickup",
            "Ready for Pickup Confirmation",
            "my_dispatch",
            "Ready_for_Pickup_Confirmation_list.php",
        ),
    ),
    (
        "in_transit",
        ListDefinition(
            "in_transit",
            "In Transit",
            "my_dispatch",
            "in_transit_2_list.php",
        ),
    ),
    (
        "awaiting_delivery",
        ListDefinition(
            "ready_for_delivery",
            "Ready for Delivery Confirmation",
            "my_dispatch",
            "Ready_for_Delivery_Confirmation_list.php",
        ),
    ),
    (
        "confirmation",
        ListDefinition(
            "fax_received",
            "Fax Received",
            "my_dispatch",
            "Fax_Received__list.php",
        ),
    ),
    (
        "confirmation",
        ListDefinition(
            "fax_returned",
            "Fax Returned",
            "my_dispatch",
            "Fax_Returned__list.php",
        ),
    ),
    (
        "pending",
        ListDefinition(
            "ftl_quotes",
            "Pending FTL Quotes",
            "my_dispatch",
            "my_ftl_quotes_list.php",
        ),
    ),
)

DELETED_LIST = ListDefinition(
    "deleted_loads",
    "Deleted Loads",
    "my_dispatch",
    "deleted_loads_list.php",
)

SALES_LISTS = (
    ListDefinition(
        "leads_no_callback",
        "Leads Without Callback",
        "sales",
        "my_leads_list.php",
    ),
    ListDefinition(
        "leads_callback",
        "Leads With Callback",
        "sales",
        "My_Leads_with_Callback_Date_list.php",
    ),
    ListDefinition(
        "priority_leads",
        "Priority Leads",
        "sales",
        "My_Priority_Leads_list.php",
    ),
    ListDefinition(
        "past_due",
        "Past Due Callbacks",
        "sales",
        "past_due_callbacks_list.php",
    ),
    ListDefinition(
        "charge_backs",
        "Charge Backs",
        "sales",
        "charge_backs_list.php",
    ),
    ListDefinition(
        "shipped_30",
        "Shipped in Last 30 Days",
        "sales",
        "newest_have_shipped_30_list.php",
    ),
    ListDefinition(
        "not_shipped_30",
        "Not Shipped in Last 30 Days",
        "sales",
        "newest_have_not_shipped_30_list.php",
    ),
    ListDefinition(
        "open_live_loads",
        "Open Live Loads",
        "sales",
        "live_loads_list.php",
    ),
)

CUSTOMERS_LIST = ListDefinition(
    "customers",
    "Customers",
    "my_dispatch",
    "customers1_list.php",
)

BRANCHES_LIST = ListDefinition(
    "branches",
    "Branches",
    "my_dispatch",
    "branches_list.php",
)

ALL_SMALL_LISTS = (
    *(definition for _, definition in STAGE_LISTS),
    DELETED_LIST,
    *SALES_LISTS,
    CUSTOMERS_LIST,
    BRANCHES_LIST,
)
