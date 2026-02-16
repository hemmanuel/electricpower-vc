import json
import os

def manual_patch_founders():
    input_file = 'companies_scored_v3.json'
    output_file = 'companies_scored_v3.json'
    
    print(f"Loading {input_file}...")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            companies = json.load(f)
    except FileNotFoundError:
        print(f"Error: {input_file} not found.")
        return

    # --- MANUAL PATCH DATA ---
    patches = {
        "Terminus Industrials": [
            {
                "name": "Bridget Youngs",
                "role": "Founder",
                "bio": "Bridget Youngs is the Founder at Terminus Industrials. Previously, Bridget was the Founder at Falcon Point Advisors and also held positions at U.S. Department Of Labor, New Energy Capital, Evercore, JPMorgan Chase. Bridget received a High School degree from Incarnate Word High School. Rice Business: 2017 - 2018 | Rice University, Bachelor of Arts - BA (Mathematics): 2014 - 2017",
                "hometown": None,
                "linkedin_url": None,
                "twitter_url": None,
                "previous_companies": ["Falcon Point Advisors", "U.S. Department Of Labor", "New Energy Capital", "Evercore", "JPMorgan Chase"],
                "education": ["Rice Business", "Rice University"],
                "is_technical": False,
                "tags": ["Woman-Led"]
            }
        ],
        "Watt AI Inc.": [] # Explicitly set to empty as requested
    }

    patched_count = 0

    for company in companies:
        name = company.get('company_name')
        
        if name in patches:
            print(f"Patching {name}...")
            # Overwrite founders with manual data
            company['founders'] = patches[name]
            patched_count += 1

    if patched_count > 0:
        print(f"Saving {patched_count} patches to {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(companies, f, indent=2)
        print("Done.")
    else:
        print("No matching companies found to patch.")

if __name__ == "__main__":
    manual_patch_founders()
