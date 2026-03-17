import logging
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from models import RequestOptions,RequestOption

logger = logging.getLogger(__name__)


class SimpleRequestGenerator:
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def generate_request_options(self, user_topic: str) -> RequestOptions:
        """Generate 1-3 request options based on user topic"""
        
        prompt = f"""
        You are helping generate public records requests for law enforcement agencies. 
        The user wants records related to: "{user_topic}"
        
        Generate 1-3 different approaches for requesting records about this topic.
        Each option should have:
        1. A clear title
        2. 3-5 specific bullet points of what to request
        3. Brief context about what this seeks
        
        Use this template structure but adapt the content:
        "We are seeking data about [TOPIC] within [JURISDICTION].
        Please provide any spreadsheets, databases, or logs showing as much of the following information..."
        
        Examples of good bullet points:
        - All incident reports involving use of force between [dates]
        - Officer names, badge numbers, and dates of incidents
        - Disciplinary actions taken, if any
        - Body camera footage availability and retention status
        - Training records related to de-escalation techniques
        - Budget allocations for equipment purchases over $5,000
        - Policy documents regarding traffic stop procedures
        
        Make the requests:
        - Specific but not overly narrow
        - Focused on data that would realistically exist
        - Professional and legally appropriate
        - Avoid requesting personal information that wouldn't be public
        
        For the topic "{user_topic}", generate different angles like:
        - Specific incident-based request
        - Policy/procedure request  
        - Training/personnel request
        - Budget/equipment request
        
        Output format:
        {{
          "options": [
            {{
              "title": "Clear title describing the request",
              "bullet_points": [
                "Specific data element 1",
                "Specific data element 2", 
                "Specific data element 3",
                "Specific data element 4"
              ],
              "context": "Brief explanation of what this request seeks to understand"
            }}
          ],
          "recommendation": "Explanation of which option might work best"
        }}
        """
        
        structured_llm = self.llm_client.with_structured_output(RequestOptions)
        result = structured_llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Generate public records request options for: {user_topic}")
        ])
        
        return result
    
    def create_full_request_text(self, selected_option: RequestOption, user_info: Dict[str, str]) -> str:
        """Create the full request text using the template"""
        
        # Create bullet point list
        bullet_list = "\n".join([f"* {point}" for point in selected_option.bullet_points])
        
        # Build the full request using the template
        request_text = f"""To Whom It May Concern:

This is a public records request made to your agency seeking records related to law enforcement officers in your jurisdiction.

{selected_option.context}

Please provide any spreadsheets, databases, or logs showing as much of the following information as is maintained in that format regarding:
{bullet_list}

If your system contains data elements not listed above, please include them in the response, provided they are releasable under the law. On the other hand, we recognize some of the information we are asking for may not be tracked by your system. If that is the case, we are willing to accept as many of the data elements as your agency maintains. If some records are more readily available, we are happy to receive partial information as soon as possible while the remaining request is processed.

In addition to the data elements listed, we request documentation necessary to understand and interpret the data, including but not limited to record layouts, data dictionaries, code sheets, lookup tables, etc.

Our preference is to receive structured data provided in a machine-readable text file, such as delimited or fixed-width formats. We can also handle a variety of other data formats including SQL databases, Excel workbooks and MS Access. If there are additional formats your agency would prefer to provide, please let us know.

We are seeking this information as a news media organization on a matter of public interest concerning the conduct of government. As such, we ask for a waiver of all fees, if allowed under state law. If fees are necessary to reimburse the agency for actual costs, we agree to pay up to $100. If costs exceed that amount, please let us know before fulfilling the request.

Please send clarifications and questions via electronic communication at any time. Thank you very much for your time and attention to this request.

Sincerely,
{user_info.get('first_name', '')} {user_info.get('last_name', '')}
{user_info.get('organization', 'Independent Researcher')}
{user_info.get('email', '')}
{user_info.get('phone', '')}"""

        return request_text