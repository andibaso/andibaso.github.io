import json
import sys

ACCOUNT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 0

# Resource attribute names. Verify with:
#   FROM Metric SELECT keyset() WHERE metricName LIKE 'mongodb.%' SINCE 1 hour ago
# and change these four lines if they differ.
PROJ = "`mongodb.project.name`"
CL = "`mongodb.cluster.name`"
HOST = "`mongodb.process.host`"
RS = "`mongodb.replica_set.name`"
STATE = "`mongodb.replica_set.state`"
NODE = "`mongodb.node.type`"

# Logs: Atlas's OTel export is metrics only. The Logs page is kept in the script but off by
# default. Turn it on if you later ship mongod logs through the collector's mongodbatlas
# receiver (its logs mode) and adjust the field names below to what arrives in Log.
INCLUDE_LOGS_PAGE = False

# Log field names. Confirm with:
#   FROM Log SELECT keyset() WHERE `mongodb.cluster.name` IS NOT NULL SINCE 1 hour ago
# and change these if they differ. Structured mongod log fields are assumed to arrive as
# c (component), id, ctx, msg and attr.* (as in the JSON log lines).
LOG_SEV = "`severity.text`"
LOG_COMP = "`c`"
LOG_ID = "`id`"
LOG_MSG = "`msg`"
LOG_CTX = "`ctx`"
LOG_ATTR = "attr"

# server_status counters arrive in New Relic as gauges carrying cumulative values,
# so they are turned into per-second rates with derivative(). If those charts come
# out flat near zero, the export is already a rate: set this to False.
SS_COUNTERS_ARE_CUMULATIVE = True

VARS = f"{PROJ} IN ({{{{project}}}}) AND {CL} IN ({{{{cluster}}}})"


def q(select, where=None, facet=None, ts=True):
    s = f"FROM Metric SELECT {select} WHERE {VARS}"
    if where:
        s += f" AND {where}"
    if facet:
        s += f" FACET {facet}"
    if ts:
        s += " TIMESERIES AUTO"
    return s


def r(metric, label=None, per="1 second"):
    """Per-second rate of a cumulative counter."""
    label = label or metric.split(".")[-1]
    return f"rate(sum(`{metric}`), {per}) AS '{label}'"


def c(metric, label=None):
    """Monotonic gauge (cumulative value delivered as a gauge)."""
    label = label or metric.split(".")[-1]
    if SS_COUNTERS_ARE_CUMULATIVE:
        return f"derivative(`{metric}`, 1 second) AS '{label}'"
    return f"latest(`{metric}`) AS '{label}'"


def g(metric, label=None, fn="latest"):
    """Gauge."""
    label = label or metric.split(".")[-1]
    return f"{fn}(`{metric}`) AS '{label}'"


def multi(*parts):
    return ", ".join(parts)


def widget(title, viz, query, col, row, w=4, h=3, extra=None):
    cfg = {
        "nrqlQueries": [{"accountId": ACCOUNT_ID, "query": query}],
        "platformOptions": {"ignoreTimeRange": False},
    }
    if viz in ("viz.line", "viz.area", "viz.stacked-bar"):
        cfg["facet"] = {"showOtherSeries": False}
        cfg["legend"] = {"enabled": True}
        cfg["yAxisLeft"] = {"zero": True}
    if viz == "viz.line":
        cfg["nullValues"] = {"nullValue": "default"}
    if viz == "viz.billboard":
        cfg["facet"] = {"showOtherSeries": False}
    if extra:
        cfg.update(extra)
    return {
        "title": title,
        "layout": {"column": col, "row": row, "width": w, "height": h},
        "linkedEntityGuids": None,
        "visualization": {"id": viz},
        "rawConfiguration": cfg,
    }


def grid(rows):
    out, row = [], 1
    for rw in rows:
        col = 1
        for spec in rw:
            title, viz, query = spec[0], spec[1], spec[2]
            w = spec[3] if len(spec) > 3 else 4
            extra = spec[4] if len(spec) > 4 else None
            out.append(widget(title, viz, query, col, row, w, 3, extra))
            col += w
        row += 3
    return out


SS = "mongodb.server_status"
HW = "mongodb.hardware"
DV = "mongodb.derived"
RSS = "mongodb.repl_status"
SRCH = "mongodb.search"

