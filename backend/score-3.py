import json
import os
import time
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tqdm import tqdm

# --- CONFIG ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY: raise ValueError("API Key not found in .env")

client = genai.Client(api_key=API_KEY)
MODEL_ID = "models/gemini-3-flash-preview"

INPUT_FILE = "companies_enriched.json"  # Change to companies_enriched.json
DIMENSIONS_FILE = "latent_dimensions.json"
CHECKPOINT_FILE = "companies_scored_checkpoint.jsonl"  # The safety file
FINAL_OUTPUT_FILE = "companies_scored_v2.json"
SAVE_INTERVAL = 5  # Update the JSON file every N records so you can explore while running


# --- SCHEMAS ---
class DimensionScore(BaseModel):
    name: str = Field(description="The exact name of the dimension from the rubric.")
    score: Optional[float] = Field(description="0.0-1.0 or null if irrelevant.")


class CompanyScoringResult(BaseModel):
    scores_list: List[DimensionScore] = Field(description="List of scores.")
    venture_scale_score: float = Field(description="0.0 to 1.0")
    stage_estimate: str = Field(description="Estimate: Pre-Seed, Seed, Series A, etc.")
    rationale: str = Field(description="2-sentence summary.")

    # TAXONOMY (Added for Sunburst Chart)
    category_l1: Literal[
        "Grid Infrastructure (Hardware)",
        "Grid Operations & Software (SaaS)",
        "Enterprise & Corporate Systems",
        "Field Operations & Services",
        "Distributed Energy (DERs) & Edge",
        "Generation & Storage",
        "Professional Services & Engineering",  # Added
        "Energy Markets & Trading",  # Added
        "Other"
    ] = Field(description="Top-level category from the provided list.")

    category_l2: str = Field(description="Mid-level sector (e.g. 'Transmission', 'Cybersecurity', 'Vegetation Mgmt').")
    category_l3: str = Field(description="Specific niche (e.g. 'Composite Poles', 'Generative AI', 'Li-Ion Battery').")


class CompanyDossier(BaseModel):
    hq_location: str = Field(description="City, State, Country")
    year_founded: str = Field(description="YYYY")
    headcount_estimate: str = Field(description="e.g. '11-50'")
    corporate_status: str = Field(description="'Independent', 'Public', or 'Acquired'")

    # The Narrative
    plain_english_summary: str = Field(description="Jargon-free explanation.")
    macro_trend: str = Field(description="The 'Why Now' driver.")
    analogy: str = Field(description="Business model analogy.")

    # Thesis
    moat_description: str = Field(description="Defensibility source.")
    total_raised: str = Field(description="Total raised or 'Unknown'.")
    latest_round: str = Field(description="Details of most recent round.")
    key_investors: str = Field(description="List of investors.")
    key_customers: str = Field(description="Major partners.")
    source_urls: List[str] = Field(description="List of URLs.")


# --- HELPERS ---
def load_checkpoint():
    """Reads the JSONL file and returns a list of processed company names."""
    processed = set()
    completed_records = []

    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    processed.add(data['company_name'])
                    completed_records.append(data)
                except json.JSONDecodeError:
                    continue  # Skip partial lines

    return processed, completed_records


def save_record_to_checkpoint(record):
    """Appends a single record to the JSONL file."""
    with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + "\n")


