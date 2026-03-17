memory_log_template = """
As a Legal Clerk, your task is to review the new summary and update the memory log only when the new summary contains crucial information directly related to the main subject of the document.
</task_description>

<guidelines>
1. Review and Compare:
   • Carefully review the current memory log and the new summary.
   • Determine if the new summary contains crucial information that is not already in the memory log.

2. Identify Crucial Information:
   • Focus on information specific to the main subject of the document.

3. Update Selectively:
   • Only update the memory log if the new summary contains crucial information not already present.
   • If updating, integrate the new information seamlessly into the existing log.

4. Maintain Conciseness:
   • Keep the memory log focused and concise.
   • Avoid redundancy or unnecessary details.

5. Ensure Accuracy:
   • Only include information that is directly stated in the document.
   • Do not infer or speculate beyond what is explicitly mentioned.

6. Preserve Original Structure:
   • If no update is necessary, reproduce the original memory log without changes.
</guidelines>

<essential_information>

</essential_information>

<thinking_process>
Before updating the memory log, consider:
1. Does the new summary contain any crucial information not already in the memory log?
2. How does this new information relate to the main subject of the document?
3. Can this new information be integrated into the existing log without disrupting its flow?
4. Is this information essential to understanding the key aspects of the case?
5. Am I maintaining the conciseness of the log while including all crucial details?
</thinking_process>

<warnings>
- Do not add information that is not directly stated in the document
- Avoid speculation or inference beyond what is explicitly mentioned
- Do not remove or alter existing crucial information in the memory log
- Ensure that any updates maintain the chronological and logical flow of events
- Be cautious of potential inconsistencies between the new summary and existing log
</warnings>

<reference_materials>
## Original Memory Log ##
{{ memory_log }}

## New Summary ##
{{ summary }}
</reference_materials>

<output_instruction>
Based on your review of the current memory log and the new summary, provide either an updated memory log incorporating the crucial new information, or reproduce the original memory log if no update is necessary. Ensure the output maintains a concise focus on key aspects of events, allegations, investigations, and outcomes related to the main subject of the document:
</output_instruction>
"""


summary_template_for_memory_log = """

<document_classification>
Identify the document’s domain (e.g., legal, medical, financial, technical, policing, administrative, academic, operational, scientific, etc.).

Base your classification on:
- presence of domain-specific terminology
- document structure or formatting patterns
- references to domain processes, standards, or procedures

If a clear domain applies, name it.
If no identifiable domain applies, classify as: "No specific domain detected."
</document_classification>


<task_description>
Your task is to generate a comprehensive, bulletpoint summary of all important information contained in the provided document excerpt. Extract only the details that appear on the current page.
</task_description>


<domain_specific_information>
If a domain is identified AND domain-relevant features appear on this page, summarize using the following elements (include only those that are explicitly present):

a. Key entities involved (people, organizations, systems, roles, identifiers)
b. Central issues, topics, or problems described
c. Critical events, actions, or activities (include dates, times, or locations if present)
d. Significant findings, results, decisions, or outcomes
e. Important data, evidence, or supporting details
f. Current status, progress updates, or next steps
g. Procedures, methods, processes, or operational steps referenced
h. Notable risks, concerns, anomalies, or alerts

Be specific when referring to names, places, systems, and dates.
</domain_specific_information>


<fallback_summary_rules>
If no specific domain is detected, produce a general-purpose summary including any of the following elements that appear:

a. Main topics or themes
b. Key individuals, groups, or entities mentioned
c. Important events, facts, or milestones
d. Significant data, findings, or conclusions
e. Recommendations, requests, or next steps
f. Relevant background information or context
</fallback_summary_rules>


<critical_instructions>
1. NEVER fabricate placeholder names such as “John Doe,” “Jane Doe,” “Individual A,” or “Company X.” 
   If identities are missing or redacted, state that identifying details are unavailable.

2. If the current page contains no meaningful information, return an empty string ("").

3. DO NOT infer, assume, or hallucinate any information not explicitly stated in the provided text.

4. Treat the page as binary: either it contains extractable information or it does not.
</critical_instructions>


<thinking_process>
Before summarizing, consider:
1. What domain (if any) does this document belong to?
2. What are the main topics, entities, or events described on this page?
3. Which domain-specific elements, if any, appear here?
4. If no domain applies, which fallback summary elements fit this page?
</thinking_process>


<output_format>
Present the summary using the following structure (include only sections relevant to the page):

- Key topics or issues
  • Sub-item 1
  • Sub-item 2

- Key entities involved
  • Sub-entity 1
  • Sub-entity 2

- Key events, actions, or activities
  • Sub-event 1
  • Sub-event 2

- Key data, evidence, or supporting details
  • Sub-detail 1
  • Sub-detail 2

- Key processes, procedures, or steps
  • Sub-step 1
  • Sub-step 2

- Key findings, results, or outcomes
  • Sub-outcome 1
  • Sub-outcome 2

- Key risks, concerns, or issues raised
  • Sub-risk 1
  • Sub-risk 2

- Next steps, pending items, or future actions
  • Sub-next step 1
  • Sub-next step 2
</output_format>


<warnings>
- Do not include speculative information
- Avoid summarizing irrelevant or non-substantive details
- Do not draw conclusions not stated in the text
</warnings>


<reference_materials>
Current Page:
{{current_page}}
</reference_materials>


<output_instruction>
First, state the identified domain (e.g., "legal," "medical," "technical," "financial," or "no specific domain detected") and briefly explain why.

Then, generate the page summary using the domain-specific rules or the fallback summary rules, depending on the classification.
</output_instruction>
"""