# ---------- Page 1: Overview ----------
overview = grid([
    [
        ("Clusters", "viz.billboard", q(f"uniqueCount({CL}) AS 'Clusters'", "metricName LIKE 'mongodb.%'", ts=False), 2),
        ("Hosts", "viz.billboard", q(f"uniqueCount({HOST}) AS 'Hosts'", "metricName LIKE 'mongodb.%'", ts=False), 2),
        ("Replica set members", "viz.table",
         q(g(f"{RSS}.my_state", "my_state"), facet=f"{HOST}, {RS}, {STATE}, {NODE}", ts=False), 4),
        ("Connections (current)", "viz.bar",
         q(g(f"{SS}.connections.current", "Connections"), facet=HOST, ts=False), 4),
    ],
    [
        ("Opcounters /s", "viz.line",
         q(multi(c(f"{SS}.opcounters.query"), c(f"{SS}.opcounters.getmore"), c(f"{SS}.opcounters.insert"),
                 c(f"{SS}.opcounters.update"), c(f"{SS}.opcounters.delete"), c(f"{SS}.opcounters.command")))),
        ("Process CPU normalized %", "viz.line",
         q(f"average(`{HW}.process.cpu.normalized_user_percent`) + average(`{HW}.process.cpu.normalized_kernel_percent`) AS 'CPU %'", facet=HOST)),
        ("Process RSS (bytes)", "viz.line",
         q(g(f"{HW}.process.memory.vm_rss_bytes", "RSS"), facet=HOST)),
    ],
    [
        ("Disk used %", "viz.line",
         q(g(f"{HW}.disk.space_used_percentage", "Used %"), facet=HOST)),
        ("Tickets available", "viz.line",
         q(multi(g(f"{SS}.queues.execution.read.available", "read"), g(f"{SS}.queues.execution.write.available", "write")), facet=HOST)),
        ("Replication lag (ms)", "viz.line",
         q(multi(g(f"{DV}.replstatus.lag_milliseconds", "lag"), g(f"{DV}.replstatus.majority_commit_lag_milliseconds", "majority commit lag")), facet=HOST)),
    ],
    [
        ("Query targeting: scanned objects vs returned /s", "viz.line",
         q(multi(c(f"{SS}.metrics.query_executor.scanned_objects", "scanned objects"), c(f"{SS}.metrics.document.returned", "returned")), facet=HOST)),
        ("Read latency p50 / p95 (micros)", "viz.line",
         q(multi(g(f"{DV}.server_status.op_latencies.reads.micros.p50", "p50"), g(f"{DV}.server_status.op_latencies.reads.micros.p95", "p95")), facet=HOST)),
        ("Write latency p50 / p95 (micros)", "viz.line",
         q(multi(g(f"{DV}.server_status.op_latencies.writes.micros.p50", "p50"), g(f"{DV}.server_status.op_latencies.writes.micros.p95", "p95")), facet=HOST)),
    ],
    [
        ("Global lock queue", "viz.line",
         q(multi(g(f"{SS}.global_lock.current_queue.readers", "readers"), g(f"{SS}.global_lock.current_queue.writers", "writers")), facet=HOST)),
        ("Failed commands /s", "viz.line",
         q(multi(r(f"{DV}.commands.failed", "failed"), r(f"{DV}.commands.total", "total")), facet=HOST)),
        ("Page faults /s", "viz.line",
         q(c(f"{SS}.extra_info.page_faults", "faults/s"), facet=HOST)),
    ],
])

