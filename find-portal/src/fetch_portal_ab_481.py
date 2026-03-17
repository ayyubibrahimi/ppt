import asyncio
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from aiohttp import ClientTimeout
from aiohttp_retry import RetryClient, ExponentialRetry
import json
from llm import gpt_4o_mini
import datetime
from typing import List, Optional, Dict
from urllib.parse import urlparse, urljoin
from models import (
    ValidationResult,
    AgentState,
    MultiAgentDecision,
    ExplorationLinks,
    ExtractedLink,
    ExtractedLinks,
)
from helpers import count_tokens
import tiktoken 



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize LLMs with structured output
structured_llm = gpt_4o_mini.with_structured_output
structured_llm_large = gpt_4o_mini.with_structured_output


LINK_SELECTOR_PROMPT = """You are a strategic intelligence analyst tasked with identifying the most relevant link to find an  Annual Military Equipment Report.
Your goal is to select the URL that will lead to a government agency's  Annual Military Equipment Report.

Millitary Equipment reports typically contain terms like:
- "Military Equipment", "Annual Military Equipment Report"
- "Military Equipment Policy", "Military Equipment Use", "Military Equipment Inventory"
- Military Equipment Annual Report"
- "Police Equipment", "Law Enforcement Equipment", "Surveillance Equipment"

Example successful analysis:
Input markdown:
[About Us](/about)
[Contact](/contact)
[Military Equipment Report](/ab481)
[News](/news)

Analysis:
url: /ab481
rationale: This link directly references millitary equipment which is highly likely to lead to the  Annual Military Equipment Report. Government agencies typically use straightforward naming conventions for their mandated reporting.

Example unsuccessful analysis:
Input markdown:
[Services](/services)
[Staff Directory](/staff)
[News & Events](/news)
[Contact](/contact)

Analysis:
url: /services
rationale: While services might contain links to military equipment reports, it's not a direct path. This was a suboptimal choice as it requires additional navigation steps.

Previous attempts (if any):
{previous_attempts}

Markdown content to analyze:
{markdown_content}

Expected Output Format:
url: (complete URL path)
rationale: (detailed explanation of selection focusing on  military equipment report indicators)"""

LINK_EXTRACTOR_PROMPT = """You are a deep link analyzer tasked with finding ALL potential paths to  Annual Military Equipment Reports within the content.

Your goal is to identify any links that might lead to:
-  Annual Military Equipment Reports
- millitary equipment military equipment documentation
- Military equipment policies and inventories
- Law enforcement equipment reports
- Police equipment annual reports
- Military equipment use reports

Look for these key indicators:
- Terms: "", "millitary equipment", "military equipment", "annual report", "equipment report"
- Equipment types: "surveillance", "police equipment", "law enforcement equipment", "tactical equipment"
- Action words: "report", "annual", "inventory", "policy", "use report"

Example successful extraction:
Input content:
Welcome to our agency! Learn [about us](/about) or [contact us](/contact).
Footer: [millitary equipment Report](/transparency/ab481) | [Military Equipment](/equipment) | [Annual Reports](/reports)
Sidebar: Need equipment info? [View millitary equipment Report](/ab481/report) or [search equipment inventory](/equipment/search)

Analysis:
links:
- url: /transparency/ab481
  context: "millitary equipment Report link in footer navigation"
  depth_value: 0.95
  parent_url: current_page_url
  reasoning: Direct "millitary equipment Report" reference in official footer navigation suggests primary military equipment report
- url: /equipment
  context: "Military Equipment link in footer"
  depth_value: 0.90
  parent_url: current_page_url
  reasoning: "Military Equipment" directly relates to millitary equipment reporting requirements - high likelihood
- url: /ab481/report
  context: "View millitary equipment Report link in sidebar"
  depth_value: 0.95
  parent_url: current_page_url
  reasoning: Action-oriented language "View millitary equipment Report" with specific millitary equipment path indicates report location

Example unsuccessful extraction:
Input content:
Check out [today's announcements](/announcements) and [upcoming events](/events).
[Staff directory](/staff) | [Budget information](/budget)

Analysis:
links:
- url: /budget
  context: "Budget information in footer"
  depth_value: 0.3
  parent_url: current_page_url
  reasoning: While budget info might contain equipment expenses, this is likely just static budget documents, not millitary equipment military equipment reports

Current page URL: {url}
Previously visited: {visited_urls}
Page content to analyze:
{content}

For each link found, provide:
1. Complete URL
2. Surrounding context
3. Depth value (0-1) based on likelihood of leading to  military equipment report
4. Parent URL (current page)
5. Reasoning for depth value assignment focusing on  military equipment report indicators"""