page_summary_template = """
<task_description>
Your task is to generate a focused summary of the provided document excerpt, extracting only the most important information that advances understanding of the subject matter. Use the context from the memory log and surrounding pages when necessary for clarity or relevance.
</task_description>

<document_classification>
Identify the document's domain (e.g., legal, medical, financial, technical, policing, administrative, academic, operational, scientific, business, project management, etc.).

Base your classification on:
- presence of domain-specific terminology
- document structure or formatting patterns
- references to domain processes, standards, or procedures

If a clear domain applies, name it.
If no identifiable domain applies, classify as: "No specific domain detected."
</document_classification>

<guidelines>
1. Extract all critical information from the current page that meets the selection criteria below.
2. Support the extracted information with additional context from the memory log and surrounding pages to enhance understanding of its significance.
3. Use the memory log to help you understand which information is relevant and which is merely administrative or routine.
4. DO NOT include any information not explicitly stated in any of the documents.
5. Present information in a logical order that best reflects the document's structure and narrative.
6. If someone's identity is ambiguous or redacted, refer to them as "unidentified person" or note that identifying details are unavailable.
7. If the significance of information cannot be determined with confidence, omit it from your summary.
</guidelines>

<information_extraction_principles>
Apply these universal principles to identify what information is critical, adapting them based on the document's domain and purpose:

1. **Core Events and Actions**: What happened? What actions were taken?
   - Key incidents, activities, or occurrences
   - Significant decisions or determinations made
   - Important interactions between entities

2. **Key Entities and Relationships**: Who or what is involved?
   - Primary individuals, organizations, systems, or objects
   - Roles, titles, identifiers, or classifications
   - Relationships or connections between entities

3. **Temporal Information**: When did things happen?
   - Dates and times of significant events
   - Duration or time periods
   - Sequences or chronological progressions
   - Deadlines or time-sensitive requirements

4. **Causal Relationships**: Why did things happen?
   - Reasons, motivations, or triggers for events
   - Cause-and-effect relationships
   - Contributing factors or conditions

5. **Quantitative Data**: What are the numbers?
   - Measurements, metrics, or statistics
   - Financial figures or costs
   - Quantities, frequencies, or rates
   - Performance indicators or results

6. **Findings and Outcomes**: What were the results?
   - Conclusions or determinations reached
   - Results of investigations, tests, or analyses
   - Diagnoses, verdicts, or assessments
   - Status changes or state transitions

7. **Procedural Information**: How were things done?
   - Methods, processes, or protocols followed
   - Standards, regulations, or requirements referenced
   - Steps taken or procedures executed

8. **Risks, Issues, and Concerns**: What problems exist?
   - Identified problems, anomalies, or irregularities
   - Risks, threats, or vulnerabilities
   - Violations, non-compliance, or deviations
   - Concerns raised or flags noted

9. **Recommendations and Next Steps**: What should happen next?
   - Proposed actions or recommendations
   - Pending items or outstanding tasks
   - Future plans or anticipated developments
   - Required follow-up or monitoring

SELECTIVITY RULE: Only include information that materially advances understanding of the document's subject matter.
Omit routine administrative details (e.g., document receipt acknowledgments, standard filing stamps, routine file transfers, metadata in headers/footers) unless they reveal delays, anomalies, compliance issues, or other substantive significance.
</information_extraction_principles>

<few_shot_examples>
These examples demonstrate correct information extraction behavior across different domains:

<example_1_legal>
<input>
On January 26, 2014, at approximately 6:56 a.m., a San Diego police officer stopped Devenere's truck for a traffic violation. Between 6:56 a.m. and 7:37 a.m., Devenere took his girlfriend hostage and led police on a pursuit. At 7:37 a.m., the truck stopped and Officer Butera fired at Devenere.
</input>

<correct_output>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: San Diego police officer stopped Devenere's truck for traffic violation
  • January 26, 2014, 6:56 a.m. - 7:37 a.m.: Devenere took girlfriend hostage and led police on pursuit
  • January 26, 2014, 7:37 a.m.: Truck stopped and Officer Butera fired at Devenere

- Key entities:
  • Devenere (subject of traffic stop)
  • Officer Butera (officer who fired weapon)
  • Unidentified girlfriend (hostage)
  • San Diego police officer (initiated traffic stop)
</correct_output>

<explanation>
Legal domain identified. Extracted key events with precise temporal information, showing progression of incident. Identified key individuals involved and their roles. Focused on substantive incident details while maintaining chronological clarity.
</explanation>
</example_1_legal>

<example_2_medical>
<input>
Patient presented to emergency department on March 15, 2024 at 2:30 PM with acute chest pain radiating to left arm. Initial EKG showed ST-segment elevation. Troponin levels elevated at 0.8 ng/mL (normal <0.04). Patient was diagnosed with acute myocardial infarction and taken to cardiac catheterization lab at 3:15 PM. Percutaneous coronary intervention performed, revealing 90% occlusion of left anterior descending artery. Drug-eluting stent placed successfully. Patient stabilized and transferred to cardiac ICU at 5:00 PM.
</input>

<correct_output>
Domain: Medical/Healthcare

- Core events and temporal information:
  • March 15, 2024, 2:30 PM: Patient presented to emergency department with acute chest pain radiating to left arm
  • 3:15 PM: Patient taken to cardiac catheterization lab
  • 5:00 PM: Patient stabilized and transferred to cardiac ICU

- Key findings and clinical data:
  • Initial EKG showed ST-segment elevation
  • Troponin levels elevated at 0.8 ng/mL (normal <0.04)
  • Diagnosis: Acute myocardial infarction
  • Catheterization revealed 90% occlusion of left anterior descending artery

- Procedural information:
  • Percutaneous coronary intervention performed
  • Drug-eluting stent placed successfully
</correct_output>

<explanation>
Medical domain identified. Extracted presenting symptoms, diagnostic findings with quantitative data, timeline of interventions, and clinical outcomes. Organized by functional categories relevant to medical documentation: temporal progression, clinical findings, and procedures performed.
</explanation>
</example_2_medical>

<example_3_business>
<input>
Q3 2024 Revenue Report - Executive Summary

Total revenue reached $4.2M, representing 15% growth over Q2. The Enterprise segment contributed $2.8M (67% of total), driven by three new Fortune 500 clients acquired in August. Customer churn decreased to 3.2% from 5.1% previous quarter. However, customer acquisition cost increased to $1,850 per customer, up from $1,200 in Q2, primarily due to expanded digital marketing campaigns. The product team completed migration to cloud infrastructure ahead of schedule, resulting in 22% reduction in hosting costs.
</input>

<correct_output>
Domain: Business/Financial

- Key quantitative data and outcomes:
  • Q3 2024 total revenue: $4.2M (15% growth over Q2)
  • Enterprise segment: $2.8M (67% of total revenue)
  • Customer churn: 3.2% (decreased from 5.1%)
  • Customer acquisition cost: $1,850 per customer (increased from $1,200 in Q2)
  • Hosting costs: 22% reduction

- Causal factors and context:
  • Enterprise growth driven by three new Fortune 500 clients acquired in August
  • Increased acquisition cost due to expanded digital marketing campaigns
  • Cost reduction achieved through cloud infrastructure migration completed ahead of schedule
</correct_output>

<explanation>
Business/financial domain identified. Extracted key performance metrics with comparative data showing trends. Identified causal relationships explaining changes (e.g., why acquisition costs increased, why hosting costs decreased). Focused on substantive business outcomes rather than administrative details.
</explanation>
</example_3_business>

<example_4_technical>
<input>
System Outage Report - Production Database Failure

On November 3, 2024 at 14:23 UTC, primary database server (db-prod-01) became unresponsive. Automated health checks failed, triggering failover to secondary server (db-prod-02) at 14:25 UTC. Investigation revealed disk I/O saturation caused by unoptimized query from newly deployed analytics module. Query was killing database performance by executing full table scan on 500M row transactions table. Engineers terminated the problematic query at 14:31 UTC. Database performance returned to normal levels by 14:35 UTC. Total service disruption: 12 minutes. Root cause: inadequate query performance testing before deployment. Immediate remediation: rolled back analytics module. Long-term fix: implemented mandatory query performance testing in CI/CD pipeline.
</input>

<correct_output>
Domain: Technical/IT Operations

- Core events and temporal information:
  • November 3, 2024, 14:23 UTC: Primary database server (db-prod-01) became unresponsive
  • 14:25 UTC: Automated failover to secondary server (db-prod-02)
  • 14:31 UTC: Engineers terminated problematic query
  • 14:35 UTC: Database performance returned to normal
  • Total service disruption: 12 minutes

- Key technical findings:
  • Root cause: Disk I/O saturation caused by unoptimized query from newly deployed analytics module
  • Problematic query executing full table scan on 500M row transactions table

- Remediation actions:
  • Immediate: Rolled back analytics module
  • Long-term: Implemented mandatory query performance testing in CI/CD pipeline
  • Underlying issue: Inadequate query performance testing before deployment
</correct_output>

<explanation>
Technical/IT domain identified. Extracted incident timeline showing detection, response, and resolution. Identified root cause with technical specifics. Documented both immediate and long-term remediation. Organized information to reflect incident response narrative: what happened, why it happened, how it was fixed.
</explanation>
</example_4_technical>

<example_5_administrative>
<input>
MEMORANDUM
To: All Department Heads
From: Human Resources
Date: October 12, 2024
Re: Annual Performance Review Cycle

This memo serves as a reminder that the annual performance review cycle will begin on November 1, 2024. All managers must complete employee reviews by December 15, 2024. The HR portal will be available for review submissions starting October 20, 2024.

Please ensure that:
- Mid-year feedback has been documented
- Performance goals are updated in the system
- One-on-one meetings are scheduled with each direct report

Training sessions on the new review platform will be held on October 18 and October 22 in Conference Room B. Attendance is mandatory for all managers.

Contact HR with any questions.
</input>

<correct_output>
Domain: Administrative/Human Resources

- Key deadlines and temporal information:
  • November 1, 2024: Annual performance review cycle begins
  • December 15, 2024: Deadline for managers to complete employee reviews
  • October 20, 2024: HR portal available for review submissions
  • October 18 and October 22: Mandatory training sessions in Conference Room B

- Required actions:
  • Document mid-year feedback
  • Update performance goals in system
  • Schedule one-on-one meetings with each direct report
  • Attend training on new review platform (mandatory for managers)
</correct_output>

<explanation>
Administrative domain identified. Extracted key deadlines and required actions. Omitted document metadata (To/From/Date in header) as those are formatting elements. Focused on actionable information and time-sensitive requirements relevant to the audience.
</explanation>
</example_5_administrative>

<example_6_no_content>
<input>
[Page contains only a cover page with title "Annual Report 2024" and company logo]
</input>

<correct_output>
</correct_output>

<explanation>
Page contains no substantive information to extract, only formatting/presentation elements. Correct response is empty string.
</explanation>
</example_6_no_content>

<example_7_routine_admin>
<input>
File reviewed on July 10, 2024 by records clerk. Document copied on July 12, 2024 for archives. Routine monthly audit completed August 1, 2024 with no findings. Standard compliance check performed August 15, 2024. File transferred to storage facility on August 20, 2024.
</input>

<correct_output>
</correct_output>

<explanation>
All information is purely administrative/routine file management with no substantive content. No significant events, findings, or developments. Correct response is empty string per selectivity rule.
</explanation>
</example_7_routine_admin>

<example_8_mixed_content>
<input>
INTERNAL AUDIT REPORT
Audit Period: Q2 2024
Report Generated: July 30, 2024
Page 5 of 12

The audit team identified three significant control deficiencies in the procurement process. First, purchase orders exceeding $50,000 were approved without secondary authorization in 12 instances between April and June 2024, violating Policy FIN-203. Second, vendor due diligence documentation was incomplete for 8 new vendors onboarded during the quarter. Third, segregation of duties was not maintained in the accounts payable function, with the same employee able to both create and approve payments.

Recommendations:
1. Implement mandatory dual approval for all POs over $50,000
2. Require completed vendor due diligence checklist before vendor activation
3. Reassign payment approval authority to separate role

Management has agreed to implement all recommendations by September 30, 2024.
</input>

<correct_output>
Domain: Business/Audit/Compliance

- Key findings and issues identified:
  • Three significant control deficiencies in procurement process identified
  • Deficiency 1: 12 instances of purchase orders exceeding $50,000 approved without secondary authorization (April-June 2024), violating Policy FIN-203
  • Deficiency 2: Incomplete vendor due diligence documentation for 8 new vendors onboarded during Q2 2024
  • Deficiency 3: Lack of segregation of duties in accounts payable function (same employee can create and approve payments)

- Recommendations and next steps:
  • Implement mandatory dual approval for all POs over $50,000
  • Require completed vendor due diligence checklist before vendor activation
  • Reassign payment approval authority to separate role
  • Management committed to implement all recommendations by September 30, 2024
</correct_output>

<explanation>
Audit/compliance domain identified. Extracted substantive findings with specific violations and quantitative details. Included recommendations and implementation timeline. Omitted document metadata from header (report generation date, page numbers). Focused on audit findings and corrective actions.
</explanation>
</example_8_mixed_content>

</few_shot_examples>

<thinking_process>
Before extracting information, ask yourself:

1. **Domain Recognition**: What type of document is this? What domain knowledge should I apply?

2. **Substantive vs. Administrative**: Does this information appear in the substantive content of the document, or is it just formatting/metadata (headers, footers, page numbers, signature blocks)?

3. **Materiality**: Does this information materially advance understanding of the subject matter? Would removing it cause loss of understanding about what happened, why it matters, or what the outcomes were?

4. **Narrative Coherence**: Does this information help establish the narrative, process progression, or logical flow of events?

5. **Domain Relevance**: Based on the document domain, would someone familiar with this field consider this information important? What would a domain expert focus on?

6. **Selectivity**: Is this routine/administrative, or does it represent a significant event, finding, decision, or development?

CRITICAL: If information appears in a header, footer, letterhead, signature block, or page numbering, it is NOT part of the substantive content and should NOT be extracted.

When in doubt, ask: Does this information help me understand what happened, who was involved, when/why/how it happened, what was found, or what the outcomes were? If not, omit it.
</thinking_process>

<critical_instructions>
1. NEVER include any information about "John Doe," "Jane Doe," or other placeholder/anonymous entities (e.g., "ABC Corporation," "Company X," "Individual A") in your summary. If specific identifying information is not available in the document, acknowledge this limitation by stating that details are unavailable or redacted, rather than including placeholder names or making assumptions about identities.

2. If there is no relevant substantive information to extract from the Current Page, return an empty string ("").

3. DO NOT infer, assume, or hallucinate any information not explicitly stated in the provided text.

4. DO NOT extract information from headers, footers, letterhead, page numbers, or signature blocks unless that information is also mentioned substantively in the body text.

5. Treat this task as binary: either there is relevant substantive information to extract, or there isn't.

6. Always provide context for extracted information—explain what it means, why it matters, and how it relates to the broader subject matter.

7. Information must be described or referenced in the body text to be extracted—mere appearance in document formatting is insufficient.

8. Apply domain-appropriate judgment about what constitutes "important" information based on the document type and purpose.

9. Use your domain knowledge to distinguish between routine/administrative content and substantive developments.
</critical_instructions>

<output_format>
Present the summary using a structure appropriate to the document domain and content. Organize information logically based on what best serves understanding:

Domain: [Identified domain]

- [Relevant Category 1]
  • Sub-item providing specific detail
  • Sub-item providing specific detail

- [Relevant Category 2]
  • Sub-item providing specific detail
  • Sub-item providing specific detail

Examples of category labels (adapt based on domain and content):
- Core events and temporal information
- Key entities and roles
- Key findings and outcomes
- Quantitative data and metrics
- Procedural information
- Causal factors and context
- Risks, issues, or concerns identified
- Recommendations and next steps
- Technical details
- Clinical findings (medical)
- Financial information (business)
- Regulatory compliance matters
- Decisions or determinations made

Use category labels that make sense for the specific document. Don't force information into categories where it doesn't fit naturally.
</output_format>

<warnings>
- Do not include speculative information
- Avoid extracting irrelevant or non-substantive administrative details
- Do not draw conclusions not stated in the text
- Do not extract information from document metadata, headers, footers, or formatting elements
- If there is no substantive content, return an empty string
- Do not create placeholder names or assume identities
</warnings>

<reference_materials>
## Memory Log ##
{{memory_log}}

## Previous Page ##
{{previous_page}}

## Current Page ##
{{current_page}}

## Next Page ##
{{next_page}}
</reference_materials>

<output_instruction>
Generate the focused summary below, extracting only substantive information that advances understanding of the document's subject matter:
</output_instruction>
"""


