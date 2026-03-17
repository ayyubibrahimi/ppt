previous_correspondence = """
[
  {
    "scenario": "Agency confirmed receipt of a request",
    "agency_action": "Agency sent confirmation that they received the public records request",
    "our_response": "Thank you for confirming."
  },
  {
    "scenario": "Agency requested an extension to provide a determination or produce records",
    "agency_action": "Agency notified us they need additional time to locate and review the requested records",
    "our_response": "Thank you for the update."
  },
  {
    "scenario": "Agency sent final batch of records",
    "agency_action": "Agency provided the last set of responsive records and indicated the request is complete",
    "our_response": "I'm confirming receipt. Thank you for your response."
  },
  {
    "scenario": "Agency sent records, will send more at a later date",
    "agency_action": "Agency provided some records but indicated additional records will follow",
    "our_response": "I'm confirming receipt. Thank you."
  },
  {
    "scenario": "180 Day Update for Withheld Records",
    "agency_action": "Agency has withheld records for 180+ days citing ongoing investigation",
    "our_response": "Under Penal Code § 832.7(b)(8), we acknowledge that certain records may be withheld due to ongoing investigations. However, the law requires your agency to keep this request open and provide written updates explaining the specific reason for continued withholding and an estimated disclosure date.\n\nPer Penal Code § 832.7(b)(8) you are obligated to provide these updates within 60 days of the incident and every 180 days thereafter while the investigation remains active. If charges have been filed, confirm whether disclosure will be delayed until after the verdict or plea withdrawal period. For administrative investigations, updates must comply with the 180-day maximum delay."
  },
  {
    "scenario": "Agency sends website where records are posted and closes the request",
    "agency_action": "Agency directed us to a website for records and attempted to close the request",
    "our_response": "Pursuant to Cal. Gov. Code § 7922.535, we expect a determination as to whether your agency possesses responsive records and whether any records are being withheld. In accordance with Cal. Gov. Code § 7922.545, we are willing to receive records via a website; however, we request notification each time additional records are made available."
  },
  {
    "scenario": "State Data Check - Multiple records missing (12+ incidents)",
    "agency_action": "Agency has not provided records for incidents that appear in state-reported data",
    "our_response": "We have reviewed our records and believe that documents related to the incidents listed in the attached file remain outstanding. These incidents were identified using data your agency reported to the California Department of Justice, as required under Government Code §§ 12525 and 12525.2, which mandate reporting of use-of-force incidents involving serious bodily injury or death, firearm discharges, and in-custody deaths.\n\nIf any of the requested records are being withheld, please cite the specific exemption under the California Public Records Act that authorizes nondisclosure, or provide a written explanation as to why the records are not releasable.\n\nIf additional information is needed to locate these records, please let us know. Under Government Code § 7922.600, your agency has an affirmative obligation to assist requesters in identifying and locating responsive records. As the court held in Cal. First Amend. Coalition v. Superior Court (1998) 67 Cal.App.4th 159, 166, this duty includes providing information about your records and systems to facilitate focused and effective requests."
  },
  {
    "scenario": "Agency provides indirect link to records instead of direct access",
    "agency_action": "Agency provided a general website link rather than direct access to responsive records",
    "our_response": "Pursuant to Cal. Gov. Code § 7922.545(b), if a requester is unable to access or reproduce records from a website, the agency must promptly provide a copy under § 7922.530(a). Accordingly, we request a direct link to all responsive records. If that is not possible, please provide copies of all responsive records."
  },
  {
    "scenario": "Request name and title of decision-maker",
    "agency_action": "Agency made a determination but did not identify who made the decision",
    "our_response": "Pursuant to Cal. Gov. Code, § 7922.540, subds. (a)–(b), please identify the name and title of the individual responsible for the determination regarding this request."
  },
  {
    "scenario": "No determination provided within 10 days",
    "agency_action": "10+ days have passed since request was submitted with no determination from agency",
    "our_response": "Pursuant to Cal. Gov. Code § 7922.535(a), your agency is required to provide a determination within 10 calendar days of receiving our public records request. This determination must state whether disclosable records exist and, if so, include an estimated date for their release. To date, we do not have a record of receiving this required response. Please provide your determination promptly."
  },
  {
    "scenario": "No determination after 14-day extension expired",
    "agency_action": "Agency took a 14-day extension but still has not provided a determination after extension period ended",
    "our_response": "Under Cal. Gov. Code § 7922.535(b), you invoked a 14-day extension to respond to our request. However, that extended deadline has now passed, and we have not received the required determination. In accordance with the statute, we request immediate compliance and prompt issuance of your response."
  },
  {
    "scenario": "No response or records within 45 days of request",
    "agency_action": "45+ days have passed since request was submitted with no substantive response or records provided",
    "our_response": "Your agency is obligated to provide a prompt response and timely production of all responsive records under the California Public Records Act.\n\nGovernment Code § 7922.530 requires that, upon receiving a request that reasonably describes an identifiable record, the agency \"shall make the records promptly available.\" Similarly, Government Code § 7922.500 makes clear that the Act does not permit an agency to \"delay or obstruct the inspection or copying of public records.\"\n\nWith respect to records subject to disclosure under Penal Code § 832.7(b), subdivision (11) mandates that such records be provided \"at the earliest possible time and no later than 45 days from the date of a request,\" unless temporary withholding is justified under the limited exceptions in subdivision (b)(8).\n\nAccordingly, we expect the agency to comply with these statutory requirements and provide all responsive records without further delay."
  },
  {
    "scenario": "Agency has not provided determination on requested records",
    "agency_action": "Agency responded but did not clearly determine whether records will be disclosed",
    "our_response": "Pursuant to Gov. Code, § 7922.000, the agency is required to issue a determination identifying whether it will disclose the specific records requested. Please provide a response addressing each item in the request."
  },
  {
    "scenario": "Agency attempts to close request before all records sent",
    "agency_action": "Agency indicated request is closed but has not provided all responsive records",
    "our_response": "Under the California Public Records Act (CPRA), a municipality may not close a request before all responsive records have been produced, unless the request has been fully satisfied or legitimately denied under an exemption."
  },
  {
    "scenario": "Agency claims they cannot find records",
    "agency_action": "Agency stated they cannot locate responsive records and attempted to close request",
    "our_response": "Pursuant to Gov. Code, § 7922.600, public agencies have an affirmative obligation to assist requesters in identifying records responsive to a Public Records Act request. As the court held in Cal. First Amend. Coalition v. Superior Court (1998) 67 Cal.App.4th 159, 166, this duty includes helping requesters make focused and effective requests by providing information about the agency's records and systems. Accordingly, please assist in identifying and locating all records responsive to my request."
  },
  {
    "scenario": "Agency asks why we want the records",
    "agency_action": "Agency requested explanation or justification for why we are seeking the records",
    "our_response": "Pursuant to Gov. Code, § 7921.300, access to a public record may not be limited based on the purpose for which the record is requested, so long as the record is otherwise subject to disclosure under the California Public Records Act."
  },
  {
    "scenario": "Agency over-redacts records beyond statutory limits",
    "agency_action": "Agency heavily redacted records beyond what appears statutorily justified",
    "our_response": "Pursuant to California Penal Code § 832.7(b)(6), an agency may redact disclosable records in limited circumstances: (A) to remove personal data such as home addresses, telephone numbers, or identities of family members, excluding names and work-related information of peace and custodial officers; (B) to preserve the anonymity of whistleblowers, complainants, victims, and witnesses; (C) to protect confidential medical, financial, or other information prohibited from disclosure by federal law or where privacy concerns clearly outweigh the public interest; and (D) where there is a specific, articulable, and particularized threat to the physical safety of any peace officer, custodial officer, or other individuals. Redactions must be narrowly tailored, and all non-exempt information must be disclosed."
  },
  {
    "scenario": "Agency redacts names of officers (except involved officers)",
    "agency_action": "Agency redacted names of peace officers who were not directly involved in the incident",
    "our_response": "Pursuant to California Penal Code § 832.7(b)(6)(A), an agency is prohibited from redacting the names and work-related information of peace and custodial officers. While limited redactions are permitted to protect personal data such as home addresses or family member identities, the statute explicitly excludes officer names and work-related details from permissible redactions."
  },
  {
    "scenario": "Agency only sends PDFs and closes request",
    "agency_action": "Agency provided only PDF documents and indicated request is complete",
    "our_response": "As a reminder our request includes all records that reference disclosable incidents, not just PDFs. Under Penal Code § 832.7(b)(3), this includes investigative reports; photographic, audio, and video evidence; interview transcripts or recordings; autopsy reports; materials submitted to the district attorney or charging authority; findings or recommendations; and all related disciplinary records, including those reflecting modifications or final actions. This also covers incidents where the officer resigned before the investigation concluded."
  },
  {
    "scenario": "Agency refuses to send records created by another agency",
    "agency_action": "Agency declined to produce records because they were originally created by a different agency",
    "our_response": "Pursuant to Becerra v. Superior Court (2020) 44 Cal.App.5th 897, your agency is obligated to disclose all disclosable police records in its possession, regardless of whether the agency itself prepared, owns, or originally used those records."
  },
  {
    "scenario": "Agency claims exemption allows them to withhold records",
    "agency_action": "Agency cited an exemption as reason for not disclosing records",
    "our_response": "Please be advised that even where exemptions under the California Public Records Act may apply, your agency retains the discretion to disclose the records. As the court recognized in Black Panther Party v. Kehoe (1974) 42 Cal.App.3d 645, 656, local agencies may choose to disclose public records even though they are exempt. Nothing in the Act prohibits voluntary disclosure of exempt material unless disclosure is otherwise prohibited by law. Accordingly, we urge the agency to exercise its discretion in favor of transparency and release any records at issue, notwithstanding the availability of an exemption."
  },
  {
    "scenario": "Agency withholds entire record claiming part is exempt",
    "agency_action": "Agency refused to disclose any portion of a record because some content may be exempt",
    "our_response": "Pursuant to Gov. Code, § 7922.525, the fact that a portion of a record may be exempt from disclosure does not justify withholding the entire record. The agency is required to redact the exempt material and disclose the remainder of the record that is subject to disclosure."
  },
  {
    "scenario": "Agency claims records have been destroyed",
    "agency_action": "Agency stated that responsive records were destroyed pursuant to retention schedule",
    "our_response": "Pursuant to Government Code § 7922.530, I request all versions of your agency's retention schedule(s) for law enforcement records, including any drafts, revisions, or adopted schedules, from January 1, 2014, to the present."
  },
  {
    "scenario": "Agency cites fee greater than $100",
    "agency_action": "Agency indicated fees exceeding $100 will be charged for the records",
    "our_response": "Pursuant to Government Code § 7922.530, I am requesting all versions of your agency's fee schedule(s) applicable to law enforcement records from January 1, 2014, to the present. This request includes, but is not limited to:\nThe actual fee schedules in effect during that period;\nAny resolutions, ordinances, or administrative documents adopting or amending those schedules;\nAny audits, studies, memos, or documentation used to justify or calculate the fees charged.\n\nIf any portion of this request is unclear, or if you require additional information to locate responsive records, please notify me in accordance with your agency's duty under § 7922.600 to assist in making a focused and effective request."
  },
  {
    "scenario": "Agency charges fees for search, review, or redaction time",
    "agency_action": "Agency attempted to charge for staff time spent searching for, reviewing, or redacting records",
    "our_response": "Please be advised that under Government Code § 7922.530, a local agency may only charge for the direct cost of duplicating a record when the requester seeks a copy, or a statutory fee if specifically authorized.\n\nAs clarified in North County Parents Organization v. Dept. of Education (1994) 23 Cal.App.4th 144, 148, the \"direct cost of duplication\" is limited to the expense of running the copy machine and, at most, the cost of the person operating it. It explicitly does not include time spent locating, reviewing, or handling files.\n\nFurther, for electronic records, National Lawyers Guild v. City of Hayward (2020) 9 Cal.5th 488, 492, confirms that duplication costs are limited to the direct cost of producing the electronic copy. Agencies may not charge for time spent on redaction or other ancillary tasks.\n\nAdditionally, Penal Code § 832.7(b)(10) expressly prohibits agencies from charging for the costs of \"searching for, editing, or redacting\" records subject to disclosure under that section. Any attempt to impose such charges would be inconsistent with both the Government Code and controlling case law."
  },
  {
    "scenario": "Agency requests extension without providing estimated date",
    "agency_action": "Agency requested additional time but did not specify when records will be available",
    "our_response": "Thank you for the update. Do you have an estimated date of disclosure?"
  }
]
"""