import json
import os
import sys
import re
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# --- CONFIG ---
# Load .env from parent directory or current
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY not found in .env")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)
MODEL_ID = "gemini-3-flash-preview"

INPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'companies_scored_v2.json')
CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), 'founders_enrichment_checkpoint.jsonl')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'companies_scored_v3.json')

# --- HELPER FUNCTIONS ---
def extract_json(text: str):
    """
    Robustly extracts JSON from a string that might contain markdown code blocks.
    Supports both objects {} and lists [].
    """
    try:
        # Remove markdown code blocks if present
        if "```json" in text:
            matches = re.findall(r'```json\s*([\s\S]*?)\s*```', text)
            if matches:
                text = matches[0]
        elif "```" in text:
             matches = re.findall(r'```\s*([\s\S]*?)\s*```', text)
             if matches:
                text = matches[0]

        # Find the first opening brace/bracket
        start_index = -1
        for i, char in enumerate(text):
            if char in '{[':
                start_index = i
                break
        
        # Find the last closing brace/bracket (searching backwards)
        end_index = -1
        if start_index != -1:
            for i in range(len(text) - 1, start_index, -1):
                if text[i] in '}]':
                    end_index = i + 1
                    break
        
        if start_index != -1 and end_index != -1:
            json_str = text[start_index:end_index]
            return json.loads(json_str)
        else:
            # Fallback: try parsing the whole text
            return json.loads(text)

    except Exception as e:
        print(f"JSON Extraction Error: {e}")
        return None

def clean_url(url: Optional[str]) -> Optional[str]:
    """
    Sanitizes URLs by fixing common LLM typos (e.g., .corn -> .com).
    """
    if not url:
        return None
    
    # Common LLM typos for LinkedIn/Twitter
    cleaned = url.replace(".corn", ".com").replace(".con/", ".com/")
    
    # Ensure protocol
    if not cleaned.startswith("http"):
        cleaned = "https://" + cleaned
        
    return cleaned

def clean_twitter_url(url: Optional[str]) -> Optional[str]:
    """
    Sanitizes Twitter/X URLs.
    """
    if not url:
        return None
        
    cleaned = url.strip()
    
    # Normalize x.com to twitter.com
    cleaned = cleaned.replace("x.com", "twitter.com")
    
    # Remove mobile subdomains
    cleaned = cleaned.replace("mobile.twitter.com", "twitter.com")
    
    # Remove query parameters
    if "?" in cleaned:
        cleaned = cleaned.split("?")[0]
        
    # Ensure protocol
    if not cleaned.startswith("http"):
        cleaned = "https://" + cleaned
        
    return cleaned

# --- DATA MODELS ---
class FounderProfile(BaseModel):
    name: str = Field(description="Full name of the founder.")
    role: str = Field(description="Specific title, e.g. 'CEO & Co-founder'.")
    bio: str = Field(description="3-5-sentence backstory focusing on PRE-FOUNDING experience. Mention specific universities (e.g. RWTH Aachen), previous employers, or technical research topics. Identify if they are part of an underrepresented group. DO NOT merely state they founded this company.")
    hometown: Optional[str] = Field(description="City/Region of origin if mentioned (e.g. 'Originally from Mumbai', 'Native of Texas').", default=None)
    linkedin_url: Optional[str] = Field(description="LinkedIn URL if found.", default=None)
    twitter_url: Optional[str] = Field(description="Twitter/X URL if found.", default=None)
    previous_companies: List[str] = Field(description="List of significant employers prior to this startup, e.g., ['Google', 'McKinsey'].", default=[])
    education: List[str] = Field(description="List of universities and degrees, e.g., ['Stanford MBA', 'BS Computer Science, IIT'].", default=[])
    is_technical: bool = Field(description="True if bio/role indicates Engineering/Science background.")
    tags: List[str] = Field(
        description="Allowed Tags: ['Veteran', 'PhD', 'Woman-Led', 'BIPOC', 'Latino/a', 'Black-Founded', 'LGBTQ+', 'Immigrant', 'Serial Founder', 'Ex-Unicorn', 'Family-Owned']"
    )