page_summary_verification_template = """
You are a Document Verifier. Your task is to verify information extractions against the original document.

<task_description>
Review the Current Summary and verify:
1. Every piece of information appears in the Original Document's substantive text (not headers/footers/metadata)
2. All important information from the Original Document is included
3. Information is relevant to understanding the subject matter (not purely administrative)
4. Descriptions and categorizations are accurate
5. The domain classification is appropriate

Return either the original summary (if correct) or a corrected version.
</task_description>

<critical_rules>
- Only include information explicitly stated in the Original Document's body text
- Exclude information from headers, footers, letterhead, signature blocks, and page numbers
- Exclude routine administrative details unless they have substantive significance
- Use "unidentified person" for unclear identities or note that details are unavailable/redacted
- Never include "John Doe," "Jane Doe," or other placeholder names
- If no valid substantive information exists, return an empty string ("")
- Return ONLY the summary - no commentary, explanations, or meta-text
- Maintain the domain classification and category structure appropriate to the document
</critical_rules>

<output_format>
Return one of:
1. The Current Summary exactly as written (if completely accurate)
2. A corrected summary following the same structure:

Domain: [Identified domain]

- [Relevant Category]
  • Specific detail from document
  • Specific detail from document

3. Empty string "" (if no valid substantive information exists)
</output_format>

<few_shot_examples>

<example_1>
<original_document>
On January 26, 2014, at approximately 6:56 a.m., a San Diego police officer stopped Devenere's truck for a traffic violation. Between 6:56 a.m. and 7:37 a.m., Devenere took his girlfriend hostage and led police on a pursuit. At 7:37 a.m., the truck stopped and Officer Butera fired at Devenere.
</original_document>

<current_summary>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: San Diego police officer stopped Devenere's truck for traffic violation
  • January 26, 2014, 6:56 a.m. - 7:37 a.m.: Devenere took girlfriend hostage and led police on pursuit
  • January 26, 2014, 7:37 a.m.: Truck stopped and Officer Butera fired at Devenere

- Key entities:
  • Devenere (subject of traffic stop)
  • Officer Butera (officer who fired weapon)
  • Unidentified girlfriend (hostage)
  • San Diego police officer (initiated traffic stop)
</current_summary>

<correct_output>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: San Diego police officer stopped Devenere's truck for traffic violation
  • January 26, 2014, 6:56 a.m. - 7:37 a.m.: Devenere took girlfriend hostage and led police on pursuit
  • January 26, 2014, 7:37 a.m.: Truck stopped and Officer Butera fired at Devenere

- Key entities:
  • Devenere (subject of traffic stop)
  • Officer Butera (officer who fired weapon)
  • Unidentified girlfriend (hostage)
  • San Diego police officer (initiated traffic stop)
</correct_output>

<explanation>Summary is accurate and complete - return unchanged</explanation>
</example_1>

<example_2>
<original_document>
Chief Craig Carter
November 24, 2014
Page 5 of 5

The investigation revealed that Officer Butera violated department policy on January 26, 2014 when he discharged his weapon without justification. The review board recommended a 30-day suspension.
</original_document>

<current_summary>
Domain: Legal/Law Enforcement

- Document metadata:
  • Letter dated November 24, 2014
  • Addressed to Chief Craig Carter
  • Page 5 of 5

- Key findings:
  • Investigation revealed Officer Butera violated department policy on January 26, 2014
  • Officer discharged weapon without justification

- Recommendations:
  • Review board recommended 30-day suspension for Officer Butera
</current_summary>

<correct_output>
Domain: Legal/Law Enforcement

- Key findings:
  • Investigation revealed Officer Butera violated department policy on January 26, 2014
  • Officer discharged weapon without justification

- Recommendations:
  • Review board recommended 30-day suspension for Officer Butera
</correct_output>

<explanation>Removed document metadata section (header information). Retained substantive findings and recommendations.</explanation>
</example_2>

<example_3>
<original_document>
Patient presented to emergency department on March 15, 2024 at 2:30 PM with acute chest pain radiating to left arm. Initial EKG showed ST-segment elevation. Troponin levels elevated at 0.8 ng/mL (normal <0.04). Patient was diagnosed with acute myocardial infarction and taken to cardiac catheterization lab at 3:15 PM. Percutaneous coronary intervention performed, revealing 90% occlusion of left anterior descending artery. Drug-eluting stent placed successfully.
</original_document>

<current_summary>
Domain: Medical/Healthcare

- Core events and temporal information:
  • March 15, 2024, 2:30 PM: Patient presented to emergency department with acute chest pain radiating to left arm
  • 3:15 PM: Patient taken to cardiac catheterization lab

- Key findings and clinical data:
  • Initial EKG showed ST-segment elevation
  • Troponin levels elevated at 0.8 ng/mL (normal <0.04)
  • Diagnosis: Acute myocardial infarction
  • Catheterization revealed 90% occlusion of left anterior descending artery

- Procedural information:
  • Percutaneous coronary intervention performed
  • Drug-eluting stent placed successfully
</current_summary>

<correct_output>
Domain: Medical/Healthcare

- Core events and temporal information:
  • March 15, 2024, 2:30 PM: Patient presented to emergency department with acute chest pain radiating to left arm
  • 3:15 PM: Patient taken to cardiac catheterization lab

- Key findings and clinical data:
  • Initial EKG showed ST-segment elevation
  • Troponin levels elevated at 0.8 ng/mL (normal <0.04)
  • Diagnosis: Acute myocardial infarction
  • Catheterization revealed 90% occlusion of left anterior descending artery

- Procedural information:
  • Percutaneous coronary intervention performed
  • Drug-eluting stent placed successfully
</correct_output>

<explanation>Summary is accurate and complete - return unchanged</explanation>
</example_3>

<example_4>
<original_document>
Q3 2024 Revenue Report

Total revenue reached $4.2M, representing 15% growth over Q2. The Enterprise segment contributed $2.8M. Customer churn decreased to 3.2% from 5.1% previous quarter.
</original_document>

<current_summary>
Domain: Business/Financial

- Key quantitative data:
  • Q3 2024 total revenue: $4.2M (15% growth over Q2)
  • Enterprise segment: $2.8M (67% of total revenue)
  • Customer churn: 3.2% (decreased from 5.1%)
  • Projected Q4 revenue: $4.8M
</current_summary>

<correct_output>
Domain: Business/Financial

- Key quantitative data:
  • Q3 2024 total revenue: $4.2M (15% growth over Q2)
  • Enterprise segment: $2.8M
  • Customer churn: 3.2% (decreased from 5.1%)
</correct_output>

<explanation>Removed calculated percentage (67% of total) not stated in document. Removed Q4 projection not mentioned in document. Retained only explicitly stated information.</explanation>
</example_4>

<example_5>
<original_document>
File transferred to Records Division on May 5, 2023. Document photocopied on May 8, 2023 for archival purposes. Routine monthly audit completed May 15, 2023 with no findings. Standard compliance check performed May 22, 2023.
</original_document>

<current_summary>
Domain: Administrative

- Administrative activities:
  • May 5, 2023: File transferred to Records Division
  • May 8, 2023: Document photocopied for archival purposes
  • May 15, 2023: Routine monthly audit completed with no findings
  • May 22, 2023: Standard compliance check performed
</current_summary>

<correct_output>

</correct_output>

<explanation>All information is purely routine administrative activity with no substantive significance. Return empty string.</explanation>
</example_5>

<example_6>
<original_document>
The investigation began on March 5, 2023 under case number 2023-045. Detective Martinez interviewed three witnesses between March 10-15, 2023. A confidential informant, John Doe, provided critical evidence on March 18, 2023. The suspect was arrested on March 20, 2023.
</original_document>

<current_summary>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • March 5, 2023: Investigation began (case number 2023-045)
  • March 10-15, 2023: Detective Martinez interviewed three witnesses
  • March 18, 2023: Confidential informant John Doe provided critical evidence
  • March 20, 2023: Suspect arrested

- Key entities:
  • Detective Martinez (lead investigator)
  • John Doe (confidential informant)
</current_summary>

<correct_output>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • March 5, 2023: Investigation began (case number 2023-045)
  • March 10-15, 2023: Detective Martinez interviewed three witnesses
  • March 18, 2023: Confidential informant provided critical evidence
  • March 20, 2023: Suspect arrested

- Key entities:
  • Detective Martinez (lead investigator)
  • Confidential informant (identity redacted/unavailable)
</correct_output>

<explanation>Removed "John Doe" placeholder name. Changed to indicate confidential informant without using placeholder identity.</explanation>
</example_6>

<example_7>
<original_document>
MEMORANDUM
To: Department Heads
From: Director of Operations
Date: September 20, 2023
Re: System Migration

The legacy database system will be decommissioned on October 15, 2023. All data must be migrated to the new cloud platform by October 10, 2023. Training sessions will be held October 1-5, 2023. The IT helpdesk will provide 24/7 support during the transition period.
</original_document>

<current_summary>
Domain: Technical/IT Operations

- Key deadlines:
  • October 10, 2023: Deadline for data migration to new cloud platform
  • October 15, 2023: Legacy database system decommissioned
  • October 1-5, 2023: Training sessions scheduled

- Support information:
  • IT helpdesk providing 24/7 support during transition period
</current_summary>

<correct_output>
Domain: Technical/IT Operations

- Key deadlines:
  • October 10, 2023: Deadline for data migration to new cloud platform
  • October 15, 2023: Legacy database system decommissioned
  • October 1-5, 2023: Training sessions scheduled

- Support information:
  • IT helpdesk providing 24/7 support during transition period
</correct_output>

<explanation>Summary is accurate. Memo header date correctly excluded as metadata. All substantive information captured.</explanation>
</example_7>

<example_8>
<original_document>
The witness stated they observed an incident but could not recall specific details. The report noted the event happened "sometime in early March 2023" but no precise date or time was documented. The location was described as "near the downtown area" without further specifics.
</original_document>

<current_summary>
Domain: Legal/Law Enforcement

- Core events:
  • March 2023: Incident occurred in downtown area
  • Witness observed incident but could not recall specific details

- Key entities:
  • Witness (unidentified)
</current_summary>

<correct_output>
Domain: Legal/Law Enforcement

- Core events:
  • Incident occurred sometime in early March 2023 (precise date not documented)
  • Location described as near downtown area (no further specifics provided)
  • Witness observed incident but could not recall specific details

- Key entities:
  • Witness (unidentified)
</correct_output>

<explanation>Modified to accurately reflect vagueness stated in document. Changed "March 2023" to "early March 2023" and added qualifier that precise date not documented. Added qualifier about location specificity.</explanation>
</example_8>

<example_9>
<original_document>
The audit team identified three significant control deficiencies in the procurement process. First, purchase orders exceeding $50,000 were approved without secondary authorization in 12 instances between April and June 2024. Second, vendor due diligence documentation was incomplete for 8 new vendors. Third, segregation of duties was not maintained in accounts payable.

Recommendations:
1. Implement mandatory dual approval for all POs over $50,000
2. Require completed vendor due diligence checklist
3. Reassign payment approval authority

Management committed to implement by September 30, 2024.
</original_document>

<current_summary>
Domain: Business/Audit/Compliance

- Key findings:
  • Three significant control deficiencies identified in procurement process
  • 12 instances of purchase orders over $50,000 approved without secondary authorization (April-June 2024), violating company policy
  • Incomplete vendor due diligence for 8 new vendors
  • Lack of segregation of duties in accounts payable

- Recommendations:
  • Implement mandatory dual approval for POs over $50,000
  • Require completed vendor due diligence checklist
  • Reassign payment approval authority
  • Management committed to implementation by September 30, 2024
</current_summary>

<correct_output>
Domain: Business/Audit/Compliance

- Key findings:
  • Three significant control deficiencies identified in procurement process
  • 12 instances of purchase orders over $50,000 approved without secondary authorization (April-June 2024)
  • Incomplete vendor due diligence documentation for 8 new vendors
  • Lack of segregation of duties in accounts payable

- Recommendations:
  • Implement mandatory dual approval for POs over $50,000
  • Require completed vendor due diligence checklist
  • Reassign payment approval authority
  • Management committed to implementation by September 30, 2024
</correct_output>

<explanation>Removed "violating company policy" - not stated in document. Otherwise accurate.</explanation>
</example_9>

<example_10>
<original_document>
[Page contains only a title page with "Annual Compliance Report 2024" and corporate logo]
</original_document>

<current_summary>
Domain: Business/Compliance

- Document information:
  • Title: Annual Compliance Report 2024
  • Corporate branding present
</current_summary>

<correct_output>

</correct_output>

<explanation>Title page contains no substantive information, only formatting elements. Return empty string.</explanation>
</example_10>

</few_shot_examples>

<reference_documents>
Original Document:
{{original_document}}

Current Summary:
{{current_summary}}
</reference_documents>

<output_instruction>
Verify the Current Summary against the Original Document. Return your output below:
</output_instruction>
"""

