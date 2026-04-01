"""
telegram_checker/llm_utils/constants.py

Fraud slang lexicon for LLM context injection.
Sourced from observed Telegram fraud channels and cross-referenced with
known cybercrime terminology.
"""

LLM_REQUEST_TIMEOUT = 60
MIN_WORD_COUNT = 3
FETCH_LIMIT    = 100
LLM_PARAMS = {
    "temperature": 0.1,
    "top_p": 1,
    "min_p": 0.01,
    "top_k": 50,
    "repeat_penalty": 1,
    "max_output_tokens": 4192,
    # "reasoning": "off"
}
LLM_DEFAULT = {
    "endpoint": "http://localhost:1234/api/v1/chat",
    "model": "openai/gpt-oss-20b"
}
FRAUD_LEXICON: dict[str, str] = {
    "aged account":     "Stolen bank account with transaction history, used to appear legitimate",
    "bin / BIN":        "Bank Identification Number — first digits of a credit card, used to identify issuer",
    "biz":              "Business check (vs. personal)",
    "bread":            "Money or profits",
    "carding":          "Using stolen credit card data to make fraudulent purchases",
    "cashier":          "Cashier's check exploited for fraud",
    "cc":               "Credit card (stolen)",
    "certified funds":  "Money orders or cashier's checks bought with fraudulent funds",
    "clonecard":        "Physical cloned credit/debit card",
    "cookies":          "Stolen browser cookies for session hijacking",
    "cooking / cookup": "Creating fake/counterfeit checks or documents",
    "cop":              "To buy or acquire fraudulent goods",
    "food":             "Checks, compromised logins, or other profitable material",
    "fresh":            "Newly obtained, high-quality stolen material",
    "fullz":            "Complete identity package: name, SSN, DOB, address",
    "glass":            "Bank check",
    "ham":              "Scammer who rips off other fraudsters; low-quality fake offers",
    "kit":              "Package with fake IDs and account access for fraud",
    "load up":          "Transfer money from a compromised account; deposit a check",
    "logs":             "Stolen login credentials with associated data (balances, etc.)",
    "mule":             "Low-level participant who cashes out funds",
    "open-ups":         "Bank accounts created with stolen identities, sold for fraud",
    "persy":            "Personal check or personal account",
    "plug":             "Insider contact (bank/USPS employee) providing access to checks",
    "popped":           "Successfully cashed a fraudulent check",
    "RDP":              "Remote Desktop Protocol access to hacked computers",
    "runner":           "Person who physically handles check cashing or pickups",
    "slips":            "High-value fraudulent checks",
    "spam":             "In fraud context: phishing or compromising victim card/account data",
    "stims":            "Government stimulus or tax refund checks",
    "uppy / UPPI":      "Uploading check images to Telegram for sale",
    "valid slips":      "Working forged or stolen checks",
    "vouch":            "Proof of legitimate delivery; testimonial from a buyer",
    "walkers":          "Elderly people recruited to cash fake checks",
}
TAGS: dict[str, str] = {
    "None": "when nothing fits",
    "bank_accounts": "related to bank accounts (access to a stolen bank account, credentials, log-in)",
    "credit_cards": "related to credit card theft or cloning",
    "bank_checks": "related to bank checks, bank check theft from mail, counterfeit bank checks",
    "drugs": "any illegal drug",
    "guns": "weapons and firearms",
    "fake_money": "counterfeit money",
    "forgery": "counterfeit and forged documents",
    "csam": "child abuse material"
}
SKIP_LV1 = {
    "i don't like it",
    "other",
    "it's not illegal, but must be taken down",
}
SKIP_LV2 = {
    "other goods and services",
    "other personal information",
    "other illegal sexual content",
    "something else",
    "i don't like it",
}
TAGS_STR = ", ".join(TAGS)
LEXICON_STR = "\n".join(f"- {term}: {definition}" for term, definition in FRAUD_LEXICON.items())
REPORT_TREE_DEFAULT = {
    "I don't like it": [],
    "It's not illegal, but must be taken down": [],
    "Other": [
        "I don't like it",
        "False information or defamation",
        "Illegal adult content",
        "Illegal goods and services",
        "Something else"
    ],
    "Child abuse": [
        "Child sexual abuse",
        "Child physical abuse"
    ],
    "Violence": [
        "Insults or false information",
        "Graphic or disturbing content",
        "Extreme violence, dismemberment",
        "Hate speech or symbols",
        "Calling for violence",
        "Organized crime",
        "Terrorism",
        "Animal abuse"
    ],
    "Illegal goods and services": [
        "Weapons",
        "Drugs",
        "Fake documents",
        "Counterfeit money",
        "Hacking tools and malware",
        "Counterfeit merchandise",
        "Other goods and services"
    ],
    "Illegal adult content": [
        "Child abuse",
        "Illegal sexual services",
        "Animal abuse",
        "Non-consensual sexual imagery",
        "Pornography",
        "Other illegal sexual content"
    ],
    "Personal data": [
        "Private images",
        "Phone number",
        "Address",
        "Stolen data or credentials",
        "Other personal information"
    ],
    "Scam or fraud": [
        "Impersonation",
        "Deceptive or unrealistic financial claims",
        "Malware, phishing",
        "Fraudulent seller, product or service"
    ],
    "Copyright": [],
    "Spam": [
        "Insults or false information",
        "Promoting illegal content",
        "Promoting other content"
    ]
}

SYSTEM_PROMPT = """\
    You are a content moderation assistant. Your sole task is to analyze Telegram \
    messages and classify them for potential policy violations.
    
    You MUST respond ONLY with a valid JSON object. \
    No explanation, no markdown, no code fences, no surrounding text — \
    just the raw JSON object.
    
    The JSON object must contain exactly these five fields:
    
      "lv1"          : string  — MUST be a top-level key from the classification tree below
      "lv2"          : string  — MUST be a value from the corresponding lv1 list; use "No report" for harmless
      "confidence"   : float   — your certainty score, strictly between 0.0 and 1.0
      "report_text"  : string  — a concise, professional report for Telegram moderators \
    (maximum 3 sentences, usually 2); empty string if harmless
      "tag"          : string  — MUST be one of: %(tags)s (use "None" if nothing fits)
    
    Classification tree (lv1 → lv2 options):
    %(categories)s
    
    Classification rules:
    - Use Harmless/No report when the message does not violate any policy.
    - confidence must honestly reflect how certain you are about the chosen category.
    - report_text must be factual and neutral; avoid subjective or personal language.
    - Messages may be in any language (Hindi, Urdu, Bengali, Arabic, English slang, etc.). \
    Classify based on meaning and context, not language.
    - Never output anything outside the JSON object.
    
    Fraud slang glossary:
    %(lexicon)s
    """.replace(f"\n{4 * ' '}", '\n').lstrip()
