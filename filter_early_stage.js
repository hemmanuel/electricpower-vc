const fs = require('fs');

const inputFile = 'companies_scored_v3.json';
const outputFile = 'companies_early_stage.json';

function parseRaised(raisedStr) {
    if (!raisedStr) return { val: 0, isUnknown: true };
    
    const s = raisedStr.toLowerCase();
    
    // Explicit exclusions
    if (s.includes('publicly traded') || s.includes('acquired') || s.includes('subsidiary')) {
        return { val: 999999999, isUnknown: false };
    }

    // Unknown/Bootstrapped
    if (s.includes('unknown') || s.includes('undisclosed') || s.includes('bootstrapped')) {
        return { val: 0, isUnknown: true };
    }

    // Extract numbers
    // Regex to find the first number in the string
    const match = s.match(/[\d,.]+/);
    if (!match) return { val: 0, isUnknown: true };

    let num = parseFloat(match[0].replace(/,/g, ''));
    
    // Multipliers
    if (s.includes('b') || s.includes('billion')) {
        num *= 1000000000;
    } else if (s.includes('m') || s.includes('million')) {
        num *= 1000000;
    } else if (s.includes('k') || s.includes('thousand')) {
        num *= 1000;
    } else {
        // If no suffix, assume it might be raw number if large, or millions if small? 
        // Actually, usually it has a symbol. 
        // Let's assume if it's < 1000 and no suffix, it might be millions if the context implies, 
        // but looking at the data, most have M/K.
        // If it's just "$500,000", the regex gets 500000.
        // If it's "$1.5", it might be 1.5M. But let's look at the data.
        // "$1.51M" -> 1.51 * 1000000
    }

    return { val: num, isUnknown: false };
}

function isEarlyStage(company) {
    const dossier = company.vc_dossier || {};
    const raisedStr = dossier.total_raised;
    const stage = company.stage_estimate || '';
    
    const { val, isUnknown } = parseRaised(raisedStr);
    
    // Threshold: $5M
    const THRESHOLD = 5000000;

    // If we have a valid number
    if (!isUnknown) {
        if (val < THRESHOLD) return true;
        return false;
    }

    // If unknown raised amount, check stage
    const stageLower = stage.toLowerCase();
    if (stageLower.includes('public') || 
        stageLower.includes('mature') || 
        stageLower.includes('late') || 
        stageLower.includes('growth') ||
        stageLower.includes('series b') ||
        stageLower.includes('series c') ||
        stageLower.includes('acquired')) {
        return false;
    }

    // If unknown raised and stage is not obviously late, keep it (e.g. Seed, Early, Unknown)
    return true;
}

try {
    const data = fs.readFileSync(inputFile, 'utf8');
    const companies = JSON.parse(data);
    
    const filtered = companies.filter(isEarlyStage);
    
    console.log(`Total companies: ${companies.length}`);
    console.log(`Filtered companies (<$5M raised): ${filtered.length}`);
    
    fs.writeFileSync(outputFile, JSON.stringify(filtered, null, 2));
    console.log(`Written to ${outputFile}`);

} catch (err) {
    console.error("Error:", err);
}
