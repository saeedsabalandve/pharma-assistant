#!/usr/bin/env python3
"""Database seeding script for PharmaAssist.

Populates databases with sample drug data, interactions,
and treatment protocols for development and testing.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

import structlog

from src.infrastructure.databases.mongodb import MongoDBClient
from src.infrastructure.databases.postgres import PostgresClient
from src.infrastructure.search.opensearch import OpenSearchClient
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Sample Data
# ---------------------------------------------------------------------------

SAMPLE_DRUGS: List[Dict[str, Any]] = [
    {
        "name": "Metformin",
        "generic_name": "metformin hydrochloride",
        "brand_names": ["Glucophage", "Fortamet", "Glumetza"],
        "category": "prescription",
        "drug_class": "Biguanide",
        "description": "First-line medication for the treatment of type 2 diabetes",
        "indications": ["Type 2 diabetes mellitus", "Polycystic ovary syndrome"],
        "contraindications": [
            "Severe renal impairment (eGFR < 30 mL/min)",
            "Acute or chronic metabolic acidosis",
            "History of lactic acidosis",
        ],
        "side_effects": [
            {"effect": "Gastrointestinal upset", "frequency": "Common"},
            {"effect": "Diarrhea", "frequency": "Common"},
            {"effect": "Nausea", "frequency": "Common"},
            {"effect": "Vitamin B12 deficiency", "frequency": "Uncommon"},
            {"effect": "Lactic acidosis", "frequency": "Rare but serious"},
        ],
        "dosage_forms": [
            {"form": "Tablet", "strengths": ["500mg", "850mg", "1000mg"]},
            {"form": "Extended-release tablet", "strengths": ["500mg", "750mg"]},
        ],
        "manufacturer": "Various",
        "fda_approved": True,
        "pregnancy_category": "B",
        "references": [
            {"title": "ADA Standards of Medical Care in Diabetes", "year": "2024"},
        ],
    },
    {
        "name": "Lisinopril",
        "generic_name": "lisinopril",
        "brand_names": ["Prinivil", "Zestril"],
        "category": "prescription",
        "drug_class": "ACE Inhibitor",
        "description": "ACE inhibitor used to treat high blood pressure and heart failure",
        "indications": ["Hypertension", "Heart failure", "Post-MI"],
        "contraindications": [
            "History of angioedema",
            "Bilateral renal artery stenosis",
            "Pregnancy",
        ],
        "side_effects": [
            {"effect": "Dry cough", "frequency": "Common"},
            {"effect": "Dizziness", "frequency": "Common"},
            {"effect": "Hyperkalemia", "frequency": "Uncommon"},
            {"effect": "Angioedema", "frequency": "Rare but serious"},
        ],
        "dosage_forms": [
            {"form": "Tablet", "strengths": ["2.5mg", "5mg", "10mg", "20mg", "40mg"]},
        ],
        "manufacturer": "Various",
        "fda_approved": True,
        "pregnancy_category": "D",
        "references": [],
    },
    {
        "name": "Warfarin",
        "generic_name": "warfarin sodium",
        "brand_names": ["Coumadin", "Jantoven"],
        "category": "prescription",
        "drug_class": "Anticoagulant",
        "description": "Vitamin K antagonist used to prevent blood clots",
        "indications": [
            "Atrial fibrillation",
            "Deep vein thrombosis",
            "Pulmonary embolism",
            "Mechanical heart valves",
        ],
        "contraindications": [
            "Active bleeding",
            "Severe thrombocytopenia",
            "Pregnancy (first trimester)",
            "Recent surgery",
        ],
        "side_effects": [
            {"effect": "Bleeding", "frequency": "Common"},
            {"effect": "Skin necrosis", "frequency": "Rare"},
            {"effect": "Purple toe syndrome", "frequency": "Rare"},
        ],
        "dosage_forms": [
            {"form": "Tablet", "strengths": ["1mg", "2mg", "2.5mg", "3mg", "4mg", "5mg", "6mg", "7.5mg", "10mg"]},
        ],
        "manufacturer": "Various",
        "fda_approved": True,
        "pregnancy_category": "X",
        "references": [],
    },
    {
        "name": "Aspirin",
        "generic_name": "acetylsalicylic acid",
        "brand_names": ["Bayer", "Ecotrin", "Bufferin"],
        "category": "otc",
        "drug_class": "NSAID / Antiplatelet",
        "description": "Nonsteroidal anti-inflammatory drug with antiplatelet effects",
        "indications": [
            "Pain relief",
            "Fever reduction",
            "Cardiovascular prevention",
            "Anti-inflammatory",
        ],
        "contraindications": [
            "Active peptic ulcer",
            "Bleeding disorders",
            "Aspirin allergy",
            "Children with viral illness (Reye's syndrome risk)",
        ],
        "side_effects": [
            {"effect": "Gastrointestinal irritation", "frequency": "Common"},
            {"effect": "Increased bleeding time", "frequency": "Common"},
            {"effect": "Tinnitus", "frequency": "Dose-related"},
            {"effect": "GI bleeding", "frequency": "Uncommon"},
        ],
        "dosage_forms": [
            {"form": "Tablet", "strengths": ["81mg", "325mg", "500mg"]},
            {"form": "Chewable tablet", "strengths": ["81mg"]},
        ],
        "manufacturer": "Bayer",
        "fda_approved": True,
        "pregnancy_category": "C",
        "references": [],
    },
    {
        "name": "Ibuprofen",
        "generic_name": "ibuprofen",
        "brand_names": ["Advil", "Motrin"],
        "category": "otc",
        "drug_class": "NSAID",
        "description": "Nonsteroidal anti-inflammatory drug for pain and inflammation",
        "indications": ["Pain", "Fever", "Inflammation", "Arthritis"],
        "contraindications": [
            "Active peptic ulcer",
            "Severe heart failure",
            "Severe renal impairment",
            "History of GI bleeding",
        ],
        "side_effects": [
            {"effect": "GI upset", "frequency": "Common"},
            {"effect": "Headache", "frequency": "Common"},
            {"effect": "Fluid retention", "frequency": "Uncommon"},
            {"effect": "GI bleeding", "frequency": "Uncommon"},
        ],
        "dosage_forms": [
            {"form": "Tablet", "strengths": ["200mg", "400mg", "600mg", "800mg"]},
            {"form": "Liquid", "strengths": ["100mg/5mL"]},
        ],
        "manufacturer": "Various",
        "fda_approved": True,
        "pregnancy_category": "C",
        "references": [],
    },
]

SAMPLE_INTERACTIONS: List[Dict[str, Any]] = [
    {
        "drug_a": "warfarin",
        "drug_b": "aspirin",
        "severity": "major",
        "interaction_type": "pharmacodynamic",
        "description": "Increased risk of bleeding due to additive anticoagulant and antiplatelet effects",
        "mechanism": "Aspirin inhibits platelet aggregation and can cause GI bleeding; warfarin inhibits clotting factors",
        "clinical_management": "Monitor INR closely; consider alternative analgesics; use gastroprotection if combined",
        "evidence_level": "Well-established",
        "references": [{"title": "Clinical Pharmacology", "source": "FDA"}],
    },
    {
        "drug_a": "warfarin",
        "drug_b": "ibuprofen",
        "severity": "major",
        "interaction_type": "pharmacokinetic",
        "description": "Increased INR and bleeding risk; NSAIDs can displace warfarin from protein binding",
        "mechanism": "NSAIDs inhibit CYP2C9 metabolism of S-warfarin and displace from albumin",
        "clinical_management": "Avoid combination if possible; if necessary, monitor INR frequently",
        "evidence_level": "Well-established",
        "references": [],
    },
    {
        "drug_a": "lisinopril",
        "drug_b": "ibuprofen",
        "severity": "moderate",
        "interaction_type": "pharmacodynamic",
        "description": "NSAIDs may decrease antihypertensive effect of ACE inhibitors",
        "mechanism": "NSAIDs inhibit prostaglandin synthesis, reducing vasodilation and increasing sodium retention",
        "clinical_management": "Monitor blood pressure; consider alternative analgesics",
        "evidence_level": "Well-established",
        "references": [],
    },
    {
        "drug_a": "aspirin",
        "drug_b": "ibuprofen",
        "severity": "moderate",
        "interaction_type": "pharmacodynamic",
        "description": "Ibuprofen may interfere with antiplatelet effect of low-dose aspirin",
        "mechanism": "Ibuprofen competes with aspirin for COX-1 binding site",
        "clinical_management": "Take ibuprofen at least 2 hours after aspirin; consider alternative analgesics",
        "evidence_level": "Moderate",
        "references": [{"title": "FDA Drug Safety Communication", "year": "2022"}],
    },
]

SAMPLE_PROTOCOLS: List[Dict[str, Any]] = [
    {
        "condition": "hypertension",
        "treatment_name": "JNC 8 Hypertension Protocol",
        "category": "pharmacological",
        "description": "Initial treatment with thiazide diuretic, ACE inhibitor, ARB, or calcium channel blocker",
        "first_line": ["Thiazide diuretics", "ACE inhibitors", "ARBs", "Calcium channel blockers"],
        "alternatives": ["Beta blockers (not first-line unless compelling indication)"],
        "monitoring": ["Blood pressure every 2-4 weeks until controlled", "Renal function", "Electrolytes"],
        "evidence_level": "A",
        "guideline_source": "JNC 8 / ACC/AHA 2017",
    },
    {
        "condition": "type 2 diabetes",
        "treatment_name": "ADA Diabetes Treatment Algorithm",
        "category": "pharmacological",
        "description": "First-line metformin plus lifestyle modifications; add second agent based on patient factors",
        "first_line": ["Metformin", "Lifestyle modifications (diet, exercise)"],
        "second_line": ["SGLT2 inhibitors", "GLP-1 receptor agonists", "DPP-4 inhibitors", "Sulfonylureas"],
        "monitoring": ["HbA1c every 3 months", "Renal function", "Blood glucose monitoring"],
        "evidence_level": "A",
        "guideline_source": "American Diabetes Association 2024",
    },
]


# ---------------------------------------------------------------------------
# Seeding Functions
# ---------------------------------------------------------------------------

async def seed_postgres() -> None:
    """Seed PostgreSQL with drug data."""
    logger.info("seeding_postgres")
    
    async with PostgresClient.session() as session:
        from sqlalchemy import text
        
        for drug in SAMPLE_DRUGS:
            drug_id = str(uuid4())
            
            await session.execute(
                text("""
                    INSERT INTO drugs (drug_id, name, generic_name, category, 
                    drug_class, description, manufacturer, fda_approved, 
                    pregnancy_category, created_at, updated_at)
                    VALUES (:drug_id, :name, :generic_name, :category,
                    :drug_class, :description, :manufacturer, :fda_approved,
                    :pregnancy_category, :created_at, :updated_at)
                    ON CONFLICT (name) DO UPDATE SET updated_at = :updated_at
                """),
                {
                    "drug_id": drug_id,
                    "name": drug["name"],
                    "generic_name": drug["generic_name"],
                    "category": drug["category"],
                    "drug_class": drug["drug_class"],
                    "description": drug["description"],
                    "manufacturer": drug["manufacturer"],
                    "fda_approved": drug["fda_approved"],
                    "pregnancy_category": drug["pregnancy_category"],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            )
        
        await session.commit()
    
    logger.info("postgres_seeded", drugs_count=len(SAMPLE_DRUGS))


async def seed_mongodb() -> None:
    """Seed MongoDB with detailed drug documents."""
    logger.info("seeding_mongodb")
    
    collection = MongoDBClient.get_collection("drug_details")
    
    for drug in SAMPLE_DRUGS:
        await collection.update_one(
            {"name": drug["name"]},
            {"$set": {
                "indications": drug.get("indications", []),
                "contraindications": drug.get("contraindications", []),
                "side_effects": drug.get("side_effects", []),
                "dosage_forms": drug.get("dosage_forms", []),
                "warnings": drug.get("warnings", []),
                "references": drug.get("references", []),
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )
    
    logger.info("mongodb_seeded")


async def seed_opensearch() -> None:
    """Seed OpenSearch with drug and interaction indices."""
    logger.info("seeding_opensearch")
    
    # Create indices
    await OpenSearchClient.create_index("drugs")
    await OpenSearchClient.create_index("drug_interactions")
    await OpenSearchClient.create_index("treatment_protocols")
    
    # Index drugs
    for drug in SAMPLE_DRUGS:
        await OpenSearchClient.index_document(
            index="drugs",
            document={
                "drug_id": str(uuid4()),
                "name": drug["name"],
                "generic_name": drug["generic_name"],
                "brand_names": drug.get("brand_names", []),
                "category": drug["category"],
                "drug_class": drug["drug_class"],
                "active_ingredient": drug.get("generic_name"),
                "indications": drug.get("indications", []),
                "fda_approved": drug["fda_approved"],
                "pregnancy_category": drug.get("pregnancy_category"),
            },
        )
    
    # Index interactions
    for interaction in SAMPLE_INTERACTIONS:
        await OpenSearchClient.index_document(
            index="drug_interactions",
            document={
                "interaction_id": str(uuid4()),
                **interaction,
            },
        )
    
    # Index protocols
    for protocol in SAMPLE_PROTOCOLS:
        await OpenSearchClient.index_document(
            index="treatment_protocols",
            document={
                "protocol_id": str(uuid4()),
                **protocol,
            },
        )
    
    logger.info(
        "opensearch_seeded",
        drugs=len(SAMPLE_DRUGS),
        interactions=len(SAMPLE_INTERACTIONS),
        protocols=len(SAMPLE_PROTOCOLS),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run all seeding operations."""
    logger.info("starting_data_seeding")
    
    try:
        # Initialize connections
        settings = get_settings()
        
        await PostgresClient.initialize(
            dsn=settings.postgres_dsn,
            min_size=2,
            max_size=5,
        )
        
        await MongoDBClient.initialize(
            uri=settings.MONGODB_URI,
            database=settings.MONGODB_DB,
        )
        
        await OpenSearchClient.initialize()
        
        # Run seeding
        await seed_postgres()
        await seed_mongodb()
        await seed_opensearch()
        
        logger.info("data_seeding_completed_successfully")
        
    except Exception as exc:
        logger.exception("data_seeding_failed", error=str(exc))
        sys.exit(1)
    finally:
        await PostgresClient.close()
        await MongoDBClient.close()


if __name__ == "__main__":
    asyncio.run(main())
