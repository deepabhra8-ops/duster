import os


# Tables scanned concurrently within one run (each is one Spark job at a time).
DQ_DEFAULT_PARALLEL_TABLES = int(os.getenv("DQ_DEFAULT_PARALLEL_TABLES", "4"))
DQ_MAX_PARALLEL_TABLES = int(os.getenv("DQ_MAX_PARALLEL_TABLES", "16"))

# Aggregate expressions per scan. Very wide tables × many rules can produce thousands,
# which bloats Spark's query plan; past this the checks split into extra passes.
DQ_MAX_EXPRS_PER_PASS = int(os.getenv("DQ_MAX_EXPRS_PER_PASS", "400"))

# Runs executing at the same time across the whole server.
DQ_RUN_WORKERS = int(os.getenv("DQ_RUN_WORKERS", "2"))

# A dry run reads column metadata per table; past this many tables it stops inspecting
# and reports the plan as truncated.
DQ_DRY_RUN_MAX_TABLES = int(os.getenv("DQ_DRY_RUN_MAX_TABLES", "200"))

DQ_RESULTS_MAX_PAGE_SIZE = int(os.getenv("DQ_RESULTS_MAX_PAGE_SIZE", "500"))
