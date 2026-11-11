"""adequacy: intake checks and readiness score for a customer's event + catalog data drop.

Input format (the "event triplets" a discovery platform asks for):
    events : user_id, event_type, item_id, timestamp
    catalog: item_id + any attribute columns (category_id, title, n_properties, ...)
"""
__version__ = "0.1.0"
