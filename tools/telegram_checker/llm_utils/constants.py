"""
telegram_checker/llm_utils/constants.py

Fraud slang lexicon for LLM context injection.
Sourced from observed Telegram fraud channels and cross-referenced with
known cybercrime terminology.
"""

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
