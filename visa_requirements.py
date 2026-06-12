"""
visa_requirements.py
Complete visa data for all major countries.
Admin can copy-paste, search, filter, and create custom checklists with pricing.
"""

VISA_REQUIREMENTS = {
    "USA": {
        "display_name": "United States",
        "visa_types": {
            "tourist": {
                "name": "Tourist (B1/B2)",
                "duration": "3-6 months",
                "processing_time": "7-10 working days",
                "validity": "10 years",
                "cost_usd": 160,
                "documents": [
                    "Valid Passport (6+ months validity)",
                    "Filled DS-160 form (online)",
                    "Photo (4x6 cm, white background)",
                    "Bank statements (3-6 months)",
                    "Hotel bookings/itinerary",
                    "Return flight ticket",
                    "Travel insurance",
                    "Employment letter/Leave approval",
                    "Property deed/Land documents",
                    "Previous USA visa (if any)",
                ],
                "requirements_text": "Must have valid US visa interview appointment.",
                "notes": "Visa interview mandatory. Strong financial proof required.",
            },
            "business": {
                "name": "Business (B1)",
                "duration": "3-6 months",
                "processing_time": "7-10 working days",
                "validity": "10 years",
                "cost_usd": 160,
                "documents": [
                    "Valid Passport (6+ months validity)",
                    "Filled DS-160 form",
                    "Photo (4x6 cm)",
                    "Bank statements (6 months)",
                    "Company letter",
                    "Business registration",
                    "ITR/Tax returns (2 years)",
                    "Invitation letter from US company",
                    "Return flight ticket",
                    "Travel insurance",
                ],
                "requirements_text": "Business tie-up or meeting invitation required.",
                "notes": "Must prove strong ties to home country.",
            },
            "student": {
                "name": "Student (F-1)",
                "duration": "Duration of studies + 60 days",
                "processing_time": "7-10 working days",
                "validity": "Multiple entry",
                "cost_usd": 350,
                "documents": [
                    "Valid Passport (6+ months)",
                    "I-20 from US University",
                    "Photo",
                    "Bank statements (full funding proof)",
                    "Admission letter",
                    "Affidavit of support (I-864)",
                    "Sponsor bank statements",
                    "Academic transcripts",
                    "Return flight ticket",
                ],
                "requirements_text": "Confirmed university admission and I-20 required.",
                "notes": "Must prove financial ability to support studies.",
            },
        },
    },
    "Canada": {
        "display_name": "Canada",
        "visa_types": {
            "tourist": {
                "name": "Tourist (TRV)",
                "duration": "6 months",
                "processing_time": "14-21 days",
                "validity": "10 years",
                "cost_cad": 100,
                "documents": [
                    "Valid Passport (1+ year validity)",
                    "Filled IMM 0008 form",
                    "Photo (4x6 cm, recent)",
                    "Bank statements (3-6 months)",
                    "Hotel bookings",
                    "Return flight ticket",
                    "Travel insurance",
                    "Employment letter",
                    "Leave approval",
                    "Property documents",
                ],
                "requirements_text": "Must demonstrate ties to home country.",
                "notes": "Biometrics may be required. Online application available.",
            },
            "student": {
                "name": "Student (Study Permit)",
                "duration": "Duration of studies + 3 months",
                "processing_time": "10-15 days",
                "validity": "As per study program",
                "cost_cad": 150,
                "documents": [
                    "Valid Passport",
                    "Study permit application",
                    "Letter of acceptance (LOA)",
                    "Bank statements (proof of funds)",
                    "Tuition receipt/proof",
                    "Identity documents",
                    "Medical exam (if required)",
                    "Police clearance (if required)",
                ],
                "requirements_text": "Valid LOA from Canadian institution required.",
                "notes": "Easier to obtain than USA. Work permission included.",
            },
            "work": {
                "name": "Work Permit",
                "duration": "As per contract",
                "processing_time": "14-21 days",
                "validity": "As per employer contract",
                "cost_cad": 275,
                "documents": [
                    "Valid Passport",
                    "Job offer letter",
                    "LMO/LMIA approval",
                    "Bank statements",
                    "Employment letter from current company",
                    "Educational certificates",
                    "Medical exam (if required)",
                    "Police clearance",
                ],
                "requirements_text": "Valid job offer with LMO required.",
                "notes": "Processing faster with LMO approval.",
            },
        },
    },
    "UK": {
        "display_name": "United Kingdom",
        "visa_types": {
            "tourist": {
                "name": "Tourist (Standard Visitor)",
                "duration": "6 months",
                "processing_time": "3-5 working days",
                "validity": "2-10 years (multiple entry)",
                "cost_gbp": 100,
                "documents": [
                    "Valid Passport",
                    "Completed application form (VAF 1)",
                    "Photo (4x6 cm)",
                    "Bank statements (3-6 months)",
                    "Accommodation proof",
                    "Return flight ticket",
                    "Travel insurance",
                    "Employment letter",
                    "Property documents",
                    "Sponsor letter (if applicable)",
                ],
                "requirements_text": "Prove financial stability and ties to home country.",
                "notes": "Fast processing. Online application only.",
            },
            "student": {
                "name": "Student Visa",
                "duration": "Duration of studies + 4 months",
                "processing_time": "3 weeks",
                "validity": "Single entry",
                "cost_gbp": 400,
                "documents": [
                    "Valid Passport",
                    "CAS from UK institution",
                    "Bank statements (proof of funds)",
                    "Tuition fees receipt",
                    "English language test (IELTS/TOEFL)",
                    "Educational certificates",
                    "Medical exam (TB test for India)",
                    "Police clearance",
                ],
                "requirements_text": "CAS from UKVI registered institution required.",
                "notes": "Post-study work visa available for 2 years.",
            },
        },
    },
    "Australia": {
        "display_name": "Australia",
        "visa_types": {
            "tourist": {
                "name": "Tourist (Visitor)",
                "duration": "Up to 12 months",
                "processing_time": "4-6 weeks",
                "validity": "As issued",
                "cost_aud": 190,
                "documents": [
                    "Valid Passport",
                    "Application form (1419)",
                    "Photo (4x6 cm)",
                    "Bank statements (6 months)",
                    "Accommodation proof",
                    "Return flight ticket",
                    "Travel insurance",
                    "Employment letter",
                    "Property documents",
                    "Character declaration",
                ],
                "requirements_text": "Health examination may be required.",
                "notes": "eVisitor system. Processing faster for some nationalities.",
            },
            "student": {
                "name": "Student Visa",
                "duration": "Duration of studies + 3 months",
                "processing_time": "5-8 weeks",
                "validity": "Single entry",
                "cost_aud": 650,
                "documents": [
                    "Valid Passport",
                    "CoE from Australian institution",
                    "Bank statements (proof of funds)",
                    "English language test",
                    "Educational certificates",
                    "Health examination (chest X-ray)",
                    "Police clearance",
                    "Genuine Temporary Entrant statement",
                ],
                "requirements_text": "CoE from CRICOS registered institution required.",
                "notes": "Work rights: 40 hrs/week during studies, full-time during breaks.",
            },
        },
    },
    "UAE": {
        "display_name": "United Arab Emirates",
        "visa_types": {
            "tourist": {
                "name": "Tourist Visa",
                "duration": "30 days (extendable to 90)",
                "processing_time": "1-2 days",
                "validity": "90 days",
                "cost_aed": 250,
                "documents": [
                    "Valid Passport (6+ months)",
                    "Recent passport photo",
                    "Bank statements (3 months)",
                    "Hotel booking confirmation",
                    "Return flight ticket",
                    "Travel insurance",
                    "Employment letter",
                    "Sponsorship letter (if staying with family)",
                ],
                "requirements_text": "Simple documentation. Tourist-friendly.",
                "notes": "Fastest processing among Gulf countries. Easy extension.",
            },
            "transit": {
                "name": "Transit Visa",
                "duration": "96 hours",
                "processing_time": "Few minutes",
                "validity": "Immediate",
                "cost_aed": 150,
                "documents": [
                    "Valid Passport",
                    "Onward flight ticket",
                    "Return/connecting flight ticket",
                ],
                "requirements_text": "Must have onward flight within 96 hours.",
                "notes": "Free for some nationalities. Quick processing.",
            },
        },
    },
    "Singapore": {
        "display_name": "Singapore",
        "visa_types": {
            "tourist": {
                "name": "Tourist Visa",
                "duration": "14-30 days",
                "processing_time": "3-5 working days",
                "validity": "Single/Multiple entry (1 month)",
                "cost_sgd": 30,
                "documents": [
                    "Valid Passport (6+ months)",
                    "Completed application form (V39)",
                    "Recent photograph",
                    "Bank statements (3 months)",
                    "Hotel booking",
                    "Return flight ticket",
                    "Travel insurance",
                    "Employment letter",
                    "Property proof",
                ],
                "requirements_text": "Straightforward process. Business-friendly.",
                "notes": "Visa-free for 30 days for Indian passport holders on arrival.",
            },
            "work": {
                "name": "Employment Pass",
                "duration": "1-2 years",
                "processing_time": "3-4 weeks",
                "validity": "As per employment contract",
                "cost_sgd": 0,
                "documents": [
                    "Valid Passport",
                    "Job offer letter",
                    "Bank statements",
                    "Educational certificates",
                    "Medical report",
                    "Police clearance",
                    "Employment contract",
                ],
                "requirements_text": "Job offer with Singapore company required.",
                "notes": "Employer sponsors. High salary requirements.",
            },
        },
    },
    "Germany": {
        "display_name": "Germany",
        "visa_types": {
            "tourist": {
                "name": "Tourist (Schengen)",
                "duration": "Up to 90 days",
                "processing_time": "4-15 days",
                "validity": "Schengen valid",
                "cost_eur": 80,
                "documents": [
                    "Valid Passport",
                    "Completed visa application form",
                    "Recent photographs (2 x 4.5x6cm)",
                    "Hotel bookings",
                    "Return flight ticket",
                    "Travel insurance (minimum €30,000)",
                    "Bank statements (3-6 months)",
                    "Employment letter",
                    "Property documents",
                    "Cover letter (purpose of visit)",
                ],
                "requirements_text": "Schengen visa covers 26 European countries.",
                "notes": "Valid for whole Schengen area. Multiple entry available.",
            },
            "student": {
                "name": "Student Visa",
                "duration": "Duration of studies",
                "processing_time": "4-8 weeks",
                "validity": "Single entry",
                "cost_eur": 75,
                "documents": [
                    "Valid Passport",
                    "University admission letter",
                    "Bank statements (proof of funds: €11,208/year)",
                    "English language certificate (IELTS/TOEFL)",
                    "Educational certificates",
                    "CV",
                    "Medical certificate",
                    "Police clearance",
                ],
                "requirements_text": "University admission required. Proof of funds for 1 year.",
                "notes": "Free or very cheap tuition in Germany. Work allowed.",
            },
        },
    },
    "Japan": {
        "display_name": "Japan",
        "visa_types": {
            "tourist": {
                "name": "Tourist Visa",
                "duration": "15-30 days",
                "processing_time": "4-7 days",
                "validity": "Single/Multiple entry (1 month)",
                "cost_jpy": 0,
                "documents": [
                    "Valid Passport",
                    "Visa application form (Form 204)",
                    "Recent photograph (4x4 cm)",
                    "Hotel booking/Itinerary",
                    "Return flight ticket",
                    "Bank statements (3-6 months)",
                    "Employment letter",
                    "Travel insurance",
                    "Purpose statement",
                ],
                "requirements_text": "Straightforward visa. Tourists welcome.",
                "notes": "Free visa for Indian citizens. Simple process.",
            },
        },
    },
}