class FounderList(BaseModel):
    founders: List[FounderProfile]

class FounderNames(BaseModel):
    names: List[str]

# --- CHECKPOINTING ---
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
                    continue
    return processed, completed_records

def save_record_to_checkpoint(record):
    """Appends a single record to the JSONL file."""
    with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + "\n")

# --- AGENT FUNCTION ---
def find_founders(company_name: str, company_dossier: dict) -> tuple[List[FounderProfile], Optional[str]]:
    """
    Uses a Two-Stage Agentic Workflow to find enriched founder profiles.
    Returns: (List[FounderProfile], company_twitter_url)
    """
    
    # --- STEP 1: DISCOVERY ---
    print(f"  > Step 1: Discovering founder names for {company_name}...")
    discovery_prompt = f"""
    Who are the founders of {company_name}? Also find the company's official Twitter/X handle if possible.
    
    Company Context:
    {json.dumps(company_dossier, indent=2)}
    
    Return ONLY a JSON object with this schema:
    {{ 
        "names": ["Name 1", "Name 2"],
        "company_twitter": "URL or null"
    }}
    """
    
    founder_names = []
    company_twitter = None
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=discovery_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearchRetrieval)],
            )
        )
        
        data = extract_json(response.text)
        if data:
            founder_names = data.get("names", [])
            company_twitter = clean_twitter_url(data.get("company_twitter"))
            print(f"  > Found {len(founder_names)} founders: {founder_names}")
            print(f"  > Company Twitter: {company_twitter}")
        else:
            print(f"  > Warning: No parsed response for {company_name}")
            return [], None

    except Exception as e:
        print(f"  > Error in discovery step: {e}")
        return [], None

    # --- STEP 2: ENRICHMENT LOOP ---
    enriched_profiles = []
    
    for name in founder_names:
        print(f"  > Step 2: Hunting for details on {name}...")
        
        # --- SUB-STEP 2A: IDENTITY RESOLUTION (THE "HUNTER") ---
        hunter_prompt = f"""
        Search Query: '{name} "{company_name}" linkedin twitter x.com'
        
        You are verifying the identity of **{name}**, a founder of **{company_name}**.
        
        1. **Extraction:** Extract the official LinkedIn and Twitter/X URLs for this person. 
        2. **Verification:** If the snippet looks like a different person (e.g., a 'Manager' when we are looking for a 'Founder', or someone in a completely different industry), return `null` for the URLs.
        3. **Twitter/X:** Look for Twitter or X.com handles (e.g. '(@handle)').
        
        Return a valid JSON object:
        {{
            "linkedin_url": "URL or null",
            "twitter_url": "URL or null"
        }}
        """
        
        linkedin_url = None
        twitter_url = None
        
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=hunter_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearchRetrieval)],
                )
            )
            
            hunter_data = extract_json(response.text)
            if hunter_data:
                linkedin_url = clean_url(hunter_data.get("linkedin_url"))
                twitter_url = clean_twitter_url(hunter_data.get("twitter_url"))
                print(f"    - Found URLs: LinkedIn={linkedin_url}, Twitter={twitter_url}")
        except Exception as e:
            print(f"    - Hunter failed for {name}: {e}")

        # --- SUB-STEP 2B: DEEP ENRICHMENT (THE "BIOGRAPHER") ---
        biographer_prompt = f"""
        Search Query: '{name} "{company_name}" biography interview education "born in" "native of"'
        
        Context found so far:
        - LinkedIn: {linkedin_url}
        - Twitter: {twitter_url}
        
        Using the search results (and the context above), write a detailed bio for **{name}**, a founder of **{company_name}**.
        
        1. **Bios:** Dig into their history. I want to know if they came from a specific lab, a big tech company, or a previous startup. I want to know their personal story as well.
        2. **Hometown:** Scan for mentions of origin (e.g., "grew up in", "native of", "originally from").
        3. **Experience & Education:** EXTRACT lists of previous employers and university degrees.
        4. **Tags:** Check for 'PhD', 'Veteran', 'Serial Founder', 'BIPOC', 'Woman-Led', 'Latino/a', 'Black-Founded', etc.
        
        Return a valid JSON object matching this schema:
        {{
            "name": "{name}",
            "role": "Title",
            "bio": "3-5-sentence backstory focusing on PRE-FOUNDING experience...",
            "hometown": "City/Region or null",
            "previous_companies": ["Company A", "Company B"],
            "education": ["University Degree 1", "University Degree 2"],
            "is_technical": boolean,
            "tags": ["Tag1", "Tag2"]
        }}
        """
        
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=biographer_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearchRetrieval)],
                )
            )
            
            bio_data = extract_json(response.text)
            
            if bio_data:
                # Merge Hunter and Biographer data
                profile = FounderProfile(
                    **bio_data,
                    linkedin_url=linkedin_url,
                    twitter_url=twitter_url
                )
                enriched_profiles.append(profile)
                print(f"    - Enriched {name} (Bio length: {len(profile.bio)})")
            else:
                print(f"    - Warning: No bio response for {name}")
                # Fallback with whatever we have
                enriched_profiles.append(FounderProfile(
                    name=name, 
                    role="Co-Founder", 
                    bio=f"Founder of {company_name}.", 
                    linkedin_url=linkedin_url,
                    twitter_url=twitter_url,
                    is_technical=False, 
                    tags=[]
                ))
            
        except Exception as e:
            print(f"    - Biographer failed for {name}: {e}")
            # Fallback
            enriched_profiles.append(FounderProfile(
                name=name, 
                role="Co-Founder", 
                bio=f"Founder of {company_name}.", 
                linkedin_url=linkedin_url,
                twitter_url=twitter_url,
                is_technical=False, 
                tags=[]
            ))

    # --- STEP 3: AGGREGATION ---
    return enriched_profiles, company_twitter