# Updated VALIDATOR_PROMPT for public records portal detection
VALIDATOR_PROMPT = """
You are a validation specialist analyzing webpages to identify  Annual Military Equipment Reports. Your goal is to determine if a page contains or serves as an  Annual Military Equipment Report where agencies document their military equipment inventory, policies, and usage.

An  Annual Military Equipment Report must meet at least ONE of these criteria:
1. Contains the actual  Annual Military Equipment Report document or content
2. Provides interface to view or download millitary equipment military equipment reports
3. Shows comprehensive military equipment inventory, policies, or usage data as required by millitary equipment
4. Contains clear documentation of military equipment as mandated by 

Positive indicators (increase confidence):
- References to "", "millitary equipment", or "AB481"
- Military equipment inventory lists, policies, or usage reports
- Annual military equipment reporting documentation
- Law enforcement or police equipment documentation
- Military equipment policy documents
- Equipment acquisition, use, or disposal reports
- Surveillance equipment documentation
- Government agency official reporting on military equipment
- Download links for millitary equipment reports or military equipment documentation

Negative indicators (decrease confidence):
- Only general information about military or law enforcement without specific equipment reporting
- General government information without millitary equipment or military equipment content
- News/press releases without actual millitary equipment reporting
- Contact forms that aren't related to military equipment reporting
- Document libraries without millitary equipment or military equipment content

Example Valid  Report:
[Input]
 Annual Military Equipment Report
Fiscal Year 2023-2024

This report is submitted in accordance with  requirements for annual military equipment reporting.

Military Equipment Inventory:
- Surveillance Cameras: 15 units
- Tactical Vehicles: 3 units
- Communications Equipment: 8 units

Download Full Report [PDF Link]
Previous Years' Reports: [Archive Link]

Analysis:
is_valid: true
confidence: 0.98
reasoning: Page contains actual  Annual Military Equipment Report with specific equipment inventory, references to millitary equipment compliance, and download functionality. This is definitively an millitary equipment military equipment report.

Example Invalid Page:
[Input]
About Our Police Department
Contact Information
Phone: (555) 123-4567
Email: info@police.gov

Department Services:
Our department provides law enforcement services to the community. We are committed to public safety and professional service.

Analysis:
is_valid: false
confidence: 0.2
reasoning: Page only provides general information about police department services and contact details. No actual millitary equipment reporting, military equipment documentation, or  content present.

Current Context:
URL: {url}
Parent URL: {parent_url}
Depth: {depth}
Content:
{content}

Expected Output Format:
is_valid: true/false
confidence: 0.0-1.0
reasoning: detailed explanation focusing on  military equipment report functionality
recommendations: list of suggestions if invalid, or None if valid
"""