# Pricing tiers for agencies to set discounts
DEFAULT_CHECKLIST_PRICES = {
    "tourist": 5000,      # INR
    "business": 7500,
    "student": 10000,
    "work": 12500,
    "transit": 2000,
}

# Global processing time estimates
PROCESSING_TIMES = {
    "USA": "7-10 days",
    "Canada": "14-21 days",
    "UK": "3-5 days",
    "Australia": "4-6 weeks",
    "UAE": "1-2 days",
    "Singapore": "3-5 days",
    "Germany": "4-15 days",
    "Japan": "4-7 days",
}


def get_country_list():
    """Return list of all available countries."""
    return sorted(VISA_REQUIREMENTS.keys())


def get_country_info(country_code: str):
    """Get all visa types and requirements for a country."""
    return VISA_REQUIREMENTS.get(country_code, None)


def get_visa_type_info(country_code: str, visa_type: str):
    """Get specific visa type details."""
    country = VISA_REQUIREMENTS.get(country_code)
    if not country:
        return None
    return country.get("visa_types", {}).get(visa_type, None)


def search_countries(query: str):
    """Search countries by name or code."""
    query = query.lower()
    results = []
    for code, data in VISA_REQUIREMENTS.items():
        if query in code.lower() or query in data["display_name"].lower():
            results.append({"code": code, "name": data["display_name"]})
    return results


