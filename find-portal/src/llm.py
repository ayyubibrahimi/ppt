from langchain_openai import AzureChatOpenAI

from dotenv import load_dotenv
load_dotenv()

gpt_4o_mini = AzureChatOpenAI(
    api_version="2024-12-01-preview",
    azure_deployment="gpt-4.1" 
)

gpt_4o = AzureChatOpenAI(
    api_version="2024-12-01-preview",
    azure_deployment="gpt-4.1"
)
