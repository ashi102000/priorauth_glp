"""Concept lexicon for criterion-specific retrieval and structured-data filters.

Written from general clinical vocabulary for GLP-1 prior authorization — not derived from the cohort's
annotations or ground truth.
"""
CONCEPT_TERMS: dict[str, list[str]] = {
    "weight_management_program": ["weight management program", "lifestyle program", "lifestyle modification",
                                  "healthy weight", "weight loss program", "dietitian", "nutrition", "coaching",
                                  "enrolled", "referred", "program", "structured", "behavioral", "follow-up"],
    "diet": ["diet", "dietary", "calorie", "kcal", "meal plan", "food log", "food diary", "portion", "plate method",
             "reduced-calorie", "mediterranean", "soda", "sugar-sweetened", "snacking", "takeout", "eating"],
    "exercise": ["exercise", "physical activity", "walking", "walk", "gym", "treadmill", "bike", "swimming",
                 "water aerobics", "active", "workout", "weights"],
    "temporal": ["started", "starting", "began", "since", "months", "stopped", "restart", "restarting", "resumed",
                 "break", "fell off", "declined", "not enrolled", "continues", "continuing", "earlier this year"],
    "response": ["plateau", "weight", "change", "despite", "adherence", "improvement"],
    "anti_obesity_medication": ["ozempic", "wegovy", "saxenda", "zepbound", "mounjaro", "semaglutide", "tirzepatide",
                                "liraglutide", "orlistat", "xenical", "phentermine", "qsymia", "contrave",
                                "glp-1", "injection", "shot", "weight-loss medication", "telehealth", "stopped",
                                "discontinued", "fill", "medications reviewed", "medication list"],
    "comorbidity": ["hypertension", "htn", "blood pressure", "bp", "dyslipidemia", "hyperlipidemia", "cholesterol",
                    "ldl", "statin", "diabetes", "a1c", "prediabetes", "sleep apnea", "cardiovascular",
                    "coronary", "resolved"],
}

# criterion -> concepts used to build its retrieval query (the policy JSON supplies extra terms)
CRITERION_CONCEPTS: dict[str, list[str]] = {
    "weight_management_program": ["weight_management_program", "diet", "exercise"],
    "program_6_months": ["weight_management_program", "diet", "exercise", "temporal"],
    "lifestyle_adjunct": ["diet", "exercise", "weight_management_program", "temporal"],
    "adjunct_diet_and_activity": ["diet", "exercise", "weight_management_program", "temporal"],
    "no_concurrent_glp1": ["anti_obesity_medication"],
    "no_concurrent_pa_weight_loss_med": ["anti_obesity_medication"],
    "comorbidity": ["comorbidity"],
}

# structured filters (matched against Condition / medication display text, lowercase substring)
WEIGHT_RELATED_CONDITION_TERMS = ["hypertens", "dyslipidemia", "hyperlipidemia", "hypercholesterol", "diabetes",
                                  "prediabetes", "sleep apnea", "coronary", "cerebrovascular", "peripheral arter",
                                  "myocardial", "heart failure"]
ANTI_OBESITY_MED_TERMS = ["ozempic", "wegovy", "saxenda", "zepbound", "mounjaro", "semaglutide", "tirzepatide",
                          "liraglutide", "dulaglutide", "trulicity", "exenatide", "rybelsus", "victoza", "orlistat",
                          "xenical", "phentermine", "qsymia", "contrave", "benzphetamine", "diethylpropion",
                          "phendimetrazine", "plenity", "imcivree"]
