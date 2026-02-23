require('dotenv').config();
const fs = require('fs');
const { GoogleGenerativeAI } = require("@google/generative-ai");

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-3.1-pro-preview" });

const categories = JSON.parse(fs.readFileSync('categories_raw.json', 'utf8'));
const enrichedCategories = [];

async function enrichCategory(category) {
    const prompt = `
    You are a Venture Capital analyst specializing in the Electric Power & Utilities sector.
    Provide a strategic overview for the startup category: "${category.name}".
    
    Context:
    - Number of companies in our dataset for this category: ${category.count}
    - Average AI Survivability Score (0-1): ${category.avg_ai_score.toFixed(2)} (Higher means more defensible against AI)
    - Average Market Depth Score (1-10): ${category.avg_market_score.toFixed(1)} (Higher means larger market/more room to pivot)
    - Example companies: ${category.companies.slice(0, 5).join(', ')}...

    Return a JSON object with the following fields:
    - "description": A 2-sentence definition of what this category entails in the context of modern power grids.
    - "ai_survivability_analysis": A 3-4 sentence analysis of why this category is or isn't defensible against AI commoditization. Mention if it relies on "atoms" (hardware/physical services) vs "bits" (software).
    - "market_pivotability": A 2-3 sentence assessment of the market size and whether a founder has room to pivot multiple times before finding product-market fit.
    - "vc_thesis": A 3-4 sentence investment thesis. Why should a VC invest here? What is the asymmetric upside? What are the major risks (e.g., regulatory, capital intensity)?
    - "hot_trends": An array of 3-4 short strings representing current buzzwords/trends in this specific category (e.g., "Virtual Power Plants", "Predictive Maintenance").

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
            ...category,
            ...data
        };
    } catch (error) {
        console.error(`Error enriching ${category.name}:`, error.message);
        return {
            ...category,
            description: "Analysis unavailable.",
            ai_survivability_analysis: "Analysis unavailable.",
            market_pivotability: "Analysis unavailable.",
            vc_thesis: "Analysis unavailable.",
            hot_trends: []
        };
    }
}

async function processBatch() {
    console.log("Starting category enrichment...");
    // Process all categories (small number, so can do sequentially or small batch)
    for (const category of categories) {
        if (category.name === "Other") continue; // Skip 'Other' or handle separately if needed
        console.log(`Processing ${category.name}...`);
        const result = await enrichCategory(category);
        enrichedCategories.push(result);
        // Small delay to be safe
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    // Sort by count or some other metric if desired, or keep original order
    enrichedCategories.sort((a, b) => b.count - a.count);

    fs.writeFileSync('categories_enriched.json', JSON.stringify(enrichedCategories, null, 2));
    console.log("Done! Saved to categories_enriched.json");
}

processBatch();