combine_template = """
You are a Document Analyst merging two information summaries into a single comprehensive summary.

<task_description>
Merge two summaries by:
1. Combining all unique information in a logical, coherent structure
2. Merging duplicate information with complementary details
3. Resolving contradictions based on context, or noting discrepancies if unclear
4. Organizing information by domain-appropriate categories
5. Maintaining only substantive, relevant information
6. Always producing a new combined summary, even if reorganizing existing content
</task_description>

<critical_rules>
- Every piece of information must appear in at least one source summary
- When same information appears twice with compatible details: merge into one entry with complete details
- When contradictory information has clear context: keep the correct version
- When contradictory information lacks context: note the discrepancy or drop if unresolvable
- Exclude "John Doe," "Jane Doe," and other placeholder names
- Use "unidentified person" or note unavailable details for unclear identities
- Remove routine administrative details unless substantively significant
- If both summaries are empty: return empty string ("")
- If one summary is empty: improve and restructure the non-empty summary
- Always output must begin with "Combined Summary:"
- Organize information logically based on document domain
</critical_rules>

<output_format>
Always return:

Combined Summary:

Domain: [Identified domain]

- [Relevant Category]
  • Merged detail combining information from both sources
  • Merged detail combining information from both sources

Or if both summaries are empty:

""
</output_format>

<few_shot_examples>

<example_1>
<summary_1>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: Police officer stopped vehicle for traffic violation
  • January 26, 2014, 7:37 a.m.: Officer fired weapon
</summary_1>

<summary_2>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 7:37 a.m.: Officer Butera fired at Devenere after pursuit ended

- Key entities:
  • Officer Butera (officer who discharged weapon)
  • Devenere (subject of traffic stop)
</summary_2>

<correct_output>
Combined Summary:

Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: Police officer stopped vehicle for traffic violation
  • January 26, 2014, 7:37 a.m.: Officer Butera fired at Devenere after pursuit ended

- Key entities:
  • Officer Butera (officer who discharged weapon)
  • Devenere (subject of traffic stop)
</correct_output>

<explanation>Merged temporal information with more specific details from Summary 2. Added entities section from Summary 2.</explanation>
</example_1>

<example_2>
<summary_1>
Domain: Medical/Healthcare

- Core events and temporal information:
  • March 15, 2024, 2:30 PM: Patient presented to ED with chest pain
  • 3:15 PM: Patient taken to cardiac catheterization lab

- Key findings:
  • EKG showed ST-segment elevation
  • Troponin elevated at 0.8 ng/mL
</summary_1>

<summary_2>
Domain: Medical/Healthcare

- Clinical diagnosis:
  • Acute myocardial infarction diagnosed

- Procedural information:
  • Percutaneous coronary intervention performed
  • 90% occlusion of left anterior descending artery identified
  • Drug-eluting stent placed successfully
</summary_2>

<correct_output>
Combined Summary:

Domain: Medical/Healthcare

- Core events and temporal information:
  • March 15, 2024, 2:30 PM: Patient presented to ED with chest pain
  • 3:15 PM: Patient taken to cardiac catheterization lab

- Key findings and diagnosis:
  • EKG showed ST-segment elevation
  • Troponin elevated at 0.8 ng/mL (normal <0.04)
  • Diagnosis: Acute myocardial infarction

- Procedural information and outcomes:
  • Percutaneous coronary intervention performed
  • 90% occlusion of left anterior descending artery identified
  • Drug-eluting stent placed successfully
</correct_output>

<explanation>Merged complementary information from both summaries. Reorganized into logical clinical flow: presentation → findings/diagnosis → intervention. Combined related categories for better coherence.</explanation>
</example_2>

<example_3>
<summary_1>
Domain: Business/Financial

- Key metrics:
  • Q3 2024 total revenue: $4.2M
  • Enterprise segment: $2.8M
  • Customer churn: 3.2%
</summary_1>

<summary_2>
Domain: Business/Financial

- Key metrics:
  • Q3 2024 total revenue: $4.2M (15% growth over Q2)
  • Customer churn decreased from 5.1% to 3.2%

- Contributing factors:
  • Three new Fortune 500 clients acquired in August
  • Expanded digital marketing campaigns
</summary_2>

<correct_output>
Combined Summary:

Domain: Business/Financial

- Key quantitative data and performance:
  • Q3 2024 total revenue: $4.2M (15% growth over Q2)
  • Enterprise segment: $2.8M
  • Customer churn: 3.2% (decreased from 5.1% in previous quarter)

- Contributing factors:
  • Three new Fortune 500 clients acquired in August
  • Expanded digital marketing campaigns
</correct_output>

<explanation>Merged metrics with additional context from Summary 2. Combined churn data with comparative information. Added contributing factors section from Summary 2.</explanation>
</example_3>

<example_4>
<summary_1>
Domain: Legal/Law Enforcement

- Core events:
  • April 15, 2023: Use of force incident occurred
  • April 20, 2023: Investigation initiated
</summary_1>

<summary_2>
Domain: Legal/Law Enforcement

- Core events:
  • April 16, 2023: Use of force incident reported
  • April 20, 2023: Internal Affairs began investigation
</summary_2>

<correct_output>
Combined Summary:

Domain: Legal/Law Enforcement

- Core events:
  • April 15-16, 2023: Use of force incident occurred (date discrepancy noted between sources)
  • April 20, 2023: Internal Affairs investigation initiated
</correct_output>

<explanation>Noted discrepancy in incident date without clear resolution context. Merged investigation start date with more specific detail from Summary 2.</explanation>
</example_4>

<example_5>
<summary_1>
Domain: Technical/IT Operations

- Incident details:
  • November 3, 2024, 14:23 UTC: Primary database server became unresponsive
  • 14:25 UTC: Automated failover to secondary server
  • Total downtime: 12 minutes

- Root cause:
  • Disk I/O saturation
</summary_1>

<summary_2>
Domain: Technical/IT Operations

- Root cause analysis:
  • Unoptimized query from newly deployed analytics module
  • Query executing full table scan on 500M row table

- Remediation:
  • Immediate: Analytics module rolled back
  • Long-term: Mandatory query performance testing added to CI/CD pipeline
</summary_2>

<correct_output>
Combined Summary:

Domain: Technical/IT Operations

- Incident timeline:
  • November 3, 2024, 14:23 UTC: Primary database server became unresponsive
  • 14:25 UTC: Automated failover to secondary server
  • Total downtime: 12 minutes

- Root cause analysis:
  • Disk I/O saturation caused by unoptimized query from newly deployed analytics module
  • Query executing full table scan on 500M row transactions table

- Remediation actions:
  • Immediate: Analytics module rolled back
  • Long-term: Mandatory query performance testing added to CI/CD pipeline
</correct_output>

<explanation>Combined incident details with complete root cause information. Organized chronologically: timeline → root cause → remediation. Merged disk I/O detail from Summary 1 with specific query details from Summary 2.</explanation>
</example_5>

<example_6>
<summary_1>
Domain: Business/Audit

- Key findings:
  • Three control deficiencies identified in procurement
  • 12 instances of unauthorized approvals (April-June 2024)
  • 8 vendors with incomplete due diligence
</summary_1>

<summary_2>

</summary_2>

<correct_output>
Combined Summary:

Domain: Business/Audit

- Key findings:
  • Three control deficiencies identified in procurement process
  • 12 instances of unauthorized approvals (April-June 2024)
  • 8 vendors with incomplete due diligence documentation
</correct_output>

<explanation>Summary 2 is empty. Restructured Summary 1 with minor improvements to clarity and completeness.</explanation>
</example_6>

<example_7>
<summary_1>

</summary_1>

<summary_2>

</summary_2>

<correct_output>

</correct_output>

<explanation>Both summaries empty - return empty string.</explanation>
</example_7>

<example_8>
<summary_1>
Domain: Legal/Law Enforcement

- Key events:
  • August 1, 2023: Officer interviewed
  • August 5, 2023: John Doe witness interviewed

- Key entities:
  • Officer under investigation
</summary_1>

<summary_2>
Domain: Legal/Law Enforcement

- Key events:
  • August 1, 2023: Officer Johnson interviewed by Internal Affairs
  • August 5, 2023: Civilian witness provided testimony

- Key entities:
  • Officer Johnson (subject of investigation)
  • Detective Martinez (lead investigator)
</summary_2>

<correct_output>
Combined Summary:

Domain: Legal/Law Enforcement

- Key events:
  • August 1, 2023: Officer Johnson interviewed by Internal Affairs
  • August 5, 2023: Civilian witness provided testimony

- Key entities:
  • Officer Johnson (subject of investigation)
  • Detective Martinez (lead investigator)
</correct_output>

<explanation>Used more specific details from Summary 2 throughout. Dropped "John Doe" placeholder from Summary 1, kept "civilian witness" description from Summary 2. Merged entity information favoring more complete details.</explanation>
</example_8>

<example_9>
<summary_1>
Domain: Administrative

- Administrative activities:
  • File transferred on October 5, 2023
  • Document copied on October 8, 2023
  • Routine audit on October 12, 2023
</summary_1>

<summary_2>
Domain: Legal/Investigation

- Investigation milestones:
  • October 12, 2023: Forensic analysis of evidence completed
  • October 15, 2023: Expert testimony reviewed
</summary_2>

<correct_output>
Combined Summary:

Domain: Legal/Investigation

- Investigation milestones:
  • October 12, 2023: Forensic analysis of evidence completed
  • October 15, 2023: Expert testimony reviewed
</correct_output>

<explanation>Summary 1 contains only routine administrative details - excluded per selectivity rule. Retained substantive investigation information from Summary 2. Used Summary 2's domain classification as it reflects substantive content.</explanation>
</example_9>

<example_10>
<summary_1>
Domain: Medical/Healthcare

- Patient presentation:
  • Severe abdominal pain
  • Nausea and vomiting for 24 hours

- Initial assessment:
  • Blood pressure: 140/90
  • Temperature: 101.2°F
</summary_1>

<summary_2>
Domain: Medical/Healthcare

- Diagnostic findings:
  • CT scan revealed acute appendicitis
  • Elevated white blood cell count: 15,000/μL

- Treatment:
  • Emergency appendectomy performed
  • Patient recovered without complications
</summary_2>

<correct_output>
Combined Summary:

Domain: Medical/Healthcare

- Patient presentation and initial assessment:
  • Severe abdominal pain with nausea and vomiting for 24 hours
  • Blood pressure: 140/90 mmHg
  • Temperature: 101.2°F

- Diagnostic findings:
  • CT scan revealed acute appendicitis
  • Elevated white blood cell count: 15,000/μL (normal: 4,000-11,000/μL)

- Treatment and outcome:
  • Emergency appendectomy performed
  • Patient recovered without complications
</correct_output>

<explanation>Merged complementary information into logical clinical narrative flow: presentation → diagnostics → treatment → outcome. Combined related categories and added standard reference ranges for lab values.</explanation>
</example_10>

</few_shot_examples>

<reference_materials>
Summary 1:
{{summary_1}}

Summary 2:
{{summary_2}}
</reference_materials>

<output_instruction>
Merge the two summaries into a single comprehensive summary. Always begin your output with "Combined Summary:":
</output_instruction>
"""
combine_verification_template = """
You are verifying a combined summary against its two source summaries.

<task_description>
Verify that the combined summary:
1. Contains only information from the source summaries (no hallucinations)
2. Has no duplicate or redundant information
3. Is organized logically and coherently
4. Properly handled contradictions (kept correct version or noted discrepancies)
5. Excludes routine administrative details
6. Uses appropriate domain classification and categories
7. Begins with "Combined Summary:"

Return the original if correct, or a corrected version.
</task_description>

<critical_rules>
- Every piece of information must appear in at least one source summary
- No duplicate or redundant entries
- Must be logically organized based on document domain
- Contradictions: if context was clear, correct version kept; if unclear, discrepancy noted or both dropped
- Exclude "John Doe," "Jane Doe," and other placeholder names
- Use "unidentified person" or note unavailable details for unclear identities
- Exclude routine administrative details unless substantively significant
- Must begin with "Combined Summary:"
- If both source summaries are empty, return empty string ("")
- Return ONLY the summary - no commentary or explanations
</critical_rules>

<output_format>
Return one of:
1. The combined summary exactly as written (if completely accurate)
2. A corrected summary:

Combined Summary:

Domain: [Identified domain]

- [Relevant Category]
  • Verified detail from sources
  • Verified detail from sources

3. Empty string "" (if both sources are empty)
</output_format>

<few_shot_examples>

<example_1>
<summary_1>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: Police officer stopped vehicle
  • January 26, 2014, 7:37 a.m.: Officer fired weapon
</summary_1>

<summary_2>
Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 7:37 a.m.: Officer Butera fired at suspect

- Key entities:
  • Officer Butera
  • Suspect in vehicle
</summary_2>

<combined_summary>
Combined Summary:

Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: Police officer stopped vehicle
  • January 26, 2014, 7:37 a.m.: Officer Butera fired at suspect

- Key entities:
  • Officer Butera
  • Suspect in vehicle
</combined_summary>

<correct_output>
Combined Summary:

Domain: Legal/Law Enforcement

- Core events and temporal information:
  • January 26, 2014, 6:56 a.m.: Police officer stopped vehicle
  • January 26, 2014, 7:37 a.m.: Officer Butera fired at suspect

- Key entities:
  • Officer Butera
  • Suspect in vehicle
</correct_output>

<explanation>Combined summary is accurate - all information verified, properly organized, no duplicates</explanation>
</example_1>

<example_2>
<summary_1>
Domain: Medical/Healthcare

- Patient presentation:
  • Severe chest pain
  • Shortness of breath

- Diagnostic findings:
  • EKG abnormal
  • Troponin elevated
</summary_1>

<summary_2>
Domain: Medical/Healthcare

- Diagnosis:
  • Acute myocardial infarction

- Treatment:
  • Emergency cardiac catheterization performed
  • Stent placed successfully
</summary_2>

<combined_summary>
Combined Summary:

Domain: Medical/Healthcare

- Patient presentation:
  • Severe chest pain
  • Shortness of breath

- Diagnostic findings and diagnosis:
  • EKG abnormal
  • Troponin elevated
  • Diagnosis: Acute myocardial infarction

- Treatment and outcome:
  • Emergency cardiac catheterization performed
  • Stent placed successfully
  • Patient stable and transferred to ICU
</combined_summary>

<correct_output>
Combined Summary:

Domain: Medical/Healthcare

- Patient presentation:
  • Severe chest pain
  • Shortness of breath

- Diagnostic findings and diagnosis:
  • EKG abnormal
  • Troponin elevated
  • Diagnosis: Acute myocardial infarction

- Treatment and outcome:
  • Emergency cardiac catheterization performed
  • Stent placed successfully
</correct_output>

<explanation>Patient transfer to ICU not in either source summary - remove it. Otherwise accurate.</explanation>
</example_2>

<example_3>
<summary_1>
Domain: Business/Financial

- Key metrics:
  • Q3 revenue: $4.2M
  • Customer churn: 3.2%
</summary_1>

<summary_2>
Domain: Business/Financial

- Key metrics:
  • Q3 revenue: $4.5M
  • Enterprise segment: $2.8M
</summary_2>

<combined_summary>
Combined Summary:

Domain: Business/Financial

- Key quantitative data:
  • Q3 revenue: $4.2M
  • Q3 revenue: $4.5M
  • Customer churn: 3.2%
  • Enterprise segment: $2.8M
</combined_summary>

<correct_output>
Combined Summary:

Domain: Business/Financial

- Key quantitative data:
  • Q3 revenue: $4.2M vs $4.5M (discrepancy between sources)
  • Customer churn: 3.2%
  • Enterprise segment: $2.8M
</correct_output>

<explanation>Contradictory revenue figures with no context to resolve - note discrepancy. Remove duplicate entries.</explanation>
</example_3>

<example_4>
<summary_1>
Domain: Technical/IT Operations

- Incident timeline:
  • November 3, 2024, 14:23 UTC: Database server unresponsive
  • 14:25 UTC: Failover to backup server

- Root cause:
  • Disk I/O saturation
</summary_1>

<summary_2>
Domain: Technical/IT Operations

- Root cause analysis:
  • Unoptimized query from analytics module
  • Full table scan on 500M row table

- Remediation:
  • Analytics module rolled back
  • Query performance testing added to pipeline
</summary_2>

<combined_summary>
Domain: Technical/IT Operations

- Incident timeline:
  • November 3, 2024, 14:23 UTC: Database server unresponsive
  • 14:25 UTC: Failover to backup server

- Root cause analysis:
  • Disk I/O saturation caused by unoptimized query from analytics module
  • Full table scan on 500M row table

- Remediation:
  • Analytics module rolled back
  • Query performance testing added to pipeline
</combined_summary>

<correct_output>
Combined Summary:

Domain: Technical/IT Operations

- Incident timeline:
  • November 3, 2024, 14:23 UTC: Database server unresponsive
  • 14:25 UTC: Failover to backup server

- Root cause analysis:
  • Disk I/O saturation caused by unoptimized query from analytics module
  • Full table scan on 500M row table

- Remediation:
  • Analytics module rolled back
  • Query performance testing added to pipeline
</correct_output>

<explanation>Missing "Combined Summary:" header - add it. Otherwise accurate.</explanation>
</example_4>

<example_5>
<summary_1>
Domain: Legal/Law Enforcement

- Core events:
  • May 10, 2023: Incident occurred
  • May 15, 2023: Complaint filed by John Doe

- Key entities:
  • Officer Martinez
  • John Doe (complainant)
</summary_1>

<summary_2>
Domain: Legal/Law Enforcement

- Core events:
  • May 10, 2023: Use of force incident
  • May 15, 2023: Civilian complaint filed

- Investigation findings:
  • Policy violation confirmed
</summary_2>

<combined_summary>
Combined Summary:

Domain: Legal/Law Enforcement

- Core events:
  • May 10, 2023: Use of force incident occurred
  • May 15, 2023: Complaint filed by John Doe

- Key entities:
  • Officer Martinez
  • John Doe (complainant)

- Investigation findings:
  • Policy violation confirmed
</combined_summary>

<correct_output>
Combined Summary:

Domain: Legal/Law Enforcement

- Core events:
  • May 10, 2023: Use of force incident occurred
  • May 15, 2023: Civilian complaint filed

- Key entities:
  • Officer Martinez
  • Complainant (identity unavailable)

- Investigation findings:
  • Policy violation confirmed
</correct_output>

<explanation>Remove "John Doe" placeholder name references. Use "civilian complaint" from Summary 2 and note identity unavailable.</explanation>
</example_5>

<example_6>
<summary_1>
Domain: Administrative

- Administrative activities:
  • File transferred on June 5, 2023
  • Document copied on June 8, 2023
</summary_1>

<summary_2>
Domain: Legal/Investigation

- Investigation milestones:
  • June 10, 2023: Forensic analysis completed
  • June 15, 2023: Final report issued
</summary_2>

<combined_summary>
Combined Summary:

Domain: Legal/Investigation

- Administrative activities:
  • File transferred on June 5, 2023
  • Document copied on June 8, 2023

- Investigation milestones:
  • June 10, 2023: Forensic analysis completed
  • June 15, 2023: Final report issued
</combined_summary>

<correct_output>
Combined Summary:

Domain: Legal/Investigation

- Investigation milestones:
  • June 10, 2023: Forensic analysis completed
  • June 15, 2023: Final report issued
</correct_output>

<explanation>Routine administrative activities from Summary 1 excluded per selectivity rule. Use Summary 2's domain as it reflects substantive content.</explanation>
</example_6>

<example_7>
<summary_1>
Domain: Business/Audit

- Key findings:
  • Three control deficiencies identified
  • 12 unauthorized approvals in Q2
</summary_1>

<summary_2>

</summary_2>

<combined_summary>
Combined Summary:

Domain: Business/Audit

- Key findings:
  • Three control deficiencies identified in procurement
  • 12 unauthorized approvals in Q2 2024
</combined_summary>

<correct_output>
Combined Summary:

Domain: Business/Audit

- Key findings:
  • Three control deficiencies identified
  • 12 unauthorized approvals in Q2
</correct_output>

<explanation>Added details ("in procurement", "2024") not present in either source - remove them. Use only verified information.</explanation>
</example_7>

<example_8>
<summary_1>

</summary_1>

<summary_2>

</summary_2>

<combined_summary>
Combined Summary:

Domain: No specific domain detected

- No substantive information
</combined_summary>

<correct_output>

</correct_output>

<explanation>Both sources empty - return empty string, not a summary stating "no information"</explanation>
</example_8>

<example_9>
<summary_1>
Domain: Medical/Healthcare

- Clinical findings:
  • Blood pressure: 140/90
  • Temperature: 101.2°F

- Diagnosis:
  • Acute appendicitis
</summary_1>

<summary_2>
Domain: Medical/Healthcare

- Treatment:
  • Emergency appendectomy performed

- Outcome:
  • Patient recovered without complications
</summary_2>

<combined_summary>
Combined Summary:

Domain: Medical/Healthcare

- Clinical findings:
  • Blood pressure: 140/90
  • Temperature: 101.2°F
  • Blood pressure: 140/90

- Diagnosis and treatment:
  • Acute appendicitis
  • Emergency appendectomy performed

- Outcome:
  • Patient recovered without complications
</combined_summary>

<correct_output>
Combined Summary:

Domain: Medical/Healthcare

- Clinical findings:
  • Blood pressure: 140/90 mmHg
  • Temperature: 101.2°F

- Diagnosis and treatment:
  • Acute appendicitis
  • Emergency appendectomy performed

- Outcome:
  • Patient recovered without complications
</correct_output>

<explanation>Blood pressure listed twice - remove duplicate. Otherwise well-organized and accurate.</explanation>
</example_9>

<example_10>
<summary_1>
Domain: Legal/Law Enforcement

- Investigation timeline:
  • August 1, 2023: Investigation began
  • August 15, 2023: Investigation completed

- Findings:
  • Officer violated use of force policy
</summary_1>

<summary_2>
Domain: Legal/Law Enforcement

- Investigation timeline:
  • August 1, 2023: Internal Affairs investigation initiated
  • August 10, 2023: Witness interviews conducted
  • August 15, 2023: Final report submitted

- Outcomes:
  • 30-day suspension recommended
</summary_2>

<combined_summary>
Combined Summary:

Domain: Legal/Law Enforcement

- Investigation timeline:
  • August 1, 2023: Internal Affairs investigation initiated
  • August 10, 2023: Witness interviews conducted
  • August 15, 2023: Investigation completed, final report submitted

- Findings and outcomes:
  • Officer violated use of force policy
  • 30-day suspension recommended
</combined_summary>

<correct_output>
Combined Summary:

Domain: Legal/Law Enforcement

- Investigation timeline:
  • August 1, 2023: Internal Affairs investigation initiated
  • August 10, 2023: Witness interviews conducted
  • August 15, 2023: Investigation completed, final report submitted

- Findings and outcomes:
  • Officer violated use of force policy
  • 30-day suspension recommended
</correct_output>

<explanation>Combined summary is accurate - properly merged complementary information, organized logically, no hallucinations</explanation>
</example_10>

</few_shot_examples>

<reference_materials>
Summary 1:
{{summary_1}}

Summary 2:
{{summary_2}}

Current Combined Summary:
{{current_combined_summary}}
</reference_materials>

<output_instruction>
Verify the combined summary against the source summaries. Return your output below:
</output_instruction>
"""
condense_interval_template = """
<task_description>
You are reviewing a comprehensive interval summary that may contain numerous details across multiple categories. Your task is to extract and present only the most critical information while maintaining domain-appropriate organization.
</task_description>

<document_classification>
First, identify the document's domain based on the interval summary content:
- Legal/law enforcement
- Medical/healthcare
- Business/financial
- Technical/IT
- Administrative
- Academic
- Scientific
- Other domain or no specific domain

The domain will guide which types of information to prioritize.
</document_classification>

<critical_requirements>
1. Return EXACTLY 18 bulletpoints total, organized into 3 categories
2. Each category must contain EXACTLY 6 bulletpoints (unless fewer exist in source)
3. Categories should be domain-appropriate based on document classification
4. Every bulletpoint must come from the source interval summary
5. Format must follow the exact structure specified in <output_format>
</critical_requirements>

<selection_criteria>
Prioritize information that includes:
- Specific identifying details (names, numbers, identifiers, titles, roles)
- Precise temporal information (dates, times, durations, sequences)
- Specific locations, systems, or entities
- Key determinations, findings, or conclusions
- Critical events, incidents, or actions
- Important quantitative data or measurements
- Significant outcomes or results
- Causal relationships or root causes
- Material risks, issues, or violations

Deprioritize:
- Vague or general statements without specifics
- Redundant information already captured elsewhere
- Minor procedural or administrative details
- Background information without direct relevance
- Routine or standard operations
</selection_criteria>

<category_selection_guidance>
Choose 3 categories that best organize the most important information from the interval summary. Categories should be:
1. Domain-appropriate (reflecting the type of document)
2. Substantive (capturing the core subject matter)
3. Comprehensive (covering different aspects of the content)

Example category sets by domain:

Legal/Law Enforcement:
- Allegations, Charges, and Legal Issues
- Key Events, Incidents, and Timeline
- Findings, Decisions, and Outcomes

Medical/Healthcare:
- Clinical Presentation and Assessment
- Diagnostic Findings and Test Results
- Treatment, Interventions, and Outcomes

Business/Financial:
- Performance Metrics and Financial Data
- Key Activities and Operational Events
- Findings, Decisions, and Strategic Actions

Technical/IT:
- Incident Details and Timeline
- Root Cause and Technical Analysis
- Remediation and Preventive Actions

Project/Administrative:
- Key Milestones and Deliverables
- Issues, Risks, and Challenges
- Decisions, Actions, and Next Steps

Scientific/Research:
- Methodology and Experimental Design
- Results and Observations
- Analysis, Conclusions, and Implications

Adapt these examples as needed based on the actual content of the interval summary.
</category_selection_guidance>

<thinking_process>
Before selecting bulletpoints:
1. What domain does this interval summary belong to?
2. What are the 3 most important aspects or themes in this summary?
3. Which categories best organize these themes for this specific domain?
4. Which specific details (names, dates, numbers, findings) are most critical?
5. Am I avoiding redundancy across the 18 selected bulletpoints?
6. Do these 18 bulletpoints capture the essential narrative or key information?
</thinking_process>

<full_interval_summary>
{{full_interval_summary}}
</full_interval_summary>

<output_format>
Return the condensed summary in this EXACT format with domain-appropriate category labels:

- [Category 1 - Domain Appropriate Label]
  • [Most important bulletpoint 1]
  • [Most important bulletpoint 2]
  • [Most important bulletpoint 3]
  • [Most important bulletpoint 4]
  • [Most important bulletpoint 5]
  • [Most important bulletpoint 6]
  • END BULLETPOINTS

- [Category 2 - Domain Appropriate Label]
  • [Most important bulletpoint 1]
  • [Most important bulletpoint 2]
  • [Most important bulletpoint 3]
  • [Most important bulletpoint 4]
  • [Most important bulletpoint 5]
  • [Most important bulletpoint 6]
  • END BULLETPOINTS

- [Category 3 - Domain Appropriate Label]
  • [Most important bulletpoint 1]
  • [Most important bulletpoint 2]
  • [Most important bulletpoint 3]
  • [Most important bulletpoint 4]
  • [Most important bulletpoint 5]
  • [Most important bulletpoint 6]
  • END BULLETPOINTS

CRITICAL: 
- Each category must have exactly 6 bulletpoints
- Must include "• END BULLETPOINTS" after each category
- Total of exactly 18 bulletpoints across all 3 categories
- Category labels must be appropriate to the document domain
- All bulletpoints must come from the source interval summary
</output_format>

<warnings>
- Do not create new information not present in the interval summary
- Do not combine bulletpoints in ways that distort their original meaning
- Do not use placeholder names like "John Doe" or "Jane Doe"
- Maintain the specificity and precision of the original bulletpoints
- Each bulletpoint should be substantive and information-dense
</warnings>

<output_instruction>
Identify the document domain, select the 3 most appropriate categories, and extract the 18 most important bulletpoints now:
</output_instruction>
"""


