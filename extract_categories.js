const fs = require('fs');

const companies = JSON.parse(fs.readFileSync('companies_enriched.json', 'utf8'));

const categories = {};

companies.forEach(c => {
    // Use l1 as the main category
    const cat = c.taxonomy?.l1 || c.primary_sector || "Other";
    
    if (!categories[cat]) {
        categories[cat] = {
            name: cat,
            count: 0,
            companies: [],
            avg_ai_score: 0,
            avg_market_score: 0
        };
    }
    
    categories[cat].count++;
    categories[cat].companies.push(c.name);
    categories[cat].avg_ai_score += (c.strategic_analysis?.ai_survival_score || 0);
    categories[cat].avg_market_score += (c.strategic_analysis?.market_depth_score || 0);
});

// Calculate averages
Object.keys(categories).forEach(k => {
    categories[k].avg_ai_score = categories[k].avg_ai_score / categories[k].count;
    categories[k].avg_market_score = categories[k].avg_market_score / categories[k].count;
});

console.log(JSON.stringify(Object.keys(categories), null, 2));

// Save the raw category data to be enriched
fs.writeFileSync('categories_raw.json', JSON.stringify(Object.values(categories), null, 2));
