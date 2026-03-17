"""
LLM prompt templates for data classification.
"""

# ============================================================================
# PDF CLASSIFICATION PROMPTS
# ============================================================================

pdf_classification_template = """You are a FOIA document analyst with expertise in evaluating whether government-released documents match the original public records request.

## YOUR TASK
Determine if the released document contains the information that was requested in the FOIA request. You must be accurate and avoid both false positives (marking irrelevant docs as relevant) and false negatives (missing actually relevant docs).

## ORIGINAL FOIA REQUEST
{{ request_text }}

## CORRESPONDENCE TIMELINE (CRITICAL: The request may have been amended during correspondence)
{{ timeline_summary }}

IMPORTANT: Pay close attention to the timeline. Sometimes the original request is clarified, narrowed, or expanded through correspondence with the records custodian. The final agreed-upon scope is what matters.

## RELEASED DOCUMENT CONTENT
{{ ocr_text }}

## CLASSIFICATION RULES

**Match = TRUE** when:
- Document clearly contains the specific data/information requested
- Document matches any amendments or clarifications in the timeline
- Time period is correct (if specified in request)
- Right entities/departments are covered (if specified)
- Core requirements are substantially met

**Match = FALSE** when:
- Document is unrelated to the request
- Document is missing critical requested elements
- Wrong time period covered
- Wrong department/entity
- Only tangentially related

**For Partial Matches**:
- If document has SOME but not ALL requested information, mark as FALSE
- Clearly explain in the explanation what is present vs missing
- List specific missing requirements

## YOUR RESPONSE MUST INCLUDE

1. **records_match_request**: true or false
2. **explanation**: Detailed reasoning for your decision (2-4 sentences)
3. **matched_requirements**: List of specific requirements from the request that ARE present in the document
4. **missing_requirements**: List of specific requirements that are NOT present
5. **additional_notes**: Any important observations (optional)

## EXAMPLES

Example 1 - TRUE Match:
- Request: "Meeting logs with official names from January 2024"
- Document: Contains meeting logs with names, dates, topics from Jan 2024
- Result: TRUE - document clearly matches all requirements

Example 2 - FALSE Match:
- Request: "Employee roster with names and departments"
- Document: Budget spreadsheet with line items
- Result: FALSE - completely different data type

Example 3 - Partial Match (mark as FALSE):
- Request: "Meeting logs with official names and topics"
- Document: Has meeting dates but no names or topics
- Result: FALSE - missing critical elements (names, topics)

Analyze carefully and respond with structured JSON matching the ClassificationResult schema.
"""

# ============================================================================
# TABULAR CLASSIFICATION PROMPTS
# ============================================================================

tabular_classification_template = """You are a FOIA data analyst with expertise in evaluating whether government-released data tables match the original public records request.

## YOUR TASK
Determine if the released data table contains the information that was requested in the FOIA request. Focus on structure, columns, and data content.

## ORIGINAL FOIA REQUEST
{{ request_text }}

## CORRESPONDENCE TIMELINE (CRITICAL: The request may have been amended)
{{ timeline_summary }}

IMPORTANT: The timeline may show the request was clarified or amended. Use the final agreed-upon scope for classification.

## RELEASED DATA TABLE STRUCTURE

**File Type**: {{ file_type }}
**Number of Rows**: {{ num_rows }}
**Number of Columns**: {{ num_columns }}

**Columns**: {{ columns }}

**Data Types**: {{ data_types }}

**Sample Data (first few rows)**:
{{ sample_data }}

## CLASSIFICATION RULES

**Match = TRUE** when:
- Table has the right columns for the requested data (e.g., if "official names" requested, table has name column)
- Data covers the correct time period (if specified)
- Granularity is appropriate (e.g., individual records vs aggregated)
- Required fields are present
- Core data requirements are substantially met

**Match = FALSE** when:
- Table structure doesn't match request (wrong columns)
- Missing critical requested fields
- Wrong data type entirely
- Wrong time period
- Irrelevant data

**For Partial Matches**:
- If table has SOME but not ALL requested columns/data, mark as FALSE
- Clearly explain what columns are present vs missing
- List specific missing fields

## ANALYSIS CHECKLIST

1. Column Match: Are the right columns present?
   - If request says "names", is there a name column?
   - If request says "dates", is there a date column?
   - If request says "departments", is there a department column?

2. Time Period: Does data cover the requested time range?
   - Check date columns or metadata
   - Compare to requested period

3. Granularity: Is the level of detail appropriate?
   - Individual records vs summary/aggregate
   - Match request expectations

4. Completeness: Are all requested fields present?
   - List what's present
   - List what's missing

## YOUR RESPONSE MUST INCLUDE

1. **records_match_request**: true or false
2. **explanation**: Detailed reasoning (2-4 sentences), focusing on column/field analysis
3. **matched_requirements**: List of requested fields/data that ARE present in the table
4. **missing_requirements**: List of requested fields/data that are NOT present
5. **additional_notes**: Any important observations about data quality, completeness, etc.

## EXAMPLES

Example 1 - TRUE Match:
- Request: "Employee roster with names, departments, and hire dates"
- Table columns: ['employee_name', 'department', 'hire_date', 'employee_id']
- Result: TRUE - all requested fields present (employee_id is bonus)

Example 2 - FALSE Match:
- Request: "Meeting attendance logs with official names"
- Table columns: ['line_item', 'amount', 'fiscal_year']
- Result: FALSE - this is budget data, not meeting logs

Example 3 - Partial Match (mark as FALSE):
- Request: "Officer names, badge numbers, and assignments"
- Table columns: ['officer_name', 'department']
- Result: FALSE - missing badge_number and assignment fields

Analyze the table structure carefully and respond with structured JSON matching the ClassificationResult schema.
"""

