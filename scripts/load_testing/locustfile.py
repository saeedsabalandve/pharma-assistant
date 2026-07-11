"""Locust load testing script for PharmaAssist API.

Tests various endpoints under load to validate
performance and identify bottlenecks.
"""

import random
import time
from typing import Any, Dict

from locust import HttpUser, between, task


class PharmaAssistUser(HttpUser):
    """Simulated user for load testing PharmaAssist API."""
    
    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)
    
    def on_start(self):
        """Setup before tests - authenticate if needed."""
        self.headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": f"load-test-{time.time()}",
        }
    
    @task(3)
    def drug_search(self):
        """Search for drugs."""
        queries = [
            "metformin",
            "aspirin",
            "lisinopril",
            "warfarin",
            "ibuprofen",
            "blood pressure",
            "diabetes medication",
            "pain relief",
        ]
        
        query = random.choice(queries)
        
        with self.client.get(
            f"/api/v1/drugs/search?q={query}&limit=10",
            headers=self.headers,
            name="/api/v1/drugs/search",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(2)
    def drug_detail(self):
        """Get drug details."""
        drug_ids = ["test-drug-1", "test-drug-2", "test-drug-3"]
        
        drug_id = random.choice(drug_ids)
        
        with self.client.get(
            f"/api/v1/drugs/{drug_id}",
            headers=self.headers,
            name="/api/v1/drugs/{id}",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(2)
    def interaction_check(self):
        """Check drug interactions."""
        drug_combinations = [
            {"drugs": ["warfarin", "aspirin"]},
            {"drugs": ["warfarin", "ibuprofen"]},
            {"drugs": ["lisinopril", "ibuprofen"]},
            {"drugs": ["metformin", "aspirin", "ibuprofen"]},
            {"drugs": ["warfarin", "aspirin", "ibuprofen"]},
        ]
        
        payload = random.choice(drug_combinations)
        
        with self.client.post(
            "/api/v1/interactions/check",
            json=payload,
            headers=self.headers,
            name="/api/v1/interactions/check",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(1)
    def assistant_query(self):
        """Query the virtual assistant."""
        queries = [
            {
                "query": "What are the side effects of metformin?",
                "context": {"age": 65, "conditions": ["type 2 diabetes"]},
            },
            {
                "query": "Can I take ibuprofen with lisinopril?",
                "context": {"age": 55, "conditions": ["hypertension"]},
            },
            {
                "query": "What is the best treatment for high blood pressure?",
                "context": None,
            },
        ]
        
        payload = random.choice(queries)
        
        with self.client.post(
            "/api/v1/assistant/query",
            json=payload,
            headers=self.headers,
            name="/api/v1/assistant/query",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(1)
    def treatment_recommendation(self):
        """Get treatment recommendations."""
        conditions = [
            {"diagnosis": "hypertension"},
            {"diagnosis": "type 2 diabetes"},
            {"diagnosis": "migraine"},
        ]
        
        payload = random.choice(conditions)
        payload["patient_factors"] = {
            "age": random.randint(25, 80),
            "gender": random.choice(["male", "female"]),
        }
        
        with self.client.post(
            "/api/v1/treatments/recommend",
            json=payload,
            headers=self.headers,
            name="/api/v1/treatments/recommend",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(1)
    def health_check(self):
        """Check health endpoints."""
        with self.client.get(
            "/health",
            headers=self.headers,
            name="/health",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
