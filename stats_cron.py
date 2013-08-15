from tapiriik.database import db
from datetime import datetime, timedelta
#  total distance synced
distanceSynced = db.sync_stats.aggregate([{"$group": {"_id": None, "total": {"$sum": "$Distance"}}}])["result"][0]["total"]

# sync time utilization
db.sync_worker_stats.remove({"Timestamp": {"$lt": datetime.utcnow() - timedelta(hours=1)}})  # clean up old records
timeUsed = db.sync_worker_stats.aggregate([{"$group": {"_id": None, "total": {"$sum": "$TimeTaken"}}}])["result"][0]["total"]

# error/pending/locked stats
lockedSyncRecords = db.users.aggregate([
                                       {"$match": {"SynchronizationWorker": {"$ne": None}}},
                                       {"$group": {"_id": None, "count": {"$sum": 1}}}
                                       ])
if len(lockedSyncRecords["result"]) > 0:
    lockedSyncRecords = lockedSyncRecords["result"][0]["count"]
else:
    lockedSyncRecords = 0

pendingSynchronizations = db.users.aggregate([
                                             {"$match": {"NextSynchronization": {"$lt": datetime.utcnow()}}},
                                             {"$group": {"_id": None, "count": {"$sum": 1}}}
                                             ])
if len(pendingSynchronizations["result"]) > 0:
    pendingSynchronizations = pendingSynchronizations["result"][0]["count"]
else:
    pendingSynchronizations = 0

usersWithErrors = db.users.aggregate([
                                     {"$match": {"SyncErrorCount": {"$gt": 0}}},
                                     {"$group": {"_id": None, "count": {"$sum": 1}}}
                                     ])
if len(usersWithErrors["result"]) > 0:
    usersWithErrors = usersWithErrors["result"][0]["count"]
else:
    usersWithErrors = 0


totalErrors = db.users.aggregate([
   {"$group": {"_id": None,
               "total": {"$sum": "$SyncErrorCount"}}}
])

if len(totalErrors["result"]) > 0:
    totalErrors = totalErrors["result"][0]["total"]
else:
    totalErrors = 0

db.sync_status_stats.insert({
        "Timestamp": datetime.utcnow(),
        "Locked": lockedSyncRecords,
        "Pending": pendingSynchronizations,
        "ErrorUsers": usersWithErrors,
        "TotalErrors": totalErrors,
        "SyncTimeUsed": timeUsed
})

db.stats.update({}, {"$set": {"TotalDistanceSynced": distanceSynced, "TotalSyncTimeUsed": timeUsed, "Updated": datetime.utcnow()}}, upsert=True)


def aggregateCommonErrors():
    from bson.code import Code
    # The exception message always appears right before "LOCALS:"
    map_operation = Code(
        "function(){"
            "var errorMatch = new RegExp(/\\n([^\\n]+)\\n\\nLOCALS:/);"
            "if (!this.SyncErrors) return;"
            "this.SyncErrors.forEach(function(error){"
                "emit(error.Message.match(errorMatch)[1],1);"
            "});"
        "}"
        )
    reduce_operation = Code(
        "function(key, counts){"
            "return Array.sum(counts);"
        "}")
    db.connections.map_reduce(map_operation, reduce_operation, "common_sync_errors")
    # We don't need to do anything with the result right now, just leave it there to appear in the dashboard

aggregateCommonErrors()

# Misc cleanup
db.sync_workers.remove({"Heartbeat": {"$lt": datetime.utcnow()-timedelta(days=7)}})
