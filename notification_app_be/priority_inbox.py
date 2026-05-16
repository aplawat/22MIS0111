"""Priority inbox using a fixed-size min-heap."""

import requests
import sys
import os
import heapq
from itertools import count
from typing import List, Dict, Tuple
from datetime import datetime
from pathlib import Path

try:
    import importlib

    dotenv_module = importlib.import_module("dotenv")
    load_dotenv = dotenv_module.load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        return False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(str(PROJECT_ROOT / ".env"))
sys.path.insert(0, str(PROJECT_ROOT))
from logging_middleware.logger import Log

NOTIFICATIONS_ENDPOINT = "http://4.224.186.213/evaluation-service/notifications"
BEARER_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()

if not BEARER_TOKEN:
    raise ValueError(
        "ACCESS_TOKEN not found in environment. "
        "Please add it to .env file or set it as an environment variable."
    )
INBOX_SIZE = 10
DAYS_LOOKBACK = 30


class NotificationPriorityInbox:
    """Track the top K notifications with a min-heap."""
    
    def __init__(self, k: int = 10):
        self.k = k
        self.heap = []
        self.counter = count()

        self.weight_map = {
            "Placement": 2.0,
            "Result": 1.0,
            "Event": 0.0
        }
    
    def calculate_score(self, notification: Dict) -> float:
        notif_type = notification.get("type", notification.get("Type", "Event"))
        weight_factor = self.weight_map.get(notif_type, 0.0)
        
        try:
            created_at_str = notification.get("createdAt", notification.get("Timestamp", ""))
            if created_at_str.endswith('Z'):
                created_at_str = created_at_str[:-1]
            created_at = datetime.fromisoformat(created_at_str)

            now = datetime.utcnow()
            age_seconds = (now - created_at).total_seconds()
            age_days = age_seconds / 86400.0

            recency_score = max(0.0, 1.0 - (age_days / DAYS_LOOKBACK))

            score = (weight_factor * 2.0) + recency_score

            return score

        except Exception as e:
            Log("backend", "warn", "service", f"Error calculating score: {str(e)}")
            return 0.0
    
    def add_notification(self, notification: Dict) -> None:
        score = self.calculate_score(notification)
        notification["_score"] = score
        timestamp = notification.get("createdAt", notification.get("Timestamp", ""))
        
        if len(self.heap) < self.k:
            heapq.heappush(self.heap, (score, timestamp, next(self.counter), notification))
            
        else:
            min_score, _, _, _ = self.heap[0]
            
            if score > min_score:
                heapq.heapreplace(self.heap, (score, timestamp, next(self.counter), notification))
    
    def get_top_k(self) -> List[Dict]:
        sorted_notifications = sorted(
            [(score, timestamp, _, notif) for score, timestamp, _, notif in self.heap],
            key=lambda item: (-item[0], item[1], item[2]),
        )
        
        return [notif for score, timestamp, _, notif in sorted_notifications]


def fetch_notifications() -> List[Dict]:
    try:
        Log("backend", "info", "controller", "Fetching notifications from API")
        
        headers = {
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(NOTIFICATIONS_ENDPOINT, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        notifications = data.get("notifications", [])
        
        Log(
            "backend",
            "info",
            "repository",
            f"Retrieved {len(notifications)} notifications from API"
        )
        
        return notifications
        
    except requests.exceptions.RequestException as e:
        Log("backend", "error", "repository", f"Failed to fetch notifications: {str(e)}")
        raise
    except ValueError as e:
        Log("backend", "error", "service", f"Invalid JSON response: {str(e)}")
        raise


def process_priority_inbox(notifications: List[Dict]) -> List[Dict]:
    Log("backend", "info", "service", f"Processing {len(notifications)} notifications through priority inbox")
    
    inbox = NotificationPriorityInbox(k=INBOX_SIZE)

    for notification in notifications:
        if not notification.get("isRead", notification.get("IsRead", False)):
            inbox.add_notification(notification)

    top_notifications = inbox.get_top_k()
    
    Log(
        "backend",
        "info",
        "service",
        f"Selected top {len(top_notifications)} notifications for priority inbox"
    )
    
    return top_notifications


def format_notification_output(notification: Dict) -> str:
    notif_id = notification.get("id", notification.get("ID", "N/A"))[:8]
    notif_type = notification.get("type", notification.get("Type", "Unknown"))
    title = notification.get("title", notification.get("Message", "No Title"))[:40]
    score = notification.get("_score", 0)
    created_at = notification.get("createdAt", notification.get("Timestamp", "Unknown"))
    
    return (
        f"  ID: {notif_id}  │  Type: {notif_type:12} │  Score: {score:.2f}  │  "
        f"Title: {title:40} │  Created: {created_at}"
    )


def main():
    """Main execution function."""
    try:
        Log("backend", "info", "handler", "Priority Inbox service started")

        notifications = fetch_notifications()
        
        if not notifications:
            Log("backend", "warn", "service", "No notifications available")
            print("[INFO] No notifications found\n")
            return

        top_notifications = process_priority_inbox(notifications)

        print("PRIORITY INBOX - TOP 10 MOST IMPORTANT UNREAD NOTIFICATIONS")
        print(f"Total Unread: {len(notifications)} | Priority Inbox Size: {len(top_notifications)}\n")
        
        if len(top_notifications) == 0:
            print("[INFO] No unread notifications in priority inbox\n")
        else:
            print(f"{'Rank':<6} │ {'ID':<10} │ {'Type':<14} │ {'Score':<8} │ {'Title':<42} │ {'Created At'}")

            for rank, notif in enumerate(top_notifications, 1):
                line = format_notification_output(notif)
                print(f"{rank:<6} │ {line}")

            print("PRIORITY INBOX STATISTICS")

            type_counts = {}
            score_sum = 0

            for notif in top_notifications:
                notif_type = notif.get("type", "Unknown")
                type_counts[notif_type] = type_counts.get(notif_type, 0) + 1
                score_sum += notif.get("_score", 0)
            
            print("\nBreakdown by Type:")
            for notif_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                print(f"  • {notif_type}: {count}")
            
            print(f"\nAverage Score: {score_sum / len(top_notifications):.2f}")
            print(f"Highest Score: {top_notifications[0].get('_score', 0):.2f}")
            print(f"Lowest Score: {top_notifications[-1].get('_score', 0):.2f}")
        
        Log("backend", "info", "handler", "Priority Inbox service completed successfully")
        
    except Exception as e:
        Log("backend", "fatal", "handler", f"Priority Inbox service failed: {str(e)}")
        print(f"[ERROR] {str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()