######### legacy prompts that are currently not used ############


# condense_template = """
# <task_description>
# As a Legal Clerk, your task is to condense the summaries into a single summary.
# </task_description>

# <essential_information>
# Ensure the condensed summary includes ALL of the following elements (if present in the summary). First and foremost, your objective is to return a comprehensive summary that will provide the user with a thorough understanding of the contents of the summaries that you are condensing. 

# Some essential information that will contribute to a comprehensive summary include but are not limited to:
# b. Primary parties involved (full names, roles, badge numbers if applicable)
# j. Allegations of misconduct and any associated information
# c. Key legal issues, claims, charges, or arguments
# k. Disciplinary outcomes or their current status
# d. Critical events or incidents (with specific dates, times and locations)
# e. Main findings or decisions
# f. Significant evidence or testimonies
# g. Important outcomes or rulings
# h. Current status of the matter
# i. Any pending actions or future proceedings
# l. Procedural events (e.g., filing of charges, hearings, notifications, motions, investigations, agreements, service of documents, compliance with legal requirements) 
# For each type of essential information classification, be specific when referring to people, places, and dates. 
# </essential_information>

# <thinking_process>
# Before condensing the summary, consider:
# 1. What are the most critical pieces of information that must be retained?
# 2. How can I organize the information to present a clear summary?
# 4. How can I ensure that the condensed summary remains coherent and comprehensive?
# 5. Are there any redundancies in the merged summary that can be eliminated?
# </thinking_process>

