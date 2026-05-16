"""Vehicle maintenance scheduler using a 0/1 knapsack DP."""

import requests
import sys
import os
from typing import List, Dict, Tuple
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

DEPOT_ENDPOINT = "http://4.224.186.213/evaluation-service/depots"
VEHICLES_ENDPOINT = "http://4.224.186.213/evaluation-service/vehicles"
BEARER_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()

if not BEARER_TOKEN:
    raise ValueError(
        "ACCESS_TOKEN not found in environment. "
        "Please add it to .env file or set it as an environment variable."
    )

def auth_headers() -> dict:
    return {"Authorization": f"Bearer {BEARER_TOKEN}"}


def fetch_depot_data() -> int:
    """Fetch available mechanic hours from the depot API."""
    try:
        Log("backend", "info", "controller", "Fetching depot data")
        response = requests.get(DEPOT_ENDPOINT, headers=auth_headers(), timeout=5)
        response.raise_for_status()
        
        data = response.json()
        depots = data.get("depots", [])
        
        if not depots:
            raise ValueError("No depots found in response")
        
        mechanic_hours = depots[0].get("MechanicHours", 0)
        Log("backend", "info", "service", f"Depot capacity: {mechanic_hours} mechanic-hours")
        
        return mechanic_hours
        
    except Exception as e:
        Log("backend", "error", "service", f"Failed to fetch depot data: {str(e)}")
        raise


def fetch_vehicle_data() -> List[Dict]:
    """Fetch maintenance tasks from the protected vehicles API."""
    try:
        Log("backend", "info", "controller", "Fetching vehicle maintenance tasks")
        headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
        response = requests.get(VEHICLES_ENDPOINT, headers=headers, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        vehicles = data.get("vehicles", [])
        
        Log("backend", "info", "service", f"Retrieved {len(vehicles)} maintenance tasks")
        return vehicles
        
    except Exception as e:
        Log("backend", "error", "repository", f"Failed to fetch vehicle data: {str(e)}")
        raise


def solve_knapsack(
    vehicles: List[Dict],
    capacity: int
) -> Tuple[List[str], int]:
    """Solve the 0/1 knapsack and return selected task IDs and impact."""
    n = len(vehicles)
    
    if n == 0 or capacity == 0:
        Log("backend", "warn", "service", "Empty vehicles list or zero capacity")
        return [], 0

    durations = [v["Duration"] for v in vehicles]
    impacts = [v["Impact"] for v in vehicles]

    dp = [[0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        item_duration = durations[i - 1]
        item_impact = impacts[i - 1]
        
        for w in range(capacity + 1):
            exclude_value = dp[i - 1][w]
            include_value = 0
            if item_duration <= w:
                include_value = item_impact + dp[i - 1][w - item_duration]

            dp[i][w] = max(exclude_value, include_value)

    selected_indices = []
    w = capacity

    for i in range(n, 0, -1):
        if dp[i][w] != dp[i - 1][w]:
            selected_indices.append(i - 1)
            w -= durations[i - 1]

    selected_indices.reverse()

    selected_task_ids = [vehicles[idx]["TaskID"] for idx in selected_indices]
    total_impact = dp[n][capacity]
    
    total_duration = sum(durations[idx] for idx in selected_indices)
    Log(
        "backend",
        "info",
        "service",
        f"Knapsack solution: {len(selected_indices)} tasks selected, "
        f"duration={total_duration}h, impact={total_impact}"
    )
    
    return selected_task_ids, total_impact


def main():
    """Main execution function."""
    try:
        Log("backend", "info", "cron_job", "Vehicle Maintenance Scheduler started")

        available_hours = fetch_depot_data()
        vehicles = fetch_vehicle_data()
        
        if not vehicles:
            Log("backend", "warn", "service", "No vehicles available for scheduling")
            print("[RESULT] No vehicles to schedule")
            return

        selected_task_ids, total_impact = solve_knapsack(vehicles, available_hours)
        print("VEHICLE MAINTENANCE SCHEDULER - RESULTS")
        print(f"Available Mechanic-Hours: {available_hours}")
        print(f"Total Maintenance Tasks: {len(vehicles)}")
        print(f"\nOptimal Selection:")
        print(f"  Selected Tasks: {len(selected_task_ids)}")
        print(f"  Task IDs: {selected_task_ids}")
        print(f"  Total Impact Score: {total_impact}")

        Log("backend", "info", "cron_job", "Vehicle Maintenance Scheduler completed successfully")
        
    except Exception as e:
        Log("backend", "fatal", "cron_job", f"Scheduler failed: {str(e)}")
        print(f"[ERROR] {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()