# Updated ORCHESTRATOR_PROMPT for public records portal search
ORCHESTRATOR_PROMPT = """
You are the orchestrator managing a recursive web crawling process to find an  Annual Military Equipment Report where government agencies document their military equipment inventory, policies, and usage as required by California law.

Decision Criteria:
1. TERMINATE (confidence >= 0.95):
   - Page contains actual  Annual Military Equipment Report
   - Clear millitary equipment reporting documentation or download links
   - Comprehensive military equipment inventory, policies, or usage data
   - No better alternatives in unexplored links
   
2. CONTINUE (confidence 0.8-0.94):
   - Page shows some millitary equipment or military equipment content but may not be the complete report
   - Unexplored links suggest more complete millitary equipment reporting
   - Within reasonable depth limit
   - Clear path to better military equipment report documentation
   
3. RETRY (confidence < 0.8):
   - Current path unlikely to lead to millitary equipment military equipment report
   - Better alternative strategies available
   - Current depth approaching limit

Example TERMINATE Decision:
Input state:
- Current depth: 2
- Latest validation: 
  * URL: /ab481/report
  * Valid: true
  * Confidence: 0.98
  * Contains complete  Annual Military Equipment Report with inventory and download links
- Unexplored links: None above 0.8 confidence

Analysis:
action: terminate
feedback: Found definitive  Annual Military Equipment Report with complete documentation, equipment inventory, and professional report format. No better alternatives visible.
alternative_strategy: None needed - objective achieved

Example CONTINUE Decision:
Input state:
- Current depth: 2 
- Latest validation:
  * URL: /transparency
  * Valid: true
  * Confidence: 0.85
  * Shows some military equipment information but no complete millitary equipment report
- Unexplored links: 2 promising paths
  * /transparency/ab481 (0.95 confidence)
  * /reports/military-equipment (0.90 confidence)

Analysis:
action: continue
feedback: Current page provides some military equipment information but lacks complete millitary equipment reporting. Unexplored links suggest more complete report documentation.
alternative_strategy: Prioritize /transparency/ab481 as it combines transparency context with specific millitary equipment reference

Example RETRY Decision:
Input state:
- Current depth: 3
- Latest validation:
  * URL: /contact/general
  * Valid: false
  * Confidence: 0.2
  * Only shows general contact information
- Better unexplored alternatives available

Analysis:
action: retry
feedback: Current path leading to general contact information rather than millitary equipment military equipment reports. Need to pivot to equipment-focused paths.
alternative_strategy: Look for links containing 'millitary equipment', '', 'military equipment', 'annual report', or 'equipment report'

Current state:
- Exploration depth: {current_depth}
- Maximum depth: {max_depth}
- Attempts made: {num_attempts}
- Latest validation: {validation_result}
- Visited URLs: {visited_urls}
- Unexplored high-value links: {unexplored_links}

Decision Process:
1. Check validation confidence against decision criteria
2. Evaluate  military equipment report indicators
3. Assess quality of unexplored alternatives
4. Consider depth and attempt limits
5. Look for clear improvement opportunities toward millitary equipment report documentation

Expected Output Format:
action: continue/terminate/retry
feedback: detailed analysis of decision factors focusing on millitary equipment military equipment report functionality
alternative_strategy: specific next steps if millitary equipment report not yet found"""