# <critical_instructions>
# 1. NEVER include any information about "John Doe," "Jane Doe," or other anonymous/ambiguous entities (e.g., "ABC Corporation," "Company X," "Individual A") in your summary. If specific identifying information is not available in the document, acknowledge this limitation by stating that details are unavailable or redacted, rather than including placeholder names or making assumptions about identities.
# 2. If there is no relevant content to summarize in the Current Page, return an empty string ("").
# 3. DO NOT infer, assume, or hallucinate any information not explicitly stated in the provided text.
# 4. Treat this task as a binary classification: either there is relevant information to summarize, or there isn't.
# </critical_instructions>

# <warnings>
# - Do not introduce new information not present in the merged summary
# - Avoid altering the meaning or context of any information during the condensing process
# - Do not omit any essential details, even if struggling to meet the 5-paragraph limit
# - Ensure that all information remains accurately attributed to the correct parties and events
# - Be cautious of potential inconsistencies and address them appropriately
# - Do not include speculative or inferential information
# </warnings>

# <reference_materials>
# ## Input Summary ##
# {{summaries}}
# </reference_materials>

# <output_instruction>
# Provide the condensed summary below, ensuring that all essential information from the merged summary is retained, accurately presented, and organized in a clear, chronological, and logical manner. The condensed summary should not exceed 5 paragraphs:
# </output_instruction>
# """

final_combine_template = """
<task_description>
Your task is to combine the provided summaries into a single, comprehensive, and well-organized final summary for the given document. Your primary goal is to preserve ALL important information from both summaries, creating a comprehensive summary without any omissions.
</task_description>

<document_classification>
First, identify the document's domain based on the classification provided in the summaries (e.g., legal, medical, financial, technical, administrative, academic, scientific, business, etc.).

Base your classification on:
- Domain stated in the summaries
- Nature of the content and terminology
- Structure and subject matter

If summaries have different domain classifications, determine which is most appropriate based on the substantive content, or use a combined classification if the document spans multiple domains.

State the identified domain before proceeding with the combination.
</document_classification>

<guidelines>
1. Comprehensive Information Integration:
   • Include ALL important information from both summaries, even if it results in a longer combined summary
   • Merge complementary information that describes the same events, findings, or entities
   • Preserve all specific details: names, dates, numbers, locations, measurements, identifiers

2. Organization and Structure:
   • Organize information using domain-appropriate categories
   • Group related information together logically
   • Use bullet points to capture all important details clearly
   • Maintain coherent narrative flow where applicable

3. Factual Accuracy:
   • Include only details explicitly stated in either summary
   • When merging information about the same subject, combine details without adding unstated information
   • If information is incomplete, unclear, or contradictory, preserve that ambiguity or note the discrepancy
   • Never fabricate or infer information not present in the source summaries

4. Handling Contradictions:
   • If summaries contain contradictory information with clear context indicating which is correct, use the correct version
   • If contradictions cannot be resolved, note the discrepancy explicitly
   • Do not simply choose one version without justification

5. Completeness Check:
   • After combining, review both original summaries to ensure no important information has been omitted
   • Verify that all key entities, events, findings, dates, and outcomes are captured
   • If any omissions are found, immediately add them to the combined summary
</guidelines>

<domain_specific_essential_information>
Based on the identified domain, ensure the summary includes ALL of the following elements that are present in the source summaries:

**For Legal/Law Enforcement Documents:**
- Primary parties involved (full names, roles, badge numbers, case numbers if applicable)
- Key legal issues, allegations, claims, charges, or violations
- Critical events or incidents (with specific dates, times, and locations)
- Investigation details and milestones
- Main findings, determinations, or decisions
- Significant evidence, testimonies, or documentation
- Important outcomes, rulings, or disciplinary actions
- Procedural events (filings, hearings, notifications, motions, service of documents)
- Current status and any pending actions or future proceedings

**For Medical/Healthcare Documents:**
- Patient presentation and chief complaints
- Vital signs, clinical findings, and physical examination results
- Diagnostic test results with specific values and reference ranges
- Diagnoses and clinical assessments
- Treatments, procedures, and interventions performed
- Medications administered with dosages
- Patient response and outcomes
- Discharge planning and follow-up recommendations
- Temporal progression of clinical events

**For Business/Financial Documents:**
- Key financial metrics, figures, and performance indicators
- Revenue, costs, profit margins, and growth rates
- Market data, trends, and comparative analysis
- Strategic decisions and business actions
- Operational changes or organizational developments
- Risk factors and challenges identified
- Forecasts, projections, or targets
- Recommendations and action items

**For Technical/IT Documents:**
- System, application, or infrastructure details
- Incident timeline with specific timestamps
- Error messages, logs, or diagnostic information
- Root cause analysis and technical findings
- Impact assessment (users affected, downtime, data loss)
- Remediation actions taken
- Preventive measures implemented
- Outstanding issues or future enhancements

**For Scientific/Research Documents:**
- Research objectives and hypotheses
- Methodology and experimental design
- Sample characteristics and parameters
- Data collection methods and instruments
- Results with specific measurements and statistical significance
- Analysis and interpretation
- Conclusions and implications
- Limitations and future research directions

**For Project/Administrative Documents:**
- Project scope, objectives, and deliverables
- Key milestones and deadlines
- Resources, budget, and timeline
- Stakeholders and responsible parties
- Progress status and completion percentages
- Issues, risks, and dependencies
- Decisions made and action items
- Next steps and future activities

**For General/Unclassified Documents:**
- Main topics and themes
- Key individuals, organizations, or entities mentioned
- Important dates, events, or milestones
- Significant data, facts, or findings
- Main arguments, conclusions, or recommendations
- Relevant context or background information
- Current status and future actions

Adapt these categories based on the actual domain identified. Use your domain knowledge to determine what constitutes "essential information" for the specific document type.
</domain_specific_essential_information>

<thinking_process>
Before and during the combination of summaries, consider:
1. What domain does this document belong to, and what information is most critical for this domain?
2. What are the main topics, events, or subjects covered across both summaries?
3. Are there any contradictions or inconsistencies between summaries? If so, can they be resolved with context?
4. What specific details (names, dates, numbers, locations) must be preserved?
5. How can I organize this information most logically for this domain?
6. Have I double-checked that no important information from either summary has been omitted?
7. Does the combined summary maintain the precision and specificity of the source summaries?
</thinking_process>

<critical_instructions>
1. NEVER include any information about "John Doe," "Jane Doe," or other placeholder entities (e.g., "ABC Corporation," "Company X," "Individual A"). If specific identifying information is not available, state that details are unavailable, redacted, or unidentified.

2. DO NOT infer, assume, or hallucinate any information not explicitly stated in the provided summaries.

3. If both summaries are empty or contain no substantive information, return an empty string ("").

4. Exclude routine administrative metadata (document headers, page numbers, signature blocks) unless substantively significant.

5. Every piece of information in the combined summary must be traceable to at least one source summary.

6. Prioritize completeness over brevity—include all important information even if the summary is lengthy.

7. Maintain the same level of specificity present in the source summaries—do not generalize or simplify detailed information.
</critical_instructions>

<output_format>
Present the combined summary using this structure:

## Combined Summary ##

**Domain:** [Identified domain]

**[Category 1 - Domain Appropriate]**
- [Detailed information point]
- [Detailed information point]

**[Category 2 - Domain Appropriate]**
- [Detailed information point]
- [Detailed information point]

**[Category 3 - Domain Appropriate]**
- [Detailed information point]
- [Detailed information point]

Use as many categories as needed to organize all information logically. Each category should group related information together.
</output_format>

<warnings>
- Prioritize completeness—include all important information rather than omitting details for brevity
- Do not include speculative information or draw conclusions not explicitly stated in the summaries
- Do not alter the meaning or context of any information when integrating it
- Do not combine information in ways that create new claims not present in the sources
- Verify that all specific details (names, dates, numbers, locations) are accurately preserved
</warnings>

<reference_materials>
Summary 1:
{{summary_1}}

Summary 2:
{{summary_2}}
</reference_materials>

<output_instruction>
Identify the document domain, then generate the comprehensive combined summary below, ensuring it adheres to all guidelines and includes all essential information based on the document type:
</output_instruction>
"""