# --- MAIN ENGINE ---
def run_scoring_pipeline():
    # 1. Validation
    if not os.path.exists(INPUT_FILE) or not os.path.exists(DIMENSIONS_FILE):
        print(f"CRITICAL ERROR: Missing inputs.")
        return

    # 2. Load Dimensions (Rubric)
    with open(DIMENSIONS_FILE, 'r', encoding='utf-8') as f:
        dims_data = json.load(f)
        dimensions = dims_data.get("dimensions", [])

    # Construct Master Rubric
    rubric_text = ""
    for i, d in enumerate(dimensions):
        rubric_text += f"### {i + 1}. {d['name']}\n- Description: {d['description']}\n- Low (0.0): {d['low_value_label']}\n- High (1.0): {d['high_value_label']}\n"

    # 3. Load & Resume Logic
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        all_companies = json.load(f)

    processed_names, current_results = load_checkpoint()

    print(f"Total Companies: {len(all_companies)}")
    print(f"Already Processed: {len(processed_names)}")

    # Filter the list
    companies_to_do = [c for c in all_companies if c.get('company_name') not in processed_names]
    print(f"Remaining to Process: {len(companies_to_do)}")

    if len(companies_to_do) == 0:
        print("All done! generating final JSON...")
        with open(FINAL_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_results, f, indent=2)
        return

    # 4. Processing Loop
    print(f"Starting analysis with {MODEL_ID}...")

    for i, company in enumerate(tqdm(companies_to_do)):
        try:
            # --- PHASE 1: SCORING & CLASSIFICATION ---
            # --- HYBRID PROMPT (Script 1 Logic + Script 2 Taxonomy) ---
            prompt = f"""
            You are a Deep Tech Venture Capital Analyst.
            Analyze the following company to determine its "Investment DNA".

            COMPANY PROFILE:
            Name: {company.get('company_name')}
            Pitch: {company.get('pitch_summary')}
            Description: {company.get('full_description')[:1500]} 

            TASK 1: DIMENSION SCORING (with Relevance Gating)
            For each of the strategic dimensions provided in the rubric, assign a score (0.0 to 1.0) OR null.

            **RUBRIC:**
            {rubric_text}

            **RELEVANCE RULE (CRITICAL):**
            - **Strictly apply `null`** if a dimension is structurally irrelevant to the company's core value proposition.
            - Examples:
              - "Voltage Magnitude" is `null` for a Recruiting Firm or Financial Software.
              - "Storage Physics" is `null` for a Grid Analytics platform that doesn't make batteries.
            - **DO NOT** default to "0.5" for irrelevance. Use `null`.

            TASK 2: VENTURE ASSESSMENT (The Gatekeeper Rule)
            1. **Venture Scale Score (0.0 to 1.0):**
               - **0.0 - 0.3 (INCUMBENT/NON-VC):** Public companies (e.g., ABB, Siemens), Linear Service/Lifestyle Businesses (Consultancies, EPC, Construction, Staffing), or subsidiaries. Low leverage.
               - **0.4 - 0.6 (SME/STEADY STATE):** High-quality businesses that lack 10x growth potential or asymmetric venture upside.
               - **0.7 - 1.0 (VENTURE SCALE):** High-Growth Venture Play (Software Platform, IP-Heavy Hard Tech, Network Effects). High leverage.
            2. **Stage Estimate:**
               - Choose best fit: ["Pre-Seed", "Seed", "Series A", "Growth", "Public/Mature", "Unknown"]

            TASK 3: INVESTMENT REASONING
            **Venture Thesis: Identify the primary venture upside. If the company is structurally unfit for venture capital (e.g., an incumbent or service business), explicitly state: "N/A - This is a [Public Incumbent/Service Business] and does not fit a venture portfolio."
            **Venture Red Flags: > * If NOT a candidate: Explain the structural disqualifiers in detail (e.g., "Company is a $100B global incumbent; growth is tied to market cycles rather than disruptive scale").
            **If it IS a candidate: List the specific hurdles/risks (e.g., "High technical risk in the power electronics," "Long utility sales cycles," "Intense competition from incumbents").
            **Rationale: 2-sentence synthesis. Justify the score by reconciling the Thesis vs. the Red Flags.

            TASK 4: CATEGORIZATION (For a Sunburst Chart)
            - **Level 1:** Pick ONE from: 
              ["Grid Infrastructure (Hardware)", "Grid Operations & Software (SaaS)", "Enterprise & Corporate Systems", "Field Operations & Services", "Distributed Energy (DERs) & Edge", "Generation & Storage", "Professional Services & Engineering", "Energy Markets & Trading", "Other"]
            - **Level 2:** Define the Sector (e.g. "Transmission", "Cybersecurity", "Vegetation Mgmt").
            - **Level 3:** Define the Specific Niche (e.g. "Composite Poles", "Generative AI", "Li-Ion Battery").
            """

            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CompanyScoringResult
                )
            )
            result = response.parsed

            # Helper: List -> Dict
            scores_dict = {item.name: item.score for item in result.scores_list}

            record = company.copy()
            record['dimension_scores'] = scores_dict
            record['venture_scale_score'] = result.venture_scale_score
            record['stage_estimate'] = result.stage_estimate
            record['rationale'] = result.rationale

            # Save Taxonomy structure
            record['taxonomy'] = {
                "l1": result.category_l1,
                "l2": result.category_l2,
                "l3": result.category_l3
            }

            # --- PHASE 2: SEARCH (Conditional) ---
            dossier_data = None
            if result.venture_scale_score > 0.6:
                print(f"\n   -> High Venture Potential ({result.venture_scale_score}). Generating Dossier...")

                search_prompt = f"""
                Research the corporate profile and funding history for {company.get('company_name')}.
                Use Google Search to build a "Pre-Meeting One-Pager" for a Generalist VC Partner who is new to the energy sector.

                Find the following specific details:

                ### 1. VITAL SIGNS (Scale & Status)
                - **HQ Location:** City, State, Country.
                - **Year Founded:** Launch year (YYYY).
                - **Headcount Estimate:** Current employee count (e.g. "11-50" or "~200").
                - **Corporate Status:** Independent, Public, or Acquired? (Crucial: Filter out "Zombie" brands).
                - **Estimated Annual Revenue:** Provide the most recent annual revenue figure (e.g., "$14.2M" or "$82B"). If private, provide an estimate based on recent news/funding or state "Undisclosed".

                ### 2. THE NARRATIVE (Translation Layer)
                - **Plain English One-Liner:** Explain what they do without using industry jargon (e.g., instead of "DERMS optimization," say "Software that acts as Air Traffic Control for solar panels").
                - **The "Why Now?":** What macro trend makes this relevant *today*? (e.g. "Wildfire liability," "AI power demand," "Electrification of Everything").
                - **The Analogy:** If applicable, provide a "X for Energy" analogy (e.g. "The Salesforce for Utility Assets" or "The Intel Inside for Power Grids").

                ### 3. VENTURE SUITABILITY (Thesis vs. Red Flags)
                - **Venture Thesis:** Identify the primary reason a VC would invest (e.g., "First-mover in Long-duration Storage," "Proprietary AI for Grid Balancing").
                - **Venture Red Flags:** Identify "Deal Killers" for a venture fund (e.g., "Publicly traded conglomerate," "Overly reliant on government grants," "Low-margin service business," "Crowded market with zero differentiation").

                ### 4. THE INVESTMENT DETAILS (Moat & Traction)
                - **The Moat:** What makes this defensible? (e.g. "Patented Hardware," "Proprietary Data," "Network Effects," "High Switching Costs").
                - **Total Capital Raised:** (e.g. "$14M", "Bootstrapped", "Publicly Traded", or "Undisclosed").
                - **Latest Round:** (e.g. "Series A in 2024", "Grant", "Share Buyback").
                - **Key Investors:** List specific investors found (VCs, CVCs, Angels, or Institutional like BlackRock). Do not filter for "notable" only.
                - **Key Customers:** Mention 1-2 major pilots, contracts, or target sectors (Proof of fit).

                **CRITICAL INSTRUCTIONS:**
                - **CITATIONS:** You MUST retain source URLs for every fact found.
                - **HONESTY:** If funding/moat/revenue is not public, state "Unknown".
                - **NO JARGON:** The partner does not know what "SCADA", "Phasor", or "DERMS" means. Simplify and define concepts.
                - **CONTEXT:** If the company is a massive public incumbent (like ABB), your Narrative and Thesis must reflect that it is a 'market standard' or 'hardware giant' rather than a high-growth startup.
                """

                search_res = client.models.generate_content(
                    model=MODEL_ID,
                    contents=search_prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        response_mime_type="application/json",
                        response_schema=CompanyDossier
                    )
                )
                dossier_data = search_res.parsed.model_dump()
                time.sleep(1.0)

            record['vc_dossier'] = dossier_data

            # --- SAVE IMMEDIATELY ---
            save_record_to_checkpoint(record)
            current_results.append(record)

            # --- AUTO-UPDATE JSON ---
            # Update immediately if it's a Venture Target (so we can see them ASAP) OR every SAVE_INTERVAL
            if result.venture_scale_score > 0.6 or (i + 1) % SAVE_INTERVAL == 0:
                with open(FINAL_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(current_results, f, indent=2)

            time.sleep(2.0)

        except Exception as e:
            print(f"\nFAILED on {company.get('company_name', 'Unknown')}: {str(e)}")
            if "429" in str(e):
                print("Hit Rate Limit. Sleeping 10s...")
                time.sleep(10)
            pass

    # 5. Finalize
    print("\nBatch Complete. Writing final JSON structure...")
    with open(FINAL_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(current_results, f, indent=2)
    print(f"DONE. Output saved to {FINAL_OUTPUT_FILE}")


if __name__ == "__main__":
    run_scoring_pipeline()