def get_document_checklist(country_code: str, visa_type: str):
    """Get document checklist for a specific visa."""
    info = get_visa_type_info(country_code, visa_type)
    if not info:
        return None
    return info.get("documents", [])


def format_visa_details(country_code: str, visa_type: str):
    """Format visa details as readable text."""
    info = get_visa_type_info(country_code, visa_type)
    if not info:
        return "Visa details not found."
    
    text = f"""
╔═══════════════════════════════════════════════════════╗
║ {info['name'].upper()}
║ {VISA_REQUIREMENTS[country_code]['display_name'].upper()}
╚═══════════════════════════════════════════════════════╝

📋 VISA DETAILS:
  Duration: {info.get('duration', 'N/A')}
  Processing: {info.get('processing_time', 'N/A')}
  Validity: {info.get('validity', 'N/A')}
  Cost: {info.get('cost_usd') or info.get('cost_cad') or info.get('cost_gbp') or info.get('cost_aud') or info.get('cost_aed') or info.get('cost_sgd') or info.get('cost_eur') or info.get('cost_jpy') or 'Contact'} 

📝 REQUIRED DOCUMENTS:
"""
    for i, doc in enumerate(info.get('documents', []), 1):
        text += f"  {i}. {doc}\n"
    
    text += f"""
⚠️  REQUIREMENTS:
  {info.get('requirements_text', 'N/A')}

💡 NOTES:
  {info.get('notes', 'N/A')}
"""
    return text
