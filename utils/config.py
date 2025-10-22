# config.py

PRESET_SEARCH_QUERIES = {
    "phone": [
        {"query": "latest smartphones under 30000 KES Nairobi", "location": "Nairobi, Kenya", "price_max": 30000},
        {"query": "best camera phones 2024 Nairobi", "location": "Nairobi, Kenya"},
        {"query": "budget Android phones Kenya", "location": "Kenya", "price_max": 20000},
        {"query": "gaming phones high refresh rate", "location": "Kenya"},
        # Add more diverse phone queries
    ],
    "laptop": [
        {"query": "gaming laptops under 150000 KES Nairobi", "location": "Nairobi, Kenya", "price_max": 150000},
        {"query": "ultrabook for students Kenya", "location": "Kenya"},
        {"query": "laptops for video editing 2024", "location": "Kenya"},
        # Add more diverse laptop queries
    ],
    "tablet": [
        {"query": "best tablets for drawing Kenya", "location": "Kenya"},
        {"query": "affordable tablets with stylus support Nairobi", "location": "Nairobi, Kenya", "price_max": 40000},
    ],
    "earpiece": [
        {"query": "best noise cancelling headphones Kenya", "location": "Kenya"},
        {"query": "wireless earbuds with long battery life Nairobi", "location": "Nairobi, Kenya"},
    ],
    "prebuilt_pc": [
        {"query": "prebuilt gaming PCs under 200000 KES Kenya", "location": "Kenya", "price_max": 200000},
        {"query": "budget prebuilt desktop for office use Nairobi", "location": "Nairobi, Kenya", "price_max": 80000},
    ]
    # PCBuilderAgent typically doesn't use the vector DB for components due to dynamic nature,
    # so no preset queries for it here.
}