# --- MAIN LOOP ---
def main():
    print(f"Loading data from {INPUT_FILE}...")
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            companies = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file {INPUT_FILE} not found.")
        return

    processed_names, _ = load_checkpoint()
    
    # Filtering logic: Only companies with vc_dossier
    companies_to_process = [
        c for c in companies 
        if c.get('vc_dossier') and c['company_name'] not in processed_names
    ]
    
    print(f"Found {len(companies_to_process)} companies with VC Dossiers to process.")
    
    if not companies_to_process:
        print("No eligible companies found to process.")
        return

    # Process all eligible companies
    for i, company in enumerate(companies_to_process):
        name = company.get('company_name', 'Unknown')
        dossier = company.get('vc_dossier')
        
        print(f"\n--- Processing {i+1}/{len(companies_to_process)}: {name} ---")
        founders, company_twitter = find_founders(name, dossier)
        
        # Update the company record
        # Convert Pydantic models to dicts
        founders_data = [f.model_dump() for f in founders]
        company['founders'] = founders_data
        company['company_twitter_url'] = company_twitter
        
        # Print result summary
        print(f"  > Saved {len(founders)} founders. Twitter: {company_twitter}")
        
        # Save checkpoint
        save_record_to_checkpoint({
            'company_name': name, 
            'founders': founders_data,
            'company_twitter_url': company_twitter
        })
        
        # Periodic save to main file (every 10 records) to prevent data loss
        if (i + 1) % 10 == 0:
            print(f"  > Saving progress to {OUTPUT_FILE}...")
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(companies, f, indent=2)
    
    # Save back to main file (Update the specific record in the original list)
    # We need to update the original 'companies' list. 
    # Since 'company' is a reference to a dict in 'companies', it is already updated in memory.
    # We just need to write 'companies' back to file.
    
    print(f"\nUpdating {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(companies, f, indent=2)
    print("Done.")

if __name__ == "__main__":
    main()
