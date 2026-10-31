"""
Query Understanding & Research Planning Engine for J.A.R.V.I.S.
Classifies query, determines depth, generates research questions and targeted queries.
"""
import re
from typing import Optional, List, Dict, Any
from .models import ResearchPlan

SUBJECT_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "PERSON": {
        "name": "People & Biographies",
        "keywords": ["biography", "who is", "actor", "actress", "leader", "scientist", "ceo", "founder", 
                     "cricketer", "minister", "author", "director", "life", "born", "family", "career",
                     "shah rukh", "shahrukh", "srk", "narendra modi", "modi", "mahatma gandhi", "gandhi",
                     "sachin tendulkar", "sachin", "virat kohli", "kohli", "elon musk", "musk",
                     "शाहरुख", "मोदी", "गांधी", "सचिन", "कोहली", "इलोन", "मस्क", "अमिताभ", "नेहरू", "कलाम", "पटेल"],
        "default_aspects": ["Birth & Early Life", "Education & Formative Years", "Career Milestones", "Major Works & Impact", "Awards & Honours", "Current Status & Verified Legacy"]
    },
    "COMPANY": {
        "name": "Companies & Organizations",
        "keywords": ["company", "inc", "ltd", "corp", "startup", "google", "apple", "microsoft", "tesla", 
                     "reliance", "tata", "spacex", "meta", "nvidia", "amazon", "business model", "valuation", "कंपनी", "उद्योग"],
        "default_aspects": ["Company Overview", "Founding & History", "Products & Flagship Offerings", "Business Model & Economics", "Market Position & Competitors", "Recent Developments & Strategy"]
    },
    "TECHNOLOGY": {
        "name": "Science & Technology",
        "keywords": ["quantum", "semiconductor", "robotics", "chips", "hardware", "engineering", "biotech", "nanotechnology", "क्वांटम", "तकनीक"],
        "default_aspects": ["Introduction & Background", "Working Principles", "Technical Architecture", "Applications", "Comparative Advantages & Limitations", "Future Roadmap"]
    },
    "AI_ML": {
        "name": "Artificial Intelligence & Machine Learning",
        "keywords": ["ai", "artificial intelligence", "machine learning", "deep learning", "llm", "neural network", "transformer", "gpt", "gemini", "claude", "nlp", "computer vision", "आर्टिफिशियल इंटेलिजेंस"],
        "default_aspects": ["Core AI Paradigm", "Architectural Mechanics", "Training & Benchmarks", "Real-World Deployments", "Safety, Alignment & Bottlenecks", "Emerging Capabilities"]
    },
    "SOFTWARE": {
        "name": "Software & Programming",
        "keywords": ["programming", "software", "python", "javascript", "rust", "c++", "framework", "database", "api", "linux", "git", "docker", "kubernetes", "प्रोग्रामिंग"],
        "default_aspects": ["Framework Overview", "Design Philosophy & Syntax", "Core Ecosystem & Tooling", "Performance & Scalability", "Best Practices", "Ecosystem Adoption"]
    },
    "PRODUCT": {
        "name": "Products & Gadgets",
        "keywords": ["iphone", "phone", "gadget", "laptop", "car", "ev", "specifications", "specs", "review", "camera", "battery", "मॉडल", "प्रोडक्ट", "गैजेट"],
        "default_aspects": ["Product Overview", "Technical Specifications", "Core Features & Innovations", "Performance Benchmark & Real-World Testing", "Pros, Cons & Trade-offs", "Pricing & Alternatives"]
    },
    "HISTORICAL_EVENT": {
        "name": "Historical Events & Civilizations",
        "keywords": ["war", "battle", "revolution", "treaty", "empire", "independence", "1947", "world war", "movement", "dynasty", "ancient", "history", "इतिहास", "युद्ध", "क्रांति", "स्वतंत्रता"],
        "default_aspects": ["Historical Context & Roots", "Root Causes & Catalysts", "Chronological Timeline of Key Events", "Decisive Figures & Turning Points", "Long-term Consequences", "Historiographical Perspectives"]
    },
    "GEOGRAPHY": {
        "name": "Geography, Nations & Cities",
        "keywords": ["country", "nation", "city", "capital", "river", "mountain", "ocean", "population", "demographics", "climate", "भूगोल", "देश", "शहर", "भारत"],
        "default_aspects": ["Geographic Profile", "Demographics & Culture", "Economy & Infrastructure", "Governance & Geopolitics", "Key Landmarks & Heritage", "Modern Outlook"]
    },
    "GOVERNMENT_POLICY": {
        "name": "Government Schemes & Public Policy",
        "keywords": ["scheme", "policy", "yojana", "act", "bill", "constitution", "subsidy", "ministry", "welfare", "योजना", "संविधान", "नीति", "अधिनियम"],
        "default_aspects": ["Policy Objective & Framework", "Eligibility & Beneficiaries", "Implementation Architecture", "Budgetary Allocation & Performance", "Critical Challenges", "Institutional Recommendations"]
    },
    "BUSINESS_ECONOMICS": {
        "name": "Business, Finance & Economics",
        "keywords": ["economy", "inflation", "gdp", "stock market", "interest rate", "trade", "banking", "fiscal", "monetary", "अर्थव्यवस्था", "मुद्रास्फीति", "बाजार", "जीडीपी"],
        "default_aspects": ["Macroeconomic Overview", "Key Indicators & Historical Trends", "Market Drivers & Fiscal Policies", "Sectoral Impact", "Risk Assessment", "Medium-term Projections"]
    },
    "SPACE_ASTRONOMY": {
        "name": "Space & Astronomy",
        "keywords": ["space", "nasa", "isro", "moon", "mars", "galaxy", "black hole", "telescope", "starship", "rocket", "orbit", "chandrayaan", "चंद्रयान", "अंतरिक्ष", "ग्रह", "ब्लैक होल"],
        "default_aspects": ["Cosmic & Mission Overview", "Scientific Objectives", "Engineering & Flight Systems", "Key Milestones & Discoveries", "Challenges & Orbital Hazards", "Upcoming Missions"]
    },
    "MEDICINE_HEALTH": {
        "name": "Medicine & Healthcare",
        "keywords": ["disease", "medicine", "vaccine", "treatment", "therapy", "clinical", "health", "cancer", "genetics", "वायरस", "दवा", "इलाज", "स्वास्थ्य"],
        "default_aspects": ["Medical Overview (Informational)", "Biological Mechanisms & Pathology", "Standard Diagnostic & Treatment Protocols", "Clinical Evidence & Efficacy", "Limitations & Safety Considerations", "Verified Medical Literature"]
    },
    "ENVIRONMENT": {
        "name": "Environment & Nature",
        "keywords": ["climate change", "pollution", "biodiversity", "forest", "wildlife", "conservation", "renewable energy", "पर्यावरण", "प्रदूषण", "जलवायु परिवर्तन"],
        "default_aspects": ["Ecological Context", "Environmental Drivers & Pressures", "Scientific Data & Measurement", "Conservation & Policy Measures", "Ecological Impact", "Sustainable Pathways"]
    },
    "ENTERTAINMENT": {
        "name": "Movies, Arts & Media",
        "keywords": ["movie", "film", "cinema", "music", "song", "album", "box office", "hollywood", "bollywood", "सिनेमा", "फिल्म", "गीत"],
        "default_aspects": ["Creative Overview", "Production & Background", "Themes & Critical Reception", "Commercial & Cultural Impact", "Awards & Accolades", "Enduring Significance"]
    },
    "LITERATURE": {
        "name": "Books & Literature",
        "keywords": ["book", "novel", "author", "poem", "literature", "plot", "character", "theme", "उपन्यास", "पुस्तक", "साहित्य"],
        "default_aspects": ["Literary Context", "Narrative Arc & Core Themes", "Character & Structural Analysis", "Critical Reception & Accolades", "Cultural Influence", "Literary Legacy"]
    },
    "CURRENT_AFFAIRS": {
        "name": "Current Affairs & Geopolitics",
        "keywords": ["summit", "election", "conflict", "treaty", "geopolitics", "foreign policy", "diplomacy", "समसामयिकी", "चुनाव", "कूटनीति"],
        "default_aspects": ["Situation Overview", "Key Stakeholders & Positions", "Chronological Timeline", "Geopolitical Implications", "Expert Opinions & Divergences", "Expected Developments"]
    },
    "SCIENTIFIC": {
        "name": "Scientific Research & Discoveries",
        "keywords": ["physics", "chemistry", "biology", "hypothesis", "experiment", "theory", "discovery", "particle", "भौतिकी", "रसायन", "जीव विज्ञान", "खोज"],
        "default_aspects": ["Theoretical Foundation", "Experimental Evidence & Methodology", "Core Principles & Mathematical/Physical Formulations", "Peer-Reviewed Consensus", "Anomalies & Open Questions", "Future Research Avenues"]
    },
    "GENERAL_TOPIC": {
        "name": "General Topic, Concept & Policy",
        "keywords": [],
        "default_aspects": ["Conceptual Foundation", "Background & Context", "Key Mechanisms & Structural Frameworks", "Evidence-based Analysis", "Socio-Economic & Global Impact", "Conclusions & Strategic Outlook"]
    }
}

