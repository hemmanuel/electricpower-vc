import json
import os

def restore_from_checkpoint():
    v3_file = 'companies_scored_v3.json'
    checkpoint_file = 'scripts/founders_enrichment_checkpoint.jsonl'
    
    print(f"Loading {v3_file}...")
    try:
        with open(v3_file, 'r', encoding='utf-8') as f:
            companies = json.load(f)
    except FileNotFoundError:
        print(f"Error: {v3_file} not found.")
        return

    # Create a lookup map for companies by name for faster access
    company_map = {c.get('company_name'): c for c in companies}
    
    print(f"Reading checkpoint from {checkpoint_file}...")
    if not os.path.exists(checkpoint_file):
        print("Checkpoint file not found.")
        return

    restored_count = 0
    with open(checkpoint_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                name = record.get('company_name')
                
                if name in company_map:
                    # Update the company record with data from checkpoint
                    company = company_map[name]
                    company['founders'] = record.get('founders', [])
                    company['company_twitter_url'] = record.get('company_twitter_url')
                    restored_count += 1
            except json.JSONDecodeError:
                continue
                
    print(f"Restored data for {restored_count} companies from checkpoint.")
    
    print(f"Saving updated data to {v3_file}...")
    with open(v3_file, 'w', encoding='utf-8') as f:
        json.dump(companies, f, indent=2)
    print("Done.")

if __name__ == "__main__":
    restore_from_checkpoint()