# ---------- Page 2: Operations ----------
operations = grid([
    [
        ("Reads /s", "viz.line", q(multi(c(f"{SS}.opcounters.query"), c(f"{SS}.opcounters.getmore")), facet=HOST)),
        ("Writes /s", "viz.line", q(multi(c(f"{SS}.opcounters.insert"), c(f"{SS}.opcounters.update"), c(f"{SS}.opcounters.delete")), facet=HOST)),
        ("Commands and aggregates /s", "viz.line", q(multi(c(f"{SS}.opcounters.command"), c(f"{SS}.opcounters.aggregate")), facet=HOST)),
    ],
    [
        ("Document rates /s", "viz.line",
         q(multi(c(f"{SS}.metrics.document.returned"), c(f"{SS}.metrics.document.inserted"),
                 c(f"{SS}.metrics.document.updated"), c(f"{SS}.metrics.document.deleted")), facet=HOST)),
        ("Query executor scanned /s", "viz.line",
         q(multi(c(f"{SS}.metrics.query_executor.scanned", "index keys"), c(f"{SS}.metrics.query_executor.scanned_objects", "objects")), facet=HOST)),
        ("Scan and order, write conflicts /s", "viz.line",
         q(multi(c(f"{SS}.metrics.operation.scan_and_order", "scan and order"), c(f"{SS}.metrics.operation.write_conflicts", "write conflicts")), facet=HOST)),
    ],
    [
        ("Command latency p50 / p95 (micros)", "viz.line",
         q(multi(g(f"{DV}.server_status.op_latencies.commands.micros.p50", "p50"), g(f"{DV}.server_status.op_latencies.commands.micros.p95", "p95")), facet=HOST)),
        ("Working time p95 (micros)", "viz.line",
         q(multi(g(f"{DV}.server_status.op_working_time.reads.micros.p95", "reads"), g(f"{DV}.server_status.op_working_time.writes.micros.p95", "writes"),
                 g(f"{DV}.server_status.op_working_time.commands.micros.p95", "commands")), facet=HOST)),
        ("Cursors", "viz.line",
         q(multi(g(f"{SS}.metrics.cursor.open", "open"), c(f"{SS}.metrics.cursor.timed_out", "timed out /s")), facet=HOST)),
    ],
    [
        ("Asserts /s", "viz.line",
         q(multi(c(f"{SS}.asserts.regular"), c(f"{SS}.asserts.warning"), c(f"{SS}.asserts.msg"), c(f"{SS}.asserts.user")), facet=HOST)),
        ("Network bytes /s", "viz.line",
         q(multi(c(f"{SS}.network.bytes_in", "in"), c(f"{SS}.network.bytes_out", "out")), facet=HOST)),
        ("Network requests /s", "viz.line", q(c(f"{SS}.network.num_requests", "req/s"), facet=HOST)),
    ],
    [
        ("Connections", "viz.line",
         q(multi(g(f"{SS}.connections.current", "current"), g(f"{SS}.connections.active", "active")), facet=HOST)),
        ("Connections created /s", "viz.line", q(c(f"{SS}.connections.total_created", "created/s"), facet=HOST)),
        ("Transactions", "viz.line",
         q(multi(g(f"{SS}.transactions.current_open", "open"), g(f"{SS}.transactions.current_prepared", "prepared")), facet=HOST)),
    ],
    [
        ("TTL deleted documents /s", "viz.line", q(c(f"{SS}.metrics.ttl.deleted_documents", "deleted/s"), facet=HOST)),
        ("Sort spill to disk /s", "viz.line", q(c(f"{SS}.metrics.query.sort.spill_to_disk", "spills/s"), facet=HOST)),
        ("Plan cache misses /s", "viz.line",
         q(multi(c(f"{SS}.metrics.query.plan_cache.classic.misses", "classic"), c(f"{SS}.metrics.query.plan_cache.sbe.misses", "sbe")), facet=HOST)),
    ],
])