def clean_subject_query(raw_query: str) -> str:
    """Extracts the clean target subject from conversational prompts."""
    clean = raw_query.strip()
    clean = re.sub(r'^(jarvis|hey jarvis|hello jarvis|जार्विस|सुनो)\s*[,:]?\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'^(please|कृपया)\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'^(create\s+a|generate\s+a|make\s+a|give\s+me\s+a|provide\s+a|write\s+a|do\s+a|do|prepare\s+a)\s+', '', clean, flags=re.IGNORECASE)
    
    triggers = [
        'deeply explain karo aur report banao', 'deeply explain karo', 'deeply explain',
        'complete research report banao', 'complete research report', 'complete report banao', 'complete report',
        'detailed research report bana kar do', 'detailed research report', 'detailed research', 'detailed report',
        'deep research report', 'deep research on', 'deep research', 'research on', 'research report', 'research karo', 'research',
        'रिसर्च करो', 'रिसर्च रिपोर्ट', 'रिसर्च', 'पूरी रिपोर्ट बनाओ', 'पूरी रिपोर्ट', 'विस्तृत रिपोर्ट बनाओ', 'विस्तृत रिपोर्ट',
        'गहन अध्ययन करो', 'गहन अध्ययन', 'बायोग्राफी बनाओ', 'बायोग्राफी', 'जीवनी बनाओ', 'जीवनी',
        'biography of', 'biography on', 'biography', 'pdf report banao', 'pdf report', 'पीडीएफ रिपोर्ट बनाओ', 'पीडीएफ रिपोर्ट',
        'रिपोर्ट बनाओ', 'रिपोर्ट तैयार करो', 'रिपोर्ट', 'report banao', 'report generate', 'case study', 'केस स्टडी',
        'डिटेल्ड रिपोर्ट', 'detailed'
    ]
    for trig in sorted(triggers, key=len, reverse=True):
        clean = re.sub(re.escape(trig), ' ', clean, flags=re.IGNORECASE)

    postpositions = [
        r'\b(ka|ki|ke|ko|par|pe|me|mein|about|for|of)\b',
        r'(का|की|के|को|पर|पे|में|बारे में)',
        r'\b(banao|bana do|bana kar do|generate karo|karo|chahiye|dega|do)\b',
        r'(बनाओ|बनाकर दो|करो|चाहिए|दो)'
    ]
    for p in postpositions:
        clean = re.sub(p, ' ', clean, flags=re.IGNORECASE)

    clean = re.sub(r'\s+', ' ', clean).strip(' ,:.-?!')
    return clean or raw_query.strip()

