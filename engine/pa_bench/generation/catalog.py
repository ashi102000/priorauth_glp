"""Static vocabularies for chart generation (generator-only).

Codes: only codes we are confident in are used. Medications are text-only CodeableConcepts
(no RxNorm codes, to avoid fabricating identifiers). See DECISIONS.md.
"""

FIRST_NAMES = {
    "female": ["Maria", "Jennifer", "Aisha", "Linda", "Priya", "Rosa", "Karen", "Mei", "Tanya", "Grace",
               "Deborah", "Fatima", "Laura", "Nicole", "Yolanda", "Hannah", "Sofia", "Denise", "Julia", "Keisha"],
    "male": ["James", "Robert", "Carlos", "David", "Anil", "Marcus", "Kevin", "Thomas", "Luis", "Daniel",
             "Brian", "Omar", "Steven", "Hiro", "Andre", "Patrick", "Samuel", "Victor", "Eric", "Jamal"],
}
LAST_NAMES = ["Alvarez", "Brooks", "Chen", "Dawson", "Ellison", "Fernandez", "Gupta", "Harper", "Ibrahim",
              "Jensen", "Kowalski", "Lopez", "Morrison", "Nguyen", "Okafor", "Patel", "Quinn", "Reyes",
              "Sullivan", "Thompson", "Underwood", "Vasquez", "Whitaker", "Yamamoto", "Zimmerman",
              "Bennett", "Castillo", "Douglas", "Foster", "Hughes"]

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"

# key -> (snomed code, display, id suffix)
CONDITIONS = {
    "hypertension": ("38341003", "Hypertensive disorder", "HTN"),
    "dyslipidemia": ("370992007", "Dyslipidemia", "DYSLIP"),
    "prediabetes": ("714628002", "Prediabetes", "PREDM"),
    "obesity": ("414916001", "Obesity", "OBESITY"),
    "overweight": ("238131007", "Overweight", "OVERWT"),
}
# Filler conditions deliberately exclude weight-related comorbidities (OSA, T2D, OA, CVD, etc.)
FILLER_CONDITIONS = [
    ("367498001", "Seasonal allergic rhinitis", "ALLERGY"),
    ("235595009", "Gastroesophageal reflux disease", "GERD"),
    ("279039007", "Low back pain", "LBP"),
    ("34713006", "Vitamin D deficiency", "VITD"),
    ("197480006", "Anxiety disorder", "ANX"),
    ("37796009", "Migraine", "MIGRAINE"),
    ("43116000", "Eczema", "ECZEMA"),
]

OBS_CODES = {
    "WT": ("29463-7", "Body weight", "kg"),
    "BMI": ("39156-5", "Body mass index (BMI) [Ratio]", "kg/m2"),
    "HT": ("8302-2", "Body height", "cm"),
    "BP": ("85354-9", "Blood pressure panel with all children optional", None),
    "A1C": ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%"),
    "LDL": ("13457-7", "Cholesterol in LDL [Mass/volume] in Serum or Plasma by calculation", "mg/dL"),
    "HDL": ("2085-9", "Cholesterol in HDL [Mass/volume] in Serum or Plasma", "mg/dL"),
    "TG": ("2571-8", "Triglyceride [Mass/volume] in Serum or Plasma", "mg/dL"),
    "VITD": ("1989-3", "25-hydroxyvitamin D3 [Mass/volume] in Serum or Plasma", "ng/mL"),
    "TSH": ("3016-3", "Thyrotropin [Units/volume] in Serum or Plasma", "m[IU]/L"),
}

# DocumentReference.type (LOINC) by note class
DOC_TYPES = {
    "progress": ("11506-3", "Progress note"),
    "consult": ("11488-4", "Consult note"),
    "hp": ("34117-2", "History and physical note"),
    "note": ("34109-9", "Note"),
}

# Setting code (ID segment) -> (display, author_role, doc type key, in_person)
SETTINGS = {
    "PCP": ("Primary care progress note", "Primary care physician", "progress", True),
    "APE": ("Annual physical exam", "Primary care physician", "hp", True),
    "NUTR": ("Nutrition / dietitian note", "Registered dietitian", "consult", True),
    "TEL": ("Telephone encounter", "RN, primary care", "note", False),
    "MSG": ("Patient portal message", "Patient / MA reply", "note", False),
    "OSR": ("Outside records (scanned)", "Outside clinic", "note", False),
    "DERM": ("Dermatology consult", "Dermatologist", "consult", True),
    "UC": ("Urgent care visit", "Urgent care NP", "progress", True),
    "IMM": ("Immunization visit", "RN, primary care", "note", True),
    "ORTH": ("Orthopedics consult", "Orthopedic surgeon", "consult", True),
    "OPH": ("Ophthalmology visit", "Ophthalmologist", "consult", True),
    "LAB": ("Lab result follow-up", "Primary care physician", "note", False),
    "PT": ("Physical therapy note", "Physical therapist", "progress", True),
    "GI": ("Gastroenterology procedure note", "Gastroenterologist", "consult", True),
    "PHARM": ("Pharmacist medication review", "Clinical pharmacist", "note", False),
}