# ---------- Page 3: Resources ----------
resources = grid([
    [
        ("Process CPU normalized %", "viz.line",
         q(multi(g(f"{HW}.process.cpu.normalized_user_percent", "user", "average"), g(f"{HW}.process.cpu.normalized_kernel_percent", "kernel", "average")), facet=HOST)),
        ("System CPU normalized %", "viz.line",
         q(multi(g(f"{HW}.system.cpu.normalized_user_percent", "user", "average"), g(f"{HW}.system.cpu.normalized_kernel_percent", "kernel", "average"),
                 g(f"{HW}.system.cpu.normalized_io_wait_percent", "iowait", "average"), g(f"{HW}.system.cpu.normalized_steal_percent", "steal", "average")), facet=HOST)),
        ("System memory used %", "viz.line", q(g(f"{HW}.system.memory.percent_used", "Used %"), facet=HOST)),
    ],
    [
        ("System memory (KiB)", "viz.line",
         q(multi(g(f"{HW}.system.memory.used_kilobytes", "used"), g(f"{HW}.system.memory.available_kilobytes", "available"), g(f"{HW}.system.memory.cached_kilobytes", "cached")), facet=HOST)),
        ("Process memory (bytes)", "viz.line",
         q(multi(g(f"{HW}.process.memory.vm_rss_bytes", "rss"), g(f"{HW}.process.memory.vm_size_bytes", "virtual")), facet=HOST)),
        ("tcmalloc (bytes)", "viz.line",
         q(multi(g(f"{SS}.tcmalloc.generic.heap_size", "heap"), g(f"{SS}.tcmalloc.generic.current_allocated_bytes", "allocated")), facet=HOST)),
    ],
    [
        ("WiredTiger cache (bytes)", "viz.line",
         q(multi(g(f"{SS}.wired_tiger.cache.bytes_currently_in_the_cache", "in cache"), g(f"{SS}.wired_tiger.cache.tracked_dirty_bytes_in_the_cache", "dirty"),
                 g(f"{SS}.wired_tiger.cache.maximum_bytes_configured", "max")), facet=HOST)),
        ("WiredTiger cache IO (bytes/s)", "viz.line",
         q(multi(c(f"{SS}.wired_tiger.cache.bytes_read_into_cache", "read into"), c(f"{SS}.wired_tiger.cache.bytes_written_from_cache", "written from")), facet=HOST)),
        ("WiredTiger cache fill %", "viz.line",
         q(f"latest(`{SS}.wired_tiger.cache.bytes_currently_in_the_cache`) / latest(`{SS}.wired_tiger.cache.maximum_bytes_configured`) * 100 AS 'Fill %'", facet=HOST)),
    ],
    [
        ("Disk IOPS", "viz.line",
         q(multi(r(f"{HW}.disk.read_count", "read"), r(f"{HW}.disk.write_count", "write")), facet=HOST)),
        ("Disk latency (ms)", "viz.line",
         q(multi(g(f"{HW}.disk.read_latency_milliseconds", "read", "average"), g(f"{HW}.disk.write_latency_milliseconds", "write", "average")), facet=HOST)),
        ("Disk throughput (bytes/s)", "viz.line",
         q(multi(g(f"{HW}.disk.read_throughput_bytes_per_second", "read", "average"), g(f"{HW}.disk.write_throughput_bytes_per_second", "write", "average")), facet=HOST)),
    ],
    [
        ("Disk space (bytes)", "viz.line",
         q(multi(g(f"{HW}.disk.space_used_bytes", "used"), g(f"{HW}.disk.space_free_bytes", "free")), facet=HOST)),
        ("Disk queue depth", "viz.line", q(g(f"{HW}.disk.queue_depth", "depth", "average"), facet=HOST)),
        ("Root disk used %", "viz.line", q(g(f"{HW}.root_disk.space_used_percentage", "Used %"), facet=HOST)),
    ],
    [
        ("Pressure stall avg10 (PSI)", "viz.line",
         q(multi(g(f"{HW}.system.pressure.cpu_some_avg10", "cpu some", "average"), g(f"{HW}.system.pressure.io_some_avg10", "io some", "average"),
                 g(f"{HW}.system.pressure.memory_some_avg10", "memory some", "average")), facet=HOST)),
        ("Swap (KiB)", "viz.line",
         q(multi(g(f"{HW}.system.memory.swap_used_kilobytes", "used"), g(f"{HW}.system.memory.swap_free_kilobytes", "free")), facet=HOST)),
        ("Swap IO and OOM kills", "viz.line",
         q(multi(r(f"{HW}.system.vm.page_swap_in", "swap in /s"), r(f"{HW}.system.vm.page_swap_out", "swap out /s"), r(f"{HW}.system.vm.oom_kill", "oom kill /s")), facet=HOST)),
    ],
    [
        ("System network (bytes/s)", "viz.line",
         q(multi(r(f"{HW}.system.network.bytes_in_bytes", "in"), r(f"{HW}.system.network.bytes_out_bytes", "out")), facet=HOST)),
        ("Uptime (hours)", "viz.line", q(f"latest(`{SS}.uptime_millis`) / 3600000 AS 'Hours'", facet=HOST)),
        ("Logical CPUs", "viz.table", q(g(f"{HW}.platform.num_logical_cpus", "CPUs"), facet=HOST, ts=False)),
    ],
])

