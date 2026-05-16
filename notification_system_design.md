# Vehicle Maintenance Scheduler Microservice



## Stage 1: API Design

API:

```http
GET /api/v1/notifications/unread
PUT /api/v1/notifications/{notificationID}/read
GET /api/v1/notifications/priority-inbox
DELETE /api/v1/notifications/{notificationID}
```

Basic response shape:

```json
{
  "status": "success",
  "data": []
}
```

For real-time delivery, I would start with WebSockets. SSE is also fine if the client only needs one-way updates. Polling can be the fallback.

## Stage 2 Database & Scaling

I would use PostgreSQL for the main store.

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    studentID BIGINT NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    weight INT NOT NULL DEFAULT 0,
    isRead BOOLEAN DEFAULT FALSE,
    createdAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deletedAt TIMESTAMP NULL
);
```

Main problems at scale are read load, write load, and old data growth. I would handle that with:
- partitioning by date
- read replicas
- archive old notifications
- optional Redis cache for unread lists

## Stage 3: Query Optimization

The slow query is:

```sql
SELECT *
FROM notifications
WHERE studentID = 1042 AND isRead = false
ORDER BY createdAt DESC;
```

The best index here is:

```sql
CREATE INDEX idx_notifications_student_read_created
ON notifications(studentID, isRead, createdAt DESC)
WHERE deletedAt IS NULL;
```

Why this index:
- `studentID` is the first filter
- `isRead` is the second filter
- `createdAt DESC` matches the sort
- the partial index keeps it smaller

I would not index every column. That makes writes slower because every insert or update has to maintain more indexes. For this table, that tradeoff is not worth it.

## Stage 4: Caching

Unread notifications get hit a lot, so Redis makes sense.

Simple flow:
- check Redis first
- if miss, read from DB
- save result back to Redis with a short TTL

If a new notification arrives, I would delete the cache key for that student right away.

## Stage 5: System Reliability

I would not send email, save to DB, and push to the app in one synchronous loop.

The better approach is a message queue.

RabbitMQ or Kafka can sit between the API and the workers:
- API writes a message to the queue
- one worker saves to DB
- another worker handles email
- another worker handles push notifications

That way one failure does not block the whole request. Retries and dead-letter handling also become easier.

## Stage 6: Priority Inbox

For the priority inbox, I would keep the top 10 unread notifications in memory using a min-heap.

The code approach is:

```python
import heapq

class PriorityInbox:
    def __init__(self, limit=10):
        self.limit = limit
        self.heap = []

    def score(self, notification):
        weight_map = {
            "Placement": 2.0,
            "Result": 1.0,
            "Event": 0.0,
        }
        weight = weight_map.get(notification["type"], 0.0)
        recency = notification["recencyScore"]
        return (weight * 2) + recency

    def add(self, notification):
        value = self.score(notification)
        item = (value, notification["createdAt"], notification)

        if len(self.heap) < self.limit:
            heapq.heappush(self.heap, item)
        elif value > self.heap[0][0]:
            heapq.heapreplace(self.heap, item)
```

This gives me:
- Placement > Result > Event
- newer notifications ranked higher
- only 10 items kept in memory

## Short summary

This system is simple but practical:
- PostgreSQL for storage
- Redis for cache
- queue for async work
- min-heap for priority inbox
- composite index for unread query speed