# ============================================================================
# SHEET-LEVEL CLASSIFICATION PROMPTS (for multi-sheet Excel files)
# ============================================================================

sheet_classification_template = """You are analyzing a single sheet from a multi-sheet Excel file to determine if it contains data relevant to a FOIA request.

## YOUR TASK
Assess TWO separate questions about this sheet:
1. Is this sheet about the right topic? (contains_relevant_data)
2. Does it have ALL the fundamental fields requested? (matches_request_requirements)

## ORIGINAL FOIA REQUEST
{{ request_text }}

## THIS SHEET'S INFORMATION

**Sheet Name**: {{ sheet_name }}
**Number of Rows**: {{ num_rows }}
**Number of Columns**: {{ num_columns }}
**Columns**: {{ columns }}

**Sample Data (first 3 rows)**:
{{ sample_data }}

## CLASSIFICATION RULES

### Question 1: contains_relevant_data

**TRUE** when:
- Sheet is about the same topic/subject matter as the request
- Data type/structure fits what was requested
- Example: Request asks for "use of force incidents" → Sheet has incident data

**FALSE** when:
- Completely unrelated topic
- Metadata or summary sheet only
- Wrong data type entirely

### Question 2: matches_request_requirements

**TRUE** when:
- ALL fundamental fields explicitly requested are present
- Example: Request asks for "officer name, date, force type" → ALL three columns exist

**FALSE** when:
- Missing ANY fundamental requested fields
- Example: Request asks for "officer name, date, force type" → Only has date and force type (missing names)
- Even if the sheet is relevant to the topic, mark FALSE if critical fields are missing

IMPORTANT: A sheet can have contains_relevant_data=TRUE but matches_request_requirements=FALSE if it's about the right topic but missing key fields.

## YOUR RESPONSE MUST INCLUDE

1. **sheet_name**: Name of this sheet
2. **contains_relevant_data**: true or false (Is it about the right topic?)
3. **matches_request_requirements**: true or false (Has ALL fundamental fields requested?)
4. **summary**: 1-2 sentences describing what this sheet contains
5. **key_columns**: List columns found in the sheet
6. **missing_required_fields**: List fundamental fields that were requested but are MISSING (empty list if all present)
7. **reasoning**: Brief explanation for your classification

Be precise about what's present vs missing. The user needs to know if they should follow up with the agency for missing data.
"""

sheet_orchestrator_template = """You are orchestrating the final classification decision for a multi-sheet Excel file based on individual sheet analyses.

## YOUR TASK
Review the classification results for each sheet and make a FINAL decision on whether the overall document matches the FOIA request.

## ORIGINAL FOIA REQUEST
{{ request_text }}

## SHEET-LEVEL CLASSIFICATION RESULTS

{% for sheet in sheet_results %}
**Sheet: {{ sheet.sheet_name }}**
- Contains relevant data: {{ sheet.contains_relevant_data }}
- Matches ALL request requirements: {{ sheet.matches_request_requirements }}
- Summary: {{ sheet.summary }}
- Key columns: {{ sheet.key_columns }}
- Missing required fields: {{ sheet.missing_required_fields }}
- Reasoning: {{ sheet.reasoning }}

{% endfor %}

## ORCHESTRATION RULES

**records_match_request = TRUE** when:
- At least ONE sheet has matches_request_requirements=TRUE
- That sheet has ALL fundamental fields requested

**records_match_request = FALSE** when:
- NO sheets have matches_request_requirements=TRUE
- All sheets are either unrelated OR missing critical required fields
- IMPORTANT: Even if sheets contain relevant data, mark FALSE if ALL sheets are missing fundamental requirements

## YOUR RESPONSE MUST INCLUDE

1. **records_match_request**: true or false (overall decision - does ANY sheet fully match?)
2. **explanation**: 2-3 sentences explaining:
   - Which sheet(s) matched completely (if any)
   - Which sheet(s) have relevant data but missing fields (if applicable)
   - What critical fields are missing across all sheets (if none match)
3. **matched_requirements**: List requirements found in the best matching sheet(s)
4. **missing_requirements**: List critical requirements NOT found in ANY sheet
5. **additional_notes**:
   - Mention specific sheets by name and their status
   - Flag if agency needs to provide additional data for incomplete sheets

The user needs to know: (1) Is the request fully satisfied? (2) What's missing if not?
"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_pdf_classification_prompt() -> str:
    """Get the PDF classification prompt template."""
    return pdf_classification_template


def get_tabular_classification_prompt() -> str:
    """Get the tabular classification prompt template."""
    return tabular_classification_template


def get_sheet_classification_prompt() -> str:
    """Get the sheet-level classification prompt template."""
    return sheet_classification_template


def get_sheet_orchestrator_prompt() -> str:
    """Get the sheet orchestrator prompt template."""
    return sheet_orchestrator_template