# ---------- Page 4: Replication, storage, search ----------
storage = grid([
    [
        ("Replication lag (ms)", "viz.line",
         q(multi(g(f"{DV}.replstatus.lag_milliseconds", "lag"), g(f"{DV}.replstatus.majority_commit_lag_milliseconds", "majority commit lag")), facet=HOST)),
        ("Oplog window (s)", "viz.line", q(g(f"{DV}.oplog.master_time_seconds", "window"), facet=HOST)),
        ("Oplog rate (bytes/s) and size (bytes)", "viz.line",
         q(multi(g(f"{DV}.oplog.bytes_per_second", "rate", "average"), g("mongodb.oplog.rs_stats.size", "size")), facet=HOST)),
    ],
    [
        ("Repl apply batches (ms/s)", "viz.line",
         q(multi(c(f"{SS}.metrics.repl.apply.batches.total_millis", "apply"), c(f"{SS}.metrics.repl.write.batches.total_millis", "write")), facet=HOST)),
        ("Repl getmores /s", "viz.line",
         q(multi(c(f"{SS}.metrics.repl.network.getmores.num", "getmores"), c(f"{SS}.metrics.repl.network.getmores.num_empty_batches", "empty batches")), facet=HOST)),
        ("Flow control", "viz.line",
         q(multi(g(f"{SS}.flow_control.is_lagged", "lagged"), g(f"{SS}.flow_control.target_rate_limit", "target rate limit")), facet=HOST)),
    ],
    [
        ("Catalog", "viz.table",
         q(multi(g(f"{SS}.catalog_stats.collections", "collections"), g(f"{SS}.catalog_stats.views", "views"), g(f"{SS}.catalog_stats.timeseries", "timeseries"),
                 g(f"{SS}.index_stats.count", "indexes")), facet=HOST, ts=False)),
        ("Index builds", "viz.line",
         q(multi(g(f"{SS}.index_builds.total", "total"), g(f"{SS}.index_bulk_builder.mem_usage", "bulk builder mem")), facet=HOST)),
        ("Oplog truncation", "viz.line",
         q(multi(c(f"{SS}.oplog_truncation.truncate_count", "truncates/s"), c(f"{SS}.oplog_truncation.total_time_truncating_micros", "micros/s")), facet=HOST)),
    ],
    [
        ("Atlas Search queries /s", "viz.line",
         q(multi(r(f"{SRCH}.index_stats_query_total_queries", "total"), r(f"{SRCH}.index_stats_query_failed_queries", "failed")), facet=HOST)),
        ("Atlas Search indexing /s", "viz.line",
         q(multi(r(f"{SRCH}.index_stats_indexing_insert", "insert"), r(f"{SRCH}.index_stats_indexing_update", "update"), r(f"{SRCH}.index_stats_indexing_delete", "delete")), facet=HOST)),
        ("Atlas Search replication lag (ms)", "viz.line", q(g(f"{SRCH}.index_stats_indexing_replication_lag_ms", "lag"), facet=HOST)),
    ],
    [
        ("Atlas Search JVM memory (bytes)", "viz.line",
         q(multi(g(f"{SRCH}.jvm_memory_used_bytes", "used"), g(f"{SRCH}.jvm_memory_max_bytes", "max")), facet=HOST)),
        ("Atlas Search index size (bytes)", "viz.line", q(g(f"{SRCH}.index_stats_index_size_bytes", "size"), facet=HOST)),
        ("Atlas Search Lucene max docs", "viz.line", q(g(f"{SRCH}.index_stats_num_lucene_max_docs", "docs"), facet=HOST)),
    ],
])


def lq(select, where=None, facet=None, ts=True):
    s = f"FROM Log SELECT {select} WHERE {CL} IS NOT NULL AND {VARS}"
    if where:
        s += f" AND {where}"
    if facet:
        s += f" FACET {facet}"
    if ts:
        s += " TIMESERIES AUTO"
    return s


A = LOG_ATTR
ERR = f"{LOG_SEV} IN ('E', 'F', 'ERROR', 'FATAL', 'error', 'fatal')"
WARN = f"{LOG_SEV} IN ('W', 'WARN', 'WARNING', 'warn', 'warning')"
SLOW = f"{LOG_ID} = 51803"

