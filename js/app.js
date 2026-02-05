document.addEventListener('alpine:init', () => {
    Alpine.data('ventureApp', () => ({
        allCompanies: [],
        isLoading: true,
        error: null,
        view: 'list',
        selectedCategory: null,
        modalOpen: false,
        selectedCompany: null,
        mobileFiltersOpen: false,
        viewMode: 'vc', 
        favorites: Alpine.$persist([]).as('venture-favorites'),
        searchQuery: '',
        searchDeep: false,
        userQuery: '',
        isChatting: false,
        chatError: '',
        chatHistory: [],
        sortDesc: true, 
        sidebarOpen: true, 
        chatProfileOpen: false, // New state for sidebar profile view
        mdParser: window.markdownit(),
        categoriesList: ["Grid Infrastructure (Hardware)","Grid Operations & Software (SaaS)","Enterprise & Corporate Systems","Field Operations & Services","Distributed Energy (DERs) & Edge","Generation & Storage","Professional Services & Engineering","Energy Markets & Trading","Other"],
        filters: { sector: '', subCat: '', stage: '', status: '', sortBy: 'score', aiFocus: false, showFavoritesOnly: false },

        init() { this.loadData(); },

        loadData() {
            this.isLoading = true;
            fetch('companies_scored_v2.json').then(r => r.json()).then(d => {
                this.allCompanies = this.processData(d);
                this.isLoading = false;
            }).catch(e => { this.error = e.message; this.isLoading = false; });
        },

        async sendMessage() {
            if (!this.userQuery.trim()) return;
            const query = this.userQuery;
            this.userQuery = ''; 
            this.chatError = '';
            this.isChatting = true;
            this.chatHistory.push({ role: 'user', content: query });
            
            this.$nextTick(() => { const c = document.getElementById('chat-container'); if(c) c.scrollTop = c.scrollHeight; });

            try {
                const aiSafeData = this.allCompanies.filter(c => c.raw.vc_dossier);

                const richData = aiSafeData.map(c => {
                    const d = c.raw.vc_dossier || {};
                    return {
                        n: c.name, s: c.score, h: c.hq, st: c.stage,
                        d: c.desc, rat: c.raw.rationale, ana: d.analogy, mac: d.macro_trend,
                        hc: d.headcount_estimate, stat: d.corporate_status, $r: d.total_raised,
                        rnd: d.latest_round, inv: d.key_investors, cust: d.key_customers,
                        tech: d.tech_stack, biz: d.business_model, m: d.moat_description, tax: c.raw.taxonomy
                    };
                });

                const systemInstruction = `
                System: You are an expert Venture Analyst, helping a VC firm begin to explore the electric power-related startup space. 
                I am providing a JSON dataset of companies who were exhibitors at 2026 Distribibutech conference and earned a high Venture score in our ai-assisted analysis..
                Keys: n=Name, s=Venture Score, h=HQ, st=Stage, d=Description, m=Moat, rat=VC Rationale, ana=Analogy, mac=Macro Trend, hc=Headcount, stat=Status, $r=Total Raised, rnd=Latest Round, inv=Investors, cust=Customers, tech=Tech Stack, biz=Business Model, tax=Taxonomy.
                
                CRITICAL RULES:
                1. Be thorough. Thoroughly review every attribute for each company, their investors, their customers, their moat, tech stack, business model, their industry (taxonomy), and ultimately the macro picture, to comprehensively answer the user's questions.
                2. When asked about companies, frame the question through the perspective of a venture capital firm that looks for early-stage, (seed and series A), middle-America,interior USA, ai-focused, defendable moat, incredibly scalable companies. Show all options including coastal US and international companies, but prioritize displaying opportunities in the interior US when you see them.
                3. Make the tone professional and not "edgy", do not sound robotic. Connect dots if you identify them. Do not skimp out on context. Your job is to help the user uncover real, deep, asymmetric insights.
                4. If you don't know the answer to something, be honest. Do not estimate or hallucinate. If you must estimate, be clear that the value you're providing is an estimate.
                5. Prioritize companies with higher Venture Scores (s) unless instructed otherwise..

                OPERATING INSTRUCTION
                Everything that was written up until now was background knowledge for you to keep in mind as you answer the question. Below this block will be the dataset, then the user will ask their question. Treat their question as the beginning of the prompt. Do not address anything that was said up until now. Do not address "middle-america", "asymmetric upside" or any of the instruction provided above. Those are internal instructions. The real prompt comes after this.
                
                DATASET:
                ${JSON.stringify(richData)}
                `;

                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: `${systemInstruction}\n\nUSER QUESTION: ${query}` })
                });

                if (!response.ok) {
                        if (response.status === 502) throw new Error("Response timed out. The analysis is too deep for the current connection.");
                        throw new Error(`Server Error: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (!data.candidates || data.candidates.length === 0) {
                    if (data.promptFeedback && data.promptFeedback.blockReason) {
                        throw new Error(`Response blocked by safety filters (${data.promptFeedback.blockReason})`);
                    }
                    throw new Error("Empty response from AI");
                }

                const reply = data.candidates[0].content.parts[0].text;
                this.chatHistory.push({ role: 'ai', content: reply });

            } catch (err) {
                console.error(err);
                this.chatError = err.message || "Error communicating with AI.";
                this.chatHistory.push({ role: 'ai', content: "⚠️ " + this.chatError });
            } finally {
                this.isChatting = false;
                this.$nextTick(() => { const c = document.getElementById('chat-container'); if(c) c.scrollTop = c.scrollHeight; });
            }
        },

        renderMarkdown(text) { return this.mdParser.render(text); },
        toggleFav(name) { if (this.favorites.includes(name)) { this.favorites = this.favorites.filter(f => f !== name); } else { this.favorites.push(name); } },
        isFav(name) { return this.favorites.includes(name); },
        clearFavorites() { if(confirm("Are you sure you want to clear all favorite companies?")) { this.favorites = []; this.filters.showFavoritesOnly = false; } },
        downloadBatchCSV() { const favs = this.allCompanies.filter(c => this.favorites.includes(c.name)); if (favs.length === 0) return alert("No favorites to export!"); this.generateCSV(favs, "venture_favorites_batch.csv"); },
        downloadSingleCSV(company) { if(!company) return; this.generateCSV([company], `venture_profile_${company.name.replace(/\s+/g, '_').toLowerCase()}.csv`); },
        generateCSV(companies, filename) {
            const headers = ["Name", "Description", "VC Alignment", "Big Picture", "Moat", "HQ", "Sector", "Sub-Sector", "Stage", "Total Raised", "Latest Round", "Venture Score", "Investors"];
            const rows = companies.map(c => {
                const dossier = c.raw.vc_dossier || {};
                return [`"${c.name}"`, `"${(c.desc || '').replace(/"/g, '""')}"`, `"${(c.raw.rationale || '').replace(/"/g, '""')}"`, `"${(dossier.macro_trend || '').replace(/"/g, '""')}"`, `"${(dossier.moat_description || '').replace(/"/g, '""')}"`, `"${c.hq}"`, `"${c.l1}"`, `"${c.l3}"`, `"${c.stage}"`, `"${c.meta['Total Raised']}"`, `"${c.meta['Last Raise']}"`, c.score.toFixed(2), `"${c.meta['Key Investors']}"`];
            });
            const csvContent = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            link.click();
        },
        processData(data) {
            if (!Array.isArray(data)) return [];
            return data.map(item => {
                const dossier = item.vc_dossier || {};
                const taxonomy = item.taxonomy || {};
                const meta = { "Total Raised": dossier.total_raised || '—', "Key Investors": this.formatList(dossier.key_investors), "Current Stage": item.stage_estimate || 'Unknown', "Last Raise": dossier.latest_round || '—', "Year Founded": dossier.year_founded || '—', "Headcount": dossier.headcount_estimate || '—', "Status": dossier.corporate_status || 'Active', "Key Customers": this.formatList(dossier.key_customers) };
                return { name: item.name, desc: item.investment_thesis_one_liner || '', hq: dossier.hq_location || 'Global', score: item.venture_scale_score || 0, status: dossier.corporate_status || 'Independent', l1: taxonomy.l1 || 'Other', l3: taxonomy.l3 || 'Unknown', stage: item.stage_estimate || 'Unknown', tech_leverage: item.dimension_scores?.['Tech Leverage'] || 0, meta: meta, sort_raised: this.parseMoney(meta["Total Raised"]), sort_headcount: this.parseHeadcount(meta["Headcount"]), sort_stage: this.parseStageScore(meta["Current Stage"]), raw: item };
            });
        },
        get categories() { return this.categoriesList.map(cat => ({ name: cat, count: (this.viewMode === 'all' ? this.allCompanies : this.allCompanies.filter(c => c.score >= 0.6)).filter(c => c.l1 === cat).length })); },
        get filteredCompanies() {
            let res = this.viewMode === 'all' ? [...this.allCompanies] : this.allCompanies.filter(c => c.score >= 0.6);
            if (this.searchQuery.trim()) {
                const q = this.searchQuery.toLowerCase();
                if (this.searchDeep) {
                        res = res.filter(c => c.name.toLowerCase().includes(q) || (c.desc || '').toLowerCase().includes(q) || (c.raw.vc_dossier?.moat_description || '').toLowerCase().includes(q) || (c.meta['Key Investors'] || '').toLowerCase().includes(q));
                } else { res = res.filter(c => c.name.toLowerCase().includes(q)); }
            }
            if (this.selectedCategory) res = res.filter(c => c.l1 === this.selectedCategory);
            if (this.filters.sector && !this.selectedCategory) res = res.filter(c => c.l1 === this.filters.sector);
            if (this.filters.subCat && this.selectedCategory) res = res.filter(c => c.l3 === this.filters.subCat);
            if (this.filters.stage) res = res.filter(c => c.stage === this.filters.stage);
            if (this.filters.status) res = res.filter(c => c.status === this.filters.status);
            if (this.filters.aiFocus) res = res.filter(c => c.tech_leverage >= 0.8);
            if (this.filters.showFavoritesOnly) res = res.filter(c => this.favorites.includes(c.name));
            const sortKey = this.filters.sortBy;
            res = res.sort((a, b) => {
                let valA, valB;
                if (sortKey === 'score') { valA = a.score; valB = b.score; }
                else if (sortKey === 'raised') { valA = a.sort_raised; valB = b.sort_raised; }
                else if (sortKey === 'headcount') { valA = a.sort_headcount; valB = b.sort_headcount; }
                else if (sortKey === 'stage') { valA = a.sort_stage; valB = b.sort_stage; }
                return this.sortDesc ? valB - valA : valA - valB;
            });
            return res;
        },
        get uniqueSectors() { return [...new Set(this.allCompanies.map(c => c.l1))].sort(); },
        get uniqueSubCats() { const pool = this.selectedCategory ? this.allCompanies.filter(c => c.l1 === this.selectedCategory) : this.allCompanies; return [...new Set(pool.map(c => c.l3))].sort(); },
        get uniqueStages() { const pool = this.selectedCategory ? this.allCompanies.filter(c => c.l1 === this.selectedCategory) : this.allCompanies; return [...new Set(pool.map(c => c.stage))].sort(); },
        get uniqueStatuses() { const pool = this.selectedCategory ? this.allCompanies.filter(c => c.l1 === this.selectedCategory) : this.allCompanies; return [...new Set(pool.map(c => c.status))].sort(); },
        selectCategory(cat) { this.selectedCategory = cat; this.view = 'list'; this.filters.subCat = ''; window.scrollTo({ top: 0, behavior: 'auto' }); },
        goBack() { this.selectedCategory = null; this.view = 'map'; },
        
        // --- UPDATED OPEN MODAL LOGIC ---
        openModal(company) { 
            this.selectedCompany = company; 
            if (this.view === 'chat') {
                // Open profile in sidebar
                this.chatProfileOpen = true;
                // Ensure sidebar is visible if it was collapsed
                this.sidebarOpen = true;
            } else {
                // Open standard modal
                this.modalOpen = true; 
                document.body.style.overflow = 'hidden'; 
            }
        },
        
        // --- UPDATED CLOSE MODAL LOGIC ---
        closeModal() { 
            this.modalOpen = false; 
            this.chatProfileOpen = false; // Close sidebar profile view
            this.selectedCompany = null; 
            document.body.style.overflow = 'auto'; 
        },
        
        formatList(val, limit=2) { if (Array.isArray(val)) return val.slice(0, limit).join(', '); return val || '—'; },
        parseList(str) { if(!str || str === '—') return []; return str.split(',').map(s => s.trim()); },
        getInitials(name) { return name.split(' ').slice(0, 2).map(n => n[0]).join(''); },
        getColor(name) { const colors = ['#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#6366F1', '#8B5CF6']; let hash = 0; for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash); return colors[Math.abs(hash) % colors.length]; },
        parseMoney(s) { if (!s || typeof s !== 'string') return 0; const clean = s.toUpperCase().replace('$', '').replace('~', ''); const match = clean.match(/[\d,.]+/); if (!match) return 0; let num = parseFloat(match[0].replace(',', '')); if (clean.includes('B')) num *= 1e9; else if (clean.includes('M')) num *= 1e6; else if (clean.includes('K')) num *= 1e3; return num; },
        parseHeadcount(s) { if (!s || typeof s !== 'string') return 0; const match = s.match(/[\d,]+/); return match ? parseInt(match[0].replace(',', '')) : 0; },
        parseStageScore(s) { const str = String(s).toLowerCase(); if (str.includes('seed')) return 1; if (str.includes('series a')) return 2; if (str.includes('series b')) return 3; if (str.includes('growth')) return 4; if (str.includes('late')) return 5; if (str.includes('public') || str.includes('mature')) return 6; return 0; }
    }));
});
