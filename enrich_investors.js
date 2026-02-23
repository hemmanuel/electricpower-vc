require('dotenv').config();
const fs = require('fs');
const { GoogleGenerativeAI } = require("@google/generative-ai");

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-3.1-pro-preview" });

const investors = JSON.parse(fs.readFileSync('investors_raw.json', 'utf8'));
const enrichedInvestors = [];

async function enrichInvestor(investor) {
    const prompt = `
    You are a Venture Capital analyst. Provide a detailed profile for the investor "${investor.name}".
    They have invested in these companies from our dataset: ${investor.portfolio_companies.join(', ')}.

    Return a JSON object with the following fields:
    - "thesis": A 2-3 sentence summary of their investment focus, stage, and sectors (especially relevant to energy/climate/deeptech if applicable).
    - "other_investments": An array of strings listing 3-5 other well-known companies they have invested in (outside of the ones listed above, if known. If they are an angel or small fund and unknown, make a best guess based on their known portfolio or return empty).
    - "exits": An array of strings listing 2-3 successful exits (IPOs, acquisitions). If unknown, return empty array.
    - "value_add": A 2-3 sentence description of how they help portfolio companies (e.g., operational support, hiring, regulatory connections, specific domain expertise).
    
    Output ONLY valid JSON. Do not include markdown formatting.
    `;

    try {
        const result = await model.generateContent(prompt);
        const response = await result.response;
        const text = response.text();
        
        // Clean up markdown if present
        const jsonStr = text.replace(/```json/g, '').replace(/```/g, '').trim();
        const data = JSON.parse(jsonStr);
        
        return {
            ...investor,
            ...data
        };
    } catch (error) {
        console.error(`Error enriching ${investor.name}:`, error.message);
        return {
            ...investor,
            thesis: "Information unavailable.",
            other_investments: [],
            exits: [],
            value_add: "Information unavailable."
        };
    }
}

async function processBatch() {
    // Process in batches of 5 to respect rate limits
    const batchSize = 5;
    for (let i = 0; i < investors.length; i += batchSize) {
        const batch = investors.slice(i, i + batchSize);
        console.log(`Processing batch ${i / batchSize + 1} of ${Math.ceil(investors.length / batchSize)}...`);
        
        const promises = batch.map(investor => enrichInvestor(investor));
        const results = await Promise.all(promises);
        
        enrichedInvestors.push(...results);
        
        // Save progress
        fs.writeFileSync('investors_enriched.json', JSON.stringify(enrichedInvestors, null, 2));
        
        // Small delay
        await new Promise(resolve => setTimeout(resolve, 2000));
    }
    console.log("Done!");
}

processBatch();