logs = grid([
    [
        ("Errors and fatals", "viz.billboard", lq("count(*) AS 'Errors'", ERR, ts=False), 2,
         {"thresholds": [{"alertSeverity": "CRITICAL", "value": 1}]}),
        ("Warnings", "viz.billboard", lq("count(*) AS 'Warnings'", WARN, ts=False), 2),
        ("Slow queries", "viz.billboard", lq("count(*) AS 'Slow queries'", SLOW, ts=False), 2),
        ("Auth failures", "viz.billboard", lq("count(*) AS 'Auth failures'", f"{LOG_ID} = 20249", ts=False), 2),
        ("Log volume by severity", "viz.stacked-bar", lq("count(*)", facet=LOG_SEV), 4),
    ],
    [
        ("Log volume by host", "viz.line", lq("count(*)", facet=HOST)),
        ("Log volume by component", "viz.stacked-bar", lq("count(*)", facet=LOG_COMP)),
        ("Errors and warnings over time", "viz.line",
         lq(f"filter(count(*), WHERE {ERR}) AS 'errors', filter(count(*), WHERE {WARN}) AS 'warnings'", facet=HOST)),
    ],
    [
        ("Slow queries per host", "viz.line", lq("count(*) AS 'slow queries'", SLOW, facet=HOST)),
        ("Slow query duration (ms)", "viz.line",
         lq(f"average(`{A}.durationMillis`) AS 'avg', max(`{A}.durationMillis`) AS 'max'", SLOW, facet=HOST)),
        ("Slow queries by namespace", "viz.bar", lq("count(*) AS 'slow queries'", SLOW, facet=f"`{A}.ns`", ts=False)),
    ],
    [
        ("Slowest queries", "viz.table",
         lq(f"max(`{A}.durationMillis`) AS 'ms', latest(`{A}.planSummary`) AS 'plan', latest(`{A}.docsExamined`) AS 'docs examined', "
            f"latest(`{A}.keysExamined`) AS 'keys examined', latest(`{A}.nreturned`) AS 'returned'",
            SLOW, facet=f"`{A}.ns`, `{A}.queryHash`", ts=False), 8),
        ("Collection scans (COLLSCAN)", "viz.line", lq("count(*) AS 'COLLSCAN'", f"{SLOW} AND `{A}.planSummary` LIKE 'COLLSCAN%'", facet=f"`{A}.ns`"), 4),
    ],
    [
        ("Connections accepted / ended", "viz.line",
         lq(f"filter(count(*), WHERE {LOG_ID} = 22943) AS 'accepted', filter(count(*), WHERE {LOG_ID} = 22944) AS 'ended'", facet=HOST)),
        ("Replication and election events", "viz.line",
         lq("count(*)", f"{LOG_COMP} IN ('REPL', 'ELECTION')", facet=f"{HOST}, {LOG_ID}")),
        ("Top log messages", "viz.table", lq("count(*)", facet=f"{LOG_ID}, {LOG_MSG}", ts=False)),
    ],
    [
        ("Recent errors and warnings", "logger.log-table-widget",
         lq("*", f"({ERR} OR {WARN})", ts=False) + " LIMIT 100", 12),
    ],
])


def var(name, title, attr):
    return {
        "name": name,
        "title": title,
        "type": "NRQL",
        "isMultiSelection": True,
        "replacementStrategy": "DEFAULT",
        "defaultValues": None,
        "items": None,
        "nrqlQuery": {
            "accountIds": [ACCOUNT_ID],
            "query": f"FROM Metric SELECT uniques({attr}, 1000) SINCE 1 day ago",
        },
        "options": {"ignoreTimeRange": True, "excluded": True},
    }


dashboard = {
    "name": "MongoDB Atlas (OpenTelemetry)",
    "description": "MongoDB Atlas metrics exported via OpenTelemetry (mongodb.server_status, mongodb.hardware, mongodb.derived, mongodb.search)",
    "permissions": "PUBLIC_READ_WRITE",
    "pages": [
        {"name": "Overview", "description": None, "widgets": overview},
        {"name": "Operations", "description": None, "widgets": operations},
        {"name": "Resources", "description": None, "widgets": resources},
        {"name": "Replication, Storage, Search", "description": None, "widgets": storage},
    ] + ([{"name": "Logs", "description": None, "widgets": logs}] if INCLUDE_LOGS_PAGE else []),
    "variables": [
        var("project", "Project", PROJ),
        var("cluster", "Cluster", CL),
    ],
}

with open("mongodb-atlas-otel-dashboard.json", "w") as f:
    json.dump(dashboard, f, indent=2)

print(sum(len(p["widgets"]) for p in dashboard["pages"]), "widgets, accountId", ACCOUNT_ID)
if ACCOUNT_ID == 0:
    print("WARNING: pass your New Relic account ID as the first argument, New Relic rejects accountId 0")
