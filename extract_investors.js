const fs = require('fs');

// Read the enriched companies file
const companies = JSON.parse(fs.readFileSync('companies_enriched.json', 'utf8'));

const investorsMap = {};

companies.forEach(company => {
    // Check if vc_dossier and key_investors exist
    if (company.vc_dossier && company.vc_dossier.key_investors) {
        // Split investors by comma, handle potential variations
        const investors = company.vc_dossier.key_investors.split(/,|;/).map(i => i.trim()).filter(i => i && i.toLowerCase() !== 'undisclosed' && i.toLowerCase() !== 'unknown');
        
        investors.forEach(investor => {
            if (!investorsMap[investor]) {
                investorsMap[investor] = {
                    name: investor,
                    portfolio_companies: []
                };
            }
            investorsMap[investor].portfolio_companies.push(company.name);
        });
    } else if (company.meta && company.meta['Key Investors']) {
         // Fallback to meta if vc_dossier is missing but meta exists (though meta is usually derived from dossier)
         const investors = company.meta['Key Investors'].split(/,|;/).map(i => i.trim()).filter(i => i && i.toLowerCase() !== 'undisclosed' && i.toLowerCase() !== 'unknown');
         
         investors.forEach(investor => {
            if (!investorsMap[investor]) {
                investorsMap[investor] = {
                    name: investor,
                    portfolio_companies: []
                };
            }
            // Avoid duplicates if both fields exist and are processed (though logic above is if/else)
            if (!investorsMap[investor].portfolio_companies.includes(company.name)) {
                investorsMap[investor].portfolio_companies.push(company.name);
            }
        });
    }
});

// Convert map to array
const investorsArray = Object.values(investorsMap).sort((a, b) => b.portfolio_companies.length - a.portfolio_companies.length);

console.log(`Found ${investorsArray.length} unique investors.`);

fs.writeFileSync('investors_raw.json', JSON.stringify(investorsArray, null, 2));
