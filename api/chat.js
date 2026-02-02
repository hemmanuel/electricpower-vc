exports.handler = async function(event, context) {
    // Only allow POST requests
    if (event.httpMethod !== "POST") {
        return { statusCode: 405, body: "Method Not Allowed" };
    }

    try {
        const { prompt } = JSON.parse(event.body);
        const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

        if (!GEMINI_API_KEY) {
            console.error("Error: GEMINI_API_KEY is missing.");
            return { statusCode: 500, body: JSON.stringify({ error: "Server Error: API Key missing" }) };
        }

        // UPDATED: Using the verified Gemini 3 Flash Preview model string
        const MODEL_ID = "gemini-3-flash-preview";
        const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL_ID}:generateContent?key=${GEMINI_API_KEY}`;

        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }]
            })
        });

        // Handle HTTP errors from Google (e.g., 400 Bad Request, 429 Rate Limit)
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`Google API Error (${response.status}):`, errorText);
            return { 
                statusCode: response.status, 
                body: JSON.stringify({ error: `AI Provider Error: ${response.statusText}` }) 
            };
        }

        const data = await response.json();

        // Safety Check: Gemini 3 sometimes returns no candidates if safety filters trigger
        if (!data.candidates || data.candidates.length === 0) {
            console.warn("Safety Filter Triggered:", JSON.stringify(data.promptFeedback));
            return { 
                statusCode: 500, 
                body: JSON.stringify({ error: "The AI blocked the response due to safety settings." }) 
            };
        }

        return {
            statusCode: 200,
            body: JSON.stringify(data)
        };

    } catch (error) {
        console.error("Function Crash:", error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: `Server Connection Error: ${error.message}` })
        };
    }
};