def identify_category(subject: str) -> str:
    """Maps a research subject to the appropriate taxonomy category using regex word boundaries."""
    sub_low = subject.lower()
    for cat_key, meta in SUBJECT_TAXONOMY.items():
        if cat_key == "GENERAL_TOPIC":
            continue
        for kw in meta["keywords"]:
            kw_low = kw.lower()
            if len(kw_low) <= 4:
                # Word boundary check for short words to prevent substring collisions (e.g. "ev" in "revolution")
                if re.search(r'\b' + re.escape(kw_low) + r'\b', sub_low):
                    return cat_key
            else:
                if kw_low in sub_low:
                    return cat_key
    return "GENERAL_TOPIC"

def determine_depth(user_query: str, requested_mode: Optional[str] = None) -> str:
    """Determines depth mode: QUICK, STANDARD, or DEEP."""
    if requested_mode and requested_mode.upper() in ["QUICK", "STANDARD", "DEEP"]:
        return requested_mode.upper()
    
    q_low = user_query.lower()
    if any(k in q_low for k in ["deep", "deeply", "exhaustive", "complete research", "पूरा रिसर्च", "गहन", "विस्तृत", "पूरी रिपोर्ट", "in detail"]):
        return "DEEP"
    elif any(k in q_low for k in ["quick", "short", "brief", "संक्षिप्त", "जल्दी", "overview"]):
        return "QUICK"
    return "STANDARD"