DIET_PLANS = [
    "reduced-calorie meal plan of about {kcal} kcal/day with food logging in a phone app",
    "Mediterranean-style reduced-calorie diet, cutting sugar-sweetened drinks, target ~{kcal} kcal/day",
    "portion-controlled plate method with a daily food diary, ~{kcal} kcal/day",
    "calorie tracking (~{kcal} kcal/day), cutting late-night snacking and takeout",
]
EXERCISE_PLANS = [
    "walking about 30 minutes {days} days a week",
    "stationary bike 30–40 minutes {days} days a week",
    "gym sessions (treadmill + light weights) {days} days a week, ~150 min/week",
    "water aerobics / lap swimming {days} times a week",
    "brisk walking with a coworker at lunch {days} days a week",
]
PROGRAM_NAMES = [
    "the clinic's Healthy Weight lifestyle program",
    "a dietitian-led weight management program",
    "the health system's 12-month lifestyle modification program",
    "an employer-sponsored weight management program with monthly coaching",
]

# Filler chronic meds by condition key; generic fillers
CONDITION_MEDS = {
    "hypertension": ["lisinopril 10 mg PO daily", "amlodipine 5 mg PO daily", "losartan 50 mg PO daily"],
    "dyslipidemia": ["atorvastatin 20 mg PO daily", "rosuvastatin 10 mg PO daily"],
}
FILLER_MEDS = ["cetirizine 10 mg PO daily PRN", "omeprazole 20 mg PO daily", "vitamin D3 2000 IU PO daily",
               "ibuprofen 400 mg PO PRN pain", "fluticasone nasal spray 1 spray each nostril daily",
               "sertraline 50 mg PO daily", "sumatriptan 50 mg PO PRN migraine", "triamcinolone 0.1% cream BID PRN"]

# Distractor note templates. trap=True: contains weight/diet/exercise/program vocabulary but is
# irrelevant to weight-management criteria (retrieval hard negatives).
DISTRACTORS = [
    {"setting": "DERM", "topic": "seborrheic keratosis on back, reassurance; cryotherapy of irritated lesion", "trap": False},
    {"setting": "DERM", "topic": "intertrigo in inframammary/abdominal skin folds; topical antifungal, keep area dry", "trap": True, "trap_concepts": ["weight_management_program"]},
    {"setting": "UC", "topic": "viral upper respiratory infection, 4 days of congestion/cough; supportive care", "trap": False},
    {"setting": "UC", "topic": "acute sinusitis symptoms 10 days; amoxicillin-clavulanate", "trap": False},
    {"setting": "IMM", "topic": "seasonal influenza vaccine administered, no reaction", "trap": False},
    {"setting": "IMM", "topic": "Tdap booster administered; COVID booster discussed", "trap": False},
    {"setting": "ORTH", "topic": "right ankle sprain after misstep on stairs; weight-bearing as tolerated in boot, ice/elevation", "trap": True, "trap_concepts": ["exercise"]},
    {"setting": "ORTH", "topic": "left shoulder impingement; subacromial injection; home exercise program for rotator cuff", "trap": True, "trap_concepts": ["exercise", "weight_management_program"]},
    {"setting": "PT", "topic": "PT for mechanical low back pain: core stabilization home exercise program, 6-visit plan of care", "trap": True, "trap_concepts": ["exercise", "weight_management_program"]},
    {"setting": "OPH", "topic": "routine dilated eye exam, mild myopia, new glasses prescription", "trap": False},
    {"setting": "APE", "topic": "annual physical: age-appropriate screening, vaccines reviewed, no acute complaints", "trap": False},
    {"setting": "LAB", "topic": "vitamin D level low-normal; continue supplement", "trap": False},
    {"setting": "LAB", "topic": "TSH within normal limits; no thyroid follow-up needed", "trap": False},
    {"setting": "LAB", "topic": "fasting lipid panel reviewed; instructions to fast 10–12 h before next draw", "trap": True, "trap_concepts": ["diet"]},
    {"setting": "GI", "topic": "screening colonoscopy, 2 small polyps removed; clear liquid diet day before, resume regular diet", "trap": True, "trap_concepts": ["diet"]},
    {"setting": "UC", "topic": "exercise-induced bronchospasm while jogging in cold air; albuterol before exertion", "trap": True, "trap_concepts": ["exercise"]},
    {"setting": "MSG", "topic": "portal message asking to reschedule appointment and for a work note", "trap": False},
    {"setting": "TEL", "topic": "refill request for allergy medication; sent to pharmacy", "trap": False},
    {"setting": "PHARM", "topic": "pharmacist review of OTC supplements, no interactions", "trap": False},
    {"setting": "DERM", "topic": "mild acne/rosacea flare; topical metronidazole", "trap": False},
    {"setting": "UC", "topic": "urinary tract infection symptoms; nitrofurantoin", "trap": False},
    {"setting": "OSR", "topic": "outside emergency department records: kidney stone, passed spontaneously; urology follow-up PRN", "trap": False},
    {"setting": "TEL", "topic": "call to confirm lab appointment time and fasting instructions for bloodwork", "trap": True, "trap_concepts": ["diet"]},
    {"setting": "MSG", "topic": "portal question about travel vaccines for an upcoming trip", "trap": False},
    {"setting": "LAB", "topic": "CBC and CMP within normal limits; no action needed", "trap": False},
    {"setting": "OSR", "topic": "outside dental office medical clearance form, no restrictions", "trap": False},
    {"setting": "MSG", "topic": "portal message: asks for a copy of immunization record for gym membership paperwork", "trap": True, "trap_concepts": ["exercise"]},
]

MUST_NOT_SAY = [
    "meets criteria", "meets the criteria", "satisfies", "qualifies", "prior authorization",
    "insurance requirement", "6-month requirement", "six-month requirement", "criterion", "eligible for coverage",
    "documented for PA",
]