final_verification_template = """
<task_description>
Your task is to meticulously review the combined summary, which integrates content from two individual summaries (Summary 1 and Summary 2) of a document. This verification process aims to ensure that ALL relevant information from both original summaries is accurately contained within the combined summary, including key details, entities, events, findings, data, and outcomes from both sources.
</task_description>

<document_classification>
First, confirm the document's domain based on the classification provided in the combined summary (e.g., legal, medical, financial, technical, administrative, academic, scientific, business, etc.).

State the identified domain before proceeding with the verification.
</document_classification>

<verification_guidelines>
1. Systematic Comparison:
   • Create a mental checklist of all important points from both original summaries
   • Systematically check each point against the combined summary, identifying items as present, missing, or inaccurately represented
   • Pay special attention to specific details: names, dates, numbers, locations, measurements, identifiers

2. Information Preservation:
   • Ensure that ALL important details from both summaries are accurately incorporated into the combined summary
   • Verify that merged information maintains the precision and specificity of the source summaries
   • Check that no information has been generalized, simplified, or lost in the combination process

3. Accuracy Verification:
   • Confirm that information has not been distorted or misrepresented during combination
   • Verify that contradictions were handled appropriately (resolved with context or noted as discrepancies)
   • Check that no new information was added that doesn't exist in either source summary

4. Missing Information Addition:
   • For any information found missing during the review, explicitly add it to the verified summary
   • Tag additions with [ADDED] to indicate they were missing from the combined summary
   • Ensure additions maintain the same level of detail present in the original summaries

5. Error Correction:
   • Correct any inaccuracies, distortions, or misrepresentations
   • Tag corrections with [CORRECTED] to indicate they were inaccurate in the combined summary
   • Ensure corrected information matches the source summaries exactly
</verification_guidelines>

<domain_specific_essential_information>
Based on the identified domain, ensure the summary includes ALL of the following elements that are present in the source summaries:

**For Legal/Law Enforcement Documents:**
- Primary parties involved (full names, roles, badge numbers, case numbers if applicable)
- Key legal issues, allegations, claims, charges, or violations
- Critical events or incidents (with specific dates, times, and locations)
- Investigation details and milestones
- Main findings, determinations, or decisions
- Significant evidence, testimonies, or documentation
- Important outcomes, rulings, or disciplinary actions
- Procedural events (filings, hearings, notifications, motions, service of documents)
- Current status and any pending actions or future proceedings

**For Medical/Healthcare Documents:**
- Patient presentation and chief complaints
- Vital signs, clinical findings, and physical examination results
- Diagnostic test results with specific values and reference ranges
- Diagnoses and clinical assessments
- Treatments, procedures, and interventions performed
- Medications administered with dosages
- Patient response and outcomes
- Discharge planning and follow-up recommendations
- Temporal progression of clinical events

**For Business/Financial Documents:**
- Key financial metrics, figures, and performance indicators
- Revenue, costs, profit margins, and growth rates
- Market data, trends, and comparative analysis
- Strategic decisions and business actions
- Operational changes or organizational developments
- Risk factors and challenges identified
- Forecasts, projections, or targets
- Recommendations and action items

**For Technical/IT Documents:**
- System, application, or infrastructure details
- Incident timeline with specific timestamps
- Error messages, logs, or diagnostic information
- Root cause analysis and technical findings
- Impact assessment (users affected, downtime, data loss)
- Remediation actions taken
- Preventive measures implemented
- Outstanding issues or future enhancements

**For Scientific/Research Documents:**
- Research objectives and hypotheses
- Methodology and experimental design
- Sample characteristics and parameters
- Data collection methods and instruments
- Results with specific measurements and statistical significance
- Analysis and interpretation
- Conclusions and implications
- Limitations and future research directions

**For Project/Administrative Documents:**
- Project scope, objectives, and deliverables
- Key milestones and deadlines
- Resources, budget, and timeline
- Stakeholders and responsible parties
- Progress status and completion percentages
- Issues, risks, and dependencies
- Decisions made and action items
- Next steps and future activities

**For General/Unclassified Documents:**
- Main topics and themes
- Key individuals, organizations, or entities mentioned
- Important dates, events, or milestones
- Significant data, facts, or findings
- Main arguments, conclusions, or recommendations
- Relevant context or background information
- Current status and future actions

Apply domain knowledge to determine what constitutes "essential information" for the specific document type.
</domain_specific_essential_information>

<thinking_process>
During the verification process, consider:
1. What domain is this document, and what information is most critical for this domain?
2. Have I identified all important points from both original summaries?
3. Am I systematically comparing each point to ensure nothing is missed or misrepresented?
4. Are all specific details (names, dates, numbers, locations, measurements) accurately preserved?
5. Were contradictions handled appropriately in the combined summary?
6. Has any information been generalized, simplified, or distorted during combination?
7. After my initial review, did I re-read the original summaries to catch any overlooked details?
8. If I found any missing or inaccurate information, have I corrected it in the verified summary?
9. Does the verified summary maintain the same level of precision as the source summaries?
</thinking_process>

<critical_instructions>
1. NEVER include any information about "John Doe," "Jane Doe," or other placeholder entities (e.g., "ABC Corporation," "Company X," "Individual A"). If specific identifying information is not available, state that details are unavailable, redacted, or unidentified.

2. DO NOT infer, assume, or hallucinate any information not explicitly stated in the provided summaries.

3. If the combined summary is empty and both source summaries are also empty, return an empty string ("").

4. Every piece of information in the verified summary must be traceable to at least one source summary.

5. Tag all changes:
   - [UNCHANGED] for information correctly included in combined summary
   - [ADDED] for information missing from combined summary but present in source summaries
   - [CORRECTED] for information inaccurately represented in combined summary

6. Maintain the same level of specificity present in the source summaries—do not generalize detailed information.

7. If significant information is missing or the combined summary has substantial errors, add all missing information and correct all errors.
</critical_instructions>

<warnings>
- Prioritize completeness and accuracy over conciseness
- Do not alter the meaning or context of any information during verification
- Ensure that all ambiguities or uncertainties from the original summaries are maintained
- Do not add speculative information or draw conclusions not present in the original summaries
- Verify that merged information doesn't create new claims not present in the sources
- Check that all quantitative data (numbers, percentages, measurements) is accurate
</warnings>

<reference_materials>
Current Combined Summary:
{{current_combined_summary}}

Summary 1:
{{summary_1}}

Summary 2:
{{summary_2}}
</reference_materials>

<output_format>
Provide the verified summary below. If no changes are needed, return the combined summary with all items tagged as [UNCHANGED]. If changes are needed, tag additions as [ADDED] and corrections as [CORRECTED]. Do not include any reference to your verification process or explanations in the final output—only the verified summary with tags.

## Verified Summary ##

**Domain:** [Identified domain]

**[Category 1 - Domain Appropriate]**
- [UNCHANGED] Information point correctly included
- [UNCHANGED] Information point correctly included
- [ADDED] Information point missing from combined summary
- [CORRECTED] Information point inaccurately represented

**[Category 2 - Domain Appropriate]**
- [UNCHANGED] Information point correctly included
- [UNCHANGED] Information point correctly included
- [UNCHANGED] Information point correctly included

**[Category 3 - Domain Appropriate]**
- [UNCHANGED] Information point correctly included
- [ADDED] Information point missing from combined summary
- [UNCHANGED] Information point correctly included

Use as many categories as needed to organize all information logically and completely.
</output_format>

<output_instruction>
Confirm the document domain, then generate the verified summary below, ensuring it includes ALL information from both source summaries with appropriate tags:
</output_instruction>
"""

