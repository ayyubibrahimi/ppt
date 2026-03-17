import logging
from typing import Dict, Any, Optional
from request_generator import SimpleRequestGenerator, RequestOption
from form_submitter import FormSubmitter

logger = logging.getLogger(__name__)

class RequestWorkflow:
    def __init__(self, llm_client, driver, screenshot_func):
        self.generator = SimpleRequestGenerator(llm_client)
        self.submitter = FormSubmitter(driver, screenshot_func)
        self.driver = driver
    
    def execute_request_workflow(self, user_topic: str, user_info: Dict[str, str]) -> Dict[str, Any]:
        """Execute the complete request workflow"""
        
        workflow_result = {
            'success': False,
            'user_topic': user_topic,
            'generated_options': None,
            'selected_option': None,
            'request_text': None,
            'submission_result': None,
            'errors': []
        }
        
        try:
            # Step 1: Generate options
            logger.info(f"Generating request options for: '{user_topic}'")
            options = self.generator.generate_request_options(user_topic)
            workflow_result['generated_options'] = options.model_dump()
            
            # Step 2: Present options and get user choice
            logger.info("Presenting options to user")
            selected_option = self._present_options_and_get_choice(options)
            
            if not selected_option:
                workflow_result['errors'].append("No option selected")
                return workflow_result
            
            workflow_result['selected_option'] = selected_option.model_dump()
            
            # Step 3: Generate full request text
            logger.info("Generating full request text")
            user_info['topic'] = user_topic  # Add topic for title generation
            request_text = self.generator.create_full_request_text(selected_option, user_info)
            workflow_result['request_text'] = request_text
            
            # Step 4: Navigate to form
            logger.info("Navigating to request form")
            if not self.submitter.navigate_to_request_form():
                workflow_result['errors'].append("Failed to navigate to form")
                return workflow_result
            
            # Step 5: Submit request
            logger.info("Submitting request")
            submission_result = self.submitter.fill_and_submit_form(request_text, user_info)
            workflow_result['submission_result'] = submission_result
            
            if submission_result['success']:
                workflow_result['success'] = True
                logger.info("✅ Request submitted successfully!")
            else:
                workflow_result['errors'].extend(submission_result['errors'])
                logger.error("❌ Request submission failed")
            
            return workflow_result
            
        except Exception as e:
            logger.error(f"Request workflow failed: {str(e)}")
            workflow_result['errors'].append(f"Workflow error: {str(e)}")
            return workflow_result
    
    def _present_options_and_get_choice(self, options) -> Optional[RequestOption]:
        """Present options to user and get their choice"""
        
        print("\n" + "="*80)
        print("📝 PUBLIC RECORDS REQUEST OPTIONS")
        print("="*80)
        
        # Display each option
        for i, option in enumerate(options.options, 1):
            print(f"\n🔹 OPTION {i}: {option.title}")
            print(f"Context: {option.context}")
            print("This request will ask for:")
            for bullet in option.bullet_points:
                print(f"  • {bullet}")
        
        # Show recommendation
        print(f"\n💡 RECOMMENDATION: {options.recommendation}")
        
        # Get user choice
        print("\n" + "="*80)
        while True:
            try:
                choice = input(f"Select option (1-{len(options.options)}) or 'q' to quit: ").strip()
                
                if choice.lower() == 'q':
                    print("Request cancelled.")
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(options.options):
                    selected = options.options[choice_num - 1]
                    print(f"\n✅ Selected: {selected.title}")
                    
                    # Show preview of full request
                    print(f"\nThis will generate a request asking for:")
                    for bullet in selected.bullet_points:
                        print(f"  • {bullet}")
                    
                    confirm = input("\nProceed with this request? (y/n): ").strip().lower()
                    if confirm == 'y':
                        return selected
                    else:
                        continue
                else:
                    print(f"Please enter a number between 1 and {len(options.options)}")
                    
            except ValueError:
                print("Please enter a valid number or 'q' to quit")
            except KeyboardInterrupt:
                print("\nOperation cancelled")
                return None