def generate_research_plan(raw_query: str, requested_mode: Optional[str] = None) -> ResearchPlan:
    """Constructs a comprehensive research plan with target questions and search queries."""
    clean_subj = clean_subject_query(raw_query)
    category = identify_category(clean_subj)
    depth = determine_depth(raw_query, requested_mode)
    cat_meta = SUBJECT_TAXONOMY.get(category, SUBJECT_TAXONOMY["GENERAL_TOPIC"])

    # 1. Objectives & Questions based on Category and Depth
    objectives = [
        f"Investigate authentic background, foundations and verified records of '{clean_subj}'.",
        f"Cross-verify significant factual claims, numbers and timelines across independent sources.",
        f"Synthesize comprehensive analysis, real-world impact, and identify uncertainties."
    ]

    questions = []
    if category == "PERSON":
        questions = [
            f"What is {clean_subj}'s documented background, birth date, education and early life?",
            f"What are the verified career milestones, major achievements, and authentic statistics?",
            f"What recognized national/international awards and legitimate honors have been conferred?",
            f"What are the documented current status, active projects, and verified public contributions?",
            f"Are there any widely reported controversies or disputed facts that require objective context?"
        ]
    elif category in ["TECHNOLOGY", "AI_ML", "SOFTWARE"]:
        questions = [
            f"What are the foundational principles, origins and architecture of {clean_subj}?",
            f"How does {clean_subj} operate technically, and what are its core components?",
            f"What are the verified real-world applications, empirical benchmarks and performance data?",
            f"What are the verified advantages, trade-offs, bottlenecks and security/ethical limitations?",
            f"What is the realistic future trajectory and upcoming research roadmap?"
        ]
    elif category == "COMPANY":
        questions = [
            f"When was {clean_subj} founded, who are the founders, and what is its corporate history?",
            f"What is its core business model, key product lines, and verified operational scale?",
            f"What are its authentic financial metrics, revenue/valuation (from dated primary filings)?",
            f"Who are its main competitors and what is its competitive moat?",
            f"What are current strategic developments, legal/market risks, and future outlook?"
        ]
    elif category == "HISTORICAL_EVENT":
        questions = [
            f"What were the underlying socio-political and economic root causes of {clean_subj}?",
            f"What is the verified chronological timeline of major events and decisive turning points?",
            f"Who were the key historical figures, and what roles did they play according to records?",
            f"What were the immediate and long-term consequences and institutional reforms?",
            f"What are the major historiographical interpretations and points of academic debate?"
        ]
    elif category == "PRODUCT":
        questions = [
            f"What are the official technical specifications and design features of {clean_subj}?",
            f"What do verified benchmark tests and real-world reviews demonstrate about its performance?",
            f"What are its documented pros, cons, hardware/software limitations, and price point?",
            f"How does it compare against direct market alternatives?"
        ]
    elif category == "SPACE_ASTRONOMY":
        questions = [
            f"What are the scientific objectives, background and mission parameters of {clean_subj}?",
            f"What propulsion, instruments and technical engineering systems are utilized?",
            f"What are the verified milestones, discoveries and empirical measurements recorded?",
            f"What orbital, gravitational or cosmic hazards exist?",
            f"What are the future mission phases and scientific implications?"
        ]
    else:
        questions = [
            f"What is the definitive conceptual overview, origin and background of {clean_subj}?",
            f"What are the core operating mechanisms, frameworks and structural principles?",
            f"What quantitative data, empirical evidence and verified metrics exist?",
            f"What are the verified challenges, criticisms, trade-offs and unresolved questions?",
            f"What are the long-term implications and future strategic outlook?"
        ]

    # Adjust question scope by depth
    if depth == "QUICK":
        questions = questions[:3]
    elif depth == "STANDARD":
        questions = questions[:5]
    else:  # DEEP
        if len(questions) < 7:
            questions.append(f"What independent expert consensus or empirical studies analyze {clean_subj}?")
            questions.append(f"What verifiable trends and documented milestones define {clean_subj} from 2020 to present?")

    # 2. Targeted Verification Targets
    verif_targets = [
        f"Exact dates, birth/founding timelines, and historical chronology of {clean_subj}",
        f"Documented achievements, official statistics, and primary institutional records",
        f"Distinguish verified facts from estimates, rumors, and unsupported claims"
    ]

    # 3. Targeted Search Queries
    search_queries = [
        f"{clean_subj} overview history official facts",
        f"{clean_subj} background biography achievements",
        f"{clean_subj} statistics data report",
        f"{clean_subj} analysis developments latest news"
    ]

    return ResearchPlan(
        topic=raw_query,
        clean_subject=clean_subj,
        category=category,
        depth=depth,
        research_objectives=objectives,
        research_questions=questions,
        verification_targets=verif_targets,
        search_queries=search_queries
    )