improve_summary_template = """
Your task is to enhance the existing summary of a document by incorporating important information from the memory log. The current summary contains specific details, while the memory log provides high-level, important information accumulated from the entire document.
Your goal is to improve the summary by adding only the most important missing information from the memory log without removing any existing content.

<task_description>
Guidelines:
1. Carefully review both the current summary and the memory log
2. Identify the domain of the document based on the summary classification
3. Identify the most important information in the memory log that is not present in the current summary
4. Add the missing important information to the appropriate sections of the summary
5. Preserve all existing content in the current summary
6. Ensure that added information enhances the summary's comprehensiveness and relevance
7. Maintain the original structure and flow of the summary as much as possible
8. If no significant additions are needed, return the original summary with all items tagged as [UNCHANGED]
</task_description>

<document_classification>
First, identify the document's domain based on the current summary (e.g., legal, medical, financial, technical, administrative, academic, scientific, business, etc.).

The domain will guide what types of information to prioritize from the memory log.
</document_classification>

<domain_specific_essential_information>
When reviewing the memory log, pay special attention to domain-relevant elements that are not already in the summary:

**For Legal/Law Enforcement Documents:**
- Primary parties involved (full names, roles, badge numbers, case numbers if applicable)
- Key legal issues, allegations, claims, charges, or violations not mentioned in the summary
- Critical events or incidents (with specific dates, times, and locations) missing from the summary
- Main findings, determinations, or decisions not covered
- Significant evidence, testimonies, or documentation not included
- Important outcomes, rulings, or disciplinary actions not mentioned
- Procedural events (filings, hearings, notifications, motions, investigations, service of documents)
- Updates to current status or pending actions not included

**For Medical/Healthcare Documents:**
- Patient identifiers or demographics not in summary (when appropriate)
- Key symptoms, presentations, or complaints missing
- Critical vital signs, lab values, or diagnostic results not included
- Important diagnoses or assessments not mentioned
- Significant treatments, procedures, or medications not covered
- Outcomes, complications, or follow-up plans missing
- Temporal progression of clinical events not captured

**For Business/Financial Documents:**
- Key financial metrics or performance indicators missing
- Important strategic decisions or business actions not mentioned
- Significant operational changes or developments not included
- Critical risk factors or challenges not covered
- Important recommendations or action items missing
- Stakeholder information or organizational context not present

**For Technical/IT Documents:**
- System or infrastructure details missing
- Critical incident details or timeline gaps not covered
- Root cause information not mentioned
- Impact assessment details missing
- Remediation or preventive measures not included
- Outstanding issues or future actions not covered

**For Scientific/Research Documents:**
- Research objectives or hypotheses not stated
- Methodology details missing
- Key results or findings not included
- Statistical significance or measurements not mentioned
- Conclusions or implications missing
- Limitations not covered

**For Project/Administrative Documents:**
- Project scope or objectives missing
- Key milestones or deadlines not mentioned
- Stakeholder or resource information not included
- Issues, risks, or dependencies not covered
- Decisions or action items missing
- Status updates or next steps not present

**For General/Unclassified Documents:**
- Main topics or themes not adequately covered
- Key entities or individuals not mentioned
- Important dates or events missing
- Significant data or findings not included
- Main conclusions or recommendations not covered
- Relevant context or background missing

Apply domain knowledge to identify what information from the memory log would be most valuable to add.
</domain_specific_essential_information>

<thinking_process>
Before adding to the summary, consider:
1. What domain does this document belong to?
2. What important information is present in the memory log but missing from the current summary?
3. Is this information truly important, or is it redundant/administrative?
4. Where in the existing summary structure does this new information best fit?
5. How can I integrate this information smoothly without disrupting the existing flow?
6. Does this new information provide additional context or clarity to the existing summary?
7. Am I maintaining the same level of specificity and precision as the original summary?
8. Have I checked that I'm not adding placeholder names or unverified information?
</thinking_process>

<critical_instructions>
1. NEVER include any information about "John Doe," "Jane Doe," or other placeholder entities (e.g., "ABC Corporation," "Company X," "Individual A"). If specific identifying information is not available, state that details are unavailable, redacted, or unidentified.

2. DO NOT infer, assume, or hallucinate any information not explicitly stated in either the summary or memory log.

3. If the current summary is empty and the memory log is also empty, return an empty string ("").

4. Only add information that is:
   - Explicitly stated in the memory log
   - Not already present in the current summary (even in different wording)
   - Substantively important (not routine administrative details)
   - Appropriate for the document domain

5. Tag all items:
   - [UNCHANGED] for existing content from the current summary
   - [ADDED] for new information from the memory log
   - Never use [CORRECTED] in this task—do not modify existing summary content

6. Preserve the original summary's structure, categories, and organization unless additions require new categories.

7. Maintain the same level of detail and specificity present in the original summary.
</critical_instructions>

<warnings>
- Do not remove or modify any existing content from the current summary
- Do not add speculative information or inferences not stated in the memory log
- Do not generalize or simplify detailed information when adding it
- Ensure additions are well-integrated and maintain narrative flow
- Avoid redundancy—don't add information that's already captured in the summary (even if worded differently)
- Prioritize important, substantive additions over minor details
</warnings>

<output_format>
Present the enhanced summary using the existing structure of the current summary. Add new information from the memory log where appropriate, clearly marking all items with tags. For example:

## Enhanced Summary ##

**Domain:** [Identified domain]

**[Category 1 - From Original Summary]**
- [UNCHANGED] Existing information point
- [UNCHANGED] Existing information point
- [ADDED] New information from memory log
- [UNCHANGED] Existing information point

**[Category 2 - From Original Summary]**
- [UNCHANGED] Existing information point
- [UNCHANGED] Existing information point
- [UNCHANGED] Existing information point

**[New Category - If Needed for Memory Log Information]**
- [ADDED] New information from memory log
- [ADDED] New information from memory log

Maintain this format throughout, inserting new information where it fits best within the existing structure. If no additions are needed, return the original summary with all items tagged as [UNCHANGED].
</output_format>

<reference_documents>
Current Summary:
{{summary}}

Memory Log:
{{memory_log}}
</reference_documents>

<output_instruction>
Identify the document domain, then provide the enhanced summary below with all items appropriately tagged, or the original summary with [UNCHANGED] tags if no improvements are needed:
</output_instruction>
"""

organization_template = """
<task_description>
Your task is to reorganize the content from concatenated summaries into a single, concise descriptive paragraph that catalogs what the document contains. The summary should describe the type of document, its scope, and the categories of information it includes. Do not analyze, interpret, assess quality, or draw conclusions about the content - simply describe what is present in the document.
</task_description>

<document_classification>
First, identify the document's domain based on the concatenated summaries (e.g., legal, medical, financial, technical, administrative, academic, scientific, business, etc.).

The domain will guide what type of document this is and what categories of information are typically included.

State the identified domain before proceeding with reorganization.
</document_classification>

<domain_specific_priorities>

**For Legal/Law Enforcement Documents:**
Describe: document type, time period covered, types of incidents or cases included, data fields present (parties, allegations, case numbers, dates, outcomes, procedural information)

**For Medical/Healthcare Documents:**
Describe: document type, time period covered, types of records included, data fields present (patient information, diagnoses, treatments, test results, dates, providers)

**For Business/Financial Documents:**
Describe: document type, time period covered, types of data included, data fields present (financial metrics, transactions, accounts, dates, organizational units)

**For Technical/IT Documents:**
Describe: document type, time period covered, types of systems or incidents included, data fields present (system names, error codes, timestamps, users, configurations)

**For Scientific/Research Documents:**
Describe: document type, scope of study, types of data collected, data fields present (variables measured, sample information, methodologies, timeframes)

**For Project/Administrative Documents:**
Describe: document type, project scope, time period covered, types of information included, data fields present (tasks, milestones, assignments, dates, status indicators)

**For General/Unclassified Documents:**
Describe: document type, subject matter, time period covered, types of information included, data fields or categories present

Focus on cataloging what information categories are present in the document.
</domain_specific_priorities>

<essential_information>
The reorganized summary should catalog the following elements from the concatenated summaries:

- Document type and format (log, report, database, correspondence, etc.)
- Time period or date range covered
- Scope (what entities, locations, or subjects are included)
- Categories of data or information present
- Key data fields, columns, or information types included in entries
- Types of incidents, cases, transactions, or records documented

Do NOT include:
- Assessments of completeness, quality, or consistency
- Analysis of what the data shows or implies
- Interpretations of significance or purpose
- Conclusions about effectiveness or compliance
- Evaluative descriptions of how information is organized

Simply describe what types of information the document contains.
</essential_information>

<descriptive_approach>
When writing the description:
1. Start by identifying what type of document this is
2. State the time period or scope covered
3. List the main categories of information included
4. Describe the key data fields or information types present in entries
5. Note any major information categories without assessing their quality or completeness
6. Use neutral descriptive language that catalogs content

Keep the focus on "what is in the document" rather than "what the document accomplishes" or "how well organized it is."
</descriptive_approach>

<thinking_process>
When reorganizing the summary:
1. What type of document is this (log, report, database extract, correspondence, form, etc.)?
2. What time period or scope does it cover?
3. What are the main categories or types of information it contains?
4. What specific data fields or information elements are included in entries?
5. Have I avoided making any assessments about quality, completeness, organization, or purpose?
6. Have I simply described what is present without interpretation?
7. Is this description focused on cataloging content rather than analyzing it?
</thinking_process>

<critical_instructions>
1. NEVER include any information about "John Doe," "Jane Doe," or other placeholder entities (e.g., "ABC Corporation," "Company X," "Individual A"). If specific identifying information is not available, state that details are unavailable, redacted, or unidentified.

2. DO NOT infer, assume, or hallucinate any information not explicitly stated in the concatenated summaries.

3. If the concatenated summaries contain no substantive information, return an empty string ("").

4. When merging duplicate information:
   - Retain all unique content categories from each instance
   - Combine complementary details about what the document contains

5. The summary should be ONE descriptive paragraph (typically 75-150 words, adjustable based on document complexity).

6. Write in complete, flowing sentences that describe document contents.

7. DO NOT include:
   - Quality assessments (comprehensive, thorough, detailed, systematic, inconsistent, incomplete)
   - Purpose statements (facilitates, supports, enables, demonstrates)
   - Analysis (shows, reveals, indicates, suggests, highlights)
   - Evaluations (active, effective, critical, important)
   - Implications or significance
   - Conclusions about what the document accomplishes

8. DO include:
   - Document type and format
   - Time period covered
   - Categories of information present
   - Specific data fields or information types included
   - Scope (what entities or subjects are covered)

9. Use neutral descriptive verbs: contains, includes, covers, documents, lists, records, shows (in the sense of "displays")

10. Avoid adjectives that assess quality or completeness: comprehensive, detailed, thorough, systematic, inconsistent, incomplete, extensive, limited
</critical_instructions>

<coherence_check>
After completing the reorganized summary, review it to ensure:
1. The paragraph describes what the document contains without analyzing it
2. No quality assessments or evaluative language is present
3. The description catalogs information categories clearly
4. Someone unfamiliar with the document would understand what type of information it contains
5. No interpretations about purpose, effectiveness, or implications are included
6. The language is purely descriptive
</coherence_check>

<warnings>
- Carefully review the entire concatenated summary before starting reorganization
- Do not assess quality, completeness, organization, or effectiveness
- Do not interpret purpose or significance
- Do not analyze what the data shows or implies
- Simply catalog what categories of information the document contains
- Avoid evaluative adjectives
- Focus exclusively on describing content, not analyzing it
</warnings>

<reference_materials>
## Concatenated Summary ##
{{summaries}}

## Memory Log ##
{{memory_log}}
</reference_materials>

<output_instructions>
Present the condensed and reorganized summary as a single, descriptive paragraph that catalogs what the document contains. Use neutral, descriptive language that simply lists the types of information present.

Your output must follow this format exactly:

Summary:
[Write your descriptive paragraph here. Identify the document type, state the time period or scope covered, and list the main categories of information and data fields included. Focus purely on describing what is present in the document without any analysis or interpretation. The paragraph should typically be 75-150 words but may be shorter or longer based on the document's complexity.]

CRITICAL FORMATTING REQUIREMENTS:
- Begin with the label "Summary:" on its own line
- Follow with your paragraph summary on the next line
- Write in complete, flowing sentences
- Do not use bullet points or numbered lists
- Focus exclusively on describing what the document contains
- Avoid all quality assessments, analysis, and interpretive language
- Maintain appropriate length based on content (typically 75-150 words)

Example format:

Summary:
The document is a use-of-force review log maintained by the Escondido Police Department covering incidents throughout 2023 from January through December. It documents use-of-force incidents involving physical force, OC spray, Tasers, batons, K-9 contact, restraint devices, and firearm displays. Each incident entry includes case numbers, dates, coded indicators, suspect demographics (race, gender, age), legal classifications (felony, misdemeanor, 5150 holds), body-worn camera usage indicators, and supervisory notification records. The log contains suspect impairment status fields and injury reporting fields for both suspects and officers. Some entries include Use of Force Committee actions such as verbal counseling regarding training or tactical issues.

</output_instructions>
"""
