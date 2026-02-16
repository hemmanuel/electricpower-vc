import json
import os

def audit_founders():
    input_file = 'companies_scored_v3.json'
    failed_output_file = 'failed_founders.json'
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            companies = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return

    total_companies = len(companies)
    companies_with_founders = 0
    companies_founders_empty = 0
    companies_founders_missing = 0
    total_founders = 0
    founders_with_linkedin = 0
    failed_companies = []

    for company in companies:
        if 'founders' not in company:
            companies_founders_missing += 1
            # failed_companies.append(company) # Optional: do we count missing as failed?
            continue
            
        founders = company['founders']
        
        if founders and len(founders) > 0:
            companies_with_founders += 1
            for founder in founders:
                total_founders += 1
                if founder.get('linkedin_url'):
                    founders_with_linkedin += 1
        else:
            companies_founders_empty += 1
            failed_companies.append(company)

    # Calculate fill rate
    linkedin_fill_rate = 0
    if total_founders > 0:
        linkedin_fill_rate = (founders_with_linkedin / total_founders) * 100

    print("=== Founder Data Audit Results ===")
    print(f"Total Companies Processed: {total_companies}")
    print(f"Companies with Founders Populated: {companies_with_founders}")
    print(f"Companies with Empty Founders List (Attempted & Failed): {companies_founders_empty}")
    print(f"Companies with Founders Key Missing (Not Attempted): {companies_founders_missing}")
    print(f"Total Founders Found: {total_founders}")
    print(f"Founders with LinkedIn URL: {founders_with_linkedin}")
    print(f"LinkedIn URL Fill Rate: {linkedin_fill_rate:.2f}%")
    
    # Save failed companies
    try:
        with open(failed_output_file, 'w', encoding='utf-8') as f:
            json.dump(failed_companies, f, indent=2)
        print(f"\nFailed companies saved to {failed_output_file}")
    except Exception as e:
        print(f"Error saving failed companies: {e}")

if __name__ == "__main__":
    audit_founders()