class IndexCrawler:
    def __init__(self, num_agents: int = 5):
        self.num_agents = num_agents
        self.agents = {}  # Dict[str, AgentState]
        self.previous_attempts = []
        self.max_attempts = 15  # Increased for multiple agents
        self.visited_urls = set()
        self.current_depth = 0
        self.max_depth = 3
        self.exploration_links = []

    def initialize_agents(self):
        """Create initial agent states"""
        for i in range(self.num_agents):
            agent_id = f"agent_{i}"
            self.agents[agent_id] = AgentState(
                agent_id=agent_id,
                current_url="",
                current_depth=0,
                visited_urls=[],
                validation_result=None,
                parent_url=None,
                depth_value=None
            )

    def normalize_url(self, base_url, url):
        """
        Normalize a URL by handling relative paths and ensuring consistent format
        
        Args:
            base_url (str): The base URL to resolve relative paths against
            url (str): The URL to normalize
            
        Returns:
            str: The normalized URL
        """
        try:
            # Handle empty or None URLs
            if not url:
                return None
                
            # Remove whitespace
            url = url.strip()
            
            # Handle relative URLs
            if url.startswith('/'):
                # Parse the base URL to get the scheme and netloc
                parsed_base = urlparse(base_url)
                return f"{parsed_base.scheme}://{parsed_base.netloc}{url}"
            elif not url.startswith(('http://', 'https://')):
                # For URLs without scheme, join with base URL
                return urljoin(base_url, url)
                
            # Return as-is if it's already an absolute URL
            return url
            
        except Exception as e:
            self.logger.error(f"Error normalizing URL {url}: {str(e)}")
            return None

    async def fetch_content(self, url: str) -> str:
        """Fetch content from URL with retry logic"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        timeout = ClientTimeout(total=300)
        retry_options = ExponentialRetry(
            attempts=3,
            start_timeout=1,
            max_timeout=30,
            factor=2.0
        )
        
        async with RetryClient(retry_options=retry_options, timeout=timeout) as session:
            fixed_url = url.replace('https//', 'https://')
            jina_url = f"https://r.jina.ai/{fixed_url}"
            async with session.get(jina_url, headers=headers) as response:
                return await response.text()

    async def select_links(self, markdown_content: str) -> ExplorationLinks:
        """Use LLM to select valuable links for exploration"""
        previous_attempts_str = "\n".join([
            f"- {attempt['url']}: {attempt.get('validation_result', {}).get('reasoning', 'No validation')}"
            for attempt in self.previous_attempts
        ])
        
        system_instructions = LINK_SELECTOR_PROMPT.format(
            previous_attempts=previous_attempts_str,
            markdown_content=markdown_content
        )
        
        selector_llm = structured_llm(ExplorationLinks)
        result = selector_llm.invoke([
            SystemMessage(content=system_instructions),
            HumanMessage(content="Select one valuable link to explore from this markdown content.")
        ])
        
        return result

    async def extract_links(self, url: str, content: str) -> ExtractedLinks:
        """Extract and analyze all potential index-related links from content"""
        system_instructions = LINK_EXTRACTOR_PROMPT.format(
            url=url,
            visited_urls=list(self.visited_urls),
            content=content
        )
        
        extractor_llm = structured_llm(ExtractedLinks)
        result = extractor_llm.invoke([
            SystemMessage(content=system_instructions),
            HumanMessage(content="Extract and analyze all potential index-related links from this content.")
        ])

        print(f"Links: {result}")
        
        # Normalize URLs and add to tracking
        for link in result.links:
            link.url = self.normalize_url(url, link.url)
            link.parent_url = url
            
        return result

    async def validate_page(self, url: str, content: str, depth: int, parent_url: str) -> ValidationResult:
        """Enhanced validation with depth, parent context, and content truncation"""
        content_tokens = count_tokens(content)
        truncated = False
        
        if content_tokens > 15000:
            enc = tiktoken.encoding_for_model("gpt-4")
            tokens = enc.encode(content)
            truncated_tokens = tokens[:1000]
            content = enc.decode(truncated_tokens)
            truncated = True

        truncation_notice = "\n## NOTE: Content truncated from {original_tokens} to 5000 tokens due to length. This may indicate a comprehensive index page. ##".format(
            original_tokens=content_tokens
        ) if truncated else ""
        
        system_instructions = VALIDATOR_PROMPT.format(
            url=url,
            content=content + truncation_notice,
            depth=depth,
            parent_url=parent_url
        )

        validator_llm = structured_llm_large(ValidationResult)
        result = validator_llm.invoke([
            SystemMessage(content=system_instructions),
            HumanMessage(content="Validate if this page is index where all of the articles live.")
        ])

        if truncated and 0.8 <= result.confidence <= 0.85:
            result.confidence = 0.95
            result.reasoning += "\nNOTE: Confidence adjusted upward due to page length requiring truncation."

        return result

    async def get_multi_agent_decision(
        self,
        agent_states: Dict[str, AgentState],
        available_links: List[ExtractedLink]
    ) -> MultiAgentDecision:
        """Orchestrate decisions across all agents based on their current states"""
        MULTI_AGENT_ORCHESTRATOR_PROMPT = """You are a high-level orchestrator managing multiple web crawling agents searching for an  Annual Military Equipment Report.

        Current Agent States:
        {agent_states}

        Available Unexplored Links:
        {available_links}

        Your task is to:
        1. Analyze the validation results from all agents
        2. Determine if any agent has found the Annual Military Equipment Report (confidence >= 0.95)
        3. If multiple agents have a high-confidence result, review the validation details for each agent to determine the best choice. For example, if one agent found a page with basic military equipment information while another found a complete millitary equipment annual report with equipment inventory and download links, the latter is likely the correct choice.
        4. If not found, decide optimal next actions:
            - Which agents should explore deeper from their current position
            - Which agents should explore new links from the initial set
            - How to distribute agents across promising paths that lead to millitary equipment military equipment reports
        
         Military Equipment Report Indicators (prioritize agents that found these):
        - Complete  Annual Military Equipment Reports or download links
        - Military equipment inventory lists, policies, or usage documentation
        - millitary equipment compliance reporting and documentation
        - Annual military equipment reporting interfaces
        - Government agency official styling with millitary equipment or military equipment focus
        
        Previous exploration history:
        {exploration_history}

        Expected output:
        - action: 'terminate' if millitary equipment report found, 'explore_new' or 'explore_deeper'
        - target_agent_ids: list of agents that should take action
        - target_urls: map of agent_id to next unique URL (if applicable)
        - rationale: detailed explanation, if there is a winner include the rationale for the winner agent focusing on millitary equipment military equipment report functionality
        - confidence: 0-1 score 
        - winner_agent_id: agent_id of the agent that has found the  Annual Military Equipment Report
        """

        # Format agent states for prompt
        agent_states_str = "\n".join([
            f"Agent {state.agent_id}:"
            f"\n- Current URL: {state.current_url}"
            f"\n- Depth: {state.current_depth}"
            f"\n- Validation: {state.validation_result.dict() if state.validation_result else 'None'}"
            for state in agent_states.values()
        ])

        # Format available links
        links_str = "\n".join([
            f"- {link.url} (depth_value: {link.depth_value})"
            for link in available_links
            if link.url not in self.visited_urls
        ])

        # Format exploration history
        history_str = "\n".join([
            f"Attempt {i}: {attempt['url']} - Valid: {attempt['validation_result']['is_valid']}"
            f" (confidence: {attempt['validation_result']['confidence']})"
            for i, attempt in enumerate(self.previous_attempts)
        ])

        # print(f"Agent states: {agent_states_str}")

        # print(f"Available links: {links_str}")

        # print(f"Exploration history: {history_str}")

        system_instructions = MULTI_AGENT_ORCHESTRATOR_PROMPT.format(
            agent_states=agent_states_str,
            available_links=links_str,
            exploration_history=history_str
        )

        orchestrator_llm = structured_llm_large(MultiAgentDecision)
        result = orchestrator_llm.invoke([
            SystemMessage(content=system_instructions),
            HumanMessage(content="Determine next actions for all agents based on their current states.")
        ])

        return result

    async def run_agent(self, agent_id: str, url: str):
        """Run a single agent's exploration of a URL"""
        agent = self.agents[agent_id]
        
        # Update agent state
        agent.current_url = url
        agent.visited_urls.append(url)
        self.visited_urls.add(url)

        # Fetch and validate content
        content = await self.fetch_content(url)
        validation_result = await self.validate_page(
            url=url,
            content=content,
            depth=agent.current_depth,
            parent_url=agent.parent_url
        )

        # Update agent state
        agent.validation_result = validation_result

        # Record attempt
        self.previous_attempts.append({
            "agent_id": agent_id,
            "url": url,
            "parent_url": agent.parent_url,
            "depth": agent.current_depth,
            "depth_value": agent.depth_value,
            "content": content,
            "validation_result": validation_result.model_dump()
        })

        # Extract new links if needed
        if not validation_result.is_valid or validation_result.confidence < 0.8:
            new_links = await self.extract_links(url, content)
            for new_link in new_links.links:
                if new_link.url not in self.visited_urls:
                    self.exploration_links.append(new_link)

    async def save_results(self, winner_agent_id: Optional[str] = None):
        """Save exploration results to files with winner agent information"""
        if not self.previous_attempts or not winner_agent_id:
            logger.info("No successful exploration to save")
            return
            
        # Find the winning attempt
        winning_attempt = next(
            (attempt for attempt in self.previous_attempts 
             if attempt.get('agent_id') == winner_agent_id),
            None
        )
        
        if not winning_attempt:
            logger.error(f"Could not find attempt for winning agent {winner_agent_id}")
            return

        validation_result = winning_attempt.get('validation_result', {})
        
        output = {
            "timestamp": datetime.datetime.now().isoformat(),
            "total_attempts": len(self.previous_attempts),
            "successful_url": winning_attempt['url'],
            "winner_agent_id": winner_agent_id,
            "attempts": self.previous_attempts
        }
        
        # Save JSON output
        json_output = {
            "timestamp": output["timestamp"],
            "total_attempts": output["total_attempts"],
            "successful_url": output["successful_url"],
            "winner_agent_id": output["winner_agent_id"],
            "attempts": [{
                "url": attempt["url"],
                "parent_url": attempt["parent_url"],
                "depth": attempt["depth"],
                "depth_value": attempt["depth_value"],
                "validation_result": attempt["validation_result"],
                "agent_id": attempt.get("agent_id")
            } for attempt in self.previous_attempts]
        }
        
        with open('exploration_results.json', 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4, ensure_ascii=False)
            
        # Save detailed text output
        with open('exploration_results.txt', 'w', encoding='utf-8') as f:
            f.write(f"=== SUCCESSFUL INDEX PAGE FOUND ===\n")
            f.write(f"URL: {winning_attempt['url']}\n")
            f.write(f"Winning Agent ID: {winner_agent_id}\n")
            f.write(f"Validation Confidence: {validation_result['confidence']}\n")
            f.write(f"Total Attempts: {len(self.previous_attempts)}\n\n")
            
            f.write(f"{'='*50} Winning Attempt Details {'='*50}\n")
            f.write(f"URL: {winning_attempt['url']}\n")
            f.write(f"Parent URL: {winning_attempt['parent_url']}\n")
            f.write(f"Depth: {winning_attempt['depth']}\n")
            f.write(f"Depth Value: {winning_attempt['depth_value']}\n")
            
            f.write(f"\nValidation Results:\n")
            f.write(f"- Valid: {validation_result['is_valid']}\n")
            f.write(f"- Confidence: {validation_result['confidence']}\n")
            f.write(f"- Reasoning: {validation_result['reasoning']}\n")
            if validation_result.get('recommendations'):
                f.write("- Recommendations:\n")
                for rec in validation_result['recommendations']:
                    f.write(f"  * {rec}\n")
            
            if 'content' in winning_attempt:
                f.write(f"\nContent Length: {len(winning_attempt['content'])} characters\n")
                f.write("\nContent Preview (first 500 chars):\n")
                f.write(f"{winning_attempt['content'][:500]}...\n")
            
            # Add a summary of all attempts
            f.write(f"\n{'='*50} All Attempts Summary {'='*50}\n")
            for i, attempt in enumerate(self.previous_attempts, 1):
                f.write(f"\nAttempt {i}:\n")
                f.write(f"Agent: {attempt.get('agent_id', 'Unknown')}\n")
                f.write(f"URL: {attempt['url']}\n")
                f.write(f"Valid: {attempt['validation_result']['is_valid']}\n")
                f.write(f"Confidence: {attempt['validation_result']['confidence']}\n")
            
            f.write(f"\n{'='*100}\n")

    async def run(self):
        """Main execution loop"""
        try:
            logger.info("Starting multi-agent web crawling")
            
            # Initialize agents
            self.initialize_agents()
            
            # Initial content fetch and link extraction
            start_url = 'https://www.alamedasheriff.gov/'
            markdown_content = await self.fetch_content(start_url)

            # TODO i think extract links shoudl be replaced with a func that parses links from the markdown content
            initial_extracted = await self.extract_links(start_url, markdown_content)
            self.exploration_links = initial_extracted.links

            while len(self.previous_attempts) < self.max_attempts:
                # Get orchestrator decision based on all agent states
                decision = await self.get_multi_agent_decision(
                    agent_states=self.agents,
                    available_links=self.exploration_links
                )

                logger.info(f"Multi-agent decision: {decision.action}")
                logger.info(f"Rationale: {decision.rationale}")

                # Fix missing target_urls when action is explore_new
                if decision.action == 'explore_new' and not decision.target_urls:
                    # Auto-assign URLs to agents from available unexplored links
                    decision.target_urls = {}
                    available_unexplored = [link for link in self.exploration_links if link.url not in self.visited_urls]
                    
                    for i, agent_id in enumerate(decision.target_agent_ids):
                        if i < len(available_unexplored):
                            decision.target_urls[agent_id] = available_unexplored[i].url
                            logger.info(f"Auto-assigned {agent_id} to {available_unexplored[i].url}")

                if decision.action == 'terminate':
                    logger.info(f"Successfully found the correct index page with agent {decision.winner_agent_id}!")
                    self.winner_agent_id = decision.winner_agent_id
                    break

                # Execute decisions for each targeted agent
                tasks = []
                for agent_id in decision.target_agent_ids:
                    if decision.target_urls and agent_id in decision.target_urls:
                        tasks.append(self.run_agent(agent_id, decision.target_urls[agent_id]))

                # Run agent tasks concurrently
                await asyncio.gather(*tasks)

            # Save results with winner agent id
            await self.save_results(winner_agent_id=getattr(self, 'winner_agent_id', None))

            if len(self.previous_attempts) >= self.max_attempts:
                logger.warning("Reached maximum attempts without finding correct page")
            
        except Exception as e:
            logger.error(f"Error in crawler execution: {str(e)}")
            raise

if __name__ == "__main__":
    crawler = IndexCrawler(num_agents=5)
    asyncio.run(crawler.run())